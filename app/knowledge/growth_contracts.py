"""Typed contracts for the governed A/B/C/D knowledge-growth loop."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import math
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid4().hex[:24]


def _path(value: str) -> str:
    raw = (value or "").strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if not raw or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("path must be a non-empty project-relative POSIX path")
    if candidate.parts and ":" in candidate.parts[0]:
        raise ValueError("path must not include a drive prefix")
    return candidate.as_posix()


class GrowthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    @model_validator(mode="after")
    def bound_structured_payloads(self) -> "GrowthModel":
        """Keep user/model supplied JSON fields bounded at every entry point."""
        for field_name in ("metadata", "manifest", "eval_summary", "quality", "package_audit"):
            value = getattr(self, field_name, None)
            if value is None:
                continue
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            if len(encoded) > 65_536:
                raise ValueError(f"{field_name} exceeds the bounded 65536-byte size")
        return self


class TriageDisposition(str, Enum):
    RESEARCH_TOPIC = "research_topic"
    KNOWLEDGE_CANDIDATE = "knowledge_candidate"
    REFERENCE = "reference"
    ARCHIVE = "archive"
    IGNORE = "ignore"


class KnowledgeCandidateType(str, Enum):
    """The independently extracted Cangjie evidence perspectives."""

    FRAMEWORK = "framework"
    PRINCIPLE = "principle"
    CASE = "case"
    COUNTEREXAMPLE = "counterexample"
    GLOSSARY = "glossary"


class KnowledgeCandidateStatus(str, Enum):
    """Candidates are review artifacts, never directly publishable assets."""

    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MethodStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class OutputStatus(str, Enum):
    REGISTERED = "registered"
    EVALUATING = "evaluating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FILED = "filed"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


# A filed output has already passed the acceptance gate. Filing makes its
# immutable Vault artifact durable; it must not make the result disappear from
# governed reuse, method evidence, or product reporting.
VERIFIED_OUTPUT_STATUSES = frozenset({
    OutputStatus.ACCEPTED.value,
    OutputStatus.FILED.value,
})


def is_verified_output_status(value: OutputStatus | str | None) -> bool:
    """Return whether an output completed evaluation and remains reusable."""
    status = value.value if isinstance(value, OutputStatus) else str(value or "")
    return status in VERIFIED_OUTPUT_STATUSES


class FeedbackType(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    RATED = "rated"
    REUSED = "reused"


class FeedbackStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class KnowledgeFailureCode(str, Enum):
    """Stable, reviewable reasons a governed knowledge operation did not work."""

    GROUNDING_DRIFT = "grounding_drift"
    CHUNK_SEGMENTATION = "chunk_segmentation"
    EMBEDDING_MISMATCH = "embedding_mismatch"
    STALE_INDEX = "stale_index"
    LONG_CHAIN_DRIFT = "long_chain_drift"
    SOURCE_CAPTURE_FAILURE = "source_capture_failure"
    ROUTING_MISMATCH = "routing_mismatch"
    EVALUATION_BLIND_SPOT = "evaluation_blind_spot"
    TOOL_MISUSE = "tool_misuse"
    MEMORY_CONTEXT_DEFECT = "memory_context_defect"
    DEPENDENCY_UNREADY = "dependency_unready"
    CONFIGURATION_DRIFT = "configuration_drift"
    PROJECT_SCOPE_INTERFERENCE = "project_scope_interference"


class KnowledgeFailurePattern(str, Enum):
    """Stable P01-P12 taxonomy for cross-run knowledge diagnostics."""

    P01_GROUNDING_DRIFT = "P01"
    P02_CHUNK_BOUNDARY = "P02"
    P03_EMBEDDING_MISMATCH = "P03"
    P04_INDEX_STALENESS = "P04"
    P05_ROUTER_MISALIGNMENT = "P05"
    P06_LONG_CHAIN_DRIFT = "P06"
    P07_TOOL_MISUSE = "P07"
    P08_MEMORY_DEFECT = "P08"
    P09_EVAL_BLIND_SPOT = "P09"
    P10_DEPENDENCY_READINESS = "P10"
    P11_CONFIGURATION_DRIFT = "P11"
    P12_TENANT_INTERFERENCE = "P12"


FAILURE_PATTERN_BY_CODE: dict[KnowledgeFailureCode, KnowledgeFailurePattern] = {
    KnowledgeFailureCode.GROUNDING_DRIFT: KnowledgeFailurePattern.P01_GROUNDING_DRIFT,
    KnowledgeFailureCode.CHUNK_SEGMENTATION: KnowledgeFailurePattern.P02_CHUNK_BOUNDARY,
    KnowledgeFailureCode.EMBEDDING_MISMATCH: KnowledgeFailurePattern.P03_EMBEDDING_MISMATCH,
    KnowledgeFailureCode.STALE_INDEX: KnowledgeFailurePattern.P04_INDEX_STALENESS,
    KnowledgeFailureCode.ROUTING_MISMATCH: KnowledgeFailurePattern.P05_ROUTER_MISALIGNMENT,
    KnowledgeFailureCode.LONG_CHAIN_DRIFT: KnowledgeFailurePattern.P06_LONG_CHAIN_DRIFT,
    KnowledgeFailureCode.TOOL_MISUSE: KnowledgeFailurePattern.P07_TOOL_MISUSE,
    KnowledgeFailureCode.MEMORY_CONTEXT_DEFECT: KnowledgeFailurePattern.P08_MEMORY_DEFECT,
    KnowledgeFailureCode.EVALUATION_BLIND_SPOT: KnowledgeFailurePattern.P09_EVAL_BLIND_SPOT,
    # Capture failures are availability/readiness failures unless an operator
    # explicitly records a more specific primary pattern at creation time.
    KnowledgeFailureCode.SOURCE_CAPTURE_FAILURE: KnowledgeFailurePattern.P10_DEPENDENCY_READINESS,
    KnowledgeFailureCode.DEPENDENCY_UNREADY: KnowledgeFailurePattern.P10_DEPENDENCY_READINESS,
    KnowledgeFailureCode.CONFIGURATION_DRIFT: KnowledgeFailurePattern.P11_CONFIGURATION_DRIFT,
    KnowledgeFailureCode.PROJECT_SCOPE_INTERFERENCE: KnowledgeFailurePattern.P12_TENANT_INTERFERENCE,
}


def default_failure_pattern(code: KnowledgeFailureCode) -> KnowledgeFailurePattern:
    """Map every governed failure code to the P01-P12 primary diagnosis."""
    return FAILURE_PATTERN_BY_CODE[code]


class KnowledgeFailureStatus(str, Enum):
    OPEN = "open"
    RETRY_SCHEDULED = "retry_scheduled"
    RESOLVED = "resolved"


class ProjectSourcePolicy(GrowthModel):
    """Revisioned, project-scoped admission and retention rules for evidence."""

    primary_origin_prefixes: list[str] = Field(default_factory=list, max_length=100)
    trusted_origin_prefixes: list[str] = Field(default_factory=list, max_length=100)
    community_origin_prefixes: list[str] = Field(default_factory=list, max_length=100)
    blocked_origin_prefixes: list[str] = Field(default_factory=list, max_length=100)
    trusted_source_types: list[str] = Field(default_factory=lambda: ["manual_upload"], max_length=100)
    require_triage_source_types: list[str] = Field(default_factory=lambda: ["horizon_signal"], max_length=100)
    primary_retention_days: int = Field(default=730, ge=1, le=3_650)
    trusted_retention_days: int = Field(default=365, ge=1, le=3_650)
    community_retention_days: int = Field(default=90, ge=1, le=3_650)
    untrusted_retention_days: int = Field(default=30, ge=1, le=3_650)

    @field_validator(
        "primary_origin_prefixes",
        "trusted_origin_prefixes",
        "community_origin_prefixes",
        "blocked_origin_prefixes",
    )
    @classmethod
    def normalize_origin_prefixes(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if len(normalized) != len(values):
            raise ValueError("origin prefixes must be non-empty and unique")
        if any(len(value) > 2_000 for value in normalized):
            raise ValueError("origin prefix exceeds 2000 characters")
        return normalized

    @field_validator("trusted_source_types", "require_triage_source_types")
    @classmethod
    def normalize_source_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))
        if len(normalized) != len(values):
            raise ValueError("source types must be non-empty and unique")
        if any(len(value) > 100 for value in normalized):
            raise ValueError("source type exceeds 100 characters")
        return normalized


class ExternalWorkerPolicy(GrowthModel):
    """Revisioned project permission for a provider-neutral HTTPS worker.

    The policy stores only a server-side credential *reference*.  API clients,
    exports and Artifact Graph records never carry the credential value.
    """

    enabled: bool = False
    worker_ids: list[str] = Field(default_factory=list, max_length=20)
    allowed_model_ids: list[str] = Field(default_factory=list, max_length=50)
    allowed_https_hosts: list[str] = Field(default_factory=list, max_length=20)
    allowed_capabilities: list[str] = Field(default_factory=list, max_length=50)
    credential_ref: str = Field(default="", max_length=160)
    allowed_environments: list[str] = Field(default_factory=lambda: ["test"], max_length=5)
    max_calls: int = Field(default=0, ge=0, le=10_000)
    max_concurrent: int = Field(default=1, ge=1, le=20)
    max_cost_microusd: int = Field(default=0, ge=0, le=1_000_000_000)
    timeout_seconds: int = Field(default=60, ge=1, le=600)

    @field_validator("worker_ids", "allowed_model_ids", "allowed_capabilities", "allowed_environments")
    @classmethod
    def normalize_identifiers(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if len(normalized) != len(values) or any(len(value) > 100 for value in normalized):
            raise ValueError("worker policy identifiers must be unique, non-empty and at most 100 characters")
        return normalized

    @field_validator("allowed_https_hosts")
    @classmethod
    def normalize_hosts(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))
        if len(normalized) != len(values) or any("/" in value or ":" in value or len(value) > 253 for value in normalized):
            raise ValueError("allowed HTTPS hosts must be unique host names without schemes, paths or ports")
        return normalized

    @model_validator(mode="after")
    def require_complete_enabled_policy(self) -> "ExternalWorkerPolicy":
        if not self.enabled:
            return self
        if not self.worker_ids or not self.allowed_model_ids or not self.allowed_https_hosts or not self.allowed_capabilities:
            raise ValueError("enabled external worker policy requires workers, models, HTTPS hosts and capabilities")
        if not self.credential_ref or self.max_calls < 1 or self.max_cost_microusd < 1:
            raise ValueError("enabled external worker policy requires credential reference and positive call/cost budgets")
        if any(value.lower() in {"production", "prod"} for value in self.allowed_environments):
            raise ValueError("external workers are restricted to non-production environments")
        return self


class ProjectKnowledgeProfile(GrowthModel):
    project_id: str = Field(min_length=1)
    revision: int = Field(default=0, ge=0)
    research_domains: list[str] = Field(default_factory=list)
    user_role: str = ""
    primary_output_types: list[str] = Field(default_factory=lambda: ["markdown"])
    target_audiences: list[str] = Field(default_factory=list)
    preferred_channels: list[str] = Field(default_factory=list)
    language: str = "zh-CN"
    content_voice: str = "clear, evidence-backed, practical"
    evidence_threshold: int = Field(default=80, ge=0, le=100)
    automatic_publication_policy: str = "review"
    method_promotion_policy: str = "gated"
    source_policy: ProjectSourcePolicy = Field(default_factory=ProjectSourcePolicy)
    external_worker_policy: ExternalWorkerPolicy = Field(default_factory=ExternalWorkerPolicy)
    actor_id: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


def evaluate_priority(relevance: int, value: int, freshness: int, outputability: int, connectedness: int) -> int:
    """Apply the PRD's weighted triage formula and round to a whole score."""
    scores = (relevance, value, freshness, outputability, connectedness)
    if any(score < 0 or score > 100 for score in scores):
        raise ValueError("triage scores must be between 0 and 100")
    return math.floor(relevance * 0.30 + value * 0.25 + freshness * 0.15 + outputability * 0.15 + connectedness * 0.15 + 0.5)


