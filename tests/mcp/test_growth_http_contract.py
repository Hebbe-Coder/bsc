import asyncio
import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mcp_http
from app.api.mcp_http import router
from app.core.config import settings
from app.knowledge.growth_contracts import MethodAsset, MethodRevision, MethodStatus, OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.wiki_contracts import SourceStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.mcp import growth_tools, server


def _client(monkeypatch, role="admin", project_id=None):
    monkeypatch.setattr(server, "_require_mcp_auth", lambda _api_key="": (role, project_id))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _call(client, name, arguments, request_id=1):
    return client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    ).json()


def _method(repo, project_id, slug, *, status=MethodStatus.PUBLISHED, revisions=2):
    revision_ids = [f"{project_id}-{slug}-revision-{index}" for index in range(1, revisions + 1)]
    method = repo.create_method(
        MethodAsset(
            project_id=project_id,
            slug=slug,
            name=slug,
            status=status,
            active_revision_id=revision_ids[-1] if revision_ids else "",
        )
    )
    saved = [
        repo.save_method_revision(
            MethodRevision(
                id=revision_id,
                project_id=project_id,
                method_id=method["id"],
                version=index,
                body=f"# {slug} v{index}",
                status=MethodStatus.PUBLISHED,
            )
        )
        for index, revision_id in enumerate(revision_ids, start=1)
    ]
    return method, saved


def _output(repo, project_id, key, *, status):
    if not repo.get_vault(project_id):
        repo.configure_vault(project_id, f"projects/{project_id}", "test")
    content = f"{project_id}-{key}".encode()
    return OutputRegistry(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).register_content(
        OutputAsset(
            project_id=project_id,
            kind="report",
            content_hash=hashlib.sha256(content).hexdigest(),
            vault_path=f"outputs/2026/{key}.md",
            idempotency_key=f"{project_id}-{key}",
            status=status,
            metadata={
                "goal": "test filing",
                "audience": "test",
                "channel": "mcp",
                "generator": "pytest",
                "provider": "local",
                "model": "none",
                "prompt_revision": "v1",
            },
        ),
        content,
    )


def test_initialize_tools_list_and_growth_calls_preserve_json_rpc(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    initialized = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    ).json()
    listed = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ).json()
    names = {item["name"] for item in listed["result"]["tools"]}

    assert initialized["result"]["protocolVersion"]
    assert {
        "knowledge_growth_profile",
        "knowledge_growth_assets",
        "knowledge_growth_method",
        "knowledge_growth_output",
        "knowledge_growth_feedback",
        "knowledge_growth_schedule",
        "knowledge_growth_run",
        "knowledge_growth_distillation",
    } <= names
    assert "wiki_search" not in names


def test_disabled_growth_and_scheduler_unavailable_have_stable_errors(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", False)
    disabled = _call(client, "knowledge_growth_summary", {"project_id": "project-a"})
    assert disabled["error"]["code"] == -32003
    assert disabled["error"]["data"] == {
        "code": "dependency_unavailable",
        "availability": {"growth": False},
    }

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)
    unavailable = _call(
        client,
        "knowledge_growth_schedule",
        {
            "project_id": "project-a",
            "action": "create",
            "job_type": "growth_daily",
            "cron": "0 17 * * *",
            "timezone": "Asia/Shanghai",
        },
        2,
    )
    assert unavailable["error"]["code"] == -32003
    assert unavailable["error"]["data"]["code"] == "dependency_unavailable"


