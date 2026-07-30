"""Safe file-based integration contract for Obsidian plugin exports."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from uuid import uuid4


MANIFEST_FILENAME = "bsc-plugins.json"
TRUST_FILENAME = "bsc-plugin-trust.json"
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_OBSERVED_EXPORT_FILES = 512
_SOURCE_ADAPTER = "filesystem_drop"
_OUTPUT_ADAPTER = "filesystem_output"
_CONTEXT_ADAPTER = "filesystem_context"
_CAPTURE_ADAPTERS = frozenset({_SOURCE_ADAPTER, _CONTEXT_ADAPTER})
_SUPPORTED_ADAPTERS = _CAPTURE_ADAPTERS | frozenset({_OUTPUT_ADAPTER})
_TRUST_REVISION = "bsc-plugin-trust-v1"
_SOURCE_EXPORT_ROOTS = frozenset({"raw", "inbox", "00_Inbox", "01_Sources"})
_OUTPUT_EXPORT_ROOTS = frozenset({"outputs", "04_Outputs"})
_SYNCABLE_KNOWLEDGE_ROOTS = _SOURCE_EXPORT_ROOTS | frozenset({"02_Assets", "03_Projects", "06_Skills"})
_WORKSPACE_ROLES = {
    "00_Inbox": "inspiration",
    "01_Sources": "resource",
    "raw": "resource",
    "inbox": "inspiration",
    "02_Assets": "asset",
    "03_Projects": "project_context",
    "06_Skills": "skill_candidate",
}

# These checks read only serialized plugin settings, never plugin source code
# or executable content. They prove that a declared bridge and the user-facing
# plugin destination agree without exposing unrelated plugin configuration.
_RUNTIME_SETTING_PROBES = {
    "obsidian-clipper": (Path(".obsidian/plugins/obsidian-clipper/data.json"), "advancedStorageFolder"),
    "xiaohongshu-importer": (Path(".obsidian/plugins/xiaohongshu-importer/data.json"), "defaultFolder"),
    "obsidian-zotero-desktop-connector": (
        Path(".obsidian/plugins/obsidian-zotero-desktop-connector/data.json"),
        "noteImportFolder",
    ),
}
_INTERACTIVE_DESTINATION_PLUGINS = frozenset({"obsidian-importer", "docxer"})
# Claudian agents work from the Vault and can create files directly. Its
# ``mediaFolder`` setting is for attachments, not a chat-transcript export
# destination, so it must never be used as proof that an output was written.
_AGENT_WORKSPACE_PLUGINS = frozenset({"realclaudian"})


@dataclass(frozen=True)
class ObsidianPlugin:
    plugin_id: str
    name: str
    adapter: str
    input_paths: tuple[str, ...]


@dataclass(frozen=True)
class ObsidianPluginTrust:
    """Explicit permission to read one immutable plugin bridge declaration."""

    plugin_id: str
    config_fingerprint: str
    trusted_at: str
    actor_id: str
    reason: str


class ObsidianPluginManifest:
    """Read an explicit manifest; never execute or inspect plugin code."""

    def __init__(
        self,
        plugins: list[ObsidianPlugin],
        *,
        configured: bool,
        errors: list[str],
        trusts: dict[str, ObsidianPluginTrust] | None = None,
        trust_errors: list[str] | None = None,
    ) -> None:
        self.plugins = plugins
        self.configured = configured
        self.errors = errors
        self.trusts = trusts or {}
        self.trust_errors = trust_errors or []

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
            plugins = [cls._plugin(item) for item in raw_plugins]
            trusts, trust_errors = cls._load_trusts(project_root)
            return cls(plugins, configured=True, errors=[], trusts=trusts, trust_errors=trust_errors)
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
        self._write_json_atomically(self._safe_project_root(project_root), MANIFEST_FILENAME, self.to_payload())

    def set_trust(
        self,
        project_root: Path,
        *,
        plugin_ids: Iterable[str],
        trusted: bool,
        actor_id: str,
        reason: str = "",
    ) -> "ObsidianPluginManifest":
        """Persist separate, configuration-bound read authorization.

        Declaring a bridge does not execute it. A trust entry permits BSC to
        read exactly that adapter and export-root configuration. Changing the
        declaration invalidates the prior approval automatically.
        """
        root = self._safe_project_root(project_root)
        declared = {plugin.plugin_id: plugin for plugin in self.plugins}
        selected = {str(value or "").strip() for value in plugin_ids}
        selected.discard("")
        if not selected:
            raise ValueError("at least one plugin id is required")
        if selected - declared.keys():
            raise ValueError("plugin trust references an undeclared plugin")
        actor = str(actor_id or "").strip()
        if not actor:
            raise ValueError("plugin trust actor is required")

        # ``from_payload`` is intentionally filesystem-free so callers can
        # validate a replacement manifest before saving it. When that caller
        # then authorizes only a new route, retain still-matching approvals
        # from the on-disk trust ledger instead of silently revoking unrelated
        # bridges.
        persisted_trusts, _ = self._load_trusts(root)
        known_trusts = {**persisted_trusts, **self.trusts}
        active = {
            plugin_id: trust
            for plugin_id, trust in known_trusts.items()
            if plugin_id in declared and trust.config_fingerprint == self._fingerprint(declared[plugin_id])
        }
        if trusted:
            now = datetime.now(timezone.utc).isoformat()
            for plugin_id in selected:
                active[plugin_id] = ObsidianPluginTrust(
                    plugin_id=plugin_id,
                    config_fingerprint=self._fingerprint(declared[plugin_id]),
                    trusted_at=now,
                    actor_id=actor[:128],
                    reason=str(reason or "").strip()[:512],
                )
        else:
            for plugin_id in selected:
                active.pop(plugin_id, None)

        payload = {
            "revision": _TRUST_REVISION,
            "plugins": [
                {
                    "id": item.plugin_id,
                    "config_fingerprint": item.config_fingerprint,
                    "trusted_at": item.trusted_at,
                    "actor_id": item.actor_id,
                    "reason": item.reason,
                }
                for item in sorted(active.values(), key=lambda item: item.plugin_id)
            ],
        }
        self._write_json_atomically(root, TRUST_FILENAME, payload)
        return self.load(root)

    @classmethod
    def _load_trusts(cls, project_root: Path) -> tuple[dict[str, ObsidianPluginTrust], list[str]]:
        path = project_root / TRUST_FILENAME
        if not path.exists():
            return {}, []
        if not path.is_file() or path.is_symlink():
            return {}, ["trust_store_invalid:path"]
        try:
            payload = path.read_bytes()
            if len(payload) > _MAX_MANIFEST_BYTES:
                raise ValueError("trust store exceeds 65536 bytes")
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict) or data.get("revision") != _TRUST_REVISION:
                raise ValueError("trust store revision is invalid")
            raw_plugins = data.get("plugins")
            if not isinstance(raw_plugins, list):
                raise ValueError("trust store plugins must be a list")
            trusts = [cls._trust(item) for item in raw_plugins]
            if len({item.plugin_id for item in trusts}) != len(trusts):
                raise ValueError("trust store plugin ids must be unique")
            return {item.plugin_id: item for item in trusts}, []
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return {}, [f"trust_store_invalid:{type(exc).__name__}"]

    @staticmethod
    def _trust(value: Any) -> ObsidianPluginTrust:
        if not isinstance(value, dict):
            raise ValueError("plugin trust declaration must be an object")
        plugin_id = str(value.get("id") or "").strip()
        if not plugin_id or any(not (char.isalnum() or char in {"-", "_", "."}) for char in plugin_id):
            raise ValueError("plugin trust id is invalid")
        fingerprint = str(value.get("config_fingerprint") or "").strip().lower()
        if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
            raise ValueError("plugin trust fingerprint is invalid")
        trusted_at = str(value.get("trusted_at") or "").strip()
        actor_id = str(value.get("actor_id") or "").strip()
        if not trusted_at or not actor_id:
            raise ValueError("plugin trust provenance is incomplete")
        return ObsidianPluginTrust(
            plugin_id=plugin_id,
            config_fingerprint=fingerprint,
            trusted_at=trusted_at[:128],
            actor_id=actor_id[:128],
            reason=str(value.get("reason") or "").strip()[:512],
        )

    @staticmethod
    def _safe_project_root(project_root: Path) -> Path:
        root = project_root.resolve()
        if root.is_symlink():
            raise ValueError("project Vault directory cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _write_json_atomically(root: Path, filename: str, payload: dict[str, Any]) -> None:
        target = root / filename
        if target.is_symlink():
            raise ValueError("plugin manifest or trust store cannot be a symlink")
        temporary = root / f".{filename}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _fingerprint(plugin: ObsidianPlugin) -> str:
        encoded = json.dumps(
            {"id": plugin.plugin_id, "adapter": plugin.adapter, "input_paths": list(plugin.input_paths)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

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
        if adapter == _SOURCE_ADAPTER:
            allowed_roots = _SOURCE_EXPORT_ROOTS
        elif adapter == _CONTEXT_ADAPTER:
            allowed_roots = frozenset({"03_Projects"})
        else:
            allowed_roots = _OUTPUT_EXPORT_ROOTS
        if path.parts[0] not in allowed_roots:
            if adapter == _SOURCE_ADAPTER:
                roots = "raw/, inbox/, 00_Inbox/, or 01_Sources/"
            elif adapter == _CONTEXT_ADAPTER:
                roots = "a dedicated 03_Projects/ path"
            else:
                roots = "outputs/ or 04_Outputs/"
            raise ValueError(
                f"plugin exports must stay under {roots}"
            )
        if adapter == _OUTPUT_ADAPTER and len(path.parts) < 2:
            raise ValueError("plugin output exports must declare a dedicated subfolder")
        if adapter == _CONTEXT_ADAPTER and len(path.parts) < 2:
            raise ValueError("plugin context exports must declare a dedicated project path")
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
    def is_syncable_knowledge_path(project_relative: tuple[str, ...]) -> bool:
        """Allow declared evidence plus human-maintained knowledge work lanes.

        Project context, curated assets, and candidate Skills are user-authored
        context for BSC to evaluate. They are not plugin exports and they do not
        become trusted facts or active methods merely because they exist.
        """
        return bool(project_relative) and project_relative[0] in _SYNCABLE_KNOWLEDGE_ROOTS

    @staticmethod
    def workspace_role_for(project_relative: tuple[str, ...]) -> str:
        """Return the cognitive work-lane for a project-relative Vault file."""
        return _WORKSPACE_ROLES.get(project_relative[0], "") if project_relative else ""

    @staticmethod
    def is_output_export_path(project_relative: tuple[str, ...]) -> bool:
        """Keep D-layer adoption inside explicit output folders."""
        return bool(project_relative) and project_relative[0] in _OUTPUT_EXPORT_ROOTS

    def declared_plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        value = project_relative.replace("\\", "/").strip("/")
        for plugin in self.plugins:
            if plugin.adapter in _CAPTURE_ADAPTERS and any(value == root or value.startswith(root + "/") for root in plugin.input_paths):
                return plugin
        return None

    def plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        plugin = self.declared_plugin_for(project_relative)
        return plugin if plugin and self.is_trusted(plugin) else None

    def declared_output_plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        value = project_relative.replace("\\", "/").strip("/")
        for plugin in self.plugins:
            if plugin.adapter == _OUTPUT_ADAPTER and any(value == root or value.startswith(root + "/") for root in plugin.input_paths):
                return plugin
        return None

    def output_plugin_for(self, project_relative: str) -> ObsidianPlugin | None:
        plugin = self.declared_output_plugin_for(project_relative)
        return plugin if plugin and self.is_trusted(plugin) else None

    def trust_state(self, plugin: ObsidianPlugin) -> str:
        if self.trust_errors:
            return "unavailable"
        trust = self.trusts.get(plugin.plugin_id)
        if not trust:
            return "untrusted"
        return "trusted" if trust.config_fingerprint == self._fingerprint(plugin) else "configuration_changed"

    def is_trusted(self, plugin: ObsidianPlugin) -> bool:
        return self.trust_state(plugin) == "trusted"

    def trusted_plugins(self, adapter: str | None = None) -> tuple[ObsidianPlugin, ...]:
        return tuple(plugin for plugin in self.plugins if (not adapter or plugin.adapter == adapter) and self.is_trusted(plugin))

    def public_status(
        self,
        sources: Iterable[dict[str, Any]] = (),
        outputs: Iterable[dict[str, Any]] = (),
        project_root: Path | None = None,
        vault_root: Path | None = None,
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
            if plugin_id in captured_sources and str(metadata.get("obsidian_adapter") or _SOURCE_ADAPTER) in _CAPTURE_ADAPTERS:
                captured_sources[plugin_id].append(source)
        for output in outputs:
            metadata = output.get("metadata") if isinstance(output, dict) else None
            plugin_id = str(metadata.get("obsidian_plugin") or "") if isinstance(metadata, dict) else ""
            if plugin_id in registered_outputs and str(metadata.get("obsidian_adapter") or "") == _OUTPUT_ADAPTER:
                registered_outputs[plugin_id].append(output)

        plugin_statuses = []
        for plugin in self.plugins:
            observation = self._export_observation(plugin, project_root)
            status = self._status(plugin, captured_sources[plugin.plugin_id], registered_outputs[plugin.plugin_id])
            plugin_statuses.append(
                {
                    "id": plugin.plugin_id,
                    "name": plugin.name,
                    "adapter": plugin.adapter,
                    "input_paths": list(plugin.input_paths),
                    "trust_state": self.trust_state(plugin),
                    "trusted_at": self.trusts.get(plugin.plugin_id).trusted_at if self.trusts.get(plugin.plugin_id) else "",
                    "trust_actor": self.trusts.get(plugin.plugin_id).actor_id if self.trusts.get(plugin.plugin_id) else "",
                    "path_status": self._path_status(plugin, project_root),
                    "runtime_configuration": self._runtime_configuration(plugin, project_root, vault_root),
                    "status": status,
                    "capture_state": self._capture_state(plugin, status, observation),
                    "export_observation": observation,
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
            )

        return {
            "configured": self.configured,
            "supported_adapters": sorted(_SUPPORTED_ADAPTERS),
            "plugins": plugin_statuses,
            "errors": [*self.errors, *self.trust_errors],
        }

    def _status(self, plugin: ObsidianPlugin, sources: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> str:
        trust_state = self.trust_state(plugin)
        if trust_state == "untrusted":
            return "awaiting_trust"
        if trust_state == "configuration_changed":
            return "trust_stale"
        if trust_state == "unavailable":
            return "trust_unavailable"
        if plugin.adapter == _OUTPUT_ADAPTER:
            return "registered_output" if outputs else "awaiting_output"
        return "captured" if sources else "awaiting_export"

    def _capture_state(self, plugin: ObsidianPlugin, status: str, observation: dict[str, Any]) -> str:
        """Distinguish a healthy empty route from an unprocessed file drop.

        The legacy ``status`` remains the authority for compatibility and
        captured provenance. This additional state is observational only: it
        never promotes a file to a source or output before the sync pipeline
        has processed it.
        """
        if status in {"awaiting_trust", "trust_stale", "trust_unavailable"}:
            return status
        if status in {"captured", "registered_output"}:
            return status
        if observation["state"] in {"files_detected", "file_limit_reached"}:
            return "files_detected_pending_registration" if plugin.adapter == _OUTPUT_ADAPTER else "files_detected_pending_capture"
        if observation["state"] == "empty":
            return "ready_for_first_output" if plugin.adapter == _OUTPUT_ADAPTER else "ready_for_first_export"
        return "route_unavailable"

    @staticmethod
    def _export_observation(plugin: ObsidianPlugin, project_root: Path | None) -> dict[str, Any]:
        """Count visible regular files without reading filenames or contents."""
        empty = {"state": "unavailable", "file_count": 0, "latest_modified_at": ""}
        if project_root is None:
            return empty
        try:
            root = project_root.resolve()
            if root.is_symlink() or not root.is_dir():
                return empty
            count = 0
            latest_modified_at = ""
            for configured_path in plugin.input_paths:
                export_root = (root / PurePosixPath(configured_path)).resolve()
                export_root.relative_to(root)
                if export_root.is_symlink() or not export_root.is_dir():
                    return empty
                for candidate in export_root.rglob("*"):
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    relative = candidate.relative_to(export_root)
                    if ObsidianPluginManifest._is_transient_export_file(relative):
                        continue
                    count += 1
                    modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc).isoformat()
                    if modified_at > latest_modified_at:
                        latest_modified_at = modified_at
                    if count >= _MAX_OBSERVED_EXPORT_FILES:
                        return {
                            "state": "file_limit_reached",
                            "file_count": count,
                            "latest_modified_at": latest_modified_at,
                        }
            return {
                "state": "files_detected" if count else "empty",
                "file_count": count,
                "latest_modified_at": latest_modified_at,
            }
        except (OSError, ValueError):
            return empty

    @staticmethod
    def _is_transient_export_file(relative: Path) -> bool:
        if any(part.startswith(".") for part in relative.parts):
            return True
        name = relative.name.lower()
        return name.startswith("~") or name.endswith((".tmp", ".temp", ".swp", ".lock"))

    @staticmethod
    def _runtime_configuration(
        plugin: ObsidianPlugin,
        project_root: Path | None,
        vault_root: Path | None,
    ) -> dict[str, str]:
        """Return a bounded destination-alignment result without reading code."""
        if plugin.plugin_id in _INTERACTIVE_DESTINATION_PLUGINS:
            return {
                "state": "interactive_destination",
                "detail_code": "plugin_selects_destination_per_import",
            }
        if plugin.plugin_id in _AGENT_WORKSPACE_PLUGINS:
            return {
                "state": "agent_workspace",
                "detail_code": "agent_writes_declared_output_path",
            }
        probe = _RUNTIME_SETTING_PROBES.get(plugin.plugin_id)
        if probe is None:
            return {"state": "declared_only", "detail_code": "no_readonly_settings_probe"}
        if project_root is None or vault_root is None:
            return {"state": "unverified", "detail_code": "vault_or_project_root_unavailable"}
        try:
            root = vault_root.resolve()
            project = project_root.resolve()
            project_relative = project.relative_to(root).as_posix()
            settings_relative, key = probe
            settings_path = (root / settings_relative).resolve()
            settings_path.relative_to(root)
            if settings_path.is_symlink() or not settings_path.is_file():
                return {"state": "unavailable", "detail_code": "plugin_settings_not_found"}
            payload = settings_path.read_bytes()
            if len(payload) > _MAX_MANIFEST_BYTES:
                return {"state": "unavailable", "detail_code": "plugin_settings_too_large"}
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                return {"state": "unavailable", "detail_code": "plugin_settings_invalid"}
            configured = str(data.get(key) or "").replace("\\", "/").strip("/")
            expected_paths = {
                "/".join([project_relative, input_path]).strip("/")
                for input_path in plugin.input_paths
            }
            if configured in expected_paths:
                return {"state": "configured", "detail_code": "destination_matches_bridge"}
            return {"state": "mismatch", "detail_code": "plugin_destination_differs_from_bridge"}
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            return {"state": "unavailable", "detail_code": "plugin_settings_unreadable"}

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
