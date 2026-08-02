"""Project-scoped read API for the LLM Wiki workspace."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.knowledge_api import _enforce_project_access
from app.api.response import ApiResponse
from app.core.config import settings
from app.knowledge.wiki_commands import WikiCommandError, WikiCommandService
from app.knowledge.evidence_scope import is_active_evidence_source
from app.knowledge.knowledge_graph import KnowledgeGraphService
from app.knowledge.knowledge_health import KnowledgeHealthService
from app.knowledge.feishu_import import FeishuImportError, FeishuImportService
from app.knowledge.wiki_bootstrap import WikiBootstrapError, WikiBootstrapService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.growth_distillation_revisions import growth_distillation_revision_metadata
from app.knowledge.source_triage import (
    SemanticSourceTriageEvaluator,
    SourceTriageService,
    current_project_triage_decisions,
    requires_project_triage,
)
from app.knowledge.primary_web_capture import PrimaryWebCapture, PrimaryWebCaptureError
from app.knowledge.wiki_source_capture import InvalidSourceTransition, SourceCaptureService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.obsidian_local_rest import ObsidianCopilotCommandBridge, ObsidianLocalRestProbe
from app.knowledge.ecosystem_release_gate import (
    RELEASE_GATE_CONTRACT_REVISION,
    ReleaseEvidence,
    ReleaseEvidencePacket,
    evaluate_release_evidence,
)
from app.knowledge.horizon_run_store import resolve_horizon_run_store_location
from app.knowledge.wiki_service import WikiService
from app.core.celery_app import is_celery_broker_available, is_celery_real


SCHEDULER_AVAILABILITY_CACHE_TTL_SECONDS = 30.0
_scheduler_availability_lock = Lock()
_scheduler_availability_cache: tuple[tuple[object, ...], float, bool] | None = None
LOCAL_REST_PROBE_CACHE_TTL_SECONDS = 5.0
_local_rest_probe_lock = Lock()
_local_rest_probe_cache: tuple[tuple[object, ...], float, dict[str, Any]] | None = None


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


def _scheduler_availability_context() -> tuple[object, ...]:
    return (
        str(settings.CELERY_BROKER_URL or ""),
        id(is_celery_real),
        id(is_celery_broker_available),
    )


def _reset_scheduler_availability_cache() -> None:
    global _scheduler_availability_cache
    with _scheduler_availability_lock:
        _scheduler_availability_cache = None


def _scheduler_available() -> bool:
    """Return short-lived advisory scheduler state for read responses.

    A user opening the Knowledge workspace reads this status in more than one
    request. Broker failures can outlive Kombu's requested timeout, so those
    reads must not repeatedly block on a network probe. Command paths keep
    their direct broker checks before they create or enqueue a run.
    """
    global _scheduler_availability_cache
    if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
        _reset_scheduler_availability_cache()
        return False
    context = _scheduler_availability_context()
    now = monotonic()
    with _scheduler_availability_lock:
        cached = _scheduler_availability_cache
        if cached and cached[0] == context and now - cached[1] < SCHEDULER_AVAILABILITY_CACHE_TTL_SECONDS:
            return cached[2]
        available = bool(is_celery_real() and is_celery_broker_available())
        _scheduler_availability_cache = (context, now, available)
        return available


def _local_rest_probe_context() -> tuple[object, ...]:
    """Key the short read cache without retaining the connector secret."""
    token = str(settings.OBSIDIAN_LOCAL_REST_API_KEY or "")
    return (
        bool(settings.OBSIDIAN_LOCAL_REST_ENABLED),
        str(settings.OBSIDIAN_LOCAL_REST_URL or ""),
        sha256(token.encode("utf-8")).hexdigest(),
        str(settings.OBSIDIAN_VAULT_ROOT or ""),
        id(ObsidianLocalRestProbe.from_settings),
    )


def _reset_local_rest_probe_cache() -> None:
    global _local_rest_probe_cache
    with _local_rest_probe_lock:
        _local_rest_probe_cache = None


def _local_rest_status() -> dict[str, Any]:
    """Return a bounded Local REST status without blocking every workspace read."""
    global _local_rest_probe_cache
    if not settings.OBSIDIAN_LOCAL_REST_ENABLED:
        _reset_local_rest_probe_cache()
        return ObsidianLocalRestProbe.from_settings(settings).probe()
    context = _local_rest_probe_context()
    now = monotonic()
    with _local_rest_probe_lock:
        cached = _local_rest_probe_cache
        if cached and cached[0] == context and now - cached[1] < LOCAL_REST_PROBE_CACHE_TTL_SECONDS:
            return dict(cached[2])
        result = ObsidianLocalRestProbe.from_settings(settings).probe()
        _local_rest_probe_cache = (context, now, dict(result))
        return dict(result)


def _release_evidence_view(record: dict[str, Any]) -> dict[str, Any]:
    """Bound the release ledger's public view to safe metadata fields."""
    return {
        "evidence_id": str(record.get("evidence_id") or ""),
        "state": str(record.get("state") or ""),
        "proof_class": str(record.get("proof_class") or ""),
        "observed_at": str(record.get("observed_at") or ""),
        "durable_ids": list(record.get("durable_ids") or []),
        "detail_code": str(record.get("detail_code") or ""),
        "revision": int(record.get("revision") or 0),
        "recorded_by": str(record.get("recorded_by") or ""),
    }


