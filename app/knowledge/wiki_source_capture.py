"""Source capture contracts for the LLM Wiki evidence layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.growth_contracts import ProjectKnowledgeProfile, ProjectSourcePolicy
from app.knowledge.wiki_contracts import (
    SourceCaptureAttempt,
    SourceCaptureOutcome,
    SourceRecord,
    SourceStatus,
    can_transition_source,
)
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.reference_projection import SourceReferenceProjector


def sha256_content(content: str | bytes) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


_TRACKING_QUERY_KEYS = frozenset({
    "dclid", "fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "ref", "ref_src",
})


def canonicalize_origin(origin: str) -> str:
    """Normalize HTTP(S) origin identity without rewriting non-web evidence paths.

    Source content remains immutable. This value is used only to decide whether
    a later capture is a version of an existing web source, so fragments and
    common analytics parameters must not create a parallel evidence lineage.
    """
    value = str(origin or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        if scheme not in {"http", "https"} or not host:
            return value
        port = parsed.port
    except ValueError:
        # Preserve malformed values for the source-policy boundary instead of
        # silently treating them as a URL owned by a different source.
        return value

    normalized_host = host.lower()
    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = normalized_host if port in {None, default_port} else f"{normalized_host}:{port}"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


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
    capture_run_id: str = Field(default="", max_length=128)

    @field_validator("origin")
    @classmethod
    def normalize_origin(cls, value: str) -> str:
        return canonicalize_origin(value)

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
    primary_origin_prefixes: tuple[str, ...] = ()
    community_origin_prefixes: tuple[str, ...] = ()
    blocked_origin_prefixes: tuple[str, ...] = ()
    primary_retention_days: int = 730
    trusted_retention_days: int = 365
    community_retention_days: int = 90
    untrusted_retention_days: int = 30

    @classmethod
    def from_project_policy(cls, policy: ProjectSourcePolicy) -> "SourceTrustPolicy":
        return cls(
            trusted_source_types=set(policy.trusted_source_types),
            trusted_origin_prefixes=tuple(policy.trusted_origin_prefixes),
            requires_profile_triage_source_types=set(policy.require_triage_source_types),
            primary_origin_prefixes=tuple(policy.primary_origin_prefixes),
            community_origin_prefixes=tuple(policy.community_origin_prefixes),
            blocked_origin_prefixes=tuple(policy.blocked_origin_prefixes),
            primary_retention_days=policy.primary_retention_days,
            trusted_retention_days=policy.trusted_retention_days,
            community_retention_days=policy.community_retention_days,
            untrusted_retention_days=policy.untrusted_retention_days,
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a bounded, secret-free policy copy for the evidence ledger."""
        return {
            "primary_origin_prefixes": list(self.primary_origin_prefixes),
            "trusted_origin_prefixes": list(self.trusted_origin_prefixes),
            "community_origin_prefixes": list(self.community_origin_prefixes),
            "blocked_origin_prefixes": list(self.blocked_origin_prefixes),
            "trusted_source_types": sorted(self.trusted_source_types),
            "require_triage_source_types": sorted(self.requires_profile_triage_source_types),
            "primary_retention_days": self.primary_retention_days,
            "trusted_retention_days": self.trusted_retention_days,
            "community_retention_days": self.community_retention_days,
            "untrusted_retention_days": self.untrusted_retention_days,
        }

    def assess(
        self,
        payload: CapturedSourceInput,
        *,
        now: datetime | None = None,
        policy_source: str = "default",
        profile_revision: int = 0,
        profile_configured: bool = False,
    ) -> "SourceTrustAssessment":
        effective_now = now or datetime.now(timezone.utc)
        extraction = str(payload.metadata.get("extraction_status") or "complete").lower()
        freshness = self._freshness(payload.metadata.get("published_at"), now=effective_now)
        relevance = self._relevance(payload.metadata.get("ai_score"))
        curation = "user_curated" if payload.metadata.get("curated") else "reviewed" if payload.trust_level == "reviewed" else "uncurated"
        reasons: list[str] = []
        authority = self._authority(payload, reasons)
        retention_days = self._retention_days(authority)
        retention_expires_at = (effective_now + timedelta(days=retention_days)).isoformat()

        if authority == "blocked":
            return SourceTrustAssessment(
                trust_level="untrusted",
                status=SourceStatus.REJECTED,
                reasons=tuple(reasons),
                freshness=freshness,
                relevance=relevance,
                curation=curation,
                extraction_quality=extraction,
                authority=authority,
                retention_days=retention_days,
                retention_expires_at=retention_expires_at,
                policy_source=policy_source,
                profile_revision=profile_revision,
                profile_configured=profile_configured,
                policy_snapshot=self.snapshot(),
            )

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
                authority=authority,
                retention_days=retention_days,
                retention_expires_at=retention_expires_at,
                policy_source=policy_source,
                profile_revision=profile_revision,
                profile_configured=profile_configured,
                policy_snapshot=self.snapshot(),
            )

        trusted = authority in {"primary", "trusted"}
        if freshness == "stale":
            reasons.append("published_material_is_stale")
        if relevance == "low":
            reasons.append("low_relevance_score")
        requires_profile_triage = (
            payload.source_type.strip().lower() in self.requires_profile_triage_source_types
            or payload.metadata.get("admission_gate") == "project_triage"
        )
        if requires_profile_triage:
            reasons.append("project_profile_triage_required")
        return SourceTrustAssessment(
            trust_level="trusted" if trusted else "reviewed" if authority == "community" else payload.trust_level,
            status=SourceStatus.VALIDATED if requires_profile_triage or authority == "community" else (
                SourceStatus.ELIGIBLE if trusted else SourceStatus.VALIDATED
            ),
            reasons=tuple(reasons),
            freshness=freshness,
            relevance=relevance,
            curation=curation,
            extraction_quality=extraction,
            authority=authority,
            retention_days=retention_days,
            retention_expires_at=retention_expires_at,
            policy_source=policy_source,
            profile_revision=profile_revision,
            profile_configured=profile_configured,
            policy_snapshot=self.snapshot(),
        )

    def _authority(self, payload: CapturedSourceInput, reasons: list[str]) -> str:
        origin = payload.origin
        source_type = payload.source_type.strip().lower()
        if self.blocked_origin_prefixes and origin.startswith(self.blocked_origin_prefixes):
            reasons.append("origin_blocklisted")
            return "blocked"
        if self.primary_origin_prefixes and origin.startswith(self.primary_origin_prefixes):
            reasons.append("primary_origin_allowlisted")
            return "primary"
        if self.trusted_origin_prefixes and origin.startswith(self.trusted_origin_prefixes):
            reasons.append("trusted_origin_allowlisted")
            return "trusted"
        if self.community_origin_prefixes and origin.startswith(self.community_origin_prefixes):
            reasons.append("community_origin_requires_review")
            return "community"
        if payload.trust_level == "trusted":
            reasons.append("explicit_trusted_source")
            return "trusted"
        if source_type not in self.trusted_source_types:
            reasons.append("source_type_requires_review")
            return "untrusted"
        if self.trusted_origin_prefixes and not origin.startswith(self.trusted_origin_prefixes):
            reasons.append("origin_not_allowlisted")
            return "untrusted"
        reasons.append("source_type_and_origin_allowlisted")
        return "trusted"

    def _retention_days(self, authority: str) -> int:
        if authority == "primary":
            return self.primary_retention_days
        if authority == "trusted":
            return self.trusted_retention_days
        if authority == "community":
            return self.community_retention_days
        return self.untrusted_retention_days

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
    authority: str
    retention_days: int
    retention_expires_at: str
    policy_source: str
    profile_revision: int
    profile_configured: bool
    policy_snapshot: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return {
            "reasons": list(self.reasons),
            "freshness": self.freshness,
            "relevance": self.relevance,
            "curation": self.curation,
            "extraction_quality": self.extraction_quality,
            "authority": self.authority,
            "retention_days": self.retention_days,
            "retention_expires_at": self.retention_expires_at,
            "policy_source": self.policy_source,
            "profile_revision": self.profile_revision,
            "profile_configured": self.profile_configured,
            "policy_snapshot": self.policy_snapshot,
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
        trust_policy: SourceTrustPolicy | None = None,
        search_index=None,
    ) -> None:
        self.repository = repository
        self.trust_policy = trust_policy or DEFAULT_SOURCE_TRUST_POLICY
        self._uses_project_profile_policy = trust_policy is None
        if search_index is None:
            from app.knowledge.wiki_index import WikiSearchIndex

            search_index = WikiSearchIndex(repository)
        self.search_index = search_index
        self.reference_projector = SourceReferenceProjector(repository)

    def capture(self, payload: CapturedSourceInput) -> CaptureResult:
        content_hash = payload.content_hash or sha256_content(payload.raw_content)
        existing = self.repository.find_source_by_content_hash(payload.project_id, content_hash)
        if existing:
            self.reference_projector.project_source_id(payload.project_id, str(existing["id"]))
            assessment = self._assess(payload)
            self._record_attempt(
                payload,
                content_hash=content_hash,
                source=existing,
                outcome=SourceCaptureOutcome.DUPLICATE,
                policy=assessment.metadata(),
                projection=dict((existing.get("metadata") or {}).get("projection") or {}),
            )
            return CaptureResult(source=existing, created=False)

        assessment = self._assess(payload)
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
        self.reference_projector.project_source_id(payload.project_id, str(created["id"]))
        if prior and prior["status"] not in {SourceStatus.REJECTED.value, SourceStatus.SUPERSEDED.value}:
            self.repository.update_source_status(payload.project_id, prior["id"], SourceStatus.SUPERSEDED)
            self.repository.mark_source_citations_stale(payload.project_id, prior["id"])
            self.repository.record_source_supersession(
                project_id=payload.project_id,
                prior_source_id=prior["id"],
                current_source_id=created["id"],
            )
        outcome = (
            SourceCaptureOutcome.REJECTED_BY_POLICY
            if assessment.status is SourceStatus.REJECTED
            else SourceCaptureOutcome.PROJECTION_FAILED
            if projection.get("status") == "failed"
            else SourceCaptureOutcome.CAPTURED
        )
        self._record_attempt(
            payload,
            content_hash=content_hash,
            source=created,
            outcome=outcome,
            policy=assessment.metadata(),
            projection=projection,
        )
        return CaptureResult(source=created, created=True)

    def _assess(self, payload: CapturedSourceInput) -> SourceTrustAssessment:
        if not self._uses_project_profile_policy:
            return self.trust_policy.assess(payload, policy_source="injected")
        get_profile = getattr(self.repository, "get_profile", None)
        if not callable(get_profile):
            return self.trust_policy.assess(payload, policy_source="default")
        persisted = get_profile(payload.project_id)
        if not persisted:
            return self.trust_policy.assess(
                payload,
                policy_source="default",
                profile_revision=0,
                profile_configured=False,
            )
        profile = ProjectKnowledgeProfile.model_validate(persisted)
        return SourceTrustPolicy.from_project_policy(profile.source_policy).assess(
            payload,
            policy_source="project_profile",
            profile_revision=profile.revision,
            profile_configured=True,
        )

    def _record_attempt(
        self,
        payload: CapturedSourceInput,
        *,
        content_hash: str,
        source: dict[str, Any],
        outcome: SourceCaptureOutcome,
        policy: dict[str, Any],
        projection: dict[str, Any],
    ) -> None:
        self.repository.create_source_capture_attempt(
            SourceCaptureAttempt(
                project_id=payload.project_id,
                source_type=payload.source_type,
                origin=payload.origin,
                content_hash=content_hash,
                run_id=payload.capture_run_id,
                source_id=str(source.get("id") or ""),
                outcome=outcome,
                policy=policy,
                projection=projection,
            )
        )

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
