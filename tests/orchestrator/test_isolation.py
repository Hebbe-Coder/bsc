from fastapi.testclient import TestClient

from app.agent.state import ProjectDraftRepository
from app.core.config import settings
from app.main import app


def _enable_auth(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-key-123")
    monkeypatch.setattr(settings, "BSC_RUNTIME_MODE", "legacy")


def _block_legacy_pipeline(monkeypatch):
    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline", blocked_run
    )


def test_orchestrator_uses_signed_same_origin_session_for_follow_up(monkeypatch):
    _enable_auth(monkeypatch)
    _block_legacy_pipeline(monkeypatch)
    client = TestClient(app)

    created = client.post(
        "/api/orchestrate",
        json={"idea": "secure session", "project_id": "project-a"},
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert created.status_code == 202
    assert "httponly" in created.headers["set-cookie"].lower()
    session_id = created.json()["session_id"]
    follow_up = client.get(f"/api/orchestrate/{session_id}")

    assert follow_up.status_code == 200
    assert follow_up.json()["project_id"] == "project-a"


def test_orchestrator_rejects_cross_browser_session_access(monkeypatch):
    _enable_auth(monkeypatch)
    _block_legacy_pipeline(monkeypatch)
    owner = TestClient(app)
    created = owner.post(
        "/api/orchestrate",
        json={"idea": "private execution", "project_id": "project-a"},
        headers={"Authorization": "Bearer test-key-123"},
    )
    assert created.status_code == 202
    session_id = created.json()["session_id"]

    other_browser = TestClient(app)
    denied = other_browser.get(
        f"/api/orchestrate/{session_id}",
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert denied.status_code == 404


def test_project_key_cannot_select_or_read_another_project(monkeypatch):
    from app.middleware import auth

    _block_legacy_pipeline(monkeypatch)

    def fake_project_auth(key, repo=None):
        mapping = {
            "project-a-key": ("project_admin", "project-a"),
            "project-b-key": ("project_admin", "project-b"),
        }
        return mapping.get(key)

    monkeypatch.setattr(auth, "resolve_knowledge_auth", fake_project_auth)
    client_a = TestClient(app)
    wrong_project = client_a.post(
        "/api/orchestrate",
        json={"idea": "wrong project", "project_id": "project-b"},
        headers={"Authorization": "Bearer project-a-key"},
    )
    assert wrong_project.status_code == 403

    created = client_a.post(
        "/api/orchestrate",
        json={"idea": "bound project"},
        headers={"Authorization": "Bearer project-a-key"},
    )
    assert created.status_code == 202
    session_id = created.json()["session_id"]
    draft = ProjectDraftRepository().get(session_id)
    assert draft is not None
    assert draft.project_id == "project-a"
    assert draft.tenant_id == settings.DEFAULT_TENANT_ID
    assert draft.owner_session_id

    client_b = TestClient(app)
    denied = client_b.get(
        f"/api/orchestrate/{session_id}",
        headers={"Authorization": "Bearer project-b-key"},
    )
    assert denied.status_code == 404
