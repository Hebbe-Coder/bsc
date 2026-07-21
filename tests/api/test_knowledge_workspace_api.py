from fastapi.testclient import TestClient

from app.api.knowledge_workspace_api import get_wiki_repository
from app.core.config import settings
from app.main import app
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_workspace_api_requires_scope_and_redacts_raw_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-api.db"))
    repo.configure_vault("project-a", "projects/project-a")
    SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="secret evidence", trust_level="trusted")
    )
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        missing = client.get("/knowledge/sources", headers={"Authorization": "Bearer workspace-admin"})
        scoped = client.get("/knowledge/sources?project_id=project-a", headers={"Authorization": "Bearer workspace-admin"})
        status = client.get("/knowledge/workspaces/project-a", headers={"Authorization": "Bearer workspace-admin"})

        assert missing.status_code == 422
        assert scoped.status_code == 200
        source = scoped.json()["data"]["sources"][0]
        assert "raw_content" not in source
        assert status.json()["data"]["vault"]["configured"] is True
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_run_event_replay_is_scoped_and_streams_terminal_events(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-events.db"))
    run = KnowledgeRun(id="run-events", project_id="project-a", run_type="weekly_distillation", trigger="manual")
    repo.create_run(run)
    repo.update_run_status("project-a", run.id, RunStatus.COMPLETED, output_refs={"week": "2026-W30"})
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer workspace-admin"}
        replay = client.get("/knowledge/runs/run-events/events?project_id=project-a", headers=headers)
        stream = client.get("/knowledge/runs/run-events/events/stream?project_id=project-a", headers=headers)
        other = client.get("/knowledge/runs/run-events/events?project_id=project-b", headers=headers)

        assert [event["sequence"] for event in replay.json()["data"]["events"]] == [1, 2]
        assert "event: knowledge.run.completed" in stream.text
        assert other.status_code == 404
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_horizon_capture_records_unavailable_when_sidecar_is_not_configured(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-horizon.db"))
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.HORIZON_ENABLED", False)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge/horizon/capture",
            headers={"Authorization": "Bearer workspace-admin"},
            json={"project_id": "project-a", "horizon_run_id": "radar-42", "stage": "filtered"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "unavailable"
        assert repo.list_runs("project-a")[0]["run_type"] == "horizon_capture"
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_source_transition_requires_scoped_writer_and_changes_lifecycle(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-transition.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="obsidian_markdown", origin="note.md", raw_content="Review me")
    ).source
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            f"/knowledge/sources/{source['id']}/status",
            headers={"Authorization": "Bearer workspace-admin"},
            json={"project_id": "project-a", "status": "eligible"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["source"]["status"] == "eligible"
    finally:
        settings.API_KEY = previous_key
        app.dependency_overrides.clear()
        repo.close()
