"""One-way, non-destructive import of user-authored Obsidian Markdown into evidence records."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
import hashlib
from datetime import datetime, timezone

from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


class ObsidianSyncService:
    """Import only user Markdown; never treat generated project output as new evidence."""

    def __init__(self, repository: WikiRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")
        self.capture_service = SourceCaptureService(repository)

    def sync(self, *, project_id: str) -> dict[str, int]:
        report = {"scanned": 0, "created": 0, "duplicates": 0, "rejected": 0, "deleted": 0, "skipped": 0}
        seen_paths: set[str] = set()
        mappings = {
            str(mapping["project_id"]): PurePosixPath(str(mapping["vault_path"]).replace("\\", "/")).parts
            for mapping in self.repository.list_vaults()
            if mapping.get("vault_path")
        }
        project_root = mappings.get(project_id, ())
        managed_roots = {("projects",)} | set(mappings.values())
        for path in self.vault_root.rglob("*"):
            if path.is_symlink():
                report["skipped"] += 1
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(self.vault_root)
            if self._excluded(relative, project_root, managed_roots):
                continue
            seen_paths.add(relative.as_posix())
            extension = path.suffix.lower()
            if extension not in {".md", ".txt", ".json", ".canvas"}:
                result = self.capture_service.capture(
                    CapturedSourceInput(
                        project_id=project_id,
                        source_type="obsidian_unsupported",
                        origin=relative.as_posix(),
                        vault_path=relative.as_posix(),
                        raw_content=f"Unsupported format retained as provenance only: {relative.as_posix()}",
                        content_hash=self._file_hash(path),
                        trust_level="untrusted",
                        metadata={
                            "sync": "obsidian",
                            "modified_at": path.stat().st_mtime_ns,
                            "extension": extension,
                            "byte_size": path.stat().st_size,
                            "extraction_status": "unsupported",
                        },
                    )
                )
                report["rejected" if result.created else "duplicates"] += 1
                self._mark_present(result.source)
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                result = self.capture_service.capture(
                    CapturedSourceInput(
                        project_id=project_id,
                        source_type="obsidian_file",
                        origin=relative.as_posix(),
                        vault_path=relative.as_posix(),
                        raw_content=f"UTF-8 extraction failed; immutable file fingerprint retained: {relative.as_posix()}",
                        content_hash=self._file_hash(path),
                        metadata={
                            "sync": "obsidian",
                            "modified_at": path.stat().st_mtime_ns,
                            "extension": extension,
                            "byte_size": path.stat().st_size,
                            "extraction_status": "encoding_error",
                        },
                    )
                )
                report["rejected" if result.created else "duplicates"] += 1
                self._mark_present(result.source)
                continue
            if not content:
                report["skipped"] += 1
                continue
            report["scanned"] += 1
            result = self.capture_service.capture(
                CapturedSourceInput(
                    project_id=project_id,
                    source_type="obsidian_markdown" if extension == ".md" else "obsidian_file",
                    origin=relative.as_posix(),
                    vault_path=relative.as_posix(),
                    raw_content=content,
                    trust_level="untrusted",
                    metadata={
                        "sync": "obsidian",
                        "modified_at": path.stat().st_mtime_ns,
                        "extension": extension,
                        "extraction_status": "complete",
                    },
                )
            )
            report["created" if result.created else "duplicates"] += 1
            self._mark_present(result.source)
        for source in self.repository.list_sources(project_id):
            metadata = source.get("metadata") or {}
            origin = str(source.get("origin") or "")
            if metadata.get("sync") != "obsidian" or not origin or origin in seen_paths or metadata.get("source_present") is False:
                continue
            self.repository.update_source_metadata(
                project_id,
                source["id"],
                {
                    **metadata,
                    "source_present": False,
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            report["deleted"] += 1
        return report

    def _mark_present(self, source: dict) -> None:
        metadata = source.get("metadata") or {}
        if metadata.get("source_present") is not False:
            return
        restored = {**metadata, "source_present": True}
        restored.pop("deleted_at", None)
        self.repository.update_source_metadata(source["project_id"], source["id"], restored)

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _excluded(
        relative: Path,
        project_root: tuple[str, ...] = (),
        managed_roots: set[tuple[str, ...]] | None = None,
    ) -> bool:
        parts = relative.parts
        if any(part.startswith(".") for part in parts):
            return True
        if parts and parts[0].lower() in {"distillations", "methods", "outputs", "reviews"}:
            return True
        name = relative.name.lower()
        if name.startswith("~") or name.endswith((".tmp", ".temp", ".swp", ".lock")):
            return True
        if project_root and parts[:len(project_root)] == project_root:
            project_relative = parts[len(project_root):]
            return not project_relative or project_relative[0] not in {"raw", "inbox"}
        return any(parts[:len(root)] == root for root in managed_roots or {("projects",)})
