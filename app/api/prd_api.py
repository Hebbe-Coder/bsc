"""PRD API - PRD智能解析与模板引导接口"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from app.api.response import ApiResponse
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prd", tags=["PRD Analysis"])


class AnalyzeRequest(BaseModel):
    """PRD分析请求"""
    prd_text: str = Field(..., description="PRD文本内容", min_length=10)
    use_llm: bool = Field(False, description="是否使用LLM增强解析")


class CompileWithAnalysisRequest(BaseModel):
    """带分析的编译请求"""
    prd_text: str = Field(..., description="PRD文本内容", min_length=10)
    analyze_first: bool = Field(True, description="是否先进行PRD分析")
    template_id: Optional[str] = Field(None, description="模板ID")
    output_types: List[str] = Field(default=["html", "json"], description="输出格式")


@router.post("/analyze", summary="分析PRD文档")
async def analyze_prd(req: AnalyzeRequest):
    """
    分析PRD文档结构，提取关键信息，检测缺失项，给出补全建议
    
    分析内容：
    - PRD结构解析：提取业务目标、核心功能、性能要求等章节
    - 行业检测：自动识别PRD所属行业
    - 缺失项检测：检测必要章节是否缺失
    - 质量评估：计算PRD完整性分数
    - 智能建议：提供补全建议和优化方向
    
    使用LLM增强（use_llm=true）：
    - 更准确的语义理解
    - 提取关键目标和功能
    - 识别潜在风险
    - 给出专业改进建议
    """
    from app.engines.prd_analyzer import PRDAnalyzer
    
    analyzer = PRDAnalyzer()
    result = analyzer.analyze(req.prd_text, use_llm=req.use_llm)
    
    return ApiResponse.ok(result)


@router.get("/templates", summary="获取PRD模板列表")
async def list_templates():
    """获取所有可用的PRD模板"""
    from app.engines.prd_analyzer import PRDTemplateManager
    
    templates = PRDTemplateManager.list_templates()
    
    return ApiResponse.ok({
        "templates": templates,
        "count": len(templates),
    })


@router.get("/templates/{template_key}", summary="获取PRD模板详情")
async def get_template(template_key: str):
    """获取指定模板的详细信息和填写指南"""
    from app.engines.prd_analyzer import PRDTemplateManager
    
    guide = PRDTemplateManager.generate_prd_guide(template_key)
    
    if not guide:
        raise HTTPException(status_code=404, detail=ApiResponse.not_found("模板不存在").dict())
    
    return ApiResponse.ok(guide)


@router.post("/templates/recommend", summary="推荐PRD模板")
async def recommend_template(prd_text: str):
    """根据PRD内容推荐最合适的行业模板"""
    from app.engines.prd_analyzer import PRDTemplateManager
    
    template_key = PRDTemplateManager.recommend_template(prd_text)
    guide = PRDTemplateManager.generate_prd_guide(template_key)
    
    return ApiResponse.ok({
        "recommended_template": template_key,
        "template_name": guide.get("template_name", ""),
        "industry": guide.get("industry", ""),
        "guide": guide,
    })


class PersonalizedTemplateRequest(BaseModel):
    """个性化模板请求"""
    user_id: str = Field(..., description="用户ID")
    industry: str = Field("general", description="行业类型")
    input_text: str = Field("", description="用户输入文本")


@router.post("/templates/personalized", summary="获取个性化PRD模板")
async def get_personalized_template(req: PersonalizedTemplateRequest):
    """
    根据用户偏好和行业获取个性化PRD模板
    
    使用用户历史偏好学习，生成定制化的模板结构：
    - 按用户常用章节排序
    - 过滤不常用章节
    - 提供个性化示例
    """
    from app.core.template_customizer import TemplateCustomizer
    
    customizer = TemplateCustomizer()
    template = customizer.get_template_with_examples(req.user_id, req.industry, req.input_text)
    
    return ApiResponse.ok({
        "template": template,
        "industry": req.industry,
        "section_count": len(template.get("sections", [])),
    })


@router.post("/compile", summary="PRD分析+编译")
async def prd_analyze_and_compile(
    req: CompileWithAnalysisRequest,
    request: Request = None,
):
    """
    PRD分析 + 编译一站式流程
    
    流程：
    1. 分析PRD结构和质量
    2. （可选）根据分析结果推荐模板
    3. 调用BSC Pipeline进行编译
    4. 返回分析结果和编译结果
    
    使用场景：
    - 产品经理提交PRD后，先看到分析反馈
    - 根据分析结果决定是否补充PRD
    - 一键进入编译流程
    """
    from app.engines.prd_analyzer import PRDAnalyzer
    
    analyzer = PRDAnalyzer()
    analysis_result = analyzer.analyze(req.prd_text, use_llm=False)
    
    if not req.analyze_first or analysis_result["prd_quality"] >= 60:
        from app.capabilities.runner import run_legacy_bsc_runtime

        compile_result = await run_legacy_bsc_runtime(
            input_text=req.prd_text,
            template_id=req.template_id,
            tenant_id=str(
                getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID)
                if request is not None
                else settings.DEFAULT_TENANT_ID
            ),
            project_id=str(
                getattr(request.state, "project_id", "") if request is not None else ""
            ),
        )
        
        bs = compile_result["business_system"]
        
        visuals = []
        if "html" in req.output_types or "json" in req.output_types:
            try:
                from app.engines.visual_binding import bind_visuals
                visual_result = bind_visuals(bs)
                visuals = visual_result.get("visuals", []) if isinstance(visual_result, dict) else visual_result
            except Exception:
                pass
        
        return ApiResponse.ok({
            "analysis": analysis_result,
            "pipeline": compile_result["pipeline"],
            "business_system": bs,
            "composed": bs.get("composed", {}),
            "workspace": compile_result.get("workspace", {}),
            "visuals": visuals,
            "summary": compile_result["summary"],
            "output_types": req.output_types,
            "compiled": True,
        })
    else:
        return ApiResponse.ok({
            "analysis": analysis_result,
            "compiled": False,
            "message": f"PRD质量分数为{analysis_result['prd_quality']}%，建议补充缺失内容后再编译",
            "recommendations": analysis_result["recommendations"],
        })


@router.get("/guide", summary="获取PRD编写指南")
async def get_prd_guide(industry: str = "general"):
    """获取指定行业的PRD编写指南"""
    from app.engines.prd_analyzer import PRDTemplateManager
    
    template_key = PRDTemplateManager.recommend_template(f"行业：{industry}")
    guide = PRDTemplateManager.generate_prd_guide(template_key)
    
    return ApiResponse.ok({
        "industry": industry,
        **guide,
    })
