"""Filesystem-backed Wiki Vault adapter scoped to one managed project directory."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGateError

_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class FilesystemWikiVault(InMemoryWikiVault):
    """Stage a complete project snapshot and atomically swap it into an Obsidian Vault."""

    def __init__(self, root: Path | str, project_id: str) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ProposalGateError("Obsidian Vault root does not exist")
        if not _PROJECT_ID.fullmatch(project_id):
            raise ProposalGateError("project_id is not safe for a Vault path")
        self.project_id = project_id

    @property
    def project_root(self) -> Path:
        return self.root / "projects" / self.project_id

    @property
    def contents(self) -> dict[str, str]:
        target = self.project_root
        if not target.exists():
            return {}
        return {
            path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
            for path in target.rglob("*")
            if path.is_file()
        }

    @contents.setter
    def contents(self, _value: dict[str, str]) -> None:
        # ``InMemoryWikiVault`` initializes this attribute; filesystem state is read on demand.
        pass

    def commit(self, staged: dict[str, str]) -> None:
        staging_parent = self.root / ".bsc-staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        transaction_id = uuid4().hex
        staged_root = staging_parent / f"{self.project_id}-{transaction_id}"
        backup_root = staging_parent / f"{self.project_id}-{transaction_id}.backup"
        try:
            for relative_path, content in staged.items():
                destination = self._safe_child(staged_root, relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8", newline="\n")
            target = self.project_root
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                os.replace(target, backup_root)
            try:
                os.replace(staged_root, target)
            except Exception:
                if backup_root.exists():
                    os.replace(backup_root, target)
                raise
            if backup_root.exists():
                shutil.rmtree(backup_root)
        finally:
            if staged_root.exists():
                shutil.rmtree(staged_root)

    @staticmethod
    def _safe_child(root: Path, relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        if root.resolve() not in candidate.parents:
            raise ProposalGateError("Vault operation escaped its staged project directory")
        return candidate
