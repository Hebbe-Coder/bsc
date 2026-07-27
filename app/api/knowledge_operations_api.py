"""Authorized REST read model for knowledge operations."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.knowledge_api import _enforce_project_access
from app.api.knowledge_workspace_api import require_knowledge_wiki_enabled
from app.api.dbos_api import dbos_service_for
from app.api.response import ApiResponse
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsInterval, OperationsScope
from app.knowledge.operations_graph import KnowledgeOperationsGraphService
from app.knowledge.operations_service import KnowledgeOperationsService
from app.repositories.knowledge_repository import KnowledgeRepository


router = APIRouter(
    prefix="/knowledge/operations",
    tags=["Knowledge Operations"],
    dependencies=[Depends(require_knowledge_wiki_enabled)],
)


class OperationsContext:
    def __init__(self, repository: GrowthRepository, project_repository: KnowledgeRepository) -> None:
        self.service = KnowledgeOperationsService(
            repository=repository,
            project_repository=project_repository,
            dbos_store_factory=lambda project_id, tenant_id: dbos_service_for(project_id, tenant_id=tenant_id).store,
        )
        self.graph = KnowledgeOperationsGraphService(
            repository=repository,
            project_repository=project_repository,
        )


def get_operations_context() -> OperationsContext:
    repository = GrowthRepository()
    project_repository = KnowledgeRepository(backend=repository._get_connection())
    # The context owns no independent database connection.
    project_repository._owns_connection = False
    return OperationsContext(repository, project_repository)


def _interval(from_at: str, to_at: str) -> OperationsInterval | None:
    if not from_at and not to_at:
        return None
    if not from_at or not to_at:
        raise HTTPException(
            status_code=422,
            detail={"code": "operations_invalid_interval", "message": "Both from and to are required for an operations interval."},
        )
    try:
        return OperationsInterval(
            start_at=datetime.fromisoformat(from_at.replace("Z", "+00:00")),
            end_at=datetime.fromisoformat(to_at.replace("Z", "+00:00")),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "operations_invalid_interval", "message": "Operations intervals must be ordered ISO-8601 timestamps with timezones."},
        ) from exc


def _tenant_id(request: Request) -> str:
    return str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))


def _portfolio_scope(request: Request, projects: KnowledgeRepository, interval: OperationsInterval | None) -> OperationsScope:
    role = str(getattr(request.state, "knowledge_role", ""))
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "operations_portfolio_admin_required", "message": "Portfolio operations require a tenant administrator."},
        )
    tenant_id = _tenant_id(request)
    return OperationsScope(
        tenant_id=tenant_id,
        role="tenant_admin",
        project_ids=tuple(str(project["id"]) for project in projects.list_projects_for_tenant(tenant_id)),
        interval=interval,
    )


def _project_scope(
    request: Request,
    projects: KnowledgeRepository,
    project_id: str,
    interval: OperationsInterval | None,
) -> OperationsScope:
    effective_project_id = _enforce_project_access(request, project_id)
    tenant_id = _tenant_id(request)
    if not projects.get_project_for_tenant(effective_project_id, tenant_id):
        # Do not reveal whether the project exists in another tenant.
        raise HTTPException(
            status_code=403,
            detail={"code": "operations_project_forbidden", "message": "This project is not available in the current tenant."},
        )
    return OperationsScope(
        tenant_id=tenant_id,
        role=str(getattr(request.state, "knowledge_role", "")),
        project_ids=(effective_project_id,),
        selected_project_id=effective_project_id,
        interval=interval,
    )


def _with_state(payload: dict) -> dict:
    response = dict(payload)
    coverage = response.get("coverage") if isinstance(response.get("coverage"), dict) else {}
    response["state"] = str(coverage.get("state") or "unavailable")
    return response


@router.get("/portfolio")
def operations_portfolio(
    request: Request,
    from_at: Annotated[str, Query(alias="from")] = "",
    to_at: Annotated[str, Query(alias="to")] = "",
    context: OperationsContext = Depends(get_operations_context),
):
    interval = _interval(from_at, to_at)
    scope = _portfolio_scope(request, context.service.project_repository, interval)
    return ApiResponse.ok(_with_state(context.service.overview(scope)))


@router.get("/projects/{project_id}")
def operations_project(
    request: Request,
    project_id: str,
    from_at: Annotated[str, Query(alias="from")] = "",
    to_at: Annotated[str, Query(alias="to")] = "",
    context: OperationsContext = Depends(get_operations_context),
):
    interval = _interval(from_at, to_at)
    scope = _project_scope(request, context.service.project_repository, project_id, interval)
    return ApiResponse.ok(_with_state(context.service.overview(scope)))


@router.get("/projects/{project_id}/graph")
def operations_project_graph(
    request: Request,
    project_id: str,
    mission_id: str = "",
    node_type: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    relation: list[str] = Query(default=[]),
    from_at: Annotated[str, Query(alias="from")] = "",
    to_at: Annotated[str, Query(alias="to")] = "",
    limit: int = Query(default=200, ge=1, le=500),
    cursor: str = Query(default="", max_length=512),
    context: OperationsContext = Depends(get_operations_context),
):
    interval = _interval(from_at, to_at)
    scope = _project_scope(request, context.service.project_repository, project_id, interval)
    try:
        payload = context.graph.project_graph(
            scope,
            project_id=project_id,
            mission_id=mission_id,
            node_types=node_type,
            statuses=status,
            relations=relation,
            interval=interval,
            limit=limit,
            cursor=cursor,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "operations_project_forbidden", "message": "This project is not available in the current tenant."},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "operations_invalid_graph_query", "message": str(exc)[:300]},
        ) from exc
    payload.update(
        {
            "generated_at": datetime.now().astimezone().isoformat(),
            "scope": scope.model_dump(mode="json"),
            "coverage": {"state": "available", "record_count": len(payload["nodes"]), "reason": ""},
            "state": "available",
        }
    )
    return ApiResponse.ok(payload)
