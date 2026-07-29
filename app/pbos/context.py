"""Bounded Obsidian context for PBOS planning.

PBOS may use working context and governed knowledge, but never treats raw
captures as personal experience or sends the full Vault to a plan compiler.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class PBOSVaultContextBuilder:
    """Return a compact, reviewable context pack from the project memory layer."""

    ALLOWED_ROOTS = (
        "03_Projects/active",
        "02_Assets/curated",
        "methods",
        "wiki",
        "04_Outputs",
        "outputs",
        "distillations",
    )
    EXCLUDED_PARTS = {"revisions", "pbos", ".obsidian", ".git"}
    MAX_DOCUMENTS = 8
    MAX_FILE_BYTES = 24 * 1024
    MAX_EXCERPT_CHARS = 1_200
    TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv"}
    NEXT_CONTEXT_FILENAMES = frozenset({
        "03-下周上下文包.md",
        "03-next-context.md",
        "next_context.md",
    })

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()

    def build(self) -> dict[str, Any]:
        if not self.project_root.is_dir():
            return {"availability": "vault_unavailable", "documents": [], "refs": []}
        documents: list[dict[str, Any]] = []
        latest_context = self._latest_weekly_context()
        if latest_context is not None:
            document = self._document(latest_context)
            if document is not None:
                documents.append(document)
        for root_name in self.ALLOWED_ROOTS:
            root = (self.project_root / root_name).resolve()
            if not root.is_dir() or not self._within_project(root):
                continue
            for candidate in sorted(root.rglob("*")):
                if len(documents) >= self.MAX_DOCUMENTS:
                    break
                if latest_context is not None and candidate == latest_context:
                    continue
                # A weekly next-context package is explicitly a handoff into
                # the next plan. Older packages are historical artifacts, not
                # competing instructions for the current decision.
                if candidate.name in self.NEXT_CONTEXT_FILENAMES:
                    continue
                if not self._eligible(candidate):
                    continue
                document = self._document(candidate)
                if document is not None:
                    documents.append(document)
            if len(documents) >= self.MAX_DOCUMENTS:
                break
        return {
            "availability": "available" if documents else "no_governed_context",
            "documents": documents,
            "refs": [item["ref"] for item in documents],
        }

    def _latest_weekly_context(self) -> Path | None:
        root = (self.project_root / "distillations").resolve()
        if not root.is_dir() or not self._within_project(root):
            return None
        candidates = [
            candidate
            for candidate in root.rglob("*")
            if candidate.name in self.NEXT_CONTEXT_FILENAMES and self._eligible(candidate)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (
                candidate.parent.name,
                candidate.stat().st_mtime_ns,
                candidate.as_posix(),
            ),
        )

    def _eligible(self, candidate: Path) -> bool:
        if not candidate.is_file() or candidate.is_symlink() or candidate.suffix.lower() not in self.TEXT_SUFFIXES:
            return False
        if candidate.name.lower().endswith(".excalidraw.md"):
            return False
        try:
            relative = candidate.resolve().relative_to(self.project_root)
        except ValueError:
            return False
        return not any(part in self.EXCLUDED_PARTS for part in relative.parts)

    def _document(self, candidate: Path) -> dict[str, Any] | None:
        try:
            payload = candidate.read_bytes()[: self.MAX_FILE_BYTES]
            text = payload.decode("utf-8")
            relative = candidate.resolve().relative_to(self.project_root).as_posix()
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        excerpt = self._excerpt(text)
        if not excerpt:
            return None
        return {
            "ref": f"vault:{relative}",
            "path": relative,
            "title": self._title(text, candidate.stem),
            "excerpt": excerpt,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _within_project(self, path: Path) -> bool:
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    def _excerpt(self, text: str) -> str:
        source_lines = text.splitlines()
        first_content = next((index for index, line in enumerate(source_lines) if line.strip()), None)
        if first_content is not None and source_lines[first_content].strip() == "---":
            closing = next(
                (index for index in range(first_content + 1, len(source_lines)) if source_lines[index].strip() == "---"),
                None,
            )
            if closing is not None:
                source_lines = source_lines[closing + 1:]
        lines = [line.strip() for line in source_lines if line.strip() and not line.strip().startswith("---")]
        return "\n".join(lines)[: self.MAX_EXCERPT_CHARS]

    @staticmethod
    def _title(text: str, fallback: str) -> str:
        for line in text.splitlines():
            value = line.strip()
            if value.startswith("# "):
                return value[2:].strip()[:200] or fallback
        return fallback[:200]
