from fastapi.testclient import TestClient

from app.api.knowledge_workspace_api import get_wiki_repository
from app.core.config import settings
from app.knowledge.wiki_contracts import KnowledgeRun
from app.knowledge.wiki_repository import WikiRepository
from app.main import app


def test_sse_reconnect_rejects_ahead_cursor_and_closes_on_durable_cancellation(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "knowledge-sse.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    prior_key = settings.API_KEY
    settings.API_KEY = "sse-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer sse-admin"}
    try:
        ahead = client.get(
            f"/knowledge/runs/{run.id}/events?project_id=project-a&after_sequence=2",
            headers=headers,
        )
        cancelled = client.post(
            f"/knowledge/runs/{run.id}/cancel?project_id=project-a",
            headers=headers,
        )
        stream = client.get(
            f"/knowledge/runs/{run.id}/events/stream?project_id=project-a&after_sequence=1",
            headers=headers,
        )
        replay = client.get(
            f"/knowledge/runs/{run.id}/events?project_id=project-a&after_sequence=1",
            headers=headers,
        )

        assert ahead.status_code == 409
        assert ahead.json()["message"]["code"] == "event_sequence_ahead"
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["run"]["status"] == "cancelled"
        assert "event: knowledge.run.cancelled" in stream.text
        assert [event["sequence"] for event in replay.json()["data"]["events"]] == [2]
    finally:
        settings.API_KEY = prior_key
        app.dependency_overrides.clear()
        repo.close()


def test_sse_requires_read_permission_and_keeps_projects_isolated(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "knowledge-sse-scope.db"))
    run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repo.create_run(run)
    prior_key = settings.API_KEY
    settings.API_KEY = "sse-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        unauthenticated = client.get(f"/knowledge/runs/{run.id}/events?project_id=project-a")
        cross_project = client.get(
            f"/knowledge/runs/{run.id}/events?project_id=project-b",
            headers={"Authorization": "Bearer sse-admin"},
        )

        assert unauthenticated.status_code == 401
        assert cross_project.status_code == 404
    finally:
        settings.API_KEY = prior_key
        app.dependency_overrides.clear()
        repo.close()
