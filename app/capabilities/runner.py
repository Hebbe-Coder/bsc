"""Shared construction and response mapping for BusinessRuntime executions."""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.artifacts import ArtifactGraphStore
from app.capabilities import (
    BusinessRuntime,
    MissionGraph,
    MissionPlanner,
    MissionStep,
    MultiAgentBoard,
    RuntimeResult,
    build_default_registry,
)
from app.core.context_policy import ContextItem, ContextManager, ContextPolicy


def new_project_id(prefix: str = "agent") -> str:
    """Create a request-scoped project id instead of using global placeholders."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def scoped_artifact_dir(
    data_dir: str,
    project_id: str,
    execution_id: str,
    tenant_id: str = "",
) -> str:
    """Return the tenant/project/execution directory for artifact isolation."""
    root = Path(data_dir)
    if tenant_id:
        root = root / _safe_path_segment(tenant_id)
    return str(root / _safe_path_segment(project_id) / _safe_path_segment(execution_id))


async def run_business_runtime(
    *,
    input_text: str,
    domain: str = "",
    mode: str = "template",
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    board: bool = False,
    data_dir: str = "./data/artifacts",
    executor_backend: str = "nanobot",
    max_iterations: int = 3,
    context_policy: ContextPolicy | str = ContextPolicy.FRESH,
    context_items: list[ContextItem | dict[str, Any]] | None = None,
    context_max_tokens: int = 12_000,
    event_sink: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """Execute the shared BusinessRuntime and map it to the Agent OS API shape."""
    scoped_project_id = project_id.strip() if project_id else new_project_id()
    scoped_execution_id = execution_id.strip() if execution_id else new_project_id("run")
    artifact_scope = scoped_artifact_dir(
        data_dir,
        scoped_project_id,
        scoped_execution_id,
        tenant_id,
    )
    store = ArtifactGraphStore(
        data_dir=artifact_scope,
        tenant_id=tenant_id,
        project_id=scoped_project_id,
        session_id=scoped_execution_id,
    )
    registry = build_default_registry()
    planner = MissionPlanner(registry=registry, mode=mode)
    runtime_kwargs = {
        "store": store,
        "registry": registry,
        "planner": planner,
        "max_iterations": max_iterations,
        "executor_backend": executor_backend,
    }
    if event_sink is not None and _accepts_keyword(BusinessRuntime, "event_sink"):
        runtime_kwargs["event_sink"] = event_sink
    runtime = BusinessRuntime(
        **runtime_kwargs,
    )

    context_packet = ContextManager(max_tokens=context_max_tokens).build(
        input_text,
        policy=context_policy,
        inherited_items=context_items or [],
    )
    result = await runtime.run(
        prd_text=context_packet.rendered_input,
        domain_hint=domain,
        project_id=scoped_project_id,
    )

    board_payload = None
    if board:
        board_result = await MultiAgentBoard(store).convene(project_id=scoped_project_id)
        board_payload = {
            "verdict": board_result.final_verdict,
            "consensus": board_result.consensus,
            "votes": board_result.votes,
        }

    return _runtime_result_to_agent_response(
        result=result,
        project_id=scoped_project_id,
        execution_id=scoped_execution_id,
        artifact_scope=artifact_scope,
        board=board_payload,
        context_usage=context_packet.usage.model_dump(mode="json"),
    )


class _LegacyBSCCompatibilityPlanner:
    """Fixed one-step plan that makes the legacy compiler a Runtime capability."""

    def __init__(self, capability_name: str) -> None:
        self._capability_name = capability_name

    async def plan(
        self, prd_text: str, domain_hint: str = "", goals: Any = None
    ) -> MissionGraph:
        del prd_text, goals
        return MissionGraph(
            mission_id=f"compatibility_{self._capability_name}",
            mission="legacy_bsc_compatibility",
            title="Legacy BSC Compatibility",
            domain=domain_hint,
            planning_mode="compatibility",
            steps=[
                MissionStep(
                    step_id=self._capability_name,
                    capability_name=self._capability_name,
                    parallel_group=0,
                )
            ],
            required_capabilities=[self._capability_name],
        )


async def run_legacy_bsc_runtime(
    *,
    input_text: str,
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    template_id: str | None = None,
    async_mode: bool = True,
    llm_service: Any = None,
    legacy_context: dict[str, Any] | None = None,
    data_dir: str = "./data/artifacts",
) -> dict[str, Any]:
    """Execute the legacy compiler as a scoped BusinessRuntime capability."""
    result = await _run_legacy_runtime(
        input_text=input_text,
        project_id=project_id,
        execution_id=execution_id,
        tenant_id=tenant_id,
        data_dir=data_dir,
        capability_name="legacy_bsc_compatibility",
        execution_context={
            "template_id": template_id or "",
            "async_mode": async_mode,
            "llm_service": llm_service,
            "legacy_context": legacy_context or {},
        },
    )
    if result.errors:
        raise RuntimeError(result.errors[0])
    return _legacy_compile_payload(result)


def run_legacy_bsc_runtime_sync(**kwargs: Any) -> dict[str, Any]:
    """Run the Runtime compatibility path from synchronous legacy callers."""
    return _run_awaitable_sync(run_legacy_bsc_runtime(**kwargs))


async def run_legacy_bsc_stage_runtime(
    *,
    input_text: str,
    stage_key: str,
    project_id: str = "",
    execution_id: str = "",
    tenant_id: str = "",
    data_dir: str = "./data/artifacts",
) -> dict[str, Any]:
    """Execute a legacy single-stage operation through BusinessRuntime."""
    result = await _run_legacy_runtime(
        input_text=input_text,
        project_id=project_id,
        execution_id=execution_id,
        tenant_id=tenant_id,
        data_dir=data_dir,
        capability_name="legacy_bsc_stage_compatibility",
        execution_context={"stage_key": stage_key},
    )
    if result.errors:
        raise ValueError(result.errors[0])
    for artifact in result.export.get("_artifact_graph", {}).get("decisions", []):
        metadata = artifact.get("metadata") or {}
        if artifact.get("source_agent") == "legacy_bsc_stage_compatibility":
            return metadata.get("legacy_stage_result") or {}
    raise RuntimeError("legacy stage did not produce a compatibility artifact")


async def _run_legacy_runtime(
    *,
    input_text: str,
    project_id: str,
    execution_id: str,
    tenant_id: str,
    data_dir: str,
    capability_name: str,
    execution_context: dict[str, Any],
) -> RuntimeResult:
    scoped_project_id = project_id.strip() if project_id else new_project_id("legacy")
    scoped_execution_id = execution_id.strip() if execution_id else new_project_id("legacy_run")
    artifact_scope = scoped_artifact_dir(
        data_dir,
        scoped_project_id,
        scoped_execution_id,
        tenant_id,
    )
    store = ArtifactGraphStore(
        data_dir=artifact_scope,
        tenant_id=tenant_id,
        project_id=scoped_project_id,
        session_id=scoped_execution_id,
    )
    registry = build_default_registry()
    runtime = BusinessRuntime(
        store=store,
        registry=registry,
        planner=_LegacyBSCCompatibilityPlanner(capability_name),
        max_iterations=1,
        executor_backend="nanobot",
        execution_context=execution_context,
    )
    return await runtime.run(
        prd_text=input_text,
        project_id=scoped_project_id,
    )


def _legacy_compile_payload(result: RuntimeResult) -> dict[str, Any]:
    business_models = result.export.get("_artifact_graph", {}).get("biz_models", [])
    for artifact in business_models:
        if artifact.get("source_agent") != "legacy_bsc_compatibility":
            continue
        metadata = artifact.get("metadata") or {}
        return {
            "business_system": metadata.get("legacy_business_system") or {},
            "pipeline": metadata.get("legacy_pipeline") or {},
            "workspace": metadata.get("legacy_workspace") or {},
            "summary": str(metadata.get("legacy_summary") or ""),
        }
    raise RuntimeError("legacy compiler did not produce a compatibility artifact")


def _runtime_result_to_agent_response(
    *,
    result: RuntimeResult,
    project_id: str,
    execution_id: str,
    artifact_scope: str,
    board: dict[str, Any] | None,
    context_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    export = result.export or {}
    graph = export.get("_artifact_graph", {})
    gaps = [_gap_payload(gap) for gap in graph.get("gaps", [])]
    board_payload = _board_payload(board)

    return {
        "status": "failed" if result.errors else "completed",
        "project_id": project_id,
        "execution_id": execution_id,
        "mission": _mission_payload(result),
        "artifacts": _artifact_count(result, graph),
        "gaps": len(gaps),
        "gap_details": gaps,
        "board": board_payload,
        "board_verdict": board_payload["verdict"] if board_payload else "",
        "board_consensus": board_payload["consensus"] if board_payload else "",
        "board_votes": board_payload["votes"] if board_payload else {},
        "runtime": {
            "status": result.status,
            "execution_id": execution_id,
            "artifact_scope": artifact_scope,
            "iterations": result.iterations,
            "elapsed_ms": result.elapsed_ms,
            "errors": result.errors,
            "stage_modes": result.stage_modes,
            "degraded": any(mode == "fallback" for mode in result.stage_modes.values()),
            "capability_executions": result.capability_executions,
            "context": context_usage or {},
        },
        "report": export,
    }


def _artifact_count(result: RuntimeResult, graph: dict[str, Any]) -> int:
    if result.artifact_graph is not None:
        return result.artifact_graph.count()
    total = graph.get("total_artifacts")
    return total if isinstance(total, int) else 0


def _mission_payload(result: RuntimeResult) -> dict[str, Any]:
    mission = getattr(result, "mission", None)
    if isinstance(mission, dict):
        return {
            "title": mission.get("title", ""),
            "steps": mission.get("steps", 0),
            "mode": mission.get("mode", ""),
        }
    return {"title": "", "steps": 0, "mode": ""}


def _board_payload(board: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(board, dict):
        return None
    return {
        "verdict": str(board.get("verdict", "") or ""),
        "consensus": str(board.get("consensus", "") or ""),
        "votes": board.get("votes", {}) if isinstance(board.get("votes"), dict) else {},
    }


def _gap_payload(gap: Any) -> dict[str, str]:
    if not isinstance(gap, dict):
        return {
            "description": str(gap),
            "category": "",
            "severity": "",
        }
    return {
        "description": str(
            gap.get("description")
            or gap.get("gap_statement")
            or gap.get("gap")
            or gap.get("label")
            or ""
        ),
        "category": str(gap.get("category", "") or ""),
        "severity": str(gap.get("severity", "") or ""),
    }


def _safe_path_segment(value: str) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
        for ch in value.strip()
    )
    return (safe[:96] or "default")


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    parameters = inspect.signature(callable_obj).parameters.values()
    return any(
        parameter.name == keyword or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _run_awaitable_sync(awaitable):
    """Bridge synchronous compatibility APIs without bypassing BusinessRuntime."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def run_in_worker() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # Re-raise the original compatibility failure.
            error.append(exc)

    worker = threading.Thread(target=run_in_worker, daemon=False)
    worker.start()
    worker.join()
    if error:
        raise error[0]
    return result["value"]
