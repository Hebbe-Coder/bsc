"""Project-scoped API for the Personal Business Operating System."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.dbos_api import _service
from app.core.celery_app import is_celery_real
from app.core.config import settings
from app.knowledge.scheduler import ScheduleValidationError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository
from app.pbos import PBOSProjectionService, PBOSReportService, PBOSScheduleCoordinator, PBOSService
from app.pbos.compiler import PBOSPlanCompiler
from app.pbos.context import PBOSGovernedContextProvider

router = APIRouter(prefix="/api/pbos", tags=["Personal Business Operating System"])


class PBOSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileRequest(PBOSRequest):
    focus: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    resources: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ExecutionRequest(PBOSRequest):
    plan_id: str = ""
    actions: list[str] = Field(default_factory=list)
    tool_receipts: list[dict[str, Any]] = Field(default_factory=list)
    reflection: dict[str, str] = Field(default_factory=dict)
    observed_at: str = ""


class LocalCaptureRequest(PBOSRequest):
    plan_id: str = ""
    root: str
    paths: list[str] = Field(default_factory=list)


class OutcomeRequest(PBOSRequest):
    quality_score: float | None = Field(default=None, ge=0, le=100)
    severe_failure: bool = False
    acceptance_status: str = "unverified"
    comparison_key: str = ""
    comparison_context: str = ""
    personal_context_fingerprint: str = ""
    baseline_quality: float | None = Field(default=None, ge=0, le=100)
    hard_failure_resolved: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(PBOSRequest):
    source: str = "manual_reflection"
    sentiment: str = "neutral"
    statement: str = Field(min_length=1, max_length=2000)


def _pbos(request: Request, project_id: str, *, write: bool) -> PBOSService:
    project_root = _project_root(project_id)
    return PBOSService(
        _service(request, project_id, write=write).store,
        project_id,
        context_provider=PBOSGovernedContextProvider(
            project_root,
            project_id=project_id,
            vault_root=settings.OBSIDIAN_VAULT_ROOT,
        ).build,
        plan_compiler=PBOSPlanCompiler.from_settings() if write else PBOSPlanCompiler(),
    )


def _project_root(project_id: str):
    root = Path(settings.OBSIDIAN_VAULT_ROOT) if settings.OBSIDIAN_VAULT_ROOT else Path()
    repository = WikiRepository()
    try:
        mapping = repository.get_vault(project_id)
    finally:
        repository.close()
    if mapping and settings.OBSIDIAN_VAULT_ROOT:
        return FilesystemWikiVault(root, project_id, str(mapping["vault_path"])).project_root
    return root / "projects" / project_id


def _sync(project_id: str, artifact) -> dict[str, str]:
    return PBOSProjectionService(_project_root(project_id), project_id).sync(artifact)


@router.get("/projects/{project_id}/profile")
def read_profile(project_id: str, request: Request):
    profile = _pbos(request, project_id, write=False).profile()
    return {"profile": profile.model_dump(mode="json") if profile else None}


@router.put("/projects/{project_id}/profile")
def save_profile(project_id: str, payload: ProfileRequest, request: Request):
    profile = _pbos(request, project_id, write=True).save_profile(payload.model_dump())
    return {"profile": profile.model_dump(mode="json"), "vault": _sync(project_id, profile)}


@router.post("/projects/{project_id}/missions/{mission_id}/plans")
def compile_plan(project_id: str, mission_id: str, request: Request, diagnosis_id: str = Query(default="")):
    try:
        plan = _pbos(request, project_id, write=True).compile_plan(mission_id, diagnosis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"plan": plan.model_dump(mode="json"), "vault": _sync(project_id, plan)}


@router.post("/projects/{project_id}/missions/{mission_id}/executions")
def record_execution(project_id: str, mission_id: str, payload: ExecutionRequest, request: Request):
    try:
        record = _pbos(request, project_id, write=True).record_execution(mission_id, payload.plan_id, payload.model_dump(exclude={"plan_id"}))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"execution": record.model_dump(mode="json"), "vault": _sync(project_id, record)}


@router.post("/projects/{project_id}/missions/{mission_id}/capture-local")
def capture_local(project_id: str, mission_id: str, payload: LocalCaptureRequest, request: Request):
    try:
        record = _pbos(request, project_id, write=True).capture_local_execution(mission_id, payload.plan_id, payload.root, payload.paths)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"execution": record.model_dump(mode="json"), "vault": _sync(project_id, record)}


@router.post("/projects/{project_id}/executions/{execution_id}/outcomes")
def record_outcome(project_id: str, execution_id: str, payload: OutcomeRequest, request: Request):
    try:
        outcome = _pbos(request, project_id, write=True).record_outcome(execution_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"outcome": outcome.model_dump(mode="json"), "vault": _sync(project_id, outcome)}


@router.post("/projects/{project_id}/outcomes/{outcome_id}/feedback")
def record_feedback(project_id: str, outcome_id: str, payload: FeedbackRequest, request: Request):
    try:
        feedback = _pbos(request, project_id, write=True).record_feedback(outcome_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"feedback": feedback.model_dump(mode="json"), "vault": _sync(project_id, feedback)}


@router.post("/projects/{project_id}/evolution/reconcile")
def reconcile(
    project_id: str,
    request: Request,
    comparison_key: str = Query(default="", max_length=160),
    comparison_context: str = Query(default="", max_length=300),
):
    value = _pbos(request, project_id, write=True).evolve(comparison_key, comparison_context)
    return {key: item.model_dump(mode="json") if hasattr(item, "model_dump") else item for key, item in value.items()}


@router.get("/projects/{project_id}/cockpit")
def cockpit(project_id: str, request: Request):
    return _pbos(request, project_id, write=False).cockpit()


@router.get("/projects/{project_id}/today-action")
def today_action(project_id: str, request: Request):
    """Read the current action without creating a plan or causing side effects."""
    return _pbos(request, project_id, write=False).today_action()


@router.post("/projects/{project_id}/reports/weekly")
def weekly_report(project_id: str, request: Request, week: str = Query(default="", pattern=r"^$|^\d{4}-W\d{2}$")):
    service = _pbos(request, project_id, write=True)
    return {"report": PBOSReportService(service, _project_root(project_id)).weekly(week)}


@router.post("/projects/{project_id}/schedules/defaults")
def ensure_schedule_defaults(project_id: str, request: Request):
    """Install durable PBOS cadence without claiming that an unavailable worker runs it."""
    _pbos(request, project_id, write=True)
    repository = WikiRepository()
    available = bool(
        settings.KNOWLEDGE_SCHEDULES_ENABLED
        and settings.CELERY_ENABLED
        and is_celery_real()
    )
    try:
        schedules = PBOSScheduleCoordinator(
            repository, scheduler_available=available
        ).ensure_defaults(project_id)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        repository.close()
    return {"schedules": schedules, "scheduler_available": available}
