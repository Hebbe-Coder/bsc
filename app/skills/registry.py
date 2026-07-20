"""Fail-closed discovery for project-local SKILL.md manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from app.core.config import settings
from app.skills.manifest import SkillManifest, builtin_skill_manifests


MAX_MANIFEST_BYTES = 256 * 1024


class SkillRegistry:
    def __init__(
        self,
        *,
        root: str | Path,
        executable_chain_ids: Iterable[str],
    ) -> None:
        self.root = Path(root)
        self.executable_chain_ids = frozenset(executable_chain_ids)
        self.diagnostics: list[str] = []
        self._manifests: dict[str, SkillManifest] | None = None

    def list(self) -> list[SkillManifest]:
        return sorted(self._load().values(), key=lambda manifest: manifest.id)

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._load().get(skill_id)

    def resolve_chain(self, skill_id: str) -> str:
        manifest = self.get(skill_id)
        if manifest is None:
            raise KeyError(f"Skill {skill_id} not found")
        if not manifest.enabled or not manifest.executable or not manifest.chain_id:
            raise PermissionError(f"Skill {skill_id} is not executable")
        return manifest.chain_id

    def _load(self) -> dict[str, SkillManifest]:
        if self._manifests is not None:
            return self._manifests

        manifests = {manifest.id: manifest for manifest in builtin_skill_manifests()}
        for manifest in self._discover_project_manifests():
            if manifest.id in manifests:
                self.diagnostics.append(
                    f"{manifest.source_path}: duplicate skill id {manifest.id}"
                )
                continue
            manifests[manifest.id] = manifest
        self._manifests = manifests
        return manifests

    def _discover_project_manifests(self) -> list[SkillManifest]:
        if not self.root.exists():
            return []
        if not self.root.is_dir() or self.root.is_symlink():
            self.diagnostics.append(f"unsafe skill root: {self.root}")
            return []

        root = self.root.resolve()
        manifests: list[SkillManifest] = []
        for path in sorted(root.rglob("SKILL.md")):
            try:
                manifests.append(
                    load_skill_manifest(
                        path,
                        root=root,
                        executable_chain_ids=self.executable_chain_ids,
                    )
                )
            except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
                self.diagnostics.append(f"{path}: {exc}")
        return manifests


def load_skill_manifest(
    path: str | Path,
    *,
    root: str | Path,
    executable_chain_ids: Iterable[str],
) -> SkillManifest:
    root_path = Path(root).resolve(strict=True)
    source_path = Path(path)
    if not is_safe_manifest_path(source_path, root=root_path):
        raise ValueError("manifest path escapes the configured skill root")
    if source_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds the maximum allowed size")

    metadata, prompt = _parse_front_matter(source_path.read_text(encoding="utf-8"))
    entrypoint = str(metadata.get("entrypoint") or "")
    chain_id = entrypoint.removeprefix("chain:") if entrypoint.startswith("chain:") else ""
    executable = bool(
        metadata.get("enabled", True)
        and chain_id
        and chain_id in set(executable_chain_ids)
    )
    return SkillManifest.model_validate(
        metadata
        | {
            "source": "project",
            "source_path": source_path.resolve().relative_to(root_path).as_posix(),
            "prompt": prompt.strip(),
            "executable": executable,
        }
    )


def is_safe_manifest_path(path: str | Path, *, root: str | Path) -> bool:
    root_path = Path(root).resolve(strict=True)
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
        relative = candidate.absolute().relative_to(root_path)
    except (OSError, ValueError):
        return False
    if resolved != root_path and root_path not in resolved.parents:
        return False

    current = root_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return resolved.name == "SKILL.md" and resolved.is_file()


def _parse_front_matter(content: str) -> tuple[dict, str]:
    if not content.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML front matter")
    marker = "\n---\n"
    boundary = content.find(marker, 4)
    if boundary < 0:
        raise ValueError("SKILL.md front matter is not terminated")
    metadata = yaml.safe_load(content[4:boundary]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md front matter must be a mapping")
    return metadata, content[boundary + len(marker):]


def build_skill_registry(*, root: str | Path | None = None) -> SkillRegistry:
    from app.api.skill_routes import CHAIN_REGISTRY

    configured_root = Path(root or settings.SKILL_ROOT)
    if not configured_root.is_absolute():
        configured_root = Path(__file__).resolve().parents[2] / configured_root
    return SkillRegistry(
        root=configured_root,
        executable_chain_ids=CHAIN_REGISTRY,
    )
