"""Rebuildable search projection for immutable evidence and authoritative Wiki pages."""

from __future__ import annotations

import hashlib
from typing import Any

from app.knowledge.service import KnowledgeService
from app.knowledge.source_triage import source_admission_reason
from app.knowledge.wiki_repository import WikiRepository


class WikiSearchIndex:
    """Project source/Wiki records into the existing hybrid retrieval tables."""

    # The complete derivative remains in the immutable Artifact Graph. Search
    # receives a bounded, rebuildable view so one large local file cannot turn
    # a source-sync run into thousands of retrieval chunks.
    MAX_EXTRACTION_INDEX_CHARS = 64 * 1024

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
            doc_id=self.source_doc_id(str(source["id"])),
        )
        return self._normalized_result(result)

    def project_completed_extraction(
        self,
        *,
        source: dict[str, Any],
        extraction: dict[str, Any],
    ) -> dict[str, Any]:
        """Project one admitted local derivative without mutating A-layer bytes.

        The retrieval document deliberately keeps the original ``source_id`` in
        its URI. A retrieval hit can therefore select the immutable source as
        before, while the context compiler receives the bounded extraction
        marked with its auditable derivative identifier.
        """
        project_id = str(source.get("project_id") or "").strip()
        source_id = str(source.get("id") or "").strip()
        extraction_id = str(extraction.get("id") or "").strip()
        if not project_id or not source_id or not extraction_id:
            return {"status": "skipped", "code": "extraction_identity_missing"}
        if (
            str(extraction.get("project_id") or "") != project_id
            or str(extraction.get("source_id") or "") != source_id
        ):
            return {"status": "skipped", "code": "extraction_scope_mismatch"}
        if str(source.get("status") or "") not in {"eligible", "processed"}:
            return {"status": "skipped", "code": "source_not_admitted"}
        if source_admission_reason(self.repository, project_id, source):
            return {"status": "skipped", "code": "source_admission_pending"}
        extraction_status = str(extraction.get("status") or "").lower()
        if extraction_status not in {"complete", "partial"}:
            return {"status": "skipped", "code": "extraction_not_usable"}
        derivative = self.repository.get_extraction_content(project_id, extraction_id) or {}
        content = str(derivative.get("content") or "").strip()
        if not content:
            return {"status": "skipped", "code": "extraction_content_unavailable"}

        bounded_content = content[: self.MAX_EXTRACTION_INDEX_CHARS]
        truncated = len(content) > len(bounded_content)
        rendered = (
            f"[LOCAL_EXTRACTION source={source_id} extraction={extraction_id} "
            f"status={extraction_status} truncated={'true' if truncated else 'false'}]\n"
            f"{bounded_content}"
        )
        result = self.service.ingest_text(
            rendered,
            project_id=project_id,
            title=self._title(content, str(source.get("origin") or source_id)),
            source=f"evidence://{project_id}/{source_id}",
            doc_format=f"evidence_extraction/{str(extraction.get('extractor') or 'local')}",
            doc_id=self.source_doc_id(source_id),
        )
        return {
            **self._normalized_result(result),
            "source_id": source_id,
            "extraction_id": extraction_id,
        }

    def sync_completed_extraction_projections(self, *, project_id: str) -> dict[str, int]:
        """Refresh one searchable derivative view for every admitted source.

        The source document id is stable, so a newer extraction replaces only
        the rebuildable retrieval projection. Old derivatives remain intact in
        the Artifact Graph and Evidence Atlas for audit and rollback.
        """
        summary = {"projected": 0, "unchanged": 0, "failed": 0, "skipped": 0}
        for source in self.repository.list_sources(project_id):
            if str(source.get("status") or "") not in {"eligible", "processed"}:
                continue
            candidates: list[dict[str, Any]] = []
            for asset in self.repository.list_media_assets(project_id, source_id=str(source.get("id") or "")):
                extraction = self.repository.latest_extraction_for_asset(project_id, str(asset.get("id") or ""))
                if extraction and str(extraction.get("status") or "").lower() in {"complete", "partial"}:
                    candidates.append(extraction)
            if not candidates:
                continue
            latest = max(candidates, key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))
            result = self.project_completed_extraction(source=source, extraction=latest)
            status = str(result.get("status") or "")
            if status in {"ingested", "updated"}:
                summary["projected"] += 1
            elif status == "skipped" and result.get("code") == "unchanged":
                summary["unchanged"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            else:
                summary["failed"] += 1
        return summary

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
    def source_doc_id(source_id: str) -> str:
        return f"wiki-source-{source_id}"

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
        status = str(result.get("status") or "failed")
        reason = str(result.get("reason") or "")
        return {
            "status": status,
            "doc_id": str(result.get("doc_id") or ""),
            "version": result.get("version"),
            "code": reason if status == "skipped" and reason else "" if result.get("status") else "index_backend_error",
        }
