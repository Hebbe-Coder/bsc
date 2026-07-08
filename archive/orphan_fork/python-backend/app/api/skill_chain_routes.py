from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import uuid

from app.api.skill_routes import CHAIN_REGISTRY, INPUT_MAPPING, executions

router = APIRouter(prefix="/api/skill-chain", tags=["skill-chains"])


class SkillChainStep(BaseModel):
    skill_id: str
    params: Dict[str, Any]
    input_mapping: Optional[Dict[str, str]] = None


class ExecuteSkillChainRequest(BaseModel):
    steps: List[SkillChainStep]
    llm_provider: str = "deepseek"
    model_name: str = ""
    streaming: bool = False


class SkillChainExecutionResponse(BaseModel):
    chain_id: str
    status: str
    results: Optional[List[Dict[str, Any]]] = None


async def execute_skill_chain_async(chain_id: str, steps: List[SkillChainStep],
                                     provider: str, model_name: str):
    results = []
    previous_output = {}
    
    try:
        for index, step in enumerate(steps):
            executions[f"{chain_id}-step-{index}"] = {
                "skill_id": step.skill_id,
                "status": "running",
                "result": None,
                "streaming": False,
            }
            
            chain_class = CHAIN_REGISTRY.get(step.skill_id)
            if not chain_class:
                raise ValueError(f"Skill {step.skill_id} not found")
            
            chain = chain_class.create(provider, model_name)
            input_key = INPUT_MAPPING.get(step.skill_id, "input")
            
            params = step.params.copy()
            if step.input_mapping:
                for target_key, source_key in step.input_mapping.items():
                    if source_key in previous_output:
                        params[target_key] = previous_output[source_key]
                    elif source_key.startswith("$"):
                        source_key = source_key[1:]
                        for prev_result in results:
                            if source_key in prev_result:
                                params[target_key] = prev_result[source_key]
                                break
            
            input_data = {input_key: params.get(input_key, params.get("input", ""))}
            
            result = await chain.ainvoke(input_data)
            
            step_result = {
                "step_index": index,
                "skill_id": step.skill_id,
                "result": str(result),
                "status": "completed",
            }
            results.append(step_result)
            previous_output = {"result": str(result)}
            
            executions[f"{chain_id}-step-{index}"]["status"] = "completed"
            executions[f"{chain_id}-step-{index}"]["result"] = str(result)
        
        executions[chain_id] = {
            "status": "completed",
            "results": results,
            "steps": steps,
        }
        
    except Exception as e:
        executions[chain_id] = {
            "status": "failed",
            "error": str(e),
            "results": results,
        }


@router.post("/execute")
async def execute_skill_chain(request: ExecuteSkillChainRequest, background_tasks: BackgroundTasks):
    chain_id = f"chain-{uuid.uuid4().hex[:8]}"
    
    executions[chain_id] = {
        "status": "running",
        "results": None,
        "steps": request.steps,
        "provider": request.llm_provider,
        "model_name": request.model_name,
    }
    
    background_tasks.add_task(
        execute_skill_chain_async,
        chain_id,
        request.steps,
        request.llm_provider,
        request.model_name,
    )
    
    return SkillChainExecutionResponse(chain_id=chain_id, status="running")


@router.get("/execution/{chain_id}")
async def get_chain_execution(chain_id: str):
    execution = executions.get(chain_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Chain execution not found")
    
    return {
        "chain_id": chain_id,
        "status": execution["status"],
        "results": execution.get("results"),
        "error": execution.get("error"),
        "steps_count": len(execution.get("steps", [])),
    }


@router.post("/preview")
async def preview_skill_chain(request: ExecuteSkillChainRequest):
    preview = []
    
    for index, step in enumerate(request.steps):
        chain_class = CHAIN_REGISTRY.get(step.skill_id)
        if chain_class:
            preview.append({
                "step_index": index,
                "skill_id": step.skill_id,
                "input_key": INPUT_MAPPING.get(step.skill_id, "input"),
                "params": step.params.keys(),
                "input_mapping": step.input_mapping,
                "valid": True,
            })
        else:
            preview.append({
                "step_index": index,
                "skill_id": step.skill_id,
                "valid": False,
                "error": f"Skill {step.skill_id} not found",
            })
    
    return {
        "preview": preview,
        "total_steps": len(request.steps),
        "valid_steps": sum(1 for p in preview if p["valid"]),
    }
