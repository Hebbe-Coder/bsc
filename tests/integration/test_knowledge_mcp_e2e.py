"""Transport-level authorization tests for the governed Wiki MCP surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.wiki_repository import WikiRepository
from app.main import app
from app.mcp import server, wiki_tools
import app.middleware.auth as auth_middleware


def _call(client: TestClient, key: str, tool: str, arguments: dict, request_id: int):
    return client.post(
        "/api/mcp",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    ).json()


def _structured(payload: dict) -> dict:
    return payload["result"]["structuredContent"]


def test_http_mcp_enforces_project_scoped_wiki_read_and_write(tmp_path, monkeypatch):
    database_path = str(tmp_path / "knowledge-mcp.db")
    repository = WikiRepository(db_path=database_path)
    repository.configure_vault("project-a", "projects/project-a")
    repository.configure_vault("project-b", "projects/project-b")
    source_a = SourceCaptureService(repository).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="a.md",
            raw_content="Project A only evidence",
            trust_level="trusted",
        )
    ).source
    SourceCaptureService(repository).capture(
        CapturedSourceInput(
            project_id="project-b",
            source_type="manual_upload",
            origin="b.md",
            raw_content="Project B only evidence",
            trust_level="trusted",
        )
    )

    principals = {
        "project-a-admin": ("project_admin", "project-a"),
        "project-a-reader": ("project_reader", "project-a"),
    }
    monkeypatch.setattr(server, "_MCP_API_KEY", "")
    monkeypatch.setattr(settings, "API_KEY", "global-admin-not-used")
    monkeypatch.setattr(server, "resolve_knowledge_auth", lambda key: principals.get(key))
    monkeypatch.setattr(auth_middleware, "resolve_knowledge_auth", lambda key: principals.get(key))
    monkeypatch.setattr(wiki_tools, "WikiRepository", lambda: WikiRepository(db_path=database_path))
    client = TestClient(app)
    try:
        readable = _call(client, "project-a-admin", "wiki_search", {"project_id": "project-a"}, 1)
        assert _structured(readable)["project_id"] == "project-a"
        assert _structured(readable)["sources"][0]["id"] == source_a["id"]

        cross_read = _call(client, "project-a-admin", "wiki_search", {"project_id": "project-b"}, 2)
        assert cross_read["error"]["code"] == -32001

        proposal_before = len(repository.list_proposals("project-b"))
        cross_write = _call(
            client,
            "project-a-admin",
            "wiki_propose_update",
            {
                "project_id": "project-b",
                "operations": [{"operation": "create", "path": "wiki/concepts/nope.md", "content": "# No"}],
            },
            3,
        )
        assert cross_write["error"]["code"] == -32001
        assert len(repository.list_proposals("project-b")) == proposal_before

        reader_read = _call(client, "project-a-reader", "wiki_search", {"project_id": "project-a"}, 4)
        assert _structured(reader_read)["count"] == 1

        reader_write = _call(
            client,
            "project-a-reader",
            "wiki_propose_update",
            {
                "project_id": "project-a",
                "operations": [{"operation": "create", "path": "wiki/concepts/nope.md", "content": "# No"}],
            },
            5,
        )
        assert reader_write["error"]["code"] == -32001
        assert repository.list_proposals("project-a") == []
    finally:
        repository.close()
