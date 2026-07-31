from fastapi.testclient import TestClient

from app.api import dbos_api
from app.artifacts import MissionArtifact
from app.core.config import settings
from app.main import app


def _mission(project_id: str, mission_id: str, title: str) -> None:
    dbos_api.dbos_service_for(project_id).store.add(
        MissionArtifact(
            artifact_id=mission_id,
            mission_id=mission_id,
            project_id=project_id,
            label=title,
            title=title,
            intent=title,
        )
    )


def test_personal_ai_delivery_loop_retains_evidence_gates(monkeypatch, tmp_path):
    project_id = "personal"
    vault = tmp_path / "vault"
    context_path = vault / "projects" / project_id / "03_Projects" / "active" / "runtime.md"
    context_path.parent.mkdir(parents=True)
    context_path.write_text("# Runtime constraint\nFreeze the API contract before widening scope.", encoding="utf-8")
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault))
    monkeypatch.setattr(settings, "SOP_LLM_PROVIDER", "mock")
    _mission(project_id, "mission-one", "Validate the first PBOS delivery loop")
    _mission(project_id, "mission-two", "Compile the next delivery plan")
    client = TestClient(app)

    profile = client.put(
        f"/api/pbos/projects/{project_id}/profile",
        json={
            "focus": ["AI project delivery"],
            "resources": ["Obsidian", "BSC"],
            "constraints": ["Solo delivery"],
            "preferences": {"evidence_first": True},
        },
    )
    assert profile.status_code == 200

    plan = client.post(f"/api/pbos/projects/{project_id}/missions/mission-one/plans")
    assert plan.status_code == 200
    plan_body = plan.json()["plan"]
    assert plan_body["knowledge_context_refs"] == ["vault:03_Projects/active/runtime.md"]

    execution = client.post(
        f"/api/pbos/projects/{project_id}/missions/mission-one/capture-bsc-workspace",
        json={
            "plan_id": plan_body["artifact_id"],
            "paths": ["tests/integration/test_pbos_e2e.py"],
            "actions": ["Ran the focused PBOS regression suite."],
            "reflection": {"completed": "The contract was validated.", "blocker": "Need an accepted delivery review."},
        },
    )
    assert execution.status_code == 200

    outcome = client.post(
        f"/api/pbos/projects/{project_id}/executions/{execution.json()['execution']['artifact_id']}/outcomes",
        json={"acceptance_status": "unverified", "metrics": {"tests_passed": True}},
    )
    assert outcome.status_code == 200

    review = client.post(
        f"/api/pbos/projects/{project_id}/outcomes/{outcome.json()['outcome']['artifact_id']}/review",
        json={"decision": "accepted", "quality_score": 88, "review_note": "Verified against the execution receipt."},
    )
    assert review.status_code == 200
    assert review.json()["outcome"]["acceptance_status"] == "accepted"

    feedback = client.post(
        f"/api/pbos/projects/{project_id}/outcomes/{outcome.json()['outcome']['artifact_id']}/feedback",
        json={"source": "three_minute_reflection", "statement": "Keep the API contract frozen before expanding scope."},
    )
    assert feedback.status_code == 200

    next_plan = client.post(f"/api/pbos/projects/{project_id}/missions/mission-two/plans")
    assert next_plan.status_code == 200
    assert feedback.json()["feedback"]["artifact_id"] in next_plan.json()["plan"]["feedback_refs"]

    evolution = client.post(f"/api/pbos/projects/{project_id}/evolution/reconcile")
    assert evolution.status_code == 200
    assert evolution.json()["state"] == "insufficient_evidence"

    cockpit = client.get(f"/api/pbos/projects/{project_id}/cockpit")
    assert cockpit.status_code == 200
    assert cockpit.json()["capabilities"] == []
    assert cockpit.json()["connectors"] == {
        "github": "awaiting_authorization",
        "feishu": "awaiting_authorization",
    }
