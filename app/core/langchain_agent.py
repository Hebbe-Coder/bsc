"""
LangChain Agent Service - 基于LangChain Agent的智能对话代理

实现高级对话能力：
1. Tool Calling - 自动调用工具完成任务
2. Memory - 对话历史记忆
3. Agent Graph - 基于LangGraph的Agent执行器
4. 多工具支持：PRD生成、问题生成、偏好查询、会话管理、质量评分、PRD精化

设计原则：
- 工具化：将所有能力封装为工具，由Agent自动选择
- 记忆持久化：使用SQLite存储对话历史
- 渐进式增强：保留现有DialogEngine能力，Agent作为增强层
- 可扩展性：易于添加新工具
"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Dict, Any, ClassVar

from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, AIMessage
from app.knowledge.tool import RetrieveKnowledgeTool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from app.services.langchain_service import LangChainService, MockLLM
from app.core.preference_db import get_preference_db
from app.core.prd_quality_scorer import PRDQualityScorer
from app.core.prd_refiner import PRDRefiner

logger = logging.getLogger(__name__)


class PRDGeneratorTool(BaseTool):
    """PRD生成工具"""
    name: str = "generate_prd"
    description: str = "生成产品需求文档(PRD)。当用户明确要求生成PRD或对话结束时使用此工具。"
    
    langchain_service: LangChainService
    db: ClassVar = get_preference_db()
    
    def _run(self, input_text: str, industry: str = "通用", 
             collected_data: str = "{}") -> str:
        """生成PRD文档"""
        try:
            collected_data_dict = json.loads(collected_data)
        except:
            collected_data_dict = {}
        
        prd_text = self.langchain_service.generate_prd(
            input_text=input_text,
            industry=industry,
            collected_data=collected_data_dict,
        )
        
        return f"PRD已生成，长度：{len(prd_text)}字\n\n{prd_text[:2000]}..."


class QuestionGeneratorTool(BaseTool):
    """问题生成工具"""
    name: str = "generate_question"
    description: str = "生成澄清问题。当需要追问用户获取更多信息时使用此工具。"
    
    langchain_service: LangChainService
    
    def _run(self, input_text: str, collected_data: str = "{}", 
             question_type: str = "business_objectives",
             question_number: int = 1, total_questions: int = 5) -> str:
        """生成对话问题"""
        try:
            collected_data_dict = json.loads(collected_data)
        except:
            collected_data_dict = {}
        
        result = self.langchain_service.generate_dialog_question(
            input_text=input_text,
            collected_data=collected_data_dict,
            question_type=question_type,
            question_number=question_number,
            total_questions=total_questions,
        )
        
        return json.dumps({
            "question": result.question,
            "question_type": result.question_type,
            "category": result.category,
            "requires_follow_up": result.requires_follow_up,
        }, ensure_ascii=False)


class PreferenceQueryTool(BaseTool):
    """用户偏好查询工具"""
    name: str = "query_preference"
    description: str = "查询用户偏好信息。当需要了解用户历史偏好时使用此工具。"
    
    db: ClassVar = get_preference_db()
    
    def _run(self, user_id: str) -> str:
        """查询用户偏好"""
        user = self.db.get_user(user_id)
        if not user:
            return "用户不存在或无偏好记录"
        
        preferences = self.db.get_user_preferences(user_id)
        
        return json.dumps({
            "user_id": user_id,
            "default_depth": user.get("default_depth", "medium"),
            "preferences": preferences,
        }, ensure_ascii=False)


class SessionInfoTool(BaseTool):
    """会话信息查询工具"""
    name: str = "get_session_info"
    description: str = "获取当前会话信息。当需要了解对话进度和已收集数据时使用此工具。"
    
    db: ClassVar = get_preference_db()
    
    def _run(self, session_id: str) -> str:
        """获取会话信息"""
        session = self.db.get_dialog_session(session_id)
        if not session:
            return "会话不存在"
        
        return json.dumps({
            "session_id": session_id,
            "status": session.get("status"),
            "input_text": session.get("input_text"),
            "depth": session.get("depth"),
            "industry": session.get("industry"),
            "collected_data": session.get("collected_data", {}),
            "total_messages": len(session.get("messages", [])),
        }, ensure_ascii=False)


class PRDQualityScorerTool(BaseTool):
    """PRD质量评分工具"""
    name: str = "score_prd_quality"
    description: str = "评估PRD文档质量并生成评分报告。当需要检查PRD质量时使用此工具。"
    
    _scorer = None
    
    @property
    def scorer(self):
        if self._scorer is None:
            self._scorer = PRDQualityScorer()
        return self._scorer
    
    def _run(self, prd_text: str, industry: str = "general") -> str:
        """评估PRD质量"""
        report = self.scorer.score(prd_text, industry)
        quality_level = self.scorer.get_quality_level(report.overall_score)
        
        dimensions_text = "\n".join([
            f"- {d.name}: {d.score}分（权重{d.weight}）" 
            for d in report.dimensions
        ])
        
        suggestions_text = "\n".join([f"- {s}" for s in report.suggestions])
        
        return f"""PRD质量评估报告
