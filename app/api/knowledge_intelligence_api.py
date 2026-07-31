"""REST boundary for governed n8n information discovery."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.knowledge_api import _enforce_project_access
from app.api.response import ApiResponse
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.information_intelligence import InformationIntelligenceError, InformationIntelligenceService
from app.knowledge.information_intelligence_contracts import SignalBatch, SourceRegistryEntry
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


@router.get("/projects/{project_id}/sources")
def information_sources(
    project_id: str,
    request: Request,
    repository: WikiRepository = Depends(get_intelligence_repository),
):
    return ApiResponse.ok({"sources": _service(repository).list_sources(_enforce_project_access(request, project_id))})


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
