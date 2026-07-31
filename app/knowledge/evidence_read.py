"""Redacted project-scoped read model for multimodal knowledge evidence."""

from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.knowledge.evidence_scope import is_active_evidence_source, is_scope_excluded_source
from app.knowledge.multimodal_extraction import LocalMultimodalExtractor
from app.knowledge.wiki_repository import WikiRepository


_SOURCE_METADATA_KEYS = frozenset({
    "obsidian_plugin", "plugin_name", "obsidian_adapter", "obsidian_workspace_role",
    "extension", "extraction_status", "zotero_citation_key", "zotero_doi",
    "zotero_url", "zotero_source_date", "zotero_item_key", "source_present",
})
_ASSET_METADATA_KEYS = frozenset({"sync", "extension"})
_EXTRACTION_METADATA_KEYS = frozenset({
    "row_count", "column_count", "truncated", "sheet", "node_count", "text_node_count",
    "element_count", "drawing_json_detected", "page_count", "width", "height", "mode",
    "format", "ocr", "byte_size", "limit_bytes", "capability",
})

_ASSET_LABELS = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel workbook",
    "application/vnd.ms-excel": "Excel workbook",
    "application/octet-stream": "Binary file",
    "text/csv": "CSV",
    "text/markdown": "Markdown",
    "text/plain": "Text file",
}

_EXTRACTION_LABELS = {
    "canvas-elements": "Canvas elements",
    "csv-table": "CSV table",
    "excalidraw-elements": "Excalidraw elements",
    "ffprobe-media-metadata": "Media metadata",
    "pdf-ocr": "PDF OCR",
    "pdf-text": "PDF text",
    "utf8-text": "Text extraction",
    "xlsx-table": "Excel table",
}

