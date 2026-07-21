"""Safe HTTP reader for Horizon staged sidecar exports."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class HorizonClientError(ValueError):
    """Raised when a Horizon sidecar response cannot be safely imported."""


@dataclass(frozen=True)
class HorizonStageResponse:
    run_id: str
    stage: str
    items: list[dict[str, Any]]


class HorizonClient:
    """Read a bounded staged export without giving Horizon database authority to BSC."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        stage_url_template: str = "/api/runs/{run_id}/stages/{stage}",
        timeout_seconds: int = 20,
        max_response_bytes: int = 2_000_000,
        allow_private_network: bool = False,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = self._validate_base_url(base_url, allow_private_network)
        self.api_key = api_key
        self.stage_url_template = stage_url_template
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.opener = opener

    def fetch_stage(self, *, run_id: str, stage: str) -> HorizonStageResponse:
        if stage not in {"filtered", "enriched"}:
            raise HorizonClientError("Horizon stage must be filtered or enriched")
        if not run_id.strip():
            raise HorizonClientError("Horizon run_id is required")
        suffix = self.stage_url_template.format(run_id=run_id, stage=stage)
        if not suffix.startswith("/") or ".." in suffix.split("/"):
            raise HorizonClientError("Horizon stage URL template escaped the API root")
        request = Request(urljoin(self.base_url + "/", suffix.lstrip("/")), headers=self._headers())
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                payload = response.read(self.max_response_bytes + 1)
        except Exception as exc:
            raise HorizonClientError("Horizon sidecar request failed") from exc
        if len(payload) > self.max_response_bytes:
            raise HorizonClientError("Horizon sidecar response exceeded the configured limit")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HorizonClientError("Horizon sidecar returned invalid JSON") from exc
        items = decoded.get("items") if isinstance(decoded, dict) else None
        if items is None and isinstance(decoded, dict) and isinstance(decoded.get("data"), dict):
            items = decoded["data"].get("items")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise HorizonClientError("Horizon stage response must contain an items array")
        return HorizonStageResponse(run_id=run_id, stage=stage, items=items)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "bsc-knowledge-horizon-adapter/1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _validate_base_url(value: str, allow_private_network: bool) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise HorizonClientError("HORIZON_API_BASE_URL must be an HTTP(S) URL without embedded credentials")
        if not allow_private_network:
            try:
                addresses = {record[4][0] for record in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
            except OSError as exc:
                raise HorizonClientError("Horizon host could not be resolved") from exc
            if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback for address in addresses):
                raise HorizonClientError("Horizon sidecar must not target a private or loopback address")
        return value.rstrip("/")