def test_mcp_summary_counts_filed_outputs_as_verified(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    db_path = str(tmp_path / "growth-mcp-summary.db")
    monkeypatch.setattr(growth_tools, "_repo", lambda: GrowthRepository(db_path=db_path))

    seed = GrowthRepository(db_path=db_path)
    try:
        for output_id, status in (("accepted", "accepted"), ("filed", "filed"), ("rejected", "rejected")):
            seed.register_output(
                OutputAsset(
                    id=output_id,
                    project_id="project-a",
                    kind="report",
                    content_hash=(output_id[0] * 64),
                    vault_path=f"outputs/2026/{output_id}/report.md",
                    idempotency_key=output_id,
                    status=status,
                )
            )
    finally:
        seed.close()

    result = _call(client, "knowledge_growth_summary", {"project_id": "project-a"})

    assert result["result"]["structuredContent"]["counts"]["outputs"] == 3
    assert result["result"]["structuredContent"]["counts"]["accepted_outputs"] == 2


def test_reader_mutation_cross_project_and_malformed_arguments_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    reader = _client(monkeypatch, role="project_reader", project_id="project-a")

    denied = _call(
        reader,
        "knowledge_growth_source_triage",
        {"project_id": "project-a", "action": "run", "source_id": "source-a"},
    )
    cross = _call(reader, "knowledge_growth_profile", {"project_id": "project-b"}, 2)
    malformed = _call(
        reader,
        "knowledge_growth_assets",
        {"project_id": "project-a", "limit": 501},
        3,
    )
    unexpected = _call(
        reader,
        "knowledge_growth_profile",
        {"project_id": "project-a", "shell": "whoami"},
        4,
    )
    reader_deprecate = _call(
        reader,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "deprecate",
            "method_id": "method-a",
            "payload": {"reason": "reader mutation"},
        },
        5,
    )
    reader_file = _call(
        reader,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": "output-a",
            "payload": {"reason": "reader mutation"},
        },
        6,
    )
    cross_deprecate = _call(
        reader,
        "knowledge_growth_method",
        {
            "project_id": "project-b",
            "action": "deprecate",
            "method_id": "method-b",
            "payload": {"reason": "cross-project mutation"},
        },
        7,
    )

    assert denied["error"]["code"] == -32001
    assert denied["error"]["data"]["code"] == "permission_denied"
    assert cross["error"]["code"] == -32001
    assert malformed["error"]["code"] == -32602
    assert unexpected["error"]["code"] == -32602
    assert reader_deprecate["error"]["code"] == -32001
    assert reader_file["error"]["code"] == -32001
    assert cross_deprecate["error"]["code"] == -32001


def test_growth_result_contains_pagination_availability_and_duplicate_state(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(
        mcp_http,
        "_TOOL_HANDLERS",
        {
            **mcp_http._TOOL_HANDLERS,
            "knowledge_growth_assets": lambda **_kwargs: {
                "project_id": "project-a",
                "items": [],
                "pagination": {"limit": 25, "cursor": None, "next_cursor": None, "count": 0},
                "availability": {"growth": True, "scheduler": False, "vault": False, "mcp_write": True},
            },
            "knowledge_growth_run": lambda **_kwargs: {
                "project_id": "project-a",
                "run": {"status": "duplicate", "run_id": "run-1"},
                "availability": {"growth": True, "scheduler": True, "vault": True, "mcp_write": True},
            },
        },
    )

    assets = _call(client, "knowledge_growth_assets", {"project_id": "project-a", "limit": 25})
    duplicate = _call(
        client,
        "knowledge_growth_run",
        {"project_id": "project-a", "action": "start", "job_type": "growth_daily", "idempotency_key": "same"},
        2,
    )

    assets_data = assets["result"]["structuredContent"]
    duplicate_data = duplicate["result"]["structuredContent"]
    assert assets_data["pagination"]["limit"] == 25
    assert assets_data["availability"]["growth"] is True
    assert duplicate_data["run"]["status"] == "duplicate"


def test_mcp_sse_message_transport_carries_growth_json_rpc_response(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(
        mcp_http,
        "_TOOL_HANDLERS",
        {
            **mcp_http._TOOL_HANDLERS,
            "knowledge_growth_summary": lambda **_kwargs: {
                "project_id": "project-a",
                "counts": {},
                "availability": {"growth": True},
            },
        },
    )

    session_id = "growth-contract-session"
    queue = asyncio.Queue()
    mcp_http._sse_sessions[session_id] = queue
    try:
        sent = client.post(
            f"/api/mcp/messages/{session_id}",
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_growth_summary",
                    "arguments": {"project_id": "project-a"},
                },
            },
        )
        payload = queue.get_nowait()
    finally:
        mcp_http._sse_sessions.pop(session_id, None)

    assert sent.status_code == 202
    assert payload["id"] == 7
    assert payload["result"]["structuredContent"]["project_id"] == "project-a"


