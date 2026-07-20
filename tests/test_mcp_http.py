from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import mcp_http
from app.api.mcp_http import router
from app.mcp import server


def _client(monkeypatch):
    monkeypatch.setattr(server, "_require_auth", lambda api_key="": None)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_mcp_http_supports_initialize_tools_list_and_profile(monkeypatch):
    client = _client(monkeypatch)

    initialized = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    listed = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    called = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "bsc_mcp_compatibility_profile", "arguments": {}},
        },
    )

    assert initialized.status_code == 200
    assert initialized.json()["result"]["capabilities"]["tools"]
    assert listed.status_code == 200
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "bsc_compile" in names
    assert called.status_code == 200
    result = called.json()["result"]
    assert result["structuredContent"]["adapter"] == "bsc-mcp-stdio-http-sse"


def test_mcp_http_returns_json_rpc_errors(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 7, "method": "unknown/method"},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32601


def test_mcp_sse_message_routes_response_to_live_session(monkeypatch):
    monkeypatch.setattr(server, "_require_auth", lambda api_key="": None)

    async def scenario():
        session_id = "sse-session"
        queue = mcp_http.asyncio.Queue()
        mcp_http._sse_sessions[session_id] = queue
        body = b'{"jsonrpc":"2.0","id":9,"method":"ping","params":{}}'
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({
            "type": "http",
            "method": "POST",
            "path": f"/api/mcp/messages/{session_id}",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 123),
            "scheme": "http",
        }, receive)
        response = await mcp_http.mcp_sse_message(session_id, request)
        message = await queue.get()
        mcp_http._sse_sessions.pop(session_id, None)
        return response, message

    import asyncio

    response, message = asyncio.run(scenario())
    assert response.status_code == 202
    assert message == {"jsonrpc": "2.0", "id": 9, "result": {}}