class SourceTriage(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    profile_revision: int = Field(ge=0)
    relevance: int = Field(ge=0, le=100)
    value: int = Field(ge=0, le=100)
    freshness: int = Field(ge=0, le=100)
    outputability: int = Field(ge=0, le=100)
    connectedness: int = Field(ge=0, le=100)
    priority: int = Field(default=-1, ge=0, le=100)
    reliability_pass: bool
    disposition: TriageDisposition
    reasons: list[str] = Field(default_factory=list)
    evaluator_revision: str = "deterministic-v1"
    evaluator_status: str = "completed"
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def calculate_priority(self) -> "SourceTriage":
        calculated = evaluate_priority(self.relevance, self.value, self.freshness, self.outputability, self.connectedness)
        if self.priority not in {-1, calculated}:
            raise ValueError("priority does not match the component scores")
        self.priority = calculated
        return self


class CandidateEvidenceAnchor(GrowthModel):
    """A short, exact pointer into the immutable source used by a candidate."""

    source_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(min_length=64, max_length=128, pattern=r"^[a-f0-9]{64,128}$")
    anchor: str = Field(min_length=1, max_length=240)
    quote: str = Field(min_length=12, max_length=1_200)


class KnowledgeCandidate(GrowthModel):
    """A Cangjie-style extracted fact awaiting an explicit human decision.

    It deliberately is not a Wiki page, method proposal, or published skill.
    Its evidence is bound to one immutable source revision so a later source
    replacement cannot silently alter the meaning of an existing candidate.
    """

    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1, max_length=128)
    source_content_hash: str = Field(min_length=64, max_length=128, pattern=r"^[a-f0-9]{64,128}$")
    extraction_run_id: str = Field(min_length=1, max_length=128)
    candidate_type: KnowledgeCandidateType
    title: str = Field(min_length=3, max_length=240)
    claim: str = Field(min_length=12, max_length=2_000)
    explanation: str = Field(default="", max_length=4_000)
    evidence: list[CandidateEvidenceAnchor] = Field(min_length=1, max_length=5)
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    status: KnowledgeCandidateStatus = KnowledgeCandidateStatus.PENDING_REVIEW
    reviewer_id: str = Field(default="", max_length=160)
    review_note: str = Field(default="", max_length=2_000)
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def bind_candidate_evidence_and_review(self) -> "KnowledgeCandidate":
        quoted = [anchor.quote for anchor in self.evidence]
        if len(quoted) != len(set(quoted)):
            raise ValueError("candidate evidence quotes must be distinct")
        if any(
            anchor.source_id != self.source_id or anchor.content_hash != self.source_content_hash
            for anchor in self.evidence
        ):
            raise ValueError("candidate evidence must bind to its immutable source id and content hash")
        reviewed = self.status in {KnowledgeCandidateStatus.ACCEPTED, KnowledgeCandidateStatus.REJECTED}
        if reviewed and (not self.reviewer_id.strip() or self.reviewed_at is None):
            raise ValueError("reviewed candidates require reviewer_id and reviewed_at")
        if not reviewed and (self.reviewer_id or self.review_note or self.reviewed_at is not None):
            raise ValueError("pending candidates cannot contain a review decision")
        return self


