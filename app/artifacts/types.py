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
    MISSION = "mission"
    DIAGNOSIS = "diagnosis"
    CAPABILITY_SELECTION = "capability_selection"
    DYNAMIC_SOP = "dynamic_sop"
    SOP_ROUTING_EVALUATION = "sop_routing_evaluation"
    EXECUTION_RESULT = "execution_result"
    MEMORY = "memory"
    CONTEXT_SNAPSHOT = "context_snapshot"
    RUN_CHECKPOINT = "run_checkpoint"
    TASK_VERIFICATION = "task_verification"
    EXTERNAL_WORKER_RUN = "external_worker_run"
    ADVISOR_REVIEW = "advisor_review"
    INTAKE_SESSION = "intake_session"
    INTAKE_ANSWER_REVISION = "intake_answer_revision"


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
    # DBOS execution states are additive. Existing artifact types continue to
    # use the four lifecycle states above, while mission and execution records
    # can expose their persisted operational state without a side channel.
    DIAGNOSED = "diagnosed"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"
    ROLLED_BACK = "rolled_back"


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
# Dynamic Business OS artifacts (additive to the existing world model)
# ---------------------------------------------------------------------------

class MissionArtifact(BaseArtifact):
    """The authorization root for a Dynamic Business OS work system."""

    artifact_type: ArtifactType = ArtifactType.MISSION
    mission_id: str = ""
    title: str = ""
    intent: str = ""
    intake_mode: str = "business"  # business | career
    mission_status: str = "draft"
    authorization: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    confirmed_by: str = ""
    confirmed_at: str = ""
    revision: int = Field(default=1, ge=1)


class IntakeSessionArtifact(BaseArtifact):
    """Project-scoped, reviewable state for a bounded DBOS intake."""

    artifact_type: ArtifactType = ArtifactType.INTAKE_SESSION
    session_id: str = ""
    original_request: str = ""
    classification: str = "uncertain"
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    classification_rationale: list[str] = Field(default_factory=list)
    domain: str = "business"
    phase: str = "classified"
    initial_context: dict[str, Any] = Field(default_factory=dict)
    declared_context: dict[str, Any] = Field(default_factory=dict)
    unresolved_fields: list[str] = Field(default_factory=list)
    active_question: dict[str, Any] = Field(default_factory=dict)
    qualifying_question_count: int = Field(default=0, ge=0, le=2)
    completion_question_count: int = Field(default=0, ge=0, le=3)
    probe_question_count: int = Field(default=0, ge=0, le=1)
    tier: str = ""
    recommendation_state: str = "idle"
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    linked_mission_id: str = ""
    handoff_path: str = ""
    handoff_sha256: str = ""


class IntakeAnswerRevisionArtifact(BaseArtifact):
    """An immutable answer or skip record owned by one intake session."""

    artifact_type: ArtifactType = ArtifactType.INTAKE_ANSWER_REVISION
    session_id: str = ""
    question_id: str = ""
    question_field: str = ""
    question_phase: str = ""
    answer: str = ""
    skipped: bool = False
    context_updates: dict[str, Any] = Field(default_factory=dict)
    revision_ordinal: int = Field(default=1, ge=1)
    supersedes_id: str = ""


class DiagnosisArtifact(BaseArtifact):
    """A normalized, reviewable business context. Missing facts stay explicit."""

    artifact_type: ArtifactType = ArtifactType.DIAGNOSIS
    mission_id: str = ""
    role: str = ""
    industry: str = ""
    organization_stage: str = ""
    goal: str = ""
    time_horizon: str = ""
    constraints: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    decision_rights: list[str] = Field(default_factory=list)
    problem_statement: str = ""
    risk_summary: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    operating_hypotheses: list[str] = Field(default_factory=list)
    diagnostic_dimensions: list[str] = Field(default_factory=list)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)


class CapabilitySelectionItem(BaseModel):
    """One explainable inclusion or rejection in a DBOS capability selection."""

    capability_name: str
    task_family: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)
    executable: bool = False


class CapabilitySelectionArtifact(BaseArtifact):
    """The selected composition, rather than a fixed SOP template lookup."""

    artifact_type: ArtifactType = ArtifactType.CAPABILITY_SELECTION
    mission_id: str = ""
    diagnosis_id: str = ""
    selected: list[CapabilitySelectionItem] = Field(default_factory=list)
    rejected: list[CapabilitySelectionItem] = Field(default_factory=list)
    selection_reasoning: str = ""

    @property
    def selected_names(self) -> list[str]:
        return [item.capability_name for item in self.selected]


