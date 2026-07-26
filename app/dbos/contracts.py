"""Public DBOS contracts shared by services, REST, MCP, and UI projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.artifacts import (
    CapabilitySelectionArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    ExecutionResultArtifact,
    MemoryArtifact,
    MissionArtifact,
)


class MissionInput(BaseModel):
    """Bounded mission intake accepted by the DBOS service boundary."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    intake_mode: str = Field(default="business", pattern="^(business|career)$")
    intent: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class DBOSFlow:
    """Traceable outputs of the diagnosis -> selection -> SOP compilation path."""

    mission: MissionArtifact
    diagnosis: DiagnosisArtifact
    selection: CapabilitySelectionArtifact
    sop: DynamicSOPArtifact
    routing_evaluation_id: str = ""
    context_snapshot_id: str = ""
    assumption_ids: list[str] = field(default_factory=list)
    gap_ids: list[str] = field(default_factory=list)
    risk_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


DBOS_ARTIFACT_TYPES = frozenset({
    "mission",
    "diagnosis",
    "capability_selection",
    "dynamic_sop",
    "sop_routing_evaluation",
    "execution_result",
    "memory",
})

__all__ = [
    "DBOS_ARTIFACT_TYPES",
    "DBOSFlow",
    "MissionInput",
    "MissionArtifact",
    "DiagnosisArtifact",
    "CapabilitySelectionArtifact",
    "DynamicSOPArtifact",
    "ExecutionResultArtifact",
    "MemoryArtifact",
]