def _workspace_release_gate(repo: WikiRepository, project_id: str) -> dict[str, Any]:
    """Evaluate current durable metadata; configured services never count as proof."""
    evidence = tuple(
        ReleaseEvidence(
            evidence_id=str(record.get("evidence_id") or ""),
            state=str(record.get("state") or "pending"),
            proof_class=str(record.get("proof_class") or "none"),
            observed_at=str(record.get("observed_at") or ""),
            durable_ids=tuple(str(item) for item in (record.get("durable_ids") or [])),
            detail_code=str(record.get("detail_code") or ""),
        )
        for record in repo.list_current_release_evidence(project_id)
    )
    return evaluate_release_evidence(
        ReleaseEvidencePacket(contract_revision=RELEASE_GATE_CONTRACT_REVISION, evidence=evidence)
    ).model_dump(mode="json")


class SourceStatusRequest(BaseModel):
    project_id: str = Field(min_length=1)
    status: SourceStatus
    triage_id: str = Field(default="", max_length=128)
    approval_note: str = Field(default="", max_length=512)


class SourceCaptureRequest(BaseModel):
    project_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    origin: str = ""
    raw_content: str = Field(min_length=1)
    vault_path: str = ""
    trust_level: str = "untrusted"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PrimaryWebCaptureRequest(BaseModel):
    project_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2_048)
    discovered_from_source_id: str = Field(default="", max_length=128)


class VaultMappingRequest(BaseModel):
    vault_path: str = Field(min_length=1, max_length=512)


class PluginManifestRequest(BaseModel):
    plugins: list[dict[str, Any]] = Field(default_factory=list, max_length=64)


class PluginTrustRequest(BaseModel):
    plugin_ids: list[str] = Field(min_length=1, max_length=64)
    trusted: bool = True
    reason: str = Field(default="", max_length=512)


class ReleaseEvidenceSubmissionRequest(BaseModel):
    evidence: ReleaseEvidence


class ReleaseEvidenceReviewRequest(BaseModel):
    evidence: ReleaseEvidence


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
    source_ids: list[str] = Field(default_factory=list, max_length=64)
    task_constraints: list[str] = Field(default_factory=list, max_length=24)


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


