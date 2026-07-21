from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_http_mcp_lists_wiki_tools_and_requires_project_scope(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "")
    client = TestClient(app)
    listed = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}

    missing = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "wiki_graph", "arguments": {}}},
    )

    assert {
        "wiki_guide", "wiki_search", "wiki_graph", "wiki_read", "wiki_propose_update", "wiki_lint",
        "wiki_apply_update", "wiki_distill", "wiki_schedule",
    } <= names
    assert missing.json()["error"]["code"] == -32602
    assert "project_id" in missing.json()["error"]["message"]

    malformed = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "wiki_propose_update", "arguments": {"project_id": "default", "operations": "not-an-array"}},
        },
    )
    assert malformed.json()["error"]["code"] == -32602
    assert "operations" in malformed.json()["error"]["message"]