================

综合评分：{report.overall_score}分
质量等级：{quality_level}
是否合格：{'是' if report.is_passed else '否'}
可改进点：{report.improvement_points}个

各维度评分：
{dimensions_text}

综合评价：
{report.summary}

改进建议：
{suggestions_text}"""


class PRDRefinerTool(BaseTool):
    """PRD精化工具"""
    name: str = "refine_prd"
    description: str = "优化PRD文档质量，支持多轮迭代。当需要提升PRD质量时使用此工具。"
    
    _refiner = None
    
    @property
    def refiner(self):
        if self._refiner is None:
            self._refiner = PRDRefiner()
        return self._refiner
    
    def _run(self, prd_text: str, industry: str = "general", 
             max_iterations: int = 3, target_score: int = 80) -> str:
        """优化PRD文档"""
        result = self.refiner.refine(
            prd_text=prd_text,
            industry=industry,
            max_iterations=max_iterations,
            quality_threshold=target_score
        )
        
        steps_text = ""
        if result.steps:
            steps_text = "\n迭代过程：\n"
            for step in result.steps:
                steps_text += f"- 第{step.iteration}轮: {step.score_before}分 → {step.score_after}分（{step.changes_made}）\n"
        
        return f"""PRD精化完成
============

初始评分：{result.initial_score}分
最终评分：{result.final_score}分
质量等级：{result.quality_level}
迭代次数：{result.iterations}/{result.max_iterations}次
评分提升：{result.delta}分
是否改进：{'是' if result.is_improved else '否'}

{steps_text}

优化后的PRD长度：{len(result.final_prd)}字"""


class IndustryTemplateTool(BaseTool):
    """行业模板查询工具"""
    name: str = "query_industry_template"
    description: str = "查询行业模板和案例。当需要了解特定行业的PRD模板和参考案例时使用此工具。"
    
    db: ClassVar = get_preference_db()
    
    def _run(self, industry: str = "general") -> str:
        """查询行业模板"""
        import os
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "data", "templates", "industry_templates.json"
        )
        
        if not os.path.exists(template_path):
            return "模板文件不存在"
        
        with open(template_path, "r", encoding="utf-8") as f:
            templates = json.load(f)
        
        industry_config = templates.get(industry)
        if not industry_config:
            return f"未找到行业'{industry}'的模板，可用行业: {', '.join(templates.keys())}"
        
        industry_name = industry_config.get("name", industry)
        description = industry_config.get("description", "")
        required_sections = industry_config.get("quality_benchmarks", {}).get("required_sections", [])
        kpi_examples = industry_config.get("kpi_examples", [])
        cases = industry_config.get("cases", [])
        
        kpi_text = "\n".join([f"- {k['name']}: {k['target']}（{k['description']}）" for k in kpi_examples])
        cases_text = "\n".join([f"- {c['name']}（评分{c['quality_score']}）: {c['description']}" for c in cases])
        
        return f"""行业模板信息
=============

行业名称：{industry_name}
行业描述：{description}

必需章节：
{', '.join(required_sections)}

典型KPI指标：
{kpi_text}

