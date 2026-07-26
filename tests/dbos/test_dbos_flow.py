from __future__ import annotations

import asyncio

import pytest

from app.artifacts import ARTIFACT_CLASS_MAP, ArtifactGraphStore, ArtifactStatus, ExecutionResultArtifact
from app.capabilities.executor import ExecutionResult
from app.dbos.service import DBOSService, MissionNotConfirmedError, MissionStateError, UnauthorizedCapabilityError


def _service(tmp_path):
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    return DBOSService(store=store)


def _record_decision_for_capability(service, mission_id: str, capability_name: str) -> None:
    center = service.control_center(mission_id)
    task = next(
        task
        for phase in center["dynamic_sop"]["phases"]
        for task in phase["tasks"]
        if task["capability_name"] == capability_name
    )
    service.record_decision(
        mission_id,
        task_id=task["task_id"],
        statement=f"Approve {capability_name} for the reviewed task.",
        rationale="The mission owner accepted the task evidence and risk gate.",
        alternatives=[],
        actor_id="owner",
    )


def test_diagnosis_and_dynamic_sop_diverge_by_business_context(tmp_path):
    service = _service(tmp_path)
    ecommerce = service.create_mission(
        project_id="project-a",
        title="618 conversion recovery",
        intake_mode="business",
        intent="618 is in 30 days and conversion has fallen",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore GMV",
            "time_horizon": "30 days",
            "constraints": ["limited budget"],
        },
    )
    career = service.create_mission(
        project_id="project-a",
        title="AI product manager ownership",
        intake_mode="career",
        intent="Become independently responsible for an AI product project",
        context={
            "role": "product manager",
            "industry": "AI SaaS",
            "organization_stage": "new hire",
            "goal": "lead first project",
            "time_horizon": "90 days",
            "constraints": ["limited decision authority"],
        },
    )

    ecommerce_flow = service.diagnose_and_compile(ecommerce.artifact_id)
    career_flow = service.diagnose_and_compile(career.artifact_id)

    assert ecommerce_flow.diagnosis.industry == "ecommerce"
    assert career_flow.diagnosis.role == "product manager"
    assert ecommerce_flow.selection.selected_names != career_flow.selection.selected_names
    assert ecommerce_flow.sop.title != career_flow.sop.title
    assert {task.task_family for phase in ecommerce_flow.sop.phases for task in phase.tasks} != {
        task.task_family for phase in career_flow.sop.phases for task in phase.tasks
    }
    assert ecommerce_flow.sop.parent_ids == [ecommerce_flow.diagnosis.artifact_id, ecommerce_flow.selection.artifact_id]


def test_compiler_composes_profile_specific_work_systems_from_evidence_and_authority(tmp_path):
    service = _service(tmp_path)
    ecommerce = service.create_mission(
        project_id="project-a",
        title="618 conversion recovery",
        intake_mode="business",
        intent="Recover GMV before 618 without increasing acquisition spend.",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion and repeat orders",
            "time_horizon": "30 days",
            "constraints": ["limited campaign budget"],
            "stakeholders": ["merchandising lead", "supply lead"],
            "decision_rights": ["operations director approves spend changes"],
            "evidence": [{
                "source": "weekly trading dashboard",
                "finding": "product-view to cart conversion fell 12% in the last two weeks",
                "strength": "high",
            }],
        },
    )
    product = service.create_mission(
        project_id="project-a",
        title="AI product manager ownership",
        intake_mode="career",
        intent="Lead the first AI feature from user discovery through a reviewed delivery plan.",
        context={
            "role": "AI product manager",
            "industry": "AI SaaS",
            "organization_stage": "new hire",
            "goal": "independently lead the first product decision",
            "time_horizon": "90 days",
            "constraints": ["limited decision authority"],
            "stakeholders": ["product director", "engineering lead"],
            "decision_rights": ["product director approves scope changes"],
            "evidence": [{
                "source": "five customer interviews",
                "finding": "users cannot explain the current AI feature value before activation",
                "strength": "medium",
            }],
        },
    )

    ecommerce_flow = service.diagnose_and_compile(ecommerce.artifact_id)
    product_flow = service.diagnose_and_compile(product.artifact_id)
    ecommerce_capabilities = set(ecommerce_flow.selection.selected_names)
    product_capabilities = set(product_flow.selection.selected_names)
    ecommerce_tasks = "\n".join(task.title for phase in ecommerce_flow.sop.phases for task in phase.tasks)
    product_tasks = "\n".join(task.title for phase in product_flow.sop.phases for task in phase.tasks)

    assert "optimization_recommendations" in ecommerce_capabilities
    assert "strategy_analysis" not in ecommerce_capabilities
    assert "strategy_analysis" in product_capabilities
    assert "optimization_recommendations" not in product_capabilities
    assert "traffic -> product view -> cart -> payment -> repeat order" in ecommerce_tasks
    assert "user problem -> product decision -> delivery milestone -> adoption signal" in product_tasks
    assert ecommerce_flow.diagnosis.evidence_refs == ecommerce_flow.evidence_ids
    assert product_flow.diagnosis.stakeholders == ["product director", "engineering lead"]
    assert ecommerce_flow.sop.quality_gates != product_flow.sop.quality_gates
    assert next(item for item in ecommerce_flow.selection.selected if item.capability_name == "optimization_recommendations").score_components


