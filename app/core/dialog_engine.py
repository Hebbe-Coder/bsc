"""
对话式需求确认引擎 - DialogEngine

实现Superpowers风格的苏格拉底式需求确认流程：
1. 用户输入简短描述后，系统自动分析并提出澄清问题
2. 支持三种对话深度：轻量/中等/深度
3. 智能跳过已明确的问题
4. 支持API和CLI两种交互模式
5. 对话结束后自动生成完整PRD
6. 支持Agent模式：使用LangChain Agent实现更智能的对话

设计原则：
- 状态管理：使用Session ID跟踪多轮对话
- 智能问题生成：根据用户输入动态调整问题
- LLM增强：使用LLM理解用户意图，生成更精准的问题
- LLM合成：使用LLM将收集的信息合成为专业PRD文档
- 持久化：对话记录持久化到SQLite
- Agent增强：使用LangChain Agent实现工具调用和记忆能力
"""
from __future__ import annotations
import uuid
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

from app.core.preference_db import get_preference_db

logger = logging.getLogger(__name__)


class DialogDepth(str, Enum):
    """对话深度枚举"""
    LIGHT = "light"
    MEDIUM = "medium"
    DEEP = "deep"


class DialogStatus(str, Enum):
    """对话状态枚举"""
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class QuestionTemplate:
    """问题模板"""
    
    def __init__(self, key: str, question: str, 
                 skip_patterns: List[str] = None,
                 follow_up: bool = False):
        self.key = key
        self.question = question
        self.skip_patterns = skip_patterns or []
        self.follow_up = follow_up
    
    def should_skip(self, input_text: str) -> bool:
        """检查是否应该跳过此问题"""
        for pattern in self.skip_patterns:
            if pattern.lower() in input_text.lower():
                return True
        return False


