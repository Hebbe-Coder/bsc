import hashlib
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.promptops import PromptTask, PromptUsage
from app.knowledge.growth_distillation import (
    ConfiguredDistillationNarrativeProvider,
    GrowthDistillationService,
    ManagedContentConflictError,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeLineageEdge,
    OutputAsset,
    OutputEvaluation,
    OutputFeedback,
    ProjectKnowledgeProfile,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.knowledge.wiki_rules import build_default_agents_rules


_CUTOFF_SAFE_TIME = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _valid_weekly_document(label: str) -> str:
    return (
        f"## Evidence\n\n{label} is grounded in the retained source and must remain scoped to that evidence "
        "rather than becoming a claim about unrecorded project work [source:source-a].\n\n"
        "## Conditional recommendation\n\nThe project should turn this observation into a review item with a "
        "named verification criterion before changing a workflow or publishing a conclusion [source:source-a].\n\n"
        "## Open question\n\nThe evidence does not establish the responsible owner, the present system "
        "state, or the outcome of a future experiment; those facts remain an Open question [source:source-a]."
    )

class _NarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {
                "daily": {
                    "headline": "Review-gate evidence changes the project decision context",
                    "signal": "[source:source-a@revision-a] shows that review gates remain a required control.",
                    "project_implication": "The project should keep the review gate explicit in its publication flow [source:source-a].",
                    "next_review": "Verify the owner and escalation path before the next publication [source:source-a].",
                    "open_question": "The evidence does not identify whether the current owner can meet the required review SLA and requires verification [source:source-a].",
                }
            }
        names = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        return {
            "weekly": {
                names[0]: _valid_weekly_document("This week decisive evidence"),
                names[1]: _valid_weekly_document("Knowledge-action evidence"),
                names[2]: _valid_weekly_document("Content-creation evidence"),
                names[3]: _valid_weekly_document("Next-context evidence"),
                names[4]: _valid_weekly_document("Method-iteration evidence"),
            }
        }


class _CorrelatedNarrativeProvider(_NarrativeProvider):
    supports_run_correlation = True
    provider = "deepseek"
    model = "deepseek-v4-pro"

    def __init__(self) -> None:
        self.knowledge_run_ids: list[str] = []
        self.last_prompt_run = SimpleNamespace(
            run_id="prompt-growth-a",
            task=PromptTask.KNOWLEDGE_DISTILLATION,
            revision="growth-distillation-v9",
            provider=self.provider,
            model=self.model,
            agent_manifest=SimpleNamespace(manifest_fingerprint="a" * 64),
            usage=PromptUsage(
                provider_calls=1,
                reported_calls=1,
                complete=True,
                latency_ms=250,
                prompt_tokens=91,
                completion_tokens=32,
                total_tokens=123,
            ),
        )

    def render(self, *, kind, project_id, period, context, knowledge_run_id=""):
        self.knowledge_run_ids.append(knowledge_run_id)
        return super().render(kind=kind, project_id=project_id, period=period, context=context)


class _UncitedNarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {"daily": "## Generic daily update\n\nNothing to review."}
        return {
            "weekly": {
                name: "## Generic weekly update\n\nNothing to review."
                for name in GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
            }
        }


class _ThinCitedDailyProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {
                "daily": (
                    "## One-line evidence update\n\n"
                    "[source:source-a] is important to the project."
                )
            }
        return _NarrativeProvider().render(
            kind=kind,
            project_id=project_id,
            period=period,
            context=context,
        )


class _PartialNarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {"daily": "## Grounded daily synthesis\n\n[source:source-a] changed the project decision context."}
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        return {
            "weekly": {
                slots[0]: _valid_weekly_document("Bespoke summary"),
                slots[1]: "## Uncited action\n\nFollow up next week.",
                slots[2]: "## Uncited content\n\nDraft a useful article.",
                slots[3]: "## Uncited context\n\nContinue the review.",
                slots[4]: "## Uncited method\n\nRevise the process.",
            }
        }


class _UnavailableNarrativeProvider:
    unavailable_reason = "response_payload_invalid"

    def render(self, *, kind, project_id, period, context):
        return None


class _ProductionUnavailableNarrativeProvider(_UnavailableNarrativeProvider):
    requires_complete_weekly_llm_for_replacement = True
    semantic_generation_attempted = True


class _ProductionOneShotPartialNarrativeProvider(_PartialNarrativeProvider):
    supports_quality_retry = True
    requires_complete_weekly_llm_for_replacement = True
    semantic_generation_attempted = True
    max_weekly_model_invocations = 1

    def __init__(self) -> None:
        self.calls = 0
        self.prompt_runs = [object()]

    def render(self, **kwargs):
        self.calls += 1
        return super().render(**kwargs)


class _ProductionBatchRepairNarrativeProvider:
    supports_quality_retry = True
    supports_targeted_weekly_retry = True
    max_weekly_model_invocations = 2

    def __init__(self) -> None:
        self.targets: list[tuple[str, ...]] = []

    def render(self, *, kind, project_id, period, context, weekly_document_names=(), **_kwargs):
        self.targets.append(tuple(weekly_document_names))
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        if weekly_document_names:
            slots_by_document = dict(zip(GrowthDistillationService.WEEKLY_DOCUMENTS, slots, strict=True))
            return {
                "weekly": {
                    slots_by_document[name]: _valid_weekly_document("Batch repair evidence")
                    for name in weekly_document_names
                }
            }
        return {
            "weekly": {
                slots[0]: _valid_weekly_document("Initial accepted evidence"),
                **{slot: "## Invalid\n\nNo evidence citation." for slot in slots[1:]},
            }
        }


class _ProductionFinalStrictRepairNarrativeProvider:
    supports_quality_retry = True
    supports_targeted_weekly_retry = True
    supports_final_strict_weekly_retry = True
    max_weekly_model_invocations = 3

    def __init__(self) -> None:
        self.calls = 0
        self.targets: list[tuple[str, ...]] = []

    def render(self, *, kind, project_id, period, context, weekly_document_names=(), **_kwargs):
        self.calls += 1
        self.targets.append(tuple(weekly_document_names))
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        slots_by_document = dict(zip(GrowthDistillationService.WEEKLY_DOCUMENTS, slots, strict=True))
        summary = GrowthDistillationService.WEEKLY_DOCUMENTS[0]
        if not weekly_document_names:
            weekly = {slot: _valid_weekly_document(f"Initial {slot} evidence") for slot in slots}
            weekly[slots[0]] += "\n\n## State\n\nThis week we decided to migrate BSC [source:source-a]."
            return {"weekly": weekly}
        if self.calls == 2:
            return {
                "weekly": {
                    slots_by_document[summary]: _valid_weekly_document("Unsafe summary")
                    + "\n\n## State\n\nThis week we decided to migrate BSC [source:source-a]."
                }
            }
        return {
            "weekly": {
                slots_by_document[summary]: _valid_weekly_document("Strictly repaired summary evidence")
            }
        }


class _ProductionFinalStrictBatchRepairNarrativeProvider:
    supports_quality_retry = True
    supports_targeted_weekly_retry = True
    supports_final_strict_batch_weekly_retry = True
    max_weekly_model_invocations = 3

    def __init__(self) -> None:
        self.targets: list[tuple[str, ...]] = []
        self.feedback: list[str] = []

    def render(self, *, kind, project_id, period, context, weekly_document_names=(), quality_feedback="", **_kwargs):
        self.targets.append(tuple(weekly_document_names))
        self.feedback.append(quality_feedback)
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        slots_by_document = dict(zip(GrowthDistillationService.WEEKLY_DOCUMENTS, slots, strict=True))
        if len(self.targets) == 1:
            return {
                "weekly": {
                    slots[0]: _valid_weekly_document("Initial accepted evidence"),
                    **{
                        slot: _valid_weekly_document("Invalid citation evidence") + "\n\n[source:not-in-ledger]"
                        for slot in slots[1:]
                    },
                }
            }
        if len(self.targets) == 2:
            return {
                "weekly": {
                    slots_by_document[name]: _valid_weekly_document("Still invalid citation evidence")
                    + "\n\n[page:not-in-ledger]"
                    for name in weekly_document_names
                }
            }
        return {
            "weekly": {
                slots_by_document[name]: _valid_weekly_document("Strict batch repair evidence")
                for name in weekly_document_names
            }
        }


class _UnsupportedProjectStateNarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        weekly = {slot: _valid_weekly_document(f"{slot} evidence") for slot in slots}
        weekly[slots[0]] += "\n\n## Unsupported status\n\nThis week we decided to migrate BSC to a new tool protocol [source:source-a]."
        return {"weekly": weekly}


class _RetryableNarrativeProvider:
    supports_quality_retry = True

    def __init__(self) -> None:
        self.feedback: list[str] = []

    def render(self, *, kind, project_id, period, context, quality_feedback=""):
        self.feedback.append(quality_feedback)
        if quality_feedback:
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        return _UnsupportedProjectStateNarrativeProvider().render(
            kind=kind,
            project_id=project_id,
            period=period,
            context=context,
        )


class _DailyRepairNarrativeProvider:
    supports_quality_retry = True
    max_daily_model_invocations = 2

    def __init__(self) -> None:
        self.feedback: list[str] = []

    def render(self, *, kind, project_id, period, context, quality_feedback=""):
        self.feedback.append(quality_feedback)
        if kind == "daily" and not quality_feedback:
            return {
                "daily": {
                    "headline": "Invalid first response",
                    "signal": "Unverified signal [source:forged].",
                    "project_implication": "Do not use this reference [source:forged].",
                    "next_review": "Verify the cited evidence [source:forged].",
                    "open_question": "The provenance is unresolved [source:forged].",
                }
            }
        return _NarrativeProvider().render(
            kind=kind,
            project_id=project_id,
            period=period,
            context=context,
        )


class _TargetedRetryNarrativeProvider:
    """Simulates a real provider whose repair request only returns rejected files."""

    supports_quality_retry = True
    supports_targeted_weekly_retry = True
    supports_run_correlation = True
    provider = "deepseek"
    model = "deepseek-v4-pro"

    def __init__(self, *, fail_first_target: bool = False) -> None:
        self.targets: list[tuple[str, ...]] = []
        self.prompt_runs: list[SimpleNamespace] = []
        self.last_prompt_run: SimpleNamespace | None = None
        self.fail_first_target = fail_first_target

    def reset_run_evidence(self) -> None:
        self.prompt_runs = []
        self.last_prompt_run = None

    def render(
        self,
        *,
        kind,
        project_id,
        period,
        context,
        knowledge_run_id="",
        quality_feedback="",
        weekly_document_names=(),
    ):
        self.targets.append(tuple(weekly_document_names))
        call_number = len(self.targets)
        self.last_prompt_run = SimpleNamespace(
            run_id=f"prompt-targeted-{call_number}",
            task=PromptTask.KNOWLEDGE_DISTILLATION,
            revision=f"growth-distillation-v{GrowthDistillationService.DISTILLATION_CONTRACT_REVISION}",
            provider=self.provider,
            model=self.model,
            agent_manifest=SimpleNamespace(manifest_fingerprint=f"{call_number}" * 64),
            usage=PromptUsage(
                provider_calls=1,
                reported_calls=1,
                complete=True,
                latency_ms=100 * call_number,
                prompt_tokens=10 * call_number,
                completion_tokens=20 * call_number,
                total_tokens=30 * call_number,
            ),
        )
        self.prompt_runs.append(self.last_prompt_run)
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        if weekly_document_names:
            slots_by_document = dict(zip(
                GrowthDistillationService.WEEKLY_DOCUMENTS,
                GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS,
                strict=True,
            ))
            if self.fail_first_target and len(self.targets) == 2:
                return {
                    "weekly": {
                        slots_by_document[name]: "## Invalid repair\n\nThe repair has no evidence citation."
                        for name in weekly_document_names
                    }
                }
            return {
                "weekly": {
                    slots_by_document[name]: _valid_weekly_document("Targeted repair evidence")
                    for name in weekly_document_names
                }
            }
        return _UnsupportedProjectStateNarrativeProvider().render(
            kind=kind,
            project_id=project_id,
            period=period,
            context=context,
        )


class _AllRejectedTargetedNarrativeProvider:
    """A whole-batch failure must not fan out into one repair per file."""

    supports_quality_retry = True
    supports_targeted_weekly_retry = True

    def __init__(self) -> None:
        self.targets: list[tuple[str, ...]] = []

    def render(
        self,
        *,
        kind,
        project_id,
        period,
        context,
        quality_feedback="",
        weekly_document_names=(),
    ):
        self.targets.append(tuple(weekly_document_names))
        if kind == "daily":
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        if quality_feedback:
            return {"weekly": {slot: _valid_weekly_document("Whole-batch repair evidence") for slot in slots}}
        return {"weekly": {slot: "## Invalid\n\nNo evidence citation." for slot in slots}}


def test_configured_narrative_provider_prefers_growth_model_override(monkeypatch):
    captured = {}

    class _Client:
        def __init__(self, *, provider, model, timeout=None):
            captured["provider"] = provider
            captured["model"] = model
            captured["timeout"] = timeout
            self.model = model
            self.last_structured_failure = ""

        def chat_structured(self, **kwargs):
            captured["structured_call_cap"] = kwargs["max_structured_attempts"]
            captured["max_tokens"] = kwargs["max_tokens"]
            return {
                "daily": {
                    "headline": "Evidence retained for review",
                    "signal": "[source:source-a] is retained for review.",
                    "project_implication": "The project must assess its relevance [source:source-a].",
                    "next_review": "Confirm the evidence owner [source:source-a].",
                    "open_question": "The operational impact requires verification [source:source-a].",
                }
            }

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "SOP_LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_LLM_MODEL", "growth-specific-model")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_LLM_TIMEOUT_SECONDS", 135.0)
    monkeypatch.setattr("app.services.sop_llm_client.SOPLLMClient", _Client)

    provider = ConfiguredDistillationNarrativeProvider()
    result = provider.render(
        kind="daily",
        project_id="project-a",
        period="2026-07-25",
        context="[source:source-a]",
        knowledge_run_id="growth-run-a",
    )

    assert result["daily"]["headline"] == "Evidence retained for review"
    assert captured == {
        "provider": "deepseek",
        "model": "growth-specific-model",
        "timeout": 135.0,
        "structured_call_cap": 1,
        "max_tokens": ConfiguredDistillationNarrativeProvider.DAILY_MAX_TOKENS,
    }
    assert provider.last_prompt_run.agent_manifest.context_refs == ("knowledge_run:growth-run-a",)