class MethodAsset(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    slug: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1)
    applicability: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    status: MethodStatus = MethodStatus.CANDIDATE
    active_revision_id: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class MethodRevision(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    method_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    body: str = Field(min_length=1)
    manifest: dict[str, Any] = Field(default_factory=dict)
    eval_summary: dict[str, Any] = Field(default_factory=dict)
    status: MethodStatus = MethodStatus.CANDIDATE
    created_at: datetime = Field(default_factory=_now)


class MethodProposal(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    method_id: str = ""
    operation: str = Field(min_length=1)
    body: str = Field(min_length=1)
    manifest: dict[str, Any] = Field(default_factory=dict)
    source_output_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    status: MethodStatus = MethodStatus.CANDIDATE
    package_audit: dict[str, Any] = Field(default_factory=dict)
    eval_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class MethodEvolutionStatus(str, Enum):
    RUNNING = "running"
    ELIGIBLE_FOR_REVIEW = "eligible_for_review"
    DISCARDED = "discarded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MethodEvolutionDecision(str, Enum):
    PENDING = "pending"
    RETAIN = "retain"
    DISCARD = "discard"
    UNAVAILABLE = "unavailable"


class MethodEvolutionRun(GrowthModel):
    """A durable, single-variable method-improvement experiment."""

    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    method_id: str = Field(min_length=1)
    baseline_revision_id: str = Field(min_length=1)
    mutation_dimension: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=24, max_length=4_000)
    supporting_output_ids: list[str] = Field(min_length=3, max_length=100)
    candidate_proposal_id: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=32, max_length=128)
    evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    decision: MethodEvolutionDecision = MethodEvolutionDecision.PENDING
    rollback_revision_id: str = Field(min_length=1)
    status: MethodEvolutionStatus = MethodEvolutionStatus.RUNNING
    idempotency_key: str = Field(min_length=1, max_length=200)
    actor_id: str = Field(default="", max_length=160)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def validate_supporting_outputs(self) -> "MethodEvolutionRun":
        values = [value.strip() for value in self.supporting_output_ids]
        if any(not value for value in values) or len(values) != len(set(values)):
            raise ValueError("supporting_output_ids must contain distinct non-empty values")
        self.supporting_output_ids = values
        return self


