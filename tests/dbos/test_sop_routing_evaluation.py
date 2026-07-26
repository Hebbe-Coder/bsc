from __future__ import annotations

import pytest

from app.artifacts import ArtifactGraphStore, SOPRoutingEvaluationArtifact
from app.dbos.evaluation import SOPRoutingCase, SOPRoutingEvaluator
from app.dbos.service import DBOSService, MissionStateError


def _service(tmp_path, *, routing_evaluator: SOPRoutingEvaluator | None = None) -> DBOSService:
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    return DBOSService(store=store, routing_evaluator=routing_evaluator)


def _commerce_mission(service: DBOSService):
    return service.create_mission(
        project_id="project-a",
        title="Conversion recovery",
        intake_mode="business",
        intent="Recover ecommerce conversion before a campaign window closes.",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
            "stakeholders": ["merchandising lead"],
            "decision_rights": ["operations director approves spend changes"],
            "evidence": [{
                "source": "trading dashboard",
                "finding": "cart conversion fell 12%",
                "strength": "high",
            }],
        },
    )


def test_dynamic_sop_persists_positive_negative_and_holdout_routing_evidence(tmp_path):
    service = _service(tmp_path)
    mission = _commerce_mission(service)

    flow = service.diagnose_and_compile(mission.artifact_id)
    evaluation = service.store.get(flow.routing_evaluation_id)
    control = service.control_center(mission.artifact_id)

    assert isinstance(evaluation, SOPRoutingEvaluationArtifact)
    assert evaluation.evaluation_status == "passed"
    assert evaluation.positive_case_count == 3
    assert evaluation.near_negative_case_count == 2
    assert evaluation.holdout_case_count == 2
    assert evaluation.holdout_passed is True
    assert all(result.passed for result in evaluation.case_results)
    assert evaluation.parent_ids == [
        mission.artifact_id,
        flow.diagnosis.artifact_id,
        flow.selection.artifact_id,
        flow.sop.artifact_id,
    ]
    assert control["sop_routing_evaluation"]["artifact_id"] == evaluation.artifact_id
    assert control["health"]["sop_routing_evaluation_status"] == "passed"
    assert control["health"]["sop_routing_holdouts_passed"] is True


def test_failed_routing_protocol_blocks_mission_confirmation(tmp_path):
    evaluator = SOPRoutingEvaluator(cases=(SOPRoutingCase(
        case_id="incomplete-protocol",
        split="positive",
        title="General operating review",
        intent="Improve an internal work handoff.",
        context={
            "role": "operations lead",
            "industry": "internal operations",
            "organization_stage": "established",
            "goal": "reduce handoff delays",
        },
        expected_profile="general",
    ),))
    service = _service(tmp_path, routing_evaluator=evaluator)
    mission = _commerce_mission(service)
    flow = service.diagnose_and_compile(mission.artifact_id)

    evaluation = service.store.get(flow.routing_evaluation_id)
    assert isinstance(evaluation, SOPRoutingEvaluationArtifact)
    assert evaluation.evaluation_status == "failed"
    assert "at least three positive cases" in " ".join(evaluation.findings)

    with pytest.raises(MissionStateError, match="routing evaluation must pass"):
        service.confirm(
            mission.artifact_id,
            actor_id="owner",
            authorized_capabilities=[flow.selection.selected_names[0]],
        )


def test_general_routing_does_not_treat_constraints_as_an_ai_product_signal(tmp_path):
    service = _service(tmp_path)
    mission = service.create_mission(
        project_id="project-a",
        title="Handoff review",
        intake_mode="business",
        intent="Improve the internal work handoff rhythm.",
        context={
            "role": "operations lead",
            "industry": "internal operations",
            "organization_stage": "established",
            "goal": "reduce handoff delays",
            "constraints": ["one reviewer per workstream"],
        },
    )

    flow = service.diagnose_and_compile(mission.artifact_id)

    assert flow.selection.metadata["diagnostic_profile"] == "general"
    assert "strategy_analysis" not in flow.selection.selected_names
    assert "general execution system" in flow.sop.title
