"""Project-safe Obsidian metadata configuration and managed index projections."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import yaml

from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository


KNOWLEDGE_INDEX_ROOT = "Knowledge Index"
KNOWLEDGE_BASES_FILENAME = "Knowledge Operations.base"
MANAGED_INDEX_REVISION = "bsc-knowledge-index-v1"
_METADATA_MENU_PATH = Path(".obsidian/plugins/metadata-menu/data.json")
_DATE_OPTIONS = {
    "dateShiftInterval": "1 day",
    "dateFormat": "YYYY-MM-DD",
    "defaultInsertAsLink": False,
    "linkPath": "",
}


def _select_options(*values: str) -> dict[str, Any]:
    return {
        "sourceType": "ValuesList",
        "valuesList": {str(index): value for index, value in enumerate(values, start=1)},
    }


def _field(field_id: str, name: str, field_type: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": name,
        "path": "",
        "type": field_type,
        "options": deepcopy(options or {}),
    }


CANONICAL_METADATA_FIELDS: dict[str, dict[str, Any]] = {
    field["name"]: field
    for field in (
        _field("bscmeta01", "bsc_id", "Input"),
        _field("bscmeta02", "project_id", "Input"),
        _field(
            "bscmeta03",
            "asset_kind",
            "Select",
            _select_options("source", "wiki_page", "method", "output", "review", "index", "media", "table"),
        ),
        _field("bscmeta04", "source_url", "Input"),
        _field("bscmeta05", "canonical_url", "Input"),
        _field("bscmeta06", "citation_key", "Input"),
        _field("bscmeta07", "source_date", "Date", _DATE_OPTIONS),
        _field("bscmeta08", "captured_at", "Date", _DATE_OPTIONS),
        _field("bscmeta09", "trust_level", "Select", _select_options("untrusted", "lead", "reviewing", "reviewed", "restricted")),
        _field(
            "bscmeta10",
            "review_status",
            "Select",
            _select_options("draft", "triaged", "admitted", "review_required", "published", "rejected", "superseded"),
        ),
        _field("bscmeta11", "freshness", "Select", _select_options("current", "aging", "stale", "unknown")),
        _field(
            "bscmeta12",
            "extraction_status",
            "Select",
            _select_options("not_requested", "queued", "running", "complete", "partial", "failed", "unsupported", "restricted", "needs_review"),
        ),
        _field("bscmeta13", "related_sources", "MultiFile"),
        _field("bscmeta14", "related_pages", "MultiFile"),
        _field("bscmeta15", "table_refs", "MultiFile"),
        _field("bscmeta16", "image_refs", "MultiFile"),
        _field("bscmeta17", "method_refs", "MultiFile"),
        _field("bscmeta18", "output_refs", "MultiFile"),
        _field("bscmeta19", "feedback_status", "Select", _select_options("none", "pending", "processed", "failed")),
        _field("bscmeta20", "managed_by_bsc", "Boolean"),
    )
}


def merge_metadata_menu_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Merge BSC's field definitions without discarding user Metadata Menu settings."""
    merged = deepcopy(dict(settings))
    existing = merged.get("presetFields", [])
    if not isinstance(existing, list):
        raise ValueError("Metadata Menu presetFields must be a list")

    retained = [field for field in existing if not isinstance(field, dict) or field.get("name") not in CANONICAL_METADATA_FIELDS]
    merged["presetFields"] = [*retained, *(deepcopy(field) for field in CANONICAL_METADATA_FIELDS.values())]
    return merged


def is_managed_index_path(project_relative: tuple[str, ...]) -> bool:
    """Return whether a project-relative file belongs to BSC's index projection."""
    return bool(project_relative) and project_relative[0] == KNOWLEDGE_INDEX_ROOT


