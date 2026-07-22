import pytest
from pydantic import ValidationError

from app.knowledge.growth_contracts import (
    FeedbackType,
    MethodAsset,
    MethodStatus,
    OutputAsset,
    OutputStatus,
    ProjectKnowledgeProfile,
    SourceTriage,
    TriageDisposition,
    evaluate_priority,
)


def test_profile_has_stable_defaults_and_rejects_unbounded_policy_values():
    profile = ProjectKnowledgeProfile(project_id="project-a")

    assert profile.language == "zh-CN"
    assert profile.evidence_threshold == 80
    assert profile.primary_output_types == ["markdown"]
    assert profile.automatic_publication_policy == "review"
    assert profile.method_promotion_policy == "gated"

    with pytest.raises(ValidationError):
        ProjectKnowledgeProfile(project_id="project-a", evidence_threshold=101)


def test_triage_formula_and_research_topic_are_explicit():
    score = evaluate_priority(100, 80, 60, 40, 20)
    assert score == 68
    triage = SourceTriage(
        project_id="project-a",
        source_id="source-a",
        profile_revision=2,
        relevance=100,
        value=80,
        freshness=60,
        outputability=40,
        connectedness=20,
        reliability_pass=False,
        disposition=TriageDisposition.RESEARCH_TOPIC,
        reasons=["high-value unanswered question"],
    )
    assert triage.priority == 68
    assert triage.disposition is TriageDisposition.RESEARCH_TOPIC


def test_method_and_output_lifecycle_models_require_project_and_safe_paths():
    method = MethodAsset(project_id="project-a", slug="weekly-review", name="Weekly review")
    assert method.status is MethodStatus.CANDIDATE

    output = OutputAsset(
        project_id="project-a",
        kind="report",
        title="Weekly report",
        content_hash="a" * 64,
        vault_path="outputs/2026/out-1/report.md",
        idempotency_key="report-1",
        status=OutputStatus.REGISTERED,
    )
    assert output.status is OutputStatus.REGISTERED

    with pytest.raises(ValidationError):
        OutputAsset(
            project_id="project-a",
            kind="report",
            title="Unsafe",
            content_hash="b" * 64,
            vault_path="../outside.md",
        )


def test_feedback_type_is_typed():
    assert FeedbackType.CORRECTED.value == "corrected"