def test_every_growth_domain_tool_executes_against_persisted_project_state(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir()
    db_path = str(tmp_path / "growth-mcp.db")
    monkeypatch.setattr(growth_tools, "_repo", lambda: GrowthRepository(db_path=db_path))

    seed = GrowthRepository(db_path=db_path)
    captured = SourceCaptureService(seed).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="web",
            raw_content="verified MCP evidence",
            trust_level="trusted",
        )
    )
    source_id = captured.source["id"]
    seed.update_source_status("project-a", source_id, SourceStatus.VALIDATED)
    seed.close()

    calls = [
        ("knowledge_growth_profile", {"project_id": "project-a"}),
        ("knowledge_growth_assets", {"project_id": "project-a", "stage": "A", "limit": 10}),
        (
            "knowledge_growth_source_triage",
            {"project_id": "project-a", "action": "run", "source_id": source_id},
        ),
        ("knowledge_growth_method", {"project_id": "project-a", "action": "list"}),
        ("knowledge_growth_output", {"project_id": "project-a", "action": "list"}),
        ("knowledge_growth_feedback", {"project_id": "project-a", "action": "list"}),
        ("knowledge_growth_lineage", {"project_id": "project-a", "limit": 10}),
        ("knowledge_growth_summary", {"project_id": "project-a"}),
        (
            "knowledge_growth_review",
            {"project_id": "project-a", "action": "method_detection", "minimum_uses": 3},
        ),
        ("knowledge_growth_schedule", {"project_id": "project-a", "action": "list"}),
        ("knowledge_growth_run", {"project_id": "project-a", "action": "list"}),
        ("knowledge_growth_distillation", {"project_id": "project-a", "action": "list"}),
    ]

    for request_id, (name, arguments) in enumerate(calls, start=20):
        response = _call(client, name, arguments, request_id)
        assert "error" not in response, (name, response)
        result = response["result"]["structuredContent"]
        assert result["project_id"] == "project-a"
        assert result["availability"]["growth"] is True


def test_mcp_lineage_returns_the_same_bounded_node_projection(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir()
    db_path = str(tmp_path / "growth-mcp-lineage.db")
    monkeypatch.setattr(growth_tools, "_repo", lambda: GrowthRepository(db_path=db_path))
    repo = GrowthRepository(db_path=db_path)
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="web",
            origin="https://example.test/mcp-lineage",
            raw_content="private MCP evidence body",
            trust_level="trusted",
        )
    ).source
    repo.update_source_status("project-a", source["id"], SourceStatus.ELIGIBLE)
    output = _output(repo, "project-a", "mcp-lineage", status="registered")
    repo.attach_output_evidence_references("project-a", output["id"], source_ids=[source["id"]], page_ids=[])

    response = _call(client, "knowledge_growth_lineage", {"project_id": "project-a"})

    result = response["result"]["structuredContent"]
    nodes = {node["id"]: node for node in result["nodes"]}
    assert nodes[source["id"]]["label"] == "example.test signal"
    assert nodes[output["id"]]["type"] == "output"
    assert result["edges"][0]["from_type"] == "source"
    assert "private MCP evidence body" not in str(result)
    repo.close()


