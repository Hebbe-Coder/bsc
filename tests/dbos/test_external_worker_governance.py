from __future__ import annotations

import asyncio
import json
from threading import Event
import time

import pytest
import httpx

from app.artifacts import (
    ArtifactGraphStore,
    ArtifactStatus,
    ArtifactType,
    DecisionArtifact,
    DeliverableArtifact,
    ExternalWorkerRunArtifact,
    MissionArtifact,
)
from app.dbos.external_worker import ExternalWorkerPolicyError, ExternalWorkerResponse, ExternalWorkerService
from app.dbos.service import DBOSService
from app.knowledge.growth_contracts import ExternalWorkerPolicy, ProjectKnowledgeProfile
from app.knowledge.growth_repository import GrowthRepository


def _setup(tmp_path, *, enabled: bool) -> tuple[ArtifactGraphStore, GrowthRepository, MissionArtifact]:
    store = ArtifactGraphStore(str(tmp_path / "artifacts"), tenant_id="tenant-a", project_id="project-a", session_id="dbos")
    repo = GrowthRepository(db_path=str(tmp_path / "growth.db"))
    policy = ExternalWorkerPolicy(
        enabled=enabled,
        worker_ids=["research-worker"] if enabled else [],
        allowed_model_ids=["test-model"] if enabled else [],
        allowed_https_hosts=["worker.example"] if enabled else [],
        allowed_capabilities=["sop_design"] if enabled else [],
        credential_ref="test_worker" if enabled else "",
        allowed_environments=["test"],
        max_calls=4 if enabled else 0,
        max_cost_microusd=1000 if enabled else 0,
    )
    repo.save_profile(ProjectKnowledgeProfile(project_id="project-a", external_worker_policy=policy), actor_id="owner")
    mission = MissionArtifact(
        project_id="project-a",
        label="Approved mission",
        mission_status="confirmed",
        status=ArtifactStatus.CONFIRMED,
        authorization={"authorized_capabilities": ["sop_design"]},
    )
    store.add(mission)
    store.add(DecisionArtifact(
        project_id="project-a",
        label="Approve external worker",
        parent_ids=[mission.artifact_id],
        metadata={"dynamic_sop_id": "sop-a", "capability_name": "sop_design"},
    ))
    return store, repo, mission


def _kwargs(mission: MissionArtifact, **overrides):
    values = {
        "mission_id": mission.artifact_id,
        "dynamic_sop_id": "sop-a",
        "capability_name": "sop_design",
        "worker_id": "research-worker",
        "model_id": "test-model",
        "endpoint": "https://worker.example/run",
        "payload": {},
        "idempotency_key": "worker-run",
    }
    values.update(overrides)
    return values


def test_external_worker_is_fail_closed_by_default_and_persists_rejection(tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=False)
    service = ExternalWorkerService(store, repo, environment="test")

    with pytest.raises(ExternalWorkerPolicyError, match="disabled"):
        service.start(**_kwargs(mission, payload={"prompt": "private"}, idempotency_key="disabled-1"))

    ledger = store.get_by_type(ArtifactType.EXTERNAL_WORKER_RUN)
    assert len(ledger) == 1
    assert ledger[0].worker_status == "rejected"
    assert ledger[0].input_fingerprint and "private" not in ledger[0].model_dump_json()
    center = DBOSService(store=store).control_center(mission.artifact_id)
    assert center["health"]["external_worker_runs_rejected"] == 1
    assert center["external_worker_runs"][0]["worker_status"] == "rejected"


def test_external_worker_uses_server_secret_requires_project_output_and_is_idempotent(monkeypatch, tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    output = DeliverableArtifact(project_id="project-a", label="Research result", kind="research")
    store.add(output)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")
    service = ExternalWorkerService(store, repo, environment="test")
    seen = {}

    async def transport(endpoint, body, secret, timeout):
        seen.update({"endpoint": endpoint, "body": body, "secret": secret, "timeout": timeout})
        return ExternalWorkerResponse(output_artifact_ids=[output.artifact_id], estimated_cost_microusd=125)

    result = asyncio.run(service.execute(**_kwargs(mission, payload={"prompt": "sensitive"}, idempotency_key="approved-1"), estimated_cost_microusd=125, transport=transport))

    assert result.worker_status == "completed"
    assert result.output_artifact_ids == [output.artifact_id]
    assert result.credential_ref == "test_worker"
    assert result.model_id == "test-model"
    assert "server-only-value" not in result.model_dump_json()
    assert seen["secret"] == "server-only-value"
    assert asyncio.run(service.execute(**_kwargs(mission, payload={"prompt": "different"}, idempotency_key="approved-1"), transport=transport)).artifact_id == result.artifact_id


def test_default_https_transport_posts_a_redacted_contract_to_the_nonproduction_worker(monkeypatch, tmp_path):
    import app.dbos.external_worker as external_worker

    store, repo, mission = _setup(tmp_path, enabled=True)
    output = DeliverableArtifact(project_id="project-a", label="HTTP worker output", kind="research")
    store.add(output)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"output_artifact_ids": [output.artifact_id], "estimated_cost_microusd": 25})

    monkeypatch.setattr(
        external_worker,
        "_HTTP_CLIENT_FACTORY",
        lambda timeout: httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(handler), trust_env=False),
    )
    result = asyncio.run(ExternalWorkerService(store, repo, environment="test").execute(
        **_kwargs(mission, payload={"task": "build a cited research brief"}, idempotency_key="http-contract-1"),
    ))

    assert result.worker_status == "completed"
    assert result.output_artifact_ids == [output.artifact_id]
    assert seen["url"] == "https://worker.example/run"
    assert seen["auth"] == "Bearer server-only-value"
    assert seen["payload"] == {"input": {"task": "build a cited research brief"}, "model_id": "test-model"}
    assert "server-only-value" not in result.model_dump_json()


