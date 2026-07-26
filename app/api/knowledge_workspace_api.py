"""Project-scoped read API for the LLM Wiki workspace."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
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
from app.knowledge.feishu_import import FeishuImportError, FeishuImportService
from app.knowledge.wiki_bootstrap import WikiBootstrapError, WikiBootstrapService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_source_capture import InvalidSourceTransition, SourceCaptureService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.horizon_run_store import resolve_horizon_run_store_location
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
    return GrowthRepository()


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


class PluginManifestRequest(BaseModel):
    plugins: list[dict[str, Any]] = Field(default_factory=list, max_length=64)


class PluginTrustRequest(BaseModel):
    plugin_ids: list[str] = Field(min_length=1, max_length=64)
    trusted: bool = True
    reason: str = Field(default="", max_length=512)


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
    # An empty ID deliberately means "discover the latest unimported native run".
    # Horizon is a producer, so users should not need to inspect its run-store.
    horizon_run_id: str = ""
    stage: str = "filtered"


class FeishuImportRequest(BaseModel):
    """An explicit user-authorized export, never a Feishu credential bundle."""

    project_id: str = Field(min_length=1)
    export: dict[str, Any] = Field(default_factory=dict)


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


def _workspace_vault_state(project_id: str, mapping: dict[str, Any] | None) -> dict[str, Any]:
    """Describe the usable Vault boundary without reading user-authored content."""
    if not mapping:
        return {"state": "unconfigured", "message": "Map a project-relative Vault folder before sync."}
    if not settings.OBSIDIAN_VAULT_ROOT:
        return {"state": "unavailable", "message": "Obsidian Vault root is not configured for this runtime."}
    try:
        vault = FilesystemWikiVault(settings.OBSIDIAN_VAULT_ROOT, project_id, mapping["vault_path"])
    except Exception as exc:
        return {"state": "unavailable", "message": _safe_error_message(str(exc))}

    project_root = vault.project_root
    if not project_root.is_dir():
        return {"state": "mapped_uninitialized", "message": "The project folder has not been initialized yet."}
    required_paths = ("AGENTS.md", "README.md", "wiki/index.md", "wiki/overview.md", "wiki/log.md")
    missing_files = [path for path in required_paths if not (project_root / path).is_file()]
    missing_directories = [
        path for path in WikiBootstrapService.managed_directories() if not (project_root / path).is_dir()
    ]
    if missing_files or missing_directories:
        return {
            "state": "mapped_incomplete",
            "message": "The project boundary is reachable but the managed knowledge workspace is incomplete.",
            "missing_managed_files": missing_files,
            "missing_managed_directories": missing_directories,
        }
    return {"state": "ready", "message": "Project Vault is reachable and the full managed knowledge workspace is present."}


def _latest_growth_run(repo: WikiRepository, project_id: str) -> dict[str, Any] | None:
    """Return the latest integrated loop without conflating it with a direct sync."""
    runs = [
        repo.latest_run_for_type(project_id, "growth_daily"),
        repo.latest_run_for_type(project_id, "growth_weekly_distillation"),
    ]
    candidates = [run for run in runs if run]
    return max(candidates, key=lambda run: (str(run.get("created_at") or ""), str(run.get("id") or "")), default=None)


def _growth_sync_summary(run: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose bounded loop evidence, never raw Vault text or provider payloads."""
    output_refs = (run or {}).get("output_refs") or {}
    raw = output_refs.get("sync")
    if not isinstance(raw, dict):
        return None

    def counts(value: object, fields: tuple[str, ...]) -> dict[str, int]:
        record = value if isinstance(value, dict) else {}
        return {field: int(record.get(field, 0) or 0) for field in fields}

    return {
        "status": str(raw.get("status") or "not_recorded"),
        "sources": counts(raw.get("sources"), ("created", "duplicates")),
        "outputs": counts(raw.get("outputs"), ("registered", "duplicates")),
        "triage": counts(raw.get("triage"), ("evaluated", "eligible", "pending_review")),
    }


