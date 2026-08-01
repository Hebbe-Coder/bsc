"""Metadata-only typed anchors for multimodal extraction derivatives."""

from __future__ import annotations

from typing import Any

from app.knowledge.wiki_contracts import ReferenceLink
from app.knowledge.wiki_repository import WikiRepository


class ExtractionReferenceProjector:
    """Connect immutable sources to their derived extraction/table records.

    The projector intentionally reads only repository metadata. It has no Vault
    root, source-body accessor, derivative-content accessor, network client, or
    lifecycle mutation. Re-running it is safe and repairs records produced
    before the explicit-anchor contract existed.
    """

    REVISION = "multimodal_extraction_reference_v1"

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def project_extraction_id(self, project_id: str, extraction_id: str) -> dict[str, int]:
        extraction = self.repository.get_extraction_artifact(project_id, extraction_id)
        if extraction is None:
            return self._empty(skipped=1)
        identities = self._identities(project_id, str(extraction.get("source_id") or ""))
        return self._project_extraction(extraction, identities)

    def project_table_id(self, project_id: str, table_id: str) -> dict[str, int]:
        table = self.repository.get_table_artifact(project_id, table_id)
        if table is None:
            return self._empty(skipped=1)
        identities = self._identities(project_id, str(table.get("source_id") or ""))
        return self._project_table(table, identities)

    def backfill_project(self, project_id: str) -> dict[str, int]:
        """Create any missing typed anchors from existing bounded derivatives."""
        identities_by_source: dict[str, set[tuple[str, str, str, str, str]]] = {}
        total = self._empty()
        for extraction in self.repository.list_extraction_artifacts(project_id, limit=500):
            source_id = str(extraction.get("source_id") or "")
            identities = identities_by_source.setdefault(source_id, self._identities(project_id, source_id))
            self._add(total, self._project_extraction(extraction, identities))
        for table in self.repository.list_table_artifacts(project_id, limit=500):
            source_id = str(table.get("source_id") or "")
            identities = identities_by_source.setdefault(source_id, self._identities(project_id, source_id))
            self._add(total, self._project_table(table, identities))
        return total

    def _project_extraction(
        self,
        extraction: dict[str, Any],
        identities: set[tuple[str, str, str, str, str]],
    ) -> dict[str, int]:
        return self._project(
            project_id=str(extraction.get("project_id") or ""),
            source_id=str(extraction.get("source_id") or ""),
            target_type="extraction",
            target_id=str(extraction.get("id") or ""),
            relation="has_extraction",
            metadata={
                "projector": self.REVISION,
                "asset_id": str(extraction.get("asset_id") or ""),
                "extractor": str(extraction.get("extractor") or ""),
                "extractor_revision": str(extraction.get("extractor_revision") or ""),
                "input_hash": str(extraction.get("input_hash") or ""),
                "content_hash": str(extraction.get("content_hash") or ""),
                "status": str(extraction.get("status") or ""),
            },
            identities=identities,
        )

    def _project_table(
        self,
        table: dict[str, Any],
        identities: set[tuple[str, str, str, str, str]],
    ) -> dict[str, int]:
        return self._project(
            project_id=str(table.get("project_id") or ""),
            source_id=str(table.get("source_id") or ""),
            target_type="table",
            target_id=str(table.get("id") or ""),
            relation="has_table",
            metadata={
                "projector": self.REVISION,
                "extraction_id": str(table.get("extraction_id") or ""),
                "content_hash": str(table.get("content_hash") or ""),
                "status": str(table.get("status") or ""),
            },
            identities=identities,
        )

    def _project(
        self,
        *,
        project_id: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relation: str,
        metadata: dict[str, str],
        identities: set[tuple[str, str, str, str, str]],
    ) -> dict[str, int]:
        if not project_id or not source_id or not target_id:
            return self._empty(skipped=1)
        identity = (target_type, target_id, "artifact", "", relation)
        if identity in identities:
            return self._empty(existing=1)
        try:
            self.repository.create_reference_link(
                ReferenceLink(
                    project_id=project_id,
                    source_id=source_id,
                    target_type=target_type,
                    target_id=target_id,
                    anchor_type="artifact",
                    anchor="",
                    relation=relation,
                    metadata=metadata,
                )
            )
        except KeyError:
            return self._empty(skipped=1)
        identities.add(identity)
        return self._empty(created=1)

    def _identities(self, project_id: str, source_id: str) -> set[tuple[str, str, str, str, str]]:
        if not project_id or not source_id:
            return set()
        return {
            self._identity(reference)
            for reference in self.repository.list_reference_links(project_id, source_id=source_id, limit=500)
        }

    @staticmethod
    def _identity(reference: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(reference.get("target_type") or ""),
            str(reference.get("target_id") or ""),
            str(reference.get("anchor_type") or ""),
            str(reference.get("anchor") or ""),
            str(reference.get("relation") or ""),
        )

    @staticmethod
    def _empty(*, created: int = 0, existing: int = 0, skipped: int = 0) -> dict[str, int]:
        return {"created": created, "existing": existing, "skipped": skipped}

    @staticmethod
    def _add(total: dict[str, int], value: dict[str, int]) -> None:
        for field in total:
            total[field] += int(value.get(field) or 0)