class OutputAsset(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    title: str = ""
    mime_type: str = "text/markdown"
    content_hash: str = Field(min_length=64, max_length=128)
    vault_path: str
    run_id: str = ""
    method_revision_id: str = ""
    context_revision: str = ""
    source_refs: list[str] = Field(default_factory=list, max_length=500)
    page_refs: list[str] = Field(default_factory=list, max_length=500)
    idempotency_key: str = Field(min_length=1)
    status: OutputStatus = OutputStatus.REGISTERED
    quality: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("vault_path")
    @classmethod
    def validate_vault_path(cls, value: str) -> str:
        return _path(value)


class OutputEvaluation(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    output_id: str = Field(min_length=1)
    groundedness: float = Field(ge=0, le=1)
    task_fit: float = Field(ge=0, le=1)
    usefulness: float = Field(ge=0, le=1)
    coherence: float = Field(ge=0, le=1)
    format_quality: float = Field(ge=0, le=1)
    quality: int = Field(default=-1, ge=0, le=100)
    status: str = "completed"
    evaluator_revision: str = "deterministic-v1"
    findings: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def calculate_quality(self) -> "OutputEvaluation":
        score = math.floor(
            self.groundedness * 30
            + self.task_fit * 25
            + self.usefulness * 20
            + self.coherence * 15
            + self.format_quality * 10
            + 0.5
        )
        if self.quality not in {-1, score}:
            raise ValueError("quality does not match evaluation components")
        self.quality = score
        return self


class OutputFeedback(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    output_id: str = Field(min_length=1)
    feedback_type: FeedbackType
    actor_id: str = ""
    rating: int | None = Field(default=None, ge=0, le=100)
    correction: str = ""
    comment: str = ""
    status: FeedbackStatus = FeedbackStatus.PENDING
    processed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class KnowledgeLineageEdge(GrowthModel):
    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    from_type: str = Field(min_length=1)
    from_id: str = Field(min_length=1)
    to_type: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    revision: str = ""
    created_at: datetime = Field(default_factory=_now)


class KnowledgeFailureRecord(GrowthModel):
    """A project-scoped failure record linked to durable run evidence when available."""

    id: str = Field(default_factory=_id, min_length=1)
    project_id: str = Field(min_length=1)
    code: KnowledgeFailureCode
    diagnostic_pattern: KnowledgeFailurePattern | None = None
    secondary_diagnostic_patterns: list[KnowledgeFailurePattern] = Field(default_factory=list, max_length=2)
    severity: str = Field(default="error", pattern=r"^(info|warning|error|critical)$")
    summary: str = Field(min_length=1, max_length=2_000)
    run_id: str = ""
    event_sequence: int | None = Field(default=None, ge=1)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    root_cause: str = Field(default="", max_length=8_000)
    minimal_structural_fix: str = Field(default="", max_length=8_000)
    retryable: bool = False
    status: KnowledgeFailureStatus = KnowledgeFailureStatus.OPEN
    resolution: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def validate_run_event_link(self) -> "KnowledgeFailureRecord":
        self.diagnostic_pattern = self.diagnostic_pattern or default_failure_pattern(self.code)
        if self.diagnostic_pattern in self.secondary_diagnostic_patterns:
            raise ValueError("secondary diagnostic patterns must not repeat the primary pattern")
        if len(self.secondary_diagnostic_patterns) != len(set(self.secondary_diagnostic_patterns)):
            raise ValueError("secondary diagnostic patterns must be distinct")
        if self.event_sequence is not None and not self.run_id:
            raise ValueError("event_sequence requires run_id")
        if self.status is KnowledgeFailureStatus.RESOLVED and not self.resolution:
            raise ValueError("resolved failures require a resolution record")
        return self
