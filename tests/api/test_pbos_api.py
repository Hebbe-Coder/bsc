from fastapi.testclient import TestClient

from app.api import dbos_api
from app.artifacts import MissionArtifact
from app.core.config import settings
from app.main import app


def test_pbos_feedback_rejects_an_outcome_outside_the_project(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    client = TestClient(app)

    response = client.post(
        "/api/pbos/projects/personal/outcomes/missing-outcome/feedback",
        json={"statement": "Need evidence before approval."},
    )

    assert response.status_code == 404
    assert "outcome record not found" in response.text


def test_pbos_plan_api_uses_project_vault_context(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(tmp_path / "vault"))
    monkeypatch.setattr(settings, "SOP_LLM_PROVIDER", "mock")
    project_root = tmp_path / "vault" / "projects" / "personal" / "03_Projects" / "active"
    project_root.mkdir(parents=True)
    (project_root / "context.md").write_text("# Runtime boundary\nFreeze contracts before widening scope.", encoding="utf-8")
    store = dbos_api.dbos_service_for("personal").store
    mission = MissionArtifact(
        artifact_id="mission-context",
        mission_id="mission-context",
        project_id="personal",
        label="Runtime delivery",
        title="Runtime delivery",
        intent="Deliver the Agent runtime evidence loop",
    )
    store.add(mission)
    client = TestClient(app)

    profile = client.put(
        "/api/pbos/projects/personal/profile",
        json={"focus": ["AI systems"], "preferences": {"architecture_first": True}},
    )
    plan = client.post("/api/pbos/projects/personal/missions/mission-context/plans")

    assert profile.status_code == 200
    assert plan.status_code == 200
    payload = plan.json()["plan"]
    assert payload["compilation_state"] == "context_grounded"
    assert payload["knowledge_context_refs"] == ["vault:03_Projects/active/context.md"]
    assert payload["compiler_metadata"]["mode"] == "contextual_deterministic"

    action = client.get("/api/pbos/projects/personal/today-action")

    assert action.status_code == 200
    assert action.json()["state"] == "recommended"
    assert action.json()["plan_id"] == payload["artifact_id"]
    assert action.json()["knowledge_context_refs"] == ["vault:03_Projects/active/context.md"]

    cockpit = client.get("/api/pbos/projects/personal/cockpit")

    assert cockpit.status_code == 200
    health = cockpit.json()["project_health"]
    assert health["knowledge_context_ready"] is True
    assert health["knowledge_context_reference_count"] == 1
    assert health["personal_learning_ready"] is False


def test_pbos_workspace_capture_records_one_execution_with_safe_receipt_and_reflection(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    store = dbos_api.dbos_service_for("personal").store
    store.add(
        MissionArtifact(
            artifact_id="mission-capture",
            mission_id="mission-capture",
            project_id="personal",
            label="Capture evidence",
            title="Capture evidence",
        )
    )
    client = TestClient(app)

    captured = client.post(
        "/api/pbos/projects/personal/missions/mission-capture/capture-bsc-workspace",
        json={
            "paths": ["tests/api/test_pbos_api.py"],
            "actions": ["Ran the project-scoped capture path."],
            "reflection": {"completed": "The receipt is attached to this execution."},
        },
    )
    unsafe = client.post(
        "/api/pbos/projects/personal/missions/mission-capture/capture-bsc-workspace",
        json={"paths": [".env"]},
    )

    assert captured.status_code == 200
    execution = captured.json()["execution"]
    assert execution["reflection"]["completed"] == "The receipt is attached to this execution."
    assert any(
        receipt["kind"] == "local_file" and receipt["path"] == "tests/api/test_pbos_api.py"
        for receipt in execution["tool_receipts"]
    )
    assert unsafe.status_code == 422

    manual = client.post(
        "/api/pbos/projects/personal/missions/mission-capture/executions",
        json={
            "actions": ["A client-submitted note."],
            "tool_receipts": [{"kind": "client_claim", "verified": True}],
            "reflection": {"completed": "No server capture occurred."},
        },
    )

    assert manual.status_code == 200
    assert manual.json()["execution"]["tool_receipts"][0]["verified"] is False
