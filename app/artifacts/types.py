"""
Phase 0 — Artifact Graph v2: Core type definitions for the Business Agent OS.

ADR-010 principle #1: Artifact Graph is the sole business state.
Never regress to `state dict` — all agent output flows through typed artifacts.

The 8 Artifact types form the Business World Model:
  BusinessModel → Assumption → Evidence
  BusinessModel → Risk → Mitigation
  BusinessModel → Constraint → Boundary
  BusinessModel → Coverage → Matrix
  BusinessModel → Gap → Resolution
  BusinessModel → Decision → Rationale

Usage:
    from app.artifacts.types import (
        BusinessModelArtifact,
        AssumptionArtifact,
        RiskArtifact,
        GapCategory, RiskDimension, Severity,
    )
    model = BusinessModelArtifact(
        label="AI SaaS 订阅业务",
        project_id="proj_001",
    )
"""

from __future__ import annotations

import uuid
import time
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# StrEnum classifications
# ---------------------------------------------------------------------------

class ArtifactType(StrEnum):
    """Taxonomy of business artifacts in the World Model."""
    BUSINESS_MODEL = "business_model"
    ASSUMPTION = "assumption"
    RISK = "risk"
    CONSTRAINT = "constraint"
    EVIDENCE = "evidence"
    COVERAGE = "coverage"
    GAP = "gap"
    DECISION = "decision"
    DELIVERABLE = "deliverable"


class GapCategory(StrEnum):
    """Why a gap exists — drives resolution strategy selection."""
    EVIDENCE_MISSING = "evidence_missing"      # Type A: 缺数据/证据
    ANALYSIS_INSUFFICIENT = "analysis_insufficient"  # Type B: 分析深度不足
    MODEL_FAILED = "model_failed"              # Type C: 方案本身不成立


class RiskDimension(StrEnum):
    """Standard risk taxonomy aligned with existing RiskAgent output."""
    PROCESS = "process"
    ORGANIZATION = "organization"
    SYSTEM = "system"
    COMPLIANCE = "compliance"
    MARKET = "market"
    FINANCIAL = "financial"
    TECHNOLOGY = "technology"
    LEGAL = "legal"
    OPERATIONAL = "operational"
    STRATEGIC = "strategic"


class Severity(StrEnum):
    """Severity / impact level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ArtifactStatus(StrEnum):
    """Lifecycle state of an artifact."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


# ---------------------------------------------------------------------------
# Base Artifact
# ---------------------------------------------------------------------------

class BaseArtifact(BaseModel):
    """Common fields shared by every artifact in the graph."""
    artifact_id: str = Field(default_factory=lambda: f"art_{uuid.uuid4().hex[:12]}")
    artifact_type: ArtifactType
    project_id: str = ""
    label: str = ""
    description: str = ""

    # Graph edges — set by ArtifactGraphStore (not in __init__)
    parent_ids: list[str] = Field(default_factory=list)
    # child_ids are derived at query time from the store index

    # Quality metadata
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: ArtifactStatus = ArtifactStatus.ACTIVE
    source_agent: str = ""           # which agent / capability produced this
    evidence_refs: list[str] = Field(default_factory=list)  # linked Evidence artifact ids

    # Extensibility
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))


# ---------------------------------------------------------------------------
# Concrete Artifacts
# ---------------------------------------------------------------------------

class BusinessModelArtifact(BaseArtifact):
    """The root artifact — describes the business model under analysis.

    This is the entry point of the Artifact Graph; all other artifacts
    trace their lineage back to a BusinessModelArtifact.

    Replaces: the unstructured "business_system" dict keys in bsc_pipeline.py
    """
    artifact_type: ArtifactType = ArtifactType.BUSINESS_MODEL

    domain: str = ""                 # e.g. "餐饮数字化", "AI SaaS"
    value_proposition: str = ""
    revenue_model: str = ""
    customer_segments: list[str] = Field(default_factory=list)
    key_partners: list[str] = Field(default_factory=list)
    key_activities: list[str] = Field(default_factory=list)
    key_resources: list[str] = Field(default_factory=list)
    cost_structure: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    project_thesis: str = ""
    distinctive_bets: list[str] = Field(default_factory=list)
    key_unknowns: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)


class AssumptionArtifact(BaseArtifact):
    """Hidden assumptions the business model depends on.

    Each assumption is a testable proposition: "The business model
    assumes X is true."  Linked Evidence artifacts confirm or refute.
    """
    artifact_type: ArtifactType = ArtifactType.ASSUMPTION

    statement: str = ""              # "讲师供给持续稳定"
    category: str = ""               # "market" | "operational" | "financial" | "technical"
    criticality: Severity = Severity.MEDIUM  # how bad if wrong
    validated: bool = False          # has evidence confirmed this?
    validation_method: str = ""      # "market_research" | "user_interview" | "data_analysis"
    counterfactual: str = ""         # "如果讲师供给下降50%，结论是否仍成立？"
    counterfactual_holds: Optional[bool] = None  # None = not evaluated


