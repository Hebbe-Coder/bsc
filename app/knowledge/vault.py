"""Filesystem-backed Wiki Vault adapter scoped to one managed project directory."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.knowledge.proposal_gate import InMemoryWikiVault, ProposalGateError

_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class FilesystemWikiVault(InMemoryWikiVault):
    """Stage a complete project snapshot and atomically swap it into an Obsidian Vault."""

    def __init__(self, root: Path | str, project_id: str, vault_path: str = "") -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ProposalGateError("Obsidian Vault root does not exist")
        if not _PROJECT_ID.fullmatch(project_id):
            raise ProposalGateError("project_id is not safe for a Vault path")
        self.project_id = project_id
        self.vault_path = vault_path or f"projects/{project_id}"
        self._project_root = self._resolve_project_root(self.vault_path)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def contents(self) -> dict[str, str]:
        target = self.project_root
        if not target.exists():
            return {}
        contents: dict[str, str] = {}
        for path in target.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                contents[path.relative_to(target).as_posix()] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary assets are outside the Markdown proposal snapshot. The
                # commit path copies them byte-for-byte before replacing text.
                continue
        return contents

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
            target = self.project_root
            if target.exists() and any(path.is_symlink() for path in target.rglob("*")):
                raise ProposalGateError("Vault project contains a symlink; refusing an atomic replacement")
            if target.exists():
                shutil.copytree(target, staged_root)
                for existing in staged_root.rglob("*"):
                    if not existing.is_file():
                        continue
                    relative_path = existing.relative_to(staged_root).as_posix()
                    try:
                        existing.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        continue
                    if relative_path not in staged:
                        existing.unlink()
            for relative_path, content in staged.items():
                destination = self._safe_child(staged_root, relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8", newline="\n")
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

    def _resolve_project_root(self, vault_path: str) -> Path:
        raw_path = str(vault_path).replace("\\", "/")
        normalized = raw_path.strip("/")
        relative = PurePosixPath(raw_path)
        if (
            not normalized
            or raw_path.startswith("/")
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or (relative.parts and ":" in relative.parts[0])
        ):
            raise ProposalGateError("project Vault mapping must be a non-empty relative path")
        safe_relative = PurePosixPath(normalized)
        candidate = (self.root.joinpath(*safe_relative.parts)).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise ProposalGateError("project Vault mapping escaped OBSIDIAN_VAULT_ROOT")
        return candidate
