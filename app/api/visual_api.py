"""
Visual API - 可视化图表生成接口

提供业务流程图、思维导图、时序图、状态图的生成和导出功能。
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import PlainTextResponse, FileResponse
from typing import Dict, Any, Optional
import os

from app.visual.flow_chart_generator import FlowChartGenerator

router = APIRouter(prefix="/visual", tags=["Visual"])


@router.post("/flowchart", response_class=PlainTextResponse, summary="生成业务流程图")
async def generate_flowchart(business_system: Dict[str, Any] = Body(...)):
    """生成业务流程图Mermaid代码"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_flowchart(business_system)
    return mermaid_code


@router.post("/mindmap", response_class=PlainTextResponse, summary="生成思维导图")
async def generate_mindmap(business_system: Dict[str, Any] = Body(...)):
    """生成思维导图Mermaid代码"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_mindmap(business_system)
    return mermaid_code


@router.post("/sequence", response_class=PlainTextResponse, summary="生成时序图")
async def generate_sequence_diagram(business_system: Dict[str, Any] = Body(...)):
    """生成时序图Mermaid代码"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_sequence_diagram(business_system)
    return mermaid_code


@router.post("/state", response_class=PlainTextResponse, summary="生成状态图")
async def generate_state_diagram(business_system: Dict[str, Any] = Body(...)):
    """生成状态图Mermaid代码"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_state_diagram(business_system)
    return mermaid_code


@router.post("/all", summary="生成所有图表")
async def generate_all_charts(business_system: Dict[str, Any] = Body(...)):
    """生成所有类型的图表Mermaid代码"""
    generator = FlowChartGenerator()
    return generator.generate_all(business_system)


@router.post("/flowchart/svg", summary="生成业务流程图SVG")
async def generate_flowchart_svg(business_system: Dict[str, Any] = Body(...)):
    """生成业务流程图并渲染为SVG"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_flowchart(business_system)
    
    try:
        output_path = generator.render_to_svg(mermaid_code)
        return FileResponse(output_path, media_type="image/svg+xml", filename="flowchart.svg")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mindmap/svg", summary="生成思维导图SVG")
async def generate_mindmap_svg(business_system: Dict[str, Any] = Body(...)):
    """生成思维导图并渲染为SVG"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_mindmap(business_system)
    
    try:
        output_path = generator.render_to_svg(mermaid_code)
        return FileResponse(output_path, media_type="image/svg+xml", filename="mindmap.svg")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flowchart/png", summary="生成业务流程图PNG")
async def generate_flowchart_png(business_system: Dict[str, Any] = Body(...)):
    """生成业务流程图并渲染为PNG"""
    generator = FlowChartGenerator()
    mermaid_code = generator.generate_flowchart(business_system)
    
    try:
        output_path = generator.render_to_png(mermaid_code)
        return FileResponse(output_path, media_type="image/png", filename="flowchart.png")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))