def test_configured_narrative_provider_reserves_enough_tokens_for_a_small_weekly_repair(monkeypatch):
    captured = {}

    class _Client:
        def __init__(self, **_kwargs):
            self.model = "growth-specific-model"
            self.last_structured_failure = ""

        def chat_structured(self, **kwargs):
            captured["max_tokens"] = kwargs["max_tokens"]
            return {"weekly": {"summary": _valid_weekly_document("Repair evidence")}}

    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED", True)
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "SOP_LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_LLM_MODEL", "growth-specific-model")
    monkeypatch.setattr("app.services.sop_llm_client.SOPLLMClient", _Client)

    provider = ConfiguredDistillationNarrativeProvider()
    result = provider.render(
        kind="weekly",
        project_id="project-a",
        period="2026-W30",
        context="[source:source-a]",
        weekly_document_names=(GrowthDistillationService.WEEKLY_DOCUMENTS[0],),
    )

    assert result["weekly"]["summary"]
    assert captured["max_tokens"] == ConfiguredDistillationNarrativeProvider.TARGETED_WEEKLY_MAX_TOKENS_FLOOR


def test_targeted_weekly_prompt_keeps_only_requested_distinct_document_contracts():
    requested = (
        GrowthDistillationService.WEEKLY_DOCUMENTS[0],
        GrowthDistillationService.WEEKLY_DOCUMENTS[3],
        GrowthDistillationService.WEEKLY_DOCUMENTS[4],
    )

    prompt = ConfiguredDistillationNarrativeProvider._system_prompt(
        "weekly",
        quality_feedback="summary (unsupported_project_state)",
        weekly_document_names=requested,
    )

    assert '"summary"' in prompt
    assert '"next_context"' in prompt
    assert '"method_iteration"' in prompt
    assert "content_briefs:" not in prompt
    assert "## Open question and constraints" in prompt
    assert "Every factual sentence must use Evidence" in prompt
    assert "Do not use BSC, Obsidian, the project, we, system, or knowledge base" in prompt
    assert "unsupported_project_state" in prompt


