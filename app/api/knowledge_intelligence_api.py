"""REST boundary for governed n8n information discovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.knowledge_api import _enforce_project_access
from app.api.response import ApiResponse
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.information_intelligence import InformationIntelligenceError, InformationIntelligenceService
from app.knowledge.information_intelligence_contracts import SignalBatch, SourceRegistryEntry
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository


def require_information_intelligence_enabled() -> None:
    if not settings.KNOWLEDGE_INTELLIGENCE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "information_intelligence_disabled",
                "message": "Governed information intelligence is disabled by configuration.",
            },
        )


router = APIRouter(
    prefix="/knowledge/intelligence",
    tags=["Knowledge Intelligence"],
    dependencies=[Depends(require_information_intelligence_enabled)],
)

MANUAL_DISPATCH_RUN_TYPE = "information_manual_dispatch"
MANUAL_DISPATCH_TRIGGER = "n8n_signed_manual_webhook"


def get_intelligence_repository() -> WikiRepository:
    return GrowthRepository()


def _service(repository: WikiRepository) -> InformationIntelligenceService:
    return InformationIntelligenceService(repository)


def _enforce_ingress_access(request: Request, project_id: str) -> str:
    role = str(getattr(request.state, "knowledge_role", ""))
    scoped_project_id = str(getattr(request.state, "knowledge_project_id", "") or "")
    if role == "admin":
        return project_id
    if role == "project_ingress" and scoped_project_id == project_id:
        return project_id
    raise HTTPException(
        status_code=403,
        detail={"code": "information_ingress_forbidden", "message": "This credential cannot submit signals for the requested project."},
    )


def _verify_signature(body: bytes, signature: str) -> None:
    secret = settings.KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"code": "information_ingress_signing_unconfigured", "message": "Ingress signing is not configured."},
        )
    supplied = signature.strip().lower()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "information_ingress_signature_invalid", "message": "Signal batch signature is missing or invalid."},
        )


def _require_manual_trigger_configuration(project_id: str) -> None:
    if not settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"code": "information_manual_trigger_disabled", "message": "The governed n8n manual trigger is disabled."},
        )
    if not settings.KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET:
        raise HTTPException(
            status_code=503,
            detail={"code": "information_ingress_signing_unconfigured", "message": "Ingress signing is not configured."},
        )
    if not settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_URL:
        raise HTTPException(
            status_code=503,
            detail={"code": "information_manual_trigger_unconfigured", "message": "The governed n8n manual trigger URL is not configured."},
        )
    if not settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID:
        raise HTTPException(
            status_code=503,
            detail={"code": "information_manual_trigger_project_unconfigured", "message": "The governed n8n manual trigger project is not configured."},
        )
    if not hmac.compare_digest(project_id, settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_PROJECT_ID):
        raise HTTPException(
            status_code=409,
            detail={"code": "information_manual_trigger_project_mismatch", "message": "The local n8n workflow is not configured for this project."},
        )


def _project_manual_run_response(payload: Any) -> dict[str, Any]:
    """Reduce an untrusted n8n webhook response to bounded receipt claims."""
    entries = payload if isinstance(payload, list) else [payload]
    batches: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        batch_id = str(entry.get("batch_id") or "").strip()
        if not batch_id:
            continue
        try:
            receipt_count = max(0, int(entry.get("receipt_count") or 0))
        except (TypeError, ValueError):
            receipt_count = 0
        batches.append(
            {
                "batch_id": batch_id[:200],
                "receipt_count": receipt_count,
                "replayed": bool(entry.get("replayed")),
                "status": str(entry.get("status") or "completed")[:80],
            }
        )
    return {
        "state": "claimed_batches" if batches else "completed_no_fresh_items",
        "batch_count": len(batches),
        "receipt_count": sum(batch["receipt_count"] for batch in batches),
        "batches": batches[:100],
    }


def _verify_persisted_manual_receipts(
    repository: WikiRepository,
    project_id: str,
    claimed: dict[str, Any],
) -> dict[str, Any]:
    """Promote a webhook claim only when BSC's project ledger proves it."""
    claimed_batches = claimed.get("batches") if isinstance(claimed.get("batches"), list) else []
    if not claimed_batches:
        return {
            "state": "completed_no_fresh_items",
            "batch_count": 0,
            "receipt_count": 0,
            "batches": [],
            "verification": {
                "state": "no_receipt_claimed",
                "claimed_batch_count": 0,
                "verified_batch_count": 0,
                "pending_batch_ids": [],
            },
        }

    verified_batches: list[dict[str, Any]] = []
    pending_batch_ids: list[str] = []
    includes_partial = False
    for claim in claimed_batches:
        if not isinstance(claim, dict):
            continue
        batch_id = str(claim.get("batch_id") or "").strip()
        if not batch_id:
            continue
        persisted_batch = repository.get_signal_batch(project_id, batch_id)
        if not persisted_batch:
            pending_batch_ids.append(batch_id)
            continue
        persisted_status = str(persisted_batch.get("status") or "")
        receipts = repository.list_signal_receipts(project_id, batch_id=batch_id, limit=100)
        reported_count = max(0, int(claim.get("receipt_count") or 0))
        if persisted_status not in {"completed", "partial"} or len(receipts) != reported_count:
            pending_batch_ids.append(batch_id)
            continue
        includes_partial = includes_partial or persisted_status == "partial"
        verified_batches.append(
            {
                "batch_id": batch_id,
                "receipt_count": len(receipts),
                "replayed": bool(claim.get("replayed")),
                "status": persisted_status,
            }
        )

    verification = {
        "state": "pending" if pending_batch_ids else "verified",
        "claimed_batch_count": len(claimed_batches),
        "verified_batch_count": len(verified_batches),
        "pending_batch_ids": pending_batch_ids[:100],
    }
    if pending_batch_ids:
        return {
            "state": "receipt_verification_pending",
            "batch_count": len(verified_batches),
            "receipt_count": sum(batch["receipt_count"] for batch in verified_batches),
            "batches": verified_batches,
            "verification": verification,
        }
    return {
        "state": "completed_with_rejections" if includes_partial else "completed",
        "batch_count": len(verified_batches),
        "receipt_count": sum(batch["receipt_count"] for batch in verified_batches),
        "batches": verified_batches,
        "verification": verification,
    }


