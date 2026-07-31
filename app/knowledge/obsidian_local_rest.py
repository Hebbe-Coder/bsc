"""Bounded health probe for the optional Obsidian Local REST API plugin.

The filesystem Vault remains BSC's compatibility path. This adapter only
verifies that a separately configured, local Obsidian REST service is alive
and authenticated. It never reads note bodies, lists Vault files, writes data,
or exposes the configured endpoint or token in a response.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


_ALLOWED_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_MAX_RESPONSE_BYTES = 16 * 1024


@dataclass(frozen=True)
class ObsidianLocalRestConfiguration:
    """Runtime-only configuration. The API key is intentionally never serialized."""

    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 3.0
    allow_insecure_tls: bool = False

    @classmethod
    def from_settings(cls, settings: Any) -> "ObsidianLocalRestConfiguration":
        return cls(
            enabled=bool(getattr(settings, "OBSIDIAN_LOCAL_REST_ENABLED", False)),
            base_url=str(getattr(settings, "OBSIDIAN_LOCAL_REST_URL", "") or ""),
            api_key=str(getattr(settings, "OBSIDIAN_LOCAL_REST_API_KEY", "") or ""),
            timeout_seconds=float(getattr(settings, "OBSIDIAN_LOCAL_REST_TIMEOUT_SECONDS", 3.0) or 3.0),
            allow_insecure_tls=bool(getattr(settings, "OBSIDIAN_LOCAL_REST_ALLOW_INSECURE_TLS", False)),
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

    @staticmethod
    def _result(
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
        }