参考案例：
{cases_text}"""


class LangChainAgentService:
    """LangChain Agent服务"""
    
    def __init__(self, provider: str = None, use_mock: bool = None):
        self.provider = provider or self._get_settings().LLM_PROVIDER
        self.use_mock = use_mock if use_mock is not None else (self.provider == "mock")
        self._llm = None
        self._agent_graphs: Dict[str, Any] = {}
        self._tools = None
        self._langchain_service = None
        self._checkpointers: Dict[str, MemorySaver] = {}
    
    def _get_settings(self):
        """懒加载配置"""
        from app.core.config import settings
        return settings
    
    @property
    def llm(self):
        """懒加载LLM实例"""
        if self._llm is None:
            if self.use_mock:
                mock_llm = MockLLM()
                from langchain_core.runnables import RunnableLambda
                self._llm = RunnableLambda(mock_llm.invoke)
            else:
                self._llm = self._create_real_llm()
        return self._llm
    
    def _create_real_llm(self):
        """创建真实LLM实例"""
        from langchain_openai import ChatOpenAI
        settings = self._get_settings()
        
        provider_config = {
            "deepseek": {
                "api_key": settings.DEEPSEEK_API_KEY,
                "base_url": settings.DEEPSEEK_BASE_URL,
                "model": settings.DEEPSEEK_MODEL,
            },
            "doubao": {
                "api_key": settings.DOUBAO_API_KEY,
                "base_url": settings.DOUBAO_BASE_URL,
                "model": settings.DOUBAO_MODEL,
            },
            "yuanbao": {
                "api_key": settings.YUANBAO_API_KEY,
                "base_url": settings.YUANBAO_BASE_URL,
                "model": settings.YUANBAO_MODEL,
            },
            "qwen": {
                "api_key": settings.QWEN_API_KEY,
                "base_url": settings.QWEN_BASE_URL,
                "model": settings.QWEN_MODEL,
            },
        }
        
        config = provider_config.get(self.provider)
        if not config or not config["api_key"]:
            logger.warning(f"No valid API key for {self.provider}, falling back to mock")
            self.use_mock = True
            mock_llm = MockLLM()
            from langchain_core.runnables import RunnableLambda
            return RunnableLambda(mock_llm.invoke)
        
        return ChatOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout=settings.LLM_TIMEOUT,
        )
    
    @property
    def langchain_service(self):
        """懒加载LangChainService"""
        if self._langchain_service is None:
            self._langchain_service = LangChainService(provider=self.provider, use_mock=self.use_mock)
        return self._langchain_service
    
    @property
    def tools(self):
        """获取工具列表"""
        if self._tools is None:
            self._tools = [
                PRDGeneratorTool(langchain_service=self.langchain_service),
                QuestionGeneratorTool(langchain_service=self.langchain_service),
                PreferenceQueryTool(),
                SessionInfoTool(),
                PRDQualityScorerTool(),
                PRDRefinerTool(),
                IndustryTemplateTool(),
                RetrieveKnowledgeTool(),
            ]
        return self._tools
    
    def _get_checkpointer(self, session_id: str) -> MemorySaver:
        """获取会话检查点（用于记忆）"""
        if session_id not in self._checkpointers:
            self._checkpointers[session_id] = MemorySaver()
        return self._checkpointers[session_id]
    
    def _build_system_prompt(self):
        """构建系统提示词"""
        return """你是一个专业的产品需求分析助手，擅长通过对话帮助产品经理理清需求并生成高质量的PRD文档。

你的职责：
1. 通过提问收集用户的业务目标、核心功能、用户角色等信息
2. 分析用户输入，识别关键信息
3. 根据收集到的信息生成完整的PRD文档
4. 使用工具完成任务，不要直接回答
5. 生成PRD后进行质量评估，如果质量不达标则自动优化

可用工具：
- generate_prd: 生成产品需求文档
- generate_question: 生成澄清问题
- query_preference: 查询用户偏好
- get_session_info: 获取会话信息
- score_prd_quality: 评估PRD质量
- refine_prd: 优化PRD文档质量
- query_industry_template: 查询行业模板和案例

工作流程：
1. 用户输入产品描述后，使用generate_question生成澄清问题
2. 根据用户回答，逐步收集需求信息
3. 当信息足够时，使用generate_prd生成PRD文档
4. 使用score_prd_quality评估PRD质量
5. 如果评分低于70分，使用refine_prd进行优化
6. 可以使用query_preference了解用户历史偏好
7. 可以使用query_industry_template了解行业模板和案例
8. 可以使用get_session_info了解当前会话状态

