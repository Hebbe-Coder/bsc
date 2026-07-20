"""Typed MCP compatibility metadata and result normalization.

The profile describes the adapter that actually exists in BSC. Unsupported
transports are kept explicit so clients do not infer capabilities from the
presence of a FastMCP dependency.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class McpContentBlock(BaseModel):
    type: Literal["text", "image", "resource", "error"]
    text: str = ""
    data: str = ""
    mime_type: str = ""
    uri: str = ""
    name: str = ""
    message: str = ""
    error_code: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class McpToolResult(BaseModel):
    content: list[McpContentBlock] = Field(default_factory=list)
    structured_content: Any = None
    is_error: bool = False


class McpCompatibilityProfile(BaseModel):
    adapter: str = "bsc-fastmcp-stdio"
    jsonrpc_version: str = "2.0"
    protocol_methods: list[str] = Field(
        default_factory=lambda: ["initialize", "tools/list", "tools/call"]
    )
    transports_supported: list[str] = Field(default_factory=lambda: ["stdio"])
    transports_unsupported: dict[str, str] = Field(
        default_factory=lambda: {
            "streamable_http": "No HTTP transport adapter is registered",
            "sse": "No SSE transport adapter is registered",
        }
    )
    content_blocks_supported: list[str] = Field(
        default_factory=lambda: ["text", "image", "resource", "error"]
    )
    auth: dict[str, Any] = Field(
        default_factory=lambda: {
            "supported_modes": ["api_key"],
            "oauth": {"supported": False, "reason": "No OAuth client flow is registered"},
        }
    )
    isolation: dict[str, Any] = Field(
        default_factory=lambda: {
            "mode": "subprocess_per_call",
            "resource_limits": ["timeout", "memory", "cpu"],
            "windows_job_object": True,
        }
    )


def build_compatibility_profile(*, api_key_configured: bool = False) -> McpCompatibilityProfile:
    profile = McpCompatibilityProfile()
    profile.auth["api_key_configured"] = api_key_configured
    return profile


def normalize_mcp_result(value: Any) -> McpToolResult:
    """Normalize SDK objects and wire dictionaries without losing rich blocks."""
    if isinstance(value, McpToolResult):
        return value
    if isinstance(value, BaseException):
        return McpToolResult(
            content=[
                McpContentBlock(
                    type="error",
                    message=str(value),
                    error_code=value.__class__.__name__,
                )
            ],
            is_error=True,
        )
    if isinstance(value, str):
        return McpToolResult(content=[McpContentBlock(type="text", text=value)])
    if isinstance(value, (list, tuple)):
        return McpToolResult(content=[normalize_mcp_content(item) for item in value])
    if isinstance(value, dict):
        raw_content = value.get("content")
        content = (
            [normalize_mcp_content(item) for item in raw_content]
            if isinstance(raw_content, list)
            else []
        )
        structured = value.get("structuredContent", value.get("structured_content"))
        if not content and structured is None:
            structured = value
        if not content and structured is not None:
            content = [
                McpContentBlock(
                    type="text",
                    text=json.dumps(structured, ensure_ascii=False, default=str),
                )
            ]
        return McpToolResult(
            content=content,
            structured_content=structured,
            is_error=bool(value.get("isError", value.get("is_error", False))),
        )
    return McpToolResult(
        content=[McpContentBlock(type="text", text=str(value))]
    )


def normalize_mcp_content(value: Any) -> McpContentBlock:
    if isinstance(value, McpContentBlock):
        return value
    if isinstance(value, str):
        return McpContentBlock(type="text", text=value)

    raw_type = _get(value, "type", "text")
    if raw_type == "text":
        return McpContentBlock(type="text", text=str(_get(value, "text", "")))
    if raw_type == "image":
        return McpContentBlock(
            type="image",
            data=str(_get(value, "data", "")),
            mime_type=str(_get(value, "mimeType", _get(value, "mime_type", ""))),
            metadata=_metadata(value),
        )
    if raw_type in {"resource", "resource_link"}:
        resource = _get(value, "resource", value)
        return McpContentBlock(
            type="resource",
            uri=str(_get(resource, "uri", "")),
            name=str(_get(resource, "name", "")),
            mime_type=str(_get(resource, "mimeType", _get(resource, "mime_type", ""))),
            text=str(_get(resource, "text", "")),
            data=str(_get(resource, "blob", _get(resource, "data", ""))),
            metadata=_metadata(value),
        )
    if raw_type == "error":
        return McpContentBlock(
            type="error",
            message=str(_get(value, "message", _get(value, "text", ""))),
            error_code=str(_get(value, "errorCode", _get(value, "error_code", ""))),
            metadata=_metadata(value),
        )
    return McpContentBlock(
        type="error",
        message=f"Unsupported MCP content block type: {raw_type}",
        error_code="unsupported_content_type",
        metadata={"raw_type": str(raw_type)},
    )


def _get(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _metadata(value: Any) -> dict[str, Any]:
    metadata = _get(value, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}
