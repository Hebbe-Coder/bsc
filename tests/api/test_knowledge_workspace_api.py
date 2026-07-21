from fastapi.testclient import TestClient

from app.api.knowledge_workspace_api import get_wiki_repository
from app.core.config import settings
from app.main import app
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_rules import build_default_agents_rules


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


def test_workspace_api_reports_a_disabled_wiki_feature(monkeypatch):
    previous_key = settings.API_KEY
    settings.API_KEY = "workspace-admin"
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    client = TestClient(app)
    try:
        response = client.get(
            "/knowledge/workspaces/project-a",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 503
        assert response.json()["message"]["code"] == "knowledge_wiki_disabled"
    finally:
        settings.API_KEY = previous_key


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


def test_workspace_admin_operations_are_scoped_and_read_distillation_files(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-operations.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    headers = {"Authorization": "Bearer workspace-admin"}
    try:
        mapping = client.put(
            "/knowledge/workspaces/project-a/vault",
            headers=headers,
            json={"vault_path": "clients/acme"},
        )
        assert mapping.status_code == 200
        assert mapping.json()["data"]["vault"]["vault_path"] == "clients/acme"

        source = SourceCaptureService(repo).capture(
            CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="private evidence")
        ).source
        source_response = client.get(f"/knowledge/sources/{source['id']}?project_id=project-a", headers=headers)
        assert source_response.status_code == 200
        assert "raw_content" not in source_response.json()["data"]["source"]

        captured = client.post(
            "/knowledge/sources/capture",
            headers=headers,
            json={
                "project_id": "project-a", "source_type": "manual_upload", "origin": "interview.txt",
                "raw_content": "Customer confirms approval is required.", "trust_level": "reviewed",
            },
        )
        assert captured.status_code == 200
        assert "raw_content" not in captured.json()["data"]["source"]
        capture_events = repo.list_run_events(project_id="project-a", run_id=captured.json()["data"]["run_id"])
        assert any(event["event_type"] == "knowledge.source.captured" for event in capture_events)

        proposal = client.post(
            "/knowledge/proposals",
            headers=headers,
            json={
                "project_id": "project-a",
                "rationale": "No longer needed",
                "operations": [{"operation": "append", "path": "wiki/log.md", "content": "- rejected\n"}],
            },
        ).json()["data"]["proposal"]
        rejected = client.post(
            f"/knowledge/proposals/{proposal['id']}/reject?project_id=project-a", headers=headers
        )
        assert rejected.status_code == 200
        assert rejected.json()["data"]["proposal"]["status"] == "rejected"

        schedule = repo.upsert_schedule(
            project_id="project-a", job_type="source_sync", cron="*/5 * * * *", timezone_name="UTC", enabled=False, next_run_at=""
        )
        paused = client.patch(
            f"/knowledge/schedules/{schedule['id']}", headers=headers,
            json={"project_id": "project-a", "enabled": False},
        )
        assert paused.status_code == 200
        assert paused.json()["data"]["schedule"]["enabled"] == 0

        vault = FilesystemWikiVault(vault_root, "project-a", "clients/acme")
        paths = [
            "distillations/2026-W30/knowledge-action.md",
            "distillations/2026-W30/content-creation.md",
            "distillations/2026-W30/context-pack.md",
        ]
        vault.commit({path: f"# {path}\n" for path in paths})
        record = repo.record_distillation(
            project_id="project-a", week="2026-W30", paths=paths, source_cutoff="cutoff"
        )
        distillation = client.get(f"/knowledge/distillations/{record['id']}?project_id=project-a", headers=headers)
        assert distillation.status_code == 200
        assert set(distillation.json()["data"]["documents"]) == set(paths)

        failed = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
        repo.create_run(failed)
        repo.update_run_status("project-a", failed.id, RunStatus.FAILED, error="temporary")
        retried = client.post(f"/knowledge/runs/{failed.id}/retry?project_id=project-a", headers=headers)
        assert retried.status_code == 200
        retry_id = retried.json()["data"]["run_id"]
        assert repo.get_run("project-a", retry_id)["retry_of"] == failed.id
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()


def test_workspace_restore_revision_creates_a_scoped_draft_proposal(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "workspace-restore.db"))
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    previous_key = settings.API_KEY
    previous_root = settings.OBSIDIAN_VAULT_ROOT
    settings.API_KEY = "workspace-admin"
    settings.OBSIDIAN_VAULT_ROOT = str(vault_root)
    repo.configure_vault("project-a", "clients/acme")
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="Evidence", trust_level="trusted")
    ).source
    version_one = "---\ntitle: Approval\nkind: concept\n---\nVersion one [source:%s]" % source["id"]
    version_two = "---\ntitle: Approval\nkind: concept\n---\nVersion two [source:%s]" % source["id"]
    contents = {
        "AGENTS.md": build_default_agents_rules("project-a"),
        "wiki/index.md": "# Index\n",
        "wiki/log.md": "# Log\n",
        "wiki/concepts/approval.md": version_one,
    }
    vault = FilesystemWikiVault(vault_root, "project-a", "clients/acme")
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    contents["wiki/concepts/approval.md"] = version_two
    vault.commit(contents)
    repo.record_publication(project_id="project-a", contents=contents, source_ids=[])
    page = next(item for item in repo.list_pages("project-a") if item["path"] == "wiki/concepts/approval.md")
    original = next(item for item in repo.list_page_revisions("project-a", page["id"]) if item["version"] == 1)
    app.dependency_overrides[get_wiki_repository] = lambda: repo
    client = TestClient(app)
    try:
        response = client.post(
            f"/knowledge/wiki/pages/{page['id']}/revisions/{original['id']}/restore?project_id=project-a",
            headers={"Authorization": "Bearer workspace-admin"},
        )

        assert response.status_code == 200
        proposal = response.json()["data"]["proposal"]
        assert proposal["status"] == "draft"
        assert proposal["operations"][0]["content"] == version_one
        assert proposal["source_ids"] == [source["id"]]
    finally:
        settings.API_KEY = previous_key
        settings.OBSIDIAN_VAULT_ROOT = previous_root
        app.dependency_overrides.clear()
        repo.close()
