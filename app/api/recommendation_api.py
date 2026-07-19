"""Recommendation API - 智能推荐接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recommendation", tags=["recommendation"])


class GenerateRecommendationsRequest(BaseModel):
    """生成推荐请求"""
    prd_content: str = Field(..., description="PRD文本内容", min_length=10)
    business_domain: str = Field(..., description="业务领域")
    industry: str = Field("general", description="行业类型")
    template_id: Optional[str] = Field(None, description="模板ID")
    business_system: Optional[Dict[str, Any]] = Field(None, description="业务系统分析结果")


class SaveRecommendationRequest(BaseModel):
    """保存推荐请求"""
    project_id: str = Field(..., description="项目ID")
    type: str = Field("optimization", description="推荐类型")
    content: str = Field(..., description="推荐内容")
    confidence: float = Field(0.5, description="置信度", ge=0.0, le=1.0)
    source: str = Field("system", description="推荐来源")


class AddIndustryPatternRequest(BaseModel):
    """添加行业模式请求"""
    industry: str = Field(..., description="行业类型")
    pattern_type: str = Field("optimization", description="模式类型")
    pattern_name: str = Field(..., description="模式名称")
    pattern_content: str = Field(..., description="模式内容")


@router.post("/generate", summary="生成智能推荐")
async def generate_recommendations(req: GenerateRecommendationsRequest):
    """
    根据PRD内容和历史数据生成智能推荐
    
    推荐来源：
    - 行业最佳实践模式（最高优先级）
    - 相似项目历史经验（中等优先级）
    - 业务系统分析结果（基础优先级）
    
    返回按置信度排序的推荐列表
    """
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    
    recommendations = engine.generate_recommendations(
        prd_content=req.prd_content,
        business_domain=req.business_domain,
        industry=req.industry,
        template_id=req.template_id,
        business_system=req.business_system,
    )
    
    return {
        "success": True,
        "recommendations": recommendations,
        "count": len(recommendations),
    }


@router.post("/save", summary="保存推荐")
async def save_recommendation(req: SaveRecommendationRequest):
    """保存推荐结果到数据库"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    rec_id = engine.save_recommendation(
        project_id=req.project_id,
        rec_type=req.type,
        content=req.content,
        confidence=req.confidence,
        source=req.source,
    )
    
    if not rec_id:
        raise HTTPException(status_code=500, detail={"success": False, "error": "保存推荐失败"})
    
    return {
        "success": True,
        "recommendation_id": rec_id,
        "message": "推荐已保存",
    }


@router.post("/{rec_id}/apply", summary="标记推荐已应用")
async def apply_recommendation(rec_id: str):
    """标记推荐已被应用"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    engine.mark_recommendation_applied(rec_id)
    
    return {
        "success": True,
        "recommendation_id": rec_id,
        "message": "推荐已标记为已应用",
    }


@router.get("/project/{project_id}", summary="获取项目推荐")
async def get_project_recommendations(project_id: str, include_applied: bool = False):
    """获取指定项目的推荐列表"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    recommendations = engine.get_project_recommendations(project_id, include_applied)
    
    return {
        "success": True,
        "project_id": project_id,
        "recommendations": recommendations,
        "count": len(recommendations),
    }


@router.post("/industry-pattern", summary="添加行业模式")
async def add_industry_pattern(req: AddIndustryPatternRequest):
    """添加或更新行业最佳实践模式"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    engine.add_industry_pattern(
        industry=req.industry,
        pattern_type=req.pattern_type,
        pattern_name=req.pattern_name,
        pattern_content=req.pattern_content,
    )
    
    return {
        "success": True,
        "message": "行业模式已添加/更新",
    }


@router.get("/industry-pattern/{industry}", summary="获取行业模式")
async def get_industry_patterns(industry: str, pattern_type: str = "optimization", top_n: int = 10):
    """获取指定行业的最佳实践模式"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    patterns = engine.get_industry_patterns(industry, pattern_type, top_n)
    
    return {
        "success": True,
        "industry": industry,
        "patterns": patterns,
        "count": len(patterns),
    }


@router.get("/history", summary="获取编译历史")
async def get_compile_history(industry: str = None, limit: int = 20):
    """获取编译历史记录"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    history = engine.get_compile_history(industry, limit)
    
    return {
        "success": True,
        "history": history,
        "count": len(history),
    }


@router.get("/stats", summary="获取编译统计")
async def get_compile_stats(industry: str = None):
    """获取编译统计信息"""
    from app.engines.recommendation_engine import get_recommendation_engine
    
    engine = get_recommendation_engine()
    stats = engine.get_compile_stats(industry)
    
    return {
        "success": True,
        "stats": stats,
    }