class DialogEngine:
    """对话式需求确认引擎"""
    
    _quality_scorer = None
    _prd_refiner = None
    
    QUESTION_TEMPLATES = {
        DialogDepth.LIGHT: [
            QuestionTemplate(
                key="business_objectives",
                question="这个产品的核心业务目标是什么？",
                skip_patterns=["核心目标", "业务目标", "objective", "goal"]
            ),
            QuestionTemplate(
                key="core_features",
                question="主要包含哪些核心功能模块？",
                skip_patterns=["核心功能", "功能模块", "feature"]
            ),
            QuestionTemplate(
                key="success_criteria",
                question="如何衡量项目成功？",
                skip_patterns=["成功标准", "衡量指标", "KPI"]
            ),
        ],
        DialogDepth.MEDIUM: [
            QuestionTemplate(
                key="business_objectives",
                question="这个产品的核心业务目标是什么？",
                skip_patterns=["核心目标", "业务目标", "objective", "goal"]
            ),
            QuestionTemplate(
                key="core_features",
                question="主要包含哪些核心功能模块？",
                skip_patterns=["核心功能", "功能模块", "feature"]
            ),
            QuestionTemplate(
                key="user_roles",
                question="系统涉及哪些用户角色？",
                skip_patterns=["用户角色", "角色定义", "persona"]
            ),
            QuestionTemplate(
                key="special_requirements",
                question="有没有特殊的技术或业务要求？",
                skip_patterns=["特殊要求", "技术要求", "业务要求"]
            ),
            QuestionTemplate(
                key="non_functional",
                question="对性能、安全等非功能需求有什么要求？",
                skip_patterns=["非功能需求", "性能要求", "安全要求"]
            ),
            QuestionTemplate(
                key="success_criteria",
                question="如何衡量项目成功？",
                skip_patterns=["成功标准", "衡量指标", "KPI"]
            ),
        ],
        DialogDepth.DEEP: [
            QuestionTemplate(
                key="business_objectives",
                question="这个产品的核心业务目标是什么？",
                skip_patterns=["核心目标", "业务目标", "objective", "goal"]
            ),
            QuestionTemplate(
                key="core_features",
                question="主要包含哪些核心功能模块？",
                skip_patterns=["核心功能", "功能模块", "feature"]
            ),
            QuestionTemplate(
                key="user_roles",
                question="系统涉及哪些用户角色？",
                skip_patterns=["用户角色", "角色定义", "persona"]
            ),
            QuestionTemplate(
                key="special_requirements",
                question="有没有特殊的技术或业务要求？",
                skip_patterns=["特殊要求", "技术要求", "业务要求"]
            ),
            QuestionTemplate(
                key="non_functional",
                question="对性能、安全等非功能需求有什么要求？",
                skip_patterns=["非功能需求", "性能要求", "安全要求"]
            ),
            QuestionTemplate(
                key="industry_context",
                question="这个产品在行业中的定位是什么？",
                skip_patterns=["行业定位", "市场定位", "行业背景"]
            ),
            QuestionTemplate(
                key="competitors",
                question="主要竞争对手有哪些？",
                skip_patterns=["竞争对手", "竞品分析", "竞争格局"]
            ),
            QuestionTemplate(
                key="risks",
                question="项目可能面临哪些风险？",
                skip_patterns=["风险评估", "风险分析", "风险识别"]
            ),
            QuestionTemplate(
                key="milestones",
                question="项目的关键里程碑是什么？",
                skip_patterns=["里程碑计划", "项目里程碑", "阶段目标"]
            ),
            QuestionTemplate(
                key="success_criteria",
                question="如何衡量项目成功？",
                skip_patterns=["成功标准", "衡量指标", "KPI"]
            ),
        ],
    }
    
    SECTION_NAMES = {
        "business_objectives": "业务目标",
        "core_features": "核心功能",
        "user_roles": "用户角色",
        "special_requirements": "特殊要求",
        "non_functional": "非功能需求",
        "industry_context": "行业背景",
        "competitors": "竞争分析",
        "risks": "风险评估",
        "milestones": "项目里程碑",
        "success_criteria": "成功标准",
    }
    
    def __init__(self, use_langchain: bool = None, use_agent: bool = None):
        self.db = get_preference_db()
        self._llm_service = None
        self._langchain_service = None
        self._agent_service = None
        self.use_langchain = use_langchain if use_langchain is not None else getattr(
            self._get_settings(), "USE_LANGCHAIN", True
        )
        self.use_agent = use_agent if use_agent is not None else getattr(
            self._get_settings(), "USE_AGENT", False
        )
    
    def _get_settings(self):
        """获取配置设置（懒加载）"""
        from app.core.config import settings
        return settings
    
    @property
    def llm_service(self):
        """懒加载LLM服务"""
        if self._llm_service is None:
            from app.services.llm_service import LLMService
            provider = getattr(self._get_settings(), "LLM_PROVIDER", "mock")
            self._llm_service = LLMService(provider=provider)
        return self._llm_service
    
    @property
    def langchain_service(self):
        """懒加载LangChain服务"""
        if self._langchain_service is None:
            from app.services.langchain_service import LangChainService
            provider = getattr(self._get_settings(), "LLM_PROVIDER", "mock")
            self._langchain_service = LangChainService(provider=provider)
        return self._langchain_service
    
    @property
    def agent_service(self):
        """懒加载LangChain Agent服务"""
        if self._agent_service is None:
            from app.core.langchain_agent import LangChainAgentService
            provider = getattr(self._get_settings(), "LLM_PROVIDER", "mock")
            self._agent_service = LangChainAgentService(provider=provider)
        return self._agent_service
    
    @property
    def quality_scorer(self):
        """懒加载PRD质量评分器"""
        if self._quality_scorer is None:
            from app.core.prd_quality_scorer import PRDQualityScorer
            provider = getattr(self._get_settings(), "LLM_PROVIDER", "mock")
            self._quality_scorer = PRDQualityScorer(provider=provider)
        return self._quality_scorer
    
    @property
    def prd_refiner(self):
        """懒加载PRD精化器"""
        if self._prd_refiner is None:
            from app.core.prd_refiner import PRDRefiner
            provider = getattr(self._get_settings(), "LLM_PROVIDER", "mock")
            self._prd_refiner = PRDRefiner(provider=provider)
        return self._prd_refiner
    
    def agent_chat(self, session_id: str, user_input: str, 
                   user_id: str = None) -> Dict[str, Any]:
        """
        使用Agent进行智能对话
        
        Args:
            session_id: 会话ID
            user_input: 用户输入
            user_id: 用户ID（可选）
            
        Returns:
            对话响应
        """
        if self.use_agent:
            try:
                result = self.agent_service.chat(session_id, user_input, user_id)
                
                if result.get("success"):
                    response_type = result.get("type", "general")
                    
                    if response_type == "prd":
                        session = self.db.get_dialog_session(session_id)
                        if session:
                            prd_text = result["response"].replace("PRD已生成，长度：", "")
                            prd_text = prd_text.split("字\n\n")[1] if "字\n\n" in prd_text else result["response"]
                            self.db.update_dialog_session(session_id, 
                                                          prd_text=prd_text,
                                                          status=DialogStatus.COMPLETED.value)
                
                return result
            except Exception as e:
                logger.error(f"Agent chat failed, falling back: {e}")
        
        return self.answer_question(session_id, user_input, user_id)
    
    def create_session(self, user_id: str, input_text: str, 
                       depth: str = "medium", industry: str = "general") -> Dict[str, Any]:
        """
        创建对话会话
        
        Args:
            user_id: 用户ID
            input_text: 用户输入文本
            depth: 对话深度（light/medium/deep）
            industry: 行业类型
            
        Returns:
            会话信息，包含第一个问题
        """
        depth_enum = self._parse_depth(depth)
        
        session_id = self.db.create_dialog_session(user_id, input_text, depth, industry)
        
        if not session_id:
            return {"error": "Failed to create session"}
        
        user = self.db.get_user(user_id)
        if not user:
            self.db.create_user(user_id, default_depth=depth)
        
        questions = self._generate_questions(input_text, depth_enum)
        
        first_question = questions[0] if questions else None
        if first_question:
            dynamic_question = self._generate_dynamic_question(
                input_text, {}, depth_enum, 1, len(questions), first_question
            )
            if dynamic_question:
                first_question.question = dynamic_question
            
            self.db.add_dialog_message(
                session_id,
                first_question.key,
                first_question.question,
                "",
                1
            )
        
        result = {
            "session_id": session_id,
            "status": DialogStatus.STARTED.value,
            "next_question": first_question.question if first_question else None,
            "question_key": first_question.key if first_question else None,
            "question_number": 1,
            "total_questions": len(questions),
            "context": {
                "industry": industry,
                "input_summary": input_text,
                "depth": depth,
            },
        }
        
        logger.info(f"Created dialog session: {session_id} for user: {user_id}")
        return result
    
    def answer_question(self, session_id: str, answer: str, 
                        user_id: str = None) -> Dict[str, Any]:
        """
        回答问题
        
        Args:
            session_id: 会话ID
            answer: 用户回答
            user_id: 用户ID（可选）
            
        Returns:
            下一个问题或会话完成信息
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        if session["status"] == DialogStatus.COMPLETED.value:
            return {"error": "Session already completed"}
        
        messages = session["messages"]
        collected_data = session["collected_data"].copy()
        
        questions = self._generate_questions(session["input_text"], self._parse_depth(session["depth"]))
        
        current_question_index = len(messages) - 1
        
        if current_question_index >= 0:
            last_msg = messages[current_question_index]
            collected_data[last_msg["question_key"]] = answer
            
            self.db.update_dialog_message_answer(session_id, last_msg["question_number"], answer)
            self.db.update_dialog_session(session_id, collected_data=collected_data)
        
        next_question_index = len(messages)
        
        if next_question_index < len(questions):
            next_question = questions[next_question_index]
            
            dynamic_question = self._generate_dynamic_question(
                session["input_text"],
                collected_data,
                self._parse_depth(session["depth"]),
                next_question_index + 1,
                len(questions),
                next_question
            )
            if dynamic_question:
                next_question.question = dynamic_question
            
            self.db.add_dialog_message(
                session_id,
                next_question.key,
                next_question.question,
                "",
                next_question_index + 1
            )
            
            return {
                "session_id": session_id,
                "status": DialogStatus.IN_PROGRESS.value,
                "next_question": next_question.question,
                "question_key": next_question.key,
                "question_number": next_question_index + 1,
                "total_questions": len(questions),
                "collected_data": collected_data,
            }
        else:
            self.db.update_dialog_session(session_id, status=DialogStatus.COMPLETED.value)
            
            prd_text = self._generate_prd(session)
            
            prd_quality = self._calculate_prd_quality(prd_text, collected_data)
            
            self.db.update_dialog_session(session_id, prd_text=prd_text)
            
            return {
                "session_id": session_id,
                "status": DialogStatus.COMPLETED.value,
                "next_question": None,
                "collected_data": collected_data,
                "prd_text": prd_text,
                "prd_quality": prd_quality,
                "ready_to_compile": True,
            }
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态"""
        return self.db.get_dialog_session(session_id)
    
    def complete_session(self, session_id: str, compile: bool = False) -> Dict[str, Any]:
        """
        结束会话
        
        Args:
            session_id: 会话ID
            compile: 是否直接编译
            
        Returns:
            会话完成信息
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        if session["status"] != DialogStatus.COMPLETED.value:
            self.db.update_dialog_session(session_id, status=DialogStatus.COMPLETED.value)
            
            prd_text = self._generate_prd(session)
            prd_quality = self._calculate_prd_quality(prd_text, session.get("collected_data", {}))
            self.db.update_dialog_session(session_id, prd_text=prd_text)
        else:
            prd_quality = self._calculate_prd_quality(
                session.get("prd_text", ""), 
                session.get("collected_data", {})
            )
        
        result = {
            "session_id": session_id,
            "status": DialogStatus.COMPLETED.value,
            "prd_text": session.get("prd_text") or "",
            "collected_data": session.get("collected_data", {}),
            "prd_quality": prd_quality,
        }
        
        if compile:
            try:
                from app.core.bsc_pipeline import compile_to_business_system
                
                bs = compile_to_business_system(result["prd_text"])
                result["business_system"] = bs
            except Exception as e:
                logger.error(f"Failed to compile: {e}")
                result["compile_error"] = str(e)
        
        return result
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return self.db.delete_dialog_session(session_id)
    
    def get_user_sessions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户会话列表"""
        return self.db.get_user_dialog_sessions(user_id, limit)
    
    def _parse_depth(self, depth: str) -> DialogDepth:
        """解析对话深度"""
        try:
            return DialogDepth(depth.lower())
        except ValueError:
            return DialogDepth.MEDIUM
    
    def _generate_questions(self, input_text: str, depth: DialogDepth) -> List[QuestionTemplate]:
        """
        生成问题列表
        
        智能跳过已在输入中明确的问题
        """
        templates = self.QUESTION_TEMPLATES.get(depth, [])
        questions = []
        
        for template in templates:
            if not template.should_skip(input_text):
                questions.append(template)
        
        return questions
    
    def _generate_dynamic_question(self, input_text: str, collected_data: Dict[str, str],
                                   depth: DialogDepth, question_number: int, 
                                   total_questions: int, 
                                   template: QuestionTemplate) -> Optional[str]:
        """
        使用LangChain生成上下文相关的个性化问题
        
        Args:
            input_text: 用户原始输入
            collected_data: 已收集的数据
            depth: 对话深度
            question_number: 当前问题序号
            total_questions: 总问题数
            template: 问题模板
            
        Returns:
            动态生成的问题，如果失败则返回None
        """
        if self.use_langchain:
            try:
                question_type = self.SECTION_NAMES.get(template.key, template.key)
                result = self.langchain_service.generate_dialog_question(
                    input_text=input_text,
                    collected_data=collected_data,
                    question_type=question_type,
                    question_number=question_number,
                    total_questions=total_questions,
                )
                if result and result.question:
                    return result.question
            except Exception as e:
                logger.debug(f"LangChain dynamic question generation failed: {e}, falling back")
        
        try:
            system_prompt = """你是一个专业的产品需求分析师，擅长通过苏格拉底式提问帮助产品经理理清需求。

请根据用户的输入和已收集的信息，生成一个上下文相关的澄清问题。

要求：
1. 问题必须针对当前对话主题，引用用户提到的具体内容
2. 问题要引导用户提供更具体、更深入的信息
3. 使用自然、友好的语言，避免机械感
4. 只输出问题本身，不要包含其他内容

示例：
用户输入："我要做一个电商系统"
已收集信息：{}
当前问题类型：业务目标
生成："这个电商系统的核心业务目标是什么？比如是提升转化率、降低成本还是增加用户粘性？"

用户输入："我要做一个电商系统"
已收集信息：{"business_objectives": "提升用户转化率"}
当前问题类型：核心功能
生成："为了达成提升转化率的目标，你认为电商系统需要哪些核心功能模块？比如商品推荐、促销活动等？"

用户输入："我要做一个医疗健康APP"
已收集信息：{"business_objectives": "提升患者就医体验"}
当前问题类型：用户角色
生成："这个医疗健康APP主要服务哪些用户角色？是患者、医生还是医院管理人员？"

格式要求：只输出问题，不要任何其他文本。"""
            
            user_prompt = f"""用户输入：{input_text}
已收集信息：{json.dumps(collected_data, ensure_ascii=False)}
当前问题类型：{self.SECTION_NAMES.get(template.key, template.key)}
当前问题序号：{question_number}/{total_questions}
对话深度：{depth.value}

请生成下一个澄清问题："""
            
            response = self.llm_service.chat(system_prompt, user_prompt)
            
            if isinstance(response, dict):
                content = response.get("content", "").strip()
            else:
                content = str(response).strip()
            
            if content and len(content) > 5:
                return content
            
            return None
        except Exception as e:
            logger.debug(f"Dynamic question generation failed: {e}")
            return None
    
    def _generate_prd(self, session: Dict[str, Any]) -> str:
        """
        使用LangChain合成专业PRD文档
        
        Args:
            session: 会话数据
            
        Returns:
            专业级PRD文本
        """
        collected_data = session.get("collected_data", {})
        industry = session.get("industry", "通用")
        input_text = session.get("input_text", "")
        
        if not collected_data:
            return self._generate_fallback_prd(session)
        
        if self.use_langchain:
            try:
                prd_text = self.langchain_service.generate_prd(
                    input_text=input_text,
                    industry=industry,
                    collected_data=collected_data,
                )
                
                if prd_text and len(prd_text) > 100:
                    logger.info("Successfully generated PRD using LangChain")
                    return prd_text
            except Exception as e:
                logger.error(f"LangChain PRD generation failed: {e}, falling back")
        
        try:
            system_prompt = """你是一个资深的产品经理，擅长撰写专业、完整、结构化的产品需求文档（PRD）。

请根据收集到的需求信息，生成一份高质量的PRD文档。

要求：
1. 结构完整：包含业务目标、核心功能、用户角色、业务流程、非功能需求等章节
2. 内容专业：每个章节要有详细的描述，不仅仅是简单罗列
3. 格式规范：使用Markdown格式，标题层级清晰
4. 示例丰富：为每个功能模块提供具体的功能点示例
5. 语言专业但易懂：使用产品经理常用的专业术语，但保持可读性
6. 补充完整：对于用户未明确的内容，基于行业最佳实践进行合理补充

PRD结构要求：
# 产品名称PRD
## 一、产品概述
## 二、业务目标（可量化）
## 三、核心功能模块（每个模块详细描述）
## 四、用户角色与权限
## 五、业务流程图
## 六、非功能需求
## 七、成功标准
## 八、项目里程碑

请确保输出是一份完整、专业的PRD文档，而不是简单的信息罗列。"""
            
            user_prompt = f"""产品名称：{input_text}
行业：{industry}

收集到的需求信息：
{json.dumps(collected_data, ensure_ascii=False, indent=2)}

请基于以上信息，生成一份专业、完整的PRD文档："""
            
            response = self.llm_service.chat(system_prompt, user_prompt)
            
            if isinstance(response, dict):
                prd_text = response.get("content", "")
            else:
                prd_text = str(response)
            
            if prd_text and len(prd_text) > 100:
                logger.info("Successfully generated PRD using LLM")
                return prd_text
            
            logger.warning("LLM PRD generation returned empty or too short, falling back to template")
            return self._generate_fallback_prd(session)
            
        except Exception as e:
            logger.error(f"LLM PRD generation failed: {e}, falling back to template")
            return self._generate_fallback_prd(session)
    
    def _generate_fallback_prd(self, session: Dict[str, Any]) -> str:
        """
        当LLM不可用时，使用模板生成PRD（带丰富示例）
        
        Args:
            session: 会话数据
            
        Returns:
            PRD文本
        """
        collected_data = session.get("collected_data", {})
        industry = session.get("industry", "通用")
        input_text = session.get("input_text", "")
        
        sections = []
        
        objectives = collected_data.get("business_objectives", "待确认")
        sections.append(f"""## 一、业务目标

{self._enhance_section('business_objectives', objectives, industry)}""")
        
        features = collected_data.get("core_features", "待确认")
        sections.append(f"""## 二、核心功能

{self._enhance_section('core_features', features, industry)}""")
        
        roles = collected_data.get("user_roles", "待确认")
        sections.append(f"""## 三、用户角色与权限

{self._enhance_section('user_roles', roles, industry)}""")
        
        sections.append(f"""## 四、业务流程

{self._generate_business_process(collected_data, industry)}""")
        
        nfr = collected_data.get("non_functional", "待确认")
        sections.append(f"""## 五、非功能需求

{self._enhance_section('non_functional', nfr, industry)}""")
        
        success = collected_data.get("success_criteria", "待确认")
        sections.append(f"""## 六、成功标准

{self._enhance_section('success_criteria', success, industry)}""")
        
        milestones = collected_data.get("milestones", "待确认")
        sections.append(f"""## 七、项目里程碑

{self._enhance_section('milestones', milestones, industry)}""")
        
        prd_title = input_text if input_text else f"{industry}产品PRD"
        
        prd_text = f"""# {prd_title}

## 基本信息
- 行业：{industry}
- 生成方式：对话式需求确认

---

{chr(10).join(sections)}

---

## 八、附录

### 需求确认记录
本PRD基于以下对话收集的需求信息生成：
{json.dumps(collected_data, ensure_ascii=False, indent=2)}

### 文档版本
- 版本：v1.0
- 生成时间：自动生成
- 状态：初稿"""
        
        return prd_text
    
    def _enhance_section(self, section_key: str, content: str, industry: str) -> str:
        """
        增强章节内容，添加行业相关示例
        
        Args:
            section_key: 章节Key
            content: 用户输入内容
            industry: 行业类型
            
        Returns:
            增强后的章节内容
        """
        if content == "待确认":
            return self._generate_section_example(section_key, industry)
        
        enhancements = {
            "business_objectives": f"""已确认目标：{content}

建议按照SMART原则细化：
- Specific（具体）：明确目标的具体内容
- Measurable（可衡量）：设定量化指标
- Achievable（可实现）：确保目标可行
- Relevant（相关）：与业务战略对齐
- Time-bound（有时限）：设定完成时间""",
            "core_features": f"""核心功能模块：{content}

建议每个功能模块包含：
- 功能描述：详细说明功能的价值和作用
- 使用场景：描述典型的使用场景
- 优先级：P0/P1/P2/P3
- 验收标准：功能完成的判定标准""",
            "user_roles": f"""用户角色：{content}

建议为每个角色定义：
- 角色描述：该角色的职责和权限
- 使用场景：该角色使用系统的典型场景
- 权限等级：访问权限和操作权限""",
            "non_functional": f"""非功能需求：{content}

建议补充：
- 性能指标：响应时间、QPS、可用性
- 安全要求：数据加密、访问控制
- 合规要求：行业合规标准
- 扩展性：未来扩展能力""",
            "success_criteria": f"""成功标准：{content}

建议设定量化指标：
- 业务指标：转化率、留存率、活跃度
- 技术指标：系统性能、稳定性
- 用户指标：满意度、NPS评分""",
            "milestones": f"""项目里程碑：{content}

建议包含：
- 时间节点：每个里程碑的完成时间
- 交付物：每个阶段的产出
- 验收标准：里程碑完成的判定条件""",
        }
        
        return enhancements.get(section_key, content)
    
    def _generate_section_example(self, section_key: str, industry: str) -> str:
        """生成章节示例"""
        examples = {
            "business_objectives": {
                "general": """## 业务目标示例

- 短期目标（1-3个月）：完成MVP版本上线，验证商业模式
- 中期目标（3-6个月）：获取10000名种子用户，日活用户达到2000
- 长期目标（6-12个月）：实现盈利，建立行业影响力""",
                "retail": """## 业务目标示例

- 提升用户转化率至5%（当前3%）
- 优化订单履约效率，降低配送成本15%
- 增加用户复购率至30%
- 建立完善的会员体系，提升用户粘性""",
                "finance": """## 业务目标示例

- 交易成功率提升至99.9%
- 降低欺诈风险损失率至0.01%
- 合规达标率100%
- 客户满意度提升至95分""",
                "healthcare": """## 业务目标示例

- 提升患者就医体验，减少排队时间50%
- 优化医疗资源配置，提升医生工作效率20%
- 医疗数据安全合规率100%
- 患者满意度提升至90分""",
            },
            "core_features": {
                "general": """## 核心功能示例

### 功能模块1
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用

### 功能模块2
- 功能点1：详细描述功能的价值和作用
- 功能点2：详细描述功能的价值和作用""",
                "retail": """## 核心功能示例

### 商品管理模块
- 商品发布：支持多规格商品、图片上传、库存管理
- 商品搜索：支持关键词搜索、分类筛选、智能推荐
- 商品管理：上下架管理、价格调整、促销活动设置

### 订单系统模块
- 订单创建：支持多种支付方式、地址管理、优惠券使用
- 订单履约：自动化配送流程、物流追踪、退换货管理

### 用户中心模块
- 会员体系：积分和等级制度、成长值计算
- 优惠券：营销活动支持、优惠券发放和使用""",
                "finance": """## 核心功能示例

### 交易处理模块
- 支付接口：支持多种支付渠道、交易路由
- 清算结算：自动清算和结算流程、对账处理

### 风控模块
- 实时风控：毫秒级风险识别、规则引擎
- 反欺诈：多维度欺诈检测、设备指纹""",
                "healthcare": """## 核心功能示例

### 在线挂号模块
- 科室选择：支持多科室挂号、医生筛选
- 预约管理：选择医生和时间、预约确认

### 电子病历模块
- 病历管理：电子病历的创建和查看
- 数据共享：跨机构数据共享、隐私保护""",
            },
            "user_roles": {
                "general": """## 用户角色示例

### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限

### 普通用户
- 职责：使用系统核心功能
- 权限：只读和操作权限

### 运营人员
- 职责：业务运营、数据监控
- 权限：运营相关权限""",
                "retail": """## 用户角色示例

### 消费者
- 职责：浏览商品、下单购买、评价反馈
- 权限：查看商品、提交订单、管理账户

### 商家
- 职责：商品管理、订单处理、数据分析
- 权限：商品上下架、订单处理、数据查看

### 平台运营
- 职责：活动策划、商家管理、平台监控
- 权限：活动配置、商家审核、数据统计""",
                "finance": """## 用户角色示例

### 商户
- 职责：发起交易、查看报表、管理账户
- 权限：交易操作、报表查看、账户管理

### 风控人员
- 职责：风险监控、规则配置、异常处理
- 权限：风险监控、规则管理、异常处理

### 管理员
- 职责：系统管理、用户管理、配置管理
- 权限：全部权限""",
            },
            "non_functional": {
                "general": """## 非功能需求示例

### 性能要求
- 响应时间：核心页面<2秒，API<500ms
- QPS：峰值>1000
- 可用性：99.9%

### 安全要求
- 数据加密：传输加密（HTTPS）、存储加密
- 访问控制：基于角色的权限控制
- 日志审计：完整的操作日志记录

### 合规要求
- 数据合规：符合行业数据保护规范
- 隐私保护：用户隐私数据保护措施""",
                "retail": """## 非功能需求示例

### 性能要求
- 页面响应时间：<1秒
- 峰值QPS：>10000
- 系统可用性：99.9%

### 安全要求
- 支付安全：符合PCI-DSS标准
- 数据加密：传输和存储加密
- 防攻击：防DDoS、防SQL注入

### 合规要求
- 消费者保护：符合消费者权益保护法
- 数据合规：符合个人信息保护法""",
                "finance": """## 非功能需求示例

### 性能要求
- 交易响应时间：<500ms
- 峰值TPS：>10000
- 系统可用性：99.99%

### 安全要求
- 等保合规：等保三级认证
- 数据加密：金融级加密标准
- 访问控制：多重身份认证

### 合规要求
- 监管合规：符合行业监管要求
- 审计日志：完整的操作审计记录""",
            },
            "success_criteria": {
                "general": """## 成功标准示例

### 业务指标
- 用户增长：月活用户增长率>20%
- 转化率：注册转化率>10%
- 留存率：7日留存>40%

### 技术指标
- 系统可用性：>99.9%
- 响应时间：<2秒
- 错误率：<0.1%

### 用户指标
- 用户满意度：>4.5分（5分制）
- NPS评分：>50""",
                "retail": """## 成功标准示例

### 业务指标
- 转化率：>5%
- 复购率：>30%
- GMV增长率：>30%/月

### 技术指标
- 页面响应时间：<1秒
- 系统可用性：99.9%
- 订单成功率：>99.5%

### 用户指标
- 用户满意度：>4.5分
- NPS评分：>50""",
                "finance": """## 成功标准示例

### 业务指标
- 交易成功率：>99.9%
- 欺诈损失率：<0.01%
- 客户增长率：>20%/月

### 技术指标
- 交易响应时间：<500ms
- 系统可用性：99.99%
- 错误率：<0.01%

### 用户指标
- 客户满意度：>95分
- NPS评分：>60""",
            },
            "milestones": {
                "general": """## 项目里程碑示例

### Phase 1：基础功能（第1-4周）
- 完成核心功能开发
- 内部测试通过
- 目标：MVP版本上线

### Phase 2：高级功能（第5-8周）
- 完成高级功能开发
- 性能优化
- 目标：功能完善版本上线

### Phase 3：优化迭代（第9-12周）
- 用户反馈收集和分析
- Bug修复和体验优化
- 目标：稳定运营版本""",
                "retail": """## 项目里程碑示例

### Phase 1：基础电商（第1-4周）
- 商品管理、订单系统开发
- 支付接口集成
- 目标：基础购物流程打通

### Phase 2：用户体系（第5-8周）
- 会员体系开发
- 优惠券系统开发
- 目标：用户运营能力完善

### Phase 3：数据分析（第9-12周）
- 数据报表开发
- 智能推荐上线
- 目标：数据驱动运营""",
                "finance": """## 项目里程碑示例

### Phase 1：基础交易（第1-4周）
- 支付接口开发
- 清算结算开发
- 目标：基础交易流程打通

### Phase 2：风控体系（第5-8周）
- 风控规则引擎开发
- 反欺诈系统开发
- 目标：风控能力完善

### Phase 3：合规审计（第9-12周）
- 合规功能开发
- 审计日志系统开发
- 目标：合规达标""",
            },
        }
        
        industry_key = industry if industry in examples[section_key] else "general"
        return examples.get(section_key, {}).get(industry_key, "请根据实际情况填写。")
    
    def _generate_business_process(self, collected_data: Dict[str, str], industry: str) -> str:
        """生成业务流程"""
        processes = {
            "general": """### 核心业务流程

```mermaid
flowchart TD
    A[用户访问] --> B[浏览产品]
    B --> C[选择功能]
    C --> D[完成操作]
    D --> E[获取结果]
```""",
            "retail": """### 核心业务流程

```mermaid
flowchart TD
    A[用户浏览] --> B[搜索/筛选商品]
    B --> C[查看商品详情]
    C --> D[加入购物车]
    D --> E[提交订单]
    E --> F[选择支付方式]
    F --> G[支付成功]
    G --> H[商家发货]
    H --> I[用户收货]
    I --> J[评价反馈]
```

### 订单流程

```mermaid
flowchart TD
    A[下单] --> B[支付]
    B --> C{支付成功?}
    C -->|是| D[商家接单]
    C -->|否| E[订单取消]
    D --> F[备货发货]
    F --> G[物流配送]
    G --> H[用户签收]
    H --> I[订单完成]
```""",
            "finance": """### 核心业务流程

```mermaid
flowchart TD
    A[发起交易] --> B[风险评估]
    B --> C{风险通过?}
    C -->|是| D[执行交易]
    C -->|否| E[交易拒绝]
    D --> F[清算结算]
    F --> G[完成]
```""",
            "healthcare": """### 核心业务流程

```mermaid
flowchart TD
    A[选择科室] --> B[选择医生]
    B --> C[预约时间]
    C --> D[确认预约]
    D --> E[按时就诊]
    E --> F[医生诊断]
    F --> G[开具处方]
    G --> H[取药/治疗]
```""",
        }
        
        return processes.get(industry, processes["general"])
    
    def _calculate_prd_quality(self, prd_text: str, collected_data: Dict[str, str]) -> float:
        """
        计算PRD质量评分
        
        Args:
            prd_text: PRD文本
            collected_data: 收集的数据
            
        Returns:
            质量评分（0-100）
        """
        score = 0
        factors = []
        
        if prd_text and len(prd_text) > 1000:
            score += 15
            factors.append("PRD长度充足（>1000字）")
        elif prd_text and len(prd_text) > 500:
            score += 10
            factors.append("PRD长度适中（500-1000字）")
        elif prd_text and len(prd_text) > 200:
            score += 5
            factors.append("PRD长度较短（200-500字）")
        
        if collected_data.get("business_objectives") and len(collected_data["business_objectives"]) > 10:
            score += 12
            factors.append("业务目标明确且详细")
        elif collected_data.get("business_objectives"):
            score += 6
            factors.append("业务目标已填写")
        
        if collected_data.get("core_features") and len(collected_data["core_features"]) > 20:
            score += 12
            factors.append("核心功能详细描述")
        elif collected_data.get("core_features"):
            score += 6
            factors.append("核心功能已填写")
        
        if collected_data.get("user_roles") and len(collected_data["user_roles"]) > 10:
            score += 10
            factors.append("用户角色详细定义")
        elif collected_data.get("user_roles"):
            score += 5
            factors.append("用户角色已填写")
        
        if collected_data.get("success_criteria") and len(collected_data["success_criteria"]) > 10:
            score += 10
            factors.append("成功标准量化明确")
        elif collected_data.get("success_criteria"):
            score += 5
            factors.append("成功标准已填写")
        
        if collected_data.get("non_functional") and len(collected_data["non_functional"]) > 10:
            score += 8
            factors.append("非功能需求详细")
        elif collected_data.get("non_functional"):
            score += 4
            factors.append("非功能需求已填写")
        
        if collected_data.get("milestones") and len(collected_data["milestones"]) > 10:
            score += 8
            factors.append("项目里程碑清晰")
        elif collected_data.get("milestones"):
            score += 4
            factors.append("项目里程碑已填写")
        
        required_sections = ["业务目标", "核心功能", "用户角色", "业务流程", "非功能需求", "成功标准", "项目里程碑"]
        found_sections = [s for s in required_sections if s in prd_text]
        
        if len(found_sections) >= 6:
            score += 10
            factors.append("结构完整（6+章节）")
        elif len(found_sections) >= 4:
            score += 6
            factors.append("结构基本完整（4-5章节）")
        elif len(found_sections) >= 2:
            score += 3
            factors.append("结构部分完整（2-3章节）")
        
        if len(collected_data) >= 6:
            score += 5
            factors.append("信息丰富（6+项数据）")
        elif len(collected_data) >= 4:
            score += 3
            factors.append("信息较丰富（4-5项数据）")
        
        if "mermaid" in prd_text or "flowchart" in prd_text:
            score += 5
            factors.append("包含业务流程图")
        
        if "###" in prd_text and "##" in prd_text:
            score += 5
            factors.append("格式规范（三级标题结构）")
        
        score = min(score, 100)
        
        return {
            "score": score,
            "factors": factors,
            "level": self._get_quality_level(score),
            "suggestions": self._generate_quality_suggestions(score, found_sections, collected_data),
        }
    
    def _generate_quality_suggestions(self, score: int, found_sections: List[str], 
                                      collected_data: Dict[str, str]) -> List[str]:
        """
        生成质量改进建议
        
        Args:
            score: 当前评分
            found_sections: 已找到的章节
            collected_data: 收集的数据
            
        Returns:
            改进建议列表
        """
        suggestions = []
        
        required_sections = ["业务目标", "核心功能", "用户角色", "业务流程", "非功能需求", "成功标准", "项目里程碑"]
        missing_sections = [s for s in required_sections if s not in found_sections]
        
        if missing_sections:
            suggestions.append(f"建议补充以下章节：{', '.join(missing_sections)}")
        
        if not collected_data.get("business_objectives") or len(collected_data.get("business_objectives", "")) <= 10:
            suggestions.append("建议详细描述业务目标，包含可量化指标")
        
        if not collected_data.get("core_features") or len(collected_data.get("core_features", "")) <= 20:
            suggestions.append("建议详细描述核心功能模块，包含具体功能点")
        
        if not collected_data.get("success_criteria") or len(collected_data.get("success_criteria", "")) <= 10:
            suggestions.append("建议设定量化的成功标准，如KPI指标")
        
        if "mermaid" not in collected_data.get("business_process", ""):
            suggestions.append("建议添加业务流程图，使用mermaid语法")
        
        if score < 60:
            suggestions.append("建议通过对话式确认补充更多需求信息")
        
        if score >= 60 and score < 80:
            suggestions.append("PRD质量良好，建议进一步细化功能描述")
        
        if score >= 80:
            suggestions.append("PRD质量优秀，可进入编译阶段")
        
        return suggestions
    
    def _get_quality_level(self, score: int) -> str:
        """获取质量等级"""
        if score >= 90:
            return "优秀"
        elif score >= 75:
            return "良好"
        elif score >= 60:
            return "合格"
        elif score >= 40:
            return "需完善"
        else:
            return "需重写"
    
    def score_prd_quality(self, session_id: str) -> Dict[str, Any]:
        """
        评估PRD质量（使用新的两层评分体系）
        
        Args:
            session_id: 会话ID
            
        Returns:
            质量评估报告
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        prd_text = session.get("prd_text", "")
        industry = session.get("industry", "general")
        
        if not prd_text:
            return {"error": "PRD not generated"}
        
        report = self.quality_scorer.score(prd_text, industry)
        
        return {
            "success": True,
            "overall_score": report.overall_score,
            "quality_level": self.quality_scorer.get_quality_level(report.overall_score),
            "is_passed": report.is_passed,
            "dimensions": [d.dict() for d in report.dimensions],
            "summary": report.summary,
            "suggestions": report.suggestions,
            "improvement_points": report.improvement_points,
        }
    
    def refine_prd(self, session_id: str, max_iterations: int = 3, 
                   target_score: int = 80) -> Dict[str, Any]:
        """
        精化PRD文档（多轮迭代优化）
        
        Args:
            session_id: 会话ID
            max_iterations: 最大迭代次数
            target_score: 目标分数
            
        Returns:
            精化结果
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        prd_text = session.get("prd_text", "")
        industry = session.get("industry", "general")
        
        if not prd_text:
            return {"error": "PRD not generated"}
        
        result = self.prd_refiner.refine(prd_text, industry, max_iterations, target_score)
        
        if result.is_improved:
            self.db.update_dialog_session(session_id, prd_text=result.final_prd)
        
        return {
            "success": True,
            "final_prd": result.final_prd,
            "iterations": result.iterations,
            "max_iterations": result.max_iterations,
            "initial_score": result.initial_score,
            "final_score": result.final_score,
            "quality_level": result.quality_level,
            "is_improved": result.is_improved,
            "delta": result.delta,
            "steps": [s.dict() for s in result.steps],
        }
    
    def auto_optimize_prd(self, session_id: str, target_score: int = 80) -> Dict[str, Any]:
        """
        自动优化PRD至目标分数
        
        Args:
            session_id: 会话ID
            target_score: 目标分数
            
        Returns:
            优化结果
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        prd_text = session.get("prd_text", "")
        industry = session.get("industry", "general")
        
        if not prd_text:
            return {"error": "PRD not generated"}
        
        result = self.prd_refiner.auto_optimize(prd_text, industry, target_score)
        
        if result.is_improved:
            self.db.update_dialog_session(session_id, prd_text=result.final_prd)
        
        return {
            "success": True,
            "final_prd": result.final_prd,
            "iterations": result.iterations,
            "initial_score": result.initial_score,
            "final_score": result.final_score,
            "quality_level": result.quality_level,
            "is_improved": result.is_improved,
            "delta": result.delta,
        }


    def get_prd_document(self, session_id: str) -> Dict[str, Any]:
        """
        获取PRD文档的结构化表示（Section树）
        
        Args:
            session_id: 会话ID
            
        Returns:
            PRD文档的结构化数据，包含章节树、标题、行业等信息
        """
        session = self.db.get_dialog_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        prd_text = session.get("prd_text", "")
        if not prd_text:
            return {"error": "PRD not generated"}
        
        from app.core.prd_document import PRDDocumentManager
        
        document = PRDDocumentManager.parse_markdown(prd_text)
        
        return {
            "success": True,
            "document_id": document.id,
            "title": document.title,
            "industry": document.industry,
            "sections": document.get_section_tree(),
            "section_count": len(document.sections),
            "markdown": document.to_markdown(),
            "html": document.to_html(),
        }


__all__ = ["DialogEngine", "DialogDepth", "DialogStatus", "QuestionTemplate"]