def _manual_dispatch_output_refs(result: dict[str, Any]) -> dict[str, Any]:
    """Retain only BSC-verifiable dispatch metadata in the audit ledger."""
    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    batches = result.get("batches") if isinstance(result.get("batches"), list) else []
    verified_batch_ids = [
        str(batch.get("batch_id") or "")[:200]
        for batch in batches
        if isinstance(batch, dict) and str(batch.get("batch_id") or "").strip()
    ][:100]
    pending_batch_ids = [
        str(batch_id)[:200]
        for batch_id in verification.get("pending_batch_ids", [])
        if str(batch_id).strip()
    ][:100]
    return {
        "trigger_kind": MANUAL_DISPATCH_TRIGGER,
        "verification_state": str(result.get("state") or "unknown")[:80],
        "claimed_batch_count": max(0, int(verification.get("claimed_batch_count") or 0)),
        "verified_batch_count": max(0, int(verification.get("verified_batch_count") or 0)),
        "verified_receipt_count": max(0, int(result.get("receipt_count") or 0)),
        "verified_batch_ids": verified_batch_ids,
        "pending_batch_ids": pending_batch_ids,
    }


async def _dispatch_n8n_manual_run(project_id: str, repository: WikiRepository) -> dict[str, Any]:
    request_payload = {
        "schema_version": "bsc-n8n-manual-run-v1",
        "project_id": project_id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "request_id": secrets.token_hex(12),
    }
    run = KnowledgeRun(
        project_id=project_id,
        run_type=MANUAL_DISPATCH_RUN_TYPE,
        trigger="manual",
        status=RunStatus.QUEUED,
        input_refs={
            "schema_version": request_payload["schema_version"],
            "request_id": request_payload["request_id"],
            "trigger_kind": MANUAL_DISPATCH_TRIGGER,
        },
    )
    repository.create_run(run)
    if not repository.claim_run_execution(project_id=project_id, run_id=run.id):
        repository.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error="manual dispatch run could not be claimed",
            output_refs={"trigger_kind": MANUAL_DISPATCH_TRIGGER, "verification_state": "failed"},
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "information_manual_trigger_unavailable", "message": "The governed n8n manual trigger is unavailable."},
        )

    serialized_payload = json.dumps(request_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(
        settings.KNOWLEDGE_INTELLIGENCE_INGRESS_SIGNING_SECRET.encode("utf-8"),
        serialized_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    try:
        _require_manual_trigger_configuration(project_id)
        timeout = httpx.Timeout(max(1.0, float(settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_TIMEOUT_SECONDS)))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                settings.KNOWLEDGE_INTELLIGENCE_N8N_MANUAL_TRIGGER_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-BSC-Manual-Payload": serialized_payload,
                    "X-BSC-Manual-Signature": signature,
                },
                content=b"{}",
            )
            response.raise_for_status()
            response_payload = response.json() if response.content else []
    except HTTPException as exc:
        error_code = str((exc.detail or {}).get("code") if isinstance(exc.detail, dict) else "information_manual_trigger_unavailable")[:120]
        repository.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error=error_code,
            output_refs={"trigger_kind": MANUAL_DISPATCH_TRIGGER, "verification_state": "configuration_failed"},
        )
        raise
    except (httpx.HTTPError, ValueError) as exc:
        repository.update_run_status(
            project_id,
            run.id,
            RunStatus.FAILED,
            error="n8n manual webhook request failed",
            output_refs={"trigger_kind": MANUAL_DISPATCH_TRIGGER, "verification_state": "failed"},
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "information_manual_trigger_failed", "message": "The governed n8n run did not return a valid receipt summary."},
        ) from exc
    result = {
        "project_id": project_id,
        "trigger": MANUAL_DISPATCH_TRIGGER,
        "run_id": run.id,
        "request_id": request_payload["request_id"],
        "requested_at": request_payload["requested_at"],
        **_verify_persisted_manual_receipts(repository, project_id, _project_manual_run_response(response_payload)),
    }
    repository.update_run_status(
        project_id,
        run.id,
        RunStatus.COMPLETED,
        output_refs=_manual_dispatch_output_refs(result),
    )
    return result