class ObsidianMetadataService:
    """Configure metadata fields and write bounded, non-source index notes."""

    def __init__(self, vault_root: Path | str, *, repository: WikiRepository | None = None) -> None:
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")
        self.repository = repository

    def configure_metadata_menu(self, *, backup_root: Path | str | None = None) -> dict[str, Any]:
        """Merge global field definitions after creating a private backup on change."""
        settings_path = self.vault_root / _METADATA_MENU_PATH
        if not settings_path.is_file() or settings_path.is_symlink():
            return {"status": "unavailable", "backup_created": False, "field_count": 0}
        try:
            current = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Metadata Menu settings are unreadable") from exc
        if not isinstance(current, dict):
            raise ValueError("Metadata Menu settings must be an object")

        merged = merge_metadata_menu_settings(current)
        current_payload = self._json_bytes(current)
        merged_payload = self._json_bytes(merged)
        if current_payload == merged_payload:
            return {"status": "unchanged", "backup_created": False, "field_count": len(CANONICAL_METADATA_FIELDS)}

        destination = Path(backup_root).resolve() if backup_root else (Path.home() / ".bsc-private-backups" / "obsidian").resolve()
        destination.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = destination / f"metadata-menu-{timestamp}-{hashlib.sha256(current_payload).hexdigest()[:12]}.json"
        self._write_bytes_atomically(backup, current_payload)
        self._write_bytes_atomically(settings_path, merged_payload)
        return {"status": "configured", "backup_created": True, "field_count": len(CANONICAL_METADATA_FIELDS)}

    def write_managed_indexes(self, *, project_id: str) -> dict[str, int]:
        """Write missing Dataview and Bases projections without replacing user edits."""
        if self.repository is None:
            raise ValueError("metadata index generation requires a Wiki repository")
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(self.vault_root, project_id, str(mapping["vault_path"]))
        project_root = vault.project_root
        if not project_root.is_dir():
            raise ValueError("project Vault directory does not exist")

        report = {"created": 0, "updated": 0, "unchanged": 0, "conflicts": 0}
        documents = {
            **self._index_documents(project_id, str(mapping["vault_path"])),
            **self._base_documents(project_id, str(mapping["vault_path"])),
        }
        for relative, content in documents.items():
            target = self._safe_target(project_root, relative)
            if target.exists():
                if not target.is_file() or target.is_symlink() or target.read_text(encoding="utf-8") != content:
                    report["conflicts"] += 1
                else:
                    report["unchanged"] += 1
                continue
            self._write_text_atomically(target, content)
            report["created"] += 1
        return report

    @staticmethod
    def _index_documents(project_id: str, vault_path: str) -> dict[str, str]:
        base = vault_path.replace("\\", "/").strip("/")
        queries = {
            "00-Home.md": (
                "Knowledge Index",
                "A read-only navigation surface for BSC-managed knowledge metadata.",
                "- [[Knowledge Operations.base|Knowledge Operations]]\n- [[01-Inbox]]\n- [[02-Sources-Requiring-Review]]\n- [[03-Published-Wiki]]\n- [[04-Method-Candidates]]\n- [[05-Registered-Outputs]]\n- [[06-Feedback-Debt]]\n- [[07-Stale-References]]\n- [[08-Extraction-Failures]]\n- [[09-Evidence-Atlas]]\n- [[10-Reference-Network]]",
            ),
            "01-Inbox.md": ("Inbox", "Incoming material awaiting triage.", f"```dataview\nTABLE source_url, captured_at, trust_level, review_status\nFROM \"{base}/00_Inbox\"\nSORT captured_at DESC\n```"),
            "02-Sources-Requiring-Review.md": ("Sources Requiring Review", "Admitted or triaged sources that need a review decision.", f"```dataview\nTABLE source_url, trust_level, freshness, captured_at\nFROM \"{base}/01_Sources\"\nWHERE review_status != \"published\"\nSORT captured_at DESC\n```"),
            "03-Published-Wiki.md": ("Published Wiki", "Reviewed B-layer knowledge pages.", f"```dataview\nTABLE kind, freshness, related_sources\nFROM \"{base}/wiki\"\nWHERE status = \"published\"\nSORT file.mtime DESC\n```"),
            "04-Method-Candidates.md": ("Method Candidates", "Candidate methods awaiting applicability or evaluation evidence.", f"```dataview\nTABLE review_status, method_refs, related_pages\nFROM \"{base}/06_Skills\"\nSORT file.mtime DESC\n```"),
            "05-Registered-Outputs.md": ("Registered Outputs", "D-layer deliverables with their evidence and feedback links.", f"```dataview\nTABLE feedback_status, output_refs, method_refs\nFROM \"{base}/outputs\"\nSORT file.mtime DESC\n```"),
            "06-Feedback-Debt.md": ("Feedback Debt", "Outputs and reviews whose feedback still needs processing.", f"```dataview\nTABLE feedback_status, output_refs, related_pages\nFROM \"{base}\"\nWHERE feedback_status = \"pending\"\nSORT file.mtime ASC\n```"),
            "07-Stale-References.md": ("Stale References", "Knowledge metadata marked stale or with unresolved reference links.", f"```dataview\nTABLE source_url, freshness, related_sources\nFROM \"{base}\"\nWHERE freshness = \"stale\"\nSORT file.mtime ASC\n```"),
            "08-Extraction-Failures.md": ("Extraction Failures", "Source assets that require an extraction retry, review, or capability change.", f"```dataview\nTABLE extraction_status, source_url, image_refs, table_refs\nFROM \"{base}\"\nWHERE extraction_status = \"failed\" OR extraction_status = \"partial\" OR extraction_status = \"needs_review\"\nSORT file.mtime DESC\n```"),
            "09-Evidence-Atlas.md": ("Evidence Atlas", "A read-only local navigation view of provenance, extraction state, and typed media anchors. BSC remains authoritative for records and permissions.", f"```dataview\nTABLE asset_kind, source_url, citation_key, trust_level, extraction_status, table_refs, image_refs\nFROM \"{base}\"\nWHERE asset_kind = \"source\" OR asset_kind = \"media\" OR asset_kind = \"table\"\nSORT captured_at DESC\n```"),
            "10-Reference-Network.md": ("Reference Network", "A navigation projection of explicit relations. It does not infer edges or replace BSC reference resolution.", f"```dataview\nTABLE related_sources, related_pages, table_refs, image_refs, method_refs, output_refs\nFROM \"{base}\"\nWHERE length(related_sources) > 0 OR length(related_pages) > 0 OR length(table_refs) > 0 OR length(image_refs) > 0\nSORT file.mtime DESC\n```"),
        }
        return {
            f"{KNOWLEDGE_INDEX_ROOT}/{filename}": ObsidianMetadataService._render_index(project_id, filename, title, description, body)
            for filename, (title, description, body) in queries.items()
        }

    @staticmethod
    def _base_documents(project_id: str, vault_path: str) -> dict[str, str]:
        """Render one native, read-only Obsidian Base from the canonical vocabulary.

        Bases operate on local frontmatter and file paths, so they are useful
        navigation when BSC is unavailable but are never a lifecycle or access
        control boundary. The generated file deliberately contains no source
        body, credential, API path, or user-specific plugin configuration.
        """
        base = vault_path.replace("\\", "/").strip("/")
        source_roots = [
            f'file.inFolder("{base}/00_Inbox")',
            f'file.inFolder("{base}/01_Sources")',
            f'file.inFolder("{base}/raw")',
            f'file.inFolder("{base}/inbox")',
            f'file.inFolder("{base}/02_Assets")',
        ]
        views = [
            ObsidianMetadataService._base_view(
                "Inbox",
                [f'file.inFolder("{base}/00_Inbox")'],
                ["file.name", "source_url", "captured_at", "trust_level", "review_status"],
            ),
            ObsidianMetadataService._base_view(
                "Review Queue",
                [f'file.inFolder("{base}/01_Sources")'],
                ["file.name", "citation_key", "trust_level", "freshness", "review_status"],
            ),
            ObsidianMetadataService._base_view(
                "Published Wiki",
                [f'file.inFolder("{base}/wiki")', 'status == "published"'],
                ["file.name", "freshness", "related_sources", "related_pages"],
            ),
            ObsidianMetadataService._base_view(
                "Method Candidates",
                [f'file.inFolder("{base}/06_Skills")'],
                ["file.name", "review_status", "method_refs", "related_pages"],
            ),
            ObsidianMetadataService._base_view(
                "Registered Outputs",
                [f'file.inFolder("{base}/04_Outputs")'],
                ["file.name", "feedback_status", "output_refs", "method_refs"],
            ),
            ObsidianMetadataService._base_view(
                "Feedback Debt",
                ['feedback_status == "pending"'],
                ["file.name", "feedback_status", "output_refs", "related_pages"],
            ),
            ObsidianMetadataService._base_view(
                "Stale References",
                ['freshness == "stale"'],
                ["file.name", "source_url", "freshness", "related_sources"],
            ),
            ObsidianMetadataService._base_view(
                "Extraction Failures",
                ['extraction_status == "failed" || extraction_status == "partial" || extraction_status == "needs_review"'],
                ["file.name", "extraction_status", "source_url", "image_refs", "table_refs"],
            ),
            ObsidianMetadataService._base_view(
                "Evidence Atlas",
                [{"or": source_roots}],
                ["file.name", "source_url", "citation_key", "trust_level", "extraction_status"],
            ),
            ObsidianMetadataService._base_view(
                "Reference Network",
                [],
                ["file.name", "related_sources", "related_pages", "table_refs", "image_refs", "method_refs", "output_refs"],
            ),
        ]
        definition = {
            "filters": {
                "and": [
                    f'file.inFolder("{base}")',
                    'file.ext == "md"',
                ]
            },
            "properties": {
                "file.name": {"displayName": "Name"},
                "bsc_id": {"displayName": "BSC ID"},
                "source_url": {"displayName": "Source URL"},
                "citation_key": {"displayName": "Citation"},
                "captured_at": {"displayName": "Captured"},
                "trust_level": {"displayName": "Trust"},
                "review_status": {"displayName": "Review"},
                "freshness": {"displayName": "Freshness"},
                "extraction_status": {"displayName": "Extraction"},
                "feedback_status": {"displayName": "Feedback"},
                "related_sources": {"displayName": "Sources"},
                "related_pages": {"displayName": "Pages"},
                "table_refs": {"displayName": "Tables"},
                "image_refs": {"displayName": "Images"},
                "method_refs": {"displayName": "Methods"},
                "output_refs": {"displayName": "Outputs"},
            },
            "views": views,
        }
        content = yaml.safe_dump(
            definition,
            allow_unicode=False,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )
        return {f"{KNOWLEDGE_INDEX_ROOT}/{KNOWLEDGE_BASES_FILENAME}": content}

    @staticmethod
    def _base_view(name: str, filters: list[Any], order: list[str]) -> dict[str, Any]:
        view: dict[str, Any] = {"type": "table", "name": name}
        if filters:
            view["filters"] = {"and": filters}
        view["order"] = order
        return view

    @staticmethod
    def _render_index(project_id: str, filename: str, title: str, description: str, body: str) -> str:
        index_id = filename.removesuffix(".md").lower()
        return (
            "---\n"
            f'bsc_id: "index:{project_id}:{index_id}"\n'
            f'project_id: "{project_id}"\n'
            "asset_kind: index\n"
            "managed_by_bsc: true\n"
            f'bsc_index_revision: "{MANAGED_INDEX_REVISION}"\n'
            "bsc_capture_excluded: true\n"
            "---\n\n"
            f"# {title}\n\n"
            f"{description}\n\n"
            f"{body}\n"
        )

    @staticmethod
    def _safe_target(project_root: Path, relative: str) -> Path:
        root = project_root.resolve()
        target = (root / relative).resolve()
        if root not in target.parents:
            raise ValueError("managed index path escaped project Vault")
        return target

    @staticmethod
    def _json_bytes(value: dict[str, Any]) -> bytes:
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")

    @staticmethod
    def _write_text_atomically(target: Path, content: str) -> None:
        ObsidianMetadataService._write_bytes_atomically(target, content.encode("utf-8"))

    @staticmethod
    def _write_bytes_atomically(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
