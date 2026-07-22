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
    "wiki_guide": server.wiki_guide,
    "wiki_search": server.wiki_search,
    "wiki_graph": server.wiki_graph,
    "wiki_read": server.wiki_read,
    "wiki_propose_update": server.wiki_propose_update,
    "wiki_lint": server.wiki_lint,
    "wiki_apply_update": server.wiki_apply_update,
    "wiki_distill": server.wiki_distill,
    "wiki_schedule": server.wiki_schedule,
    "knowledge_growth_profile": server.knowledge_growth_profile,
    "knowledge_growth_assets": server.knowledge_growth_assets,
    "knowledge_growth_source_triage": server.knowledge_growth_source_triage,
    "knowledge_growth_method": server.knowledge_growth_method,
    "knowledge_growth_output": server.knowledge_growth_output,
    "knowledge_growth_feedback": server.knowledge_growth_feedback,
    "knowledge_growth_summary": server.knowledge_growth_summary,
    "knowledge_growth_lineage": server.knowledge_growth_lineage,
    "knowledge_growth_review": server.knowledge_growth_review,
    "knowledge_growth_schedule": server.knowledge_growth_schedule,
    "knowledge_growth_run": server.knowledge_growth_run,
    "knowledge_growth_distillation": server.knowledge_growth_distillation,
    "knowledge_growth_triage": server.knowledge_growth_triage,
    "knowledge_growth_weekly_distill": server.knowledge_growth_weekly_distill,
    "analyze_domain": server.analyze_domain,
}

