"""P1 - CapabilityExecutor: Unified execution layer for all capabilities.

Bridges the gap between Capability declaration and actual execution.
Two backends:
  - NanobotAgentBackend:  uses Nanobot Agent Loop + Tool Call (real Agent OS)
  - LocalAgentBackend:    uses existing BSC agents (backward compat)

Key insight: 12 capabilities → 12 prompt templates → 1 executor.
The Capability defines WHAT to do; the executor handles HOW.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.artifacts.store import ArtifactGraphStore
from app.artifacts.types import (
    ArtifactType, BaseArtifact, ARTIFACT_CLASS_MAP,
    BusinessModelArtifact, AssumptionArtifact, RiskArtifact,
    ConstraintArtifact, EvidenceArtifact, CoverageArtifact,
    GapArtifact, DecisionArtifact, Severity, GapCategory,
)
from .registry import Capability, CapabilityRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    """Result of executing a single capability."""
    capability_name: str = ""
    status: str = "pending"        # success | failed | skipped
    artifacts_produced: list[str] = Field(default_factory=list)  # artifact_ids
    error: str = ""
    elapsed_ms: float = 0.0
    backend: str = "local"         # nanobot | local
    retries: int = 0


# ---------------------------------------------------------------------------
# Prompt templates (one per capability)
# ---------------------------------------------------------------------------

CAPABILITY_PROMPTS: dict[str, str] = {
    "business_understanding": """You are a Business Analyst. Analyze the following PRD/document and extract:
1. Business domain
2. Value proposition
3. Customer segments
4. Key objectives
5. Revenue model
6. Key activities and resources

PRD: {input_text}

Output JSON with fields: domain, value_proposition, customer_segments (list), objectives (list), revenue_model, key_activities (list), key_resources (list).""",

    "assumption_reasoning": """You are an Assumption Analyst. Given a business model, identify the HIDDEN ASSUMPTIONS that the model depends on. For each assumption:
1. State it clearly as a testable proposition
2. Classify it (market/operational/financial/technical)
3. Rate criticality (critical/high/medium/low)
4. Propose a counterfactual: "If this is wrong, what breaks?"

BUSINESS MODEL:
{business_model}

Output JSON: {{"assumptions": [{{"statement": "...", "category": "...", "criticality": "...", "counterfactual": "..."}}]}}""",

    "risk_analysis": """You are a Risk Analyst. Given a business model and its assumptions, identify risks across these dimensions:
- process (workflow bottlenecks)
- organization (people/talent)
- system (technology/infrastructure)
- compliance (regulatory/legal)
- market (competition/demand)
- financial (revenue/cost)

For each risk: state it clearly, rate severity and probability, propose mitigation.

BUSINESS MODEL: {business_model}
ASSUMPTIONS: {assumptions}

Output JSON: {{"risks": [{{"risk": "...", "dimension": "...", "severity": "...", "probability": "...", "mitigation": "..."}}]}}""",

    "constraint_generation": """You are a Constraint Analyst. Given a business model and risks, identify hard constraints:
- Regulatory constraints
- Resource constraints (budget, talent, time)
- Market constraints
- Technical constraints
- Organizational constraints

For each: state the constraint, classify type, indicate if hard limit, and propose workaround.

BUSINESS MODEL: {business_model}
RISKS: {risks}

Output JSON: {{"constraints": [{{"constraint": "...", "type": "...", "hard_limit": true, "workaround": "..."}}]}}""",

    "sop_design": """You are a Process Designer. Given a business model, design Standard Operating Procedures:
1. Key workflows
2. Roles and responsibilities
3. Decision points
4. SLAs and metrics
5. Handoff points

BUSINESS MODEL: {business_model}

Output JSON with workflows, roles, sla, metrics, kpi sections.""",

    "coverage_analysis": """You are a Coverage Analyst. Given all artifacts so far, assess which business dimensions are covered and which are MISSING. Dimensions to check:
- Market analysis
- Financial modeling
- Risk assessment
- Operational design
- Regulatory compliance
- Technology feasibility
- Customer validation
- Competitive landscape

Score each dimension 0-1 and list missed dimensions.

{all_artifacts}

Output JSON: {{"dimension_scores": {{...}}, "dimensions_missed": [...], "overall_coverage": 0.X}}""",

    "gap_detection": """You are a Gap Detector. Review all artifacts and find:
