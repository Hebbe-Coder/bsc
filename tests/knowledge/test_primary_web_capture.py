import socket

import httpx
import pytest

from app.knowledge.primary_web_capture import PrimaryWebCapture, PrimaryWebCaptureError


def _resolver(_host, _port, type):
    assert type == socket.SOCK_STREAM
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _client(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False)


def test_primary_web_capture_extracts_visible_https_evidence_without_scripts():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://publisher.example/article"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                b"<html><head><title>Primary Evidence</title><script>ignored()</script></head>"
                b"<body><h1>Verified finding</h1><p>The independent source contains enough primary evidence.</p></body></html>"
            ),
            request=request,
        )

    result = PrimaryWebCapture(resolver=_resolver, client_factory=_client(handler)).capture("https://publisher.example/article")

    assert result.title == "Primary Evidence"
    assert "Verified finding" in result.content
    assert "ignored" not in result.content
    assert result.content_type == "text/html"
    assert len(result.response_sha256) == 64


def test_primary_web_capture_validates_redirect_targets_before_following_them():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://private.example/internal"}, request=request)

    def resolver(host, _port, type):
        if host == "private.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        return _resolver(host, _port, type)

    with pytest.raises(PrimaryWebCaptureError, match="private or reserved"):
        PrimaryWebCapture(resolver=resolver, client_factory=_client(handler)).capture("https://publisher.example/article")


def test_primary_web_capture_rejects_oversized_or_non_text_responses():
    def oversized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain", "content-length": "1001"})

    with pytest.raises(PrimaryWebCaptureError, match="exceeded"):
        PrimaryWebCapture(max_response_bytes=1_000, resolver=_resolver, client_factory=_client(oversized)).capture(
            "https://publisher.example/article"
        )

    def binary(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF", request=request)

    with pytest.raises(PrimaryWebCaptureError, match="content type"):
        PrimaryWebCapture(resolver=_resolver, client_factory=_client(binary)).capture("https://publisher.example/article")


def test_primary_web_capture_retries_only_transient_http_failures():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectTimeout("temporary", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="A complete primary source remains available after a transient network failure and retry.",
            request=request,
        )

    result = PrimaryWebCapture(resolver=_resolver, client_factory=_client(handler), max_attempts=2).capture(
        "https://publisher.example/article"
    )

    assert attempts == 2
    assert "transient network failure" in result.content
