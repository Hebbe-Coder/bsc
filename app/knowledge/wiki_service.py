"""Narrow project Wiki facade shared by API, MCP, tasks, and tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.knowledge.wiki_bootstrap import WikiBootstrapService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_index import WikiSearchIndex
from app.knowledge.wiki_repository import WikiRepository


class WikiService:
    """Expose bootstrap and read operations without transport or scheduler concerns."""

    def __init__(self, repository: WikiRepository, *, search_index: Any | None = None) -> None:
        self.repository = repository
        self.search_index = search_index or WikiSearchIndex(repository)

    def initialize_project(self, project_id: str, actor: str = "") -> dict[str, Any]:
        run = KnowledgeRun(
            project_id=project_id,
            run_type="wiki_initialize",
            trigger="manual",
            status=RunStatus.RUNNING,
            actor_id=actor,
            started_at=datetime.now(timezone.utc),
        )
        self.repository.create_run(run)
        try:
            result = WikiBootstrapService(self.repository, search_index=self.search_index).initialize(
                project_id=project_id,
                actor_id=actor,
            )
            self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.COMPLETED,
                output_refs={"created": result["created"], "indexing": result["indexing"]},
            )
            return {**result, "run_id": run.id}
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=str(exc))
            raise

    def get_workspace_status(self, project_id: str) -> dict[str, Any]:
        mapping = self.repository.get_vault(project_id)
        return {
            "project_id": project_id,
            "configured": bool(mapping),
            "status": mapping.get("status") if mapping else "unconfigured",
            "vault_path": mapping.get("vault_path", "") if mapping else "",
            "pages": len(self.repository.list_pages(project_id)),
            "sources": len(self.repository.list_sources(project_id)),
            "runs": len(self.repository.list_runs(project_id)),
            "schedules": len(self.repository.list_schedules(project_id)),
        }

    def list_pages(self, project_id: str) -> list[dict[str, Any]]:
        return self.repository.list_pages(project_id)

    def read_page(self, project_id: str, page_id: str) -> dict[str, Any]:
        page = self.repository.get_page(project_id, page_id)
        content = self.repository.get_page_content(project_id, page_id) if page else None
        if not page or not content:
            raise KeyError("published Wiki page not found")
        return {
            "page": page,
            "content": content["content"],
            "revisions": self.repository.list_page_revisions(project_id, page_id),
            "citations": self.repository.list_citations(project_id, page_id),
        }

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        return self.repository.list_runs(project_id)
