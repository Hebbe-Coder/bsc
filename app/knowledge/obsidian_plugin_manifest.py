"""Safe file-based integration contract for Obsidian plugin exports."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from uuid import uuid4


MANIFEST_FILENAME = "bsc-plugins.json"
_MAX_MANIFEST_BYTES = 64 * 1024
_SOURCE_ADAPTER = "filesystem_drop"
_OUTPUT_ADAPTER = "filesystem_output"
_SUPPORTED_ADAPTERS = frozenset({_SOURCE_ADAPTER, _OUTPUT_ADAPTER})
_SOURCE_EXPORT_ROOTS = frozenset({"raw", "inbox", "00_Inbox", "01_Sources"})
_OUTPUT_EXPORT_ROOTS = frozenset({"outputs", "04_Outputs"})


@dataclass(frozen=True)
class ObsidianPlugin:
    plugin_id: str
    name: str
    adapter: str
    input_paths: tuple[str, ...]


class ObsidianPluginManifest:
    """Read an explicit manifest; never inspect or execute `.obsidian` plugins."""

    def __init__(self, plugins: list[ObsidianPlugin], *, configured: bool, errors: list[str]) -> None:
        self.plugins = plugins
        self.configured = configured
        self.errors = errors

    @classmethod
    def load(cls, project_root: Path | None) -> "ObsidianPluginManifest":
        if project_root is None:
            return cls([], configured=False, errors=["project_vault_unconfigured"])
        path = project_root / MANIFEST_FILENAME
        if not path.is_file() or path.is_symlink():
            return cls([], configured=False, errors=[])
        try:
            payload = path.read_bytes()
            if len(payload) > _MAX_MANIFEST_BYTES:
                raise ValueError("manifest exceeds 65536 bytes")
            data = json.loads(payload.decode("utf-8"))
            raw_plugins = data.get("plugins") if isinstance(data, dict) else None
            if not isinstance(raw_plugins, list):
                raise ValueError("plugins must be a list")
            return cls([cls._plugin(item) for item in raw_plugins], configured=True, errors=[])
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return cls([], configured=True, errors=[f"manifest_invalid:{type(exc).__name__}"])

    @classmethod
    def from_payload(cls, payload: Any) -> "ObsidianPluginManifest":
        """Validate an API payload using the same contract as on-disk manifests."""
        if not isinstance(payload, dict):
            raise ValueError("plugin manifest must be an object")
        raw_plugins = payload.get("plugins")
        if not isinstance(raw_plugins, list):
            raise ValueError("plugins must be a list")
        plugins = [cls._plugin(item) for item in raw_plugins]
        if len({plugin.plugin_id for plugin in plugins}) != len(plugins):
            raise ValueError("plugin ids must be unique")
        manifest = cls(plugins, configured=True, errors=[])
        if len(json.dumps(manifest.to_payload(), ensure_ascii=True).encode("utf-8")) > _MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds 65536 bytes")
        return manifest

    def to_payload(self) -> dict[str, Any]:
        return {
            "plugins": [
                {
                    "id": plugin.plugin_id,
                    "name": plugin.name,
                    "adapter": plugin.adapter,
                    "input_paths": list(plugin.input_paths),
                }
                for plugin in self.plugins
            ]
        }

    def write_to(self, project_root: Path) -> None:
        """Atomically persist the explicit bridge without touching `.obsidian`."""
        root = project_root.resolve()
        if root.is_symlink():
            raise ValueError("project Vault directory cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        target = root / MANIFEST_FILENAME
        if target.is_symlink():
            raise ValueError("plugin manifest cannot be a symlink")
        temporary = root / f".{MANIFEST_FILENAME}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(self.to_payload(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _plugin(value: Any) -> ObsidianPlugin:
        if not isinstance(value, dict):
            raise ValueError("plugin declaration must be an object")
        plugin_id = str(value.get("id") or "").strip()
        if not plugin_id or any(not (char.isalnum() or char in {"-", "_", "."}) for char in plugin_id):
            raise ValueError("plugin id is invalid")
        adapter = str(value.get("adapter") or _SOURCE_ADAPTER)
        if value.get("enabled", True) is not True or adapter not in _SUPPORTED_ADAPTERS:
            raise ValueError("plugin is disabled or uses an unsupported adapter")
        paths = value.get("input_paths")
        if not isinstance(paths, list) or not paths:
            raise ValueError("plugin input_paths must be a non-empty list")
        return ObsidianPlugin(
            plugin_id=plugin_id,
            name=str(value.get("name") or plugin_id),
            adapter=adapter,
            input_paths=tuple(ObsidianPluginManifest._input_path(path, adapter=adapter) for path in paths),
        )

    @staticmethod
    def _input_path(value: Any, *, adapter: str) -> str:
        raw = str(value or "").strip().replace("\\", "/").strip("/")
        path = PurePosixPath(raw)
        if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("plugin input path is invalid")
        allowed_roots = _SOURCE_EXPORT_ROOTS if adapter == _SOURCE_ADAPTER else _OUTPUT_EXPORT_ROOTS
        if path.parts[0] not in allowed_roots:
            roots = "raw/, inbox/, 00_Inbox/, or 01_Sources/" if adapter == _SOURCE_ADAPTER else "outputs/ or 04_Outputs/"
            raise ValueError(
                f"plugin exports must stay under {roots}"
            )
        if adapter == _OUTPUT_ADAPTER and len(path.parts) < 2:
            raise ValueError("plugin output exports must declare a dedicated subfolder")
        return path.as_posix()

    @staticmethod
    def is_source_export_path(project_relative: tuple[str, ...]) -> bool:
        """Keep sync inside explicit A-layer evidence folders.

        ``00_Inbox`` and ``01_Sources`` are the documented Obsidian layout
        aliases for the newer ``inbox`` and ``raw`` project layout. BSC does
        not scan Wiki, skills, review, or output folders as new evidence.
        """
        return bool(project_relative) and project_relative[0] in _SOURCE_EXPORT_ROOTS

    @staticmethod
    def is_output_export_path(project_relative: tuple[str, ...]) -> bool:
        """Keep D-layer adoption inside explicit output folders."""
        return bool(project_relative) and project_relative[0] in _OUTPUT_EXPORT_ROOTS

    def plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        value = project_relative.replace("\\", "/").strip("/")
        for plugin in self.plugins:
            if plugin.adapter == _SOURCE_ADAPTER and any(value == root or value.startswith(root + "/") for root in plugin.input_paths):
                return plugin
        return None

    def output_plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        value = project_relative.replace("\\", "/").strip("/")
        for plugin in self.plugins:
            if plugin.adapter == _OUTPUT_ADAPTER and any(value == root or value.startswith(root + "/") for root in plugin.input_paths):
                return plugin
        return None

    def public_status(
        self,
        sources: Iterable[dict[str, Any]] = (),
        outputs: Iterable[dict[str, Any]] = (),
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        """Expose configured path readiness separately from captured output."""
        captured_sources: dict[str, list[dict[str, Any]]] = {
            plugin.plugin_id: [] for plugin in self.plugins
        }
        registered_outputs: dict[str, list[dict[str, Any]]] = {
            plugin.plugin_id: [] for plugin in self.plugins
        }
        for source in sources:
            metadata = source.get("metadata") if isinstance(source, dict) else None
            plugin_id = str(metadata.get("obsidian_plugin") or "") if isinstance(metadata, dict) else ""
            if plugin_id in captured_sources and str(metadata.get("obsidian_adapter") or _SOURCE_ADAPTER) == _SOURCE_ADAPTER:
                captured_sources[plugin_id].append(source)
        for output in outputs:
            metadata = output.get("metadata") if isinstance(output, dict) else None
            plugin_id = str(metadata.get("obsidian_plugin") or "") if isinstance(metadata, dict) else ""
            if plugin_id in registered_outputs and str(metadata.get("obsidian_adapter") or "") == _OUTPUT_ADAPTER:
                registered_outputs[plugin_id].append(output)

        return {
            "configured": self.configured,
            "supported_adapters": sorted(_SUPPORTED_ADAPTERS),
            "plugins": [
                {
                    "id": plugin.plugin_id,
                    "name": plugin.name,
                    "adapter": plugin.adapter,
                    "input_paths": list(plugin.input_paths),
                    "path_status": self._path_status(plugin, project_root),
                    "status": self._status(plugin, captured_sources[plugin.plugin_id], registered_outputs[plugin.plugin_id]),
                    "captured_sources": len(captured_sources[plugin.plugin_id]),
                    "registered_outputs": len(registered_outputs[plugin.plugin_id]),
                    "last_captured_at": max(
                        (str(source.get("captured_at") or "") for source in captured_sources[plugin.plugin_id]),
                        default="",
                    ),
                    "last_registered_at": max(
                        (str(output.get("created_at") or "") for output in registered_outputs[plugin.plugin_id]),
                        default="",
                    ),
                }
                for plugin in self.plugins
            ],
            "errors": list(self.errors),
        }

    @staticmethod
    def _status(plugin: ObsidianPlugin, sources: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> str:
        if plugin.adapter == _OUTPUT_ADAPTER:
            return "registered_output" if outputs else "awaiting_output"
        return "captured" if sources else "awaiting_export"

    @staticmethod
    def _path_status(plugin: ObsidianPlugin, project_root: Path | None) -> str:
        if project_root is None:
            return "unverified"
        try:
            root = project_root.resolve()
            if root.is_symlink() or not root.is_dir():
                return "unavailable"
            for configured_path in plugin.input_paths:
                current = root
                for part in PurePosixPath(configured_path).parts:
                    current = current / part
                    if current.is_symlink():
                        return "missing"
                resolved = current.resolve()
                resolved.relative_to(root)
                if not resolved.is_dir():
                    return "missing"
        except (OSError, ValueError):
            return "unavailable"
        return "ready"