def test_validated_markdown_normalizes_structured_list_items_before_citation_validation():
    content = GrowthDistillationService._validated_markdown(
        [
            "Review the current project decision against [source:source-a].",
            "Draft one evidence-backed content angle from [source:source-a].",
        ],
        {"citation_source_ids": ["source-a"]},
    )

    assert content == (
        "- Review the current project decision against [source:source-a].\n\n"
        "- Draft one evidence-backed content angle from [source:source-a]."
    )
    assert "['Review" not in content


def test_weekly_markdown_rejects_non_evidence_references_and_unsupported_state_claims():
    context = {"citation_source_ids": ["source-a"]}
    method_reference = _valid_weekly_document("Method reference") + "\n\n## Method\n\n[method:method-a] is not evidence."
    unsupported_state = _valid_weekly_document("State claim") + (
        "\n\n## Status\n\n\u7cfb\u7edf\u672a\u80fd\u5728\u5bfc\u5165\u9636\u6bb5\u8b66\u793a\u622a\u65ad\u6e90 [source:source-a]."
    )

    assert GrowthDistillationService._validated_weekly_markdown(method_reference, context) == ""
    assert GrowthDistillationService._validated_weekly_markdown(unsupported_state, context) == ""


@pytest.mark.parametrize(
    ("content", "expected_reason"),
    [
        ("## Evidence\n\nA short claim without a ledger reference.\n\n## Open question\n\nOpen question.", "missing_citation"),
        (_valid_weekly_document("Invalid label").replace("source-a", "source-not-in-ledger"), "invalid_reference"),
        ("## Evidence\n\n[source:source-a]\n\n## Open question\n\nOpen question.", "too_short"),
        (
            "## Evidence\n\n" + "Grounded observation [source:source-a]. " * 12 + "Open question remains.",
            "missing_sections",
        ),
        (_valid_weekly_document("Closed claim").replace("Open question", "Resolved item"), "missing_uncertainty"),
        (
            _valid_weekly_document("Unsupported state")
            + "\n\n## State\n\nThis week we decided to migrate BSC [source:source-a].",
            "unsupported_project_state",
        ),
    ],
)
def test_weekly_markdown_exposes_non_content_rejection_reasons(content, expected_reason):
    validated, reason = GrowthDistillationService._weekly_markdown_validation(
        content,
        {"citation_source_ids": ["source-a"]},
    )

    assert validated == ""
    assert reason == expected_reason


def test_daily_narrative_requires_a_citation_in_every_evidence_section():
    daily = GrowthDistillationService._validated_daily_narrative(
        {
            "headline": "A grounded daily card",
            "signal": "The signal is supported [source:source-a].",
            "project_implication": "The impact has not been cited.",
            "next_review": "Review the source before acting [source:source-a].",
            "open_question": "The unresolved question still cites its evidence [source:source-a].",
        },
        {"citation_source_ids": ["source-a"]},
    )

    assert daily == ""


def test_daily_narrative_requires_an_explicit_uncertainty_in_the_question_body():
    daily, reason = GrowthDistillationService._validated_daily_narrative_with_reason(
        {
            "headline": "A grounded daily card",
            "signal": "The signal is supported [source:source-a].",
            "project_implication": "Keep the evidence boundary visible [source:source-a].",
            "next_review": "Verify the source before acting [source:source-a].",
            "open_question": "Which reviewer owns the next check [source:source-a]?",
        },
        {"citation_source_ids": ["source-a"]},
    )

    assert daily == ""
    assert reason == "missing_uncertainty"


