import pytest

from app.artifacts import ArtifactGraphStore, ArtifactType, IntakeAnswerRevisionArtifact, IntakeSessionArtifact
from app.core.config import settings
from app.dbos.intake import IntakeDisabledError, IntakeService


def _service(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="project-a")
    return IntakeService(store)


def test_intake_artifacts_round_trip_through_the_scoped_graph(tmp_path):
    store = ArtifactGraphStore(str(tmp_path), project_id="project-a")
    session = IntakeSessionArtifact(project_id="project-a", label="Intake", original_request="Build a customer portal")
    store.add(session)
    revision = IntakeAnswerRevisionArtifact(
        project_id="project-a",
        label="Answer: role",
        session_id=session.artifact_id,
        question_id="qualify-role",
        answer="product manager",
        parent_ids=[session.artifact_id],
    )
    store.add(revision)

    restored = store.get(session.artifact_id)
    assert isinstance(restored, IntakeSessionArtifact)
    assert restored.artifact_type == ArtifactType.INTAKE_SESSION
    assert store.get(revision.artifact_id).artifact_type == ArtifactType.INTAKE_ANSWER_REVISION


def test_classifier_routes_build_direct_help_and_uncertain_requests(tmp_path):
    service = _service(tmp_path)

    build = service.create_session("project-a", "我想搭建一个客户预约网站")
    direct = service.create_session("project-a", "别问了，直接执行这个自动化脚本")
    help_request = service.create_session("project-a", "这篇论文的数据分析错误是什么意思？")
    uncertain = service.create_session("project-a", "最近有点乱")

    assert (build.classification, build.phase, build.domain) == ("build", "clarifying", "product_build")
    assert (direct.classification, direct.phase) == ("direct", "ready_for_review")
    assert (help_request.classification, help_request.phase) == ("help", "exited")
    assert (uncertain.classification, uncertain.phase) == ("uncertain", "classified")


def test_question_budget_rejects_an_extra_question_before_mutating(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("project-a", "我要搭建一个内容创作自动化")

    for _ in range(2):
        question = service.next_question(session.artifact_id)
        service.answer(session.artifact_id, question["question_id"], "owner")
    for _ in range(3):
        question = service.next_question(session.artifact_id)
        service.answer(session.artifact_id, question["question_id"], "declared")
    question = service.next_question(session.artifact_id)
    service.answer(session.artifact_id, question["question_id"], "main risk")

    assert service.next_question(session.artifact_id) is None
    restored = service.get_session(session.artifact_id)
    assert restored.phase == "ready_for_review"
    assert restored.qualifying_question_count == 2
    assert restored.completion_question_count == 3
    assert restored.probe_question_count == 1


def test_store_scope_rejects_an_intake_parent_from_another_project(tmp_path):
    project_a = ArtifactGraphStore(str(tmp_path), project_id="project-a")
    project_b = ArtifactGraphStore(str(tmp_path), project_id="project-b")
    session = IntakeSessionArtifact(project_id="project-a", label="A", original_request="build")
    project_a.add(session)

    foreign_revision = IntakeAnswerRevisionArtifact(
        project_id="project-b",
        label="foreign",
        session_id=session.artifact_id,
        question_id="q",
        parent_ids=[session.artifact_id],
    )
    try:
        project_b.add(foreign_revision)
    except ValueError as exc:
        assert "outside this store scope" in str(exc)
    else:
        raise AssertionError("cross-project Intake parent should be rejected")


def test_prefilled_context_skips_duplicate_questions_and_direct_review_persists_unanswered_fields(tmp_path):
    service = _service(tmp_path)
    session = service.create_session(
        "project-a",
        "Build a customer research portal",
        context={"role": "Product lead", "industry": "Software or AI"},
    )

    question = service.next_question(session.artifact_id)
    assert question is not None
    assert question["field"] == "goal"

    reviewed = service.direct_to_review(session.artifact_id)
    assert reviewed.phase == "ready_for_review"
    assert "role" not in reviewed.unresolved_fields
    assert "industry" not in reviewed.unresolved_fields
    assert {"goal", "organization_stage", "success_metrics", "primary_risk"} <= set(reviewed.unresolved_fields)


def test_feature_flag_blocks_every_intake_mutation_after_a_session_exists(tmp_path, monkeypatch):
    service = _service(tmp_path)
    session = service.create_session("project-a", "Build a customer portal")
    monkeypatch.setattr(settings, "DBOS_BLINDSPOT_INTAKE_ENABLED", False)

    with pytest.raises(IntakeDisabledError):
        service.next_question(session.artifact_id)
    with pytest.raises(IntakeDisabledError):
        service.direct_to_review(session.artifact_id)

    restored = service.get_session(session.artifact_id)
    assert restored.phase == "clarifying"
    assert not restored.active_question
