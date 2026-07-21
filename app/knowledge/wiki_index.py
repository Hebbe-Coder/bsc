"""Rebuildable search projection for immutable evidence and authoritative Wiki pages."""

from __future__ import annotations

import hashlib
from typing import Any

from app.knowledge.service import KnowledgeService
from app.knowledge.wiki_repository import WikiRepository


class WikiSearchIndex:
    """Project source/Wiki records into the existing hybrid retrieval tables."""

    def __init__(self, repository: WikiRepository, service: KnowledgeService | None = None) -> None:
        self.repository = repository
        self.service = service or KnowledgeService(repo=repository)

    def project_source(self, source: dict[str, Any]) -> dict[str, Any]:
        result = self.service.ingest_text(
            str(source["raw_content"]),
            project_id=str(source["project_id"]),
            title=self._title(str(source.get("raw_content") or ""), str(source.get("origin") or source["id"])),
            source=f"evidence://{source['project_id']}/{source['id']}",
            doc_format=f"evidence/{source['source_type']}",
            doc_id=f"wiki-source-{source['id']}",
        )
        return self._normalized_result(result)

    def sync_wiki_snapshot(self, *, project_id: str, contents: dict[str, str]) -> dict[str, Any]:
        managed = {
            path: content
            for path, content in contents.items()
            if path == "AGENTS.md" or path.startswith("wiki/")
        }
        expected_ids: set[str] = set()
        failures: list[dict[str, str]] = []
        indexed = 0
        for path, content in sorted(managed.items()):
            doc_id = self.wiki_doc_id(project_id, path)
            expected_ids.add(doc_id)
            result = self._normalized_result(
                self.service.ingest_text(
                    content,
                    project_id=project_id,
                    title=self._title(content, path),
                    source=f"wiki://{project_id}/{path}",
                    doc_format="wiki_markdown",
                    doc_id=doc_id,
                )
            )
            if result["status"] == "failed":
                failures.append({"path": path, "code": result["code"]})
            else:
                indexed += 1

        stale_rows = self.repository._execute(
            "SELECT id FROM knowledge_docs WHERE project_id=? AND doc_format='wiki_markdown'",
            (project_id,),
        ).fetchall()
        stale_ids = {str(row["id"]) for row in stale_rows} - expected_ids
        removed = sum(1 for doc_id in stale_ids if self.service.delete_document(doc_id))
        return {"indexed": indexed, "removed": removed, "failures": failures}

    @staticmethod
    def wiki_doc_id(project_id: str, path: str) -> str:
        digest = hashlib.sha256(f"{project_id}|{path}".encode("utf-8")).hexdigest()[:24]
        return f"wiki-page-{digest}"

    @staticmethod
    def _title(content: str, fallback: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip() or fallback
        return fallback

    @staticmethod
    def _normalized_result(result: dict[str, Any]) -> dict[str, Any]:
        if result.get("status") == "error":
            return {"status": "failed", "code": "index_backend_error"}
        return {
            "status": str(result.get("status") or "failed"),
            "doc_id": str(result.get("doc_id") or ""),
            "version": result.get("version"),
            "code": "" if result.get("status") else "index_backend_error",
        }
