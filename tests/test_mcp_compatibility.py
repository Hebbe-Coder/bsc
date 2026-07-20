from types import SimpleNamespace

from app.mcp.compatibility import (
    build_compatibility_profile,
    normalize_mcp_result,
)
from app.mcp import server


def test_profile_reports_only_real_transport_support():
    profile = build_compatibility_profile(api_key_configured=True)

    assert profile.transports_supported == ["stdio", "streamable_http", "sse"]
    assert profile.transports_unsupported == {}
    assert profile.auth["api_key_configured"] is True
    assert profile.auth["oauth"]["supported"] is False
    assert profile.isolation["mode"] == "subprocess_per_call"


def test_normalizer_preserves_text_image_resource_and_error_blocks():
    result = normalize_mcp_result({
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "image", "data": "base64", "mimeType": "image/png"},
            {"type": "resource", "resource": {"uri": "file://report", "text": "body"}},
            {"type": "resource_link", "uri": "https://example.test/report"},
            {"type": "error", "message": "denied", "errorCode": "auth"},
        ],
        "isError": True,
    })

    assert [block.type for block in result.content] == ["text", "image", "resource", "resource", "error"]
    assert result.content[1].mime_type == "image/png"
    assert result.content[2].uri == "file://report"
    assert result.content[3].uri == "https://example.test/report"
    assert result.content[4].error_code == "auth"
    assert result.is_error is True


def test_normalizer_accepts_sdk_style_objects_and_structured_results():
    image = SimpleNamespace(type="image", data="abc", mimeType="image/jpeg")
    image_result = normalize_mcp_result([image])
    structured = normalize_mcp_result({"answer": "ok", "citations": ["c1"]})

    assert image_result.content[0].type == "image"
    assert image_result.content[0].data == "abc"
    assert structured.structured_content["citations"] == ["c1"]
    assert '"answer": "ok"' in structured.content[0].text


def test_fastmcp_profile_tool_exposes_the_typed_profile(monkeypatch):
    monkeypatch.setattr(server, "_require_auth", lambda api_key="": None)
    monkeypatch.setattr(server, "_MCP_API_KEY", "configured")

    payload = server.bsc_mcp_compatibility_profile()

    assert payload["adapter"] == "bsc-mcp-stdio-http-sse"
    assert "streamable_http" in payload["transports_supported"]
    assert payload["auth"]["api_key_configured"] is True