def _horizon_run_summary(run: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose the latest import outcome without exposing source bodies or provider payloads."""
    if not run:
        return None
    output_refs = run.get("output_refs") or {}
    report = output_refs.get("horizon") if isinstance(output_refs.get("horizon"), dict) else {}
    raw_failure = output_refs.get("failure") if isinstance(output_refs.get("failure"), dict) else None
    failure = (
        {
            "category": str(raw_failure.get("category") or ""),
            "code": str(raw_failure.get("code") or ""),
            "retryable": bool(raw_failure.get("retryable", False)),
        }
        if raw_failure
        else None
    )

    def count(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    accepted = count(report.get("accepted"))
    rejected = count(report.get("rejected"))
    items_observed = count(output_refs.get("items_observed"))
    if "items_observed" not in output_refs:
        items_observed = accepted + rejected
    status = str(run.get("status") or "not_run")
    outcome = str(output_refs.get("outcome") or "")
    if not outcome:
        if status == RunStatus.COMPLETED.value:
            outcome = "no_new_artifact" if bool(report.get("skipped", False)) else "empty_result" if items_observed == 0 else "processed"
        elif failure and failure["category"] == "configuration":
            outcome = "configuration_error"
        elif failure and failure["code"] == "horizon_unavailable":
            outcome = "channel_error"
        else:
            outcome = "failed"
    return {
        "id": str(run.get("id") or ""),
        "status": status,
        "updated_at": str(run.get("updated_at") or ""),
        "horizon_run_id": str(output_refs.get("horizon_run_id") or ""),
        "stage": str(output_refs.get("stage") or ""),
        "source_mode": str(output_refs.get("source_mode") or ""),
        "accepted": accepted,
        "created": count(report.get("created")),
        "duplicates": count(report.get("duplicates")),
        "rejected": rejected,
        "skipped": bool(report.get("skipped", False)),
        "outcome": outcome,
        "items_observed": items_observed,
        "failure": failure,
    }


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
    project_root = None
    if vault and settings.OBSIDIAN_VAULT_ROOT:
        try:
            project_root = FilesystemWikiVault(
                settings.OBSIDIAN_VAULT_ROOT, project_id, vault["vault_path"]
            ).project_root
        except Exception:
            project_root = None
    sources = repo.list_sources(project_id)
    horizon_sources = [source for source in sources if source.get("source_type") == "horizon_signal"]
    outputs = repo.list_outputs(project_id) if isinstance(repo, GrowthRepository) else []
    plugins = ObsidianPluginManifest.load(project_root).public_status(
        sources,
        outputs,
        project_root=project_root,
        vault_root=Path(settings.OBSIDIAN_VAULT_ROOT) if settings.OBSIDIAN_VAULT_ROOT else None,
    )
    role = str(getattr(request.state, "knowledge_role", ""))
    sync_run = repo.latest_run_for_type(project_id, "source_sync")
    horizon_run = repo.latest_run_for_type(project_id, "horizon_capture")
    growth_run = _latest_growth_run(repo, project_id)
    horizon_store = resolve_horizon_run_store_location(
        runs_root=settings.HORIZON_RUNS_ROOT,
        host_path=settings.HORIZON_RUNS_HOST_PATH,
    )
    scheduler_available = (
        settings.KNOWLEDGE_SCHEDULES_ENABLED
        and is_celery_real()
        and is_celery_broker_available()
    )
    return ApiResponse.ok(
        {
            "project_id": project_id,
            "vault": {
                "configured": bool(vault),
                "status": vault.get("status") if vault else "unconfigured",
                "vault_path": vault.get("vault_path") if vault else "",
                "connection": _workspace_vault_state(project_id, vault),
            },
            "plugins": plugins,
            "sources": len(sources),
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
            "horizon": {
                "enabled": settings.HORIZON_ENABLED,
                "captured_sources": len(horizon_sources),
                "last_run": _horizon_run_summary(horizon_run),
                "artifact_store": {
                    "configured": horizon_store.configured,
                    "available": horizon_store.available,
                    "mode": horizon_store.mode,
                },
            },
            "growth": {
                "status": growth_run["status"] if growth_run else "not_run",
                "last_run": growth_run,
                "sync": _growth_sync_summary(growth_run),
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


@router.put("/workspaces/{project_id}/plugins")
def configure_workspace_plugins(
    payload: PluginManifestRequest, request: Request, project_id: str, repo: WikiRepository = Depends(get_wiki_repository)
):
    """Register filesystem-drop plugin exports for an already mapped project Vault."""
    project_id = _enforce_project_access(request, project_id, write=True)
    mapping = repo.get_vault(project_id)
    if not mapping:
        raise HTTPException(
            status_code=409,
            detail={"code": "knowledge_vault_unconfigured", "message": "Map the project Vault before registering plugin exports"},
        )
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise HTTPException(status_code=400, detail="OBSIDIAN_VAULT_ROOT is not configured")
    try:
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
        manifest = ObsidianPluginManifest.from_payload({"plugins": payload.plugins})
        manifest.write_to(vault.project_root)
        if manifest.plugins:
            # This is an explicit project-admin command, distinct from a
            # bridge merely appearing on disk. Persist the approval separately
            # so later manifest changes require another trust decision.
            manifest = manifest.set_trust(
                vault.project_root,
                plugin_ids=[plugin.plugin_id for plugin in manifest.plugins],
                trusted=True,
                actor_id=str(getattr(request.state, "knowledge_role", "") or "http"),
                reason="registered through the governed workspace API",
            )
    except Exception as exc:
        raise _command_error(exc) from exc
    return ApiResponse.ok(manifest.public_status(project_root=vault.project_root, vault_root=Path(settings.OBSIDIAN_VAULT_ROOT)))


@router.put("/workspaces/{project_id}/plugins/trust")
def set_workspace_plugin_trust(
    payload: PluginTrustRequest,
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    """Approve or revoke reads from already declared Obsidian bridge paths."""
    project_id = _enforce_project_access(request, project_id, write=True)
    mapping = repo.get_vault(project_id)
    if not mapping:
        raise HTTPException(
            status_code=409,
            detail={"code": "knowledge_vault_unconfigured", "message": "Map the project Vault before managing plugin trust"},
        )
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise HTTPException(status_code=400, detail="OBSIDIAN_VAULT_ROOT is not configured")
    try:
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
        manifest = ObsidianPluginManifest.load(vault.project_root)
        if not manifest.configured:
            raise ValueError("plugin manifest is not configured")
        manifest = manifest.set_trust(
            vault.project_root,
            plugin_ids=payload.plugin_ids,
            trusted=payload.trusted,
            actor_id=str(getattr(request.state, "knowledge_role", "") or "http"),
            reason=payload.reason,
        )
    except Exception as exc:
        raise _command_error(exc) from exc
    return ApiResponse.ok(manifest.public_status(project_root=vault.project_root, vault_root=Path(settings.OBSIDIAN_VAULT_ROOT)))


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


@router.post("/sources/feishu/import")
def import_workspace_feishu_export(
    payload: FeishuImportRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    """Persist one selected Feishu CLI/export payload as immutable A-layer evidence.

    The caller's project-scoped write authorization is the authorization for
    this handoff. The export service rejects credentials and does not fetch
    Feishu, which keeps the browser/API boundary distinct from user-owned CLI
    authentication.
    """
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    run = KnowledgeRun(
        project_id=project_id,
        run_type="feishu_import",
        trigger="manual",
        status=RunStatus.RUNNING,
        actor_id=str(getattr(request.state, "knowledge_role", "") or "http"),
        input_refs={"provider": "feishu", "mode": "explicit_export"},
    )
    repo.create_run(run)
    try:
        result = FeishuImportService(repo).import_export(
            project_id=project_id,
            payload=payload.export,
            authorized=True,
        )
        source = result.source
        output_refs = {
            "created": result.created,
            "source_id": source["id"],
            "source_type": source["source_type"],
            "source_revision": str((source.get("metadata") or {}).get("feishu_revision_id") or ""),
        }
        repo.append_run_event(
            project_id=project_id,
            run_id=run.id,
            event_type="knowledge.feishu.imported",
            payload=output_refs,
        )
        repo.update_run_status(project_id, run.id, RunStatus.COMPLETED, output_refs=output_refs)
        return ApiResponse.ok({"source": _source_view(source), "created": result.created, "run_id": run.id})
    except FeishuImportError as exc:
        safe_message = _safe_error_message(str(exc))
        repo.update_run_status(project_id, run.id, RunStatus.FAILED, error=safe_message)
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": safe_message}) from exc
    except Exception as exc:
        safe_message = _safe_error_message(str(exc))
        repo.update_run_status(project_id, run.id, RunStatus.FAILED, error=safe_message)
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
    records = [_legacy_distillation_view(record) for record in repo.list_distillations(project_id)]
    if isinstance(repo, GrowthRepository):
        records.extend(_growth_distillation_view(record) for record in repo.list_growth_distillations(project_id, limit=500))
    records.sort(key=lambda record: (str(record.get("created_at") or ""), str(record.get("period") or "")), reverse=True)
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
    legacy = repo.get_distillation(project_id, distillation_id)
    if legacy:
        try:
            result = WikiCommandService(repo).read_distillation(project_id=project_id, distillation_id=distillation_id)
        except WikiCommandError as exc:
            raise _command_error(exc) from exc
        result["distillation"] = _legacy_distillation_view(legacy)
        return ApiResponse.ok(result)

    growth = repo.get_growth_distillation_by_id(project_id, distillation_id) if isinstance(repo, GrowthRepository) else None
    if growth:
        try:
            documents = _read_growth_distillation_documents(repo, growth)
        except WikiCommandError as exc:
            raise _command_error(exc) from exc
        return ApiResponse.ok({"distillation": _growth_distillation_view(growth), "documents": documents})
    raise _command_error(WikiCommandError("weekly distillation not found"))


def _legacy_distillation_view(record: dict[str, Any]) -> dict[str, Any]:
    paths = [str(record.get(key) or "") for key in ("knowledge_path", "content_path", "context_path")]
    return {
        **record,
        "record_type": "legacy",
        "kind": "weekly",
        "period": str(record.get("week") or ""),
        "paths": [path for path in paths if path],
        "manifest": {},
        "generation": {},
    }


def _growth_distillation_view(record: dict[str, Any]) -> dict[str, Any]:
    manifest = record.get("manifest") if isinstance(record.get("manifest"), dict) else {}
    paths = [str(path) for path in record.get("paths") or [] if str(path)]
    period = str(record.get("period") or "")
    return {
        "id": record.get("id", ""),
        "project_id": record.get("project_id", ""),
        "record_type": "growth",
        "kind": str(record.get("kind") or "weekly"),
        "period": period,
        "week": period if str(record.get("kind") or "") == "weekly" else "",
        "knowledge_path": paths[0] if paths else "",
        "content_path": paths[1] if len(paths) > 1 else "",
        "context_path": paths[2] if len(paths) > 2 else "",
        "paths": paths,
        "source_cutoff": str(manifest.get("source_cutoff") or ""),
        "status": str(record.get("status") or ""),
        "created_at": str(record.get("created_at") or ""),
        "manifest": manifest,
        "generation": manifest.get("generation") if isinstance(manifest.get("generation"), dict) else {},
    }


def _read_growth_distillation_documents(repo: GrowthRepository, record: dict[str, Any]) -> dict[str, str]:
    mapping = repo.get_vault(str(record.get("project_id") or ""))
    if not mapping:
        raise WikiCommandError("project Vault mapping is not configured")
    vault_root = str(settings.OBSIDIAN_VAULT_ROOT or "").strip()
    if not vault_root:
        raise WikiCommandError("Obsidian Vault is not configured")
    try:
        vault = FilesystemWikiVault(vault_root, str(record["project_id"]), mapping["vault_path"])
    except (OSError, ValueError) as exc:
        raise WikiCommandError("project Vault is unavailable") from exc

    documents: dict[str, str] = {}
    for relative, path in _growth_distillation_document_locations(vault, record):
        try:
            unavailable = not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000
        except OSError:
            unavailable = True
        if unavailable:
            raise WikiCommandError("managed distillation document is unavailable")
        try:
            documents[relative] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise WikiCommandError("managed distillation document is unreadable") from exc
    if not documents:
        raise WikiCommandError("growth distillation has no managed documents")
    return documents


def _growth_distillation_document_locations(
    vault: FilesystemWikiVault, record: dict[str, Any]
) -> list[tuple[str, Path]]:
    paths = [str(path) for path in record.get("paths") or [] if str(path)]
    locations = [(relative, _safe_growth_distillation_path(vault, relative)) for relative in paths]
    input_hash = str(record.get("input_hash") or "")
    if not re.fullmatch(r"[a-f0-9]{64}", input_hash) or not locations:
        return locations

    if str(record.get("kind") or "") == "weekly":
        current_root = locations[0][1].parent
        current_hash = _weekly_manifest_input_hash(current_root / "manifest.json")
        if not current_hash or current_hash == input_hash:
            return locations
        return [
            (
                relative,
                _safe_growth_distillation_path(
                    vault,
                    (Path(relative).parent / "revisions" / input_hash / Path(relative).name).as_posix(),
                ),
            )
            for relative, _path in locations
        ]

    if str(record.get("kind") or "") == "daily" and len(locations) == 1:
        relative, current = locations[0]
        current_hash = _daily_marker_input_hash(current)
        if current_hash and current_hash != input_hash:
            archived = Path(relative).parent / "revisions" / str(record.get("period") or "") / f"{input_hash}.md"
            return [(relative, _safe_growth_distillation_path(vault, archived.as_posix()))]
    return locations


def _weekly_manifest_input_hash(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = str(payload.get("input_hash") or "") if isinstance(payload, dict) else ""
    return value if re.fullmatch(r"[a-f0-9]{64}", value) else ""


def _daily_marker_input_hash(path: Path) -> str:
    try:
        first_line = path.open("r", encoding="utf-8").readline(2_048)
    except (OSError, UnicodeDecodeError):
        return ""
    match = re.search(r"\binput_hash=([a-f0-9]{64})\b", first_line)
    return match.group(1) if match else ""


def _safe_growth_distillation_path(vault: FilesystemWikiVault, relative: str) -> Path:
    normalized = str(relative or "").replace("\\", "/")
    parts = Path(normalized).parts
    if (
        not normalized
        or normalized.startswith("/")
        or not parts
        or parts[0].casefold() != "distillations"
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
    ):
        raise WikiCommandError("persisted growth output path is invalid")
    root = vault.project_root.resolve()
    candidate = (root / Path(normalized)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WikiCommandError("persisted growth output path escaped the project Vault") from exc
    return candidate


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
