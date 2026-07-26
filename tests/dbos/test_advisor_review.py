from __future__ import annotations

from types import SimpleNamespace

from app.artifacts import ArtifactGraphStore
from app.dbos.advisor import MissionAdvisor
from app.dbos.service import DBOSService
from app.promptops import PromptOpsError, PromptTask


class _PromptOpsStub:
    def __init__(self, output=None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(
            run_id="prompt-review-1",
            provider="test-provider",
            model="test-model",
            agent_manifest=SimpleNamespace(agent_id="dbos_advisor", agent_revision="dbos-advisor-v1"),
            output=self.output,
        )


def _service(tmp_path, promptops: _PromptOpsStub) -> DBOSService:
    store = ArtifactGraphStore(
        str(tmp_path / "artifacts"),
        tenant_id="tenant-a",
        project_id="project-a",
        session_id="dbos",
    )
    return DBOSService(store=store, advisor=MissionAdvisor(promptops))


def _diagnosed_mission(service: DBOSService):
    mission = service.create_mission(
        project_id="project-a",
        title="Conversion recovery",
        intake_mode="business",
        intent="Restore ecommerce conversion before the campaign window.",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
            "time_horizon": "30 days",
            "constraints": ["fixed acquisition budget"],
            "evidence": [{
                "source": "weekly trading dashboard",
                "finding": "cart conversion fell by 12 percent",
                "strength": "high",
            }],
        },
    )
    flow = service.diagnose_and_compile(mission.artifact_id)
    return mission, flow


def test_advisor_review_is_structured_idempotent_and_has_no_authority(tmp_path):
    stub = _PromptOpsStub()
    service = _service(tmp_path, stub)
    mission, flow = _diagnosed_mission(service)
    evidence_id = flow.evidence_ids[0]
    stub.output = {
        "verdict": "needs_attention",
        "summary": "The conversion claim has a bounded source but no owner for the evidence refresh.",
        "findings": [{
            "severity": "medium",
            "category": "evidence",
            "statement": "Refresh the conversion baseline before budget changes.",
            "recommendation": "Assign an owner and review date.",
            "evidence_refs": [evidence_id],
        }],
        "open_questions": ["Who accepts the refreshed baseline?"],
    }

    before = service.get_mission(mission.artifact_id)
    first = service.review_mission(mission.artifact_id, idempotency_key="advisor-once")
    second = service.review_mission(mission.artifact_id, idempotency_key="advisor-once")
    after = service.get_mission(mission.artifact_id)
    center = service.control_center(mission.artifact_id)

    assert first.artifact_id == second.artifact_id
    assert len(stub.requests) == 1
    assert first.advisor_status == "completed"
    assert first.verdict == "needs_attention"
    assert first.findings[0].evidence_refs == [evidence_id]
    assert first.mission_id == mission.artifact_id
    assert first.dynamic_sop_id == flow.sop.artifact_id
    assert before.authorization == after.authorization
    assert before.mission_status == after.mission_status == "ready_for_confirmation"
    assert stub.requests[0].task == PromptTask.QUALITY_JUDGE
    assert stub.requests[0].agent_definition is not None
    assert stub.requests[0].agent_definition.external_side_effects_allowed is False
    assert center["health"]["advisor_reviews_completed"] == 1
    assert center["health"]["advisor_findings_open"] == 1
    assert center["advisor_reviews"][0]["artifact_id"] == first.artifact_id


def test_advisor_review_rejects_unadmitted_references_without_claiming_success(tmp_path):
    stub = _PromptOpsStub({
        "verdict": "advisory",
        "summary": "The plan needs a stronger source.",
        "findings": [{
            "severity": "high",
            "category": "evidence",
            "statement": "Unsupported reference.",
            "recommendation": "Use an admitted source.",
            "evidence_refs": ["art_not_admitted"],
        }],
        "open_questions": [],
    })
    service = _service(tmp_path, stub)
    mission, _ = _diagnosed_mission(service)

    review = service.review_mission(mission.artifact_id, idempotency_key="advisor-invalid")

    assert review.advisor_status == "failed"
    assert review.verdict == "invalid_response"
    assert review.error_category == "structured_response_invalid"
    assert not review.findings


def test_advisor_review_records_provider_unavailability_instead_of_inventing_a_review(tmp_path):
    stub = _PromptOpsStub(error=PromptOpsError("provider_not_configured"))
    service = _service(tmp_path, stub)
    mission, _ = _diagnosed_mission(service)

    review = service.review_mission(mission.artifact_id, idempotency_key="advisor-unavailable")

    assert review.advisor_status == "unavailable"
    assert review.verdict == "unavailable"
    assert review.error_category == "provider_not_configured"
    assert not review.findings
