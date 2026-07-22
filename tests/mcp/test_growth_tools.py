import pytest

from app.api import mcp_http
from app.core.config import settings
from app.mcp import server


EXPECTED_GROWTH_TOOLS = {
    "knowledge_growth_profile",
    "knowledge_growth_assets",
    "knowledge_growth_source_triage",
    "knowledge_growth_method",
    "knowledge_growth_output",
    "knowledge_growth_feedback",
    "knowledge_growth_lineage",
    "knowledge_growth_summary",
    "knowledge_growth_review",
    "knowledge_growth_schedule",
    "knowledge_growth_run",
    "knowledge_growth_distillation",
}


def test_complete_growth_tool_surface_is_independent_of_legacy_wiki(monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)

    names = {item["name"] for item in mcp_http._tool_list()}

    assert EXPECTED_GROWTH_TOOLS <= names
    assert "knowledge_growth_triage" in names
    assert "knowledge_growth_weekly_distill" in names
    assert "wiki_read" not in names


@pytest.mark.parametrize("role", ["admin", "system", "project_admin"])
def test_growth_admin_and_system_roles_can_mutate_scoped_project(monkeypatch, role):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    scoped = "project-a" if role in {"system", "project_admin"} else None
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": (role, scoped))

    server._authorize_growth_project("project-a", "key", write=True)
    if scoped:
        with pytest.raises(PermissionError, match="project"):
            server._authorize_growth_project("project-b", "key", write=True)


@pytest.mark.parametrize("role", ["reader", "project_reader"])
def test_growth_reader_roles_are_read_only(monkeypatch, role):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    scoped = "project-a" if role == "project_reader" else None
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": (role, scoped))

    server._authorize_growth_project("project-a", "reader-key")
    with pytest.raises(PermissionError, match="read-only"):
        server._authorize_growth_project("project-a", "reader-key", write=True)
    if scoped:
        with pytest.raises(PermissionError, match="project"):
            server._authorize_growth_project("project-b", "reader-key")


def test_growth_authorization_reports_availability_and_write_policy(monkeypatch):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("admin", None))
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", False)
    with pytest.raises(RuntimeError, match="disabled"):
        server._authorize_growth_project("project-a")

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", False)
    with pytest.raises(RuntimeError, match="writes are disabled"):
        server._authorize_growth_project("project-a", write=True)


def test_growth_action_permissions_are_stable():
    assert server._growth_action_is_write("method", "list") is False
    assert server._growth_action_is_write("method", "revisions") is False
    assert server._growth_action_is_write("method", "propose") is True
    assert server._growth_action_is_write("method", "deprecate") is True
    assert server._growth_action_is_write("output", "file") is True
    assert server._growth_action_is_write("run", "events") is False
    with pytest.raises(ValueError, match="unsupported"):
        server._growth_action_is_write("run", "shell")
