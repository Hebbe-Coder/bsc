from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mcp_http import router
from app.core.config import settings
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import build_default_agents_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.mcp import server, wiki_tools


def _call(client, name, arguments, request_id):
    response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "error" not in payload, payload
    return payload["result"]["structuredContent"]


def test_http_json_rpc_calls_every_governed_wiki_tool_against_real_state(tmp_path, monkeypatch):
    database_path = str(tmp_path / "wiki-mcp.db")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = WikiRepository(db_path=database_path)
    repo.configure_vault("project-a", "projects/project-a")
    vault = FilesystemWikiVault(vault_root, "project-a")
    contents = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/overview.md": "---\ntitle: Overview\nkind: brief\n---\n# Overview\n",
        "wiki/index.md": "# Index\n- [[wiki/overview.md]]\n",
        "wiki/log.md": "# Log\n",
    }
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="policy.md",
            raw_content="Approval requires a reviewer.", trust_level="trusted",
        )
    ).source
    SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="weekly.md",
            raw_content="# Weekly signal\nA separate eligible source for distillation.", trust_level="trusted",
        )
    )
    WikiEvaluator(repo).save_case(
        project_id="project-a", case_id="source", case_type="citation", expected={"source_ids": [source["id"]]}
    )
    page = next(item for item in repo.list_pages("project-a") if item["path"] == "wiki/overview.md")
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("admin", None))
    monkeypatch.setattr(wiki_tools, "WikiRepository", lambda: WikiRepository(db_path=database_path))
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault_root))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    try:
        initialized = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        listed = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert initialized.json()["result"]["protocolVersion"]
        names = {item["name"] for item in listed.json()["result"]["tools"]}
        assert {"wiki_guide", "wiki_search", "wiki_graph", "wiki_read", "wiki_propose_update", "wiki_lint", "wiki_apply_update", "wiki_distill", "wiki_schedule"} <= names

        assert _call(client, "wiki_guide", {"project_id": "project-a"}, 2)["project_id"] == "project-a"
        assert _call(client, "wiki_search", {"project_id": "project-a", "query": "policy"}, 3)["count"] == 1
        assert _call(client, "wiki_graph", {"project_id": "project-a"}, 4)["count"] == 1
        assert _call(client, "wiki_read", {"project_id": "project-a", "page_id": page["id"]}, 5)["page"]["id"] == page["id"]
        proposal = _call(
            client,
            "wiki_propose_update",
            {
                "project_id": "project-a",
                "source_ids": [source["id"]],
                "rationale": "Record approval evidence.",
                "operations": [
                    {"operation": "create", "path": "wiki/concepts/approval.md", "content": f"---\ntitle: Approval\nkind: concept\n---\nApproval requires a reviewer. [source:{source['id']}]", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/index.md", "content": "\n- [[wiki/concepts/approval.md]]\n", "source_ids": [source["id"]]},
                    {"operation": "append", "path": "wiki/log.md", "content": f"\n- Approval added. [source:{source['id']}]\n", "source_ids": [source["id"]]},
                ],
            },
            6,
        )["proposal"]
        assert _call(client, "wiki_lint", {"project_id": "project-a", "proposal_id": proposal["id"]}, 7)["valid"] is True
        assert _call(client, "wiki_apply_update", {"project_id": "project-a", "proposal_id": proposal["id"]}, 8)["status"] == "published"
        assert _call(client, "wiki_distill", {"project_id": "project-a"}, 9)["status"] == "completed"
        schedule = _call(
            client,
            "wiki_schedule",
            {"project_id": "project-a", "job_type": "source_sync", "cron": "*/15 * * * *", "timezone": "Asia/Shanghai"},
            10,
        )
        assert schedule["job_type"] == "source_sync"
        assert schedule["enabled"] == 0
    finally:
        repo.close()


def test_http_json_rpc_returns_stable_non_sensitive_wiki_error_codes(monkeypatch):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _key="": ("admin", None))
    monkeypatch.setitem(__import__("app.api.mcp_http", fromlist=["_TOOL_HANDLERS"])._TOOL_HANDLERS, "wiki_read", lambda **_kwargs: (_ for _ in ()).throw(ValueError("published Wiki page not found")))
    app = FastAPI()
    app.include_router(router)
    payload = TestClient(app).post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "wiki_read", "arguments": {"project_id": "project-a", "page_id": "missing"}}},
    ).json()

    assert payload["error"]["code"] == -32004
    assert payload["error"]["data"]["code"] == "resource_not_found"
