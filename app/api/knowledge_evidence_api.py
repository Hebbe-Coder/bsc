"""Read-only, redacted multimodal evidence endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.api.knowledge_api import _enforce_project_access
from app.api.knowledge_workspace_api import get_wiki_repository, require_knowledge_wiki_enabled
from app.api.response import ApiResponse
from app.knowledge.evidence_read import EvidenceReadService
from app.knowledge.wiki_repository import WikiRepository


router = APIRouter(
    prefix="/knowledge/evidence",
    tags=["Knowledge Evidence"],
    dependencies=[Depends(require_knowledge_wiki_enabled)],
)


def get_evidence_repository() -> WikiRepository:
    return get_wiki_repository()


@router.get("/projects/{project_id}")
def evidence_overview(
    request: Request,
    project_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    repository: WikiRepository = Depends(get_evidence_repository),
):
    return ApiResponse.ok(EvidenceReadService(repository).overview(_enforce_project_access(request, project_id), limit=limit))


@router.get("/projects/{project_id}/tables/{table_id}/preview")
def table_preview(
    request: Request,
    project_id: str,
    table_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    repository: WikiRepository = Depends(get_evidence_repository),
):
    preview = EvidenceReadService(repository).table_preview(
        _enforce_project_access(request, project_id),
        table_id,
        page=page,
        page_size=page_size,
    )
    if preview is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_table_not_found", "message": "Table evidence is unavailable in this project."})
    return ApiResponse.ok(preview)


@router.get("/projects/{project_id}/assets/{asset_id}/thumbnail")
def image_thumbnail(
    request: Request,
    project_id: str,
    asset_id: str,
    repository: WikiRepository = Depends(get_evidence_repository),
):
    thumbnail = EvidenceReadService(repository).image_thumbnail(
        _enforce_project_access(request, project_id),
        asset_id,
    )
    if thumbnail is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_image_preview_unavailable", "message": "An authorized image preview is unavailable for this asset."})
    return Response(content=thumbnail, media_type="image/webp", headers={"Cache-Control": "private, no-store"})


@router.get("/projects/{project_id}/records/{record_type}/{record_id}")
def evidence_record(
    request: Request,
    project_id: str,
    record_type: str,
    record_id: str,
    repository: WikiRepository = Depends(get_evidence_repository),
):
    try:
        record = EvidenceReadService(repository).record(_enforce_project_access(request, project_id), record_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "evidence_record_type_invalid", "message": str(exc)}) from exc
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_record_not_found", "message": "Evidence record is unavailable in this project."})
    return ApiResponse.ok({"record": record})