@router.post("/signal-batches")
async def ingest_signal_batch(request: Request, repository: WikiRepository = Depends(get_intelligence_repository)):
    body = await request.body()
    _verify_signature(body, request.headers.get("X-BSC-Signal-Signature", ""))
    try:
        batch = SignalBatch.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "signal_batch_invalid", "message": "SignalBatch does not match the v1 contract.", "errors": exc.errors(include_input=False)},
        ) from exc
    _enforce_ingress_access(request, batch.project_id)
    try:
        return ApiResponse.ok(_service(repository).ingest(batch))
    except InformationIntelligenceError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "signal_batch_idempotency_conflict", "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "information_registry_forbidden", "message": str(exc)},
        ) from exc


@router.get("/n8n/source-manifest")
def n8n_source_manifest(
    request: Request,
    connector_type: str = "",
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    """Expose only a project-ingress producer's enabled RSS configuration."""
    project_id = _enforce_ingress_access(request, str(getattr(request.state, "knowledge_project_id", "") or ""))
    try:
        return ApiResponse.ok(_service(repository).n8n_source_manifest(project_id, connector_type))
    except InformationIntelligenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "information_manifest_connector_invalid", "message": str(exc)},
        ) from exc


@router.get("/projects/{project_id}")
def information_overview(
    project_id: str,
    request: Request,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    return ApiResponse.ok(_service(repository).overview(_enforce_project_access(request, project_id)))


@router.get("/projects/{project_id}/daily-brief")
def information_daily_brief(
    project_id: str,
    request: Request,
    day: str = "",
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    try:
        effective_project_id = _enforce_project_access(request, project_id)
        return ApiResponse.ok(_service(repository).daily_brief(effective_project_id, day=day))
    except InformationIntelligenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "information_brief_day_invalid", "message": str(exc)},
        ) from exc


@router.get("/projects/{project_id}/horizon-review-queue")
def information_horizon_review_queue(
    project_id: str,
    request: Request,
    limit: int = 100,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    effective_project_id = _enforce_project_access(request, project_id)
    return ApiResponse.ok(_service(repository).horizon_review_queue(effective_project_id, limit=limit))


@router.get("/projects/{project_id}/sources")
def information_sources(
    project_id: str,
    request: Request,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    return ApiResponse.ok({"sources": _service(repository).list_sources(_enforce_project_access(request, project_id))})


@router.post("/projects/{project_id}/manual-runs")
async def trigger_information_manual_run(
    project_id: str,
    request: Request,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    """Run the configured project's n8n source check through a signed local webhook."""
    effective_project_id = _enforce_project_access(request, project_id, write=True)
    return ApiResponse.ok(await _dispatch_n8n_manual_run(effective_project_id, repository))


@router.post("/projects/{project_id}/sources")
def register_information_source(
    project_id: str,
    entry: SourceRegistryEntry,
    request: Request,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    effective_project_id = _enforce_project_access(request, project_id, write=True)
    if entry.project_id != effective_project_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "information_source_project_mismatch", "message": "Source registry project must match the URL project."},
        )
    return ApiResponse.ok({"source": _service(repository).register_source(entry)})


@router.get("/projects/{project_id}/receipts")
def information_receipts(
    project_id: str,
    request: Request,
    limit: int = 100,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    return ApiResponse.ok({"receipts": _service(repository).list_receipts(_enforce_project_access(request, project_id), limit=limit)})


@router.get("/projects/{project_id}/derivatives")
def information_derivatives(
    project_id: str,
    request: Request,
    source_id: str = "",
    limit: int = 100,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    effective_project_id = _enforce_project_access(request, project_id)
    derivatives = _service(repository).list_derivatives(effective_project_id, source_id=source_id, limit=limit)
    # List views expose traceability but not long model output. Evidence and
    # derivative bodies stay inside the project-scoped source inspection flow.
    for derivative in derivatives:
        derivative.pop("content", None)
    return ApiResponse.ok({"derivatives": derivatives})
