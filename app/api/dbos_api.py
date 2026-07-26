"""Project-scoped REST API for the Dynamic Business OS lifecycle."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.artifacts import ArtifactGraphStore, MissionArtifact
from app.core.config import settings
from app.dbos.execution import (
    ManualRetryRequiredError,
    MissionNotConfirmedError,
    MissionNotFoundError,
    UnauthorizedCapabilityError,
)
from app.dbos.service import DBOSService, MissionStateError
from app.dbos.external_worker import ExternalWorkerPolicyError


router = APIRouter(prefix="/api/dbos", tags=["Dynamic Business OS"])
DBOS_DATA_ROOT = Path("./data/dbos")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DBOSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionCreateRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    intake_mode: str = Field(default="business", pattern="^(business|career)$")
    intent: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)


class ConfirmRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=200)
    authorized_capabilities: list[str] = Field(min_length=1, max_length=50)


class ExecuteRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    capability_name: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(default="", max_length=200)


class ExternalWorkerRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    dynamic_sop_id: str = Field(min_length=1, max_length=128)
    capability_name: str = Field(min_length=1, max_length=100)
    worker_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=2_000)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=200)
    estimated_cost_microusd: int = Field(default=0, ge=0, le=1_000_000_000)


class ExternalWorkerCancelRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class AdvisorReviewRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=200)


class FeedbackRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=20_000)
    source_refs: list[str] = Field(default_factory=list, max_length=100)


class DecisionRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=4_000)
    rationale: str = Field(default="", max_length=20_000)
    alternatives: list[str] = Field(default_factory=list, max_length=50)
    actor_id: str = Field(min_length=1, max_length=200)


class StopRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class RollbackRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class IntakeCreateRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    request_text: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)


class IntakeUncertaintyRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    action: str = Field(pattern="^(clarify|direct|help)$")


class IntakeAnswerRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    question_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(default="", max_length=4_000)
    skipped: bool = False


class IntakeTierRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    tier: str = Field(pattern="^(lite|standard|full)$")


class IntakeProjectRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)


class IntakeConvertRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=300)


class IntakeHandoffRequest(DBOSRequest):
    project_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=200)
    approved: bool = False


@router.post("/intake", status_code=201)
def create_intake(payload: IntakeCreateRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.create_intake(payload.project_id, payload.request_text, context=payload.context))
    return {"intake": intake.model_dump(mode="json")}


@router.get("/intake/{session_id}")
def read_intake(session_id: str, request: Request, project_id: str = Query(min_length=1, max_length=128)):
    service = _service(request, project_id, write=False)
    try:
        intake = service.get_intake(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="intake session not found in project") from exc
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/uncertainty")
def resolve_intake_uncertainty(session_id: str, payload: IntakeUncertaintyRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.resolve_intake_uncertainty(session_id, payload.action))
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/questions/next")
def next_intake_question(session_id: str, payload: IntakeProjectRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    question = _guard(lambda: service.next_intake_question(session_id))
    return {"intake": service.get_intake(session_id).model_dump(mode="json"), "question": question}


@router.post("/intake/{session_id}/answers")
def answer_intake(session_id: str, payload: IntakeAnswerRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.answer_intake(session_id, payload.question_id, payload.answer, skipped=payload.skipped))
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/answers/{revision_id}/revert")
def revert_intake_answer(session_id: str, revision_id: str, payload: IntakeProjectRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.revert_intake_answer(session_id, revision_id))
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/tier")
def select_intake_tier(session_id: str, payload: IntakeTierRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.select_intake_tier(session_id, payload.tier))
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/convert")
def convert_intake(session_id: str, payload: IntakeConvertRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    flow = _guard(lambda: service.convert_intake(session_id, title=payload.title))
    return {"intake": service.get_intake(session_id).model_dump(mode="json"), "mission": flow.mission.model_dump(mode="json")}


@router.post("/intake/{session_id}/recommendations")
def recommend_intake(session_id: str, payload: IntakeProjectRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    intake = _guard(lambda: service.recommend_intake(session_id))
    return {"intake": intake.model_dump(mode="json")}


@router.post("/intake/{session_id}/handoff", status_code=201)
def export_intake_handoff(session_id: str, payload: IntakeHandoffRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    deliverable = _guard(lambda: service.export_intake_handoff(session_id, actor_id=payload.actor_id, approved=payload.approved))
    return {"intake": service.get_intake(session_id).model_dump(mode="json"), "handoff": deliverable.model_dump(mode="json")}


@router.post("/missions", status_code=201)
def create_mission(payload: MissionCreateRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    mission = _guard(lambda: service.create_mission(**payload.model_dump()))
    return {"mission": mission.model_dump(mode="json")}


@router.get("/missions")
def list_missions(request: Request, project_id: str = Query(min_length=1, max_length=128)):
    service = _service(request, project_id, write=False)
    return {"project_id": project_id, "missions": service.list_missions()}


@router.post("/missions/{mission_id}/diagnose")
def diagnose_mission(mission_id: str, request: Request, project_id: str = Query(min_length=1, max_length=128)):
    service = _service(request, project_id, write=True)
    flow = _guard(lambda: service.diagnose_and_compile(mission_id))
    return {
        "mission": flow.mission.model_dump(mode="json"),
        "diagnosis": flow.diagnosis.model_dump(mode="json"),
        "selection": flow.selection.model_dump(mode="json"),
        "dynamic_sop": flow.sop.model_dump(mode="json"),
        "sop_routing_evaluation_id": flow.routing_evaluation_id,
        "runtime_context_id": flow.context_snapshot_id,
        "assumption_ids": flow.assumption_ids,
        "gap_ids": flow.gap_ids,
    }


@router.post("/missions/{mission_id}/confirm")
def confirm_mission(mission_id: str, payload: ConfirmRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    mission = _guard(lambda: service.confirm(
        mission_id,
        actor_id=payload.actor_id,
        authorized_capabilities=payload.authorized_capabilities,
    ))
    return {"mission": mission.model_dump(mode="json")}


@router.post("/missions/{mission_id}/executions")
async def execute_mission(mission_id: str, payload: ExecuteRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    result = await _guard_async(lambda: service.execute(
        mission_id,
        payload.capability_name,
        idempotency_key=payload.idempotency_key,
    ))
    return {"execution_result": result.model_dump(mode="json")}


@router.post("/missions/{mission_id}/external-workers", status_code=202)
def execute_external_worker(mission_id: str, payload: ExternalWorkerRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    result = _guard(lambda: service.run_external_worker(
        mission_id,
        dynamic_sop_id=payload.dynamic_sop_id,
        capability_name=payload.capability_name,
        worker_id=payload.worker_id,
        model_id=payload.model_id,
        endpoint=payload.endpoint,
        payload=payload.payload,
        idempotency_key=payload.idempotency_key,
        estimated_cost_microusd=payload.estimated_cost_microusd,
    ))
    return {"external_worker_run": result.model_dump(mode="json")}


@router.delete("/external-workers/{worker_run_id}", status_code=202)
def cancel_external_worker(worker_run_id: str, payload: ExternalWorkerCancelRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    result = _guard(lambda: service.cancel_external_worker(worker_run_id, reason=payload.reason))
    return {"external_worker_run": result.model_dump(mode="json")}


@router.post("/missions/{mission_id}/advisor-reviews", status_code=201)
def review_mission(mission_id: str, payload: AdvisorReviewRequest, request: Request):
    """Request a metered Advisor review with no capability-grant effect."""
    service = _service(request, payload.project_id, write=True)
    result = _guard(lambda: service.review_mission(
        mission_id,
        idempotency_key=payload.idempotency_key,
    ))
    return {"advisor_review": result.model_dump(mode="json")}


@router.post("/missions/{mission_id}/feedback", status_code=201)
def record_feedback(mission_id: str, payload: FeedbackRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    memory = _guard(lambda: service.record_feedback(mission_id, payload.statement, payload.source_refs))
    return {"memory": memory.model_dump(mode="json")}


@router.post("/missions/{mission_id}/decisions", status_code=201)
def record_decision(mission_id: str, payload: DecisionRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    decision = _guard(lambda: service.record_decision(
        mission_id,
        task_id=payload.task_id,
        statement=payload.statement,
        rationale=payload.rationale,
        alternatives=payload.alternatives,
        actor_id=payload.actor_id,
    ))
    return {"decision": decision.model_dump(mode="json")}


@router.post("/missions/{mission_id}/verifications/reconcile")
def reconcile_mission_verifications(mission_id: str, request: Request, project_id: str = Query(min_length=1, max_length=128)):
    """Reconcile missing proof for historic provider-backed executions only."""
    service = _service(request, project_id, write=True)
    verifications = _guard(lambda: service.reconcile_execution_verifications(mission_id))
    return {"verifications": [item.model_dump(mode="json") for item in verifications]}


@router.post("/missions/{mission_id}/stop")
async def stop_mission(mission_id: str, payload: StopRequest, request: Request):
    service = _service(request, payload.project_id, write=True)
    mission = _guard(lambda: service.get_mission(mission_id))
    stopped = _guard(lambda: service.execution_service.stop(mission, payload.reason))
    return {"mission": stopped.model_dump(mode="json")}


@router.post("/executions/{execution_id}/rollback")
async def rollback_execution(execution_id: str, payload: RollbackRequest, request: Request):
    from app.artifacts import ExecutionResultArtifact

    service = _service(request, payload.project_id, write=True)
    execution = service.store.get(execution_id)
    if not isinstance(execution, ExecutionResultArtifact):
        raise HTTPException(status_code=404, detail="execution not found in project")
    result = _guard(lambda: service.execution_service.rollback(execution, payload.reason))
    return {"execution_result": result.model_dump(mode="json")}


@router.get("/missions/{mission_id}")
@router.get("/missions/{mission_id}/control-center")
def read_control_center(mission_id: str, request: Request, project_id: str = Query(min_length=1, max_length=128)):
    service = _service(request, project_id, write=False)
    control_center = _guard(lambda: service.control_center(mission_id))
    executions = control_center.get("execution_results", [])
    control_center["health"] = {
        **control_center.get("health", {}),
        "executions_total": len(executions),
        "executions_completed": sum(item.get("execution_status") == "completed" for item in executions),
        "executions_failed": sum(item.get("execution_status") == "failed" for item in executions),
        "executions_rejected": sum(item.get("execution_status") == "rejected" for item in executions),
        "unresolved_gaps": len((control_center.get("diagnosis") or {}).get("missing_fields", [])),
    }
    return control_center


def _service(request: Request, project_id: str, *, write: bool) -> DBOSService:
    if not settings.DYNAMIC_BUSINESS_OS_ENABLED:
        raise HTTPException(status_code=503, detail={"code": "dbos_disabled", "message": "Dynamic Business OS is disabled by configuration"})
    if not _PROJECT_ID.fullmatch(project_id):
        raise HTTPException(status_code=422, detail="invalid project_id")
    role = str(getattr(request.state, "auth_role", ""))
    bound_project = getattr(request.state, "project_id", None)
    if bound_project and bound_project != project_id:
        raise HTTPException(status_code=403, detail="project key is bound to another project")
    if write and role in {"reader", "project_reader"}:
        raise HTTPException(status_code=403, detail="read-only key cannot mutate DBOS missions")
    tenant = str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))
    return dbos_service_for(project_id, tenant_id=tenant)


def dbos_service_for(project_id: str, *, tenant_id: str | None = None) -> DBOSService:
    """Resolve the single project-scoped DBOS ledger for non-HTTP adapters.

    Authorization belongs to the REST/MCP transport. This function owns the
    storage boundary so those transports cannot accidentally use distinct
    Artifact Graphs for the same project.
    """
    if not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("invalid project_id")
    tenant = str(tenant_id or settings.DEFAULT_TENANT_ID)
    safe_tenant = re.sub(r"[^A-Za-z0-9._-]", "_", tenant)[:128] or "default"
    data_dir = Path(DBOS_DATA_ROOT) / safe_tenant / project_id
    store = ArtifactGraphStore(
        str(data_dir),
        tenant_id=tenant,
        project_id=project_id,
        session_id="dbos",
    )
    # The adapter opens project knowledge only while compiling a diagnosis and
    # closes it immediately afterwards. It exposes governed metadata, never
    # raw source or output bodies, and has no write path into A/B/C/D.
    from app.knowledge.growth_repository import GrowthRepository

    return DBOSService(store=store, knowledge_repository_factory=GrowthRepository)


def recover_dbos_runs_on_startup(data_root: Path | None = None) -> list[str]:
    """Close interrupted DBOS attempts found after an application restart.

    Each directory is a project ledger. Recovery only marks persisted work as
    interrupted and returns it to a confirmed mission; it never dispatches a
    registered capability or repeats a provider call.
    """
    root = Path(data_root or DBOS_DATA_ROOT)
    if not root.exists():
        return []
    recovered_ids: list[str] = []
    for tenant_dir in root.iterdir():
        if not tenant_dir.is_dir():
            continue
        for project_dir in tenant_dir.iterdir():
            if not project_dir.is_dir() or not _PROJECT_ID.fullmatch(project_dir.name):
                continue
            try:
                store = ArtifactGraphStore(
                    str(project_dir),
                    project_id=project_dir.name,
                    session_id="dbos",
                )
                recovered_ids.extend(
                    execution.artifact_id
                    for execution in DBOSService(store=store).recover_interrupted_executions()
                )
                from app.dbos.external_worker import recover_interrupted_external_workers

                recovered_ids.extend(
                    worker.artifact_id
                    for worker in recover_interrupted_external_workers(store)
                )
            except Exception:
                # One damaged local ledger must not block API availability or
                # conceal recovery in other projects. The existing artifact
                # files remain untouched when the ledger cannot be read.
                continue
    return recovered_ids


def _guard(operation):
    try:
        return operation()
    except (KeyError, MissionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionNotConfirmedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (MissionStateError, UnauthorizedCapabilityError, ManualRetryRequiredError, ExternalWorkerPolicyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _guard_async(operation):
    try:
        return await operation()
    except (KeyError, MissionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionNotConfirmedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (MissionStateError, UnauthorizedCapabilityError, ManualRetryRequiredError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
