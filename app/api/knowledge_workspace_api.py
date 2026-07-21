"""Project-scoped read API for the LLM Wiki workspace."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.knowledge_api import _enforce_project_access
from app.api.response import ApiResponse
from app.core.config import settings
from app.knowledge.wiki_commands import WikiCommandError, WikiCommandService
from app.knowledge.knowledge_graph import KnowledgeGraphService
from app.knowledge.knowledge_health import KnowledgeHealthService
from app.knowledge.wiki_bootstrap import WikiBootstrapError
from app.knowledge.wiki_contracts import SourceStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import InvalidSourceTransition, SourceCaptureService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_service import WikiService
from app.core.celery_app import is_celery_broker_available, is_celery_real


def require_knowledge_wiki_enabled() -> None:
    if not settings.KNOWLEDGE_WIKI_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "knowledge_wiki_disabled",
                "message": "Project Wiki workspace is disabled by configuration",
            },
        )


router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Workspace"],
    dependencies=[Depends(require_knowledge_wiki_enabled)],
)


def get_wiki_repository() -> WikiRepository:
    return WikiRepository()


class SourceStatusRequest(BaseModel):
    project_id: str = Field(min_length=1)
    status: SourceStatus


class SourceCaptureRequest(BaseModel):
    project_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    origin: str = ""
    raw_content: str = Field(min_length=1)
    vault_path: str = ""
    trust_level: str = "untrusted"
    metadata: dict[str, Any] = Field(default_factory=dict)


class VaultMappingRequest(BaseModel):
    vault_path: str = Field(min_length=1, max_length=512)


class ScheduleStateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    enabled: bool


class ProposalRequest(BaseModel):
    project_id: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    operations: list[dict[str, Any]] = Field(min_length=1)
    rationale: str = ""
    base_revision: str = ""


class PublishProposalRequest(BaseModel):
    override_reason: str = Field(default="", max_length=500)


class EvalCaseRequest(BaseModel):
    project_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_type: str = Field(min_length=1)
    expected: dict[str, Any] = Field(default_factory=dict)


class ScheduleRequest(BaseModel):
    project_id: str = Field(min_length=1)
    job_type: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    timezone: str = "Asia/Shanghai"


class RunNowRequest(BaseModel):
    project_id: str = Field(min_length=1)
    job_type: str = Field(min_length=1)


class HorizonCaptureRequest(BaseModel):
    project_id: str = Field(min_length=1)
    horizon_run_id: str = Field(min_length=1)
    stage: str = "filtered"


def _command_error(exc: Exception) -> HTTPException:
    message = str(exc)
    normalized = message.lower()
    if "conflict" in normalized or "revision" in normalized:
        status, code = 409, "knowledge_conflict"
    elif "not found" in normalized:
        status, code = 404, "knowledge_not_found"
    elif "unavailable" in normalized or "not configured" in normalized or "disabled" in normalized:
        status, code = 503, "knowledge_dependency_unavailable"
    elif "permission" in normalized or "forbidden" in normalized:
        status, code = 403, "knowledge_permission_denied"
    else:
        status, code = 400, "knowledge_invalid_request"
    return HTTPException(status_code=status, detail={"code": code, "message": _safe_error_message(message)})


def _safe_error_message(message: str) -> str:
    root = str(settings.OBSIDIAN_VAULT_ROOT or "")
    redacted = message.replace(root, "<vault>") if root else message
    return redacted[:500]


def _validate_event_cursor(repo: WikiRepository, project_id: str, run_id: str, after_sequence: int) -> None:
    if after_sequence < 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_event_sequence", "message": "after_sequence must be non-negative"},
        )
    latest = repo.latest_run_event_sequence(project_id=project_id, run_id=run_id)
    if after_sequence > latest:
        raise HTTPException(
            status_code=409,
            detail={"code": "event_sequence_ahead", "message": "after_sequence is ahead of persisted run history"},
        )


@router.get("/workspaces/{project_id}")
def workspace_status(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    vault = repo.get_vault(project_id)
    role = str(getattr(request.state, "knowledge_role", ""))
    sync_run = repo.latest_run_for_type(project_id, "source_sync")
    scheduler_available = (
        settings.KNOWLEDGE_SCHEDULES_ENABLED
        and is_celery_real()
        and is_celery_broker_available()
    )
    return ApiResponse.ok(
        {
            "project_id": project_id,
            "vault": {"configured": bool(vault), "status": vault.get("status") if vault else "unconfigured"},
            "sources": len(repo.list_sources(project_id)),
            "runs": len(repo.list_runs(project_id)),
            "schedules": len(repo.list_schedules(project_id)),
            "access": {"role": role, "can_write": role in {"admin", "project_admin"}},
            "features": {
                "wiki": settings.KNOWLEDGE_WIKI_ENABLED,
                "obsidian_sync": settings.KNOWLEDGE_OBSIDIAN_SYNC_ENABLED,
                "schedules": settings.KNOWLEDGE_SCHEDULES_ENABLED,
                "mcp_write": settings.KNOWLEDGE_MCP_WRITE_ENABLED,
                "horizon": settings.HORIZON_ENABLED,
                "automatic_publication": settings.KNOWLEDGE_WIKI_AUTO_PUBLISH_ENABLED,
            },
            "sync": {
                "status": sync_run["status"] if sync_run else "not_run",
                "last_run": sync_run,
            },
            "scheduler": {
                "available": scheduler_available,
                "mode": "celery" if scheduler_available else "manual",
            },
        }
    )


@router.post("/workspaces/{project_id}/initialize")
def initialize_workspace(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        return ApiResponse.ok(WikiService(repo).initialize_project(project_id, actor="http"))
    except WikiBootstrapError as exc:
        raise _command_error(exc) from exc


@router.put("/workspaces/{project_id}/vault")
def configure_workspace_vault(
    payload: VaultMappingRequest, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id, write=True)
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise HTTPException(status_code=400, detail="OBSIDIAN_VAULT_ROOT is not configured")
    try:
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, payload.vault_path)
    except Exception as exc:
        raise _command_error(exc) from exc
    canonical_path = vault.project_root.relative_to(vault.root).as_posix()
    mapping = repo.configure_vault(project_id, canonical_path, actor_id="http")
    return ApiResponse.ok({"vault": {"configured": True, "status": mapping["status"], "vault_path": mapping["vault_path"]}})


@router.get("/sources")
def list_workspace_sources(request: Request, project_id: str, status: str = "", repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    records = repo.list_sources(project_id, status=status or None)
    return ApiResponse.ok({"sources": [_source_view(record) for record in records], "count": len(records)})


@router.post("/sources/capture")
def capture_workspace_source(
    payload: SourceCaptureRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        result = WikiCommandService(repo).capture_source(
            {**payload.model_dump(), "project_id": project_id}, actor_id="http"
        )
        return ApiResponse.ok({"source": _source_view(result["source"]), "created": result["created"], "run_id": result["run_id"]})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.get("/sources/{source_id}")
def read_workspace_source(source_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    source = repo.get_source(project_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="knowledge source not found")
    return ApiResponse.ok({"source": _source_view(source)})


@router.post("/sources/{source_id}/status")
def transition_workspace_source(
    source_id: str, payload: SourceStatusRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        source = SourceCaptureService(repo).transition_source(project_id, source_id, payload.status)
        return ApiResponse.ok({"source": _source_view(source)})
    except (KeyError, InvalidSourceTransition) as exc:
        raise _command_error(exc) from exc


@router.get("/runs")
def list_workspace_runs(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    runs = repo.list_runs(project_id)
    return ApiResponse.ok({"runs": runs, "count": len(runs)})


@router.get("/runs/{run_id}/events")
def list_workspace_run_events(
    run_id: str, request: Request, project_id: str, after_sequence: int = 0, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id)
    if not repo.get_run(project_id, run_id):
        raise HTTPException(status_code=404, detail="knowledge run not found")
    _validate_event_cursor(repo, project_id, run_id, after_sequence)
    events = repo.list_run_events(project_id=project_id, run_id=run_id, after_sequence=after_sequence)
    return ApiResponse.ok({"events": events, "count": len(events)})


@router.get("/runs/{run_id}/events/stream")
async def stream_workspace_run_events(
    run_id: str, request: Request, project_id: str, after_sequence: int = 0, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id)
    if not repo.get_run(project_id, run_id):
        raise HTTPException(status_code=404, detail="knowledge run not found")
    _validate_event_cursor(repo, project_id, run_id, after_sequence)

    async def event_stream():
        sequence = after_sequence
        for _ in range(60):
            events = repo.list_run_events(project_id=project_id, run_id=run_id, after_sequence=sequence)
            for event in events:
                sequence = event["sequence"]
                yield f"id: {sequence}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            current = repo.get_run(project_id, run_id)
            if current and current["status"] in {"completed", "failed", "cancelled", "unavailable"}:
                return
            if await request.is_disconnected():
                return
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/proposals")
def list_workspace_proposals(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    proposals = repo.list_proposals(project_id)
    return ApiResponse.ok({"proposals": proposals, "count": len(proposals)})


@router.get("/wiki/pages")
def list_workspace_pages(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    pages = repo.list_pages(project_id)
    return ApiResponse.ok({"pages": pages, "count": len(pages)})


@router.get("/wiki/pages/{page_id}")
def read_workspace_page(page_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    page = repo.get_page(project_id, page_id)
    content = repo.get_page_content(project_id, page_id) if page else None
    if not page or not content:
        raise HTTPException(status_code=404, detail="published Wiki page not found")
    return ApiResponse.ok({
        "page": page,
        "content": content["content"],
        "revisions": repo.list_page_revisions(project_id, page_id),
        "citations": repo.list_citations(project_id, page_id),
        "backlinks": repo.list_backlinks(project_id, page_id),
    })


@router.post("/wiki/pages/{page_id}/revisions/{revision_id}/restore")
def restore_workspace_page_revision(
    page_id: str, revision_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        proposal = WikiCommandService(repo).create_rollback_proposal(
            project_id=project_id, page_id=page_id, revision_id=revision_id, actor_id="http"
        )
        return ApiResponse.ok({"proposal": proposal})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/proposals")
def create_workspace_proposal(
    payload: ProposalRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        proposal = WikiCommandService(repo).create_proposal(
            {**payload.model_dump(), "project_id": project_id}, actor_id="http"
        )
        return ApiResponse.ok({"proposal": proposal})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/proposals/{proposal_id}/lint")
def lint_workspace_proposal(
    proposal_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        return ApiResponse.ok(WikiCommandService(repo).lint_proposal(project_id=project_id, proposal_id=proposal_id))
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/proposals/{proposal_id}/publish")
def publish_workspace_proposal(
    proposal_id: str,
    request: Request,
    project_id: str,
    payload: PublishProposalRequest | None = None,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        role = str(getattr(request.state, "knowledge_role", ""))
        return ApiResponse.ok(
            WikiCommandService(repo).publish_proposal(
                project_id=project_id,
                proposal_id=proposal_id,
                actor_id=role or "http",
                actor_role=role,
                override_reason=payload.override_reason if payload else "",
            )
        )
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/proposals/{proposal_id}/reject")
def reject_workspace_proposal(
    proposal_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        proposal = WikiCommandService(repo).reject_proposal(project_id=project_id, proposal_id=proposal_id)
        return ApiResponse.ok({"proposal": proposal})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/eval-cases")
def save_workspace_eval_case(
    payload: EvalCaseRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        result = WikiCommandService(repo).save_eval_case(
            project_id=project_id, case_id=payload.case_id, case_type=payload.case_type, expected=payload.expected
        )
        return ApiResponse.ok({"eval_case": result})
    except (ValueError, WikiCommandError) as exc:
        raise _command_error(exc) from exc


@router.get("/wiki/graph")
def workspace_graph(
    request: Request,
    project_id: str,
    edge_type: str = "",
    limit: int = 500,
    offset: int = 0,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id)
    payload = KnowledgeGraphService(repo).visualization(
        project_id=project_id,
        edge_type=edge_type or None,
        limit=limit,
        offset=offset,
    )
    return ApiResponse.ok({**payload, "count": len(payload["edges"])})


@router.get("/health")
def workspace_health(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    return ApiResponse.ok(KnowledgeHealthService(repo).snapshot(project_id=project_id))


@router.get("/health/trend")
def workspace_health_trend(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    return ApiResponse.ok(KnowledgeHealthService(repo).trend(project_id=project_id))


@router.get("/schedules")
def workspace_schedules(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    available = (
        settings.KNOWLEDGE_SCHEDULES_ENABLED
        and is_celery_real()
        and is_celery_broker_available()
    )
    schedules = [
        {
            **schedule,
            "scheduler_available": available,
            "last_result": repo.latest_run_for_type(project_id, schedule["job_type"]),
        }
        for schedule in repo.list_schedules(project_id)
    ]
    return ApiResponse.ok({"schedules": schedules, "count": len(schedules), "scheduler_available": available})


@router.get("/distillations")
def list_workspace_distillations(request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id)
    records = repo.list_distillations(project_id)
    return ApiResponse.ok({"distillations": records, "count": len(records)})


@router.post("/schedules")
def configure_workspace_schedule(
    payload: ScheduleRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        schedule = WikiCommandService(repo).configure_schedule(
            project_id=project_id, job_type=payload.job_type, cron=payload.cron, timezone_name=payload.timezone
        )
        return ApiResponse.ok({"schedule": schedule})
    except (ValueError, WikiCommandError) as exc:
        raise _command_error(exc) from exc


@router.patch("/schedules/{schedule_id}")
def set_workspace_schedule_state(
    schedule_id: str, payload: ScheduleStateRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        schedule = WikiCommandService(repo).set_schedule_enabled(
            project_id=project_id, schedule_id=schedule_id, enabled=payload.enabled
        )
        return ApiResponse.ok({"schedule": schedule})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/runs")
def run_workspace_job(
    payload: RunNowRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        run = WikiCommandService(repo).start_run(project_id=project_id, job_type=payload.job_type, trigger="http")
        return ApiResponse.ok(run)
    except (ValueError, WikiCommandError) as exc:
        raise _command_error(exc) from exc


@router.post("/runs/{run_id}/retry")
def retry_workspace_run(run_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        return ApiResponse.ok(WikiCommandService(repo).retry_run(project_id=project_id, run_id=run_id))
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/runs/{run_id}/cancel")
def cancel_workspace_run(run_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)):
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        return ApiResponse.ok({"run": WikiCommandService(repo).cancel_run(project_id=project_id, run_id=run_id)})
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


@router.post("/horizon/capture")
def capture_horizon_workspace(
    payload: HorizonCaptureRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        result = WikiCommandService(repo).start_horizon_capture(
            project_id=project_id, horizon_run_id=payload.horizon_run_id, stage=payload.stage, trigger="http"
        )
        return ApiResponse.ok(result)
    except (ValueError, WikiCommandError) as exc:
        raise _command_error(exc) from exc


@router.get("/distillations/{distillation_id}")
def read_workspace_distillation(
    distillation_id: str, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, project_id)
    try:
        return ApiResponse.ok(WikiCommandService(repo).read_distillation(project_id=project_id, distillation_id=distillation_id))
    except WikiCommandError as exc:
        raise _command_error(exc) from exc


def _source_view(record: dict) -> dict:
    """Expose provenance and lifecycle state without returning raw evidence bodies."""
    return {
        "id": record["id"],
        "project_id": record["project_id"],
        "source_type": record["source_type"],
        "origin": record["origin"],
        "vault_path": record["vault_path"],
        "content_hash": record["content_hash"],
        "trust_level": record["trust_level"],
        "status": record["status"],
        "metadata": record["metadata"],
        "supersedes_id": record["supersedes_id"],
        "captured_at": record["captured_at"],
    }