def _project_copilot_command_bridge(project_id: str, repo: WikiRepository) -> ObsidianCopilotCommandBridge:
    """Return the Local REST command bridge only for a configured project Copilot route."""
    mapping = repo.get_vault(project_id)
    if not mapping:
        raise HTTPException(
            status_code=409,
            detail={"code": "knowledge_vault_unconfigured", "message": "Map the project Vault before opening Copilot delivery"},
        )
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise HTTPException(
            status_code=503,
            detail={"code": "obsidian_vault_unavailable", "message": "The Obsidian Vault is unavailable to this runtime"},
        )
    try:
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
    except Exception as exc:
        raise _command_error(exc) from exc
    if not vault.project_root.is_dir():
        raise HTTPException(
            status_code=409,
            detail={"code": "knowledge_vault_uninitialized", "message": "Initialize the mapped project Vault before opening Copilot delivery"},
        )
    manifest = ObsidianPluginManifest.load(vault.project_root)
    plugin = next((item for item in manifest.plugins if item.plugin_id == "copilot"), None)
    if plugin is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "copilot_bridge_unconfigured", "message": "Register the project Copilot bridge before opening delivery"},
        )
    if manifest.trust_state(plugin) != "trusted":
        raise HTTPException(
            status_code=409,
            detail={"code": "copilot_bridge_not_trusted", "message": "Trust the declared project Copilot bridge before opening delivery"},
        )
    plugin_status = next(
        (
            item
            for item in manifest.public_status(
                project_root=vault.project_root,
                vault_root=Path(settings.OBSIDIAN_VAULT_ROOT),
            )["plugins"]
            if item["id"] == "copilot"
        ),
        None,
    )
    runtime = (plugin_status or {}).get("runtime_configuration") or {}
    if runtime.get("state") != "configured":
        raise HTTPException(
            status_code=409,
            detail={"code": "copilot_runtime_not_configured", "message": "Configure Copilot conversation storage before opening delivery"},
        )
    model_readiness = (plugin_status or {}).get("model_readiness") or {}
    if model_readiness.get("state") == "unavailable":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "copilot_model_not_configured",
                "message": "Enable Copilot Plus or configure the selected Copilot provider before opening delivery",
                "detail_code": model_readiness.get("detail_code", "copilot_provider_credential_missing"),
            },
        )
    if (plugin_status or {}).get("path_status") != "ready":
        raise HTTPException(
            status_code=409,
            detail={"code": "copilot_output_route_unavailable", "message": "Create the governed Copilot output route before opening delivery"},
        )
    return ObsidianCopilotCommandBridge.from_settings(settings)


def _copilot_bridge_error(result: dict[str, Any]) -> HTTPException:
    """Map redacted bridge state to a stable API error without exposing Local REST internals."""
    state = str(result.get("state") or "unavailable")
    detail_code = str(result.get("detail_code") or "command_unavailable")
    if state in {"command_unavailable", "rejected"}:
        status_code = 409
        message = "The configured project Copilot command is not available in Obsidian"
    elif state in {"unconfigured", "configuration_invalid"}:
        status_code = 503
        message = "The local Obsidian command service is not configured"
    elif state == "authentication_failed":
        status_code = 503
        message = "The local Obsidian command service rejected its configured authentication"
    else:
        status_code = 503
        message = "The local Obsidian command service is unavailable"
    return HTTPException(
        status_code=status_code,
        detail={"code": f"copilot_command_{detail_code}", "message": message},
    )


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

    summary = {
        "status": str(raw.get("status") or "not_recorded"),
        "sources": counts(raw.get("sources"), ("created", "duplicates")),
        "outputs": counts(raw.get("outputs"), ("registered", "duplicates")),
        "triage": counts(raw.get("triage"), ("evaluated", "eligible", "pending_review")),
    }
    metadata_views = raw.get("metadata_views")
    if isinstance(metadata_views, dict):
        # The workspace needs operational evidence that the local navigation
        # projection ran, but never the Vault paths, note bodies, or plugin
        # settings that produced it.
        summary["metadata_views"] = {
            "status": str(metadata_views.get("status") or "not_recorded"),
            **counts(metadata_views, ("created", "updated", "unchanged", "conflicts")),
        }
    return summary


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


