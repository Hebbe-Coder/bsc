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
        for field_name in ("metadata", "manifest", "eval_summary", "quality"):
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
    eval_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


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
