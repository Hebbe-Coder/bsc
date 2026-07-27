"""Bounded HTTPS capture for primary evidence discovered by a radar source."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit

import httpx


class PrimaryWebCaptureError(ValueError):
    """Raised when a public web page cannot become immutable primary evidence."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class PrimaryWebCaptureResult:
    requested_url: str
    final_url: str
    title: str
    content: str
    content_type: str
    response_sha256: str
    extraction_revision: str = "primary-web-visible-text-v1"


class _VisibleTextParser(HTMLParser):
    _SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skipped_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in self._SKIPPED_TAGS:
            self._skipped_depth += 1
        if normalized == "title" and not self._skipped_depth:
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "title":
            self._in_title = False
        if normalized in self._SKIPPED_TAGS and self._skipped_depth:
            self._skipped_depth -= 1

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if not normalized or self._skipped_depth:
            return
        if self._in_title:
            self._title_parts.append(normalized)
        self._parts.append(normalized)

    @property
    def title(self) -> str:
        return " ".join(self._title_parts).strip()

    @property
    def text(self) -> str:
        return "\n".join(self._parts).strip()


class PrimaryWebCapture:
    """Fetch a public HTTPS page without credentials, redirects, or private-network access."""

    _ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain", "text/markdown", "application/json"})
    _CHARSET = re.compile(r"charset=([A-Za-z0-9._-]+)", re.IGNORECASE)

    def __init__(
        self,
        *,
        timeout_seconds: float = 20,
        max_response_bytes: int = 1_000_000,
        max_redirects: int = 4,
        max_attempts: int = 3,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.max_attempts = max(1, max_attempts)
        self.resolver = resolver
        self.client_factory = client_factory or self._default_client

    def capture(self, url: str) -> PrimaryWebCaptureResult:
        last_error: PrimaryWebCaptureError | None = None
        for _ in range(self.max_attempts):
            try:
                return self._capture_once(url)
            except PrimaryWebCaptureError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise PrimaryWebCaptureError("primary web capture failed before an attempt was made")

    def _capture_once(self, url: str) -> PrimaryWebCaptureResult:
        requested_url = self._validate_url(url)
        current_url = requested_url
        visited: set[str] = set()
        with self.client_factory() as client:
            for _ in range(self.max_redirects + 1):
                current_url = self._validate_url(current_url)
                if current_url in visited:
                    raise PrimaryWebCaptureError("primary web capture encountered a redirect loop")
                visited.add(current_url)
                try:
                    with client.stream(
                        "GET",
                        current_url,
                        headers={
                            "Accept": "text/html, text/plain, text/markdown, application/json",
                            "User-Agent": "bsc-knowledge-primary-capture/1",
                        },
                    ) as response:
                        status = int(response.status_code)
                        if 300 <= status < 400:
                            location = response.headers.get("location", "").strip()
                            if not location:
                                raise PrimaryWebCaptureError("primary web capture received a redirect without a location")
                            current_url = urljoin(current_url, location)
                            continue
                        if status >= 400:
                            raise PrimaryWebCaptureError(f"primary web capture failed with HTTP {status}")
                        if status < 200 or status >= 300:
                            raise PrimaryWebCaptureError("primary web capture returned an unsupported HTTP response")
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                        if content_type not in self._ALLOWED_CONTENT_TYPES:
                            raise PrimaryWebCaptureError("primary web capture returned an unsupported content type")
                        advertised_size = response.headers.get("content-length", "")
                        if advertised_size.isdigit() and int(advertised_size) > self.max_response_bytes:
                            raise PrimaryWebCaptureError("primary web capture response exceeded the configured limit")
                        payload = self._read_bounded(response)
                        final_url = self._validate_url(str(response.url))
                except PrimaryWebCaptureError:
                    raise
                except httpx.HTTPError as exc:
                    raise PrimaryWebCaptureError("primary web capture request failed", retryable=True) from exc

                decoded = self._decode(payload, response.headers.get("content-type", ""))
                title, text = self._extract(decoded, content_type)
                if len(text) < 80:
                    raise PrimaryWebCaptureError("primary web capture did not extract enough readable evidence")
                display_title = title or self._fallback_title(final_url)
                content = f"# {display_title}\n\nSource URL: {final_url}\n\n{text}"
                return PrimaryWebCaptureResult(
                    requested_url=requested_url,
                    final_url=final_url,
                    title=display_title,
                    content=content,
                    content_type=content_type,
                    response_sha256=hashlib.sha256(payload).hexdigest(),
                )
        raise PrimaryWebCaptureError("primary web capture exceeded the redirect limit")

    def _default_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    def _validate_url(self, value: str) -> str:
        candidate = str(value or "").strip()
        if not candidate or len(candidate) > 2_048 or any(character in candidate for character in "\r\n\x00"):
            raise PrimaryWebCaptureError("primary web capture URL is invalid")
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise PrimaryWebCaptureError("primary web capture requires an HTTPS URL without embedded credentials")
        try:
            port = parsed.port
        except ValueError as exc:
            raise PrimaryWebCaptureError("primary web capture URL has an invalid port") from exc
        if port not in {None, 443}:
            raise PrimaryWebCaptureError("primary web capture only permits the HTTPS default port")
        try:
            addresses = {record[4][0] for record in self.resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise PrimaryWebCaptureError("primary web capture host could not be resolved") from exc
        if not addresses:
            raise PrimaryWebCaptureError("primary web capture host could not be resolved")
        try:
            unsafe = any(not ipaddress.ip_address(address).is_global for address in addresses)
        except ValueError as exc:
            raise PrimaryWebCaptureError("primary web capture host resolved to an invalid address") from exc
        if unsafe:
            raise PrimaryWebCaptureError("primary web capture does not permit private or reserved network targets")
        return candidate

    def _read_bounded(self, response: httpx.Response) -> bytes:
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > self.max_response_bytes:
                raise PrimaryWebCaptureError("primary web capture response exceeded the configured limit")
        return bytes(payload)

    def _decode(self, payload: bytes, content_type: str) -> str:
        match = self._CHARSET.search(content_type)
        encoding = match.group(1) if match else "utf-8"
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            raise PrimaryWebCaptureError("primary web capture response could not be decoded") from exc

    @staticmethod
    def _extract(content: str, content_type: str) -> tuple[str, str]:
        if content_type != "text/html":
            return "", "\n".join(line.strip() for line in content.splitlines() if line.strip())
        parser = _VisibleTextParser()
        try:
            parser.feed(content)
            parser.close()
        except Exception as exc:
            raise PrimaryWebCaptureError("primary web capture HTML could not be parsed") from exc
        return parser.title, parser.text

    @staticmethod
    def _fallback_title(url: str) -> str:
        parsed = urlsplit(url)
        return (parsed.hostname or "Primary web source").strip()
