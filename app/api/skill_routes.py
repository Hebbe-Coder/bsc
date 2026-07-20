from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.chains.chart_generation_chain import ChartGenerationChain
from app.chains.kpi_extraction_chain import KpiExtractionChain
from app.chains.objective_extraction_chain import ObjectiveExtractionChain
from app.chains.presentation_generation_chain import PresentationGenerationChain
from app.chains.prd_analysis_chain import PrdAnalysisChain
from app.chains.report_generation_chain import ReportGenerationChain
from app.chains.risk_assessment_chain import RiskAssessmentChain
from app.chains.strategy_analysis_chain import StrategyAnalysisChain
from app.services.cache_service import get_cache_service
from app.skills.registry import build_skill_registry

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
    llm_provider: str = "mock"
    model_name: str = ""
    streaming: bool = False
    use_cache: bool = True


class SkillExecutionResponse(BaseModel):
    execution_id: str
    status: str
    result: Optional[str] = None
    from_cache: bool = False


def generate_cache_key(skill_id: str, params: dict, revision: str = "") -> str:
    params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    combined = f"{skill_id}:{revision}:{params_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _skill_execution(skill_id: str, params: Dict[str, Any]):
    registry = build_skill_registry()
    manifest = registry.get(skill_id)
    if manifest is None:
        raise KeyError(f"Skill {skill_id} not found")
    chain_id = registry.resolve_chain(skill_id)
    chain_class = CHAIN_REGISTRY.get(chain_id)
    if chain_class is None:
        raise PermissionError(f"Skill {skill_id} has no approved execution entrypoint")

    chain_input_key = INPUT_MAPPING.get(chain_id, "input")
    declared_input = manifest.inputs[0].name if manifest.inputs else chain_input_key
    input_value = params.get(
        declared_input,
        params.get(chain_input_key, params.get("input", "")),
    )
    if manifest.prompt:
        input_value = f"{manifest.prompt}\n\nInput:\n{input_value}"
    return manifest, chain_class, {chain_input_key: input_value}


async def execute_skill_async(
    execution_id: str,
    skill_id: str,
    params: Dict[str, Any],
    provider: str,
    model_name: str,
    use_cache: bool = True,
):
    try:
        cache = get_cache_service()
        manifest, chain_class, input_data = _skill_execution(skill_id, params)

        if use_cache:
            cache_key = generate_cache_key(skill_id, params, manifest.revision)
            cached_result = cache.get(cache_key)
            if cached_result:
                executions[execution_id]["status"] = "completed"
                executions[execution_id]["result"] = cached_result
                executions[execution_id]["from_cache"] = True
                return

        chain = chain_class.create(provider, model_name)
        result = await chain.ainvoke(input_data)
        result_str = str(result)

        executions[execution_id]["status"] = "completed"
        executions[execution_id]["result"] = result_str
        executions[execution_id]["from_cache"] = False

        if use_cache:
            cache_key = generate_cache_key(skill_id, params, manifest.revision)
            cache.set(cache_key, result_str, ttl=3600)
    except Exception as exc:
        executions[execution_id]["status"] = "failed"
        executions[execution_id]["result"] = str(exc)


async def stream_skill_output(
    execution_id: str,
    skill_id: str,
    params: Dict[str, Any],
    provider: str,
    model_name: str,
) -> AsyncGenerator[str, None]:
    try:
        manifest, chain_class, input_data = _skill_execution(skill_id, params)
        chain = chain_class.create(provider, model_name)

        full_result = ""
        async for chunk in chain.astream(input_data):
            chunk_text = str(chunk)
            full_result += chunk_text
            yield f"data: {json.dumps({'content': chunk_text, 'status': 'running'})}\n\n"
            await asyncio.sleep(0.01)

        executions[execution_id]["status"] = "completed"
        executions[execution_id]["result"] = full_result

        cache = get_cache_service()
        cache_key = generate_cache_key(skill_id, params, manifest.revision)
        cache.set(cache_key, full_result, ttl=3600)
        yield f"data: {json.dumps({'content': '', 'status': 'completed'})}\n\n"
    except Exception as exc:
        executions[execution_id]["status"] = "failed"
        executions[execution_id]["result"] = str(exc)
        yield f"data: {json.dumps({'content': '', 'status': 'failed', 'error': str(exc)})}\n\n"


@router.post("/execute")
async def execute_skill(request: ExecuteSkillRequest, background_tasks: BackgroundTasks):
    try:
        manifest, _, _ = _skill_execution(request.skill_id, request.params)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        cache = get_cache_service()
        cache_key = generate_cache_key(request.skill_id, request.params, manifest.revision)
        cached_result = cache.get(cache_key)
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
    registry = build_skill_registry()
    return [manifest.public_payload() for manifest in registry.list()]


@router.get("/cache/stats")
async def get_cache_stats():
    return get_cache_service().stats()


@router.delete("/cache/{skill_id}")
async def clear_skill_cache(skill_id: str):
    for key in list(executions):
        if executions[key].get("skill_id") == skill_id:
            del executions[key]
    get_cache_service().clear(pattern=skill_id)
    return {"message": f"Cache cleared for skill: {skill_id}"}