class DynamicSOPTask(BaseModel):
    """A stable, inspectable task in a compiled operating system."""

    task_id: str
    title: str
    task_family: str
    capability_name: str = ""
    owner: str = ""
    deliverable: str = ""
    metric: str = ""
    trigger: str = ""
    decision_point: str = ""
    risk: str = ""
    check: str = ""
    retrospect: str = ""
    parent_refs: list[str] = Field(default_factory=list)


class DynamicSOPPhase(BaseModel):
    phase_id: str
    title: str
    objective: str
    tasks: list[DynamicSOPTask] = Field(default_factory=list)


class DynamicSOPArtifact(BaseArtifact):
    """A diagnosis-specific business operating system, not a generic SOP."""

    artifact_type: ArtifactType = ArtifactType.DYNAMIC_SOP
    mission_id: str = ""
    diagnosis_id: str = ""
    selection_id: str = ""
    title: str = ""
    objective: str = ""
    diagnostic_summary: str = ""
    quality_gates: list[str] = Field(default_factory=list)
    phases: list[DynamicSOPPhase] = Field(default_factory=list)
    compilation_reasoning: str = ""


class SOPRoutingCaseResult(BaseModel):
    """One deterministic regression case for Dynamic SOP routing."""

    case_id: str
    split: str = "positive"
    passed: bool = False
    observed_profile: str = ""
    selected_capabilities: list[str] = Field(default_factory=list)
    selected_task_families: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class SOPRoutingEvaluationArtifact(BaseArtifact):
    """Persisted positive, negative, and holdout evidence for a Dynamic SOP route."""

    artifact_type: ArtifactType = ArtifactType.SOP_ROUTING_EVALUATION
    mission_id: str = ""
    diagnosis_id: str = ""
    selection_id: str = ""
    dynamic_sop_id: str = ""
    evaluator_revision: str = ""
    selector_fingerprint: str = ""
    evaluation_status: str = "pending"
    positive_case_count: int = Field(default=0, ge=0)
    near_negative_case_count: int = Field(default=0, ge=0)
    holdout_case_count: int = Field(default=0, ge=0)
    holdout_passed: bool = False
    case_results: list[SOPRoutingCaseResult] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class ExecutionResultArtifact(BaseArtifact):
    """An audited DBOS execution attempt and its actual effects."""

    artifact_type: ArtifactType = ArtifactType.EXECUTION_RESULT
    execution_id: str = ""
    mission_id: str = ""
    dynamic_sop_id: str = ""
    capability_name: str = ""
    execution_status: str = "queued"
    attempt: int = Field(default=1, ge=1)
    idempotency_key: str = ""
    context_snapshot_id: str = ""
    effects: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""
    stop_reason: str = ""
    rollback: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""


class MemoryArtifact(BaseArtifact):
    """A project-scoped advisory pattern/case backed by DBOS provenance."""

    artifact_type: ArtifactType = ArtifactType.MEMORY
    memory_kind: str = "feedback"
    statement: str = ""
    source_refs: list[str] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    governance_status: str = "candidate"


class RuntimeContextArtifact(BaseArtifact):
    """Redacted, inspectable context contract used for one DBOS runtime step.

    This is intentionally a composition ledger rather than a prompt archive:
    BSC records the policy, source artifact references, field names and
    fingerprints needed to reproduce or audit a decision without persisting
    raw user prompts, source bodies, model output or credentials.
    """

    artifact_type: ArtifactType = ArtifactType.CONTEXT_SNAPSHOT
    snapshot_id: str = ""
    mission_id: str = ""
    audience: str = "primary"
    purpose: str = "execution"
    context_revision: str = "dbos-context-v1"
    referenced_artifact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    method_ids: list[str] = Field(default_factory=list)
    context_fields: list[str] = Field(default_factory=list)
    prompt_fingerprint: str = ""
    input_fingerprint: str = ""
    estimated_tokens: int = Field(default=0, ge=0)
    context_window_tokens: int = Field(default=32_000, ge=1)
    compaction_threshold: float = Field(default=0.75, gt=0.0, le=1.0)
    compaction_required: bool = False
    data_classification: str = "internal"
    redacted: bool = True


class RunCheckpointArtifact(BaseArtifact):
    """Immutable lifecycle checkpoint for a DBOS capability attempt.

    Checkpoints keep restart recovery honest. An interrupted dispatch is never
    automatically replayed: a new, explicit idempotency key is required for a
    human-approved retry.
    """

    artifact_type: ArtifactType = ArtifactType.RUN_CHECKPOINT
    checkpoint_id: str = ""
    mission_id: str = ""
    execution_id: str = ""
    capability_name: str = ""
    idempotency_key: str = ""
    attempt: int = Field(default=1, ge=1)
    checkpoint_status: str = "prepared"
    context_snapshot_id: str = ""
    recovery_policy: str = "manual_retry_required"
    reason: str = ""
    resumed_from_execution_id: str = ""
    checkpointed_at: str = ""


