from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, AsyncGenerator
import time

import asyncio
import json
import uuid

from app.chains.prd_analysis_chain import PrdAnalysisChain
from app.chains.objective_extraction_chain import ObjectiveExtractionChain
from app.chains.kpi_extraction_chain import KpiExtractionChain
from app.chains.chart_generation_chain import ChartGenerationChain
from app.chains.risk_assessment_chain import RiskAssessmentChain
from app.chains.strategy_analysis_chain import StrategyAnalysisChain
from app.chains.presentation_generation_chain import PresentationGenerationChain
from app.chains.report_generation_chain import ReportGenerationChain
from app.core.cache import CacheManager, ExecutionHistory

router = APIRouter(prefix="/api/skill", tags=["skills"])

executions: Dict[str, Dict[str, Any]] = {}

CHAIN_REGISTRY = {
    "prd-analysis": PrdAnalysisChain,
    "objective-extraction": ObjectiveExtractionChain,
    "kpi-extraction": KpiExtractionChain,
    "chart-generation": ChartGenerationChain,
    "risk-assessment": RiskAssessmentChain,
    "strategy-analysis": StrategyAnalysisChain,
    "presentation-generation": PresentationGenerationChain,
    "report-generation": ReportGenerationChain,
}

INPUT_MAPPING = {
    "prd-analysis": "prd_content",
    "objective-extraction": "business_content",
    "kpi-extraction": "business_content",
    "chart-generation": "data_description",
    "risk-assessment": "business_context",
    "strategy-analysis": "business_info",
    "presentation-generation": "business_content",
    "report-generation": "business_content",
}


class ExecuteSkillRequest(BaseModel):
    skill_id: str
    params: Dict[str, Any]
    llm_provider: str = "deepseek"
    model_name: str = ""
    streaming: bool = False
    use_cache: bool = True


class SkillExecutionResponse(BaseModel):
    execution_id: str
    status: str
    result: Optional[str] = None
    from_cache: bool = False


async def execute_skill_async(execution_id: str, skill_id: str, params: Dict[str, Any], 
                              provider: str, model_name: str, use_cache: bool = True):
    start_time = time.time()
    
    try:
        if use_cache:
            cached_result = await CacheManager.get_cached_result(skill_id, params)
            if cached_result:
                executions[execution_id]["status"] = "completed"
                executions[execution_id]["result"] = cached_result
                executions[execution_id]["from_cache"] = True
                
                duration_ms = int((time.time() - start_time) * 1000)
                await ExecutionHistory.add_record(
                    execution_id=execution_id,
                    skill_id=skill_id,
                    status="completed",
                    params=params,
                    result=cached_result,
                    duration_ms=duration_ms,
                )
                return
        
        chain_class = CHAIN_REGISTRY.get(skill_id)
        if not chain_class:
            executions[execution_id]["status"] = "failed"
            executions[execution_id]["result"] = f"Skill {skill_id} not found"
            
            duration_ms = int((time.time() - start_time) * 1000)
            await ExecutionHistory.add_record(
                execution_id=execution_id,
                skill_id=skill_id,
                status="failed",
                params=params,
                error=f"Skill {skill_id} not found",
                duration_ms=duration_ms,
            )
            return
        
        chain = chain_class.create(provider, model_name)
        input_key = INPUT_MAPPING.get(skill_id, "input")
        input_data = {input_key: params.get(input_key, params.get("input", ""))}
        
        result = await chain.ainvoke(input_data)
        result_str = str(result)
        
        executions[execution_id]["status"] = "completed"
        executions[execution_id]["result"] = result_str
        executions[execution_id]["from_cache"] = False
        
        if use_cache:
            await CacheManager.set_cached_result(skill_id, params, result_str)
        
        duration_ms = int((time.time() - start_time) * 1000)
        await ExecutionHistory.add_record(
            execution_id=execution_id,
            skill_id=skill_id,
            status="completed",
            params=params,
            result=result_str,
            duration_ms=duration_ms,
        )
        
    except Exception as e:
        executions[execution_id]["status"] = "failed"
        executions[execution_id]["result"] = str(e)
        
        duration_ms = int((time.time() - start_time) * 1000)
        await ExecutionHistory.add_record(
            execution_id=execution_id,
            skill_id=skill_id,
            status="failed",
            params=params,
            error=str(e),
            duration_ms=duration_ms,
        )