def test_missing_source_backed_evidence_creates_a_visible_gap_and_validation_workstream(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="unmeasured conversion problem",
        intake_mode="business",
        intent="Improve ecommerce conversion.",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    )

    flow = service.diagnose_and_compile(mission.artifact_id)
    center = service.control_center(mission.artifact_id)

    assert "evidence_validation" in flow.selection.selected_names
    assert center["health"]["evidence_gaps"] >= 1
    assert any("source-backed baseline" in item["gap_statement"] for item in center["gaps"])
    assert any(task.task_family == "evidence_validation" for phase in flow.sop.phases for task in phase.tasks)


def test_missing_context_is_recorded_as_assumptions_and_gaps(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="ambiguous request",
        intake_mode="business",
        intent="Improve execution efficiency",
        context={"role": "team lead"},
    )

    flow = service.diagnose_and_compile(mission.artifact_id)

    assert set(flow.diagnosis.missing_fields) >= {"industry", "goal", "organization_stage"}
    assert flow.assumption_ids
    assert flow.gap_ids


def test_unconfirmed_mission_cannot_execute_and_confirmed_scope_is_enforced(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="recovery",
        intake_mode="business",
        intent="Recover 618 conversion",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability = flow.selection.selected_names[0]
    calls: list[str] = []

    async def executor(name, context):
        calls.append(name)
        return {"effect": "internal analysis complete", "context": context["mission_id"]}

    with pytest.raises(MissionNotConfirmedError):
        asyncio.run(service.execute(mission.artifact_id, capability, executor=executor))
    assert calls == []

    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability])
    with pytest.raises(UnauthorizedCapabilityError):
        asyncio.run(service.execute(mission.artifact_id, "risk_analysis", executor=executor))
    assert calls == []

    with pytest.raises(MissionStateError, match="persisted decision"):
        asyncio.run(service.execute(mission.artifact_id, capability, executor=executor))
    assert calls == []

    _record_decision_for_capability(service, mission.artifact_id, capability)
    result = asyncio.run(service.execute(mission.artifact_id, capability, executor=executor))
    assert result.execution_status == "completed"
    assert calls == [capability]
    assert result.parent_ids[0] == mission.artifact_id


def test_execution_is_idempotent_and_control_center_projects_real_state(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="research delivery",
        intake_mode="business",
        intent="Prepare client delivery",
        context={
            "role": "consultant",
            "industry": "professional services",
            "organization_stage": "delivery",
            "goal": "evidence backed brief",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability = flow.selection.selected_names[0]
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability])
    _record_decision_for_capability(service, mission.artifact_id, capability)

    async def executor(name, context):
        return {"effect": name}

    first = asyncio.run(service.execute(mission.artifact_id, capability, idempotency_key="once", executor=executor))
    second = asyncio.run(service.execute(mission.artifact_id, capability, idempotency_key="once", executor=executor))

    assert first.artifact_id == second.artifact_id
    center = service.control_center(mission.artifact_id)
    assert center["mission"]["mission_status"] == "completed"
    assert center["execution_results"][0]["execution_status"] == "completed"
    assert center["health"]["executions_total"] == 1
    assert center["health"]["executions_completed"] == 1
    assert center["health"]["unresolved_gaps"] == 0
    assert center["reasoning_graph"]["nodes"]