class TaskVerificationArtifact(BaseArtifact):
    """Evidence that a real capability met, or failed, its output contract."""

    artifact_type: ArtifactType = ArtifactType.TASK_VERIFICATION
    mission_id: str = ""
    execution_id: str = ""
    dynamic_sop_id: str = ""
    capability_name: str = ""
    verification_status: str = "pending"
    declared_output_types: list[str] = Field(default_factory=list)
    produced_artifact_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    verified_at: str = ""


class ExternalWorkerRunArtifact(BaseArtifact):
    """Redacted, project-scoped ledger entry for a governed external worker.

    This record intentionally excludes credentials, request bodies and model
    output text.  Output must be represented by ordinary Artifact Graph IDs.
    """

    artifact_type: ArtifactType = ArtifactType.EXTERNAL_WORKER_RUN
    mission_id: str = ""
    dynamic_sop_id: str = ""
    capability_name: str = ""
    worker_id: str = ""
    model_id: str = ""
    egress_host: str = ""
    credential_ref: str = ""
    policy_revision: int = Field(default=0, ge=0)
    worker_status: str = "rejected"
    idempotency_key: str = ""
    input_fingerprint: str = ""
    output_artifact_ids: list[str] = Field(default_factory=list)
    call_index: int = Field(default=0, ge=0)
    estimated_cost_microusd: int = Field(default=0, ge=0)
    timeout_seconds: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    escalated: bool = False
    reason: str = ""
    requested_at: str = ""
    outbound_started_at: str = ""
    cancellation_requested_at: str = ""
    cancelled_at: str = ""
    recovered_at: str = ""
    completed_at: str = ""


class AdvisorFinding(BaseModel):
    """One bounded recommendation from a non-authoritative Advisor review."""

    model_config = {"extra": "forbid"}

    severity: str = Field(default="medium", pattern="^(critical|high|medium|low)$")
    category: str = Field(
        default="scope",
        pattern="^(scope|evidence|risk|metric|decision|execution)$",
    )
    statement: str = Field(min_length=1, max_length=2_000)
    recommendation: str = Field(default="", max_length=2_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)


class AdvisorReviewArtifact(BaseArtifact):
    """A PromptOps-governed advisory review with no execution authority.

    The review is deliberately separate from decisions and capability grants.
    It may expose missing evidence or risk, but it cannot confirm a Mission,
    authorize a capability, publish a method, or change runtime state.
    """

    artifact_type: ArtifactType = ArtifactType.ADVISOR_REVIEW
    mission_id: str = ""
    diagnosis_id: str = ""
    dynamic_sop_id: str = ""
    context_snapshot_id: str = ""
    idempotency_key: str = ""
    advisor_status: str = "unavailable"
    verdict: str = "unavailable"
    summary: str = ""
    findings: list[AdvisorFinding] = Field(default_factory=list, max_length=24)
    open_questions: list[str] = Field(default_factory=list, max_length=12)
    admitted_context_refs: list[str] = Field(default_factory=list, max_length=128)
    prompt_run_id: str = ""
    prompt_agent_id: str = ""
    prompt_agent_revision: str = ""
    provider: str = ""
    model_id: str = ""
    error_category: str = ""
    reviewed_at: str = ""


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
    ArtifactType.MISSION: MissionArtifact,
    ArtifactType.DIAGNOSIS: DiagnosisArtifact,
    ArtifactType.CAPABILITY_SELECTION: CapabilitySelectionArtifact,
    ArtifactType.DYNAMIC_SOP: DynamicSOPArtifact,
    ArtifactType.SOP_ROUTING_EVALUATION: SOPRoutingEvaluationArtifact,
    ArtifactType.EXECUTION_RESULT: ExecutionResultArtifact,
    ArtifactType.MEMORY: MemoryArtifact,
    ArtifactType.CONTEXT_SNAPSHOT: RuntimeContextArtifact,
    ArtifactType.RUN_CHECKPOINT: RunCheckpointArtifact,
    ArtifactType.TASK_VERIFICATION: TaskVerificationArtifact,
    ArtifactType.EXTERNAL_WORKER_RUN: ExternalWorkerRunArtifact,
    ArtifactType.ADVISOR_REVIEW: AdvisorReviewArtifact,
    ArtifactType.INTAKE_SESSION: IntakeSessionArtifact,
    ArtifactType.INTAKE_ANSWER_REVISION: IntakeAnswerRevisionArtifact,
}
