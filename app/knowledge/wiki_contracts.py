"""Typed contracts for the project-scoped LLM Wiki domain."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


def _normalize_vault_path(value: str) -> str:
    path = (value or "").strip()
    if not path or "\x00" in path or "\\" in path:
        raise ValueError("path must be a non-empty POSIX relative path")
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise ValueError("path must stay within the project vault")
    if normalized.parts and ":" in normalized.parts[0]:
        raise ValueError("path must not include a drive prefix")
    return normalized.as_posix()


def _normalize_sha256(value: str, *, required: bool = True) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized and not required:
        return ""
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError("value must be a SHA-256 hexadecimal digest")
    return normalized


class SourceStatus(str, Enum):
    CAPTURED = "captured"
    VALIDATED = "validated"
    ELIGIBLE = "eligible"
    PROCESSED = "processed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SourceCaptureOutcome(str, Enum):
    """The immutable result of one source-capture attempt."""

    CAPTURED = "captured"
    DUPLICATE = "duplicate"
    REJECTED_BY_POLICY = "rejected_by_policy"
    PROJECTION_FAILED = "projection_failed"


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class AssetAccessState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    RESTRICTED = "restricted"
    ARCHIVED = "archived"


class ExtractionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    RESTRICTED = "restricted"
    UNAVAILABLE = "unavailable"
    NEEDS_REVIEW = "needs_review"


class ReferenceResolutionState(str, Enum):
    RESOLVED = "resolved"
    STALE = "stale"
    BROKEN = "broken"
    RESTRICTED = "restricted"


class WikiOperationType(str, Enum):
    CREATE = "create"
    REPLACE = "replace"
    APPEND = "append"
    ARCHIVE = "archive"
    MOVE = "move"


_SOURCE_TRANSITIONS = {
    SourceStatus.CAPTURED: {SourceStatus.VALIDATED, SourceStatus.REJECTED, SourceStatus.SUPERSEDED},
    SourceStatus.VALIDATED: {SourceStatus.ELIGIBLE, SourceStatus.REJECTED, SourceStatus.SUPERSEDED},
    SourceStatus.ELIGIBLE: {SourceStatus.PROCESSED, SourceStatus.REJECTED, SourceStatus.SUPERSEDED},
    SourceStatus.PROCESSED: {SourceStatus.SUPERSEDED},
    SourceStatus.REJECTED: set(),
    SourceStatus.SUPERSEDED: set(),
}


def can_transition_source(current: SourceStatus, target: SourceStatus) -> bool:
    """Return whether a source lifecycle transition is allowed."""
    return target in _SOURCE_TRANSITIONS.get(current, set())


class WikiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class VaultMapping(WikiModel):
    project_id: str = Field(min_length=1)
    vault_path: str
    actor_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("vault_path")
    @classmethod
    def validate_vault_path(cls, value: str) -> str:
        return _normalize_vault_path(value)


class SourceRecord(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    origin: str = ""
    vault_path: str = ""
    content_hash: str = Field(min_length=1)
    raw_content: str = Field(min_length=1)
    trust_level: str = "untrusted"
    status: SourceStatus = SourceStatus.CAPTURED
    metadata: dict[str, Any] = Field(default_factory=dict)
    supersedes_id: str | None = None
    captured_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("vault_path")
    @classmethod
    def validate_optional_vault_path(cls, value: str) -> str:
        return _normalize_vault_path(value) if value else ""


class SourceCaptureAttempt(WikiModel):
    """A privacy-bounded ledger entry for one evidence-capture decision."""

    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    origin: str = Field(default="", max_length=2_000)
    content_hash: str = Field(default="", max_length=128)
    run_id: str = Field(default="", max_length=128)
    source_id: str = Field(default="", max_length=128)
    outcome: SourceCaptureOutcome
    policy: dict[str, Any] = Field(default_factory=dict)
    projection: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("content_hash")
    @classmethod
    def validate_optional_content_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and (len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized)):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest")
        return normalized


class WikiOperation(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    operation: WikiOperationType
    path: str
    content: str = ""
    destination_path: str = ""
    expected_content_hash: str = ""
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("path", "destination_path")
    @classmethod
    def validate_operation_path(cls, value: str) -> str:
        return _normalize_vault_path(value) if value else ""

    @model_validator(mode="after")
    def validate_move_destination(self) -> "WikiOperation":
        if self.operation is WikiOperationType.MOVE and not self.destination_path:
            raise ValueError("move operations require destination_path")
        if self.operation is not WikiOperationType.MOVE and self.destination_path:
            raise ValueError("destination_path is only valid for move operations")
        return self


class WikiProposal(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    base_revision: str = ""
    source_ids: list[str] = Field(default_factory=list)
    operations: list[WikiOperation]
    rationale: str = ""
    status: ProposalStatus = ProposalStatus.DRAFT
    eval_summary: dict[str, Any] = Field(default_factory=dict)
    manual: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_provenance(self) -> "WikiProposal":
        if not self.operations:
            raise ValueError("proposal requires at least one operation")
        operation_ids = [operation.id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("proposal operation IDs must be unique")
        has_operation_sources = any(operation.source_ids for operation in self.operations)
        if not self.manual and not self.source_ids and not has_operation_sources:
            raise ValueError("proposal requires source provenance unless manual")
        return self


class WikiPage(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    path: str
    title: str = ""
    page_kind: str = "general"
    content_hash: str = ""
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "published"
    published_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        return _normalize_vault_path(value)


class CitationLink(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    wiki_page_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    anchor: str = ""
    claim_text: str = ""
    status: str = "active"
    created_at: datetime = Field(default_factory=_utc_now)


class MediaAsset(WikiModel):
    """Immutable original-media descriptor; bytes stay in declared storage."""

    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    mime_type: str = Field(min_length=3, max_length=255)
    byte_hash: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0)
    storage_ref: str
    rights: str = Field(default="unknown", max_length=128)
    access_state: AssetAccessState = AssetAccessState.AVAILABLE
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("byte_hash")
    @classmethod
    def validate_byte_hash(cls, value: str) -> str:
        return _normalize_sha256(value)

    @field_validator("storage_ref")
    @classmethod
    def validate_storage_ref(cls, value: str) -> str:
        return _normalize_vault_path(value)


class ExtractionArtifact(WikiModel):
    """Versioned, auditable derivative. Public read models exclude ``content``."""

    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    extractor: str = Field(min_length=1, max_length=128)
    extractor_revision: str = Field(min_length=1, max_length=128)
    input_hash: str = Field(min_length=64, max_length=64)
    content_hash: str = Field(default="", max_length=64)
    content: str = ""
    status: ExtractionStatus
    error: str = Field(default="", max_length=1_024)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("input_hash")
    @classmethod
    def validate_input_hash(cls, value: str) -> str:
        return _normalize_sha256(value)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _normalize_sha256(value, required=False)


class TableArtifact(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    extraction_id: str = Field(min_length=1)
    table_schema: list[str] = Field(default_factory=list, alias="schema", serialization_alias="schema")
    row_count: int = Field(ge=0)
    units: dict[str, str] = Field(default_factory=dict)
    content_hash: str = Field(min_length=64, max_length=64)
    status: str = Field(default="detected", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("content_hash")
    @classmethod
    def validate_table_content_hash(cls, value: str) -> str:
        return _normalize_sha256(value)


class ReferenceLink(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=128)
    anchor_type: str = Field(min_length=1, max_length=64)
    anchor: str = Field(default="", max_length=2_048)
    relation: str = Field(min_length=1, max_length=64)
    resolution_state: ReferenceResolutionState = ReferenceResolutionState.RESOLVED
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class KnowledgeRun(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    run_type: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    status: RunStatus = RunStatus.QUEUED
    actor_id: str = ""
    input_refs: dict[str, Any] = Field(default_factory=dict)
    output_refs: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    retry_of: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class KnowledgeSchedule(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    job_type: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class WeeklyDistillation(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    week: str = Field(min_length=1)
    knowledge_path: str
    content_path: str
    context_path: str
    source_cutoff: str = Field(min_length=1)
    status: str = "generated"
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("knowledge_path", "content_path", "context_path")
    @classmethod
    def validate_distillation_path(cls, value: str) -> str:
        return _normalize_vault_path(value)


class KnowledgeGraphEdge(WikiModel):
    id: str = Field(default_factory=_new_id, min_length=1)
    project_id: str = Field(min_length=1)
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    edge_type: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    revision: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
