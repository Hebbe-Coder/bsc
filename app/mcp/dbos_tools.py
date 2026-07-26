"""Project-scoped MCP delegates for the Dynamic Business OS.

The module deliberately has no separate state or execution policy.  It uses
the same scoped DBOS service as REST so an MCP client cannot create a hidden
mission ledger or bypass capability confirmation.
"""

from __future__ import annotations

from typing import Any

from app.artifacts import ExecutionResultArtifact
from app.api.dbos_api import dbos_service_for
from app.dbos.external_worker import ExternalWorkerPolicyError


def dbos_create_mission(
    project_id: str,
    title: str,
    intent: str,
    intake_mode: str = "business",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _project(project_id)
    mission = dbos_service_for(project_id).create_mission(
        project_id=project_id,
        title=title,
        intent=intent,
        intake_mode=intake_mode,
        context=context or {},
    )
    return {"mission": mission.model_dump(mode="json")}


def dbos_diagnose_mission(project_id: str, mission_id: str) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    service = dbos_service_for(project_id)
    flow = service.diagnose_and_compile(mission_id)
    return {
        "mission": service._mission_view(flow.mission),
        "diagnosis": flow.diagnosis.model_dump(mode="json"),
        "selection": flow.selection.model_dump(mode="json"),
        "dynamic_sop": flow.sop.model_dump(mode="json"),
        "sop_routing_evaluation_id": flow.routing_evaluation_id,
        "assumption_ids": flow.assumption_ids,
        "gap_ids": flow.gap_ids,
    }


def dbos_confirm_mission(
    project_id: str,
    mission_id: str,
    actor_id: str,
    authorized_capabilities: list[str],
) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    mission = dbos_service_for(project_id).confirm(
        mission_id,
        actor_id=actor_id,
        authorized_capabilities=authorized_capabilities,
    )
    return {"mission": mission.model_dump(mode="json")}


async def dbos_execute_mission(
    project_id: str,
    mission_id: str,
    capability_name: str,
    idempotency_key: str = "",
) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    if not capability_name.strip():
        raise ValueError("capability_name is required")
    execution = await dbos_service_for(project_id).execute(
        mission_id,
        capability_name,
        idempotency_key=idempotency_key,
    )
    return {"execution_result": execution.model_dump(mode="json")}


def dbos_run_external_worker(
    project_id: str,
    mission_id: str,
    dynamic_sop_id: str,
    capability_name: str,
    worker_id: str,
    model_id: str,
    endpoint: str,
    payload: dict[str, Any],
    idempotency_key: str,
    estimated_cost_microusd: int = 0,
) -> dict[str, Any]:
    """Queue an allowlisted HTTPS worker through the same DBOS policy gate."""
    _project(project_id)
    if not mission_id.strip() or not idempotency_key.strip():
        raise ValueError("mission_id and idempotency_key are required")
    result = dbos_service_for(project_id).run_external_worker(
        mission_id,
        dynamic_sop_id=dynamic_sop_id,
        capability_name=capability_name,
        worker_id=worker_id,
        model_id=model_id,
        endpoint=endpoint,
        payload=payload,
        idempotency_key=idempotency_key,
        estimated_cost_microusd=estimated_cost_microusd,
    )
    return {"external_worker_run": result.model_dump(mode="json")}


def dbos_cancel_external_worker(
    project_id: str,
    worker_run_id: str,
    reason: str,
) -> dict[str, Any]:
    """Request transport cancellation and return the durable worker ledger state."""
    _project(project_id)
    if not worker_run_id.strip():
        raise ValueError("worker_run_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    result = dbos_service_for(project_id).cancel_external_worker(worker_run_id, reason=reason)
    return {"external_worker_run": result.model_dump(mode="json")}


def dbos_review_mission(
    project_id: str,
    mission_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Persist a non-authoritative PromptOps Advisor review for a compiled mission."""
    _project(project_id)
    if not mission_id.strip() or not idempotency_key.strip():
        raise ValueError("mission_id and idempotency_key are required")
    result = dbos_service_for(project_id).review_mission(
        mission_id,
        idempotency_key=idempotency_key,
    )
    return {"advisor_review": result.model_dump(mode="json")}


def dbos_control_center(project_id: str, mission_id: str) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    return dbos_service_for(project_id).control_center(mission_id)


def dbos_record_feedback(
    project_id: str,
    mission_id: str,
    statement: str,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    memory = dbos_service_for(project_id).record_feedback(
        mission_id,
        statement,
        source_refs or [],
    )
    return {"memory": memory.model_dump(mode="json")}


def dbos_record_decision(
    project_id: str,
    mission_id: str,
    task_id: str,
    statement: str,
    rationale: str = "",
    alternatives: list[str] | None = None,
    actor_id: str = "mcp",
) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    decision = dbos_service_for(project_id).record_decision(
        mission_id,
        task_id=task_id,
        statement=statement,
        rationale=rationale,
        alternatives=alternatives or [],
        actor_id=actor_id,
    )
    return {"decision": decision.model_dump(mode="json")}


def dbos_stop_mission(project_id: str, mission_id: str, reason: str) -> dict[str, Any]:
    _project(project_id)
    if not mission_id.strip():
        raise ValueError("mission_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    service = dbos_service_for(project_id)
    mission = service.execution_service.stop(service.get_mission(mission_id), reason)
    return {"mission": mission.model_dump(mode="json")}


def dbos_rollback_execution(project_id: str, execution_id: str, reason: str) -> dict[str, Any]:
    _project(project_id)
    if not execution_id.strip():
        raise ValueError("execution_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    service = dbos_service_for(project_id)
    execution = service.store.get(execution_id)
    if not isinstance(execution, ExecutionResultArtifact):
        raise KeyError("execution not found in project")
    result = service.execution_service.rollback(execution, reason)
    return {"execution_result": result.model_dump(mode="json")}


def dbos_mission(
    project_id: str,
    action: str = "read",
    mission_id: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact MCP lifecycle facade backed by the explicit DBOS operations."""
    values = payload or {}
    if action == "create":
        return dbos_create_mission(
            project_id,
            str(values.get("title") or ""),
            str(values.get("intent") or ""),
            str(values.get("intake_mode") or "business"),
            values.get("context") if isinstance(values.get("context"), dict) else {},
        )
    if action == "diagnose":
        return dbos_diagnose_mission(project_id, mission_id)
    if action in {"read", "control_center"}:
        return dbos_control_center(project_id, mission_id)
    raise ValueError("action must be create, diagnose, read, or control_center")


def dbos_confirm(
    project_id: str,
    mission_id: str,
    authorized_capabilities: list[str],
    actor_id: str = "mcp",
) -> dict[str, Any]:
    return dbos_confirm_mission(project_id, mission_id, actor_id, authorized_capabilities)


async def dbos_execute(
    project_id: str,
    mission_id: str,
    capability_name: str,
    idempotency_key: str = "",
) -> dict[str, Any]:
    return await dbos_execute_mission(project_id, mission_id, capability_name, idempotency_key)


def dbos_feedback(
    project_id: str,
    mission_id: str,
    statement: str,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    return dbos_record_feedback(project_id, mission_id, statement, source_refs)


def _project(project_id: str) -> None:
    if not project_id or not project_id.strip():
        raise ValueError("project_id is required")


__all__ = [
    "dbos_confirm_mission",
    "dbos_confirm",
    "dbos_cancel_external_worker",
    "dbos_control_center",
    "dbos_create_mission",
    "dbos_diagnose_mission",
    "dbos_execute",
    "dbos_execute_mission",
    "dbos_feedback",
    "dbos_mission",
    "dbos_record_feedback",
    "dbos_record_decision",
    "dbos_run_external_worker",
    "dbos_review_mission",
    "dbos_rollback_execution",
    "dbos_stop_mission",
]