1. Missing evidence (claims without data)
2. Insufficient analysis (shallow or skipped dimensions)
3. Logical flaws (contradictions, circular reasoning)
4. Model failures (the business model itself doesn't work)

{all_artifacts}

Output JSON: {{"gaps": [{{"gap": "...", "category": "evidence_missing|analysis_insufficient|model_failed", "severity": "...", "recommendation": "..."}}]}}""",

    "decision_support": """You are a Decision Advisor. Given all analysis, propose a clear business decision:
1. State the decision
2. List alternatives considered
3. Provide rationale (why this over alternatives)
4. Assess assumption confidence
5. Evaluate risk acceptability
6. State coverage percentage

{all_artifacts}

Output JSON: {{"decision": "...", "alternatives": [...], "rationale": "...", "assumption_confidence": 0.X, "risk_acceptable": true/false, "coverage_pct": XX}}""",

    "evidence_validation": """You are an Evidence Validator. Given an assumption, determine if evidence supports or refutes it:
1. What data would validate this?
2. What do we actually have?
3. Is the evidence strong enough?

ASSUMPTION: {assumption}
AVAILABLE DATA: {available_evidence}

Output JSON: {{"finding": "...", "evidence_type": "...", "strength": "...", "contradicts": true/false}}""",

    "report_composition": """You are a Report Composer. Compile all analysis into an executive summary:
1. Business overview
2. Key assumptions (validated vs unvalidated)
3. Risk summary (by severity)
4. Gaps identified
5. Decision recommendation
6. Next steps

{all_artifacts}

Output JSON with executive_summary, sections, key_findings, recommendations.""",
}


# ---------------------------------------------------------------------------
# Nanobot Agent Backend (abstracted — swap in real Nanobot later)
# ---------------------------------------------------------------------------

class NanobotAgentBackend:
    """Nanobot-compatible agent execution backend.

    This is designed to be replaced with real Nanobot Agent Loop:
      while task:
          think → tool_call → observe → respond

    Currently uses a local LLM call pattern that mirrors Nanobot's interface.
    When Nanobot is installed, swap the _run_agent method.

    Nanobot concepts mapped:
      - ToolRegistry  → artifact_read / artifact_write tools
      - MemoryStore   → ArtifactGraphStore (already compatible)
      - AgentLoop     → _run_agent() implements the loop
      - MCP           → capability-specific prompt templates
    """

    def __init__(self, store: ArtifactGraphStore, llm_service=None):
        self.store = store
        self._llm = llm_service

    async def execute(
        self, capability: Capability, input_text: str = "", project_id: str = ""
    ) -> ExecutionResult:
        """Execute a capability using Nanobot-aligned agent loop.

        Args:
            capability: The Capability to execute.
            input_text: Raw text input (PRD, etc).
            project_id: Project scope.

        Returns:
            ExecutionResult with produced artifact IDs.
        """
        import time
        t0 = time.perf_counter()

        try:
            # Build the prompt from capability template
            prompt = self._build_prompt(capability, input_text)

            # Nanobot agent loop (simulated)
            llm = self._get_llm()
            response_text = await llm.generate(prompt)

            # Parse response into artifacts
            artifact_ids = self._persist_response(
                response_text, capability, project_id
            )

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "NanobotBackend executed %s: %d artifacts in %.0fms",
                capability.name, len(artifact_ids), elapsed,
            )

            return ExecutionResult(
                capability_name=capability.name,
                status="success",
                artifacts_produced=artifact_ids,
                elapsed_ms=elapsed,
                backend="nanobot",
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("NanobotBackend failed for %s: %s", capability.name, exc)
            return ExecutionResult(
                capability_name=capability.name,
                status="failed",
                error=str(exc),
                elapsed_ms=elapsed,
                backend="nanobot",
            )

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from app.services.llm_adapter import get_llm_adapter
        self._llm = get_llm_adapter()
        return self._llm

    def _build_prompt(self, capability: Capability, input_text: str) -> str:
        """Build the execution prompt from capability template + artifact context."""
        template = CAPABILITY_PROMPTS.get(
            capability.name,
            "Analyze the following and produce structured output:\n\n{input_text}",
        )

        # Gather context from Artifact Graph
        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        risks = self.store.get_by_type(ArtifactType.RISK)

        business_model_text = self._format_artifacts(biz_models)
        assumptions_text = self._format_artifacts(assumptions)
        risks_text = self._format_artifacts(risks)
        all_text = self._format_all_artifacts()

        return template.format(
            input_text=input_text[:4000],
            business_model=business_model_text or "(none)",
            assumptions=assumptions_text or "(none)",
            risks=risks_text or "(none)",
            all_artifacts=all_text or "(none)",
            assumption="(see assumptions above)",
            available_evidence="(see artifacts above)",
        )

    def _format_artifacts(self, artifacts: list) -> str:
        if not artifacts:
            return ""
        lines = []
        for a in artifacts:
            d = a.model_dump()
            # Extract meaningful fields
            parts = []
            for key in ("label", "statement", "risk_statement", "decision_statement",
                        "gap_statement", "constraint_statement", "finding",
                        "description", "rationale", "mitigation"):
                val = d.get(key, "")
                if val:
                    parts.append(f"{key}: {val}")
            if parts:
                lines.append(f"[{a.artifact_id}] {' | '.join(parts)}")
        return "\n".join(lines)

    def _format_all_artifacts(self) -> str:
        lines = []
        for aid in self.store.list_all():
            art = self.store.get(aid)
            if art is None:
                continue
            d = art.model_dump()
            # Compact representation
            compact = {
                "type": d.get("artifact_type", ""),
                "label": d.get("label", ""),
            }
            for key in ("statement", "risk_statement", "decision_statement",
                        "gap_statement", "finding", "rationale", "mitigation",
                        "severity", "validated", "confidence"):
                val = d.get(key, "")
                if val:
                    compact[key] = str(val)
            lines.append(f"  [{art.artifact_id}] {compact}")
        return "\n".join(lines)

    def _persist_response(
        self, response_text: str, capability: Capability, project_id: str
    ) -> list[str]:
        """Parse LLM JSON response and persist as typed Artifacts."""
        artifact_ids: list[str] = []

        # Parse JSON
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning("Could not parse LLM response: %s", text[:200])
                return artifact_ids

        # Map JSON to artifacts based on capability output types
        for at in capability.output_artifact_types:
            artifacts = self._map_to_artifacts(data, at, project_id)
            for art in artifacts:
                self.store.add(art)
                artifact_ids.append(art.artifact_id)

        return artifact_ids

    def _map_to_artifacts(
        self, data: dict, artifact_type: ArtifactType, project_id: str
    ) -> list[BaseArtifact]:
        """Map parsed JSON data to typed artifacts."""
        cls = ARTIFACT_CLASS_MAP.get(artifact_type)
        if cls is None:
            return []

        results = []

        if artifact_type == ArtifactType.BUSINESS_MODEL:
            results.append(cls(
                artifact_type=artifact_type,
                project_id=project_id,
                label=data.get("domain", "Business Model"),
                domain=data.get("domain", ""),
                value_proposition=data.get("value_proposition", ""),
                customer_segments=data.get("customer_segments", []),
                objectives=data.get("objectives", []),
                revenue_model=data.get("revenue_model", ""),
                key_activities=data.get("key_activities", []),
                key_resources=data.get("key_resources", []),
            ))

        elif artifact_type == ArtifactType.ASSUMPTION:
            for a in data.get("assumptions", []):
                results.append(cls(
                    artifact_type=artifact_type,
                    project_id=project_id,
                    label=a.get("statement", "")[:80],
                    statement=a.get("statement", ""),
                    category=a.get("category", ""),
                    criticality=_parse_sev(a.get("criticality", "medium")),
                    counterfactual=a.get("counterfactual", ""),
                ))

        elif artifact_type == ArtifactType.RISK:
            for r in data.get("risks", []):
                results.append(cls(
                    artifact_type=artifact_type,
                    project_id=project_id,
                    label=r.get("risk", "")[:80],
                    risk_statement=r.get("risk", ""),
                    severity=_parse_sev(r.get("severity", "medium")),
                    probability=_parse_sev(r.get("probability", "medium")),
                    mitigation=r.get("mitigation", ""),
                ))

        elif artifact_type == ArtifactType.CONSTRAINT:
            for c in data.get("constraints", []):
                results.append(cls(
                    artifact_type=artifact_type,
                    project_id=project_id,
                    label=c.get("constraint", "")[:80],
                    constraint_statement=c.get("constraint", ""),
                    constraint_type=c.get("type", ""),
                    hard_limit=c.get("hard_limit", True),
                    workaround=c.get("workaround", ""),
                ))

        elif artifact_type == ArtifactType.COVERAGE:
            results.append(cls(
                artifact_type=artifact_type,
                project_id=project_id,
                label="Coverage Analysis",
                dimension_scores=data.get("dimension_scores", {}),
                dimensions_missed=data.get("dimensions_missed", []),
                dimensions_covered=list(data.get("dimension_scores", {}).keys()),
                overall_coverage=data.get("overall_coverage", 0.0),
            ))

        elif artifact_type == ArtifactType.GAP:
            for g in data.get("gaps", []):
                results.append(cls(
                    artifact_type=artifact_type,
                    project_id=project_id,
                    label=g.get("gap", "")[:80],
                    gap_statement=g.get("gap", ""),
                    category=GapCategory(g.get("category", "evidence_missing")),
                    severity=_parse_sev(g.get("severity", "medium")),
                    resolution=g.get("recommendation", ""),
                ))

        elif artifact_type == ArtifactType.DECISION:
            results.append(cls(
                artifact_type=artifact_type,
                project_id=project_id,
                label=data.get("decision", "Decision")[:80],
                decision_statement=data.get("decision", ""),
                alternatives=data.get("alternatives", []),
                rationale=data.get("rationale", ""),
                assumption_confidence=data.get("assumption_confidence", 0.0),
                risk_acceptable=data.get("risk_acceptable", False),
                coverage_pct=data.get("coverage_pct", 0.0),
            ))

        elif artifact_type == ArtifactType.EVIDENCE:
            results.append(cls(
                artifact_type=artifact_type,
                project_id=project_id,
                label=data.get("finding", "Evidence")[:80],
                evidence_type=data.get("evidence_type", ""),
                finding=data.get("finding", ""),
                strength=_parse_sev(data.get("strength", "medium")),
                contradicts=data.get("contradicts", False),
            ))

        return results


# ---------------------------------------------------------------------------
# Local Agent Backend (existing BSC agents)
# ---------------------------------------------------------------------------

class LocalAgentBackend:
    """Backward-compatible backend using existing BSC agents."""

    def __init__(self, store: ArtifactGraphStore):
        self.store = store

    async def execute(
        self, capability: Capability, input_text: str = "", project_id: str = ""
    ) -> ExecutionResult:
        """Execute using existing BSC AgentFactory."""
        import time
        t0 = time.perf_counter()

        try:
            from app.agents.unified_agent import AgentContext, AgentFactory

            ctx = AgentContext(
                project_name=project_id or "default",
                business_system=self.store.export(project_id=project_id),
                params={"capability": capability.name},
            )

            agent = AgentFactory.create_agent(capability.executor_key)
            result = agent.run(ctx)

            artifact_ids: list[str] = []
            if result.status == "completed" and result.data:
                artifact_ids = self._persist_agent_result(
                    result.data, capability, project_id
                )

            elapsed = (time.perf_counter() - t0) * 1000
            return ExecutionResult(
                capability_name=capability.name,
                status="success" if result.status == "completed" else "failed",
                artifacts_produced=artifact_ids,
                elapsed_ms=elapsed,
                backend="local",
                error=result.error or "",
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return ExecutionResult(
                capability_name=capability.name,
                status="failed",
                error=str(exc),
                elapsed_ms=elapsed,
                backend="local",
            )

    def _persist_agent_result(
        self, data: dict, capability: Capability, project_id: str
    ) -> list[str]:
        """Persist agent output as artifacts."""
        artifact_ids: list[str] = []
        for at in capability.output_artifact_types:
            cls = ARTIFACT_CLASS_MAP.get(at)
            if cls is None:
                continue
            try:
                art = cls(
                    artifact_type=at,
                    project_id=project_id,
                    label=data.get("label", at.value),
                )
                self.store.add(art)
                artifact_ids.append(art.artifact_id)
            except Exception as exc:
                logger.debug("Could not persist %s: %s", at.value, exc)
        return artifact_ids


# ---------------------------------------------------------------------------
# Unified Capability Executor
# ---------------------------------------------------------------------------

class CapabilityExecutor:
    """Unified executor — routes to Nanobot or Local backend.

    Usage:
        store = ArtifactGraphStore(...)
        executor = CapabilityExecutor(store, backend="nanobot")
        result = await executor.execute(capability, prd_text)
    """

    def __init__(
        self,
        store: ArtifactGraphStore,
        backend: str = "nanobot",
        llm_service=None,
    ):
        self.store = store
        self.backend_name = backend
        if backend == "nanobot":
            self._backend: NanobotAgentBackend | LocalAgentBackend = (
                NanobotAgentBackend(store, llm_service)
            )
        else:
            self._backend = LocalAgentBackend(store)

    async def execute(
        self, capability: Capability, input_text: str = "", project_id: str = ""
    ) -> ExecutionResult:
        return await self._backend.execute(capability, input_text, project_id)

    async def execute_all(
        self,
        capabilities: list[Capability],
        input_text: str = "",
        project_id: str = "",
        parallel: bool = True,
    ) -> list[ExecutionResult]:
        """Execute multiple capabilities, optionally in parallel."""
        if not parallel or len(capabilities) <= 1:
            results = []
            for cap in capabilities:
                results.append(await self.execute(cap, input_text, project_id))
            return results

        tasks = [
            self.execute(cap, input_text, project_id)
            for cap in capabilities
        ]
        return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sev(value: str) -> Severity:
    mapping = {
        "critical": Severity.CRITICAL, "crit": Severity.CRITICAL,
        "high": Severity.HIGH, "h": Severity.HIGH,
        "medium": Severity.MEDIUM, "med": Severity.MEDIUM, "m": Severity.MEDIUM,
        "low": Severity.LOW, "l": Severity.LOW,
    }
    return mapping.get(str(value).lower().strip(), Severity.MEDIUM)
