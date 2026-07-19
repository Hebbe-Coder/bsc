import json
import os
from typing import Dict, List
from pydantic import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from app.core.config import settings
from app.core.prd_quality_scorer import PRDQualityScorer

logger = __import__('logging').getLogger(__name__)


class RefinementStep(BaseModel):
    iteration: int = Field(description="迭代次数")
    score_before: int = Field(description="优化前评分")
    score_after: int = Field(description="优化后评分")
    improvements: List[str] = Field(description="改进点")
    changes_made: str = Field(description="具体修改内容")


class RefinementResult(BaseModel):
    final_prd: str = Field(description="最终PRD内容")
    iterations: int = Field(description="迭代次数")
    max_iterations: int = Field(description="最大迭代次数")
    initial_score: int = Field(description="初始评分")
    final_score: int = Field(description="最终评分")
    quality_level: str = Field(description="质量等级")
    steps: List[RefinementStep] = Field(description="迭代步骤")
    is_improved: bool = Field(description="是否有改进")
    delta: int = Field(description="评分提升幅度")


class PRDRefiner:
    """PRD精化器 - 支持多轮迭代优化"""
    
    def __init__(self, provider: str = None):
        self.settings = settings
        self.provider = provider or self.settings.LLM_PROVIDER
        self.use_mock = self.provider == "mock"
        self._llm = None
        self._scorer = None
        self._templates = None
    
    @property
    def templates(self):
        """加载行业模板"""
        if self._templates is None:
            template_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "app", "data", "templates", "industry_templates.json"
            )
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    self._templates = json.load(f)
            else:
                self._templates = {}
        return self._templates
    
    @property
    def llm(self):
        """懒加载LLM"""
        if self._llm is None:
            if self.use_mock:
                from app.services.llm_service import MockLLM
                mock_llm = MockLLM()
                self._llm = RunnableLambda(mock_llm.invoke)
            else:
                try:
                    from langchain_openai import ChatOpenAI
                    self._llm = ChatOpenAI(
                        model=self.settings.OPENAI_MODEL,
                        api_key=self.settings.OPENAI_API_KEY,
                        base_url=self.settings.OPENAI_API_BASE,
                        temperature=0.3
                    )
                except ImportError:
                    from app.services.llm_service import MockLLM
                    mock_llm = MockLLM()
                    self._llm = RunnableLambda(mock_llm.invoke)
        return self._llm
    
    @property
    def scorer(self):
        """懒加载质量评分器"""
        if self._scorer is None:
            self._scorer = PRDQualityScorer(provider=self.provider)
        return self._scorer
    
    def _generate_refinement_prompt(self, prd_text: str, quality_report: Dict, 
                                   industry: str = "general") -> str:
        """
        生成精化提示词
        
        Args:
            prd_text: 当前PRD内容
            quality_report: 质量报告
            industry: 行业类型
            
        Returns:
            str: 精化提示词
        """
        industry_name = self.templates.get(industry, {}).get("name", "通用行业")
        industry_cases = self.templates.get(industry, {}).get("cases", [])
        
        case_examples = ""
        if industry_cases:
            case_examples = "\n\n参考案例：\n"
            for case in industry_cases[:2]:
                case_examples += f"- {case['name']}（评分：{case['quality_score']}）：{case['description']}\n"
                case_examples += f"  核心功能：{', '.join(case['key_features'])}\n"
        
        suggestions_text = "\n".join([f"- {s}" for s in quality_report.get("suggestions", [])])
        
        prompt = PromptTemplate(
            template="""你是一个专业的PRD优化专家。请根据质量评估结果，对以下PRD进行优化。
            
行业：{industry_name}
当前评分：{current_score}分
质量等级：{quality_level}

需要改进的问题：
{suggestions}

{case_examples}

优化要求：
1. 根据问题列表，针对性地完善缺失内容
2. 增强描述的详细度和可执行性
3. 补充具体的业务指标和成功标准
4. 确保逻辑连贯性和行业相关性
5. 保持原有的文档结构和格式
6. 只输出优化后的PRD内容，不要添加额外说明

当前PRD：
{prd_text}

请输出优化后的PRD：
""",
            input_variables=["prd_text", "current_score", "quality_level", 
                            "suggestions", "industry_name", "case_examples"]
        )
        
        return prompt
    
    def refine(self, prd_text: str, industry: str = "general", 
               max_iterations: int = 3, quality_threshold: int = 70,
               min_delta: int = 5) -> RefinementResult:
        """
        多轮迭代精化PRD
        
        Args:
            prd_text: 原始PRD内容
            industry: 行业类型
            max_iterations: 最大迭代次数（默认3次）
            quality_threshold: 质量阈值（默认70分）
            min_delta: 最小改进幅度（默认5分）
            
        Returns:
            RefinementResult: 精化结果
        """
        steps = []
        current_prd = prd_text
        initial_score = 0
        final_score = 0
        
        for iteration in range(1, max_iterations + 1):
            quality_report = self.scorer.score(current_prd, industry)
            
            if iteration == 1:
                initial_score = quality_report.overall_score
            
            if quality_report.overall_score >= quality_threshold:
                final_score = quality_report.overall_score
                break
            
            if iteration > 1:
                prev_score = steps[-1].score_after
                if (quality_report.overall_score - prev_score) < min_delta:
                    logger.info(f"改进幅度不足{min_delta}分，停止迭代")
                    final_score = quality_report.overall_score
                    break
            
            logger.info(f"迭代{iteration}: 当前评分{quality_report.overall_score}分，开始优化")
            
            quality_level = self.scorer.get_quality_level(quality_report.overall_score)
            
            prompt = self._generate_refinement_prompt(
                prd_text=current_prd,
                quality_report=quality_report.dict(),
                industry=industry
            )
            
            chain = prompt | self.llm | StrOutputParser()
            
            try:
                refined_prd = chain.invoke({
                    "prd_text": current_prd,
                    "current_score": quality_report.overall_score,
                    "quality_level": quality_level,
                    "suggestions": "\n".join([f"- {s}" for s in quality_report.suggestions]),
                    "industry_name": self.templates.get(industry, {}).get("name", "通用行业"),
                    "case_examples": ""
                })
                
                refined_prd = refined_prd.strip()
                
                if not refined_prd:
                    logger.warning("优化后PRD为空，停止迭代")
                    final_score = quality_report.overall_score
                    break
                
                new_quality_report = self.scorer.score(refined_prd, industry)
                
                step = RefinementStep(
                    iteration=iteration,
                    score_before=quality_report.overall_score,
                    score_after=new_quality_report.overall_score,
                    improvements=quality_report.suggestions,
                    changes_made=f"优化后评分提升{new_quality_report.overall_score - quality_report.overall_score}分"
                )
                steps.append(step)
                
                current_prd = refined_prd
                final_score = new_quality_report.overall_score
                
                logger.info(f"迭代{iteration}完成: 评分从{quality_report.overall_score}提升至{new_quality_report.overall_score}")
                
                if new_quality_report.overall_score >= quality_threshold:
                    break
                    
            except Exception as e:
                logger.error(f"迭代{iteration}优化失败：{e}")
                final_score = quality_report.overall_score
                break
        
        if not steps:
            quality_report = self.scorer.score(current_prd, industry)
            initial_score = quality_report.overall_score
            final_score = quality_report.overall_score
        
        quality_level = self.scorer.get_quality_level(final_score)
        
        return RefinementResult(
            final_prd=current_prd,
            iterations=len(steps),
            max_iterations=max_iterations,
            initial_score=initial_score,
            final_score=final_score,
            quality_level=quality_level,
            steps=steps,
            is_improved=final_score > initial_score,
            delta=final_score - initial_score
        )
    
    def suggest_improvements(self, prd_text: str, industry: str = "general", 
                            count: int = 5) -> List[str]:
        """
        仅获取改进建议，不执行优化
        
        Args:
            prd_text: PRD内容
            industry: 行业类型
            count: 建议数量
            
        Returns:
            List[str]: 改进建议列表
        """
        quality_report = self.scorer.score(prd_text, industry)
        return quality_report.suggestions[:count]
    
    def auto_optimize(self, prd_text: str, industry: str = "general",
                      target_score: int = 80) -> RefinementResult:
        """
        自动优化至目标分数
        
        Args:
            prd_text: PRD内容
            industry: 行业类型
            target_score: 目标分数
            
        Returns:
            RefinementResult: 精化结果
        """
        quality_report = self.scorer.score(prd_text, industry)
        
        if quality_report.overall_score >= target_score:
            return RefinementResult(
                final_prd=prd_text,
                iterations=0,
                max_iterations=0,
                initial_score=quality_report.overall_score,
                final_score=quality_report.overall_score,
                quality_level=self.scorer.get_quality_level(quality_report.overall_score),
                steps=[],
                is_improved=False,
                delta=0
            )
        
        iterations_needed = min(5, int((target_score - quality_report.overall_score) / 10) + 2)
        
        return self.refine(
            prd_text=prd_text,
            industry=industry,
            max_iterations=iterations_needed,
            quality_threshold=target_score
        )
