from fastapi.testclient import TestClient

from app.api import dbos_api
from app.main import app
from app.mcp import server


def _call(client: TestClient, name: str, arguments: dict, request_id: int = 1) -> dict:
    return client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    ).json()


def test_pbos_mcp_tools_advertise_and_enforce_project_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _api_key="": ("project_reader", "personal"))
    client = TestClient(app)

    listed = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert {"pbos_cockpit", "pbos_weekly_report"}.issubset(names)

    cockpit = _call(client, "pbos_cockpit", {"project_id": "personal"}, 2)
    data = cockpit["result"]["structuredContent"]["data"]
    assert data["profile"] is None
    assert data["connectors"]["github"] == "awaiting_authorization"

    denied = _call(client, "pbos_cockpit", {"project_id": "another-project"}, 3)
    assert denied["error"]["code"] == -32001
    assert denied["error"]["data"]["code"] == "permission_denied"
