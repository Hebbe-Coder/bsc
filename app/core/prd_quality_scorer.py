import json
import os
import re
from typing import Dict, List
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from app.core.config import settings
from app.core.llm_policy import ensure_fallback_allowed, ensure_mock_allowed

logger = __import__('logging').getLogger(__name__)


class QualityDimension(BaseModel):
    name: str = Field(description="维度名称")
    score: int = Field(description="分数（0-100）")
    max_score: int = Field(default=100, description="满分")
    weight: float = Field(default=0.0, description="权重")
    feedback: str = Field(description="改进建议")
    details: str = Field(description="详细说明")


class QualityReport(BaseModel):
    overall_score: int = Field(description="总分（0-100）")
    dimensions: List[QualityDimension] = Field(description="各维度评分")
    summary: str = Field(description="综合评价")
    suggestions: List[str] = Field(description="改进建议列表")
    is_passed: bool = Field(description="是否达到合格标准")
    improvement_points: int = Field(description="可改进的点数")


class LLMQualityResult(BaseModel):
    completeness: int = Field(description="内容完整性评分（0-100）")
    specificity: int = Field(description="描述详细度评分（0-100）")
    actionability: int = Field(description="可执行性评分（0-100）")
    coherence: int = Field(description="逻辑连贯性评分（0-100）")
    industry_relevance: int = Field(description="行业相关性评分（0-100）")
    summary: str = Field(description="综合评价")
    suggestions: List[str] = Field(description="改进建议")


