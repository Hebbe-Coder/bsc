import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mcp_http
from app.api.mcp_http import router
from app.core.config import settings
from app.mcp import information_intelligence_tools, server


def test_information_mcp_tools_are_read_only_and_project_scoped(monkeypatch):
    previous_enabled = settings.KNOWLEDGE_INTELLIGENCE_ENABLED
    previous_wiki_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.KNOWLEDGE_INTELLIGENCE_ENABLED = True
    settings.KNOWLEDGE_WIKI_ENABLED = True
    calls = []
    try:
        monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_reader", "project-a"))
        monkeypatch.setattr(information_intelligence_tools, "overview", lambda project_id: calls.append(("overview", project_id)) or {"project_id": project_id})
        monkeypatch.setattr(information_intelligence_tools, "receipts", lambda project_id, limit=100: calls.append(("receipts", project_id, limit)) or {"project_id": project_id})

        assert server.knowledge_information_overview("project-a") == {"project_id": "project-a"}
        assert server.knowledge_information_receipts("project-a", limit=999) == {"project_id": "project-a"}
        assert calls == [("overview", "project-a"), ("receipts", "project-a", 500)]
        with pytest.raises(PermissionError):
            server.knowledge_information_overview("project-b")
    finally:
        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = previous_enabled
        settings.KNOWLEDGE_WIKI_ENABLED = previous_wiki_enabled


def test_ingress_key_cannot_use_information_read_tools(monkeypatch):
    previous_enabled = settings.KNOWLEDGE_INTELLIGENCE_ENABLED
    previous_wiki_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.KNOWLEDGE_INTELLIGENCE_ENABLED = True
    settings.KNOWLEDGE_WIKI_ENABLED = True
    try:
        monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_ingress", "project-a"))
        with pytest.raises(PermissionError):
            server.knowledge_information_overview("project-a")
    finally:
        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = previous_enabled
        settings.KNOWLEDGE_WIKI_ENABLED = previous_wiki_enabled


def test_http_mcp_advertises_and_invokes_information_read_tools_only_when_enabled(monkeypatch):
    previous_enabled = settings.KNOWLEDGE_INTELLIGENCE_ENABLED
    try:
        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = True
        names = {tool["name"] for tool in mcp_http._tool_list()}
        assert {"knowledge_information_overview", "knowledge_information_receipts", "knowledge_information_daily_brief"} <= names

        calls = []
        monkeypatch.setitem(
            mcp_http._TOOL_HANDLERS,
            "knowledge_information_overview",
            lambda project_id, api_key="": calls.append((project_id, api_key)) or {"project_id": project_id, "state": "ready"},
        )
        app = FastAPI()
        app.include_router(router)
        payload = TestClient(app).post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "knowledge_information_overview", "arguments": {"project_id": "project-a"}},
            },
        ).json()
        assert payload["result"]["structuredContent"] == {"project_id": "project-a", "state": "ready"}
        assert calls == [("project-a", "")]

        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = False
        names = {tool["name"] for tool in mcp_http._tool_list()}
        assert "knowledge_information_overview" not in names
        assert "knowledge_information_receipts" not in names
        assert "knowledge_information_daily_brief" not in names
    finally:
        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = previous_enabled


def test_mcp_daily_brief_is_project_scoped_and_read_only(monkeypatch):
    previous_enabled = settings.KNOWLEDGE_INTELLIGENCE_ENABLED
    previous_wiki_enabled = settings.KNOWLEDGE_WIKI_ENABLED
    settings.KNOWLEDGE_INTELLIGENCE_ENABLED = True
    settings.KNOWLEDGE_WIKI_ENABLED = True
    try:
        monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("project_reader", "project-a"))
        monkeypatch.setattr(
            information_intelligence_tools,
            "daily_brief",
            lambda project_id, day="": {"project_id": project_id, "day": day, "state": "no_sample"},
        )

        assert server.knowledge_information_daily_brief("project-a", day="2026-07-31") == {
            "project_id": "project-a", "day": "2026-07-31", "state": "no_sample"
        }
        with pytest.raises(PermissionError):
            server.knowledge_information_daily_brief("project-b", day="2026-07-31")
    finally:
        settings.KNOWLEDGE_INTELLIGENCE_ENABLED = previous_enabled
        settings.KNOWLEDGE_WIKI_ENABLED = previous_wiki_enabled
