# tests/orchestrator/test_api.py
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.agent.state import ProjectDraftRepository
from app.core.config import settings

@pytest.fixture
def client():
    return TestClient(app)


def _enable_auth(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-key-123")


def test_orchestrate_requires_auth(client, monkeypatch):
    _enable_auth(monkeypatch)
    # 注：全局 AuthMiddleware 在 TestClient 下会把 401 以 HTTPException 形式抛出，
    # 与仓库内 tests/knowledge/test_api_auth.py 的既有约定一致，故用 pytest.raises 校验。
    with pytest.raises(HTTPException) as exc:
        client.post("/api/orchestrate", json={"idea": "内容审核中心"})
    assert exc.value.status_code in (401, 403)


def test_orchestrate_runs(client, monkeypatch):
    _enable_auth(monkeypatch)

    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    r = client.post("/api/orchestrate", json={"idea": "内容审核中心"},
                    headers={"Authorization": "Bearer test-key-123"})
    assert r.status_code == 202
    sid = r.json()["session_id"]
    assert sid and sid != "started"
    repo = ProjectDraftRepository()
    got = repo.get(sid)
    assert got is not None
    assert "project" in got.to_dict()


def test_create_returns_202_and_discovery_urls(client, monkeypatch):
    _enable_auth(monkeypatch)

    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    response = client.post(
        "/api/orchestrate",
        json={"idea": "test business"},
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"].endswith(body["session_id"])
    assert body["events_url"].endswith(body["session_id"] + "/events")


def test_create_rejects_duplicate_session_id(client, monkeypatch):
    import uuid

    async def blocked_run(self, session_id, idea):
        return {}

    _enable_auth(monkeypatch)
    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    sid = f"dup-{uuid.uuid4().hex[:8]}"
    payload = {"idea": "test business", "session_id": sid}
    first = client.post(
        "/api/orchestrate",
        json=payload,
        headers={"Authorization": "Bearer test-key-123"},
    )
    second = client.post(
        "/api/orchestrate",
        json=payload,
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert first.status_code == 202
    assert second.status_code == 409


def test_status_endpoint_returns_terminal_flag(client, monkeypatch):
    _enable_auth(monkeypatch)

    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    created = client.post(
        "/api/orchestrate",
        json={"idea": "test business"},
        headers={"Authorization": "Bearer test-key-123"},
    ).json()
    repo = ProjectDraftRepository()
    repo.transition(created["session_id"], "running")
    repo.transition(created["session_id"], "completed")

    response = client.get(
        f"/api/orchestrate/{created['session_id']}",
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["terminal"] is True


def test_cancel_requests_the_retained_task(client, monkeypatch):
    import uuid

    from app.api import orchestrate as orchestrate_api
    from app.agent.state import ProjectDraft, ProjectDraftRepository

    class Cancellable:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    _enable_auth(monkeypatch)
    sid = f"cancel-{uuid.uuid4().hex[:8]}"
    ProjectDraftRepository().save(ProjectDraft(
        session_id=sid,
        idea="x",
        status="running",
    ))
    task = Cancellable()
    orchestrate_api._tasks[sid] = task
    try:
        response = client.delete(
            f"/api/orchestrate/{sid}",
            headers={"Authorization": "Bearer test-key-123"},
        )
    finally:
        orchestrate_api._tasks.pop(sid, None)

    assert response.status_code == 202
    assert response.json()["cancel_requested"] is True
    assert task.cancelled is True


def test_resume_cursor_uses_last_event_id_header():
    from starlette.requests import Request
    from app.api import orchestrate as orchestrate_api

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/orchestrate/s1/events",
        "headers": [(b"last-event-id", b"7")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
        "scheme": "http",
    })

    assert orchestrate_api._resume_after(request, after=3) == 7


def test_unknown_status_returns_404(client, monkeypatch):
    _enable_auth(monkeypatch)
    response = client.get(
        "/api/orchestrate/missing-session",
        headers={"Authorization": "Bearer test-key-123"},
    )
    assert response.status_code == 404


def test_task_cancelled_before_start_reaches_terminal(draft_repo, monkeypatch):
    import asyncio

    from app.api import orchestrate as orchestrate_api
    from app.agent.state import ProjectDraft
    from app.orchestrator.contracts import EventType
    from app.orchestrator.sse import SessionEventBus

    sid = "cancel-before-start"
    bus = SessionEventBus()
    draft_repo.save(ProjectDraft(
        session_id=sid,
        idea="x",
        status="queued",
    ))
    monkeypatch.setattr(
        orchestrate_api,
        "ProjectDraftRepository",
        lambda: draft_repo,
    )
    monkeypatch.setattr(orchestrate_api, "_bus", bus)

    async def blocked():
        await asyncio.sleep(60)

    async def scenario():
        task = orchestrate_api._retain_task(sid, blocked())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert draft_repo.get(sid).status == "cancelled"
    events = list(bus._history[sid])
    assert events[-1].type == EventType.PIPELINE_CANCELLED
    assert events[-1].terminal is True


def test_create_returns_before_slow_pipeline_finishes(client, monkeypatch):
    import asyncio
    import time

    _enable_auth(monkeypatch)

    async def slow_run(self, session_id, idea):
        await asyncio.sleep(0.5)
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        slow_run,
    )
    started = time.perf_counter()
    response = client.post(
        "/api/orchestrate",
        json={"idea": "slow test business"},
        headers={"Authorization": "Bearer test-key-123"},
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 202
    assert elapsed < 0.2


def test_mock_provider_is_forced_for_orchestrator(client, monkeypatch):
    from app.api import orchestrate as orchestrate_api

    captured = {}

    class FakeLLM:
        def __init__(self, *, force_mock=False):
            captured["force_mock"] = force_mock

    async def blocked_run(self, session_id, idea):
        return {}

    _enable_auth(monkeypatch)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(orchestrate_api, "LLMService", FakeLLM)
    monkeypatch.setattr(orchestrate_api, "build_agents", lambda llm: {})
    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )

    response = client.post(
        "/api/orchestrate",
        json={"idea": "mock test business"},
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert response.status_code == 202
    assert captured["force_mock"] is True