@router.get("/workspaces")
def list_workspace_projects(request: Request, repo: WikiRepository = Depends(get_wiki_repository)):
    """List only project-picker metadata that the authenticated actor may open."""
    role = str(getattr(request.state, "knowledge_role", ""))
    tenant_id = str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))
    scoped_project_id = str(getattr(request.state, "knowledge_project_id", ""))
    if role == "admin":
        projects = repo.list_workspace_projects_for_tenant(tenant_id)
    elif role in {"project_admin", "project_reader"} and scoped_project_id:
        project = repo.get_workspace_project_for_tenant(scoped_project_id, tenant_id)
        projects = [project] if project else []
    else:
        raise HTTPException(status_code=403, detail="workspace project discovery is not authorized")
    return ApiResponse.ok({"projects": projects, "count": len(projects)})


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
    sources = [source for source in repo.list_sources(project_id) if is_active_evidence_source(source)]
    horizon_sources = [source for source in sources if source.get("source_type") == "horizon_signal"]
    outputs = repo.list_outputs(project_id) if isinstance(repo, GrowthRepository) else []
    plugins = ObsidianPluginManifest.load(project_root).public_status(
        sources,
        outputs,
        project_root=project_root,
        vault_root=Path(settings.OBSIDIAN_VAULT_ROOT) if settings.OBSIDIAN_VAULT_ROOT else None,
    )
    local_rest = _local_rest_status()
    role = str(getattr(request.state, "knowledge_role", ""))
    sync_run = repo.latest_run_for_type(project_id, "source_sync")
    horizon_run = repo.latest_run_for_type(project_id, "horizon_capture")
    growth_run = _latest_growth_run(repo, project_id)
    horizon_store = resolve_horizon_run_store_location(
        runs_root=settings.HORIZON_RUNS_ROOT,
        host_path=settings.HORIZON_RUNS_HOST_PATH,
    )
    scheduler_available = _scheduler_available()
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
            "local_rest": local_rest,
            "release_gate": _workspace_release_gate(repo, project_id),
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


@router.get("/workspaces/{project_id}/copilot/commands")
def list_workspace_copilot_commands(
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    """List the fixed BSC Copilot commands currently present in this project Vault."""
    project_id = _enforce_project_access(request, project_id, write=True)
    bridge = _project_copilot_command_bridge(project_id, repo)
    result = bridge.available_commands()
    if result.get("state") != "available":
        raise _copilot_bridge_error(result)
    return ApiResponse.ok({"commands": result["commands"], "state": "available"})


@router.post("/workspaces/{project_id}/copilot/commands/{command_key}")
def invoke_workspace_copilot_command(
    request: Request,
    project_id: str,
    command_key: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    """Open one allowlisted project Copilot command and retain an audit receipt.

    Dispatching invokes the visible Copilot command in Obsidian. A command may
    create an external file, but BSC neither approves it nor registers it as a
    governed output until the separate trusted output-sync path evaluates it.
    """
    project_id = _enforce_project_access(request, project_id, write=True)
    normalized_key = str(command_key or "").strip()
    run = KnowledgeRun(
        project_id=project_id,
        run_type="obsidian_copilot_command",
        trigger="manual",
        status=RunStatus.RUNNING,
        actor_id=str(getattr(request.state, "knowledge_role", "") or "http"),
        input_refs={
            "bridge": "obsidian_local_rest",
            "plugin_id": "copilot",
            "command_key": normalized_key,
        },
    )
    repo.create_run(run)
    try:
        bridge = _project_copilot_command_bridge(project_id, repo)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        detail_code = str(detail.get("code") or "command_preflight_rejected")
        repo.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error=detail_code,
            output_refs={"state": "failed", "detail_code": detail_code, "command_key": normalized_key},
        )
        raise
    try:
        result = bridge.invoke(normalized_key)
    except Exception:
        repo.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error="copilot_command_bridge_internal_error",
            output_refs={"state": "failed", "detail_code": "bridge_internal_error", "command_key": normalized_key},
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "copilot_command_bridge_internal_error", "message": "The local Obsidian command service is unavailable"},
        )

    output_refs = {
        "state": str(result.get("state") or "unavailable"),
        "detail_code": str(result.get("detail_code") or "command_unavailable"),
        "command_key": str(result.get("command_key") or normalized_key),
    }
    if result.get("state") != "invoked":
        repo.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error=output_refs["detail_code"],
            output_refs=output_refs,
        )
        raise _copilot_bridge_error(result)

    repo.append_run_event(
        project_id=project_id,
        run_id=run.id,
        event_type="knowledge.obsidian_copilot_command.invoked",
        payload=output_refs,
    )
    repo.update_run_status(project_id, run.id, RunStatus.COMPLETED, output_refs=output_refs)
    return ApiResponse.ok(
        {
            "run_id": run.id,
            "state": "invoked",
            "command": {
                "key": output_refs["command_key"],
                "name": str(result.get("command_name") or ""),
            },
        }
    )


