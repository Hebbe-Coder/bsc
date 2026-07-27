"""Project-scoped, non-destructive Obsidian projections for BSC evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Iterable
from uuid import uuid4

from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository


MANAGED_EVIDENCE_ROOT = ("01_Sources", "bsc-evidence")
MANAGED_EVIDENCE_PREFIX = "/".join(MANAGED_EVIDENCE_ROOT)
PROJECTION_REVISION = "bsc-source-mirror-v1"
_SOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def is_managed_evidence_path(project_relative: tuple[str, ...]) -> bool:
    """Return whether a project-relative path is a BSC-generated evidence page."""
    return project_relative[: len(MANAGED_EVIDENCE_ROOT)] == MANAGED_EVIDENCE_ROOT


class ObsidianSourceProjection:
    """Expose BSC-owned immutable evidence in Obsidian without importing it again.

    The database remains authoritative for the source record. The Markdown page
    is a human-readable projection with a recorded content fingerprint. A page
    changed outside this service is treated as a user edit and is never replaced.
    """

    def __init__(self, repository: WikiRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")

    def sync(self, *, project_id: str, source_ids: Iterable[str] | None = None) -> dict[str, int]:
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        vault = FilesystemWikiVault(self.vault_root, project_id, str(mapping["vault_path"]))
        if not vault.project_root.is_dir():
            raise ValueError("project Vault directory does not exist")

        selected = {str(source_id) for source_id in source_ids or () if str(source_id)}
        report = {"eligible": 0, "created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "conflicts": 0}
        for source in self.repository.list_sources(project_id):
            if selected and str(source["id"]) not in selected:
                continue
            if not self._should_project(source):
                report["skipped"] += 1
                continue
            report["eligible"] += 1
            outcome = self._project(vault, source)
            report[outcome] += 1
        return report

    @staticmethod
    def _should_project(source: dict[str, Any]) -> bool:
        source_id = str(source.get("id") or "")
        metadata = source.get("metadata") or {}
        if not _SOURCE_ID.fullmatch(source_id):
            return False
        # Obsidian imports already have a user-authored source file. Mirroring
        # them would duplicate the source and hide which file the user owns.
        if metadata.get("sync") == "obsidian":
            return False
        return True

    def _project(self, vault: FilesystemWikiVault, source: dict[str, Any]) -> str:
        relative = f"{MANAGED_EVIDENCE_PREFIX}/{source['id']}.md"
        target = self._safe_target(vault.project_root, relative)
        content = self._render(source)
        projected_hash = self._hash_text(content)
        metadata = dict(source.get("metadata") or {})
        previous = metadata.get("obsidian_source_mirror")
        previous_path = str(previous.get("path") or "") if isinstance(previous, dict) else ""
        previous_hash = str(previous.get("projected_hash") or "") if isinstance(previous, dict) else ""

        if target.exists():
            if not target.is_file() or target.is_symlink():
                return "conflicts"
            actual_hash = self._file_hash(target)
            if actual_hash == projected_hash and previous_path == relative and previous_hash == actual_hash:
                return "unchanged"
            if previous_path != relative or previous_hash != actual_hash:
                return "conflicts"
            self._write_atomically(target, content)
            outcome = "updated"
        else:
            self._write_atomically(target, content)
            outcome = "created"

        now = datetime.now(timezone.utc).isoformat()
        self.repository.update_source_metadata(
            source["project_id"],
            source["id"],
            {
                **metadata,
                "obsidian_source_mirror": {
                    "revision": PROJECTION_REVISION,
                    "path": relative,
                    "projected_hash": projected_hash,
                    "source_content_hash": str(source.get("content_hash") or ""),
                    "projected_at": now,
                },
            },
        )
        return outcome

    @staticmethod
    def _safe_target(project_root: Path, relative: str) -> Path:
        root = project_root.resolve()
        target = (root / Path(relative)).resolve()
        if root not in target.parents:
            raise ValueError("managed evidence projection escaped project Vault")
        return target

    @staticmethod
    def _render(source: dict[str, Any]) -> str:
        metadata = source.get("metadata") or {}
        title = str(metadata.get("title") or source.get("origin") or source.get("source_type") or source.get("id"))
        fence = ObsidianSourceProjection._fence(str(source.get("raw_content") or ""))
        fields = {
            "bsc_managed": True,
            "projection_revision": PROJECTION_REVISION,
            "source_id": str(source["id"]),
            "source_type": str(source.get("source_type") or ""),
            "origin": str(source.get("origin") or ""),
            "content_hash": str(source.get("content_hash") or ""),
            "trust_level": str(source.get("trust_level") or ""),
            "status": str(source.get("status") or ""),
            "captured_at": str(source.get("captured_at") or ""),
        }
        frontmatter = "\n".join(f"{key}: {ObsidianSourceProjection._yaml_value(value)}" for key, value in fields.items())
        return (
            f"---\n{frontmatter}\n---\n\n"
            f"# BSC Evidence: {title}\n\n"
            "This is a BSC-managed, read-only projection of immutable evidence. "
            "Review the source record in BSC for lifecycle and audit details.\n\n"
            "## Immutable Evidence Body\n\n"
            f"{fence}\n{source['raw_content']}\n{fence}\n"
        )

    @staticmethod
    def _yaml_value(value: object) -> str:
        if value is True:
            return "true"
        if value is False:
            return "false"
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    @staticmethod
    def _fence(content: str) -> str:
        longest = max((len(match.group(0)) for match in re.finditer(r"~+", content)), default=2)
        return "~" * max(3, longest + 1)

    @staticmethod
    def _hash_text(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_atomically(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
