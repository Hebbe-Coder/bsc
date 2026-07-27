from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.capabilities.executor import ExecutionResult
from app.main import app


def test_dbos_api_requires_confirmation_and_projects_real_control_center(monkeypatch, tmp_path):
    from app.api import dbos_api

    async def fake_execute(self, capability, input_text="", project_id=""):
        return ExecutionResult(
            capability_name=capability.name,
            status="success",
            artifacts_produced=[],
            backend="test",
        )

    import app.capabilities as capability_module

    monkeypatch.setattr(capability_module.CapabilityExecutor, "execute", fake_execute)
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")

    from app.promptops import PromptTask
    from app.promptops.service import PromptOps

    def fake_prompt_run(_self, request):
        if request.task != PromptTask.QUALITY_JUDGE:
            raise AssertionError("only the Advisor review should invoke PromptOps in this API test")
        return SimpleNamespace(
            run_id="prompt-api-review",
            provider="test-provider",
            model="test-model",
            agent_manifest=SimpleNamespace(agent_id="dbos_advisor", agent_revision="dbos-advisor-v1"),
            output={
                "verdict": "advisory",
                "summary": "Review the evidence refresh owner before changing spend.",
                "findings": [],
                "open_questions": [],
            },
        )

    monkeypatch.setattr(PromptOps, "run_structured", fake_prompt_run)
    client = TestClient(app)
    payload = {
        "project_id": "dbos-api-project",
        "title": "618 recovery",
        "intake_mode": "business",
        "intent": "Recover ecommerce conversion before 618",
        "context": {
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    }

    created = client.post("/api/dbos/missions", json=payload)
    assert created.status_code == 201
    mission = created.json()["mission"]
    mission_id = mission["artifact_id"]

    listed = client.get("/api/dbos/missions", params={"project_id": payload["project_id"]})
    assert listed.status_code == 200
    assert [item["artifact_id"] for item in listed.json()["missions"]] == [mission_id]

    diagnosed = client.post(f"/api/dbos/missions/{mission_id}/diagnose", params={"project_id": payload["project_id"]})
    assert diagnosed.status_code == 200
    assert diagnosed.json()["sop_routing_evaluation_id"]
    selection = diagnosed.json()["selection"]
    capability = selection["selected"][0]["capability_name"]
    task_id = diagnosed.json()["dynamic_sop"]["phases"][0]["tasks"][0]["task_id"]

    advisor = client.post(
        f"/api/dbos/missions/{mission_id}/advisor-reviews",
        json={"project_id": payload["project_id"], "idempotency_key": "api-advisor-once"},
    )
    assert advisor.status_code == 201
    assert advisor.json()["advisor_review"]["advisor_status"] == "completed"
    assert advisor.json()["advisor_review"]["verdict"] == "advisory"

    decision = client.post(
        f"/api/dbos/missions/{mission_id}/decisions",
        json={
            "project_id": payload["project_id"],
            "task_id": task_id,
            "statement": "Prioritize conversion experiments before paid acquisition.",
            "rationale": "Budget is constrained and conversion is the documented gap.",
            "alternatives": ["Increase paid acquisition"],
            "actor_id": "owner",
        },
    )
    assert decision.status_code == 201

    blocked = client.post(
        f"/api/dbos/missions/{mission_id}/executions",
        json={"project_id": payload["project_id"], "capability_name": capability},
    )
    assert blocked.status_code == 409

    confirmed = client.post(
        f"/api/dbos/missions/{mission_id}/confirm",
        json={"project_id": payload["project_id"], "actor_id": "owner", "authorized_capabilities": [capability]},
    )
    assert confirmed.status_code == 200

    external = client.post(
        f"/api/dbos/missions/{mission_id}/external-workers",
        json={
            "project_id": payload["project_id"],
            "dynamic_sop_id": diagnosed.json()["dynamic_sop"]["artifact_id"],
            "capability_name": capability,
            "worker_id": "research-worker",
            "model_id": "test-model",
            "endpoint": "https://worker.example/run",
            "payload": {"prompt": "must not be sent"},
            "idempotency_key": "external-disabled",
        },
    )
    assert external.status_code == 409
    assert "disabled" in external.text

    executed = client.post(
        f"/api/dbos/missions/{mission_id}/executions",
        json={"project_id": payload["project_id"], "capability_name": capability, "idempotency_key": "api-once"},
    )
    assert executed.status_code == 200
    assert executed.json()["execution_result"]["execution_status"] == "completed"

    reconciled = client.post(
        f"/api/dbos/missions/{mission_id}/verifications/reconcile",
        params={"project_id": payload["project_id"]},
        json={},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["verifications"] == []

    control = client.get(f"/api/dbos/missions/{mission_id}/control-center", params={"project_id": payload["project_id"]})
    assert control.status_code == 200
    assert control.json()["health"]["executions_completed"] == 1
    assert control.json()["health"]["executions_total"] == 1
    assert control.json()["health"]["external_worker_runs_rejected"] == 1
    assert control.json()["health"]["advisor_reviews_completed"] == 1
    assert control.json()["decisions"][0]["metadata"]["task_id"] == task_id
    assert control.json()["sop_routing_evaluation"]["evaluation_status"] == "passed"
    assert control.json()["health"]["sop_routing_holdouts_passed"] is True
    assert control.json()["reasoning_graph"]["nodes"]

    from app.artifacts import ArtifactStatus, ExternalWorkerRunArtifact

    worker = ExternalWorkerRunArtifact(
        project_id=payload["project_id"],
        label="External worker: recovery",
        mission_id=mission_id,
        dynamic_sop_id=diagnosed.json()["dynamic_sop"]["artifact_id"],
        capability_name=capability,
        worker_id="recovery-worker",
        worker_status="executing",
        status=ArtifactStatus.EXECUTING,
        idempotency_key="lost-worker",
    )
    dbos_api.dbos_service_for(payload["project_id"]).store.add(worker)
    cancelled = client.request(
        "DELETE",
        f"/api/dbos/external-workers/{worker.artifact_id}",
        json={"project_id": payload["project_id"], "reason": "Reviewer cancelled the request"},
    )
    assert cancelled.status_code == 202
    assert cancelled.json()["external_worker_run"]["worker_status"] == "interrupted"

    projected = client.get(f"/api/dbos/missions/{mission_id}/control-center", params={"project_id": payload["project_id"]})
    assert projected.status_code == 200
    assert projected.json()["health"]["external_worker_runs_interrupted"] == 1


def test_dbos_service_reopens_the_same_project_ledger_after_a_new_service_instance(monkeypatch, tmp_path):
    from app.api import dbos_api

    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "durable-dbos")
    first = dbos_api.dbos_service_for("durable-project")
    mission = first.create_mission(
        project_id="durable-project",
        title="Persistent Mission",
        intake_mode="business",
        intent="Verify the durable Artifact Graph root.",
        context={"role": "operator", "industry": "services", "goal": "verify persistence"},
    )

    second = dbos_api.dbos_service_for("durable-project")

    assert [item["artifact_id"] for item in second.list_missions()] == [mission.artifact_id]
