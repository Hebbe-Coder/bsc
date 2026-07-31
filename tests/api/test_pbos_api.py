from fastapi.testclient import TestClient

from app.api import dbos_api
from app.artifacts import MissionArtifact, WorkOutcomeArtifact
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


def test_pbos_outcome_review_updates_the_existing_pending_outcome(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    store = dbos_api.dbos_service_for("personal").store
    store.add(
        MissionArtifact(
            artifact_id="mission-review",
            mission_id="mission-review",
            project_id="personal",
            label="Review evidence",
            title="Review evidence",
        )
    )
    from app.pbos import PBOSService

    service = PBOSService(store, "personal")
    record = service.record_execution(
        "mission-review",
        "",
        {
            "actions": ["Captured a reviewable result."],
            "tool_receipts": [{"kind": "test", "verified": True}],
            "reflection": {"completed": "Ready for explicit review."},
        },
    )
    outcome = service.record_outcome(record.artifact_id, {"acceptance_status": "unverified"})
    client = TestClient(app)

    missing_score = client.post(
        f"/api/pbos/projects/personal/outcomes/{outcome.artifact_id}/review",
        json={"decision": "accepted"},
    )
    response = client.post(
        f"/api/pbos/projects/personal/outcomes/{outcome.artifact_id}/review",
        json={"decision": "accepted", "quality_score": 88, "review_note": "Verified during release review."},
    )

    assert missing_score.status_code == 422
    assert response.status_code == 200
    reviewed = response.json()["outcome"]
    assert reviewed["artifact_id"] == outcome.artifact_id
    assert reviewed["acceptance_status"] == "accepted"
    assert reviewed["quality_score"] == 88
    assert reviewed["review_history"][0]["previous_acceptance_status"] == "unverified"


def test_pbos_outcome_api_rejects_a_duplicate_outcome_for_one_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    store = dbos_api.dbos_service_for("personal").store
    store.add(
        MissionArtifact(
            artifact_id="mission-outcome-uniqueness",
            mission_id="mission-outcome-uniqueness",
            project_id="personal",
            label="Outcome uniqueness",
            title="Outcome uniqueness",
        )
    )
    from app.pbos import PBOSService

    record = PBOSService(store, "personal").record_execution(
        "mission-outcome-uniqueness",
        "",
        {"actions": ["Captured one result."], "reflection": {"completed": "Ready for review."}},
    )
    client = TestClient(app)

    first = client.post(
        f"/api/pbos/projects/personal/executions/{record.artifact_id}/outcomes",
        json={"acceptance_status": "unverified"},
    )
    duplicate = client.post(
        f"/api/pbos/projects/personal/executions/{record.artifact_id}/outcomes",
        json={"acceptance_status": "unverified"},
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert "already has an outcome" in duplicate.json()["message"]


def test_pbos_outcome_review_api_rejects_acceptance_without_verified_execution_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    store = dbos_api.dbos_service_for("personal").store
    store.add(
        MissionArtifact(
            artifact_id="mission-incomplete-review",
            mission_id="mission-incomplete-review",
            project_id="personal",
            label="Incomplete review evidence",
            title="Incomplete review evidence",
        )
    )
    from app.pbos import PBOSService

    service = PBOSService(store, "personal")
    record = service.record_execution(
        "mission-incomplete-review",
        "",
        {
            "actions": ["Captured an unverified manual receipt."],
            "tool_receipts": [{"kind": "manual", "verified": False}],
            "reflection": {"completed": "Receipt verification is still missing."},
        },
    )
    outcome = service.record_outcome(record.artifact_id, {"acceptance_status": "unverified"})

    response = TestClient(app).post(
        f"/api/pbos/projects/personal/outcomes/{outcome.artifact_id}/review",
        json={"decision": "accepted", "quality_score": 91},
    )

    assert response.status_code == 422
    assert "verified_tool_receipt" in response.json()["message"]
    persisted = store.get(outcome.artifact_id)
    assert isinstance(persisted, WorkOutcomeArtifact)
    assert persisted.acceptance_status == "unverified"