@router.get("/sources")
def list_workspace_sources(
    request: Request,
    project_id: str,
    status: str = "",
    include_scope_excluded: bool = False,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id)
    records = repo.list_sources(project_id, status=status or None)
    if include_scope_excluded:
        role = str(getattr(request.state, "knowledge_role", ""))
        if role not in {"admin", "project_admin"}:
            raise HTTPException(status_code=403, detail="scope-excluded evidence audit requires project administration")
    else:
        records = [record for record in records if is_active_evidence_source(record)]
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


@router.post("/sources/capture-web")
def capture_primary_web_source(
    payload: PrimaryWebCaptureRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    """Capture a public primary page without promoting the originating radar signal."""
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        discovery_source_id = payload.discovered_from_source_id.strip()
        if discovery_source_id:
            discovery = repo.get_source(project_id, discovery_source_id)
            if not discovery or discovery.get("source_type") != "horizon_signal":
                raise ValueError("discovered_from_source_id must reference a Horizon signal in this project")
        captured = PrimaryWebCapture().capture(payload.url)
        metadata = {
            "title": captured.title,
            "admission_gate": "project_triage",
            "evidence_role": "primary_capture",
            "discovered_from_source_id": discovery_source_id,
            "supports_horizon_signal_ids": [discovery_source_id] if discovery_source_id else [],
            "fetch": {
                "requested_url": captured.requested_url,
                "final_url": captured.final_url,
                "content_type": captured.content_type,
                "response_sha256": captured.response_sha256,
                "extraction_revision": captured.extraction_revision,
            },
        }
        result = WikiCommandService(repo).capture_source(
            {
                "project_id": project_id,
                "source_type": "primary_web",
                "origin": captured.final_url,
                "raw_content": captured.content,
                "trust_level": "reviewed",
                "metadata": metadata,
            },
            actor_id="http",
        )
        if discovery_source_id:
            source = _attach_primary_capture_support(
                repo,
                project_id=project_id,
                source=result["source"],
                horizon_signal_id=discovery_source_id,
            )
            result = {**result, "source": source}
        return ApiResponse.ok({"source": _source_view(result["source"]), "created": result["created"], "run_id": result["run_id"]})
    except (PrimaryWebCaptureError, ValueError, WikiCommandError) as exc:
        raise _command_error(exc) from exc


def _attach_primary_capture_support(
    repo: WikiRepository,
    *,
    project_id: str,
    source: dict[str, Any],
    horizon_signal_id: str,
) -> dict[str, Any]:
    """Preserve an explicit Horizon-to-primary link across idempotent captures."""
    metadata = dict(source.get("metadata") or {})
    if source.get("source_type") != "primary_web" or metadata.get("evidence_role") != "primary_capture":
        raise ValueError("matching evidence is not a governed primary web capture")
    raw_supported = metadata.get("supports_horizon_signal_ids")
    supported_ids = [
        str(value).strip()
        for value in raw_supported
        if str(value).strip()
    ] if isinstance(raw_supported, (list, tuple, set)) else []
    if horizon_signal_id not in supported_ids:
        supported_ids.append(horizon_signal_id)
        metadata["supports_horizon_signal_ids"] = supported_ids
    if not str(metadata.get("discovered_from_source_id") or "").strip():
        metadata["discovered_from_source_id"] = horizon_signal_id
    if metadata == source.get("metadata"):
        return source
    return repo.update_source_metadata(project_id, str(source["id"]), metadata)


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


@router.get("/sources/{source_id}/triage")
def read_workspace_source_triage(
    source_id: str,
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    """Return the active profile-bound admission recommendation without raw evidence."""
    project_id = _enforce_project_access(request, project_id)
    if not repo.get_source(project_id, source_id):
        raise HTTPException(status_code=404, detail="knowledge source not found")
    decision = current_project_triage_decisions(repo, project_id).get(source_id)
    return ApiResponse.ok({"triage": decision})


@router.post("/sources/{source_id}/semantic-triage")
def semantic_triage_workspace_source(
    source_id: str,
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    """Create a review-only semantic triage record for one immutable source.

    This endpoint intentionally does not transition source lifecycle state. A
    project operator must still approve a passing recommendation before Wiki
    maintenance can use the source.
    """
    project_id = _enforce_project_access(request, project_id, write=True)
    try:
        service = SourceTriageService(repo, evaluator=SemanticSourceTriageEvaluator())
        triage = service.triage_source(project_id, source_id, apply_admission=False)
        source = repo.get_source(project_id, source_id)
        return ApiResponse.ok(
            {
                "source": _source_view(source) if source else None,
                "triage": triage,
                "admission": "explicit_approval_required",
            }
        )
    except (KeyError, ValueError) as exc:
        raise _command_error(exc) from exc


@router.post("/sources/{source_id}/status")
def transition_workspace_source(
    source_id: str, payload: SourceStatusRequest, request: Request, repo: WikiRepository = Depends(get_wiki_repository)
):
    project_id = _enforce_project_access(request, payload.project_id, write=True)
    try:
        source = repo.get_source(project_id, source_id)
        if not source:
            raise KeyError(f"source not found: {source_id}")
        approval = None
        if payload.status is SourceStatus.ELIGIBLE and requires_project_triage(source):
            triage_id = payload.triage_id.strip()
            if triage_id:
                approval = _build_triage_approval(repo, project_id, source, triage_id, payload.approval_note)
            elif source.get("status") != SourceStatus.ELIGIBLE.value:
                raise ValueError("eligible transition requires a current authoring-eligible triage_id")
        source = SourceCaptureService(repo).transition_source(project_id, source_id, payload.status)
        if approval:
            metadata = dict(source.get("metadata") or {})
            metadata["admission_approval"] = approval
            source = repo.update_source_metadata(project_id, source_id, metadata)
        return ApiResponse.ok({"source": _source_view(source)})
    except (KeyError, ValueError, InvalidSourceTransition) as exc:
        raise _command_error(exc) from exc


def _build_triage_approval(
    repo: WikiRepository,
    project_id: str,
    source: dict[str, Any],
    triage_id: str,
    approval_note: str,
) -> dict[str, Any]:
    """Bind an explicit source approval to one current, authoring-safe review."""
    growth_repository = repo if hasattr(repo, "list_triage") else GrowthRepository.borrow(repo)
    profile = growth_repository.get_profile(project_id) or {"revision": 0}
    profile_revision = int(profile.get("revision", 0) or 0)
    decision = next(
        (
            item
            for item in growth_repository.list_triage(project_id, limit=500)
            if str(item.get("id") or "") == triage_id
        ),
        None,
    )

    if decision is None or str(decision.get("source_id") or "") != str(source.get("id") or ""):
        raise ValueError("triage_id does not belong to this source in the selected project")
    if int(decision.get("profile_revision", -1)) != profile_revision:
        raise ValueError("triage_id is stale for the current project profile")
    if decision.get("evaluator_status") != "completed" or not bool(decision.get("reliability_pass")):
        raise ValueError("triage_id is not a completed reliable review")
    if decision.get("disposition") != "knowledge_candidate":
        raise ValueError("triage_id is not approved for evidence authoring")
    return {
        "triage_id": triage_id,
        "profile_revision": profile_revision,
        "evaluator_revision": str(decision.get("evaluator_revision") or ""),
        "approved_at": repo._now(),
        "actor_id": "http",
        **({"note": approval_note.strip()} if approval_note.strip() else {}),
    }


@router.get("/workspaces/{project_id}/release-evidence")
def list_workspace_release_evidence(
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id)
    evidence = [_release_evidence_view(record) for record in repo.list_current_release_evidence(project_id)]
    return ApiResponse.ok({"evidence": evidence, "count": len(evidence)})


@router.post("/workspaces/{project_id}/release-evidence")
def submit_workspace_release_evidence(
    payload: ReleaseEvidenceSubmissionRequest,
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id, write=True)
    if payload.evidence.state == "verified":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "release_evidence_review_required",
                "message": "Verified release evidence requires tenant-admin review.",
            },
        )
    record = repo.append_release_evidence(
        project_id,
        payload.evidence,
        recorded_by=str(getattr(request.state, "knowledge_role", "") or "http"),
    )
    return ApiResponse.ok({"evidence": _release_evidence_view(record)})


@router.post("/workspaces/{project_id}/release-evidence/{evidence_id}/verify")
def verify_workspace_release_evidence(
    evidence_id: str,
    payload: ReleaseEvidenceReviewRequest,
    request: Request,
    project_id: str,
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id, write=True)
    if str(getattr(request.state, "knowledge_role", "")) != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "release_evidence_admin_required", "message": "Release evidence review requires a tenant administrator."},
        )
    if payload.evidence.evidence_id != evidence_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "release_evidence_id_mismatch", "message": "Evidence path and payload IDs must match."},
        )
    if payload.evidence.state != "verified" or payload.evidence.proof_class != "real":
        raise HTTPException(
            status_code=400,
            detail={"code": "release_evidence_invalid_review", "message": "Review requires verified real evidence."},
        )
    if not repo.get_latest_release_evidence(project_id, evidence_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "release_evidence_not_submitted", "message": "Submit evidence before review."},
        )
    record = repo.append_release_evidence(project_id, payload.evidence, recorded_by="admin")
    return ApiResponse.ok({"evidence": _release_evidence_view(record)})


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
    available = _scheduler_available()
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
def list_workspace_distillations(
    request: Request,
    project_id: str,
    include_history: bool = Query(default=False),
    repo: WikiRepository = Depends(get_wiki_repository),
):
    project_id = _enforce_project_access(request, project_id)
    records = [_legacy_distillation_view(record) for record in repo.list_distillations(project_id)]
    if isinstance(repo, GrowthRepository):
        records.extend(
            _growth_distillation_views(
                repo,
                repo.list_growth_distillations(project_id, limit=500),
                include_history=include_history,
            )
        )
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
        source_ids = list(dict.fromkeys(str(item).strip() for item in payload.source_ids if str(item).strip()))
        task_constraints = list(dict.fromkeys(str(item).strip() for item in payload.task_constraints if str(item).strip()))
        if (source_ids or task_constraints) and payload.job_type != "wiki_maintenance":
            raise ValueError("source_ids and task_constraints are only supported for wiki_maintenance")
        if any(len(item) > 128 for item in source_ids):
            raise ValueError("source_ids entries must be at most 128 characters")
        if any(len(item) > 2_000 for item in task_constraints):
            raise ValueError("task_constraints entries must be at most 2000 characters")
        run = WikiCommandService(repo).start_run(
            project_id=project_id,
            job_type=payload.job_type,
            trigger="http",
            input_refs={
                **({"source_ids": source_ids} if source_ids else {}),
                **({"task_constraints": task_constraints} if task_constraints else {}),
            },
        )
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
        views = _growth_distillation_views(
            repo,
            repo.list_growth_distillations(project_id, limit=500),
            include_history=True,
        )
        view = next((item for item in views if item.get("id") == distillation_id), _growth_distillation_view(growth))
        return ApiResponse.ok({"distillation": view, "documents": documents})
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


def _growth_distillation_views(
    repo: GrowthRepository,
    records: list[dict[str, Any]],
    *,
    include_history: bool,
) -> list[dict[str, Any]]:
    metadata = growth_distillation_revision_metadata(repo, records, vault_root=str(settings.OBSIDIAN_VAULT_ROOT or ""))
    views: list[dict[str, Any]] = []
    for record in records:
        revision = metadata.get(str(record.get("id") or ""), {"current": True, "revision_count": 1})
        if include_history or bool(revision["current"]):
            views.append(
                _growth_distillation_view(
                    record,
                    current=bool(revision["current"]),
                    revision_count=int(revision["revision_count"]),
                )
            )
    return views


def _growth_distillation_view(
    record: dict[str, Any],
    *,
    current: bool = True,
    revision_count: int = 1,
) -> dict[str, Any]:
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
        "current": current,
        "revision_count": revision_count,
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
