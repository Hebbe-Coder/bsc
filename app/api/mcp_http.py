"""HTTP JSON-RPC and SSE transport for the BSC MCP tool surface."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.mcp import server
from app.mcp.compatibility import build_compatibility_profile, normalize_mcp_result

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
_sse_sessions: dict[str, asyncio.Queue[dict[str, Any]]] = {}

_TOOL_HANDLERS = {
    "bsc_mcp_compatibility_profile": server.bsc_mcp_compatibility_profile,
    "bsc_compile": server.bsc_compile,
    "bsc_generate_sop": server.bsc_generate_sop,
    "knowledge_ask": server.knowledge_ask,
    "analyze_domain": server.analyze_domain,
}

_TOOL_SPECS = {
    "bsc_mcp_compatibility_profile": {
        "description": "Return supported BSC MCP transports, auth and isolation capabilities.",
        "properties": {},
    },
    "bsc_compile": {
        "description": "Compile a business description through the BSC runtime.",
        "properties": {
            "description": {"type": "string"},
            "template_id": {"type": "string"},
        },
        "required": ["description"],
    },
    "bsc_generate_sop": {
        "description": "Generate a complete SOP report from a business description.",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
    },
    "knowledge_ask": {
        "description": "Ask the scoped BSC knowledge base.",
        "properties": {
            "question": {"type": "string"},
            "project_id": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["question"],
    },
    "analyze_domain": {
        "description": "Classify a business text into a domain.",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


@router.post("")
async def mcp_json_rpc(request: Request):
    api_key = _request_api_key(request)
    payload = await request.json()
    response = await _dispatch(payload, api_key=api_key)
    if response is None:
        return JSONResponse(status_code=202, content={})
    return JSONResponse(response)


@router.get("/compatibility")
async def mcp_compatibility(request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    configured = bool(server._MCP_API_KEY or server._get_settings_api_key())
    return build_compatibility_profile(api_key_configured=configured).model_dump()


@router.get("/sse")
async def mcp_sse(request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _sse_sessions[session_id] = queue

    async def events():
        endpoint = f"/api/mcp/messages/{session_id}"
        yield f"event: endpoint\ndata: {endpoint}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
        finally:
            _sse_sessions.pop(session_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{session_id}")
async def mcp_sse_message(session_id: str, request: Request):
    api_key = _request_api_key(request)
    _require_http_auth(api_key)
    queue = _sse_sessions.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="MCP SSE session not found")
    response = await _dispatch(await request.json(), api_key=api_key)
    if response is not None:
        await queue.put(response)
    return JSONResponse(status_code=202, content={})


async def _dispatch(payload: Any, *, api_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return _error(None, -32600, "JSON-RPC request must be an object")
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(method, str):
        return _error(request_id, -32600, "JSON-RPC method is required")
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "initialize":
        return _success(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "bsc-engine", "version": "5.0.0"},
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": _tool_list()})
    if method == "tools/call":
        return await _call_tool(request_id, params, api_key=api_key)
    return _error(request_id, -32601, f"Method not found: {method}")


async def _call_tool(request_id: Any, params: Any, *, api_key: str) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "tools/call params must be an object")
    name = params.get("name")
    if name not in _TOOL_HANDLERS:
        return _error(request_id, -32602, f"Unknown MCP tool: {name}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "tools/call arguments must be an object")
    arguments = dict(arguments)
    argument_error = _validate_tool_arguments(name, arguments)
    if argument_error:
        return _error(request_id, -32602, argument_error)
    arguments["api_key"] = api_key
    try:
        result = await asyncio.to_thread(_TOOL_HANDLERS[name], **arguments)
        return _success(request_id, _wire_result(normalize_mcp_result(result)))
    except PermissionError as exc:
        return _error(request_id, -32001, str(exc))
    except Exception as exc:
        return _error(request_id, -32000, str(exc))


def _tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": {
                "type": "object",
                "properties": spec.get("properties", {}),
                "required": spec.get("required", []),
            },
        }
        for name, spec in _TOOL_SPECS.items()
    ]


def _validate_tool_arguments(name: str, arguments: dict[str, Any]) -> str | None:
    """Apply the advertised MCP tool contract before entering a handler."""
    spec = _TOOL_SPECS[name]
    properties = spec.get("properties", {})
    unexpected = sorted(set(arguments) - set(properties))
    if unexpected:
        return f"Unexpected arguments for {name}: {', '.join(unexpected)}"

    missing = [key for key in spec.get("required", []) if key not in arguments]
    if missing:
        return f"Missing required arguments for {name}: {', '.join(missing)}"

    for key, value in arguments.items():
        schema = properties[key]
        expected_type = schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return f"Argument {key} for {name} must be a string"
        if expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"Argument {key} for {name} must be an integer"
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                return f"Argument {key} for {name} must be at least {minimum}"
            if maximum is not None and value > maximum:
                return f"Argument {key} for {name} must be at most {maximum}"
    return None


def _wire_result(result) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for block in result.content:
        if block.type == "text":
            content.append({"type": "text", "text": block.text})
        elif block.type == "image":
            content.append({
                "type": "image",
                "data": block.data,
                "mimeType": block.mime_type,
            })
        elif block.type == "resource":
            content.append({
                "type": "resource",
                "resource": {
                    "uri": block.uri,
                    "name": block.name,
                    "mimeType": block.mime_type,
                    "text": block.text,
                    "blob": block.data,
                },
            })
        else:
            content.append({
                "type": "text",
                "text": block.message,
                "annotations": {"error_code": block.error_code},
            })
    payload: dict[str, Any] = {"content": content, "isError": result.is_error}
    if result.structured_content is not None:
        payload["structuredContent"] = result.structured_content
    return payload


def _request_api_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("x-api-key", "")


def _require_http_auth(api_key: str) -> None:
    try:
        server._require_auth(api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _success(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
