from __future__ import annotations

import asyncio

import pytest

from app.api.dbos_api import recover_dbos_runs_on_startup
from app.artifacts import (
    ArtifactGraphStore,
    ArtifactStatus,
    ArtifactType,
    ExternalWorkerRunArtifact,
    ExecutionResultArtifact,
    RunCheckpointArtifact,
    RuntimeContextArtifact,
)
from app.dbos.execution import ManualRetryRequiredError
from app.dbos.service import DBOSService


def _service(tmp_path, *, root_name: str = "artifacts") -> DBOSService:
    store = ArtifactGraphStore(
        str(tmp_path / root_name),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    return DBOSService(store=store)


def _prepared_mission(service: DBOSService):
    mission = service.create_mission(
        project_id="project-a",
        title="Conversion recovery",
        intake_mode="business",
        intent="Recover ecommerce conversion from the private weekly trading report.",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
            "constraints": ["limited budget"],
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability = flow.selection.selected_names[0]
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability])
    return mission, flow, capability


def test_diagnosis_persists_redacted_context_manifest(tmp_path):
    service = _service(tmp_path)
    mission, flow, _ = _prepared_mission(service)

    snapshot = service.store.get(flow.context_snapshot_id)

    assert isinstance(snapshot, RuntimeContextArtifact)
    assert snapshot.mission_id == mission.artifact_id
    assert snapshot.redacted is True
    assert "industry" in snapshot.context_fields
    assert snapshot.estimated_tokens > 0
    assert mission.intent not in snapshot.model_dump_json()
    center = service.control_center(mission.artifact_id)
    assert center["runtime_context"]["artifact_id"] == snapshot.artifact_id
    assert snapshot.artifact_id in {node["id"] for node in center["reasoning_graph"]["nodes"]}


def test_recovery_marks_execution_interrupted_and_requires_explicit_manual_retry(tmp_path):
    service = _service(tmp_path)
    mission, flow, capability = _prepared_mission(service)
    task = next(
        task
        for phase in flow.sop.phases
        for task in phase.tasks
        if task.capability_name == capability
    )
    service.record_decision(
        mission.artifact_id,
        task_id=task.task_id,
        statement="Retry only after the interrupted runtime has been reviewed.",
        rationale="The restart left the capability outcome unknown.",
        alternatives=[],
        actor_id="owner",
    )
    confirmed = service.get_mission(mission.artifact_id)
    service.store.update(confirmed.model_copy(update={
        "mission_status": "executing",
        "status": ArtifactStatus.EXECUTING,
    }))
    interrupted = ExecutionResultArtifact(
        project_id="project-a",
        label="Execution: interrupted capability",
        mission_id=mission.artifact_id,
        dynamic_sop_id=flow.sop.artifact_id,
        capability_name=capability,
        execution_id="exec_interrupted",
        execution_status="executing",
        attempt=1,
        idempotency_key="crash-key",
        context_snapshot_id=flow.context_snapshot_id,
        parent_ids=[mission.artifact_id, flow.sop.artifact_id, flow.context_snapshot_id],
        status=ArtifactStatus.EXECUTING,
        source_agent="test",
    )
    service.store.add(interrupted)

    recovered = service.recover_interrupted_executions()

    assert [item.artifact_id for item in recovered] == [interrupted.artifact_id]
    recovered_execution = service.store.get(interrupted.artifact_id)
    assert isinstance(recovered_execution, ExecutionResultArtifact)
    assert recovered_execution.execution_status == "interrupted"
    assert recovered_execution.stop_reason == "process_restart_manual_retry_required"
    assert service.get_mission(mission.artifact_id).mission_status == "confirmed"
    checkpoints = service.store.get_by_type(ArtifactType.RUN_CHECKPOINT)
    assert any(
        isinstance(item, RunCheckpointArtifact)
        and item.execution_id == interrupted.artifact_id
        and item.checkpoint_status == "interrupted"
        for item in checkpoints
    )

    with pytest.raises(ManualRetryRequiredError):
        asyncio.run(service.execute(mission.artifact_id, capability, idempotency_key="crash-key"))

    retried = asyncio.run(service.execute(
        mission.artifact_id,
        capability,
        idempotency_key="operator-approved-retry",
        executor=lambda _name, _context: {"effect": "manual retry completed"},
    ))
    assert retried.execution_status == "completed"
    assert retried.attempt == 2


def test_startup_recovery_scans_project_ledgers_without_dispatching_capabilities(tmp_path):
    root = tmp_path / "dbos"
    service = _service(root / "tenant-a" / "project-a", root_name=".")
    mission, flow, capability = _prepared_mission(service)
    service.store.update(service.get_mission(mission.artifact_id).model_copy(update={
        "mission_status": "executing",
        "status": ArtifactStatus.EXECUTING,
    }))
    execution = ExecutionResultArtifact(
        project_id="project-a",
        label="Execution: startup recovery",
        mission_id=mission.artifact_id,
        dynamic_sop_id=flow.sop.artifact_id,
        capability_name=capability,
        execution_id="exec_startup_recovery",
        execution_status="executing",
        idempotency_key="startup-crash",
        context_snapshot_id=flow.context_snapshot_id,
        parent_ids=[mission.artifact_id, flow.sop.artifact_id, flow.context_snapshot_id],
        status=ArtifactStatus.EXECUTING,
        source_agent="test",
    )
    service.store.add(execution)
    external = ExternalWorkerRunArtifact(
        project_id="project-a",
        label="External worker: startup recovery",
        mission_id=mission.artifact_id,
        dynamic_sop_id=flow.sop.artifact_id,
        capability_name=capability,
        worker_id="recovery-worker",
        worker_status="executing",
        idempotency_key="external-startup-crash",
        status=ArtifactStatus.EXECUTING,
        parent_ids=[mission.artifact_id, flow.sop.artifact_id],
    )
    service.store.add(external)

    recovered_ids = recover_dbos_runs_on_startup(root)

    assert set(recovered_ids) == {execution.artifact_id, external.artifact_id}
    persisted = service.store.get(execution.artifact_id)
    assert isinstance(persisted, ExecutionResultArtifact)
    assert persisted.execution_status == "interrupted"
    persisted_external = service.store.get(external.artifact_id)
    assert isinstance(persisted_external, ExternalWorkerRunArtifact)
    assert persisted_external.worker_status == "interrupted"
    assert "not automatically replay" in persisted_external.reason
