"""MCP adapters for the read-only Knowledge Operations projection."""

from __future__ import annotations

from typing import Any

from app.api.dbos_api import dbos_service_for
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.operations_contracts import OperationsScope
from app.knowledge.operations_graph import KnowledgeOperationsGraphService
from app.knowledge.operations_service import KnowledgeOperationsService
from app.repositories.knowledge_repository import KnowledgeRepository


def _services() -> tuple[GrowthRepository, KnowledgeOperationsService, KnowledgeOperationsGraphService]:
    repository = GrowthRepository()
    projects = KnowledgeRepository(backend=repository._get_connection())
    projects._owns_connection = False
    return (
        repository,
        KnowledgeOperationsService(
            repository=repository,
            project_repository=projects,
            dbos_store_factory=lambda project_id, tenant_id: dbos_service_for(project_id, tenant_id=tenant_id).store,
        ),
        KnowledgeOperationsGraphService(repository=repository, project_repository=projects),
    )


def project_tenant(project_id: str) -> str:
    """Return the durable tenant binding for an already-authorized project key."""
    repository, service, _graph = _services()
    try:
        project = service.project_repository.get_project(project_id)
        tenant_id = str(project.get("tenant_id") or "").strip() if project else ""
        if not tenant_id:
            raise PermissionError("authorized project is not available in a tenant")
        return tenant_id
    finally:
        repository.close()


def portfolio(tenant_id: str = "") -> dict[str, Any]:
    repository, service, _graph = _services()
    try:
        tenant = tenant_id or settings.DEFAULT_TENANT_ID
        projects = service.project_repository.list_projects_for_tenant(tenant)
        payload = service.overview(
            OperationsScope(
                tenant_id=tenant,
                role="tenant_admin",
                project_ids=tuple(str(project["id"]) for project in projects),
            )
        )
        payload["state"] = payload["coverage"]["state"]
        return payload
    finally:
        repository.close()


def project(project_id: str, *, tenant_id: str = "") -> dict[str, Any]:
    repository, service, _graph = _services()
    try:
        tenant = tenant_id or settings.DEFAULT_TENANT_ID
        payload = service.overview(
            OperationsScope(
                tenant_id=tenant,
                role="project_reader",
                project_ids=(project_id,),
                selected_project_id=project_id,
            )
        )
        payload["state"] = payload["coverage"]["state"]
        return payload
    finally:
        repository.close()


def graph(project_id: str, *, mission_id: str = "", limit: int = 200, cursor: str = "", tenant_id: str = "") -> dict[str, Any]:
    repository, service, graph_service = _services()
    try:
        tenant = tenant_id or settings.DEFAULT_TENANT_ID
        scope = OperationsScope(
            tenant_id=tenant,
            role="project_reader",
            project_ids=(project_id,),
            selected_project_id=project_id,
        )
        payload = graph_service.project_graph(
            scope,
            project_id=project_id,
            mission_id=mission_id,
            limit=limit,
            cursor=cursor,
        )
        payload.update(
            {
                "scope": scope.model_dump(mode="json"),
                "coverage": {"state": "available", "record_count": len(payload["nodes"]), "reason": ""},
                "state": "available",
            }
        )
        return payload
    finally:
        repository.close()