_WIKI_READ_TOOLS = {"wiki_guide", "wiki_search", "wiki_graph", "wiki_read"}
_WIKI_WRITE_TOOLS = {"wiki_propose_update", "wiki_lint", "wiki_apply_update", "wiki_distill", "wiki_schedule"}
_GROWTH_TOOLS = {
    "knowledge_growth_profile",
    "knowledge_growth_assets",
    "knowledge_growth_source_triage",
    "knowledge_growth_method",
    "knowledge_growth_output",
    "knowledge_growth_feedback",
    "knowledge_growth_summary",
    "knowledge_growth_lineage",
    "knowledge_growth_review",
    "knowledge_growth_schedule",
    "knowledge_growth_run",
    "knowledge_growth_distillation",
    "knowledge_growth_triage",
    "knowledge_growth_weekly_distill",
}
_GROWTH_WRITE_ONLY_TOOLS = {
    "knowledge_growth_review",
    "knowledge_growth_triage",
    "knowledge_growth_weekly_distill",
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
    "wiki_guide": {
        "description": "Explain the governed project Wiki workflow.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_search": {
        "description": "Search project-scoped Wiki evidence metadata.",
        "properties": {"project_id": {"type": "string"}, "query": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_graph": {
        "description": "Read the project-scoped derived Knowledge Graph.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_read": {
        "description": "Read a published project Wiki page and its citation metadata.",
        "properties": {"project_id": {"type": "string"}, "page_id": {"type": "string"}},
        "required": ["project_id", "page_id"],
    },
    "wiki_propose_update": {
        "description": "Create a reviewable Wiki proposal without writing to the Vault.",
        "properties": {
            "project_id": {"type": "string"},
            "operations": {"type": "array"},
            "source_ids": {"type": "array"},
            "rationale": {"type": "string"},
        },
        "required": ["project_id", "operations"],
    },
    "wiki_lint": {
        "description": "Lint a project Wiki proposal before publication.",
        "properties": {"project_id": {"type": "string"}, "proposal_id": {"type": "string"}},
        "required": ["project_id", "proposal_id"],
    },
    "wiki_apply_update": {
        "description": "Publish a proposal through the Wiki gates.",
        "properties": {"project_id": {"type": "string"}, "proposal_id": {"type": "string"}},
        "required": ["project_id", "proposal_id"],
    },
    "wiki_distill": {
        "description": "Queue a governed weekly evidence distillation.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "wiki_schedule": {
        "description": "Configure a bounded persistent Wiki schedule.",
        "properties": {
            "project_id": {"type": "string"},
            "job_type": {"type": "string"},
            "cron": {"type": "string"},
            "timezone": {"type": "string"},
        },
        "required": ["project_id", "job_type", "cron"],
    },
    "knowledge_growth_profile": {
        "description": "Read or update the project knowledge-growth profile with revisioned persistence.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["get", "update"]},
            "profile": {"type": "object"},
            "expected_revision": {"type": "integer", "minimum": 0},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_assets": {
        "description": "List project-scoped A/B/C/D growth assets.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "stage": {"type": "string", "enum": ["", "A", "B", "C", "D", "review"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_source_triage": {
        "description": "Read or run deterministic profile-bound source triage.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["get", "run"]},
            "source_id": {"type": "string", "maxLength": 128},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_method": {
        "description": "List revisions and govern proposal, publication, resolution and audited deprecation of method assets.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "propose", "review", "publish", "resolve", "revisions", "deprecate"]},
            "method_id": {"type": "string", "maxLength": 128},
            "proposal_id": {"type": "string", "maxLength": 128},
            "status": {"type": "string", "maxLength": 32},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {
                "type": "object",
                "description": "Action payload; deprecate requires a non-blank reason of at most 500 characters.",
            },
        },
        "required": ["project_id"],
    },
    "knowledge_growth_output": {
        "description": "List, read, register, evaluate or file immutable project outputs.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "register", "evaluate", "file"]},
            "output_id": {"type": "string", "maxLength": 128},
            "status": {"type": "string", "maxLength": 32},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {
                "type": "object",
                "description": "Action payload; file requires a non-blank reason of at most 500 characters.",
            },
        },
        "required": ["project_id"],
    },
    "knowledge_growth_feedback": {
        "description": "List, create or process project output feedback through governed routing.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "create", "process"]},
            "feedback_id": {"type": "string", "maxLength": 128},
            "output_id": {"type": "string", "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {"type": "object"},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_summary": {
        "description": "Read persisted knowledge-growth counts and quality flow summary.",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    "knowledge_growth_lineage": {
        "description": "Read bounded project-scoped source/page/method/output lineage.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "relation": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_review": {
        "description": "Route feedback or detect method proposals without direct publication.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["feedback", "method_detection"]},
            "target_id": {"type": "string", "maxLength": 128},
            "minimum_uses": {"type": "integer", "minimum": 3, "maximum": 100},
        },
        "required": ["project_id", "action"],
    },
    "knowledge_growth_schedule": {
        "description": "List or configure bounded persistent growth schedules.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "create"]},
            "job_type": {"type": "string", "enum": ["", "growth_daily", "growth_weekly_distillation"]},
            "cron": {"type": "string", "maxLength": 100},
            "timezone": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_run": {
        "description": "List, start, read or replay durable growth runs.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "start", "get", "events"]},
            "run_id": {"type": "string", "maxLength": 128},
            "job_type": {"type": "string", "enum": ["", "growth_daily", "growth_weekly_distillation"]},
            "idempotency_key": {"type": "string", "maxLength": 200},
            "after_sequence": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
            "payload": {"type": "object"},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_distillation": {
        "description": "List, read or start a durable weekly growth distillation.",
        "properties": {
            "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "action": {"type": "string", "enum": ["list", "get", "start"]},
            "distillation_id": {"type": "string", "maxLength": 128},
            "kind": {"type": "string", "enum": ["", "daily", "weekly"]},
            "week": {"type": "string", "maxLength": 32},
            "source_cutoff": {"type": "string", "maxLength": 64},
            "idempotency_key": {"type": "string", "maxLength": 200},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 16},
        },
        "required": ["project_id"],
    },
    "knowledge_growth_triage": {
        "description": "Run profile-bound triage for one validated source.",
        "properties": {"project_id": {"type": "string"}, "source_id": {"type": "string"}},
        "required": ["project_id", "source_id"],
    },
    "knowledge_growth_weekly_distill": {
        "description": "Run an idempotent project weekly distillation.",
        "properties": {"project_id": {"type": "string"}, "week": {"type": "string"}, "source_cutoff": {"type": "string"}},
        "required": ["project_id", "week", "source_cutoff"],
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
    except server.growth_tools.GrowthUnavailableError as exc:
        return _error(
            request_id,
            -32003,
            str(exc),
            data={"code": "dependency_unavailable", "availability": exc.availability},
        )
    except PermissionError as exc:
        return _error(request_id, -32001, str(exc), data={"code": "permission_denied"})
    except KeyError as exc:
        return _error(request_id, -32004, str(exc), data={"code": "resource_not_found"})
    except server.growth_tools.GrowthStateConflictError as exc:
        return _error(
            request_id,
            -32009,
            str(exc),
            data={"code": "knowledge_conflict"},
        )
    except ValueError as exc:
        message = str(exc)
        normalized = message.lower()
        if "conflict" in normalized or "revision" in normalized:
            return _error(request_id, -32009, message, data={"code": "knowledge_conflict"})
        if "not found" in normalized:
            return _error(request_id, -32004, message, data={"code": "resource_not_found"})
        if "unavailable" in normalized or "not configured" in normalized:
            return _error(request_id, -32003, message, data={"code": "dependency_unavailable"})
        return _error(request_id, -32602, message, data={"code": "invalid_arguments"})
    except Exception as exc:
        return _error(request_id, -32000, "MCP tool execution failed", data={"code": "internal_tool_error"})


def _tool_list() -> list[dict[str, Any]]:
    from app.core.config import settings

    enabled_names = set(_TOOL_SPECS)
    if not settings.KNOWLEDGE_WIKI_ENABLED:
        enabled_names -= _WIKI_READ_TOOLS | _WIKI_WRITE_TOOLS
    elif not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        enabled_names -= _WIKI_WRITE_TOOLS
    if not settings.KNOWLEDGE_GROWTH_ENABLED:
        enabled_names -= _GROWTH_TOOLS
    elif not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        enabled_names -= _GROWTH_WRITE_ONLY_TOOLS
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": {
                "type": "object",
                "properties": spec.get("properties", {}),
                "required": spec.get("required", []),
                "additionalProperties": False,
            },
        }
        for name, spec in _TOOL_SPECS.items()
        if name in enabled_names
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
        if expected_type == "string" and isinstance(value, str):
            if schema.get("minLength") is not None and len(value) < schema["minLength"]:
                return f"Argument {key} for {name} is shorter than {schema['minLength']} characters"
            if schema.get("maxLength") is not None and len(value) > schema["maxLength"]:
                return f"Argument {key} for {name} is longer than {schema['maxLength']} characters"
            if schema.get("enum") is not None and value not in schema["enum"]:
                return f"Argument {key} for {name} must be one of: {', '.join(schema['enum'])}"
        if expected_type == "array" and not isinstance(value, list):
            return f"Argument {key} for {name} must be an array"
        if expected_type == "object" and not isinstance(value, dict):
            return f"Argument {key} for {name} must be an object"
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
        server._require_mcp_auth(api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _success(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload
