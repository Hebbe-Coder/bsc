from app.knowledge.growth_contracts import ProjectKnowledgeProfile, TriageDisposition
from app.knowledge.growth_repository import GrowthRepository
import pytest
from types import SimpleNamespace

from app.core.config import settings
from app.promptops import PromptOpsError
from app.knowledge.source_triage import (
    SemanticSourceTriageEvaluator,
    SourceTriageService,
    TriageEvaluation,
    source_admission_reason,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_triage_routes_by_score_and_reliability(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage.db"))
    try:
        repo.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", research_domains=["knowledge systems"]),
            actor_id="owner",
        )
        repo.create_source(
            SourceRecord(
                id="source-a", project_id="project-a", source_type="article",
                content_hash="a" * 64, raw_content="important article", status=SourceStatus.VALIDATED,
                trust_level="trusted", metadata={"relevance": 95, "value": 90, "freshness": 80, "outputability": 90, "connectedness": 80},
            )
        )
        result = SourceTriageService(repo).triage_source("project-a", "source-a")
        assert result["disposition"] == TriageDisposition.KNOWLEDGE_CANDIDATE.value
        assert result["priority"] >= 80
        assert repo.get_source("project-a", "source-a")["status"] == SourceStatus.ELIGIBLE.value
    finally:
        repo.close()


def test_unreliable_high_score_is_not_eligible_and_research_question_is_typed(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-reliability.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-b", project_id="project-a", source_type="web_clip",
                content_hash="b" * 64, raw_content="unverified claim", status=SourceStatus.VALIDATED,
                trust_level="untrusted", metadata={"relevance": 100, "value": 100, "freshness": 100, "outputability": 100, "connectedness": 100, "research_question": True},
            )
        )
        result = SourceTriageService(repo).triage_source("project-a", "source-b")
        assert result["disposition"] == TriageDisposition.RESEARCH_TOPIC.value
        assert result["reliability_pass"] == 0
        assert repo.get_source("project-a", "source-b")["status"] == SourceStatus.VALIDATED.value
    finally:
        repo.close()


@pytest.mark.parametrize(
    ("score", "disposition"),
    [
        (39, TriageDisposition.IGNORE),
        (40, TriageDisposition.ARCHIVE),
        (59, TriageDisposition.ARCHIVE),
        (60, TriageDisposition.REFERENCE),
        (79, TriageDisposition.REFERENCE),
        (80, TriageDisposition.KNOWLEDGE_CANDIDATE),
    ],
)
def test_triage_routing_boundaries_are_exact(tmp_path, score, disposition):
    repo = GrowthRepository(db_path=str(tmp_path / f"boundary-{score}.db"))
    try:
        repo.create_source(
            SourceRecord(
                id=f"source-{score}",
                project_id="project-a",
                source_type="article",
                content_hash=f"{score:02x}" * 32,
                raw_content="boundary evidence",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "relevance": score,
                    "value": score,
                    "freshness": score,
                    "outputability": score,
                    "connectedness": score,
                },
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", f"source-{score}")

        assert result["priority"] == score
        assert result["disposition"] == disposition.value
    finally:
        repo.close()


def test_triage_rerun_is_idempotent_after_source_becomes_eligible(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-rerun.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-rerun",
                project_id="project-a",
                source_type="article",
                content_hash="c" * 64,
                raw_content="high quality evidence",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            )
        )
        service = SourceTriageService(repo)

        first = service.triage_source("project-a", "source-rerun")
        second = service.triage_source("project-a", "source-rerun")

        assert second["id"] == first["id"]
        assert len(repo.list_triage("project-a")) == 1
    finally:
        repo.close()


def test_triage_keeps_one_auditable_decision_per_evaluator_revision(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-evaluator-revision.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-evaluator", project_id="project-a", source_type="article",
                content_hash="d" * 64, raw_content="high quality evidence", status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            )
        )

        first = SourceTriageService(repo).triage_source(
            "project-a", "source-evaluator", evaluator_revision="deterministic-v2"
        )
        second = SourceTriageService(repo).triage_source(
            "project-a", "source-evaluator", evaluator_revision="profile-aware-v2"
        )

        assert first["id"] != second["id"]
        assert {item["evaluator_revision"] for item in repo.list_triage("project-a")} == {
            "deterministic-v2", "profile-aware-v2"
        }
    finally:
        repo.close()


