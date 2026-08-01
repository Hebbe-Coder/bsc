"""Bounded health probe for the optional Obsidian Local REST API plugin.

The filesystem Vault remains BSC's compatibility path. This adapter only
verifies that a separately configured, local Obsidian REST service is alive
and authenticated. It never reads note bodies, lists Vault files, writes data,
or exposes the configured endpoint or token in a response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


_ALLOWED_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_MAX_RESPONSE_BYTES = 16 * 1024
_MAX_COMMAND_RESPONSE_BYTES = 256 * 1024
_PLUGIN_SETTINGS_RELATIVE_PATH = Path(".obsidian/plugins/obsidian-local-rest-api/data.json")


@dataclass(frozen=True)
class ObsidianCopilotCommand:
    """A project command BSC may open through the local Obsidian service."""

    key: str
    command_id: str
    name: str


# These are deliberately fixed project commands, not a proxy for the complete
# Obsidian command palette. Changing this set requires a code and review change.
COPILOT_COMMANDS: dict[str, ObsidianCopilotCommand] = {
    "evidence_plan": ObsidianCopilotCommand(
        key="evidence_plan",
        command_id="copilot:pbos-%E8%AF%81%E6%8D%AE%E5%8C%96%E6%89%A7%E8%A1%8C%E8%AE%A1%E5%88%92",
        name="Copilot: PBOS-证据化执行计划",
    ),
    "three_minute_reflection": ObsidianCopilotCommand(
        key="three_minute_reflection",
        command_id="copilot:pbos-%E4%B8%89%E5%88%86%E9%92%9F%E5%A4%8D%E7%9B%98",
        name="Copilot: PBOS-三分钟复盘",
    ),
    "governed_delivery": ObsidianCopilotCommand(
        key="governed_delivery",
        command_id="copilot:pbos-%E4%B8%80%E9%94%AE%E5%8F%97%E6%B2%BB%E7%90%86%E4%BA%A4%E4%BB%98",
        name="Copilot: PBOS-一键受治理交付",
    ),
    "knowledge_review": ObsidianCopilotCommand(
        key="knowledge_review",
        command_id="copilot:bsc%20%E7%9F%A5%E8%AF%86%E5%AE%A1%E6%9F%A5%E4%B8%8E%E6%B2%89%E6%B7%80",
        name="Copilot: BSC 知识审查与沉淀",
    ),
    "project_delivery": ObsidianCopilotCommand(
        key="project_delivery",
        command_id="copilot:bsc%20project%20delivery",
        name="Copilot: BSC Project Delivery",
    ),
}


@dataclass(frozen=True)
class ObsidianLocalRestConfiguration:
    """Runtime-only configuration. The API key is intentionally never serialized."""

    enabled: bool = False
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 3.0
    allow_insecure_tls: bool = False
    configuration_source: str = "not_configured"
    configuration_error: str = ""

    @classmethod
    def from_settings(cls, settings: Any) -> "ObsidianLocalRestConfiguration":
        enabled = bool(getattr(settings, "OBSIDIAN_LOCAL_REST_ENABLED", False))
        base_url = str(getattr(settings, "OBSIDIAN_LOCAL_REST_URL", "") or "")
        api_key = str(getattr(settings, "OBSIDIAN_LOCAL_REST_API_KEY", "") or "")
        timeout_seconds = float(getattr(settings, "OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS", 3.0) or 3.0)
        allow_insecure_tls = bool(getattr(settings, "OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS", False))
        if not enabled:
            return cls(
                enabled=False,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                allow_insecure_tls=allow_insecure_tls,
            )
        if base_url.strip() or api_key.strip():
            return cls(
                enabled=True,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                allow_insecure_tls=allow_insecure_tls,
                configuration_source="runtime_env",
            )
        return cls._from_local_plugin_settings(settings, timeout_seconds)

    @classmethod
    def _from_local_plugin_settings(cls, settings: Any, timeout_seconds: float) -> "ObsidianLocalRestConfiguration":
        """Read only the configured plugin's local transport settings.

        This fallback is active only after an operator enables Local REST and
        supplies no separate runtime token. It does not scan Vault content or
        import plugin code. The bounded plugin settings file is already
        required by Obsidian to run the explicitly installed local service.
        """
        root_value = str(getattr(settings, "OBSIDIAN_VAULT_ROOT", "") or "").strip()
        if not root_value:
            return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_vault_unavailable")
        try:
            root = Path(root_value).expanduser().resolve()
            configured_path = root / _PLUGIN_SETTINGS_RELATIVE_PATH
            if cls._has_symlink_component(root, configured_path):
                return cls(
                    enabled=True,
                    timeout_seconds=timeout_seconds,
                    configuration_source="plugin_config",
                    configuration_error="plugin_settings_unsafe_path",
                )
            candidate = configured_path.resolve()
            candidate.relative_to(root)
            if not candidate.is_file():
                return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_settings_missing")
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_settings_invalid")
        if not isinstance(payload, dict):
            return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_settings_invalid")
        token = str(payload.get("apiKey") or "").strip()
        try:
            port = int(payload.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if not token or not 1 <= port <= 65535:
            return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_settings_incomplete")
        if payload.get("enableSecureServer") is not True:
            return cls(enabled=True, timeout_seconds=timeout_seconds, configuration_source="plugin_config", configuration_error="plugin_secure_server_disabled")
        return cls(
            enabled=True,
            base_url=f"https://host.docker.internal:{port}",
            api_key=token,
            timeout_seconds=timeout_seconds,
            # Obsidian Local REST uses a local self-signed certificate. The
            # endpoint guard still permits only an explicit local HTTPS host.
            allow_insecure_tls=True,
            configuration_source="plugin_config",
        )

    @staticmethod
    def _has_symlink_component(root: Path, candidate: Path) -> bool:
        """Do not allow a plugin-settings path to resolve into Vault content."""
        relative = candidate.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return True
        return False


class ObsidianLocalRestProbe:
    """Read one bounded service manifest from an explicitly configured plugin."""

    def __init__(self, configuration: ObsidianLocalRestConfiguration, *, transport: httpx.BaseTransport | None = None) -> None:
        self.configuration = configuration
        self.transport = transport

    @classmethod
    def from_settings(cls, settings: Any) -> "ObsidianLocalRestProbe":
        return cls(ObsidianLocalRestConfiguration.from_settings(settings))

    def probe(self) -> dict[str, Any]:
        configuration_error, endpoint, transport = self._endpoint()
        if configuration_error:
            return self._result("unconfigured" if configuration_error == "disabled" else "configuration_invalid", configuration_error)
        assert endpoint is not None
        assert transport is not None
        headers = {
            "Authorization": f"Bearer {self.configuration.api_key}",
            "Accept": "application/json",
            "User-Agent": "BSC-Obsidian-Local-Rest-Probe/1.0",
        }
        try:
            with httpx.Client(
                verify=not self.configuration.allow_insecure_tls,
                timeout=self.configuration.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                with client.stream("GET", endpoint, headers=headers) as response:
                    if response.status_code in {401, 403}:
                        return self._result("authentication_failed", "authorization_rejected", transport=transport)
                    if response.status_code != 200:
                        return self._result("unavailable", "unexpected_status", transport=transport)
                    raw_content = self._bounded_content(response)
        except httpx.TimeoutException:
            return self._result("unavailable", "request_timeout", transport=transport)
        except httpx.TransportError:
            return self._result("unavailable", "transport_unavailable", transport=transport)
        except ValueError:
            return self._result("unavailable", "response_too_large", transport=transport)

        try:
            payload = json.loads(raw_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._result("unavailable", "response_invalid", transport=transport)
        if not isinstance(payload, dict):
            return self._result("unavailable", "response_invalid", transport=transport)
        manifest = payload.get("manifest")
        if not isinstance(manifest, dict) or manifest.get("id") != "obsidian-local-rest-api":
            return self._result("unavailable", "service_identity_invalid", transport=transport)
        if payload.get("authenticated") is not True:
            return self._result("authentication_failed", "authentication_not_confirmed", transport=transport)
        return self._result(
            "connected",
            "authenticated_manifest_verified",
            transport=transport,
            plugin_version=str(manifest.get("version") or "")[:64],
        )

    def _endpoint(self) -> tuple[str, str | None, str | None]:
        if self.configuration.configuration_error:
            return self.configuration.configuration_error, None, None
        if not self.configuration.enabled:
            return "disabled", None, None
        if not self.configuration.api_key.strip():
            return "api_key_missing", None, None
        if not 0.1 <= self.configuration.timeout_seconds <= 10:
            return "timeout_invalid", None, None
        parsed = urlsplit(self.configuration.base_url.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme != "https"
            or not host
            or host not in _ALLOWED_LOCAL_HOSTS
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.strip("/")
        ):
            return "endpoint_not_local_tls", None, None
        transport = "docker_host_tls" if host == "host.docker.internal" else "loopback_tls"
        return "", urlunsplit(("https", parsed.netloc, "/", "", "")), transport

    @staticmethod
    def _bounded_content(response: httpx.Response) -> bytes:
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > _MAX_RESPONSE_BYTES:
                raise ValueError("response exceeds bounded health payload")
        return bytes(content)

    def _result(
        self,
        state: str,
        detail_code: str,
        *,
        transport: str = "not_configured",
        plugin_version: str = "",
    ) -> dict[str, Any]:
        return {
            "state": state,
            "detail_code": detail_code,
            "transport": transport,
            "plugin_id": "obsidian-local-rest-api",
            "plugin_version": plugin_version,
            "configuration_source": self.configuration.configuration_source,
        }


class ObsidianCopilotCommandBridge:
    """Open only verified project Copilot commands through Obsidian Local REST.

    This bridge never accepts command IDs from callers, reads notes, sends a
    prompt, or treats a successful command dispatch as a saved Copilot output.
    Local REST still owns the visible Copilot interaction and any later write.
    """

    def __init__(self, configuration: ObsidianLocalRestConfiguration, *, transport: httpx.BaseTransport | None = None) -> None:
        self.configuration = configuration
        self.transport = transport

    @classmethod
    def from_settings(cls, settings: Any) -> "ObsidianCopilotCommandBridge":
        return cls(ObsidianLocalRestConfiguration.from_settings(settings))

    def available_commands(self) -> dict[str, Any]:
        result, discovered = self._discover()
        if result is not None:
            return result
        assert discovered is not None
        return {
            "state": "available",
            "detail_code": "allowed_commands_discovered",
            "transport": self._transport_name(),
            "commands": [
                {
                    "key": command.key,
                    "name": command.name,
                    "available": (command.command_id, command.name) in discovered,
                }
                for command in COPILOT_COMMANDS.values()
            ],
        }

    def invoke(self, command_key: str) -> dict[str, Any]:
        command = COPILOT_COMMANDS.get(str(command_key or "").strip())
        if command is None:
            return self._command_result("rejected", "command_not_allowed", command_key=str(command_key or "").strip())

        failure, discovered = self._discover()
        if failure is not None:
            return {**failure, "command_key": command.key, "command_name": command.name}
        assert discovered is not None
        if (command.command_id, command.name) not in discovered:
            return self._command_result("command_unavailable", "command_not_registered", command=command)

        configuration_error, endpoint, transport = self._endpoint()
        if configuration_error:
            return self._command_result(
                "unconfigured" if configuration_error == "disabled" else "configuration_invalid",
                configuration_error,
                command=command,
            )
        assert endpoint is not None
        assert transport is not None
        command_endpoint = endpoint.rstrip("/") + "/commands/" + quote(command.command_id, safe=":")
        try:
            with httpx.Client(
                verify=not self.configuration.allow_insecure_tls,
                timeout=self.configuration.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                with client.stream("POST", command_endpoint, headers=self._headers()) as response:
                    if response.status_code in {401, 403}:
                        return self._command_result("authentication_failed", "authorization_rejected", command=command, transport=transport)
                    if response.status_code != 204:
                        return self._command_result("unavailable", "command_dispatch_rejected", command=command, transport=transport)
                    # Consume only a bounded empty/diagnostic response before closing it.
                    ObsidianLocalRestProbe._bounded_content(response)
        except httpx.TimeoutException:
            return self._command_result("unavailable", "request_timeout", command=command, transport=transport)
        except httpx.TransportError:
            return self._command_result("unavailable", "transport_unavailable", command=command, transport=transport)
        except ValueError:
            return self._command_result("unavailable", "response_too_large", command=command, transport=transport)
        return self._command_result("invoked", "command_invoked", command=command, transport=transport)

    def _discover(self) -> tuple[dict[str, Any] | None, set[tuple[str, str]] | None]:
        configuration_error, endpoint, transport = self._endpoint()
        if configuration_error:
            state = "unconfigured" if configuration_error == "disabled" else "configuration_invalid"
            return self._command_result(state, configuration_error), None
        assert endpoint is not None
        assert transport is not None
        try:
            with httpx.Client(
                verify=not self.configuration.allow_insecure_tls,
                timeout=self.configuration.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                with client.stream("GET", endpoint.rstrip("/") + "/commands", headers=self._headers()) as response:
                    if response.status_code in {401, 403}:
                        return self._command_result("authentication_failed", "authorization_rejected", transport=transport), None
                    if response.status_code != 200:
                        return self._command_result("unavailable", "command_catalog_unavailable", transport=transport), None
                    raw_content = self._bounded_command_content(response)
        except httpx.TimeoutException:
            return self._command_result("unavailable", "request_timeout", transport=transport), None
        except httpx.TransportError:
            return self._command_result("unavailable", "transport_unavailable", transport=transport), None
        except ValueError:
            return self._command_result("unavailable", "response_too_large", transport=transport), None

        try:
            payload = json.loads(raw_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._command_result("unavailable", "command_catalog_invalid", transport=transport), None
        raw_commands = payload.get("commands") if isinstance(payload, dict) else payload
        if not isinstance(raw_commands, list):
            return self._command_result("unavailable", "command_catalog_invalid", transport=transport), None
        discovered = {
            (str(item.get("id") or ""), str(item.get("name") or ""))
            for item in raw_commands
            if isinstance(item, dict)
        }
        return None, discovered

    def _endpoint(self) -> tuple[str, str | None, str | None]:
        # Reuse the same local HTTPS and bounded timeout policy as the health probe.
        return ObsidianLocalRestProbe(self.configuration, transport=self.transport)._endpoint()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.configuration.api_key}",
            "Accept": "application/json",
            "User-Agent": "BSC-Obsidian-Copilot-Bridge/1.0",
        }

    @staticmethod
    def _bounded_command_content(response: httpx.Response) -> bytes:
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > _MAX_COMMAND_RESPONSE_BYTES:
                raise ValueError("command catalog exceeds bounded payload")
        return bytes(content)

    def _transport_name(self) -> str:
        _error, _endpoint, transport = self._endpoint()
        return transport or "not_configured"

    @staticmethod
    def _command_result(
        state: str,
        detail_code: str,
        *,
        command: ObsidianCopilotCommand | None = None,
        command_key: str = "",
        transport: str = "not_configured",
    ) -> dict[str, Any]:
        return {
            "state": state,
            "detail_code": detail_code,
            "transport": transport,
            "command_key": command.key if command else command_key,
            "command_name": command.name if command else "",
        }
