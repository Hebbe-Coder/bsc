"""One-way, non-destructive import of user-authored Obsidian Markdown into evidence records."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath

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
        report = {"scanned": 0, "created": 0, "duplicates": 0, "skipped": 0}
        managed_roots = {("projects",)} | {
            PurePosixPath(str(mapping["vault_path"]).replace("\\", "/")).parts
            for mapping in self.repository.list_vaults()
            if mapping.get("vault_path")
        }
        for path in self.vault_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json", ".canvas"}:
                continue
            relative = path.relative_to(self.vault_root)
            if self._excluded(relative, managed_roots):
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                report["skipped"] += 1
                continue
            if not content:
                report["skipped"] += 1
                continue
            report["scanned"] += 1
            result = self.capture_service.capture(
                CapturedSourceInput(
                    project_id=project_id,
                    source_type="obsidian_markdown" if path.suffix.lower() == ".md" else "obsidian_file",
                    origin=relative.as_posix(),
                    vault_path=relative.as_posix(),
                    raw_content=content,
                    trust_level="untrusted",
                    metadata={
                        "sync": "obsidian",
                        "modified_at": path.stat().st_mtime_ns,
                        "extension": path.suffix.lower(),
                    },
                )
            )
            report["created" if result.created else "duplicates"] += 1
        return report

    @staticmethod
    def _excluded(relative: Path, managed_roots: set[tuple[str, ...]] | None = None) -> bool:
        if relative.parts[0].startswith("."):
            return True
        parts = relative.parts
        return any(parts[:len(root)] == root for root in managed_roots or {("projects",)})