_MAX_TABLE_PREVIEW_PAGE_SIZE = 100
_MAX_TABLE_PREVIEW_CELL_CHARS = 1_024
_MAX_IMAGE_PREVIEW_BYTES = 10 * 1024 * 1024
_MAX_IMAGE_PREVIEW_EDGE = 1_280
def _metadata(value: Any, allowed: frozenset[str]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {key: raw[key] for key in sorted(allowed) if key in raw}


class EvidenceReadService:
    """Compose visualization data without reading source or derivative bodies."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def overview(self, project_id: str, *, limit: int = 100) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 200))
        source_records = [
            item for item in self.repository.list_sources(project_id)
            if is_active_evidence_source(item)
        ]
        active_source_ids = {str(item["id"]) for item in source_records}
        sources = [self._source(item) for item in source_records]
        assets = [
            self._asset(item)
            for item in self.repository.list_media_assets(project_id, limit=500)
            if str(item.get("source_id") or "") in active_source_ids
        ]
        extractions = [
            self._extraction(item)
            for item in self.repository.list_extraction_artifacts(project_id, limit=500)
            if str(item.get("source_id") or "") in active_source_ids
        ]
        tables = [
            self._table(item)
            for item in self.repository.list_table_artifacts(project_id, limit=500)
            if str(item.get("source_id") or "") in active_source_ids
        ]
        references = self._references(project_id, active_source_ids)
        timeline = self._timeline(sources, assets, extractions, tables, references, limit=bounded_limit)
        graph = self._graph(sources, assets, extractions, tables, references, limit=bounded_limit)
        extraction_counts = Counter(str(item["status"]) for item in extractions)
        source_counts = Counter(str(item["status"]) for item in sources)
        total = len(sources) + len(assets) + len(extractions) + len(tables) + len(references)
        return {
            "project_id": project_id,
            "state": "available" if total else "no_sample",
            "summary": {
                "sources": len(sources),
                "assets": len(assets),
                "extractions": dict(sorted(extraction_counts.items())),
                "tables": len(tables),
                "references": len(references),
                "source_statuses": dict(sorted(source_counts.items())),
                "denominator": total,
            },
            "capabilities": LocalMultimodalExtractor.capabilities(),
            "sources": sources[:bounded_limit],
            "assets": assets[:bounded_limit],
            "extractions": extractions[:bounded_limit],
            "tables": tables[:bounded_limit],
            "references": references[:bounded_limit],
            "timeline": timeline,
            "graph": graph,
            "truncated": any(len(values) > bounded_limit for values in (sources, assets, extractions, tables, references, timeline)),
        }

    def record(self, project_id: str, record_type: str, record_id: str) -> dict[str, Any] | None:
        if record_type == "source":
            value = self.repository.get_source(project_id, record_id)
            return self._source(value) if value and is_active_evidence_source(value) else None
        if record_type == "asset":
            value = self.repository.get_media_asset(project_id, record_id)
            return self._asset(value) if value and self._source_is_visible(project_id, value.get("source_id")) else None
        if record_type == "extraction":
            value = self.repository.get_extraction_artifact(project_id, record_id)
            return self._extraction(value) if value and self._source_is_visible(project_id, value.get("source_id")) else None
        if record_type == "table":
            value = self.repository.get_table_artifact(project_id, record_id)
            return self._table(value) if value and self._source_is_visible(project_id, value.get("source_id")) else None
        if record_type == "reference":
            value = self.repository.get_reference_link(project_id, record_id)
            if value and self._source_is_visible(project_id, value.get("source_id")):
                return self._reference(value)
            if record_id.startswith("citation:"):
                citation = self.repository.get_citation(project_id, record_id.removeprefix("citation:"))
                return self._citation_reference(citation) if citation and self._source_is_visible(project_id, citation.get("source_id")) else None
            return None
        raise ValueError("unsupported evidence record type")

    def _references(self, project_id: str, active_source_ids: set[str]) -> list[dict[str, Any]]:
        """Join explicit evidence links with redacted, read-only Wiki citations.

        Wiki publication owns ``knowledge_citations`` and its immutable claim
        text. The Evidence Atlas needs the same provenance edge but must not
        duplicate or expose the claim. These synthetic records make that edge
        inspectable without migrating, mutating, or merging the two domains.
        """
        explicit = [
            self._reference(item)
            for item in self.repository.list_reference_links(project_id, limit=500)
            if str(item.get("source_id") or "") in active_source_ids
        ]
        citations = [
            self._citation_reference(item)
            for item in self.repository.list_citations(project_id, include_stale=True)
            if str(item.get("source_id") or "") in active_source_ids
        ]
        return sorted([*explicit, *citations], key=lambda item: (str(item["created_at"]), str(item["id"])), reverse=True)

    def table_preview(
        self,
        project_id: str,
        table_id: str,
        *,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any] | None:
        """Return one bounded, authorized view of a tabular derivative.

        Overview and record endpoints intentionally exclude derivative content.
        A table cell is exposed only through this explicit project-scoped
        inspector path, never through the graph or metadata catalog.
        """
        table = self.repository.get_table_artifact(project_id, table_id)
        if table is None or not self._source_is_visible(project_id, table.get("source_id")):
            return None

        bounded_page = max(1, int(page))
        bounded_page_size = max(1, min(int(page_size), _MAX_TABLE_PREVIEW_PAGE_SIZE))
        schema = [str(value)[:256] for value in table.get("schema", []) if isinstance(value, str)]
        declared_rows = max(0, int(table.get("row_count") or 0))
        content = self.repository.get_extraction_content(project_id, str(table["extraction_id"]))
        if content is None or not str(content.get("content_hash") or ""):
            return self._empty_table_preview(
                table,
                schema=schema,
                page=bounded_page,
                page_size=bounded_page_size,
                state="unavailable",
                reason="table_derivative_unavailable",
            )
        if str(content.get("content_hash") or "") != str(table.get("content_hash") or ""):
            return self._empty_table_preview(
                table,
                schema=schema,
                page=bounded_page,
                page_size=bounded_page_size,
                state="unavailable",
                reason="table_derivative_content_hash_mismatch",
            )

        derived_rows = self._table_rows(str(content.get("content") or ""), schema)
        available_rows = min(len(derived_rows), declared_rows) if declared_rows else len(derived_rows)
        derived_rows = derived_rows[:available_rows]
        total_pages = max(1, (available_rows + bounded_page_size - 1) // bounded_page_size)
        current_page = min(bounded_page, total_pages)
        start = (current_page - 1) * bounded_page_size
        metadata = table.get("metadata") if isinstance(table.get("metadata"), dict) else {}
        extraction = self.repository.get_extraction_artifact(project_id, str(table["extraction_id"])) or {}
        extraction_metadata = extraction.get("metadata") if isinstance(extraction.get("metadata"), dict) else {}
        return {
            "table_id": str(table["id"]),
            "source_id": str(table["source_id"]),
            "extraction_id": str(table["extraction_id"]),
            "schema": schema,
            "units": dict(table.get("units") or {}),
            "rows": derived_rows[start:start + bounded_page_size],
            "page": current_page,
            "page_size": bounded_page_size,
            "total_rows": declared_rows,
            "available_rows": available_rows,
            "total_pages": total_pages,
            "truncated": bool(extraction_metadata.get("truncated")) or available_rows < declared_rows,
            "derived": True,
            "state": "available" if available_rows else "no_rows",
            "reason": "",
            "provenance": {
                "extractor": str(metadata.get("extractor") or extraction.get("extractor") or ""),
                "extractor_revision": str(metadata.get("extractor_revision") or extraction.get("extractor_revision") or ""),
                "sheet": str(extraction_metadata.get("sheet") or ""),
                "content_hash": str(table.get("content_hash") or ""),
            },
        }

    def image_thumbnail(self, project_id: str, asset_id: str) -> bytes | None:
        """Create a bounded, metadata-stripped image preview for one asset.

        The thumbnail is deliberately not part of overview data. Callers must
        first pass the same project authorization gate as every evidence read.
        """
        asset = self.repository.get_media_asset(project_id, asset_id)
        if (
            asset is None
            or not self._source_is_visible(project_id, asset.get("source_id"))
            or not str(asset.get("mime_type") or "").lower().startswith("image/")
        ):
            return None
        vault = self.repository.get_vault(project_id)
        project_path = str((vault or {}).get("vault_path") or "")
        storage_ref = str(asset.get("storage_ref") or "")
        if not project_path or not settings.OBSIDIAN_VAULT_ROOT or not storage_ref:
            return None
        try:
            relative = PurePosixPath(storage_ref)
            mapped_project = PurePosixPath(project_path.replace("\\", "/"))
            if (
                relative.is_absolute()
                or mapped_project.is_absolute()
                or not mapped_project.parts
                or ".." in relative.parts
                or ".." in mapped_project.parts
                or ":" in mapped_project.parts[0]
                or tuple(relative.parts[:len(mapped_project.parts)]) != tuple(mapped_project.parts)
            ):
                return None
            vault_root = Path(settings.OBSIDIAN_VAULT_ROOT).resolve()
            project_root = vault_root.joinpath(*mapped_project.parts).resolve()
            asset_path = vault_root.joinpath(*relative.parts).resolve()
            asset_path.relative_to(vault_root)
            asset_path.relative_to(project_root)
            if not asset_path.is_file() or asset_path.stat().st_size > _MAX_IMAGE_PREVIEW_BYTES:
                return None
            from PIL import Image, ImageOps

            with Image.open(asset_path) as original:
                image = ImageOps.exif_transpose(original)
                image.thumbnail((_MAX_IMAGE_PREVIEW_EDGE, _MAX_IMAGE_PREVIEW_EDGE))
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                output = BytesIO()
                image.save(output, format="WEBP", quality=84, method=4)
                return output.getvalue()
        except (OSError, ValueError):
            return None

    def _source_is_visible(self, project_id: str, source_id: Any) -> bool:
        if not source_id:
            return False
        source = self.repository.get_source(project_id, str(source_id))
        return bool(source) and is_active_evidence_source(source)

    @staticmethod
    def _table_rows(content: str, schema: list[str]) -> list[list[str]]:
        lines = content.splitlines()
        if len(lines) < 2:
            return []
        columns = len(schema)
        if not columns:
            columns = min(max(len(lines[0].split("\t")), 1), 100)
        rows: list[list[str]] = []
        for line in lines[1:]:
            values = line.split("\t")[:columns]
            values.extend([""] * (columns - len(values)))
            rows.append([value[:_MAX_TABLE_PREVIEW_CELL_CHARS] for value in values])
        return rows

    @staticmethod
    def _empty_table_preview(
        table: dict[str, Any],
        *,
        schema: list[str],
        page: int,
        page_size: int,
        state: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "table_id": str(table["id"]),
            "source_id": str(table["source_id"]),
            "extraction_id": str(table["extraction_id"]),
            "schema": schema,
            "units": dict(table.get("units") or {}),
            "rows": [],
            "page": page,
            "page_size": page_size,
            "total_rows": max(0, int(table.get("row_count") or 0)),
            "available_rows": 0,
            "total_pages": 1,
            "truncated": False,
            "derived": True,
            "state": state,
            "reason": reason,
            "provenance": {"extractor": "", "extractor_revision": "", "sheet": "", "content_hash": str(table.get("content_hash") or "")},
        }

    @staticmethod
    def _source(item: dict[str, Any]) -> dict[str, Any]:
        origin, origin_kind = EvidenceReadService._safe_origin(str(item.get("origin") or ""), str(item["id"]))
        return {
            "id": str(item["id"]), "record_type": "source", "source_type": str(item["source_type"]),
            "origin": origin, "origin_kind": origin_kind,
            "content_hash": str(item.get("content_hash") or ""), "trust_level": str(item.get("trust_level") or ""),
            "status": str(item.get("status") or ""), "captured_at": str(item.get("captured_at") or ""),
            "updated_at": str(item.get("updated_at") or ""), "metadata": _metadata(item.get("metadata"), _SOURCE_METADATA_KEYS),
        }

    @staticmethod
    def _safe_origin(origin: str, record_id: str) -> tuple[str, str]:
        normalized = origin.replace("\\", "/")
        is_vault_path = (
            normalized.startswith("projects/")
            or normalized.startswith("/")
            or normalized.startswith("../")
            or (len(normalized) >= 3 and normalized[1:3] == ":/")
        )
        if is_vault_path:
            return f"vault-source:{record_id[:8]}", "vault"
        if normalized.startswith(("http://", "https://")):
            return origin, "url"
        if normalized.startswith(("user://", "repo://")):
            return origin, "virtual"
        return origin, "opaque"

    @staticmethod
    def _asset(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item["id"]), "record_type": "asset", "source_id": str(item["source_id"]),
            "mime_type": str(item["mime_type"]), "byte_hash": str(item["byte_hash"]),
            "byte_size": int(item["byte_size"]),
            "rights": str(item["rights"]), "access_state": str(item["access_state"]),
            "created_at": str(item["created_at"]), "updated_at": str(item["updated_at"]),
            "metadata": _metadata(item.get("metadata"), _ASSET_METADATA_KEYS),
        }

    @staticmethod
    def _extraction(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item["id"]), "record_type": "extraction", "source_id": str(item["source_id"]),
            "asset_id": str(item["asset_id"]), "extractor": str(item["extractor"]),
            "extractor_revision": str(item["extractor_revision"]), "input_hash": str(item["input_hash"]),
            "content_hash": str(item.get("content_hash") or ""), "status": str(item["status"]),
            "error": str(item.get("error") or ""), "created_at": str(item["created_at"]),
            "metadata": _metadata(item.get("metadata"), _EXTRACTION_METADATA_KEYS),
        }

    @staticmethod
    def _table(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item["id"]), "record_type": "table", "source_id": str(item["source_id"]),
            "extraction_id": str(item["extraction_id"]), "schema": list(item.get("schema") or []),
            "row_count": int(item["row_count"]), "units": dict(item.get("units") or {}),
            "content_hash": str(item["content_hash"]), "status": str(item["status"]),
            "created_at": str(item["created_at"]),
        }

    @staticmethod
    def _reference(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item["id"]), "record_type": "reference", "source_id": str(item["source_id"]),
            "target_type": str(item["target_type"]), "target_id": str(item["target_id"]),
            "anchor_type": str(item["anchor_type"]), "anchor": str(item.get("anchor") or ""),
            "relation": str(item["relation"]), "resolution_state": str(item["resolution_state"]),
            "created_at": str(item["created_at"]),
        }

    @staticmethod
    def _citation_reference(item: dict[str, Any]) -> dict[str, Any]:
        status = str(item.get("status") or "")
        resolution_state = "resolved" if status == "active" else "stale" if status == "stale" else "broken"
        return {
            "id": f"citation:{str(item['id'])}", "record_type": "reference", "source_id": str(item["source_id"]),
            "target_type": "wiki_page", "target_id": str(item["wiki_page_id"]),
            "anchor_type": "wiki_citation", "anchor": "", "relation": "cites",
            "resolution_state": resolution_state, "created_at": str(item["created_at"]),
        }

    @staticmethod
    def _timeline(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for group in groups:
            for item in group:
                created_at = str(item.get("created_at") or item.get("captured_at") or "")
                timeline.append({
                    "id": item["id"], "record_type": item["record_type"], "status": str(item.get("status") or item.get("access_state") or ""),
                    "occurred_at": created_at,
                })
        return sorted(timeline, key=lambda item: (item["occurred_at"], item["id"]), reverse=True)[:limit]

    @staticmethod
    def _graph(
        sources: list[dict[str, Any]], assets: list[dict[str, Any]], extractions: list[dict[str, Any]],
        tables: list[dict[str, Any]], references: list[dict[str, Any]], *, limit: int,
    ) -> dict[str, Any]:
        nodes_by_id: dict[str, dict[str, Any]] = {}
        for item in [*sources, *assets, *extractions, *tables]:
            nodes_by_id[item["id"]] = EvidenceReadService._graph_node(item)
        all_edges: list[dict[str, Any]] = []
        for asset in assets:
            all_edges.append({"id": f"source-asset:{asset['source_id']}:{asset['id']}", "source": asset["source_id"], "target": asset["id"], "relation": "has_asset"})
        for extraction in extractions:
            all_edges.append({"id": f"asset-extraction:{extraction['asset_id']}:{extraction['id']}", "source": extraction["asset_id"], "target": extraction["id"], "relation": "extracted_by"})
        for table in tables:
            all_edges.append({"id": f"extraction-table:{table['extraction_id']}:{table['id']}", "source": table["extraction_id"], "target": table["id"], "relation": "contains_table"})
        for reference in references:
            source_id = reference["source_id"]
            target_id = reference["target_id"]
            graph_target_id = target_id
            if target_id not in nodes_by_id:
                graph_target_id = f"target:{reference['target_type']}:{target_id}"
                if graph_target_id not in nodes_by_id:
                    nodes_by_id[graph_target_id] = {
                        "id": graph_target_id,
                        "type": "target",
                        "status": reference["resolution_state"],
                        "target_type": reference["target_type"],
                        "target_id": target_id,
                        "anchor": str(reference.get("anchor") or ""),
                        "label": EvidenceReadService._target_graph_label(
                            str(reference["target_type"]),
                            target_id,
                            str(reference.get("anchor") or ""),
                        ),
                    }
            all_edges.append({"id": reference["id"], "source": source_id, "target": graph_target_id, "relation": reference["relation"], "resolution_state": reference["resolution_state"]})

        # Connected evidence gets the first display slots so a large source
        # inventory cannot turn a real lineage graph into a field of isolated nodes.
        connected_ids = {node_id for edge in all_edges for node_id in (edge["source"], edge["target"])}
        candidates = [node for node_id, node in nodes_by_id.items() if node_id in connected_ids]
        candidates.extend(node for node_id, node in nodes_by_id.items() if node_id not in connected_ids)
        nodes = candidates[:limit]
        visible_ids = {node["id"] for node in nodes}
        edges = [edge for edge in all_edges if edge["source"] in visible_ids and edge["target"] in visible_ids][:limit]
        omitted_edge_count = len(all_edges) - len(edges)
        return {
            "nodes": nodes,
            "edges": edges,
            "node_total": len(nodes_by_id),
            "edge_total": len(all_edges),
            "omitted_edge_count": omitted_edge_count,
            "truncated": len(candidates) > limit or omitted_edge_count > 0,
        }

    @staticmethod
    def _graph_node(item: dict[str, Any]) -> dict[str, Any]:
        record_type = str(item["record_type"])
        label = {
            "source": EvidenceReadService._source_graph_label(item),
            "asset": f"Asset: {EvidenceReadService._asset_graph_label(str(item.get('mime_type') or ''))}",
            "extraction": (
                f"Extraction: {EvidenceReadService._extraction_graph_label(str(item.get('extractor') or ''))}"
                f" ({str(item.get('status') or 'recorded')})"
            ),
            "table": f"Table: {int(item.get('row_count') or 0)} rows",
        }.get(record_type, f"{record_type.title()}: {str(item['id'])[:8]}")
        return {
            "id": item["id"],
            "type": record_type,
            "status": str(item.get("status") or item.get("access_state") or ""),
            "label": label,
        }

    @staticmethod
    def _source_graph_label(item: dict[str, Any]) -> str:
        origin_kind = str(item.get("origin_kind") or "")
        origin = str(item.get("origin") or "")
        if origin_kind == "url":
            parsed = urlsplit(origin)
            display = f"{parsed.hostname or 'web source'}{parsed.path or '/'}"
            return f"Source: {EvidenceReadService._truncate_label(display)}"
        if origin_kind == "vault":
            return f"Vault source: {str(item.get('id') or '')[:8]}"
        if origin_kind == "virtual":
            return f"Managed source: {EvidenceReadService._truncate_label(origin)}"
        source_type = str(item.get("source_type") or "source").replace("_", " ")
        return f"{source_type.title()}: {str(item.get('id') or '')[:8]}"

    @staticmethod
    def _asset_graph_label(mime_type: str) -> str:
        if mime_type in _ASSET_LABELS:
            return _ASSET_LABELS[mime_type]
        if mime_type.startswith("image/"):
            return "Image"
        if mime_type.startswith("audio/"):
            return "Audio"
        if mime_type.startswith("video/"):
            return "Video"
        return "File"

    @staticmethod
    def _extraction_graph_label(extractor: str) -> str:
        return _EXTRACTION_LABELS.get(extractor, extractor.replace("-", " ").title() or "Extraction")

    @staticmethod
    def _target_graph_label(target_type: str, target_id: str, anchor: str = "") -> str:
        if target_type == "url" and anchor:
            parsed = urlsplit(anchor)
            display = f"{parsed.hostname or 'web source'}{parsed.path or '/'}"
            return f"URL: {EvidenceReadService._truncate_label(display)}"
        if target_type == "doi" and anchor:
            return f"DOI: {EvidenceReadService._truncate_label(anchor)}"
        if target_type == "citekey" and anchor:
            return f"Citekey: {EvidenceReadService._truncate_label(anchor)}"
        kind = target_type.replace("_", " ").capitalize() or "Target"
        return f"{kind}: {target_id[:7]}"

    @staticmethod
    def _truncate_label(value: str, *, limit: int = 52) -> str:
        compact = value.strip()
        return compact if len(compact) <= limit else f"{compact[:limit - 3]}..."
