"""Source capture contracts for the LLM Wiki evidence layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.wiki_contracts import SourceRecord, SourceStatus, can_transition_source
from app.knowledge.wiki_repository import WikiRepository


def sha256_content(content: str | bytes) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


class CaptureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapturedSourceInput(CaptureModel):
    project_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    origin: str = ""
    raw_content: str = Field(min_length=1)
    vault_path: str = ""
    trust_level: str = "untrusted"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trust_level")
    @classmethod
    def validate_trust_level(cls, value: str) -> str:
        normalized = value.strip().lower() or "untrusted"
        if normalized not in {"trusted", "reviewed", "untrusted"}:
            raise ValueError("trust_level must be trusted, reviewed, or untrusted")
        return normalized


class HorizonSignal(CaptureModel):
    project_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    source_name: str = "Horizon"
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def to_source_input(self) -> CapturedSourceInput:
        published = self.published_at.isoformat() if self.published_at else ""
        raw_content = "\n".join(
            part
            for part in (
                f"# {self.title}",
                self.summary,
                f"Source: {self.source_name}",
                f"URL: {self.url}",
                f"Published: {published}" if published else "",
            )
            if part
        )
        return CapturedSourceInput(
            project_id=self.project_id,
            source_type="horizon_signal",
            origin=self.url,
            raw_content=raw_content,
            metadata={
                "source_name": self.source_name,
                "published_at": published,
                "tags": self.tags,
                "raw_payload": self.raw_payload,
            },
        )


@dataclass(frozen=True)
class CaptureResult:
    source: dict[str, Any]
    created: bool


class InvalidSourceTransition(ValueError):
    """Raised when source lifecycle rules would be violated."""


@dataclass(frozen=True)
class SourceTrustPolicy:
    trusted_source_types: set[str]
    trusted_origin_prefixes: tuple[str, ...] = ()

    def assess(self, payload: CapturedSourceInput) -> tuple[str, SourceStatus]:
        if payload.trust_level == "trusted":
            return "trusted", SourceStatus.ELIGIBLE
        if payload.source_type not in self.trusted_source_types:
            return payload.trust_level, SourceStatus.VALIDATED
        if self.trusted_origin_prefixes and not payload.origin.startswith(self.trusted_origin_prefixes):
            return "untrusted", SourceStatus.VALIDATED
        return "trusted", SourceStatus.ELIGIBLE


DEFAULT_SOURCE_TRUST_POLICY = SourceTrustPolicy(
    trusted_source_types={"manual_upload"},
)


class SourceCaptureService:
    """Capture immutable evidence records without touching Vault files."""

    def __init__(
        self,
        repository: WikiRepository,
        trust_policy: SourceTrustPolicy = DEFAULT_SOURCE_TRUST_POLICY,
    ) -> None:
        self.repository = repository
        self.trust_policy = trust_policy

    def capture(self, payload: CapturedSourceInput) -> CaptureResult:
        content_hash = sha256_content(payload.raw_content)
        existing = self.repository.find_source_by_content_hash(payload.project_id, content_hash)
        if existing:
            return CaptureResult(source=existing, created=False)

        trust_level, status = self.trust_policy.assess(payload)
        prior = self.repository.find_latest_source_by_origin(payload.project_id, payload.source_type, payload.origin)
        source = SourceRecord(
            project_id=payload.project_id,
            source_type=payload.source_type,
            origin=payload.origin,
            vault_path=payload.vault_path,
            content_hash=content_hash,
            raw_content=payload.raw_content,
            trust_level=trust_level,
            status=status,
            metadata=payload.metadata,
            supersedes_id=prior["id"] if prior else None,
        )
        created = self.repository.create_source(source)
        if prior and prior["status"] not in {SourceStatus.REJECTED.value, SourceStatus.SUPERSEDED.value}:
            self.repository.update_source_status(payload.project_id, prior["id"], SourceStatus.SUPERSEDED)
            self.repository.mark_source_citations_stale(payload.project_id, prior["id"])
            self.repository.record_source_supersession(
                project_id=payload.project_id,
                prior_source_id=prior["id"],
                current_source_id=created["id"],
            )
        return CaptureResult(source=created, created=True)

    def transition_source(self, project_id: str, source_id: str, target: SourceStatus) -> dict[str, Any]:
        source = self.repository.get_source(project_id, source_id)
        if not source:
            raise KeyError(f"source not found: {source_id}")
        current = SourceStatus(source["status"])
        if current is target:
            return source
        if not can_transition_source(current, target):
            raise InvalidSourceTransition(f"invalid source transition: {current.value} -> {target.value}")
        return self.repository.update_source_status(project_id, source_id, target)
