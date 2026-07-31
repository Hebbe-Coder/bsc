"""Metadata-only E1 release evidence gate for the personal knowledge ecosystem."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RELEASE_GATE_CONTRACT_REVISION = "e1-knowledge-ecosystem-v1"
REQUIRED_RELEASE_EVIDENCE: tuple[str, ...] = (
    "o1_secure_boundary_restart",
    "o2_metadata_views",
    "o3_real_plugin_exports",
    "o4_extraction_reference",
    "o5_visualization_inspection",
    "o6_feedback_cycle",
    "compose_recovery",
    "authorization_isolation",
    "browser_desktop_mobile",
)

_SAFE_CODE = r"^[a-z0-9][a-z0-9_.:-]{0,127}$"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")


class ReleaseEvidence(BaseModel):
    """One bounded handoff fact; source and provider payloads are not fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=128, pattern=_SAFE_CODE)
    state: Literal["verified", "pending", "unavailable", "failed"]
    proof_class: Literal["real", "fixture", "none"]
    observed_at: str = Field(default="", max_length=64)
    durable_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    detail_code: str = Field(default="", max_length=128, pattern=_SAFE_CODE)

    @field_validator("durable_ids")
    @classmethod
    def normalize_durable_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(str(value).strip() for value in values if str(value).strip())
        if len(normalized) != len(set(normalized)):
            raise ValueError("durable evidence IDs must be unique")
        if any(not _SAFE_ID.fullmatch(value) for value in normalized):
            raise ValueError("durable evidence IDs must be bounded ASCII identifiers")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return normalized


class ReleaseEvidencePacket(BaseModel):
    """Frozen O1-O6/E1 handoff input containing only safe metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_revision: str = Field(min_length=1, max_length=64, pattern=_SAFE_CODE)
    evidence: tuple[ReleaseEvidence, ...] = Field(default_factory=tuple, max_length=32)

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> "ReleaseEvidencePacket":
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("release evidence IDs must be unique")
        unknown = sorted(set(evidence_ids) - set(REQUIRED_RELEASE_EVIDENCE))
        if unknown:
            raise ValueError("release packet contains unknown evidence IDs")
        return self


class ReleaseMatrixRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=128, pattern=_SAFE_CODE)
    state: Literal["verified", "pending", "unavailable", "failed", "missing"]
    proof_class: Literal["real", "fixture", "none"]
    durable_id_count: int = Field(default=0, ge=0, le=32)
    detail_code: str = Field(default="", max_length=128, pattern=_SAFE_CODE)


class ReleaseGateDecision(BaseModel):
    """Safe release decision and bounded matrix for the E1 handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "release_ready",
        "implemented_with_operational_proof_pending",
        "not_release_ready",
    ]
    contract_revision: str = Field(min_length=1, max_length=64, pattern=_SAFE_CODE)
    matrix: tuple[ReleaseMatrixRow, ...] = Field(max_length=32)
    missing_evidence: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    pending_evidence: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    failed_evidence: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    blocking_reasons: tuple[
        Literal[
            "missing_evidence",
            "pending_operational_proof",
            "fixture_substitution",
            "failed_evidence",
            "invalid_real_proof",
        ],
        ...
    ] = Field(default_factory=tuple, max_length=8)


def evaluate_release_evidence(packet: ReleaseEvidencePacket) -> ReleaseGateDecision:
    """Evaluate every required gate without inspecting any content payload."""
    evidence_by_id = {item.evidence_id: item for item in packet.evidence}
    matrix: list[ReleaseMatrixRow] = []
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    reasons: list[str] = []

    def add_reason(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    for evidence_id in REQUIRED_RELEASE_EVIDENCE:
        item = evidence_by_id.get(evidence_id)
        if item is None:
            matrix.append(ReleaseMatrixRow(
                evidence_id=evidence_id,
                state="missing",
                proof_class="none",
                detail_code="missing_evidence",
            ))
            missing.append(evidence_id)
            add_reason("missing_evidence")
            continue

        matrix.append(ReleaseMatrixRow(
            evidence_id=item.evidence_id,
            state=item.state,
            proof_class=item.proof_class,
            durable_id_count=len(item.durable_ids),
            detail_code=item.detail_code,
        ))
        if item.state == "failed":
            failed.append(evidence_id)
            add_reason("failed_evidence")
        elif item.state == "verified" and item.proof_class != "real":
            failed.append(evidence_id)
            add_reason("fixture_substitution")
        elif item.state == "verified" and (not item.observed_at or not item.durable_ids):
            pending.append(evidence_id)
            add_reason("invalid_real_proof")
        elif item.state != "verified":
            pending.append(evidence_id)
            add_reason("pending_operational_proof")

    if failed or "fixture_substitution" in reasons:
        status = "not_release_ready"
    elif missing or pending:
        status = "implemented_with_operational_proof_pending"
    else:
        status = "release_ready"

    return ReleaseGateDecision(
        status=status,
        contract_revision=packet.contract_revision,
        matrix=tuple(matrix),
        missing_evidence=tuple(missing),
        pending_evidence=tuple(pending),
        failed_evidence=tuple(failed),
        blocking_reasons=tuple(reasons),
    )