def test_confirmed_mission_stays_open_until_every_granted_capability_has_a_result(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="sequenced recovery",
        intake_mode="business",
        intent="Recover conversion with an evidence-aware operating cadence",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    granted = list(dict.fromkeys(flow.selection.selected_names[:2]))
    assert len(granted) == 2
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=granted)
    for capability in granted:
        _record_decision_for_capability(service, mission.artifact_id, capability)

    asyncio.run(service.execute(mission.artifact_id, granted[0], executor=lambda name, _context: {"effect": name}))
    after_first = service.control_center(mission.artifact_id)
    assert after_first["mission"]["mission_status"] == "confirmed"

    asyncio.run(service.execute(mission.artifact_id, granted[1], executor=lambda name, _context: {"effect": name}))
    after_second = service.control_center(mission.artifact_id)
    assert after_second["mission"]["mission_status"] == "completed"
    assert len(after_second["execution_results"]) == 2


def test_real_execution_fails_when_its_declared_output_contract_is_not_met(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="verified delivery",
        intake_mode="business",
        intent="Produce a reviewable business artifact.",
        context={
            "role": "consultant",
            "industry": "professional services",
            "organization_stage": "delivery",
            "goal": "evidence backed brief",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability = flow.selection.selected_names[0]
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability])
    _record_decision_for_capability(service, mission.artifact_id, capability)

    result = asyncio.run(service.execute(
        mission.artifact_id,
        capability,
        executor=lambda name, _context: ExecutionResult(
            capability_name=name,
            status="success",
            artifacts_produced=["missing-artifact"],
            backend="test",
            mode="api",
        ),
    ))

    assert result.execution_status == "failed"
    assert result.stop_reason == "task_verification_failed"
    center = service.control_center(mission.artifact_id)
    assert center["health"]["executions_verified"] == 0
    assert center["health"]["executions_verification_failed"] == 1
    assert center["verifications"][0]["verification_status"] == "failed"


def test_real_execution_records_a_verified_task_contract_when_artifacts_match(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="verified delivery",
        intake_mode="business",
        intent="Produce a reviewable business artifact.",
        context={
            "role": "consultant",
            "industry": "professional services",
            "organization_stage": "delivery",
            "goal": "evidence backed brief",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability_name = flow.selection.selected_names[0]
    capability = service.registry.get(capability_name)
    assert capability and capability.output_artifact_types
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability_name])
    _record_decision_for_capability(service, mission.artifact_id, capability_name)

    def executor(name, _context):
        artifact_type = capability.output_artifact_types[0]
        artifact = ARTIFACT_CLASS_MAP[artifact_type](
            project_id="project-a",
            label="Verified capability output",
        )
        service.store.add(artifact)
        return ExecutionResult(
            capability_name=name,
            status="success",
            artifacts_produced=[artifact.artifact_id],
            backend="test",
            mode="api",
        )

    result = asyncio.run(service.execute(mission.artifact_id, capability_name, executor=executor))

    assert result.execution_status == "completed"
    center = service.control_center(mission.artifact_id)
    assert center["health"]["executions_verified"] == 1
    assert center["verifications"][0]["verification_status"] == "passed"


def test_historical_provider_execution_is_reconciled_from_persisted_output_ids(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="historical provider execution",
        intake_mode="business",
        intent="Confirm that historic output proof is reconciled without rerunning work.",
        context={
            "role": "consultant",
            "industry": "professional services",
            "organization_stage": "delivery",
            "goal": "reviewable business artifact",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability_name = flow.selection.selected_names[0]
    capability = service.registry.get(capability_name)
    assert capability and capability.output_artifact_types
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability_name])
    output = ARTIFACT_CLASS_MAP[capability.output_artifact_types[0]](
        project_id="project-a",
        label="Historic provider output",
    )
    service.store.add(output)
    legacy = ExecutionResultArtifact(
        project_id="project-a",
        label="Legacy provider execution",
        mission_id=mission.artifact_id,
        dynamic_sop_id=flow.sop.artifact_id,
        capability_name=capability_name,
        execution_id="exec_legacy_verified",
        execution_status="completed",
        status=ArtifactStatus.COMPLETED,
        idempotency_key="legacy-provider-run",
        effects=[{
            "kind": "registered_bsc_capability",
            "capability_name": capability_name,
            "artifact_ids": [output.artifact_id],
            "backend": "nanobot",
            "mode": "api",
        }],
        parent_ids=[mission.artifact_id, flow.sop.artifact_id],
    )
    service.store.add(legacy)

    reconciled = service.reconcile_execution_verifications(mission.artifact_id)

    assert len(reconciled) == 1
    assert reconciled[0].verification_status == "passed"
    assert service.reconcile_execution_verifications(mission.artifact_id) == []
    center = service.control_center(mission.artifact_id)
    assert center["health"]["executions_verified"] == 1
    assert center["health"]["executions_unverified"] == 0


