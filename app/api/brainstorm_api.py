"""Brainstorm API - 头脑风暴接口"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
import logging
import uuid
import json

from app.api.response import ApiResponse
from app.enums import BrainstormMode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brainstorm", tags=["Brainstorm"])


class GenerateIdeasRequest(BaseModel):
    business_domain: str = Field(..., description="业务领域")
    problem: str = Field(..., description="问题描述")
    context: str = Field("", description="背景信息")
    num_ideas: int = Field(10, description="生成数量", ge=1, le=20)
    mode: str = Field("divergent", description="模式：divergent(发散)/convergent(收敛)")
    
    @field_validator("mode")
    def validate_mode(cls, v):
        if v not in {"divergent", "convergent"}:
            raise ValueError(f"无效的模式: {v}，可选值: divergent, convergent")
        return v


class ChainBrainstormRequest(BaseModel):
    business_domain: str = Field(..., description="业务领域")
    problem: str = Field(..., description="问题描述")
    context: str = Field("", description="背景信息")
    rounds: int = Field(3, description="迭代轮数", ge=1, le=5)
    num_ideas_per_round: int = Field(8, description="每轮生成数量", ge=1, le=15)


class MindmapRequest(BaseModel):
    topic: str = Field(..., description="中心主题")
    business_domain: str = Field("", description="业务领域")


class ProblemAnalysisRequest(BaseModel):
    problem: str = Field(..., description="问题描述")
    business_domain: str = Field("", description="业务领域")


class EvaluateIdeasRequest(BaseModel):
    ideas: List[Dict[str, Any]] = Field(..., description="创意列表")
    criteria: Optional[List[str]] = Field(None, description="评估标准列表")


class ExportRequest(BaseModel):
    result: Dict[str, Any] = Field(..., description="头脑风暴结果")
    format: str = Field("json", description="导出格式：json, markdown")
    
    @field_validator("format")
    def validate_format(cls, v):
        if v not in {"json", "markdown"}:
            raise ValueError(f"无效的导出格式: {v}，可选值: json, markdown")
        return v


@router.post("/generate", summary="生成创意想法")
async def generate_ideas(req: GenerateIdeasRequest):
    """
    生成创意想法
    
    根据业务领域和问题描述，使用发散思维模式生成创新解决方案。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    engine = BrainstormEngine()
    result = engine.generate_ideas(
        business_domain=req.business_domain,
        problem=req.problem,
        context=req.context,
        num_ideas=req.num_ideas,
        mode=req.mode,
    )
    
    return ApiResponse.ok(result)


@router.post("/chain", summary="链式头脑风暴")
async def chain_brainstorm(req: ChainBrainstormRequest):
    """
    链式头脑风暴 - 多轮迭代生成创意
    
    通过多轮迭代逐步深化想法，最后筛选出最佳创意。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    engine = BrainstormEngine()
    result = engine.chain_brainstorm(
        business_domain=req.business_domain,
        problem=req.problem,
        context=req.context,
        rounds=req.rounds,
        num_ideas_per_round=req.num_ideas_per_round,
    )
    
    return ApiResponse.ok(result)


@router.post("/converge", summary="收敛创意")
async def converge_ideas(req: EvaluateIdeasRequest):
    """
    收敛创意 - 筛选和优化最佳创意
    
    对已生成的创意进行评估，筛选出最有价值的方案。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    if not req.ideas:
        raise HTTPException(status_code=400, detail=ApiResponse.error("创意列表不能为空", code=400).dict())
    
    engine = BrainstormEngine()
    result = engine.converge_ideas(
        business_domain="",
        ideas=req.ideas,
        top_n=min(5, len(req.ideas)),
    )
    
    return ApiResponse.ok(result)


@router.post("/mindmap", summary="生成思维导图")
async def generate_mindmap(req: MindmapRequest):
    """
    生成思维导图
    
    基于主题和业务领域生成结构化的思维导图数据。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    engine = BrainstormEngine()
    result = engine.generate_mindmap(
        topic=req.topic,
        business_domain=req.business_domain,
    )
    
    return ApiResponse.ok(result)


@router.post("/analyze", summary="问题分析")
async def analyze_problem(req: ProblemAnalysisRequest):
    """
    问题分析
    
    使用多种分析方法（5W1H、鱼骨图等）对问题进行全面分析。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    engine = BrainstormEngine()
    result = engine.analyze_problem(
        problem=req.problem,
        business_domain=req.business_domain,
    )
    
    return ApiResponse.ok(result)


@router.post("/evaluate", summary="评估创意")
async def evaluate_ideas(req: EvaluateIdeasRequest):
    """
    评估创意
    
    根据指定标准对创意进行评分和排序。
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    if not req.ideas:
        raise HTTPException(status_code=400, detail=ApiResponse.error("创意列表不能为空", code=400).dict())
    
    engine = BrainstormEngine()
    result = engine.evaluate_ideas(
        ideas=req.ideas,
        criteria=req.criteria,
    )
    
    return ApiResponse.ok(result)


@router.post("/export", summary="导出头脑风暴结果")
async def export_brainstorm(req: ExportRequest):
    """
    导出头脑风暴结果
    
    支持的格式：
    - json: JSON格式
    - markdown: Markdown格式
    """
    from app.engines.brainstorm_engine import BrainstormEngine
    
    engine = BrainstormEngine()
    
    if req.format == "markdown":
        content = engine.export_to_markdown(req.result)
        media_type = "text/markdown"
        filename = f"brainstorm_{uuid.uuid4().hex[:8]}.md"
    else:
        content = engine.export_to_json(req.result)
        media_type = "application/json"
        filename = f"brainstorm_{uuid.uuid4().hex[:8]}.json"
    
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": media_type,
        },
    )