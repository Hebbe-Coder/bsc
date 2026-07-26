from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_intake_rest_flow_converts_to_a_confirmation_gated_mission(monkeypatch, tmp_path):
    from app.api import dbos_api

    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    client = TestClient(app)
    project_id = "intake-api-project"
    created = client.post("/api/dbos/intake", json={"project_id": project_id, "request_text": "Build a customer research workflow"})
    assert created.status_code == 201
    intake = created.json()["intake"]
    assert intake["classification"] == "build"
    session_id = intake["artifact_id"]

    while intake["phase"] == "clarifying":
        next_response = client.post(f"/api/dbos/intake/{session_id}/questions/next", json={"project_id": project_id})
        assert next_response.status_code == 200
        question = next_response.json()["question"]
        if question is None:
            break
        answered = client.post(
            f"/api/dbos/intake/{session_id}/answers",
            json={"project_id": project_id, "question_id": question["question_id"], "skipped": True},
        )
        assert answered.status_code == 200
        intake = answered.json()["intake"]

    tier = client.post(f"/api/dbos/intake/{session_id}/tier", json={"project_id": project_id, "tier": "standard"})
    assert tier.status_code == 200
    converted = client.post(f"/api/dbos/intake/{session_id}/convert", json={"project_id": project_id})
    assert converted.status_code == 200
    mission = converted.json()["mission"]
    assert mission["mission_status"] == "ready_for_confirmation"
    assert mission["context"]["intake_session_id"] == session_id

    read = client.get(f"/api/dbos/intake/{session_id}", params={"project_id": project_id})
    assert read.status_code == 200
    assert read.json()["intake"]["linked_mission_id"] == mission["artifact_id"]
    assert client.get(f"/api/dbos/intake/{session_id}", params={"project_id": "another-project"}).status_code == 404


def test_intake_rest_rejects_extra_fields_and_unapproved_handoff(monkeypatch, tmp_path):
    from app.api import dbos_api

    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    client = TestClient(app)
    rejected = client.post("/api/dbos/intake", json={"project_id": "project-a", "request_text": "Build a site", "surprise": True})
    assert rejected.status_code == 422

    created = client.post("/api/dbos/intake", json={"project_id": "project-a", "request_text": "Direct execution: build a site"})
    session_id = created.json()["intake"]["artifact_id"]
    converted = client.post(f"/api/dbos/intake/{session_id}/convert", json={"project_id": "project-a"})
    assert converted.status_code == 200
    handoff = client.post(
        f"/api/dbos/intake/{session_id}/handoff",
        json={"project_id": "project-a", "actor_id": "owner", "approved": False},
    )
    assert handoff.status_code == 422
    assert "explicit approval" in handoff.text
