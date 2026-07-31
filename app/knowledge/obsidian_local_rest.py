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
from urllib.parse import urlsplit, urlunsplit

import httpx


_ALLOWED_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_MAX_RESPONSE_BYTES = 16 * 1024
_PLUGIN_SETTINGS_RELATIVE_PATH = Path(".obsidian/plugins/obsidian-local-rest-api/data.json")


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
            candidate = (root / _PLUGIN_SETTINGS_RELATIVE_PATH).resolve()
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