class PRDQualityScorer:
    """PRD质量评分器 - 两层评分体系"""
    
    def __init__(self, provider: str = None):
        self.settings = settings
        self.provider = provider or self.settings.LLM_PROVIDER
        self.use_mock = self.provider == "mock"
        self._llm = None
        self._langchain_service = None
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
                ensure_mock_allowed("PRD Quality")
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
                        temperature=0.2
                    )
                except ImportError:
                    ensure_fallback_allowed("PRD Quality")
                    from app.services.llm_service import MockLLM
                    mock_llm = MockLLM()
                    self._llm = RunnableLambda(mock_llm.invoke)
        return self._llm
    
    def _calculate_rule_based_score(self, prd_text: str, industry: str = "general") -> Dict:
        """
        规则启发式评分 - 快速评估PRD质量
        
        评估维度：
        1. 长度检查
        2. 必需章节覆盖
        3. 章节深度（段落数）
        4. 结构化程度（标题层级）
        5. 业务指标完整性
        """
        scores = []
        total_weight = 0
        
        industry_config = self.templates.get(industry, self.templates.get("general", {}))
        benchmarks = industry_config.get("quality_benchmarks", {})
        section_weights = benchmarks.get("section_weights", {})
        required_sections = benchmarks.get("required_sections", [])
        min_length = benchmarks.get("minimum_length", 1500)
        
        prd_text = prd_text or ""
        text_length = len(prd_text)
        
        length_score = min(100, int(text_length / min_length * 100))
        scores.append(QualityDimension(
            name="内容完整性",
            score=length_score,
            weight=0.25,
            feedback=f"当前长度：{text_length}字，建议至少{min_length}字" if text_length < min_length else "内容长度达标",
            details=f"文本长度评估：{text_length}/{min_length}"
        ))
        total_weight += 0.25
        
        section_count = 0
        for section in required_sections:
            if section in prd_text:
                section_count += 1
        
        section_score = int(section_count / len(required_sections) * 100) if required_sections else 100
        missing_sections = [s for s in required_sections if s not in prd_text]
        scores.append(QualityDimension(
            name="章节覆盖度",
            score=section_score,
            weight=0.20,
            feedback=f"缺失章节：{', '.join(missing_sections)}" if missing_sections else "所有必需章节已覆盖",
            details=f"覆盖章节：{section_count}/{len(required_sections)}"
        ))
        total_weight += 0.20
        
        paragraphs = [p for p in prd_text.split('\n') if p.strip() and not p.strip().startswith('#')]
        paragraph_score = min(100, int(len(paragraphs) / 30 * 100))
        scores.append(QualityDimension(
            name="内容丰富度",
            score=paragraph_score,
            weight=0.15,
            feedback=f"当前{len(paragraphs)}个段落，建议至少30个段落" if len(paragraphs) < 30 else "段落数量达标",
            details=f"段落数量：{len(paragraphs)}"
        ))
        total_weight += 0.15
        
        headings = len(re.findall(r'^#{1,3}\s', prd_text, re.MULTILINE))
        heading_score = min(100, int(headings / 15 * 100))
        scores.append(QualityDimension(
            name="结构化程度",
            score=heading_score,
            weight=0.15,
            feedback=f"当前{headings}个标题，建议至少15个标题" if headings < 15 else "标题数量达标",
            details=f"标题数量：{headings}"
        ))
        total_weight += 0.15
        
        kpi_count = len(re.findall(r'(目标|指标|KPI|成功率|增长率|转化率|完成率)', prd_text))
        kpi_score = min(100, int(kpi_count / 10 * 100))
        scores.append(QualityDimension(
            name="业务指标",
            score=kpi_score,
            weight=0.15,
            feedback=f"当前{kpi_count}个业务指标相关表述，建议至少10个" if kpi_count < 10 else "业务指标丰富",
            details=f"业务指标提及次数：{kpi_count}"
        ))
        total_weight += 0.15
        
        overall_score = sum(d.score * d.weight for d in scores)
        
        suggestions = []
        for dim in scores:
            if dim.score < 60:
                suggestions.append(f"{dim.name}不足：{dim.feedback}")
        
        return {
            "overall_score": int(overall_score),
            "dimensions": scores,
            "summary": f"规则评分：{int(overall_score)}分，共发现{len(suggestions)}个改进点",
            "suggestions": suggestions,
            "is_passed": overall_score >= 60,
            "improvement_points": len(suggestions)
        }
    
    def _calculate_llm_based_score(self, prd_text: str, industry: str = "general") -> Dict:
        """
        LLM评估评分 - 深度评估PRD质量
        
        评估维度：
        1. 完整性：是否覆盖所有必要内容
        2. 详细度：描述是否具体可执行
        3. 可执行性：方案是否可落地
        4. 连贯性：逻辑是否清晰
        5. 行业相关性：是否符合行业特点
        """
        parser = PydanticOutputParser(pydantic_object=LLMQualityResult)
        
        industry_name = self.templates.get(industry, {}).get("name", "通用行业")
        
        prompt = PromptTemplate(
            template="""你是一个专业的PRD质量评估专家。请对以下PRD文档进行深度评估。
            
行业：{industry_name}

PRD文档：
{prd_text}

请从以下维度进行评分（0-100分）：
1. 完整性：是否覆盖业务目标、核心功能、用户角色、业务流程、非功能需求等必要内容
2. 详细度：描述是否具体、可量化，是否有足够的细节支撑开发
3. 可执行性：方案是否可落地，是否有明确的优先级和里程碑
4. 连贯性：逻辑是否清晰，各部分之间是否有合理的关联
5. 行业相关性：是否符合{industry_name}的行业特点和最佳实践

{format_instructions}
""",
            input_variables=["prd_text", "industry_name"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )
        
        try:
            chain = prompt | self.llm | parser
            result = chain.invoke({
                "prd_text": prd_text,
                "industry_name": industry_name
            })
            
            scores = []
            weights = {
                "completeness": 0.20,
                "specificity": 0.25,
                "actionability": 0.25,
                "coherence": 0.15,
                "industry_relevance": 0.15
            }
            
            scores.append(QualityDimension(
                name="完整性",
                score=result.completeness,
                weight=weights["completeness"],
                feedback="",
                details=""
            ))
            scores.append(QualityDimension(
                name="详细度",
                score=result.specificity,
                weight=weights["specificity"],
                feedback="",
                details=""
            ))
            scores.append(QualityDimension(
                name="可执行性",
                score=result.actionability,
                weight=weights["actionability"],
                feedback="",
                details=""
            ))
            scores.append(QualityDimension(
                name="连贯性",
                score=result.coherence,
                weight=weights["coherence"],
                feedback="",
                details=""
            ))
            scores.append(QualityDimension(
                name="行业相关性",
                score=result.industry_relevance,
                weight=weights["industry_relevance"],
                feedback="",
                details=""
            ))
            
            overall_score = sum(d.score * d.weight for d in scores)
            
            return {
                "overall_score": int(overall_score),
                "dimensions": scores,
                "summary": result.summary,
                "suggestions": result.suggestions,
                "is_passed": overall_score >= 70,
                "improvement_points": sum(1 for d in scores if d.score < 70)
            }
        except Exception as e:
            if settings.is_production:
                raise
            logger.error(f"LLM质量评估失败：{e}")
            return {
                "overall_score": 50,
                "dimensions": [],
                "summary": "LLM评估失败，使用默认评分",
                "suggestions": ["无法进行深度评估，建议检查LLM配置"],
                "is_passed": False,
                "improvement_points": 1
            }
    
    def score(self, prd_text: str, industry: str = "general", 
              use_llm: bool = True) -> QualityReport:
        """
        综合评分 - 结合规则启发式和LLM评估
        
        Args:
            prd_text: PRD文档内容
            industry: 行业类型
            use_llm: 是否使用LLM进行深度评估
            
        Returns:
            QualityReport: 质量报告
        """
        rule_result = self._calculate_rule_based_score(prd_text, industry)
        
        if use_llm and rule_result["overall_score"] < 90:
            llm_result = self._calculate_llm_based_score(prd_text, industry)
            
            combined_dimensions = []
            for rule_dim, llm_dim in zip(rule_result["dimensions"], llm_result["dimensions"]):
                combined_score = int(rule_dim.score * 0.3 + llm_dim.score * 0.7)
                combined_dimensions.append(QualityDimension(
                    name=rule_dim.name,
                    score=combined_score,
                    weight=rule_dim.weight,
                    feedback=llm_dim.feedback or rule_dim.feedback,
                    details=llm_dim.details or rule_dim.details
                ))
            
            overall_score = int(rule_result["overall_score"] * 0.3 + llm_result["overall_score"] * 0.7)
            suggestions = list(set(rule_result["suggestions"] + llm_result["suggestions"]))
            summary = f"综合评分：{overall_score}分\n规则评分：{rule_result['overall_score']}分\nLLM评分：{llm_result['overall_score']}分\n\n{llm_result['summary']}"
        else:
            combined_dimensions = rule_result["dimensions"]
            overall_score = rule_result["overall_score"]
            suggestions = rule_result["suggestions"]
            summary = rule_result["summary"]
        
        return QualityReport(
            overall_score=overall_score,
            dimensions=combined_dimensions,
            summary=summary,
            suggestions=suggestions,
            is_passed=overall_score >= 70,
            improvement_points=len(suggestions)
        )
    
    def get_quality_level(self, score: int) -> str:
        """根据分数获取质量等级"""
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 70:
            return "合格"
        elif score >= 60:
            return "待改进"
        else:
            return "不合格"
