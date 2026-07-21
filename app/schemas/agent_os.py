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