请始终使用工具完成任务，不要直接给出答案。"""
    
    def _get_agent_graph(self, session_id: str):
        """获取Agent图"""
        if session_id not in self._agent_graphs:
            system_prompt = self._build_system_prompt()
            checkpointer = self._get_checkpointer(session_id)
            
            self._agent_graphs[session_id] = create_agent(
                model=self.llm,
                tools=self.tools,
                system_prompt=system_prompt,
                checkpointer=checkpointer,
                debug=True,
            )
        
        return self._agent_graphs[session_id]
    
    def chat(self, session_id: str, user_input: str, 
             user_id: str = None) -> Dict[str, Any]:
        """
        与Agent进行对话
        
        Args:
            session_id: 会话ID
            user_input: 用户输入
            user_id: 用户ID
            
        Returns:
            对话响应
        """
        try:
            agent_graph = self._get_agent_graph(session_id)
            
            config = {"configurable": {"thread_id": session_id}}
            
            result = agent_graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config
            )
            
            response_content = ""
            for msg in result.get("messages", []):
                if isinstance(msg, AIMessage):
                    response_content = msg.content
                    break
            
            return {
                "success": True,
                "response": response_content,
                "session_id": session_id,
                "type": self._detect_response_type(response_content),
            }
        except Exception as e:
            logger.error(f"LangChain Agent chat failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "session_id": session_id,
            }
    
    def _detect_response_type(self, response: str) -> str:
        """检测响应类型"""
        if not response:
            return "general"
        
        response_lower = response.lower()
        
        if "PRD已生成" in response or "PRD" in response_lower and ("生成" in response or "文档" in response):
            return "prd"
        if "###" in response and ("产品名称" in response or "业务目标" in response):
            return "prd"
        if "{" in response and "}" in response and ("question" in response_lower or "核心业务目标" in response):
            return "question"
        if "?" in response and len(response) < 100:
            return "question"
        if "用户偏好" in response or "preferences" in response_lower or "默认深度" in response:
            return "preference"
        if "会话信息" in response or "session_id" in response_lower or "collected_data" in response_lower:
            return "session_info"
        if "质量评估" in response or "综合评分" in response or "质量等级" in response:
            return "quality_report"
        if "PRD精化" in response or "精化完成" in response or "优化后" in response:
            return "refined_prd"
        if "行业模板" in response or "行业描述" in response or "参考案例" in response:
            return "industry_template"
        return "general"
    
    def create_session(self, user_id: str, input_text: str, 
                       depth: str = "medium", industry: str = "general") -> Dict[str, Any]:
        """
        创建Agent会话
        
        Args:
            user_id: 用户ID
            input_text: 用户输入文本
            depth: 对话深度
            industry: 行业类型
            
        Returns:
            会话信息
        """
        db = get_preference_db()
        session_id = db.create_dialog_session(user_id, input_text, depth, industry)
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        checkpointer = self._get_checkpointer(session_id)
        
        return {
            "session_id": session_id,
            "status": "started",
            "context": {
                "industry": industry,
                "input_summary": input_text,
                "depth": depth,
            },
        }
    
    def clear_session_memory(self, session_id: str):
        """清除会话记忆"""
        if session_id in self._checkpointers:
            del self._checkpointers[session_id]
        if session_id in self._agent_graphs:
            del self._agent_graphs[session_id]
    
    def score_prd(self, prd_text: str, industry: str = "general") -> Dict[str, Any]:
        """
        评估PRD质量
        
        Args:
            prd_text: PRD文档内容
            industry: 行业类型
            
        Returns:
            质量评估结果
        """
        scorer = PRDQualityScorer(provider=self.provider)
        report = scorer.score(prd_text, industry)
        
        return {
            "success": True,
            "overall_score": report.overall_score,
            "quality_level": scorer.get_quality_level(report.overall_score),
            "is_passed": report.is_passed,
            "dimensions": [d.dict() for d in report.dimensions],
            "summary": report.summary,
            "suggestions": report.suggestions,
            "improvement_points": report.improvement_points,
        }
    
    def refine_prd(self, prd_text: str, industry: str = "general",
                   max_iterations: int = 3, target_score: int = 80) -> Dict[str, Any]:
        """
        精化PRD文档
        
        Args:
            prd_text: PRD文档内容
            industry: 行业类型
            max_iterations: 最大迭代次数
            target_score: 目标分数
            
        Returns:
            精化结果
        """
        refiner = PRDRefiner(provider=self.provider)
        result = refiner.refine(prd_text, industry, max_iterations, target_score)
        
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


__all__ = ["LangChainAgentService", "PRDGeneratorTool", "QuestionGeneratorTool", 
           "PreferenceQueryTool", "SessionInfoTool", "PRDQualityScorerTool", 
           "PRDRefinerTool", "IndustryTemplateTool"]