from __future__ import annotations

import pytest

from app.artifacts import ArtifactGraphStore
from app.dbos.intake import IntakeError, IntakeService


@pytest.mark.parametrize(
    ("request_text", "classification", "domain"),
    [
        ("Build a customer portal", "build", "product_build"),
        ("Create a website for client bookings", "build", "product_build"),
        ("Build an app for research notes", "build", "product_build"),
        ("Build an automation workflow", "build", "automation"),
        ("Create a workflow for weekly reporting", "build", "automation"),
        ("Build a data analysis workflow", "build", "data_analysis"),
        ("Create a data analysis dashboard", "build", "data_analysis"),
        ("Build a career interview preparation plan", "build", "career"),
        ("Direct execution: build a customer portal", "direct", "product_build"),
        ("Skip questions and create an automation workflow", "direct", "automation"),
        ("Just do it: create a website", "direct", "product_build"),
        ("What is a source citation?", "help", "business"),
        ("Explain an automation workflow", "help", "automation"),
        ("Why did the data analysis fail?", "help", "data_analysis"),
        ("Can you explain career interview loops?", "help", "career"),
        ("Please explain whether I should build an app", "help", "product_build"),
        ("I feel scattered about this work", "uncertain", "business"),
        ("Need guidance before deciding", "uncertain", "business"),
    ],
)
def test_classifier_evaluation_matrix(request_text, classification, domain):
    observed = IntakeService.classify(request_text)
    assert observed[0] == classification
    assert observed[3] == domain


@pytest.mark.parametrize(
    ("request_text", "domain"),
    [
        ("Build a product website", "product_build"),
        ("Build an automation workflow", "automation"),
        ("Build a data analysis workflow", "data_analysis"),
        ("Build a career interview plan", "career"),
        ("Build an operating model", "business"),
    ],
)
def test_every_build_domain_stops_after_the_governed_six_question_budget(tmp_path, request_text, domain):
    service = IntakeService(ArtifactGraphStore(str(tmp_path), project_id="project-a"))
    session = service.create_session("project-a", request_text)
    assert session.domain == domain

    answered = 0
    while question := service.next_question(session.artifact_id):
        answered += 1
        service.answer(session.artifact_id, question["question_id"], "declared")

    complete = service.get_session(session.artifact_id)
    assert answered == 6
    assert complete.phase == "ready_for_review"
    assert (complete.qualifying_question_count, complete.completion_question_count, complete.probe_question_count) == (2, 3, 1)


@pytest.mark.parametrize(
    ("request_text", "expected_phase"),
    [
        ("Direct execution: build a site", "ready_for_review"),
        ("Skip questions and create a workflow", "ready_for_review"),
        ("What is a source citation?", "exited"),
        ("I feel scattered", "classified"),
    ],
)
def test_non_build_entries_do_not_open_an_interview_without_a_user_choice(tmp_path, request_text, expected_phase):
    service = IntakeService(ArtifactGraphStore(str(tmp_path), project_id="project-a"))
    session = service.create_session("project-a", request_text)
    assert session.phase == expected_phase
    assert service.next_question(session.artifact_id) is None


@pytest.mark.parametrize("operation", ["answer_without_question", "answer_wrong_question", "tier_without_review", "resolve_non_uncertain", "blank_answer"])
def test_invalid_transitions_never_mutate_a_governed_intake(tmp_path, operation):
    service = IntakeService(ArtifactGraphStore(str(tmp_path), project_id="project-a"))
    session = service.create_session("project-a", "Build a customer portal")

    if operation == "answer_without_question":
        call = lambda: service.answer(session.artifact_id, "qualify-role", "owner")
    elif operation == "answer_wrong_question":
        service.next_question(session.artifact_id)
        call = lambda: service.answer(session.artifact_id, "complete-industry", "owner")
    elif operation == "tier_without_review":
        call = lambda: service.select_tier(session.artifact_id, "lite")
    elif operation == "resolve_non_uncertain":
        call = lambda: service.resolve_uncertain(session.artifact_id, "direct")
    else:
        question = service.next_question(session.artifact_id)
        call = lambda: service.answer(session.artifact_id, question["question_id"], "")

    with pytest.raises(IntakeError):
        call()
    restored = service.get_session(session.artifact_id)
    assert restored.phase == "clarifying"
    assert restored.qualifying_question_count == 0
