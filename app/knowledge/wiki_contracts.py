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


class SourceStatus(str, Enum):
    CAPTURED = "captured"
    VALIDATED = "validated"
    ELIGIBLE = "eligible"
    PROCESSED = "processed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


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
