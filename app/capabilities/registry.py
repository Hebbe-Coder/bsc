"""Phase 1 - Capability System: Business capability abstraction layer.

ADR-010 principle #2: Planner selects Capability, not Agent.
Agent is just the implementation detail behind a Capability.

This mirrors nanobot's ToolRegistry pattern:
  ToolRegistry.register() / .get()  ←→  CapabilityRegistry.register() / .get()

Usage:
    from app.capabilities import Capability, CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register(Capability(
        name="risk_analysis",
        description="Analyze business risks across dimensions",
        input_artifact_types=[ArtifactType.BUSINESS_MODEL],
        output_artifact_types=[ArtifactType.RISK],
        executor_key="risk",
    ))
    caps = registry.find_by_input(ArtifactType.BUSINESS_MODEL)
"""

from __future__ import annotations

import time
import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.artifacts.types import ArtifactType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability model
# ---------------------------------------------------------------------------

class Capability(BaseModel):
    """A declared business capability that can be executed.

    This is the unit of planning — the Mission Planner selects capabilities,
    not agents. An agent (or any callable) implements the capability.
    """
    name: str                                       # e.g. "risk_analysis"
    description: str = ""
    input_artifact_types: list[ArtifactType] = Field(default_factory=list)
    output_artifact_types: list[ArtifactType] = Field(default_factory=list)

    # Quality metadata (for Planner scoring)
    quality: float = Field(default=0.8, ge=0.0, le=1.0)
    cost_estimate: int = 5000                       # estimated tokens
    avg_duration_ms: float = 0.0                    # tracked over time
    success_rate: float = Field(default=0.9, ge=0.0, le=1.0)

    # Domain tags (for intelligent matching)
    industries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Executor binding (what actually runs)
    executor_key: str = ""                          # key into AgentFactory / AgentPool
    executor_fn: Optional[Callable] = None           # direct callable fallback

    # Metadata
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def score_for(self, *, industry: str = "", input_type: ArtifactType | None = None) -> float:
        """Compute a relevance score for a given context (0-1)."""
        score = self.quality * 0.5 + self.success_rate * 0.5
        if industry and industry in self.industries:
            score += 0.15
        if input_type and input_type in self.input_artifact_types:
            score += 0.15
        return min(score, 1.0)


# ---------------------------------------------------------------------------
# Capability Registry
# ---------------------------------------------------------------------------

