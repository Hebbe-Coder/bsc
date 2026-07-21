"""Project-scoped Knowledge Graph derived from published Wiki page snapshots."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.knowledge.wiki_contracts import KnowledgeGraphEdge
from app.knowledge.wiki_repository import WikiRepository

_SOURCE_REF = re.compile(r"\[source:([^\]\s]+)\]")
_WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")


class KnowledgeGraphService:
    """Rebuild only derived graph edges; it never mutates pages or source evidence."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def rebuild(self, *, project_id: str, pages: list[dict[str, Any]], proposal_id: str = "") -> list[dict]:
        page_by_path = {}
        for page in pages:
            if page.get("project_id") != project_id:
                raise ValueError("pages must be project scoped")
            page_by_path[page["path"]] = page
        edges: list[KnowledgeGraphEdge] = []
        for page in pages:
            page_id = str(page["id"])
            content = str(page.get("content") or "")
            for target in _WIKI_LINK.findall(content):
                target_path = target if target.endswith(".md") else f"{target}.md"
                target_page = page_by_path.get(target_path)
                if target_page:
                    edges.append(self._edge(project_id, page_id, str(target_page["id"]), "wiki_links_to"))
            for source_id in _SOURCE_REF.findall(content):
                edges.append(self._edge(project_id, page_id, source_id, "wiki_cites_source"))
                if page.get("page_kind") == "decision":
                    edges.append(self._edge(project_id, page_id, source_id, "decision_uses_evidence"))
            if proposal_id:
                edges.append(self._edge(project_id, proposal_id, page_id, "proposal_changes_page"))
        return self.repository.replace_graph_edges(project_id, edges)

    def list_edges(self, project_id: str, edge_type: str | None = None) -> list[dict]:
        return self.repository.list_graph_edges(project_id, edge_type=edge_type)

    @staticmethod
    def _edge(project_id: str, from_id: str, to_id: str, edge_type: str) -> KnowledgeGraphEdge:
        edge_id = hashlib.sha256(f"{project_id}|{from_id}|{to_id}|{edge_type}".encode("utf-8")).hexdigest()[:24]
        return KnowledgeGraphEdge(id=edge_id, project_id=project_id, from_id=from_id, to_id=to_id, edge_type=edge_type)
