import pytest

from app.api import mcp_http
from app.mcp import operations_tools, server


def test_operations_mcp_catalog_and_role_bound_delegation(monkeypatch):
    names = {item["name"] for item in mcp_http._tool_list()}
    assert {
        "knowledge_operations_portfolio",
        "knowledge_operations_project",
        "knowledge_operations_graph",
    } <= names

    calls = []
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("admin", None))
    monkeypatch.setattr(operations_tools, "portfolio", lambda: {"state": "available", "scope": {"tenant_id": "default"}})
    monkeypatch.setattr(operations_tools, "project", lambda project_id, **kwargs: calls.append(("project", project_id, kwargs)) or {"project_id": project_id})
    monkeypatch.setattr(operations_tools, "graph", lambda project_id, **kwargs: calls.append(("graph", project_id, kwargs)) or {"project_id": project_id})

    assert server.knowledge_operations_portfolio() == {"state": "available", "scope": {"tenant_id": "default"}}
    assert server.knowledge_operations_project("project-a")["project_id"] == "project-a"
    assert server.knowledge_operations_graph("project-a", mission_id="mission-a", limit=12)["project_id"] == "project-a"
    assert calls == [
        ("project", "project-a", {"tenant_id": "default"}),
        ("graph", "project-a", {"mission_id": "mission-a", "limit": 12, "cursor": "", "tenant_id": "default"}),
    ]


def test_operations_mcp_refuses_portfolio_for_project_scoped_principals(monkeypatch):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_reader", "project-a"))
    calls = []
    monkeypatch.setattr(operations_tools, "project_tenant", lambda project_id: "tenant-b")
    monkeypatch.setattr(operations_tools, "project", lambda project_id, **kwargs: calls.append((project_id, kwargs)) or {"project_id": project_id})
    monkeypatch.setattr(operations_tools, "graph", lambda project_id, **kwargs: calls.append((f"graph:{project_id}", kwargs)) or {"project_id": project_id})
    with pytest.raises(PermissionError, match="admin"):
        server.knowledge_operations_portfolio()
    assert server.knowledge_operations_project("project-a") == {"project_id": "project-a"}
    assert server.knowledge_operations_graph("project-a", mission_id="mission-a", limit=12) == {"project_id": "project-a"}
    assert calls == [
        ("project-a", {"tenant_id": "tenant-b"}),
        ("graph:project-a", {"mission_id": "mission-a", "limit": 12, "cursor": "", "tenant_id": "tenant-b"}),
    ]
    with pytest.raises(PermissionError, match="project"):
        server.knowledge_operations_project("project-b")
