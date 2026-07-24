"""Profile-bound, reproducible source triage for the A evidence layer."""

from __future__ import annotations

import hashlib
import json
import re
from time import perf_counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.capture_adapters import redact_secrets
from app.knowledge.growth_contracts import (
    ProjectKnowledgeProfile,
    SourceTriage,
    TriageDisposition,
    evaluate_priority,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceStatus


_ADMITTED_DISPOSITIONS = frozenset({
    TriageDisposition.KNOWLEDGE_CANDIDATE,
    TriageDisposition.REFERENCE,
})


def requires_project_triage(source: dict[str, Any]) -> bool:
    """Return whether discovery evidence needs current project-specific admission."""
    metadata = source.get("metadata") or {}
    return (
        source.get("source_type") == "horizon_signal"
        or metadata.get("admission_gate") == "project_triage"
    )


def current_project_triage_decisions(repository: Any, project_id: str) -> dict[str, dict[str, Any]]:
    """Return the latest evaluator decision for each source under the active profile."""
    triage_repository = repository
    if not hasattr(triage_repository, "list_triage"):
        triage_repository = GrowthRepository.borrow(repository)
    profile = triage_repository.get_profile(project_id) or {"revision": 0}
    profile_revision = int(profile.get("revision", 0) or 0)
    decisions: dict[str, dict[str, Any]] = {}
    for item in triage_repository.list_triage(project_id, limit=500):
        if int(item.get("profile_revision", -1)) != profile_revision:
            continue
        source_id = str(item.get("source_id") or "")
        if not source_id:
            continue
        previous = decisions.get(source_id)
        if previous is None or (
            str(item.get("created_at") or ""), str(item.get("id") or "")
        ) > (
            str(previous.get("created_at") or ""), str(previous.get("id") or "")
        ):
            decisions[source_id] = item
    return decisions


def source_admission_reason(
    repository: Any,
    project_id: str,
    source: dict[str, Any],
    *,
    current_decisions: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Explain why an otherwise eligible discovery source cannot be used yet."""
    if not requires_project_triage(source) or source.get("status") == SourceStatus.PROCESSED.value:
        return ""
    decision = (current_decisions or current_project_triage_decisions(repository, project_id)).get(
        str(source.get("id") or "")
    )
    if decision is None:
        return "current_project_triage_missing"
    if decision.get("evaluator_status") != "completed":
        return "project_triage_unavailable"
    if not bool(decision.get("reliability_pass")):
        return "project_triage_reliability_failed"
    if decision.get("disposition") not in {item.value for item in _ADMITTED_DISPOSITIONS}:
        return "project_triage_not_admitted"
    return ""


class TriageEvaluation(BaseModel):
    """Inspectable output shared by deterministic and optional model evaluators."""

    model_config = ConfigDict(extra="forbid")

    relevance: int = Field(ge=0, le=100)
    value: int = Field(ge=0, le=100)
    freshness: int = Field(ge=0, le=100)
    outputability: int = Field(ge=0, le=100)
    connectedness: int = Field(ge=0, le=100)
    evaluator_revision: str = Field(min_length=1, max_length=200)
    status: Literal["completed", "unavailable", "failed"] = "completed"
    latency_ms: int = Field(default=0, ge=0)
    reasons: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, values: list[str]) -> list[str]:
        normalized = [str(redact_secrets(value)).strip() for value in values]
        if any(not value or len(value) > 1_000 for value in normalized):
            raise ValueError("triage reasons must be non-empty and at most 1000 characters")
        return normalized


class SourceTriageEvaluator(Protocol):
    def evaluate(self, *, source: dict[str, Any], profile: ProjectKnowledgeProfile) -> TriageEvaluation: ...


class MetadataTriageEvaluator:
    """Deterministic policy evaluator for explicit normalized source signals."""

    revision = "profile-aware-v2"
    _PROFILE_STOPWORDS = frozenset({
        "and", "for", "from", "into", "project", "projects", "specific",
        "system", "systems", "the", "this", "with", "workflow", "workflows",
    })

    def evaluate(self, *, source: dict[str, Any], profile: ProjectKnowledgeProfile) -> TriageEvaluation:
        metadata = source.get("metadata") or {}
        relevance, profile_reasons = self._relevance(source=source, metadata=metadata, profile=profile)
        return TriageEvaluation(
            relevance=relevance,
            value=self._component(metadata, "value", fallback=metadata.get("value_score")),
            freshness=self._component(metadata, "freshness", fallback=metadata.get("freshness_score")),
            outputability=self._component(metadata, "outputability", fallback=metadata.get("outputability_score")),
            connectedness=self._component(metadata, "connectedness", fallback=metadata.get("connectedness_score")),
            evaluator_revision=self.revision,
            reasons=[f"profile_domains={len(profile.research_domains)}", *profile_reasons],
        )

    @classmethod
    def _relevance(
        cls,
        *,
        source: dict[str, Any],
        metadata: dict[str, Any],
        profile: ProjectKnowledgeProfile,
    ) -> tuple[int, list[str]]:
        if "relevance" in metadata:
            return cls._component(metadata, "relevance"), ["profile_relevance=explicit"]

        horizon_signal = cls._component(
            metadata,
            "relevance",
            fallback=metadata.get("ai_score"),
            fallback_scale=10,
        )
        signals = cls._profile_signals(profile)
        searchable = cls._searchable_text(source, metadata)
        matched = [
            label
            for label, terms in signals
            if all(term in searchable[1] for term in terms)
        ]
        if not matched:
            # A generic model importance score is not project relevance. Keep
            # unaligned discoveries reviewable, but stop them from dominating
            # a project-specific SOP or weekly context.
            return max(20, min(55, horizon_signal - 30)), ["profile_matches=none"]

        # One concrete domain match restores the discovery score; additional
        # independent matches reward material that connects multiple current
        # project concerns without exceeding the normalized 0-100 range.
        relevance = min(100, max(75, horizon_signal) + min(20, (len(matched) - 1) * 10))
        return relevance, [f"profile_matches={','.join(matched[:5])}"]

    @classmethod
    def _profile_signals(cls, profile: ProjectKnowledgeProfile) -> tuple[tuple[str, tuple[str, ...]], ...]:
        signals: dict[str, tuple[str, ...]] = {}
        for value in profile.research_domains:
            normalized = cls._normalize(value)
            chinese = tuple(chunk for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", normalized) if len(chunk) >= 2)
            if chinese:
                signals["-".join(chinese)] = chinese
                continue
            tokens = [
                token[:-1] if token.endswith("s") and len(token) > 4 else token
                for token in re.findall(r"[a-z0-9]+", normalized)
            ]
            terms = tuple(
                token
                for token in tokens
                if token not in cls._PROFILE_STOPWORDS and token not in {"ai", "research"}
            )
            if not terms:
                continue
            # Obsidian is a named tool boundary, while multi-word domains need
            # all meaningful words to avoid matching unrelated generic prose.
            if "obsidian" in terms:
                signals["obsidian"] = ("obsidian",)
            else:
                signals["-".join(terms)] = terms

        output_terms = {
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for value in profile.primary_output_types
            for token in re.findall(r"[a-z0-9]+", cls._normalize(value))
        }
        for token in sorted(output_terms & {"prd", "sop", "distillation", "workbench", "playbook"}):
            signals[token] = (token,)
        return tuple(sorted(signals.items()))

    @classmethod
    def _searchable_text(cls, source: dict[str, Any], metadata: dict[str, Any]) -> tuple[str, frozenset[str]]:
        text = "\n".join(
            (
                str(source.get("raw_content") or ""),
                str(source.get("origin") or ""),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str),
            )
        )
        normalized = cls._normalize(text)
        tokens = frozenset(
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for token in re.findall(r"[a-z0-9]+", normalized)
        )
        return normalized, tokens

    @staticmethod
    def _normalize(value: Any) -> str:
        return re.sub(r"[-_/]+", " ", str(value or "").lower())

    @staticmethod
    def _component(
        metadata: dict[str, Any],
        key: str,
        *,
        fallback: Any = None,
        fallback_scale: int = 100,
    ) -> int:
        explicit = key in metadata
        value = metadata.get(key) if explicit else fallback
        if value is None:
            return 50
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 50
        if not explicit and fallback_scale == 10 and 0 <= number <= 10:
            number *= 10
        return max(0, min(100, round(number)))


class SourceTriageService:
    def __init__(self, repository: GrowthRepository, *, evaluator: SourceTriageEvaluator | None = None) -> None:
        self.repository = repository
        self.evaluator = evaluator or MetadataTriageEvaluator()

    def triage_source(
        self,
        project_id: str,
        source_id: str,
        *,
        evaluator_revision: str | None = None,
    ) -> dict[str, Any]:
        source = self.repository.get_source(project_id, source_id)
        if not source:
            raise KeyError("source not found in project")
        if source["status"] not in {
            SourceStatus.CAPTURED.value,
            SourceStatus.VALIDATED.value,
            SourceStatus.ELIGIBLE.value,
        }:
            raise ValueError("only captured, validated, or eligible sources can be triaged")
        profile_data = self.repository.get_profile(project_id)
        profile = ProjectKnowledgeProfile.model_validate(profile_data or {"project_id": project_id})
        evaluation = self._evaluate(source=source, profile=profile)
        if evaluator_revision:
            evaluation = evaluation.model_copy(update={"evaluator_revision": evaluator_revision})

        existing = self._existing_decision(
            project_id,
            source_id,
            profile_revision=profile.revision,
            evaluator_revision=evaluation.evaluator_revision,
        )
        if existing:
            return existing

        reliable, reliability_reasons = self._reliability(source)
        priority = self._priority(evaluation)
        research_question = bool(
            (source.get("metadata") or {}).get("research_question")
            or (source.get("metadata") or {}).get("unanswered_question")
        )
        disposition = self._disposition(priority, reliable, research_question, evaluation.value)
        reasons = [
            f"priority={priority}",
            f"reliability={'pass' if reliable else 'fail'}",
            f"profile_revision={profile.revision}",
            f"latency_ms={evaluation.latency_ms}",
            *reliability_reasons,
            *evaluation.reasons,
        ]
        if research_question:
            reasons.append("unanswered_research_question")
        triage_id = hashlib.sha256(
            f"{project_id}|{source_id}|{profile.revision}|{evaluation.evaluator_revision}".encode("utf-8")
        ).hexdigest()[:24]
        triage = SourceTriage(
            id=triage_id,
            project_id=project_id,
            source_id=source_id,
            profile_revision=profile.revision,
            relevance=evaluation.relevance,
            value=evaluation.value,
            freshness=evaluation.freshness,
            outputability=evaluation.outputability,
            connectedness=evaluation.connectedness,
            reliability_pass=reliable,
            disposition=disposition,
            reasons=reasons,
            evaluator_revision=evaluation.evaluator_revision,
            evaluator_status=evaluation.status,
        )
        try:
            result = self.repository.save_triage(triage)
        except Exception:
            # A concurrent idempotent writer may have won the unique-key race.
            result = self._existing_decision(
                project_id,
                source_id,
                profile_revision=profile.revision,
                evaluator_revision=evaluation.evaluator_revision,
            )
            if result is None:
                raise
        admitted = (
            evaluation.status == "completed"
            and reliable
            and disposition in _ADMITTED_DISPOSITIONS
        )
        if admitted and source["status"] != SourceStatus.ELIGIBLE.value:
            self.repository.update_source_status(project_id, source_id, SourceStatus.ELIGIBLE)
        elif (
            not admitted
            and requires_project_triage(source)
            and source["status"] == SourceStatus.ELIGIBLE.value
        ):
            self.repository.return_source_to_review(
                project_id,
                source_id,
                reason=f"triage:{evaluation.evaluator_revision}:{disposition.value}",
            )
        return result

    def _evaluate(
        self,
        *,
        source: dict[str, Any],
        profile: ProjectKnowledgeProfile,
    ) -> TriageEvaluation:
        started = perf_counter()
        try:
            return TriageEvaluation.model_validate(self.evaluator.evaluate(source=source, profile=profile))
        except Exception as exc:
            latency_ms = max(0, round((perf_counter() - started) * 1_000))
            revision = str(getattr(self.evaluator, "revision", "evaluator-unavailable")).strip()
            return TriageEvaluation(
                relevance=0,
                value=0,
                freshness=0,
                outputability=0,
                connectedness=0,
                evaluator_revision=revision or "evaluator-unavailable",
                status="unavailable",
                latency_ms=latency_ms,
                reasons=[f"evaluator_exception={type(exc).__name__}"],
            )

    def triage_project(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        sources = self.repository.list_sources(project_id, status=SourceStatus.VALIDATED.value)
        sources.extend(
            source for source in self.repository.list_sources(project_id, status=SourceStatus.ELIGIBLE.value)
            if requires_project_triage(source)
        )
        bounded = max(1, min(limit, 500))
        return [self.triage_source(project_id, source["id"]) for source in sources[:bounded]]

    def list_research_topics(self, project_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        decisions = self.repository.list_triage(
            project_id,
            limit=max(1, min(limit, 500)),
            disposition=TriageDisposition.RESEARCH_TOPIC.value,
        )
        return [
            {
                "type": "research_topic",
                "project_id": project_id,
                "source_id": decision["source_id"],
                "triage_id": decision["id"],
                "reasons": decision.get("reasons", []),
                "status": "recommended",
            }
            for decision in decisions
        ]

    def _existing_decision(
        self,
        project_id: str,
        source_id: str,
        *,
        profile_revision: int,
        evaluator_revision: str,
    ) -> dict[str, Any] | None:
        # The current repository exposes bounded project listing but no scoped
        # point lookup for this compound key.
        for decision in self.repository.list_triage(project_id, limit=500):
            if (
                decision.get("source_id") == source_id
                and int(decision.get("profile_revision", -1)) == profile_revision
                and decision.get("evaluator_revision") == evaluator_revision
            ):
                return decision
        return None

    @staticmethod
    def _priority(evaluation: TriageEvaluation) -> int:
        return evaluate_priority(
            evaluation.relevance,
            evaluation.value,
            evaluation.freshness,
            evaluation.outputability,
            evaluation.connectedness,
        )

    @staticmethod
    def _disposition(
        priority: int,
        reliable: bool,
        research_question: bool,
        value_score: int,
    ) -> TriageDisposition:
        if research_question and not reliable and value_score >= 60:
            return TriageDisposition.RESEARCH_TOPIC
        if priority >= 80 and reliable:
            return TriageDisposition.KNOWLEDGE_CANDIDATE
        if priority >= 60:
            return TriageDisposition.REFERENCE
        if priority >= 40:
            return TriageDisposition.ARCHIVE
        return TriageDisposition.IGNORE

    @staticmethod
    def _reliability(source: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        trust_level = str(source.get("trust_level") or "untrusted")
        if trust_level not in {"trusted", "reviewed"}:
            reasons.append("source_not_trusted_or_reviewed")
        assessment = (source.get("metadata") or {}).get("policy_assessment") or {}
        extraction = str(assessment.get("extraction_quality") or (source.get("metadata") or {}).get("extraction_status") or "complete")
        extraction_ok = extraction not in {
            "failed",
            "unsupported",
            "encoding_error",
            "extraction_unavailable",
        }
        if not extraction_ok:
            reasons.append(f"extraction_{extraction}")
        return trust_level in {"trusted", "reviewed"} and extraction_ok, reasons
