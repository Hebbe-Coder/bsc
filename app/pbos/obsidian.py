"""Managed, conflict-aware L3 PBOS projections for an Obsidian project Vault."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from app.artifacts import BaseArtifact


class PBOSProjectionService:
    ROOT = "pbos"

    def __init__(self, project_root: Path | str, project_id: str) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_id = project_id

    def sync(self, artifact: BaseArtifact) -> dict[str, str]:
        if not self.project_root.is_dir():
            return {"state": "vault_unavailable"}
        relative = self._relative(artifact)
        target = self._safe_target(relative)
        content = self._render(artifact)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing != content:
                conflict = self._safe_target(f"{self.ROOT}/conflicts/{artifact.artifact_id}.md")
                self._write(conflict, content)
                return {"state": "conflict", "path": conflict.relative_to(self.project_root).as_posix()}
            if existing == content:
                return {"state": "unchanged", "path": relative}
        self._write(target, content)
        return {"state": "synced", "path": relative}

    def _relative(self, artifact: BaseArtifact) -> str:
        grouping = {
            "personal_profile": "profile",
            "capability": "capabilities",
            "personal_execution_plan": "plans",
            "work_execution_record": "executions",
            "work_outcome": "outcomes",
            "work_feedback": "feedback",
            "experience": "experiences",
            "sop_version": "strategies",
            "sop_promotion": "promotions",
        }.get(artifact.artifact_type.value, "assets")
        return f"{self.ROOT}/{grouping}/{artifact.artifact_id}.md"

    def _render(self, artifact: BaseArtifact) -> str:
        body = artifact.model_dump(mode="json")
        body.pop("metadata", None)
        content = "---\n" + "\n".join((
            f'bsc_id: "{artifact.artifact_id}"', f'project_id: "{self.project_id}"',
            f'asset_kind: "{artifact.artifact_type.value}"', "managed_by_bsc: true",
            f'confidence: {artifact.confidence}', f'status: "{artifact.status.value}"',
            "pbos_layer: " + "L3",
        )) + "\n---\n\n"
        content += f"# {artifact.label or artifact.artifact_type.value}\n\n```json\n{__import__('json').dumps(body, ensure_ascii=False, indent=2)}\n```\n"
        return content + f"\n<!-- pbos-managed-sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()} -->\n"

    @staticmethod
    def _managed_hash(content: str) -> str:
        marker = "<!-- pbos-managed-sha256:"
        start = content.rfind(marker)
        if start < 0:
            return ""
        return content[start + len(marker):].split("-->", 1)[0].strip()

    def _safe_target(self, relative: str) -> Path:
        target = (self.project_root / relative).resolve()
        if self.project_root not in target.parents:
            raise ValueError("PBOS projection path escaped project Vault")
        return target

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