class CapabilityRegistry:
    """Registry of all business capabilities.

    Nanobot-aligned design: register/get/list pattern like ToolRegistry.

    Usage:
        reg = CapabilityRegistry()
        reg.register(Capability(name="risk_analysis", ...))
        cap = reg.get("risk_analysis")
        matches = reg.find_by_input(ArtifactType.BUSINESS_MODEL)
    """

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}

    # -- CRUD --

    def register(self, capability: Capability) -> None:
        """Register a capability. Overwrites if name already exists."""
        self._capabilities[capability.name] = capability
        logger.debug("Capability registered: %s", capability.name)

    def register_many(self, capabilities: list[Capability]) -> None:
        for cap in capabilities:
            self.register(cap)

    def get(self, name: str) -> Optional[Capability]:
        """Get a capability by name, or None."""
        return self._capabilities.get(name)

    def list_all(self) -> list[Capability]:
        """Return all registered capabilities."""
        return sorted(self._capabilities.values(), key=lambda c: c.name)

    def remove(self, name: str) -> bool:
        """Remove a capability. Returns True if it existed."""
        if name in self._capabilities:
            del self._capabilities[name]
            return True
        return False

    def count(self) -> int:
        return len(self._capabilities)

    # -- Query by artifact type --

    def find_by_input(self, artifact_type: ArtifactType) -> list[Capability]:
        """Find capabilities that consume the given artifact type."""
        return [
            c for c in self._capabilities.values()
            if artifact_type in c.input_artifact_types
        ]

    def find_by_output(self, artifact_type: ArtifactType) -> list[Capability]:
        """Find capabilities that produce the given artifact type."""
        return [
            c for c in self._capabilities.values()
            if artifact_type in c.output_artifact_types
        ]

    def find_by_io(
        self,
        input_type: Optional[ArtifactType] = None,
        output_type: Optional[ArtifactType] = None,
    ) -> list[Capability]:
        """Find capabilities matching both input and output constraints."""
        results = list(self._capabilities.values())
        if input_type:
            results = [c for c in results if input_type in c.input_artifact_types]
        if output_type:
            results = [c for c in results if output_type in c.output_artifact_types]
        return results

    # -- Query by domain --

    def find_by_industry(self, industry: str) -> list[Capability]:
        """Find capabilities tagged for a specific industry."""
        return [
            c for c in self._capabilities.values()
            if industry in c.industries
        ]

    def find_by_tag(self, tag: str) -> list[Capability]:
        return [
            c for c in self._capabilities.values()
            if tag in c.tags
        ]

    # -- Best-match selection (for Planner) --

    def best_for(
        self,
        *,
        input_type: Optional[ArtifactType] = None,
        output_type: Optional[ArtifactType] = None,
        industry: str = "",
        min_score: float = 0.5,
    ) -> Optional[Capability]:
        """Return the highest-scoring capability matching the constraints."""
        candidates = self.find_by_io(input_type=input_type, output_type=output_type)
        if not candidates:
            return None
        scored = [(c, c.score_for(industry=industry, input_type=input_type)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        best, score = scored[0]
        if score < min_score:
            return None
        return best

    # -- Serialization --

    def to_dict(self) -> dict:
        """Export the registry as a dict (for debugging / display)."""
        return {
            name: {
                "description": cap.description,
                "inputs": [t.value for t in cap.input_artifact_types],
                "outputs": [t.value for t in cap.output_artifact_types],
                "quality": cap.quality,
                "success_rate": cap.success_rate,
                "executor_key": cap.executor_key,
                "industries": cap.industries,
            }
            for name, cap in self._capabilities.items()
        }


# ---------------------------------------------------------------------------
# Pre-built capability catalog (maps to existing agents)
# ---------------------------------------------------------------------------

def build_default_registry() -> CapabilityRegistry:
    """Build a CapabilityRegistry pre-populated with all existing BSC agents.

    This is the zero-risk Phase 1 wrapper — every existing agent gets
    a Capability entry without changing the agent code.
    """
    reg = CapabilityRegistry()

    # Core analysis capabilities (mapped to existing agents)
    capabilities = [
        Capability(
            name="business_understanding",
            description="Analyze PRD and extract business domain, objectives, context",
            input_artifact_types=[],
            output_artifact_types=[ArtifactType.BUSINESS_MODEL],
            executor_key="business_understanding",
            tags=["entry", "analysis"],
            success_rate=0.92,
        ),
        Capability(
            name="assumption_reasoning",
            description="Extract hidden assumptions behind a business model; evaluate counterfactuals",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL],
            output_artifact_types=[ArtifactType.ASSUMPTION],
            executor_key="business_understanding",
            tags=["analysis", "reasoning", "critical_thinking"],
            success_rate=0.85,
        ),
        Capability(
            name="risk_analysis",
            description="Identify and assess risks across process, org, system, compliance, market dimensions",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.ASSUMPTION],
            output_artifact_types=[ArtifactType.RISK],
            executor_key="risk",
            tags=["analysis", "risk"],
            success_rate=0.90,
        ),
        Capability(
            name="constraint_generation",
            description="Generate regulatory, resource, and market constraints",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.RISK],
            output_artifact_types=[ArtifactType.CONSTRAINT],
            executor_key="strategy",
            tags=["analysis", "constraint"],
            success_rate=0.82,
        ),
        Capability(
            name="sop_design",
            description="Design standard operating procedures and workflows",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL],
            output_artifact_types=[],
            executor_key="sop",
            tags=["generation", "workflow"],
            success_rate=0.88,
        ),
        Capability(
            name="strategy_analysis",
            description="Analyze growth opportunities and strategic paths",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.RISK],
            output_artifact_types=[],
            executor_key="strategy",
            tags=["analysis", "strategy"],
            success_rate=0.84,
        ),
        Capability(
            name="optimization_recommendations",
            description="Generate optimization recommendations for business processes",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.CONSTRAINT],
            output_artifact_types=[],
            executor_key="optimization",
            tags=["optimization", "recommendation"],
            success_rate=0.80,
        ),
        Capability(
            name="coverage_analysis",
            description="Analyze which business dimensions are covered and which are missing",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.RISK, ArtifactType.ASSUMPTION],
            output_artifact_types=[ArtifactType.COVERAGE],
            executor_key="composer",
            tags=["analysis", "coverage"],
            success_rate=0.78,
        ),
        Capability(
            name="gap_detection",
            description="Detect gaps in business analysis — missing evidence, insufficient analysis, failed models",
            input_artifact_types=[ArtifactType.COVERAGE, ArtifactType.ASSUMPTION, ArtifactType.RISK],
            output_artifact_types=[ArtifactType.GAP],
            executor_key="composer",
            tags=["analysis", "gap", "reflection"],
            success_rate=0.75,
        ),
        Capability(
            name="decision_support",
            description="Generate business decisions with rationale, confidence, and alternatives",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.RISK, ArtifactType.COVERAGE],
            output_artifact_types=[ArtifactType.DECISION],
            executor_key="composer",
            tags=["synthesis", "decision"],
            success_rate=0.82,
        ),
        Capability(
            name="evidence_validation",
            description="Validate assumptions with market data, benchmarks, or expert opinion",
            input_artifact_types=[ArtifactType.ASSUMPTION],
            output_artifact_types=[ArtifactType.EVIDENCE],
            executor_key="business_understanding",
            tags=["validation", "evidence"],
            success_rate=0.70,
        ),
        Capability(
            name="report_composition",
            description="Compose final business analysis report from all artifacts",
            input_artifact_types=[ArtifactType.BUSINESS_MODEL, ArtifactType.RISK, ArtifactType.DECISION],
            output_artifact_types=[],
            executor_key="composer",
            tags=["synthesis", "export"],
            success_rate=0.90,
        ),
    ]

    reg.register_many(capabilities)
    return reg
