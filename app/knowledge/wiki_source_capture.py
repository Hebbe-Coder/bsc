"""Source capture contracts for the LLM Wiki evidence layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    content_hash: str = ""

    @field_validator("trust_level")
    @classmethod
    def validate_trust_level(cls, value: str) -> str:
        normalized = value.strip().lower() or "untrusted"
        if normalized not in {"trusted", "reviewed", "untrusted"}:
            raise ValueError("trust_level must be trusted, reviewed, or untrusted")
        return normalized

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized and (len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized)):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest")
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
    requires_profile_triage_source_types: set[str] = field(default_factory=set)

    def assess(self, payload: CapturedSourceInput, *, now: datetime | None = None) -> "SourceTrustAssessment":
        extraction = str(payload.metadata.get("extraction_status") or "complete").lower()
        freshness = self._freshness(payload.metadata.get("published_at"), now=now)
        relevance = self._relevance(payload.metadata.get("ai_score"))
        curation = "user_curated" if payload.metadata.get("curated") else "reviewed" if payload.trust_level == "reviewed" else "uncurated"
        reasons: list[str] = []

        if extraction in {"unsupported", "failed", "encoding_error"}:
            reasons.append(f"extraction_{extraction}")
            return SourceTrustAssessment(
                trust_level="untrusted",
                status=SourceStatus.REJECTED,
                reasons=tuple(reasons),
                freshness=freshness,
                relevance=relevance,
                curation=curation,
                extraction_quality=extraction,
            )

        trusted = payload.trust_level == "trusted"
        if trusted:
            reasons.append("explicit_trusted_source")
        elif payload.source_type not in self.trusted_source_types:
            reasons.append("source_type_requires_review")
        elif self.trusted_origin_prefixes and not payload.origin.startswith(self.trusted_origin_prefixes):
            reasons.append("origin_not_allowlisted")
        else:
            trusted = True
            reasons.append("source_type_and_origin_allowlisted")
        if freshness == "stale":
            reasons.append("published_material_is_stale")
        if relevance == "low":
            reasons.append("low_relevance_score")
        requires_profile_triage = (
            payload.source_type in self.requires_profile_triage_source_types
            or payload.metadata.get("admission_gate") == "project_triage"
        )
        if requires_profile_triage:
            reasons.append("project_profile_triage_required")
        return SourceTrustAssessment(
            trust_level="trusted" if trusted else payload.trust_level,
            status=SourceStatus.VALIDATED if requires_profile_triage else (
                SourceStatus.ELIGIBLE if trusted else SourceStatus.VALIDATED
            ),
            reasons=tuple(reasons),
            freshness=freshness,
            relevance=relevance,
            curation=curation,
            extraction_quality=extraction,
        )

    @staticmethod
    def _freshness(value: Any, *, now: datetime | None) -> str:
        if not value:
            return "unknown"
        try:
            published = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age_days = ((now or datetime.now(timezone.utc)) - published.astimezone(timezone.utc)).days
        except (TypeError, ValueError):
            return "unknown"
        if age_days <= 30:
            return "fresh"
        if age_days <= 180:
            return "aging"
        return "stale"

    @staticmethod
    def _relevance(value: Any) -> str:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return "unknown"
        if score >= 8:
            return "high"
        if score >= 6:
            return "medium"
        return "low"


@dataclass(frozen=True)
class SourceTrustAssessment:
    trust_level: str
    status: SourceStatus
    reasons: tuple[str, ...]
    freshness: str
    relevance: str
    curation: str
    extraction_quality: str

    def metadata(self) -> dict[str, Any]:
        return {
            "reasons": list(self.reasons),
            "freshness": self.freshness,
            "relevance": self.relevance,
            "curation": self.curation,
            "extraction_quality": self.extraction_quality,
        }


DEFAULT_SOURCE_TRUST_POLICY = SourceTrustPolicy(
    trusted_source_types={"manual_upload"},
    requires_profile_triage_source_types={"horizon_signal"},
)


class SourceCaptureService:
    """Capture immutable evidence records without touching Vault files."""

    def __init__(
        self,
        repository: WikiRepository,
        trust_policy: SourceTrustPolicy = DEFAULT_SOURCE_TRUST_POLICY,
        search_index=None,
    ) -> None:
        self.repository = repository
        self.trust_policy = trust_policy
        if search_index is None:
            from app.knowledge.wiki_index import WikiSearchIndex

            search_index = WikiSearchIndex(repository)
        self.search_index = search_index

    def capture(self, payload: CapturedSourceInput) -> CaptureResult:
        content_hash = payload.content_hash or sha256_content(payload.raw_content)
        existing = self.repository.find_source_by_content_hash(payload.project_id, content_hash)
        if existing:
            return CaptureResult(source=existing, created=False)

        assessment = self.trust_policy.assess(payload)
        prior = self.repository.find_latest_source_by_origin(payload.project_id, payload.source_type, payload.origin)
        metadata = {**payload.metadata, "policy_assessment": assessment.metadata()}
        source = SourceRecord(
            project_id=payload.project_id,
            source_type=payload.source_type,
            origin=payload.origin,
            vault_path=payload.vault_path,
            content_hash=content_hash,
            raw_content=payload.raw_content,
            trust_level=assessment.trust_level,
            status=assessment.status,
            metadata=metadata,
            supersedes_id=prior["id"] if prior else None,
        )
        created = self.repository.create_source(source)
        if assessment.status is SourceStatus.REJECTED:
            projection = {"status": "skipped", "code": "source_rejected_by_policy"}
        else:
            try:
                projection = self.search_index.project_source(created)
            except Exception:
                projection = {"status": "failed", "code": "index_backend_exception"}
            if projection.get("status") == "error":
                projection = {"status": "failed", "code": "index_backend_error"}
        created = self.repository.update_source_metadata(
            payload.project_id,
            created["id"],
            {**created.get("metadata", {}), "projection": projection},
        )
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
