"""Adopt explicitly declared Obsidian plugin outputs into the governed D-layer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import mimetypes
from pathlib import Path

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.output_registry import OutputRegistry


_MAX_OUTPUT_BYTES = 25 * 1024 * 1024
_TEMPORARY_SUFFIXES = (".tmp", ".temp", ".swp", ".lock")


class ObsidianOutputSyncService:
    """Copy declared external plugin results into immutable, pending D-layer assets.

    The original Obsidian file remains untouched. Registered copies are not
    eligible for future context until the existing output evaluation and
    feedback gates accept them.
    """

    def __init__(self, repository: GrowthRepository, vault_root: Path | str) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ValueError("Obsidian Vault root does not exist")

    def sync(self, *, project_id: str, run_id: str = "") -> dict[str, int]:
        report = {"scanned": 0, "registered": 0, "duplicates": 0, "rejected": 0, "skipped": 0}
        mapping = self.repository.get_vault(project_id)
        if not mapping:
            raise ValueError("project Vault mapping is not configured")
        project_root = (self.vault_root / str(mapping["vault_path"])).resolve()
        if self.vault_root not in project_root.parents and project_root != self.vault_root:
            raise ValueError("project Vault mapping escaped the configured root")
        manifest = ObsidianPluginManifest.load(project_root)
        if not project_root.is_dir():
            return report
        registry = OutputRegistry(self.repository, self.vault_root)
        for plugin in manifest.plugins:
            if plugin.adapter != "filesystem_output":
                continue
            for configured_path in plugin.input_paths:
                export_root = (project_root / configured_path).resolve()
                if project_root not in export_root.parents and export_root != project_root:
                    report["rejected"] += 1
                    continue
                if not export_root.is_dir() or export_root.is_symlink():
                    continue
                for path in export_root.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.is_symlink() or self._skip(path, export_root):
                        report["skipped"] += 1
                        continue
                    try:
                        relative = path.relative_to(project_root).as_posix()
                        if manifest.output_plugin_for(relative) != plugin:
                            report["skipped"] += 1
                            continue
                        if path.stat().st_size > _MAX_OUTPUT_BYTES:
                            report["rejected"] += 1
                            continue
                        report["scanned"] += 1
                        content = path.read_bytes()
                        output = self._asset(project_id, run_id, plugin.plugin_id, plugin.name, relative, content)
                        output_id = registry.deterministic_id(output)
                        existed = self.repository.get_output(project_id, output_id) is not None
                        registry.register_content(output, content, original_path=relative)
                        report["duplicates" if existed else "registered"] += 1
                    except (OSError, ValueError):
                        report["rejected"] += 1
        return report

    @staticmethod
    def _skip(path: Path, export_root: Path) -> bool:
        relative = path.relative_to(export_root)
        if any(part.startswith(".") for part in relative.parts):
            return True
        return path.name.lower().endswith(_TEMPORARY_SUFFIXES)

    @staticmethod
    def _asset(
        project_id: str,
        run_id: str,
        plugin_id: str,
        plugin_name: str,
        original_path: str,
        content: bytes,
    ) -> OutputAsset:
        content_hash = hashlib.sha256(content).hexdigest()
        filename = Path(original_path).name
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        now = datetime.now(timezone.utc)
        return OutputAsset(
            project_id=project_id,
            kind="external_plugin_output",
            title=filename,
            mime_type=mime_type,
            content_hash=content_hash,
            vault_path=f"outputs/{now:%Y}/pending/{filename}",
            run_id=run_id,
            idempotency_key=f"obsidian_plugin_output|{plugin_id}|{original_path}|{content_hash}",
            metadata={
                "origin": "external",
                "original_path": original_path,
                "obsidian_plugin": plugin_id,
                "plugin_name": plugin_name,
                "obsidian_adapter": "filesystem_output",
                "goal": "not_provided_by_external_plugin",
                "audience": "not_provided_by_external_plugin",
                "channel": "obsidian_plugin",
                "generator": f"obsidian_plugin:{plugin_id}",
                "provider": "external_plugin",
                "model": "unknown",
                "prompt_revision": "unknown",
                "provenance_gaps": ["goal", "audience", "provider", "model", "prompt_revision"],
            },
        )
