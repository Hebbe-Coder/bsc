"""Classify managed growth-distillation revisions without altering evidence."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.vault import FilesystemWikiVault


_INPUT_HASH = re.compile(r"[a-f0-9]{64}")


def growth_distillation_revision_metadata(
    repo: GrowthRepository,
    records: list[dict[str, Any]],
    *,
    vault_root: str,
) -> dict[str, dict[str, int | bool]]:
    """Return currentness and revision count for every same-period record.

    The managed Vault marker is authoritative when it is available. Database
    ordering is only a fallback for a disconnected Vault, never a claim that a
    file was inspected.
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault((str(record.get("kind") or ""), str(record.get("period") or "")), []).append(record)

    vault = _project_vault(repo, records, vault_root)
    metadata: dict[str, dict[str, int | bool]] = {}
    for group_records in grouped.values():
        readable_records = [
            record
            for record in group_records
            if str(record.get("status") or "") != "superseded_artifact_missing"
        ]
        current = next(
            (record for record in readable_records if vault and _is_current_managed_record(vault, record)),
            readable_records[0] if readable_records else None,
        )
        current_id = str((current or {}).get("id") or "")
        revision_count = len(group_records)
        for record in group_records:
            record_id = str(record.get("id") or "")
            if record_id:
                metadata[record_id] = {"current": record_id == current_id, "revision_count": revision_count}
    return metadata


def _project_vault(
    repo: GrowthRepository,
    records: list[dict[str, Any]],
    vault_root: str,
) -> FilesystemWikiVault | None:
    if not records or not vault_root:
        return None
    try:
        project_id = str(records[0].get("project_id") or "")
        mapping = repo.get_vault(project_id)
        if not mapping:
            return None
        return FilesystemWikiVault(vault_root, project_id, str(mapping["vault_path"]))
    except (KeyError, OSError, ValueError):
        return None


def _is_current_managed_record(vault: FilesystemWikiVault, record: dict[str, Any]) -> bool:
    input_hash = str(record.get("input_hash") or "")
    paths = [str(path) for path in record.get("paths") or [] if str(path)]
    if not _INPUT_HASH.fullmatch(input_hash) or not paths:
        return False
    try:
        current_path = _safe_distillation_path(vault, paths[0])
    except ValueError:
        return False
    kind = str(record.get("kind") or "")
    if kind == "weekly":
        return _weekly_manifest_input_hash(current_path.parent / "manifest.json") == input_hash
    if kind == "daily":
        return _daily_marker_input_hash(current_path) == input_hash
    return False


def _weekly_manifest_input_hash(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = str(payload.get("input_hash") or "") if isinstance(payload, dict) else ""
    return value if _INPUT_HASH.fullmatch(value) else ""


def _daily_marker_input_hash(path: Path) -> str:
    try:
        first_line = path.open("r", encoding="utf-8").readline(2_048)
    except (OSError, UnicodeDecodeError):
        return ""
    match = re.search(r"\binput_hash=([a-f0-9]{64})\b", first_line)
    return match.group(1) if match else ""


def _safe_distillation_path(vault: FilesystemWikiVault, relative: str) -> Path:
    normalized = str(relative or "").replace("\\", "/")
    parts = Path(normalized).parts
    if (
        not normalized
        or normalized.startswith("/")
        or not parts
        or parts[0].casefold() != "distillations"
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
    ):
        raise ValueError("persisted growth output path is invalid")
    root = vault.project_root.resolve()
    candidate = (root / Path(normalized)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("persisted growth output path escaped the project Vault") from exc
    return candidate