async def stream_skill_output(execution_id: str, skill_id: str, params: Dict[str, Any],
                               provider: str, model_name: str) -> AsyncGenerator[str, None]:
    start_time = time.time()
    
    try:
        chain_class = CHAIN_REGISTRY.get(skill_id)
        if not chain_class:
            yield json.dumps({"status": "failed", "error": f"Skill {skill_id} not found"})
            return
        
        chain = chain_class.create(provider, model_name)
        input_key = INPUT_MAPPING.get(skill_id, "input")
        input_data = {input_key: params.get(input_key, params.get("input", ""))}
        
        full_result = ""
        async for chunk in chain.astream(input_data):
            full_result += chunk
            yield f"data: {json.dumps({'content': chunk, 'status': 'running'})}\n\n"
            await asyncio.sleep(0.01)
        
        executions[execution_id]["status"] = "completed"
        executions[execution_id]["result"] = full_result
        
        await CacheManager.set_cached_result(skill_id, params, full_result)
        
        duration_ms = int((time.time() - start_time) * 1000)
        await ExecutionHistory.add_record(
            execution_id=execution_id,
            skill_id=skill_id,
            status="completed",
            params=params,
            result=full_result,
            duration_ms=duration_ms,
        )
        
        yield f"data: {json.dumps({'content': '', 'status': 'completed'})}\n\n"
        
    except Exception as e:
        executions[execution_id]["status"] = "failed"
        executions[execution_id]["result"] = str(e)
        
        duration_ms = int((time.time() - start_time) * 1000)
        await ExecutionHistory.add_record(
            execution_id=execution_id,
            skill_id=skill_id,
            status="failed",
            params=params,
            error=str(e),
            duration_ms=duration_ms,
        )
        
        yield f"data: {json.dumps({'content': '', 'status': 'failed', 'error': str(e)})}\n\n"


@router.post("/execute")
async def execute_skill(request: ExecuteSkillRequest, background_tasks: BackgroundTasks):
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"
    
    executions[execution_id] = {
        "skill_id": request.skill_id,
        "status": "running",
        "result": None,
        "streaming": request.streaming,
        "params": request.params,
        "provider": request.llm_provider,
        "model_name": request.model_name,
        "from_cache": False,
    }
    
    if request.use_cache:
        cached_result = await CacheManager.get_cached_result(request.skill_id, request.params)
        if cached_result:
            executions[execution_id]["status"] = "completed"
            executions[execution_id]["result"] = cached_result
            executions[execution_id]["from_cache"] = True
            return SkillExecutionResponse(
                execution_id=execution_id,
                status="completed",
                result=cached_result,
                from_cache=True,
            )
    
    if request.streaming:
        return SkillExecutionResponse(execution_id=execution_id, status="streaming")
    
    background_tasks.add_task(
        execute_skill_async,
        execution_id,
        request.skill_id,
        request.params,
        request.llm_provider,
        request.model_name,
        request.use_cache,
    )
    
    return SkillExecutionResponse(execution_id=execution_id, status="running")


@router.get("/stream/{execution_id}")
async def stream_skill(execution_id: str):
    execution = executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    if not execution.get("streaming"):
        raise HTTPException(status_code=400, detail="This execution is not streaming")
    
    return StreamingResponse(
        stream_skill_output(
            execution_id,
            execution["skill_id"],
            execution["params"],
            execution["provider"],
            execution["model_name"],
        ),
        media_type="text/event-stream",
    )


@router.get("/execution/{execution_id}")
async def get_execution(execution_id: str):
    execution = executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {
        "execution_id": execution_id,
        "skill_id": execution["skill_id"],
        "status": execution["status"],
        "result": execution["result"],
        "from_cache": execution.get("from_cache", False),
    }


@router.get("/list")
async def list_skills():
    return [
        {"id": "prd-analysis", "name": "PRD分析", "description": "分析产品需求文档"},
        {"id": "objective-extraction", "name": "目标提取", "description": "从业务内容提取目标"},
        {"id": "kpi-extraction", "name": "KPI提取", "description": "识别关键绩效指标"},
        {"id": "chart-generation", "name": "图表生成", "description": "生成ECharts配置"},
        {"id": "risk-assessment", "name": "风险评估", "description": "评估业务风险"},
        {"id": "strategy-analysis", "name": "战略分析", "description": "SWOT分析和战略规划"},
        {"id": "presentation-generation", "name": "演示文稿生成", "description": "生成PPT大纲"},
        {"id": "report-generation", "name": "报告生成", "description": "生成业务分析报告"},
    ]


@router.get("/history")
async def get_execution_history(limit: int = Query(20, ge=1, le=100)):
    history = await ExecutionHistory.get_history(limit)
    return {
        "history": history,
        "total": len(history),
    }


@router.get("/cache/stats")
async def get_cache_stats():
    stats = await CacheManager.get_cache_stats()
    return stats


@router.delete("/cache/{skill_id}")
async def clear_skill_cache(skill_id: str):
    all_keys = list(executions.keys())
    for key in all_keys:
        if executions[key].get("skill_id") == skill_id:
            del executions[key]
    
    await CacheManager.clear_local_cache()
    return {"message": f"Cache cleared for skill: {skill_id}"}
