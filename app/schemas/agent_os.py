from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.prompt_context import PromptContextUsage
from app.core.llm_usage import ModelUsage


class AgentOSRequest(BaseModel):
    input: str
    mode: str = "llm"
    domain: str = ""
    project_id: str = ""
    board: bool = False


class AgentMission(BaseModel):
    title: str = ""
    steps: int = 0
    mode: str = ""


class AgentGapDetail(BaseModel):
    description: str = ""
    category: str = ""
    severity: str = ""


class AgentBoard(BaseModel):
    verdict: str = ""
    consensus: str = ""
    votes: dict[str, Any] = Field(default_factory=dict)


class CapabilityExecutionAttempt(BaseModel):
    attempt: int
    outcome: str
    elapsed_ms: float = 0.0
    error_code: str = ""
    error: str = ""
    retryable: bool = False


class CapabilityExecutionMetadata(BaseModel):
    capability_name: str
    status: str
    artifacts_produced: list[str] = Field(default_factory=list)
    error: str = ""
    error_code: str = ""
    elapsed_ms: float = 0.0
    backend: str = ""
    mode: str = ""
    retries: int = 0
    attempts: list[CapabilityExecutionAttempt] = Field(default_factory=list)
    prompt_context: PromptContextUsage | None = None
    model_usage: ModelUsage | None = None


class KnowledgeContextMetadata(BaseModel):
    """Traceable project knowledge used by one Agent OS execution."""

    knowledge_context_used: bool = False
    context_type: str = ""
    availability: str = "unavailable"
    context_pack_id: str = ""
    profile_revision: int = 0
    rules_revision: str = ""
    page_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    method_revision_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    rejected_output_ids: list[str] = Field(default_factory=list)
    evaluation_ids: list[str] = Field(default_factory=list)
    feedback_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    omitted_refs: list[str] = Field(default_factory=list)


class KnowledgeOutputRegistration(BaseModel):
    """D-layer staging result for structured work products from one run."""

    status: str = "not_attempted"
    attempted: int = 0
    registered: int = 0
    output_ids: list[str] = Field(default_factory=list)
    audit_run_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AgentRuntimeMetadata(BaseModel):
    status: str = ""
    execution_id: str = ""
    artifact_scope: str = ""
    iterations: int = 0
    elapsed_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
    stage_modes: dict[str, str] = Field(default_factory=dict)
    degraded: bool = False
    capability_executions: list[CapabilityExecutionMetadata] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: KnowledgeContextMetadata = Field(default_factory=KnowledgeContextMetadata)
    knowledge_output_registration: KnowledgeOutputRegistration = Field(
        default_factory=KnowledgeOutputRegistration
    )


class AgentAnalysisResponse(BaseModel):
    status: Literal["completed", "failed"]
    project_id: str
    execution_id: str
    mission: AgentMission
    artifacts: int = 0
    gaps: int = 0
    gap_details: list[AgentGapDetail] = Field(default_factory=list)
    board: AgentBoard | None = None
    board_verdict: str = ""
    board_consensus: str = ""
    board_votes: dict[str, Any] = Field(default_factory=dict)
    trusted_audit: dict[str, Any] | None = None
    runtime: AgentRuntimeMetadata
    report: dict[str, Any] = Field(default_factory=dict)
