from __future__ import annotations

import asyncio

import pytest

from app.artifacts import ArtifactGraphStore, AssumptionArtifact, GapArtifact
from app.dbos.execution import MissionNotConfirmedError
from app.dbos.intake import IntakeError
from app.dbos.service import DBOSService


def _service(tmp_path) -> DBOSService:
    return DBOSService(store=ArtifactGraphStore(str(tmp_path), project_id="project-a"))


def _complete_by_skipping(service: DBOSService, session_id: str) -> None:
    while question := service.next_intake_question(session_id):
        service.answer_intake(session_id, question["question_id"], skipped=True)


def test_skipped_answers_become_explicit_artifacts_and_conversion_is_idempotent(tmp_path):
    service = _service(tmp_path)
    session = service.create_intake("project-a", "Build a research workflow")
    _complete_by_skipping(service, session.artifact_id)

    first = service.convert_intake(session.artifact_id)
    second = service.convert_intake(session.artifact_id)
    mission = service.get_mission(first.mission.artifact_id)
    artifacts = service.store.get_by_project("project-a")

    assert first.mission.artifact_id == second.mission.artifact_id
    assert mission.mission_status == "ready_for_confirmation"
    assert mission.context["sop_generation_mode"] == "adaptive"
    assert mission.parent_ids == [session.artifact_id]
    assert any(isinstance(item, AssumptionArtifact) and "unanswered" in item.tags for item in artifacts)
    assert any(isinstance(item, GapArtifact) and "unanswered" in item.tags for item in artifacts)
    with pytest.raises(MissionNotConfirmedError):
        asyncio.run(service.execute(mission.artifact_id, "diagnosis"))


def test_career_intake_maps_to_existing_career_mission_mode(tmp_path):
    service = _service(tmp_path)
    session = service.create_intake("project-a", "Build a career interview preparation workflow")
    _complete_by_skipping(service, session.artifact_id)

    flow = service.convert_intake(session.artifact_id, title="Career planning")

    assert session.domain == "career"
    assert flow.mission.intake_mode == "career"
    assert flow.mission.intent == session.original_request


def test_answer_reversion_is_allowed_before_conversion_but_not_after(tmp_path):
    service = _service(tmp_path)
    session = service.create_intake("project-a", "Build an internal portal")
    question = service.next_intake_question(session.artifact_id)
    service.answer_intake(session.artifact_id, question["question_id"], "owner")
    revision = next(item for item in service.store.get_by_project("project-a") if item.__class__.__name__ == "IntakeAnswerRevisionArtifact")

    reopened = service.revert_intake_answer(session.artifact_id, revision.artifact_id)
    assert reopened.qualifying_question_count == 0

    _complete_by_skipping(service, session.artifact_id)
    service.convert_intake(session.artifact_id)
    with pytest.raises(IntakeError):
        service.revert_intake_answer(session.artifact_id, revision.artifact_id)


def test_direct_review_conversion_persists_bypassed_fields_as_assumptions_and_gaps(tmp_path):
    service = _service(tmp_path)
    session = service.create_intake("project-a", "Build a customer research portal")

    reviewed = service.direct_to_review(session.artifact_id)
    flow = service.convert_intake(session.artifact_id)
    artifacts = service.store.get_by_project("project-a")

    assert reviewed.phase == "ready_for_review"
    assert "role" in reviewed.unresolved_fields
    assert flow.mission.mission_status == "ready_for_confirmation"
    assert any(isinstance(item, AssumptionArtifact) and item.label == "Unanswered intake: role" for item in artifacts)
    assert any(isinstance(item, GapArtifact) and item.label == "Unanswered intake: role" for item in artifacts)