def test_historical_provider_execution_fails_closed_when_outputs_are_missing(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="historic proof gap",
        intake_mode="business",
        intent="Reject a historic provider execution whose output cannot be found.",
        context={
            "role": "consultant",
            "industry": "professional services",
            "organization_stage": "delivery",
            "goal": "reviewable business artifact",
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    capability_name = flow.selection.selected_names[0]
    service.confirm(mission.artifact_id, actor_id="owner", authorized_capabilities=[capability_name])
    legacy = ExecutionResultArtifact(
        project_id="project-a",
        label="Legacy provider execution without output",
        mission_id=mission.artifact_id,
        dynamic_sop_id=flow.sop.artifact_id,
        capability_name=capability_name,
        execution_id="exec_legacy_missing",
        execution_status="completed",
        status=ArtifactStatus.COMPLETED,
        idempotency_key="legacy-provider-missing-output",
        effects=[{
            "kind": "registered_bsc_capability",
            "capability_name": capability_name,
            "artifact_ids": ["missing-artifact"],
            "backend": "nanobot",
            "mode": "api",
        }],
        parent_ids=[mission.artifact_id, flow.sop.artifact_id],
    )
    service.store.add(legacy)

    reconciled = service.reconcile_execution_verifications(mission.artifact_id)

    assert len(reconciled) == 1
    assert reconciled[0].verification_status == "failed"
    assert service.store.get(legacy.artifact_id).execution_status == "failed"
    assert service.get_mission(mission.artifact_id).mission_status == "failed"


def test_stop_and_rollback_are_persisted_as_governance_events(tmp_path):
    service = _service(tmp_path)
    stopped_mission = service.create_mission(
        project_id="project-a",
        title="paused recovery",
        intake_mode="business",
        intent="Recover conversion without external changes.",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    )
    stopped_flow = service.diagnose_and_compile(stopped_mission.artifact_id)
    stopped_capability = stopped_flow.selection.selected_names[0]
    service.confirm(stopped_mission.artifact_id, actor_id="owner", authorized_capabilities=[stopped_capability])

    stopped = service.execution_service.stop(
        service.get_mission(stopped_mission.artifact_id),
        "Owner paused the mission after a changed operating constraint.",
    )

    assert stopped.mission_status == "stopped"
    assert stopped.authorization["stop_reason"].startswith("Owner paused")

    rollback_mission = service.create_mission(
        project_id="project-a",
        title="rollback recovery",
        intake_mode="business",
        intent="Recover conversion with a bounded internal analysis.",
        context={
            "role": "operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
        },
    )
    rollback_flow = service.diagnose_and_compile(rollback_mission.artifact_id)
    capability = rollback_flow.selection.selected_names[0]
    service.confirm(rollback_mission.artifact_id, actor_id="owner", authorized_capabilities=[capability])
    _record_decision_for_capability(service, rollback_mission.artifact_id, capability)
    execution = asyncio.run(service.execute(
        rollback_mission.artifact_id,
        capability,
        executor=lambda name, _context: {"effect": f"{name} completed"},
    ))

    rolled_back = service.execution_service.rollback(execution, "Reviewer rejected the outcome for revision.")
    center = service.control_center(rollback_mission.artifact_id)

    assert rolled_back.execution_status == "rolled_back"
    assert rolled_back.rollback["reason"].startswith("Reviewer rejected")
    assert center["mission"]["mission_status"] == "rolled_back"
    assert center["execution_results"][0]["execution_status"] == "rolled_back"
