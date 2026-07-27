"""Typed, metadata-only contracts for knowledge operations projections."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OperationsMetricState(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    UNAVAILABLE = "unavailable"


class OperationsInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def ordered_utc_range(self) -> "OperationsInterval":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("operations interval must use timezone-aware timestamps")
        if self.start_at >= self.end_at:
            raise ValueError("operations interval start must be before end")
        return self


class OperationsScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)
    project_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=500)
    selected_project_id: str = Field(default="", max_length=128)
    interval: OperationsInterval | None = None

    @field_validator("project_ids")
    @classmethod
    def normalize_projects(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
        return normalized

    @model_validator(mode="after")
    def selected_project_is_authorized(self) -> "OperationsScope":
        if self.selected_project_id and self.selected_project_id not in self.project_ids:
            raise ValueError("selected project is outside the authorized operations scope")
        return self

    @property
    def is_portfolio(self) -> bool:
        return not self.selected_project_id


class OperationsCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: OperationsMetricState
    record_count: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=512)


class OperationsMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    state: OperationsMetricState
    value: float | int | None = None
    unit: str = Field(default="count", max_length=64)
    record_count: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=512)


class OperationsDrilldown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: Literal["knowledge", "growth", "dbos", "operations"]
    entity_id: str = Field(min_length=1, max_length=256)
    mission_id: str = Field(default="", max_length=256)


_SEVERITY_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_ACTION_KIND_PRIORITY = {
    "unresolved_risk": 0,
    "evidence_gap": 1,
    "failed_verification": 2,
    "unverified_execution": 3,
    "unvalidated_assumption": 4,
    "pending_proposal": 5,
    "knowledge_debt": 6,
    "maintenance": 7,
}


class OperationalAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=96)
    severity: str = Field(min_length=1, max_length=32)
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    recommendation: str = Field(min_length=1, max_length=1_000)
    created_at: datetime
    drilldown: OperationsDrilldown

    @field_validator("source_refs")
    @classmethod
    def unique_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
        if len(normalized) != len(values):
            raise ValueError("source references must be non-empty and unique")
        return normalized

    @property
    def sort_key(self) -> tuple[int, int, float, str]:
        created = self.created_at.astimezone(timezone.utc).timestamp()
        return (
            _ACTION_KIND_PRIORITY.get(self.kind, _ACTION_KIND_PRIORITY["maintenance"]),
            _SEVERITY_PRIORITY.get(self.severity.lower(), _SEVERITY_PRIORITY["info"]),
            created,
            self.id,
        )


class OperationsFreshness(BaseModel):
    """Latest durable activity for one authorized project, never a synthetic SLA."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: OperationsMetricState
    latest_activity_at: datetime | None = None
    record_count: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def availability_matches_activity(self) -> "OperationsFreshness":
        if self.state == OperationsMetricState.AVAILABLE and self.latest_activity_at is None:
            raise ValueError("available freshness requires a persisted activity timestamp")
        if self.state != OperationsMetricState.AVAILABLE and self.latest_activity_at is not None:
            raise ValueError("unavailable freshness cannot claim an activity timestamp")
        return self


class OperationsProjectMetrics(BaseModel):
    """Comparable, durable metrics used by the tenant portfolio read model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_count: OperationsMetric
    verified: OperationsMetric
    pending_validation: OperationsMetric
    risk_debt: OperationsMetric
    durable_references: OperationsMetric


class OperationsProjectSummary(BaseModel):
    """Tenant-authorized project health summary without domain payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    project_name: str = Field(min_length=1, max_length=256)
    coverage: OperationsCoverage
    freshness: OperationsFreshness
    metrics: OperationsProjectMetrics
    highest_priority_action: OperationalAction | None = None