def test_unadmitted_legacy_horizon_signal_returns_to_review(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-horizon-review.db"))
    try:
        repo.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", research_domains=["agent orchestration"]),
            actor_id="owner",
        )
        repo.create_source(
            SourceRecord(
                id="horizon-unrelated", project_id="project-a", source_type="horizon_signal",
                content_hash="e" * 64, raw_content="OpenGL graphics rendering guide.",
                status=SourceStatus.ELIGIBLE, trust_level="reviewed",
                metadata={"ai_score": 8.5, "admission_gate": "project_triage"},
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", "horizon-unrelated")

        assert result["disposition"] == TriageDisposition.ARCHIVE.value
        source = repo.get_source("project-a", "horizon-unrelated")
        assert source["status"] == SourceStatus.VALIDATED.value
        assert source["metadata"]["admission_correction"]["reason"].endswith(":archive")
    finally:
        repo.close()


def test_reference_evidence_requires_corroboration_before_authoring(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-reference-corroboration.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="reference-source",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="9" * 64,
                raw_content="A useful but secondary report.",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "admission_gate": "project_triage",
                    **{key: 70 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
                },
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", "reference-source")
        source = repo.get_source("project-a", "reference-source")

        assert result["disposition"] == TriageDisposition.REFERENCE.value
        assert source["status"] == SourceStatus.ELIGIBLE.value
        assert source_admission_reason(repo, "project-a", source) == "project_triage_reference_requires_corroboration"
    finally:
        repo.close()


def test_horizon_candidate_requires_an_independent_primary_capture_before_authoring(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-horizon-primary-capture.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="horizon-candidate",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="8" * 64,
                raw_content="A high-value radar discovery, not independently captured source evidence.",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "admission_gate": "project_triage",
                    **{key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
                },
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", "horizon-candidate")
        source = repo.get_source("project-a", "horizon-candidate")

        assert result["disposition"] == TriageDisposition.KNOWLEDGE_CANDIDATE.value
        assert source["status"] == SourceStatus.ELIGIBLE.value
        assert source_admission_reason(repo, "project-a", source) == "horizon_signal_requires_independent_primary_capture"
    finally:
        repo.close()


def test_horizon_candidate_can_be_used_only_after_an_explicit_independent_primary_capture(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-horizon-primary-link.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="horizon-candidate",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://news.example.com/approval-controls",
                content_hash="8" * 64,
                raw_content="A high-value radar discovery.",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "admission_gate": "project_triage",
                    **{key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
                },
            )
        )
        SourceTriageService(repo).triage_source("project-a", "horizon-candidate")
        repo.create_source(
            SourceRecord(
                id="primary-capture",
                project_id="project-a",
                source_type="web_clip",
                origin="https://news.example.com/approval-controls",
                content_hash="7" * 64,
                raw_content="The independently captured primary article.",
                status=SourceStatus.ELIGIBLE,
                trust_level="trusted",
                metadata={
                    "evidence_role": "primary_capture",
                    "supports_horizon_signal_ids": ["horizon-candidate"],
                },
            )
        )

        horizon = repo.get_source("project-a", "horizon-candidate")

        assert source_admission_reason(repo, "project-a", horizon) == ""
    finally:
        repo.close()


def test_horizon_candidate_accepts_the_legacy_discovery_link_on_existing_primary_capture(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-horizon-legacy-primary-link.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="horizon-candidate",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://news.example.com/approval-controls",
                content_hash="8" * 64,
                raw_content="A high-value radar discovery.",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "admission_gate": "project_triage",
                    **{key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
                },
            )
        )
        SourceTriageService(repo).triage_source("project-a", "horizon-candidate")
        repo.create_source(
            SourceRecord(
                id="legacy-primary-capture",
                project_id="project-a",
                source_type="primary_web",
                origin="https://news.example.com/approval-controls",
                content_hash="7" * 64,
                raw_content="An independently captured primary article from an earlier BSC version.",
                status=SourceStatus.ELIGIBLE,
                trust_level="trusted",
                metadata={
                    "evidence_role": "primary_capture",
                    "discovered_from_source_id": "horizon-candidate",
                },
            )
        )

        horizon = repo.get_source("project-a", "horizon-candidate")

        assert source_admission_reason(repo, "project-a", horizon) == ""
    finally:
        repo.close()


def test_horizon_candidate_rejects_cross_project_or_unlinked_primary_captures(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-horizon-primary-isolation.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="horizon-candidate",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="8" * 64,
                raw_content="A high-value radar discovery.",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={
                    "admission_gate": "project_triage",
                    **{key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
                },
            )
        )
        SourceTriageService(repo).triage_source("project-a", "horizon-candidate")
        repo.create_source(
            SourceRecord(
                id="unlinked-primary",
                project_id="project-a",
                source_type="web_clip",
                content_hash="7" * 64,
                raw_content="Another primary article.",
                status=SourceStatus.ELIGIBLE,
                trust_level="trusted",
                metadata={"evidence_role": "primary_capture", "supports_horizon_signal_ids": ["other-signal"]},
            )
        )
        repo.create_source(
            SourceRecord(
                id="foreign-primary",
                project_id="project-b",
                source_type="web_clip",
                content_hash="6" * 64,
                raw_content="A foreign project article.",
                status=SourceStatus.ELIGIBLE,
                trust_level="trusted",
                metadata={
                    "evidence_role": "primary_capture",
                    "supports_horizon_signal_ids": ["horizon-candidate"],
                },
            )
        )

        horizon = repo.get_source("project-a", "horizon-candidate")

        assert source_admission_reason(
            repo, "project-a", horizon
        ) == "horizon_signal_requires_independent_primary_capture"
    finally:
        repo.close()


def test_preeligible_source_can_record_profile_bound_triage_without_lifecycle_regression(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-preeligible.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-preeligible",
                project_id="project-a",
                source_type="browser_clip",
                content_hash="f" * 64,
                raw_content="trusted browser evidence",
                status=SourceStatus.ELIGIBLE,
                trust_level="trusted",
                metadata={key: 88 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            )
        )
        service = SourceTriageService(repo)

        first = service.triage_source("project-a", "source-preeligible")
        second = service.triage_source("project-a", "source-preeligible")

        assert first["profile_revision"] == 1
        assert second["id"] == first["id"]
        assert repo.get_source("project-a", "source-preeligible")["status"] == SourceStatus.ELIGIBLE.value
        assert len(repo.list_triage("project-a")) == 1
    finally:
        repo.close()


def test_trusted_browser_clip_from_capture_service_can_be_triaged_idempotently(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-captured-browser-clip.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        captured = SourceCaptureService(repo).capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="browser_clip",
                origin="https://example.com/trusted",
                raw_content="trusted browser evidence",
                trust_level="trusted",
                metadata={key: 90 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            )
        )
        assert captured.source["status"] == SourceStatus.ELIGIBLE.value

        service = SourceTriageService(repo)
        first = service.triage_source("project-a", captured.source["id"])
        second = service.triage_source("project-a", captured.source["id"])

        assert first["disposition"] == TriageDisposition.KNOWLEDGE_CANDIDATE.value
        assert second["id"] == first["id"]
        assert repo.get_source("project-a", captured.source["id"])["status"] == SourceStatus.ELIGIBLE.value
        assert len(repo.list_triage("project-a")) == 1
    finally:
        repo.close()


@pytest.mark.parametrize("terminal_status", [SourceStatus.PROCESSED, SourceStatus.REJECTED, SourceStatus.SUPERSEDED])
def test_triage_never_reopens_terminal_source_states(tmp_path, terminal_status):
    repo = GrowthRepository(db_path=str(tmp_path / f"triage-{terminal_status.value}.db"))
    try:
        repo.create_source(
            SourceRecord(
                id=f"source-{terminal_status.value}",
                project_id="project-a",
                source_type="article",
                content_hash=("1" if terminal_status is SourceStatus.PROCESSED else "2" if terminal_status is SourceStatus.REJECTED else "3") * 64,
                raw_content="terminal evidence",
                status=terminal_status,
                trust_level="trusted",
            )
        )

        with pytest.raises(ValueError, match="captured, validated, or eligible"):
            SourceTriageService(repo).triage_source("project-a", f"source-{terminal_status.value}")

        assert repo.get_source("project-a", f"source-{terminal_status.value}")["status"] == terminal_status.value
        assert repo.list_triage("project-a") == []
    finally:
        repo.close()


class _UnavailableEvaluator:
    def evaluate(self, *, source, profile):
        return TriageEvaluation(
            relevance=0,
            value=0,
            freshness=0,
            outputability=0,
            connectedness=0,
            evaluator_revision="model-v9",
            status="unavailable",
            latency_ms=321,
            reasons=["provider_timeout"],
        )


class _FailingEvaluator:
    revision = "model-v10"

    def evaluate(self, *, source, profile):
        raise RuntimeError("Bearer evaluator-secret-123456789")


class _SemanticPromptOps:
    def __init__(self):
        self.requests = []

    def run_structured(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            run_id="prompt_semantic_triage",
            provider="deepseek",
            model="deepseek-v4-pro",
            usage=SimpleNamespace(latency_ms=123),
            output={
                "relevance": 92,
                "value": 86,
                "freshness": 75,
                "outputability": 88,
                "connectedness": 84,
                "reasons": [
                    "The source directly addresses AI coding-agent workflow evaluation for this project's knowledge-system scope.",
                    "The source is a secondary report, so primary-session details should be verified before using it as a factual authority.",
                ],
            },
        )


def test_semantic_triage_is_audited_and_never_auto_admits_a_source(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "semantic-triage.db"))
    previous_provider = settings.KNOWLEDGE_WIKI_LLM_PROVIDER
    previous_model = settings.KNOWLEDGE_GROWTH_LLM_MODEL
    previous_deepseek_model = settings.DEEPSEEK_MODEL
    settings.KNOWLEDGE_WIKI_LLM_PROVIDER = "deepseek"
    settings.KNOWLEDGE_GROWTH_LLM_MODEL = ""
    settings.DEEPSEEK_MODEL = "deepseek-v4-pro"
    try:
        repo.save_profile(
            ProjectKnowledgeProfile(project_id="project-a", research_domains=["AI agents", "knowledge management"]),
            actor_id="owner",
        )
        repo.create_source(
            SourceRecord(
                id="semantic-source",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="7" * 64,
                raw_content="A report on AI coding-agent workflows and evidence-backed maintenance practices.",
                status=SourceStatus.VALIDATED,
                trust_level="reviewed",
                metadata={"admission_gate": "project_triage"},
            )
        )
        promptops = _SemanticPromptOps()

        result = SourceTriageService(
            repo,
            evaluator=SemanticSourceTriageEvaluator(promptops=promptops),
        ).triage_source("project-a", "semantic-source", apply_admission=False)

        assert result["evaluator_revision"] == "semantic-source-triage-v3"
        assert result["disposition"] == TriageDisposition.KNOWLEDGE_CANDIDATE.value
        assert result["priority"] >= 80
        assert "prompt_run=prompt_semantic_triage" in result["reasons"]
        assert repo.get_source("project-a", "semantic-source")["status"] == SourceStatus.VALIDATED.value
        assert promptops.requests[0].context_refs == (
            "source:semantic-source@" + "7" * 64,
            "profile:project-a@1",
        )
        assert promptops.requests[0].model_override == "deepseek-v4-pro"
        assert promptops.requests[0].max_tokens == 1_800
    finally:
        settings.KNOWLEDGE_WIKI_LLM_PROVIDER = previous_provider
        settings.KNOWLEDGE_GROWTH_LLM_MODEL = previous_model
        settings.DEEPSEEK_MODEL = previous_deepseek_model
        repo.close()


def test_semantic_triage_persists_a_safe_provider_failure_category(monkeypatch):
    class UnavailablePromptOps:
        def run_structured(self, _request):
            raise PromptOpsError("structured_response_invalid")

    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_LLM_PROVIDER", "deepseek")
    evaluation = SemanticSourceTriageEvaluator(promptops=UnavailablePromptOps()).evaluate(
        source={"id": "source-a", "content_hash": "a" * 64, "raw_content": "evidence"},
        profile=ProjectKnowledgeProfile(project_id="project-a"),
    )

    assert evaluation.status == "unavailable"
    assert evaluation.reasons == ["provider_failure=structured_response_invalid"]


def test_optional_evaluator_unavailability_is_persisted_without_eligibility(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-unavailable.db"))
    try:
        repo.create_source(
            SourceRecord(
                id="source-model",
                project_id="project-a",
                source_type="article",
                content_hash="d" * 64,
                raw_content="source",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
            )
        )

        result = SourceTriageService(repo, evaluator=_UnavailableEvaluator()).triage_source(
            "project-a", "source-model"
        )

        assert result["evaluator_revision"] == "model-v9"
        assert result["evaluator_status"] == "unavailable"
        assert "latency_ms=321" in result["reasons"]
        assert "provider_timeout" in result["reasons"]
        assert repo.get_source("project-a", "source-model")["status"] == SourceStatus.VALIDATED.value
    finally:
        repo.close()


def test_optional_evaluator_exception_becomes_redacted_unavailable_decision(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-evaluator-exception.db"))
    try:
        repo.create_source(
            SourceRecord(
                id="source-evaluator-exception",
                project_id="project-a",
                source_type="article",
                content_hash="6" * 64,
                raw_content="source",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
            )
        )

        result = SourceTriageService(repo, evaluator=_FailingEvaluator()).triage_source(
            "project-a", "source-evaluator-exception"
        )

        assert result["evaluator_revision"] == "model-v10"
        assert result["evaluator_status"] == "unavailable"
        assert "evaluator_exception=RuntimeError" in result["reasons"]
        assert "evaluator-secret" not in str(result)
        assert repo.get_source("project-a", "source-evaluator-exception")["status"] == SourceStatus.VALIDATED.value
    finally:
        repo.close()


def test_new_profile_revision_creates_a_new_reviewable_triage_decision(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-profile-revision.db"))
    try:
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a", research_domains=["agents"]), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="source-profile",
                project_id="project-a",
                source_type="article",
                content_hash="e" * 64,
                raw_content="source",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={key: 50 for key in ("relevance", "value", "freshness", "outputability", "connectedness")},
            )
        )
        service = SourceTriageService(repo)
        first = service.triage_source("project-a", "source-profile")
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a", research_domains=["knowledge"]), actor_id="owner")
        second = service.triage_source("project-a", "source-profile")

        assert first["profile_revision"] == 1
        assert second["profile_revision"] == 2
        assert first["id"] != second["id"]
    finally:
        repo.close()


def test_triage_priority_uses_domain_half_up_rounding(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-rounding.db"))
    try:
        repo.create_source(
            SourceRecord(
                id="source-rounding",
                project_id="project-a",
                source_type="article",
                content_hash="4" * 64,
                raw_content="rounding evidence",
                status=SourceStatus.VALIDATED,
                trust_level="trusted",
                metadata={"relevance": 15, "value": 0, "freshness": 0, "outputability": 0, "connectedness": 0},
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", "source-rounding")

        assert result["priority"] == 5
        assert "priority=5" in result["reasons"]
    finally:
        repo.close()


def test_low_value_unanswered_note_is_not_promoted_to_research_topic(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-low-value-question.db"))
    try:
        repo.create_source(
            SourceRecord(
                id="source-low-value-question",
                project_id="project-a",
                source_type="article",
                content_hash="5" * 64,
                raw_content="minor unresolved note",
                status=SourceStatus.VALIDATED,
                trust_level="untrusted",
                metadata={
                    "relevance": 30,
                    "value": 30,
                    "freshness": 30,
                    "outputability": 30,
                    "connectedness": 30,
                    "unanswered_question": True,
                },
            )
        )

        result = SourceTriageService(repo).triage_source("project-a", "source-low-value-question")

        assert result["disposition"] == TriageDisposition.IGNORE.value
        assert SourceTriageService(repo).list_research_topics("project-a") == []
    finally:
        repo.close()


def test_profile_terms_raise_relevance_only_for_matching_unscored_sources(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "triage-profile-match.db"))
    try:
        repo.save_profile(
            ProjectKnowledgeProfile(
                project_id="project-a",
                research_domains=["AI agents", "Obsidian knowledge workflows"],
                primary_output_types=["project-specific PRD and SOP"],
            ),
            actor_id="owner",
        )
        for source_id, content, tags in (
            (
                "agent-signal",
                "A practical guide to evaluating AI agent workflows with MCP.",
                ["AI agents", "MCP"],
            ),
            (
                "graphics-signal",
                "A research guide to learning OpenGL graphics rendering.",
                ["graphics", "OpenGL", "research"],
            ),
        ):
            repo.create_source(
                SourceRecord(
                    id=source_id,
                    project_id="project-a",
                    source_type="horizon_signal",
                    content_hash=("a" if source_id == "agent-signal" else "b") * 64,
                    raw_content=content,
                    status=SourceStatus.VALIDATED,
                    trust_level="reviewed",
                    metadata={"ai_score": 8.0, "ai_tags": tags},
                )
            )

        service = SourceTriageService(repo)
        matching = service.triage_source("project-a", "agent-signal")
        unrelated = service.triage_source("project-a", "graphics-signal")

        assert matching["relevance"] > unrelated["relevance"]
        assert matching["priority"] > unrelated["priority"]
        assert any(reason.startswith("profile_matches=agent") for reason in matching["reasons"])
        assert "profile_matches=none" in unrelated["reasons"]
    finally:
        repo.close()