def test_two_worker_failures_escalate_without_claiming_success(monkeypatch, tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")
    service = ExternalWorkerService(store, repo, environment="test")

    async def fail(*_args):
        raise TimeoutError("upstream timed out")

    first = asyncio.run(service.execute(**_kwargs(mission, idempotency_key="failure-1"), transport=fail))
    second = asyncio.run(service.execute(**_kwargs(mission, idempotency_key="failure-2"), transport=fail))

    assert first.worker_status == "failed" and first.escalated is False
    assert second.worker_status == "failed" and second.escalated is True
    assert second.status == ArtifactStatus.FAILED


def test_worker_reported_cost_cannot_exceed_project_budget(monkeypatch, tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")
    service = ExternalWorkerService(store, repo, environment="test")

    async def over_budget(*_args):
        return ExternalWorkerResponse(output_artifact_ids=[], estimated_cost_microusd=1001)

    result = asyncio.run(service.execute(**_kwargs(mission, idempotency_key="over-budget"), estimated_cost_microusd=1, transport=over_budget))

    assert result.worker_status == "failed"
    assert result.estimated_cost_microusd == 1001
    assert "budget" in result.reason


def test_worker_cannot_complete_without_a_bsc_owned_output_artifact(monkeypatch, tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")

    async def missing_output(*_args):
        return ExternalWorkerResponse(output_artifact_ids=[], estimated_cost_microusd=1)

    result = asyncio.run(ExternalWorkerService(store, repo, environment="test").execute(
        **_kwargs(mission, idempotency_key="missing-output"), transport=missing_output,
    ))

    assert result.worker_status == "failed"
    assert "did not identify" in result.reason


def test_queued_worker_cancellation_interrupts_the_transport_before_a_response(monkeypatch, tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    monkeypatch.setenv("BSC_EXTERNAL_WORKER_SECRET_TEST_WORKER", "server-only-value")
    service = ExternalWorkerService(store, repo, environment="test")
    transport_entered = Event()
    transport_cancelled = Event()

    async def blocking_transport(*_args):
        transport_entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            transport_cancelled.set()
            raise

    queued = service.start(**_kwargs(mission, idempotency_key="cancel-1"), transport=blocking_transport)
    assert queued.worker_status == "queued"
    assert transport_entered.wait(timeout=2), "isolated worker did not start its transport"

    requested = service.request_cancel(queued.artifact_id, reason="Reviewer withdrew outbound approval")
    assert requested.worker_status == "cancellation_requested"

    deadline = time.monotonic() + 2
    terminal = store.get(queued.artifact_id)
    while isinstance(terminal, ExternalWorkerRunArtifact) and terminal.worker_status not in {"cancelled", "interrupted"} and time.monotonic() < deadline:
        time.sleep(0.01)
        terminal = store.get(queued.artifact_id)

    assert transport_cancelled.is_set(), "cancel signal did not reach the active transport task"
    assert isinstance(terminal, ExternalWorkerRunArtifact)
    assert terminal.worker_status == "cancelled"
    assert terminal.cancellation_requested_at
    assert terminal.cancelled_at
    assert terminal.outbound_started_at
    assert terminal.status == ArtifactStatus.CANCELLED


def test_restart_recovery_marks_unfinished_worker_interrupted_without_replay(tmp_path):
    store, repo, mission = _setup(tmp_path, enabled=True)
    pending = ExternalWorkerRunArtifact(
        project_id="project-a",
        label="External worker: research-worker",
        mission_id=mission.artifact_id,
        dynamic_sop_id="sop-a",
        capability_name="sop_design",
        worker_id="research-worker",
        worker_status="executing",
        status=ArtifactStatus.EXECUTING,
        idempotency_key="crash-1",
    )
    store.add(pending)

    recovered = ExternalWorkerService(store, repo, environment="test").recover_interrupted()
    restored = store.get(pending.artifact_id)

    assert [item.artifact_id for item in recovered] == [pending.artifact_id]
    assert isinstance(restored, ExternalWorkerRunArtifact)
    assert restored.worker_status == "interrupted"
    assert restored.status == ArtifactStatus.INTERRUPTED
    assert restored.recovered_at
    assert "not automatically replay" in restored.reason