def test_weekly_distillation_is_idempotent_and_writes_dual_track_bundle(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.register_output(
            OutputAsset(
                id="output-a", project_id="project-a", kind="report", title="Accepted report", content_hash="a" * 64,
                vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", status="accepted",
                metadata={"task_family": "weekly-report"},
            )
        )
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T17:00:00Z")
        second = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T17:00:00Z")
        assert first["input_hash"] == second["input_hash"]
        assert second["status"] == "noop"
        project_root = root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        for name in ["00-本周总结.md", "01-知识行动.md", "02-内容创作.md", "03-下周上下文包.md", "04-方法迭代.md", "manifest.json"]:
            assert (project_root / name).exists()
        manifest = json.loads((project_root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["input_hash"] == first["input_hash"]
        assert manifest["owner"] == "bsc.knowledge.growth"
        assert manifest["ownership_marker"] == "bsc-growth-distillation/v1"
        assert len(manifest["paths"]) == 5
        for relative, expected_hash in manifest["file_hashes"].items():
            assert hashlib.sha256((root / "projects" / "project-a" / relative).read_bytes()).hexdigest() == expected_hash
    finally:
        repo.close()


def test_distillation_surfaces_unpromoted_horizon_metadata_without_source_body(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-horizon-queue.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        cited = SourceRecord(
            id="horizon-cited",
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://example.test/cited",
            content_hash="a" * 64,
            raw_content="This Horizon signal is already represented by a published Wiki citation.",
            trust_level="reviewed",
            status=SourceStatus.ELIGIBLE,
            metadata={"title": "Already cited signal", "ai_score": 9.2},
        )
        pending = SourceRecord(
            id="horizon-pending",
            project_id="project-a",
            source_type="horizon_signal",
            origin="https://example.test/pending",
            content_hash="b" * 64,
            raw_content="PRIVATE HORIZON BODY MUST NOT BE COPIED INTO THE RADAR QUEUE.",
            trust_level="reviewed",
            status=SourceStatus.ELIGIBLE,
            metadata={"title": "Pending agent signal", "ai_score": 8.7, "task_families": ["context_mapping"]},
        )
        repo.create_source(cited)
        repo.create_source(pending)
        repo.record_publication(
            project_id="project-a",
            contents={
                "wiki/index.md": "# Index\n",
                "wiki/log.md": "# Log\n",
                "wiki/concepts/cited.md": "# Cited\n[source:horizon-cited]\n",
            },
            source_ids=["horizon-cited"],
        )
        # Citation rows are authoritative even before an optional graph rebuild.
        monkeypatch.setattr(repo, "list_lineage", lambda _project_id, limit=500: [])

        result = GrowthDistillationService(repo, root).run_weekly(
            "project-a", "2026-W30", source_cutoff="2100-01-01T00:00:00Z"
        )
        weekly_root = root / "projects" / "project-a" / "distillations" / GrowthDistillationService.WEEKLY_DIRECTORY / "2026-W30"
        summary = (weekly_root / GrowthDistillationService.WEEKLY_DOCUMENTS[0]).read_text(encoding="utf-8")
        actions = (weekly_root / GrowthDistillationService.WEEKLY_DOCUMENTS[1]).read_text(encoding="utf-8")
        context = result["manifest"]["context"]

        assert any(item.get("id") == "horizon-pending" for item in result["manifest"]["inputs"])
        assert context["horizon_signal_queue_ids"] == ["horizon-pending"], context
        assert "[source:horizon-pending]" in summary
        assert "Pending agent signal" in actions
        assert "https://example.test/pending" in actions
        assert "horizon-cited" not in context["horizon_signal_queue_ids"]
        assert "PRIVATE HORIZON BODY" not in summary + actions
        assert context["horizon_signal_queue_ids"] == ["horizon-pending"]
    finally:
        repo.close()


def test_distillation_uses_validated_narrative_provider_and_records_its_mode(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-narrative.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="The project must keep review gates before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        service = GrowthDistillationService(repo, root, narrative_provider=_NarrativeProvider())

        daily = service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        weekly = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")

        daily_path = root / "projects" / "project-a" / daily["paths"][0]
        weekly_path = root / "projects" / "project-a" / weekly["paths"][0]
        assert "# Review-gate evidence changes the project decision context" in daily_path.read_text(encoding="utf-8")
        assert "## Next review" in daily_path.read_text(encoding="utf-8")
        assert "## Open question" in daily_path.read_text(encoding="utf-8")
        assert "[source:source-a]" in daily_path.read_text(encoding="utf-8")
        assert "[source:source-a@revision-a]" not in daily_path.read_text(encoding="utf-8")
        assert "decisive evidence" in weekly_path.read_text(encoding="utf-8")
        assert daily["manifest"]["generation"]["mode"] == "llm"
        assert daily["manifest"]["generation"]["llm_documents"] == ["daily"]
        assert weekly["manifest"]["generation"]["mode"] == "llm"
        assert weekly["manifest"]["distillation_contract_revision"] == GrowthDistillationService.DISTILLATION_CONTRACT_REVISION
    finally:
        repo.close()


def test_distillation_manifest_links_native_model_evidence_to_the_durable_growth_run(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-promptops-link.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="A review gate must remain in the publication workflow.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        provider = _CorrelatedNarrativeProvider()
        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_daily(
            "project-a",
            "2026-07-24",
            source_cutoff="2026-07-24T09:00:00Z",
            knowledge_run_id="growth-run-a",
        )

        promptops = result["manifest"]["generation"]["promptops"]
        assert provider.knowledge_run_ids == ["growth-run-a"]
        assert promptops == {
            "knowledge_run_id": "growth-run-a",
            "prompt_run_id": "prompt-growth-a",
            "agent_manifest_fingerprint": "a" * 64,
            "task": "knowledge_distillation",
            "revision": "growth-distillation-v9",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "attempt_count": 1,
            "retry_count": 0,
            "retry_categories": [],
            "usage": {
                "provider_calls": 1,
                "reported_calls": 1,
                "complete": True,
                "latency_ms": 250,
                "prompt_tokens": 91,
                "completion_tokens": 32,
                "total_tokens": 123,
                "cached_tokens": None,
                "reasoning_tokens": None,
            },
        }
    finally:
        repo.close()


def test_daily_distillation_rejects_a_thin_cited_paragraph_and_uses_the_full_fallback(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-thin-daily.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="A review gate must remain in the publication workflow.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(
            repo,
            root,
            narrative_provider=_ThinCitedDailyProvider(),
        ).run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")

        daily = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert result["manifest"]["generation"] == {
            "mode": "deterministic",
            "provider": "",
            "model": "",
            "reason": "provider_response_rejected",
            "rejection_reasons": {"daily": "invalid_shape"},
        }
        assert "One-line evidence update" not in daily
        assert "# Daily knowledge growth" in daily
        assert "## Incremental change counts" in daily
    finally:
        repo.close()


def test_daily_distillation_prefers_current_primary_capture_over_horizon_discovery_when_budget_is_tight(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-triage-priority.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="legacy-source",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Legacy evidence that should not crowd out current triage. " * 40,
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        repo.create_source(
            SourceRecord(
                id="horizon-current",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="b" * 64,
                raw_content="Current Horizon evidence selected for this project. " * 300,
                trust_level="reviewed",
                status=SourceStatus.VALIDATED,
                metadata={
                    "admission_gate": "project_triage",
                    "relevance": 100,
                    "value": 100,
                    "freshness": 100,
                    "outputability": 100,
                    "connectedness": 100,
                },
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        SourceTriageService(repo).triage_source("project-a", "horizon-current")
        repo.create_source(
            SourceRecord(
                id="primary-current",
                project_id="project-a",
                source_type="primary_web",
                content_hash="c" * 64,
                raw_content="Independent primary capture that corroborates the current project signal. " * 300,
                trust_level="reviewed",
                status=SourceStatus.VALIDATED,
                metadata={
                    "admission_gate": "project_triage",
                    "discovered_from_source_id": "horizon-current",
                    "relevance": 100,
                    "value": 100,
                    "freshness": 100,
                    "outputability": 100,
                    "connectedness": 100,
                },
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        SourceTriageService(repo).triage_source("project-a", "primary-current")

        result = GrowthDistillationService(
            repo,
            root,
            narrative_provider=_UncitedNarrativeProvider(),
        ).run_daily(
            "project-a",
            "2026-07-24",
            source_cutoff="2026-08-01T00:00:00Z",
        )

        assert repo.get_source("project-a", "horizon-current")["status"] == SourceStatus.ELIGIBLE.value
        assert repo.get_source("project-a", "primary-current")["status"] == SourceStatus.ELIGIBLE.value
        assert "horizon-current" not in result["manifest"]["context"]["source_ids"]
        assert "primary-current" in result["manifest"]["context"]["source_ids"]
        assert "primary-current" in result["manifest"]["context"]["citation_source_ids"]
    finally:
        repo.close()


def test_daily_distillation_scopes_multi_topic_evidence_before_accepting_a_model_claim(tmp_path):
    """A cited but irrelevant sentence cannot author a project insight."""
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-evidence-scope.db"))

    class _UnrelatedQuoteProvider:
        def render(self, *, kind, project_id, period, context):
            if kind == "daily":
                return {
                    "daily": {
                        "headline": "Culture becomes an unsupported agent-policy analogy",
                        "signal": "The roundup says 'Slack is the home for great culture' [source:source-a].",
                        "project_implication": "Treat culture as an agent-policy signal [source:source-a].",
                        "next_review": "Review the retained source evidence before acting [source:source-a].",
                        "open_question": "This remains an evidence gap requiring verification [source:source-a].",
                    }
                }
            return _NarrativeProvider().render(kind=kind, project_id=project_id, period=period, context=context)

    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.save_profile(
            ProjectKnowledgeProfile(
                project_id="project-a",
                research_domains=["LLM context engineering and agent orchestration"],
                primary_output_types=["custom SOP"],
            ),
            actor_id="owner",
        )
        unrelated = "Slack is the home for great culture. " + ("Market culture commentary without a project mechanism. " * 120)
        relevant = (
            "Agentic context management lets agents decide when to compress context, "
            "offload information to memory, and retrieve it later."
        )
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="primary_web",
                content_hash="a" * 64,
                raw_content=f"{unrelated}\n\n{relevant}",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        scoped = GrowthDistillationService._daily_source_scope(
            repo.get_source("project-a", "source-a") or {},
            repo.get_profile("project-a") or {},
        )
        assert scoped and "Agentic context management" in scoped
        assert "Slack is the home for great culture" not in scoped

        result = GrowthDistillationService(
            repo,
            root,
            narrative_provider=_UnrelatedQuoteProvider(),
        ).run_daily("project-a", "2026-07-24", source_cutoff="2026-08-01T00:00:00Z")

        assert result["manifest"]["context"]["daily_source_scope_ids"] == ["source-a"]
        assert result["manifest"]["generation"] == {
            "mode": "deterministic",
            "provider": "",
            "model": "",
            "reason": "provider_response_rejected",
            "rejection_reasons": {"daily": "missing_scoped_evidence_quote"},
        }
        rendered = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Slack is the home for great culture" not in rendered
    finally:
        repo.close()


def test_distillation_rejects_uncited_narrative_and_uses_governed_fallback(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-uncited.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(repo, root, narrative_provider=_UncitedNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        assert result["manifest"]["generation"] == {
            "mode": "deterministic",
            "provider": "",
            "model": "",
            "reason": "provider_response_rejected",
        }
        rendered = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Generic weekly update" not in rendered
        assert "source-a" in rendered
        assert all(
            "[source:source-a]" in (root / "projects" / "project-a" / path).read_text(encoding="utf-8")
            for path in result["paths"]
        )
    finally:
        repo.close()


def test_daily_distillation_repairs_an_invalid_model_card_once_without_relaxing_citations(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-quality-repair.db"))
    provider = _DailyRepairNarrativeProvider()
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_daily(
            "project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z"
        )

        generation = result["manifest"]["generation"]
        assert generation["mode"] == "llm"
        assert generation["quality_retry_count"] == 1
        assert provider.feedback[0] == ""
        assert "invalid_reference" in provider.feedback[1]
        daily = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "[source:source-a]" in daily
        assert "[source:forged]" not in daily
    finally:
        repo.close()


def test_distillation_preserves_only_cited_llm_documents_and_records_hybrid_provenance(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-hybrid.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(repo, root, narrative_provider=_PartialNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        generation = result["manifest"]["generation"]
        assert generation["mode"] == "hybrid"
        assert generation["reason"] == "invalid_llm_documents_replaced"
        assert generation["llm_documents"] == [GrowthDistillationService.WEEKLY_DOCUMENTS[0]]
        assert set(generation["fallback_documents"]) == set(GrowthDistillationService.WEEKLY_DOCUMENTS[1:])
        summary = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Bespoke summary" in summary
        assert "Uncited action" not in (root / "projects" / "project-a" / result["paths"][1]).read_text(encoding="utf-8")
    finally:
        repo.close()


def test_weekly_distillation_reserves_a_larger_evidence_context_than_daily(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-context-budget.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        service = GrowthDistillationService(repo, root, narrative_provider=_NarrativeProvider())

        daily = service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        weekly = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")

        assert daily["manifest"]["context"]["character_budget"] == service.DAILY_CONTEXT_CHARACTER_BUDGET
        assert weekly["manifest"]["context"]["character_budget"] == service.WEEKLY_CONTEXT_CHARACTER_BUDGET
        assert weekly["manifest"]["context"]["character_budget"] > daily["manifest"]["context"]["character_budget"]
    finally:
        repo.close()


@pytest.mark.parametrize("degraded_provider", [_PartialNarrativeProvider(), _UnavailableNarrativeProvider()])
def test_incomplete_weekly_generation_cannot_replace_a_published_bundle(tmp_path, degraded_provider):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-preserve-weekly.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        initial = GrowthDistillationService(repo, root, narrative_provider=_NarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )
        weekly_root = root / "projects" / "project-a" / "distillations" / GrowthDistillationService.WEEKLY_DIRECTORY / "2026-W30"
        before = {path.name: path.read_bytes() for path in weekly_root.iterdir() if path.is_file()}

        preserved = GrowthDistillationService(repo, root, narrative_provider=degraded_provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T10:00:00Z"
        )

        assert preserved["status"] == "preserved"
        assert preserved["input_hash"] != initial["input_hash"]
        assert preserved["preserved_input_hash"] == initial["input_hash"]
        assert preserved["paths"] == []
        assert preserved["manifest"]["publication"] == {
            "status": "preserved",
            "reason": "incomplete_llm_generation_cannot_replace_published_weekly_bundle",
            "preserved_input_hash": initial["input_hash"],
            "preserved_generation_mode": "llm",
        }
        assert {path.name: path.read_bytes() for path in weekly_root.iterdir() if path.is_file()} == before
        assert not (weekly_root / "revisions" / preserved["input_hash"]).exists()
        assert len(repo.list_growth_distillations("project-a", "weekly")) == 1
    finally:
        repo.close()


def test_production_fallback_cannot_replace_an_existing_deterministic_weekly_bundle(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-preserve-production-fallback.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        initial = GrowthDistillationService(repo, root, narrative_provider=_UnavailableNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )
        weekly_root = root / "projects" / "project-a" / "distillations" / GrowthDistillationService.WEEKLY_DIRECTORY / "2026-W30"
        before = {path.name: path.read_bytes() for path in weekly_root.iterdir() if path.is_file()}

        preserved = GrowthDistillationService(
            repo, root, narrative_provider=_ProductionUnavailableNarrativeProvider()
        ).run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T10:00:00Z")

        assert initial["manifest"]["generation"]["mode"] == "deterministic"
        assert preserved["status"] == "preserved"
        assert preserved["preserved_input_hash"] == initial["input_hash"]
        assert {path.name: path.read_bytes() for path in weekly_root.iterdir() if path.is_file()} == before
    finally:
        repo.close()


def test_production_weekly_budget_preserves_existing_bundle_without_a_second_model_render(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-production-one-shot.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        GrowthDistillationService(repo, root, narrative_provider=_NarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )
        provider = _ProductionOneShotPartialNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T10:00:00Z"
        )

        assert provider.calls == 1
        assert result["status"] == "preserved"
        assert result["manifest"]["generation"]["reason"] == "invalid_llm_documents_replaced"
    finally:
        repo.close()


def test_production_weekly_budget_repairs_all_rejected_documents_in_one_batch(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-production-batch-repair.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        provider = _ProductionBatchRepairNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        assert provider.targets == [(), tuple(GrowthDistillationService.WEEKLY_DOCUMENTS[1:])]
        assert result["manifest"]["generation"]["mode"] == "llm"
        assert result["manifest"]["generation"]["quality_retry_count"] == 1
        assert result["manifest"]["generation"]["fallback_documents"] == []
    finally:
        repo.close()


def test_production_weekly_uses_one_final_strict_repair_for_a_single_remaining_document(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-production-final-strict-repair.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        provider = _ProductionFinalStrictRepairNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        generation = result["manifest"]["generation"]
        assert provider.calls == 3
        assert provider.targets == [(), (GrowthDistillationService.WEEKLY_DOCUMENTS[0],), (GrowthDistillationService.WEEKLY_DOCUMENTS[0],)]
        assert generation["mode"] == "llm"
        assert generation["fallback_documents"] == []
        assert generation["quality_retry_count"] == 2
    finally:
        repo.close()


def test_production_weekly_uses_final_strict_batch_repair_for_multiple_invalid_references(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-production-final-strict-batch.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        provider = _ProductionFinalStrictBatchRepairNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        rejected = tuple(GrowthDistillationService.WEEKLY_DOCUMENTS[1:])
        generation = result["manifest"]["generation"]
        assert provider.targets == [(), rejected, rejected]
        assert "[source:source-a]" in provider.feedback[-1]
        assert generation["mode"] == "llm"
        assert generation["fallback_documents"] == []
        assert generation["quality_retry_count"] == 2
    finally:
        repo.close()


def test_weekly_distillation_rejects_unsupported_project_state_claims(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-unsupported-state.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="The source describes a tool protocol, not completed project work.",
            trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))

        result = GrowthDistillationService(
            repo, root, narrative_provider=_UnsupportedProjectStateNarrativeProvider()
        ).run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")

        generation = result["manifest"]["generation"]
        assert generation["mode"] == "hybrid"
        assert GrowthDistillationService.WEEKLY_DOCUMENTS[0] in generation["fallback_documents"]
        assert generation["rejection_reasons"][GrowthDistillationService.WEEKLY_DOCUMENTS[0]] == "unsupported_project_state"
        summary = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "we decided to migrate" not in summary
        assert "The source describes a tool protocol" not in summary
    finally:
        repo.close()


@pytest.mark.parametrize(
    "unsupported_fragment",
    [
        "\n\n## Owner\n\nAssign [codex-runtime-repair] to verify the source [source:source-a].",
        "\n\n## Historical state\n\n\u4e0a\u5468\u5df2\u542f\u52a8\u89c4\u8303\u5ba1\u67e5 [source:source-a]",
        "\n\n## Historical review\n\n\u672c\u5468\u5bf9 MCP \u8fdb\u884c\u4e86\u5b9a\u5411\u5ba1\u67e5 [source:source-a]",
        "\n\n## Historical review\n\n\u672c\u5468\u6211\u4eec\u5ba1\u67e5\u4e86 MCP \u5f52\u6863 [source:source-a]",
        "\n\n## Project decision\n\n\u6211\u4eec\u6682\u5b9a\u5c06 MCP \u4f5c\u4e3a\u63d2\u4ef6\u534f\u8bae [source:source-a]",
        "\n\n## Project state\n\n\u9879\u76ee\u5df2\u5c06 MCP \u6807\u8bb0\u4e3a\u7814\u7a76\u6e90 [source:source-a]",
        "\n\n## System state\n\nBSC \u4e0e Obsidian \u5de5\u4f5c\u53f0\u4ecd\u4ee5\u81ea\u5b9a\u4e49\u534f\u8bae\u4e3a\u4e3b [source:source-a]",
        "\n\n## Review outcome\n\nMCP \u5ba1\u67e5\u5f3a\u5316\u4e86\u65b9\u6cd5\u539f\u5219 [source:source-a]",
        "\n\n## Invented scope\n\n\u7ea6 15 \u4e2a\u8282\u70b9\u9700\u8981\u91cd\u65b0\u8fde\u63a5 [source:source-a]",
    ],
)
def test_weekly_markdown_rejects_non_evidence_brackets_and_unbounded_state_claims(unsupported_fragment):
    context = {"source_ids": ["source-a"], "page_ids": []}
    content = _valid_weekly_document("Governed evidence") + unsupported_fragment

    assert GrowthDistillationService._validated_weekly_markdown(content, context) == ""


def test_weekly_distillation_retries_a_rejected_real_provider_draft_once(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-quality-retry.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="A governed review must distinguish evidence from proposed work.",
            trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        provider = _RetryableNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        generation = result["manifest"]["generation"]
        assert len(provider.feedback) == 2
        assert provider.feedback[0] == ""
        assert "Rejected documents" in provider.feedback[1]
        assert generation["mode"] == "llm"
        assert generation["fallback_documents"] == []
        assert generation["quality_retry_count"] == 1
        assert all(
            "we decided to migrate" not in (root / "projects" / "project-a" / path).read_text(encoding="utf-8")
            for path in result["paths"]
        )
    finally:
        repo.close()


def test_weekly_distillation_repairs_only_rejected_documents_and_audits_both_model_calls(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-targeted-retry.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="A governed review must distinguish evidence from proposed work.",
            trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        provider = _TargetedRetryNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a",
            "2026-W30",
            source_cutoff="2026-07-24T09:00:00Z",
            knowledge_run_id="growth-run-targeted",
        )

        rejected_name = GrowthDistillationService.WEEKLY_DOCUMENTS[0]
        assert provider.targets == [(), (rejected_name,)]
        generation = result["manifest"]["generation"]
        assert generation["mode"] == "llm"
        assert generation["fallback_documents"] == []
        assert generation["quality_retry_count"] == 1
        assert generation["promptops"]["provider_invocation_count"] == 2
        assert generation["promptops"]["usage"]["provider_calls"] == 2
        assert generation["promptops"]["usage"]["total_tokens"] == 90
        assert [item["prompt_run_id"] for item in generation["promptops"]["prompt_runs"]] == [
            "prompt-targeted-1",
            "prompt-targeted-2",
        ]
        summary = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Targeted repair evidence" in summary
        assert "we decided to migrate" not in summary
    finally:
        repo.close()


def test_weekly_distillation_rewrites_once_when_every_document_is_rejected(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-whole-batch-retry.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="A governed review must distinguish evidence from proposed work.",
            trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        provider = _AllRejectedTargetedNarrativeProvider()

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        assert provider.targets == [(), ()]
        assert result["manifest"]["generation"]["mode"] == "llm"
        assert result["manifest"]["generation"]["quality_retry_count"] == 1
        assert all(
            "Whole-batch repair evidence" in (root / "projects" / "project-a" / path).read_text(encoding="utf-8")
            for path in result["paths"]
        )
    finally:
        repo.close()


def test_weekly_distillation_allows_one_additional_targeted_repair_before_fallback(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-two-targeted-repairs.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="A governed review must distinguish evidence from proposed work.",
            trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        provider = _TargetedRetryNarrativeProvider(fail_first_target=True)

        result = GrowthDistillationService(repo, root, narrative_provider=provider).run_weekly(
            "project-a",
            "2026-W30",
            source_cutoff="2026-07-24T09:00:00Z",
            knowledge_run_id="growth-run-two-repairs",
        )

        rejected_name = GrowthDistillationService.WEEKLY_DOCUMENTS[0]
        assert provider.targets == [(), (rejected_name,), (rejected_name,)]
        generation = result["manifest"]["generation"]
        assert generation["mode"] == "llm"
        assert generation["quality_retry_count"] == 2
        assert generation["promptops"]["provider_invocation_count"] == 3
        assert generation["promptops"]["usage"]["provider_calls"] == 3
    finally:
        repo.close()


def test_hybrid_fallback_uses_only_records_retained_in_its_bounded_context(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-hybrid-citations.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="Eligible evidence.", trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        repo.create_source(SourceRecord(
            id="source-b", project_id="project-a", source_type="article", content_hash="b" * 64,
            raw_content="Superseded evidence.", trust_level="trusted", status=SourceStatus.SUPERSEDED,
        ))

        result = GrowthDistillationService(repo, root, narrative_provider=_PartialNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        fallback_context = (root / "projects" / "project-a" / result["paths"][3]).read_text(encoding="utf-8")
        assert "[source:source-a]" in fallback_context
        assert "[source:source-b]" not in fallback_context
        assert '"rendered"' not in fallback_context
    finally:
        repo.close()


def test_distillation_contract_revision_participates_in_idempotency_hash(monkeypatch):
    baseline = GrowthDistillationService._input_hash([], "2026-07-24T09:00:00+00:00", "context")
    monkeypatch.setattr(
        GrowthDistillationService,
        "DISTILLATION_CONTRACT_REVISION",
        GrowthDistillationService.DISTILLATION_CONTRACT_REVISION + 1,
    )

    revised = GrowthDistillationService._input_hash([], "2026-07-24T09:00:00+00:00", "context")

    assert revised != baseline


def test_weekly_distillation_interprets_legacy_naive_repository_timestamps_as_shanghai_time(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-naive-timezone.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="article",
            content_hash="a" * 64,
            raw_content="A captured source must remain available to the weekly review.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        ))
        # Older repository writes use local wall-clock timestamps with no
        # offset. At 00:24Z it was already 08:24 in the schedule timezone.
        repo._execute(
            "UPDATE knowledge_sources SET captured_at=?, updated_at=? WHERE project_id=? AND id=?",
            ("2026-07-24T07:13:19", "2026-07-24T07:13:19", "project-a", "source-a"),
        )
        repo._commit()

        result = GrowthDistillationService(repo, root).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T00:24:18.951698Z"
        )

        assert result["manifest"]["context"]["citation_source_ids"] == ["source-a"]
        assert {item["id"] for item in result["manifest"]["inputs"]} >= {"source-a"}
    finally:
        repo.close()


def test_tampered_managed_file_is_never_archived_or_overwritten(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-tamper.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        managed = weekly_root / service.WEEKLY_DOCUMENTS[0]
        managed.write_text("user edited the managed report", encoding="utf-8")

        with pytest.raises(ManagedContentConflictError, match="hash conflict"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")

        assert managed.read_text(encoding="utf-8") == "user edited the managed report"
        assert not (weekly_root / "revisions" / first["input_hash"]).exists()
    finally:
        repo.close()


def test_tampered_manifest_is_rejected_even_when_documents_are_unchanged(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-manifest-tamper.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        manifest_path = weekly_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["inputs"] = [{"type": "source", "id": "forged"}]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ManagedContentConflictError, match="persisted manifest"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
    finally:
        repo.close()


def test_weekly_publish_restores_original_directory_when_final_swap_fails(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-atomic.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        user_file = weekly_root / "user-note.md"
        user_file.write_text("preserve through rollback", encoding="utf-8")
        original_manifest = (weekly_root / "manifest.json").read_bytes()
        real_replace = os.replace

        def fail_final_swap(source, destination):
            if str(source).endswith(".tmp") and os.fspath(destination) == os.fspath(weekly_root):
                raise OSError("simulated final directory swap failure")
            return real_replace(source, destination)

        monkeypatch.setattr("app.knowledge.growth_distillation.os.replace", fail_final_swap)
        with pytest.raises(OSError, match="simulated final"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")

        assert (weekly_root / "manifest.json").read_bytes() == original_manifest
        assert user_file.read_text(encoding="utf-8") == "preserve through rollback"
        assert repo.get_growth_distillation("project-a", "weekly", "2026-W30", first["input_hash"])
    finally:
        repo.close()


def test_daily_revisions_are_owned_redacted_and_user_file_is_protected(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-owned.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        secret = "sk-" + "d" * 32
        repo.register_output(OutputAsset(
            id="secret-output", project_id="project-a", kind="report", content_hash="d" * 64,
            vault_path="outputs/secret/report.md", idempotency_key="secret-output", status="accepted",
            quality={"token": secret, "quality": 90},
        ))
        service = GrowthDistillationService(repo, root)
        first = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        second = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T10:00:00Z")
        daily = root / "projects" / "project-a" / second["paths"][0]
        archive = daily.parent / "revisions" / "2026-07-22" / f"{first['input_hash']}.md"
        assert archive.exists()
        assert "bsc-growth-distillation/v1" in daily.read_text(encoding="utf-8")
        assert secret not in daily.read_text(encoding="utf-8")
        assert secret not in json.dumps(second["manifest"], ensure_ascii=False)

        other_date = daily.with_name("2026-07-23.md")
        other_date.write_text("user-authored daily note", encoding="utf-8")
        with pytest.raises(ManagedContentConflictError, match="unmarked user-authored"):
            service.run_daily("project-a", "2026-07-23", source_cutoff="2026-07-23T09:00:00Z")
        assert other_date.read_text(encoding="utf-8") == "user-authored daily note"
    finally:
        repo.close()


def test_daily_rerun_uses_the_disk_matched_record_when_same_day_timestamps_disagree(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-rerun-order.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        second = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T10:00:00Z")
        repo._execute(
            "UPDATE knowledge_growth_distillations SET created_at=? WHERE id=?",
            ("2099-01-01T00:00:00Z", first["id"]),
        )
        repo._commit()

        third = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T11:00:00Z")

        daily = root / "projects" / "project-a" / third["paths"][0]
        archive = daily.parent / "revisions" / "2026-07-22" / f"{second['input_hash']}.md"
        assert archive.exists()
        assert third["input_hash"] != second["input_hash"]
    finally:
        repo.close()


def test_daily_body_hash_protects_user_edits_after_filesystem_publish_before_db_commit(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-crash-window.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        daily = root / "projects" / "project-a" / first["paths"][0]
        edited = daily.read_text(encoding="utf-8") + "\nUser correction after publish.\n"
        daily.write_text(edited, encoding="utf-8")
        repo._execute("DELETE FROM knowledge_growth_distillations WHERE id=?", (first["id"],))
        repo._commit()

        with pytest.raises(ManagedContentConflictError, match="body hash conflict"):
            service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T10:00:00Z")
        assert daily.read_text(encoding="utf-8") == edited
    finally:
        repo.close()


def test_next_day_daily_digest_compares_with_previous_day_instead_of_readding_history(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-incremental.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.register_output(OutputAsset(
            id="stable-output", project_id="project-a", kind="report", content_hash="e" * 64,
            vault_path="outputs/stable.md", idempotency_key="stable-output", status="accepted",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ))
        service = GrowthDistillationService(repo, root)
        service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        second = service.run_daily("project-a", "2026-07-23", source_cutoff="2026-07-23T09:00:00Z")
        daily = root / "projects" / "project-a" / second["paths"][0]
        content = daily.read_text(encoding="utf-8")
        assert "Added: `0`; changed: `0`; removed: `0`" in content
    finally:
        repo.close()


def test_weekly_manifest_covers_feedback_evaluations_contradictions_and_cutoff(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "weekly-complete-input.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        for source_id in ("source-a", "source-b"):
            repo.create_source(SourceRecord(
                id=source_id,
                project_id="project-a",
                source_type="manual_upload",
                content_hash=hashlib.sha256(source_id.encode()).hexdigest(),
                raw_content=f"Evidence from {source_id}",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
                updated_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
            ))
        repo.create_source(SourceRecord(
            id="future-source",
            project_id="project-a",
            source_type="manual_upload",
            content_hash="f" * 64,
            raw_content="This arrived after the immutable cutoff.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            captured_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
        ))
        repo.register_output(OutputAsset(
            id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
            vault_path="outputs/output-a.md", idempotency_key="output-a", status="accepted",
            source_refs=["source-a"],
            created_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        repo.save_output_evaluation(OutputEvaluation(
            id="eval-a", project_id="project-a", output_id="output-a",
            groundedness=0.9, task_fit=0.9, usefulness=0.9, coherence=0.9, format_quality=0.9,
            findings=["retain exact source references"],
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))
        repo.add_output_feedback(OutputFeedback(
            id="feedback-a", project_id="project-a", output_id="output-a",
            feedback_type=FeedbackType.CORRECTED, correction="Clarify the approval owner.",
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))
        # Saving an evaluation updates the output lifecycle timestamp. Model
        # this complete historical record as having existed before the cutoff.
        repo._execute(
            "UPDATE knowledge_outputs SET updated_at=? WHERE project_id=? AND id=?",
            (_CUTOFF_SAFE_TIME.isoformat(), "project-a", "output-a"),
        )
        repo._commit()
        repo.add_lineage_edge(KnowledgeLineageEdge(
            id="contradiction-a", project_id="project-a",
            from_type="source", from_id="source-a", to_type="source", to_id="source-b",
            relation="source_contradicts_source",
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))

        service = GrowthDistillationService(repo, root)
        result = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")
        manifest = result["manifest"]
        input_types = {item["type"] for item in manifest["inputs"]}
        input_ids = {item["id"] for item in manifest["inputs"]}
        assert {"source", "output", "evaluation", "feedback", "lineage"} <= input_types
        assert "future-source" not in input_ids
        assert manifest["source_cutoff"] == "2026-07-24T09:00:00+00:00"

        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        summary = (weekly_root / "00-本周总结.md").read_text(encoding="utf-8")
        methods = (weekly_root / "04-方法迭代.md").read_text(encoding="utf-8")
        assert "Contradictions requiring review: `1`" in summary
        assert "feedback-a" in methods
        assert "eval-a" in methods
    finally:
        repo.close()


def test_changed_weekly_input_preserves_previous_managed_revision_and_user_file(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-revision.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        (weekly_root / "user-note.md").write_text("keep me", encoding="utf-8")
        second = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")
        assert second["input_hash"] != first["input_hash"]
        assert (weekly_root / "revisions" / first["input_hash"] / "manifest.json").exists()
        assert (weekly_root / "user-note.md").read_text(encoding="utf-8") == "keep me"
    finally:
        repo.close()


def test_weekly_context_uses_published_b_page_without_duplicating_rules_or_audit_log(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-context-pages.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        project_root = root / "projects" / "project-a"
        project_root.mkdir(parents=True)
        (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
        source = SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            content_hash="a" * 64,
            raw_content="The ABCD loop requires immutable evidence.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        )
        repo.create_source(source)
        repo.record_publication(
            project_id="project-a",
            contents={
                "AGENTS.md": build_default_agents_rules("project-a"),
                "wiki/index.md": "# Index\n- [[wiki/concepts/loop.md]]\n",
                "wiki/log.md": "# Log\n- Publication event\n",
                "wiki/concepts/loop.md": (
                    "---\ntitle: ABCD loop\nkind: concept\n---\n"
                    "ABCD governs knowledge growth. [source:source-a]\n"
                ),
            },
            source_ids=["source-a"],
        )

        result = GrowthDistillationService(repo, root).run_weekly(
            "project-a", "2026-W30", source_cutoff="2100-01-01T00:00:00Z"
        )
        context = result["manifest"]["context"]
        page_by_path = {page["path"]: page["id"] for page in repo.list_pages("project-a")}

        assert page_by_path["wiki/concepts/loop.md"] in context["page_ids"]
        assert page_by_path["AGENTS.md"] not in context["page_ids"]
        assert page_by_path["wiki/log.md"] not in context["page_ids"]
    finally:
        repo.close()