class RiskArtifact(BaseArtifact):
    """Identified risk with structured taxonomy.

    Replaces: Unstructured risk dicts in bsc_pipeline.py:
      {"risk": "…", "severity": "high", "probability": "medium", "mitigation": "…"}
    """
    artifact_type: ArtifactType = ArtifactType.RISK

    risk_statement: str = ""
    dimension: RiskDimension = RiskDimension.OPERATIONAL
    severity: Severity = Severity.MEDIUM
    probability: Severity = Severity.MEDIUM
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    mitigation: str = ""
    contingency: str = ""
    trigger_signals: list[str] = Field(default_factory=list)
    affected_artifact_ids: list[str] = Field(default_factory=list)


class ConstraintArtifact(BaseArtifact):
    """Regulatory, resource, or market constraint that bounds the business model.

    Each constraint defines a boundary: "We cannot do Y because of Z."
    """
    artifact_type: ArtifactType = ArtifactType.CONSTRAINT

    constraint_statement: str = ""
    constraint_type: str = ""        # "regulatory" | "resource" | "market" | "technical" | "organizational"
    hard_limit: bool = True          # False = soft guideline; True = absolute boundary
    consequence_if_violated: str = ""
    workaround: str = ""


class EvidenceArtifact(BaseArtifact):
    """Empirical data that supports or refutes an Assumption.

    Linked to AssumptionArtifact via parent_ids and evidence_refs.
    """
    artifact_type: ArtifactType = ArtifactType.EVIDENCE

    evidence_type: str = ""          # "market_data" | "user_interview" | "benchmark" | "expert_opinion"
    source: str = ""                 # where this evidence came from
    strength: Severity = Severity.MEDIUM  # how strong/conclusive
    supports_assumption_id: str = "" # the Assumption this evidence addresses
    finding: str = ""                # "数据表明讲师供给过去12个月下降15%"
    contradicts: bool = False        # True = this evidence REFUTES the assumption


class CoverageArtifact(BaseArtifact):
    """Coverage analysis: which business dimensions have been analyzed?

    Maps each dimension → coverage score + gap summary.
    """
    artifact_type: ArtifactType = ArtifactType.COVERAGE

    dimensions_covered: list[str] = Field(default_factory=list)
    dimensions_missed: list[str] = Field(default_factory=list)
    overall_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    dimension_scores: dict[str, float] = Field(default_factory=dict)

    def coverage_pct(self) -> float:
        return round(self.overall_coverage * 100, 1)


class GapArtifact(BaseArtifact):
    """Identified gap in the business analysis.

    Three gap categories per ADR-010:
      - EVIDENCE_MISSING → RequestEvidence
      - ANALYSIS_INSUFFICIENT → AddCapability
      - MODEL_FAILED → GenerateAlternative
    """
    artifact_type: ArtifactType = ArtifactType.GAP

    gap_statement: str = ""
    category: GapCategory = GapCategory.EVIDENCE_MISSING
    severity: Severity = Severity.MEDIUM
    affected_artifact_ids: list[str] = Field(default_factory=list)
    resolution: str = ""             # proposed fix
    resolved: bool = False


class DecisionArtifact(BaseArtifact):
    """A business decision with rationale.

    This is the payoff artifact — why the business should choose path X over Y.
    Enterprise consulting reports live here.
    """
    artifact_type: ArtifactType = ArtifactType.DECISION

    decision_statement: str = ""     # "选择A市场进入策略"
    alternatives: list[str] = Field(default_factory=list)  # "B策略", "C策略"
    rationale: str = ""              # why this decision
    assumption_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_acceptable: bool = False
    coverage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendation: str = ""
    decision_makers: list[str] = Field(default_factory=list)


class DeliverableArtifact(BaseArtifact):
    """A reviewable, project-specific work product generated by a capability."""

    artifact_type: ArtifactType = ArtifactType.DELIVERABLE
    kind: str = ""
    title: str = ""
    summary: str = ""
    differentiators: list[str] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    context_pack_id: str = ""


# ---------------------------------------------------------------------------
# Type registry for fast lookup
# ---------------------------------------------------------------------------

ARTIFACT_CLASS_MAP: dict[ArtifactType, type[BaseArtifact]] = {
    ArtifactType.BUSINESS_MODEL: BusinessModelArtifact,
    ArtifactType.ASSUMPTION: AssumptionArtifact,
    ArtifactType.RISK: RiskArtifact,
    ArtifactType.CONSTRAINT: ConstraintArtifact,
    ArtifactType.EVIDENCE: EvidenceArtifact,
    ArtifactType.COVERAGE: CoverageArtifact,
    ArtifactType.GAP: GapArtifact,
    ArtifactType.DECISION: DecisionArtifact,
    ArtifactType.DELIVERABLE: DeliverableArtifact,
}
