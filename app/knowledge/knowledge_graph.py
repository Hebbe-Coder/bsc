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
            for sequence, source_id in enumerate(dict.fromkeys(_SOURCE_REF.findall(content))):
                source = self.repository.get_source(project_id, source_id)
                evidence = self._evidence_metadata(page, source_id, sequence, source)
                edges.append(self._edge(
                    project_id,
                    page_id,
                    source_id,
                    "wiki_cites_source",
                    metadata={"evidence": evidence},
                    revision=evidence["page_content_hash"],
                ))
                if page.get("page_kind") == "decision":
                    edges.append(self._edge(
                        project_id,
                        page_id,
                        source_id,
                        "decision_uses_evidence",
                        metadata={"evidence": evidence},
                        revision=evidence["page_content_hash"],
                    ))
            if proposal_id:
                edges.append(self._edge(project_id, proposal_id, page_id, "proposal_changes_page"))
        return self.repository.replace_graph_edges(project_id, edges)

    def list_edges(
        self, project_id: str, edge_type: str | None = None, *, limit: int = 1000, offset: int = 0
    ) -> list[dict]:
        return self.repository.list_graph_edges(project_id, edge_type=edge_type, limit=limit, offset=offset)

    def backlinks(self, *, project_id: str, page_id: str, limit: int = 200) -> list[dict]:
        if not self.repository.get_page(project_id, page_id):
            return []
        return self.repository.list_backlinks(project_id, page_id, limit=limit)

    def visualization(
        self,
        *,
        project_id: str,
        edge_type: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return only persisted graph entities so the UI never invents graph nodes."""
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        edges = self.list_edges(project_id, edge_type=edge_type, limit=limit, offset=offset)
        total = self.repository.count_graph_edges(project_id, edge_type=edge_type)
        nodes: dict[str, dict] = {}
        for source in self.repository.list_sources(project_id):
            nodes[source["id"]] = {
                "id": source["id"], "node_type": "source", "label": source.get("origin") or source["id"],
                "status": source.get("status", ""), "created_at": source.get("captured_at", ""),
            }
        for page in self.repository.list_pages(project_id):
            nodes[page["id"]] = {
                "id": page["id"], "node_type": "page", "label": page.get("title") or page.get("path") or page["id"],
                "status": page.get("status", "published"), "created_at": page.get("published_at") or page.get("created_at", ""),
            }
        for proposal in self.repository.list_proposals(project_id):
            nodes[proposal["id"]] = {
                "id": proposal["id"], "node_type": "proposal", "label": proposal.get("rationale") or proposal["id"],
                "status": proposal.get("status", ""), "created_at": proposal.get("created_at", ""),
            }
        referenced_ids = {edge["from_id"] for edge in edges} | {edge["to_id"] for edge in edges}
        return {
            "nodes": [node for node_id, node in nodes.items() if node_id in referenced_ids],
            "edges": edges,
            "total": total,
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(edges) < total,
        }

    @staticmethod
    def _edge(
        project_id: str,
        from_id: str,
        to_id: str,
        edge_type: str,
        *,
        metadata: dict[str, Any] | None = None,
        revision: str = "",
    ) -> KnowledgeGraphEdge:
        edge_id = hashlib.sha256(f"{project_id}|{from_id}|{to_id}|{edge_type}".encode("utf-8")).hexdigest()[:24]
        return KnowledgeGraphEdge(
            id=edge_id,
            project_id=project_id,
            from_id=from_id,
            to_id=to_id,
            edge_type=edge_type,
            metadata=metadata or {},
            revision=revision,
        )

    @staticmethod
    def _evidence_metadata(
        page: dict[str, Any],
        source_id: str,
        sequence: int,
        source: dict[str, Any] | None,
    ) -> dict[str, Any]:
        page_content = str(page.get("content") or "")
        page_hash = str(page.get("content_hash") or hashlib.sha256(page_content.encode("utf-8")).hexdigest())
        page_version = int(page.get("version") or 0)
        citation_id = hashlib.sha256(f"{page['id']}|{source_id}|{sequence}".encode("utf-8")).hexdigest()[:24]
        return {
            "citation_id": citation_id,
            "source_id": source_id,
            "source_content_hash": str((source or {}).get("content_hash") or ""),
            "source_status": str((source or {}).get("status") or "missing"),
            "source_revision_available": bool(source),
            "page_content_hash": page_hash,
            "page_version": page_version,
            "extraction_method": "explicit_source_marker_v1",
        }