def test_mcp_profile_cas_and_run_idempotency_are_durable(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", False)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir()
    db_path = str(tmp_path / "growth-mcp-cas.db")
    monkeypatch.setattr(growth_tools, "_repo", lambda: GrowthRepository(db_path=db_path))

    updated = _call(
        client,
        "knowledge_growth_profile",
        {
            "project_id": "project-a",
            "action": "update",
            "profile": {"user_role": "researcher"},
            "expected_revision": 0,
        },
        40,
    )
    stale = _call(
        client,
        "knowledge_growth_profile",
        {
            "project_id": "project-a",
            "action": "update",
            "profile": {"user_role": "stale"},
            "expected_revision": 0,
        },
        41,
    )
    first_run = _call(
        client,
        "knowledge_growth_run",
        {
            "project_id": "project-a",
            "action": "start",
            "job_type": "growth_daily",
            "idempotency_key": "same-run",
        },
        42,
    )
    duplicate = _call(
        client,
        "knowledge_growth_run",
        {
            "project_id": "project-a",
            "action": "start",
            "job_type": "growth_daily",
            "idempotency_key": "same-run",
        },
        43,
    )

    assert updated["result"]["structuredContent"]["profile"]["revision"] == 1
    assert stale["error"]["code"] == -32009
    assert stale["error"]["data"]["code"] == "knowledge_conflict"
    assert first_run["result"]["structuredContent"]["run"]["status"] == "unavailable"
    assert duplicate["result"]["structuredContent"]["run"]["status"] == "duplicate"
    assert (
        first_run["result"]["structuredContent"]["run"]["run_id"]
        == duplicate["result"]["structuredContent"]["run"]["run_id"]
    )


def test_mcp_method_revisions_deprecation_and_output_filing_are_governed(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_MCP_WRITE_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir()
    db_path = str(tmp_path / "growth-mcp-lifecycle.db")
    monkeypatch.setattr(growth_tools, "_repo", lambda: GrowthRepository(db_path=db_path))

    seed = GrowthRepository(db_path=db_path)
    published, revisions = _method(seed, "project-a", "published-method")
    candidate, _ = _method(
        seed,
        "project-a",
        "candidate-method",
        status=MethodStatus.CANDIDATE,
        revisions=0,
    )
    other_method, _ = _method(seed, "project-b", "other-method", revisions=1)
    accepted = _output(seed, "project-a", "accepted", status="accepted")
    registered = _output(seed, "project-a", "registered", status="registered")
    other_output = _output(seed, "project-b", "other", status="accepted")
    immutable_before = {
        key: accepted[key]
        for key in ("id", "project_id", "content_hash", "vault_path", "idempotency_key")
    }
    seed.close()

    revision_page = _call(
        client,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "revisions",
            "method_id": published["id"],
            "limit": 1,
        },
        50,
    )
    deprecated = _call(
        client,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "deprecate",
            "method_id": published["id"],
            "payload": {"reason": "superseded by reviewed workflow"},
        },
        51,
    )
    repeated_deprecation = _call(
        client,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "deprecate",
            "method_id": published["id"],
            "payload": {"reason": "safe retry"},
        },
        52,
    )
    invalid_deprecation = _call(
        client,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "deprecate",
            "method_id": candidate["id"],
            "payload": {"reason": "invalid state"},
        },
        53,
    )
    cross_deprecation = _call(
        client,
        "knowledge_growth_method",
        {
            "project_id": "project-a",
            "action": "deprecate",
            "method_id": other_method["id"],
            "payload": {"reason": "cross project"},
        },
        54,
    )

    filed = _call(
        client,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": accepted["id"],
            "payload": {"reason": "approved for durable filing"},
        },
        55,
    )
    repeated_filing = _call(
        client,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": accepted["id"],
            "payload": {"reason": "safe retry"},
        },
        56,
    )
    invalid_filing = _call(
        client,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": registered["id"],
            "payload": {"reason": "not accepted"},
        },
        57,
    )
    cross_filing = _call(
        client,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": other_output["id"],
            "payload": {"reason": "cross project"},
        },
        58,
    )
    missing_reason = _call(
        client,
        "knowledge_growth_output",
        {
            "project_id": "project-a",
            "action": "file",
            "output_id": registered["id"],
            "payload": {},
        },
        59,
    )

    revision_data = revision_page["result"]["structuredContent"]
    assert revision_data["revisions"][0]["id"] == revisions[1]["id"]
    assert revision_data["pagination"]["next_cursor"] == "1"
    assert deprecated["result"]["structuredContent"]["method"]["status"] == "deprecated"
    assert deprecated["result"]["structuredContent"]["idempotent"] is False
    assert repeated_deprecation["result"]["structuredContent"]["idempotent"] is True
    assert invalid_deprecation["error"]["code"] == -32009
    assert cross_deprecation["error"]["code"] == -32004

    assert filed["result"]["structuredContent"]["output"]["status"] == "filed"
    assert filed["result"]["structuredContent"]["idempotent"] is False
    assert repeated_filing["result"]["structuredContent"]["idempotent"] is True
    assert invalid_filing["error"]["code"] == -32009
    assert cross_filing["error"]["code"] == -32004
    assert missing_reason["error"]["code"] == -32602
    verify = GrowthRepository(db_path=db_path)
    try:
        assert {
            key: verify.get_output("project-a", accepted["id"])[key]
            for key in immutable_before
        } == immutable_before
        lifecycle_runs = {
            run["run_type"]: run
            for run in verify.list_runs("project-a", limit=500)
            if run["run_type"] in {"method_deprecate", "output_file"}
        }
        assert set(lifecycle_runs) == {"method_deprecate", "output_file"}
        assert lifecycle_runs["method_deprecate"]["actor_id"] == "mcp"
        assert lifecycle_runs["output_file"]["actor_id"] == "mcp"
        assert lifecycle_runs["method_deprecate"]["input_refs"]["reason"] == (
            "superseded by reviewed workflow"
        )
        assert lifecycle_runs["output_file"]["input_refs"]["reason"] == (
            "approved for durable filing"
        )
    finally:
        verify.close()
