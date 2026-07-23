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
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from app.artifacts.store import ArtifactGraphStore
from app.artifacts.types import (
    ArtifactType, BaseArtifact, ARTIFACT_CLASS_MAP,
    BusinessModelArtifact, AssumptionArtifact, RiskArtifact,
    ConstraintArtifact, EvidenceArtifact, CoverageArtifact,
    GapArtifact, DecisionArtifact, DeliverableArtifact, Severity, GapCategory,
)
from app.core.prompt_context import (
    CapabilityPromptBudget,
    PromptContextItem,
    PromptContextUsage,
)
from app.core.llm_usage import ModelUsage
from .registry import Capability, CapabilityRegistry

logger = logging.getLogger(__name__)


MOCK_CAPABILITY_FACTORIES: dict[str, Callable[[], dict[str, Any]]] = {
    "business_understanding": lambda: {
        "domain": "customer_service",
        "value_proposition": "Shorten response time with automation",
        "customer_segments": ["operations_team", "support_managers"],
        "objectives": ["Reduce backlog", "Improve first response quality"],
        "revenue_model": "internal_efficiency",
        "key_activities": ["intake", "triage", "resolution"],
        "key_resources": ["agents", "knowledge_base"],
    },
    "assumption_reasoning": lambda: {
        "assumptions": [{
            "statement": "Customers will accept AI-assisted support",
            "category": "market",
            "criticality": "high",
            "counterfactual": "Escalate to human review for low-confidence cases",
        }],
    },
    "risk_analysis": lambda: {
        "risks": [{
            "risk": "Automation may route critical cases incorrectly",
            "dimension": "process",
            "severity": "high",
            "probability": "medium",
            "mitigation": "Add reviewer checkpoints and exception handling",
        }],
    },
    "constraint_generation": lambda: {
        "constraints": [{
            "constraint": "Sensitive customer data requires approval before export",
            "type": "regulatory",
            "hard_limit": True,
            "workaround": "Keep exports inside the audited workspace",
        }],
    },
    "sop_design": lambda: {
        "kind": "sop",
        "title": "Support intake operating loop",
        "summary": "Triage work before automation and retain exceptions for review.",
        "differentiators": ["Human review threshold is explicit"],
        "sections": [{"title": "Intake", "details": ["Classify and route each request"]}],
        "actions": [{"title": "Triage request", "owner": "Operator", "trigger": "New request", "action": "Classify and route", "output": "assigned case", "metric": "response_time < 10m", "timebox": "5m"}],
        "evidence_gaps": ["No baseline quality data"],
    },
    "strategy_analysis": lambda: {
        "kind": "strategy",
        "title": "Support automation pilot strategy",
        "summary": "Validate one high-volume intent before scaling automation.",
        "differentiators": ["Scale is gated by exception quality"],
        "sections": [{"title": "Pilot", "details": ["Use a single high-volume intent"]}],
        "actions": [{"title": "Run pilot", "owner": "Support lead", "trigger": "Weekly review", "action": "Compare exception rate to baseline", "output": "scale decision", "metric": "exception rate", "timebox": "30m"}],
        "evidence_gaps": ["No demand baseline"],
    },
    "optimization_recommendations": lambda: {
        "kind": "optimization",
        "title": "Classification optimization plan",
        "summary": "Remove repeat triage only after measuring misrouting.",
        "differentiators": ["Misrouting guardrail precedes automation"],
        "sections": [{"title": "Guardrail", "details": ["Review low-confidence classifications"]}],
        "actions": [{"title": "Measure routing", "owner": "Operations analyst", "trigger": "Before rollout", "action": "Sample routing quality", "output": "baseline", "metric": "misroute rate", "timebox": "2h"}],
        "evidence_gaps": ["No current routing sample"],
    },
    "coverage_analysis": lambda: {
        "dimension_scores": {"operations": 0.9, "risk": 0.8, "customer": 0.85},
        "dimensions_missed": [],
        "overall_coverage": 0.85,
    },
    "gap_detection": lambda: {
        "gaps": [{
            "gap": "Need stronger evidence for adoption assumptions",
            "category": "evidence_missing",
            "severity": "medium",
            "recommendation": "Run pilot interviews with support leads",
        }],
    },
    "decision_support": lambda: {
        "decision": "Launch an internal pilot before broad rollout",
        "alternatives": ["Immediate full rollout"],
        "rationale": "Pilot reduces operational risk while validating demand",
        "assumption_confidence": 0.75,
        "risk_acceptable": True,
        "coverage_pct": 85,
    },
    "evidence_validation": lambda: {
        "finding": "Interview feedback supports the assumption",
        "evidence_type": "user_interview",
        "strength": "medium",
        "contradicts": False,
    },
    "report_composition": lambda: {
        "kind": "decision_brief",
        "title": "Support automation decision brief",
        "summary": "Approve a measured pilot, not a broad rollout.",
        "differentiators": ["Decision depends on documented exception evidence"],
        "sections": [{"title": "Recommendation", "details": ["Pilot first"]}],
        "actions": [{"title": "Approve pilot", "owner": "Operations lead", "trigger": "Decision review", "action": "Fund one pilot lane", "output": "pilot charter", "metric": "validated quality", "timebox": "30m"}],
        "evidence_gaps": ["No acceptance baseline"],
    },
}


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
    mode: str = ""                 # real | mock | fallback | compatibility
    retries: int = 0
    error_code: str = ""
    attempts: list["ExecutionAttempt"] = Field(default_factory=list)
    prompt_context: PromptContextUsage | None = None
    model_usage: ModelUsage | None = None


class ExecutionAttempt(BaseModel):
    """One bounded attempt made while executing a capability."""

    attempt: int = Field(gt=0)
    outcome: str  # success | failed | timeout
    elapsed_ms: float = 0.0
    error_code: str = ""
    error: str = ""
    retryable: bool = False


class CapabilityExecutionPolicy(BaseModel):
    """Operational limits shared by native and compatibility capabilities."""

    max_attempts: int = Field(default=3, ge=1, le=5)
    attempt_timeout_seconds: float = Field(default=90.0, gt=0, le=900)
    initial_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    max_backoff_seconds: float = Field(default=4.0, ge=0, le=60)
    backoff_multiplier: float = Field(default=2.0, ge=1, le=10)

    def delay_before_retry(self, failed_attempt: int) -> float:
        delay = self.initial_backoff_seconds * (
            self.backoff_multiplier ** max(failed_attempt - 1, 0)
        )
        return min(delay, self.max_backoff_seconds)


@dataclass
class CallableExecutionOutcome:
    """Value and telemetry from a direct capability callable."""

    value: Any = None
    execution: ExecutionResult = field(default_factory=ExecutionResult)


@dataclass
class _PolicyRun:
    value: Any = None
    attempts: list[ExecutionAttempt] = field(default_factory=list)
    elapsed_ms: float = 0.0
    error_code: str = ""
    error: str = ""


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

    "sop_design": """You are a Process Designer. Build a project-specific operating procedure, not a generic template.
Use only stated facts and the project knowledge in the input. Separate every missing fact into evidence_gaps; do not invent a market, role, metric, or baseline.

BUSINESS MODEL: {business_model}

Output exactly one JSON object: {{"kind":"sop","title":"...","summary":"...","differentiators":["specific decision or operating constraint"],"sections":[{{"title":"...","details":["..."]}}],"actions":[{{"title":"...","owner":"...","trigger":"...","action":"...","output":"...","metric":"...","timebox":"..."}}],"evidence_gaps":["..."]}}.
Each action must be executable and must expose its trigger, accountable owner, output and success measure.""",

    "strategy_analysis": """You are a Strategy Analyst. Form a project-specific strategic path from the available business artifacts and project knowledge.
Do not reuse generic expansion or pilot advice. Identify the distinctive bet, the evidence that supports it, and the uncertainty that could invalidate it.

BUSINESS MODEL: {business_model}
RISKS: {risks}

Output exactly one JSON object: {{"kind":"strategy","title":"...","summary":"...","differentiators":["..."],"sections":[{{"title":"...","details":["..."]}}],"actions":[{{"title":"...","owner":"...","trigger":"...","action":"...","output":"...","metric":"...","timebox":"..."}}],"evidence_gaps":["..."]}}.""",

    "optimization_recommendations": """You are an Operations Optimizer. Produce a constrained improvement plan tailored to the project artifacts and project knowledge.
Prioritize bottlenecks that are actually evidenced. State the guardrail that prevents optimization from harming quality, compliance, or the user experience.

BUSINESS MODEL: {business_model}
CONSTRAINTS: {all_artifacts}

Output exactly one JSON object: {{"kind":"optimization","title":"...","summary":"...","differentiators":["..."],"sections":[{{"title":"...","details":["..."]}}],"actions":[{{"title":"...","owner":"...","trigger":"...","action":"...","output":"...","metric":"...","timebox":"..."}}],"evidence_gaps":["..."]}}.""",

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

    "report_composition": """You are a Report Composer. Write a decision brief for this specific project, using the artifacts and project knowledge provided.
Make the recommendation traceable: distinguish evidence from assumptions, preserve unresolved evidence gaps, and name the exact next action that changes the decision.

{all_artifacts}

Output exactly one JSON object: {{"kind":"decision_brief","title":"...","summary":"...","differentiators":["..."],"sections":[{{"title":"...","details":["..."]}}],"actions":[{{"title":"...","owner":"...","trigger":"...","action":"...","output":"...","metric":"...","timebox":"..."}}],"evidence_gaps":["..."]}}.""",
}


# ---------------------------------------------------------------------------
# Nanobot-aligned capability backend
# ---------------------------------------------------------------------------

class NanobotAgentBackend:
    """Nanobot-compatible agent execution backend.

    BSC capabilities are single-turn structured analyses: the prompt is the
    task, the provider response is the observation, and typed Artifact
    persistence is the state update. The shared execution policy supplies the
    bounded lifecycle around that turn.

    Nanobot concepts mapped:
      - ToolRegistry  → artifact_read / artifact_write tools
      - MemoryStore   → ArtifactGraphStore (already compatible)
      - AgentLoop     → _run_agent() implements the loop
      - MCP           → capability-specific prompt templates
    """

    def __init__(
        self,
        store: ArtifactGraphStore,
        llm_service=None,
        prompt_budget: CapabilityPromptBudget | None = None,
    ):
        self.store = store
        self._llm = llm_service
        self._prompt_budget = prompt_budget or _default_prompt_context_budget()

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
        llm = None
        prompt_context = None
        model_usage = None

        try:
            llm = self._get_llm()
            if _uses_mock_capability_response(llm):
                artifact_ids = self._persist_mock_response(capability, project_id)
                elapsed = (time.perf_counter() - t0) * 1000
                return ExecutionResult(
                    capability_name=capability.name,
                    status="success",
                    artifacts_produced=artifact_ids,
                    elapsed_ms=elapsed,
                    backend="nanobot-mock",
                    mode="mock",
                )

            # Build a bounded, artifact-aware prompt before invoking the model.
            prompt, prompt_context = self._build_prompt_with_usage(capability, input_text)

            # Complete the capability turn and persist its typed observation.
            response_text = await llm.generate(prompt)
            usage = getattr(llm, "last_usage", None)
            model_usage = usage if isinstance(usage, ModelUsage) else None

            execution_mode = getattr(llm, "last_mode", "") or "real"
            if execution_mode == "fallback":
                # LLMService has already policy-gated this development fallback.
                # Use the capability's structured fixture rather than parsing its
                # generic fallback text, which cannot satisfy each output schema.
                artifact_ids = self._persist_mock_response(capability, project_id)
            else:
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
                mode=execution_mode,
                prompt_context=prompt_context,
                model_usage=model_usage,
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
                mode=getattr(llm, "last_mode", "") or "real",
                prompt_context=prompt_context,
                model_usage=model_usage,
            )

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from app.services.llm_adapter import get_llm_adapter
        self._llm = get_llm_adapter()
        return self._llm

    def _persist_mock_response(
        self,
        capability: Capability,
        project_id: str,
    ) -> list[str]:
        factory = MOCK_CAPABILITY_FACTORIES.get(capability.name)
        if factory is None:
            return []
        payload = factory()
        artifact_ids: list[str] = []
        for at in capability.output_artifact_types:
            artifacts = self._map_to_artifacts(payload, at, project_id)
            for art in artifacts:
                self.store.add(art)
                artifact_ids.append(art.artifact_id)
        return artifact_ids

    def _build_prompt(self, capability: Capability, input_text: str) -> str:
        """Build the execution prompt from capability template + artifact context."""
        return self._build_prompt_with_usage(capability, input_text)[0]

    def _build_prompt_with_usage(
        self,
        capability: Capability,
        input_text: str,
    ) -> tuple[str, PromptContextUsage]:
        template = CAPABILITY_PROMPTS.get(
            capability.name,
            "Analyze the following and produce structured output:\n\n{input_text}",
        )

        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        risks = self.store.get_by_type(ArtifactType.RISK)
        all_artifacts = self._ranked_artifacts(capability)
        rendered = self._prompt_budget.render(
            template,
            input_text=input_text,
            context_blocks=[
                ("business_model", self._prompt_context_items(biz_models)),
                ("assumptions", self._prompt_context_items(assumptions)),
                ("risks", self._prompt_context_items(risks)),
                ("all_artifacts", self._prompt_context_items(all_artifacts)),
                ("assumption", self._prompt_context_items(assumptions[:1])),
                ("available_evidence", self._prompt_context_items(all_artifacts)),
            ],
        )
        return rendered.prompt, rendered.usage

    def _ranked_artifacts(self, capability: Capability) -> list[BaseArtifact]:
        artifacts = [
            self.store.get(artifact_id)
            for artifact_id in self.store.list_all()
        ]
        ranked = [artifact for artifact in artifacts if artifact is not None]
        ranked.sort(key=lambda artifact: artifact.artifact_id)
        ranked.sort(key=lambda artifact: artifact.created_at, reverse=True)
        ranked.sort(key=self._artifact_severity_priority)
        input_types = set(capability.input_artifact_types)
        ranked.sort(
            key=lambda artifact: 0 if artifact.artifact_type in input_types else 1
        )
        return ranked

    @staticmethod
    def _artifact_severity_priority(artifact: BaseArtifact) -> int:
        value = getattr(artifact, "severity", None) or getattr(
            artifact, "criticality", None
        )
        normalized = getattr(value, "value", value)
        return {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }.get(str(normalized).lower(), 4)

    def _prompt_context_items(self, artifacts: list[BaseArtifact]) -> list[PromptContextItem]:
        return [
            PromptContextItem(
                artifact_id=artifact.artifact_id,
                text=self._format_prompt_artifact(artifact),
            )
            for artifact in artifacts
        ]

    @staticmethod
    def _format_prompt_artifact(artifact: BaseArtifact) -> str:
        data = artifact.model_dump()
        fields = (
            "label", "domain", "value_proposition", "customer_segments",
            "objectives", "key_activities", "key_resources", "statement",
            "project_thesis", "distinctive_bets", "key_unknowns", "success_metrics",
            "category", "criticality", "counterfactual", "risk_statement",
            "dimension", "severity", "probability", "mitigation",
            "constraint_statement", "constraint_type", "hard_limit", "workaround",
            "finding", "evidence_type", "strength", "contradicts",
            "dimension_scores", "dimensions_missed", "overall_coverage",
            "gap_statement", "resolution", "decision_statement", "alternatives",
            "rationale", "assumption_confidence", "risk_acceptable", "coverage_pct",
            "kind", "title", "summary", "differentiators", "sections", "actions",
            "evidence_gaps", "context_pack_id",
            "confidence", "status",
        )
        parts = [f"[{artifact.artifact_id}] type: {artifact.artifact_type.value}"]
        for field_name in fields:
            value = data.get(field_name)
            if value is None or value == "" or value == [] or value == {}:
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"{field_name}: {value}")
        return " | ".join(parts)

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
            artifact_data = data
            if at == ArtifactType.DELIVERABLE and not data.get("kind"):
                artifact_data = {
                    **data,
                    "kind": _deliverable_kind(capability.name),
                }
            artifacts = self._map_to_artifacts(artifact_data, at, project_id)
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
                project_thesis=data.get("project_thesis", ""),
                distinctive_bets=_string_list(data.get("distinctive_bets")),
                key_unknowns=_string_list(data.get("key_unknowns")),
                success_metrics=_string_list(data.get("success_metrics")),
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
                    category=_parse_gap_category(g.get("category")),
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

        elif artifact_type == ArtifactType.DELIVERABLE:
            title = str(data.get("title") or "Project deliverable")
            results.append(cls(
                artifact_type=artifact_type,
                project_id=project_id,
                label=title[:80],
                kind=str(data.get("kind") or "deliverable"),
                title=title,
                summary=str(data.get("summary") or ""),
                differentiators=_string_list(data.get("differentiators")),
                sections=_object_list(data.get("sections")),
                actions=_object_list(data.get("actions")),
                evidence_gaps=_string_list(data.get("evidence_gaps")),
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
        policy: CapabilityExecutionPolicy | None = None,
    ):
        self.store = store
        self.backend_name = backend
        self.policy = policy or _default_execution_policy()
        if backend == "nanobot":
            self._backend: NanobotAgentBackend | LocalAgentBackend = (
                NanobotAgentBackend(store, llm_service)
            )
        else:
            self._backend = LocalAgentBackend(store)

    async def execute(
        self, capability: Capability, input_text: str = "", project_id: str = ""
    ) -> ExecutionResult:
        run = await self._run_with_policy(
            capability,
            lambda: self._backend.execute(capability, input_text, project_id),
        )
        return self._execution_result(capability.name, run)

    async def execute_callable(
        self,
        capability: Capability,
        operation: Callable[[], Awaitable[Any]],
        *,
        backend: str = "callable",
    ) -> CallableExecutionOutcome:
        """Apply the same policy to direct compatibility capability callables."""
        run = await self._run_with_policy(capability, operation)
        execution = self._execution_result(capability.name, run, backend=backend)
        return CallableExecutionOutcome(
            value=run.value if execution.status == "success" else None,
            execution=execution,
        )

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

    async def _run_with_policy(
        self,
        capability: Capability,
        operation: Callable[[], Awaitable[Any]],
    ) -> _PolicyRun:
        started = time.perf_counter()
        attempts: list[ExecutionAttempt] = []
        last_value: Any = None
        last_error = ""
        last_error_code = ""

        for attempt_number in range(1, self.policy.max_attempts + 1):
            attempt_started = time.perf_counter()
            try:
                value = await asyncio.wait_for(
                    operation(),
                    timeout=self.policy.attempt_timeout_seconds,
                )
                if isinstance(value, ExecutionResult) and value.status != "success":
                    last_value = value
                    last_error = value.error or "capability execution failed"
                    last_error_code, retryable = _classify_execution_failure(last_error)
                    attempts.append(ExecutionAttempt(
                        attempt=attempt_number,
                        outcome="failed",
                        elapsed_ms=(time.perf_counter() - attempt_started) * 1000,
                        error_code=last_error_code,
                        error=last_error,
                        retryable=retryable,
                    ))
                elif _is_empty_capability_output(capability, value):
                    last_value = value
                    last_error = "capability produced no artifacts"
                    last_error_code = "empty_output"
                    retryable = False
                    attempts.append(ExecutionAttempt(
                        attempt=attempt_number,
                        outcome="failed",
                        elapsed_ms=(time.perf_counter() - attempt_started) * 1000,
                        error_code=last_error_code,
                        error=last_error,
                        retryable=False,
                    ))
                else:
                    attempts.append(ExecutionAttempt(
                        attempt=attempt_number,
                        outcome="success",
                        elapsed_ms=(time.perf_counter() - attempt_started) * 1000,
                    ))
                    return _PolicyRun(
                        value=value,
                        attempts=attempts,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                last_error = (
                    "capability attempt timed out after "
                    f"{self.policy.attempt_timeout_seconds:g}s"
                )
                last_error_code = "timeout"
                retryable = True
                attempts.append(ExecutionAttempt(
                    attempt=attempt_number,
                    outcome="timeout",
                    elapsed_ms=(time.perf_counter() - attempt_started) * 1000,
                    error_code=last_error_code,
                    error=last_error,
                    retryable=True,
                ))
            except Exception as exc:
                last_error = str(exc) or type(exc).__name__
                last_error_code, retryable = _classify_execution_failure(
                    last_error,
                    exception=exc,
                )
                attempts.append(ExecutionAttempt(
                    attempt=attempt_number,
                    outcome="failed",
                    elapsed_ms=(time.perf_counter() - attempt_started) * 1000,
                    error_code=last_error_code,
                    error=last_error,
                    retryable=retryable,
                ))

            if not retryable or attempt_number >= self.policy.max_attempts:
                break
            delay = self.policy.delay_before_retry(attempt_number)
            if delay:
                await asyncio.sleep(delay)

        return _PolicyRun(
            value=last_value,
            attempts=attempts,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            error_code=last_error_code,
            error=last_error,
        )

    def _execution_result(
        self,
        capability_name: str,
        run: _PolicyRun,
        *,
        backend: str | None = None,
    ) -> ExecutionResult:
        if isinstance(run.value, ExecutionResult):
            result = run.value.model_copy(deep=True)
        elif run.error:
            result = ExecutionResult(
                capability_name=capability_name,
                status="failed",
                backend=backend or self.backend_name,
                error=run.error,
                error_code=run.error_code,
            )
        else:
            result = ExecutionResult(
                capability_name=capability_name,
                status="success",
                backend=backend or self.backend_name,
            )

        if run.error:
            result.status = "failed"
            result.error = run.error
            result.error_code = run.error_code
        result.elapsed_ms = run.elapsed_ms
        result.retries = max(len(run.attempts) - 1, 0)
        result.attempts = run.attempts
        return result


def assert_mock_coverage(registry: CapabilityRegistry) -> None:
    """Fail fast when a registered capability has no deterministic mock path."""
    missing = [
        cap.name
        for cap in registry.list_all()
        if cap.executor_fn is None and cap.name not in MOCK_CAPABILITY_FACTORIES
    ]
    if missing:
        raise ValueError(
            "Missing mock coverage for capabilities: " + ", ".join(sorted(missing))
        )


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


def _parse_gap_category(value: Any) -> GapCategory:
    normalized = str(value or "").lower().strip().replace("-", "_").replace(" ", "_")
    mapping = {
        "evidence_missing": GapCategory.EVIDENCE_MISSING,
        "missing_evidence": GapCategory.EVIDENCE_MISSING,
        "evidence_gap": GapCategory.EVIDENCE_MISSING,
        "data_missing": GapCategory.EVIDENCE_MISSING,
        "analysis_insufficient": GapCategory.ANALYSIS_INSUFFICIENT,
        "logical_flaw": GapCategory.ANALYSIS_INSUFFICIENT,
        "logic_flaw": GapCategory.ANALYSIS_INSUFFICIENT,
        "incomplete_analysis": GapCategory.ANALYSIS_INSUFFICIENT,
        "model_failed": GapCategory.MODEL_FAILED,
        "model_failure": GapCategory.MODEL_FAILED,
        "invalid_model": GapCategory.MODEL_FAILED,
    }
    return mapping.get(normalized, GapCategory.ANALYSIS_INSUFFICIENT)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _deliverable_kind(capability_name: str) -> str:
    return {
        "sop_design": "sop",
        "strategy_analysis": "strategy",
        "optimization_recommendations": "optimization",
        "report_composition": "decision_brief",
    }.get(capability_name, "deliverable")


def _uses_mock_capability_response(llm: Any) -> bool:
    provider = str(getattr(llm, "provider", "") or "")
    force_mock = bool(getattr(llm, "force_mock", False))
    return force_mock or provider == "mock"


def _is_empty_capability_output(capability: Capability, value: Any) -> bool:
    return (
        isinstance(value, ExecutionResult)
        and value.status == "success"
        and bool(capability.output_artifact_types)
        and not value.artifacts_produced
    )


def _classify_execution_failure(
    message: str,
    *,
    exception: BaseException | None = None,
) -> tuple[str, bool]:
    """Return a stable error code and whether another attempt is justified."""
    normalized = message.lower()
    if isinstance(exception, (ConnectionError, OSError)):
        return "transport", True
    if any(token in normalized for token in ("cancelled", "canceled")):
        return "cancelled", False
    if any(token in normalized for token in ("invalid", "validation", "schema", "payload")):
        return "invalid_request", False
    if any(token in normalized for token in ("permission", "unauthorized", "forbidden")):
        return "permission_denied", False
    if any(token in normalized for token in ("rate limit", "429")):
        return "rate_limited", True
    if any(token in normalized for token in (
        "temporary", "temporarily", "unavailable", "overload", "connection",
        "network", "gateway", "reset", "refused", "5xx", "internal server error",
    )):
        return "transient", True
    if "empty" in normalized or "no artifacts" in normalized:
        return "empty_output", False
    return "execution_failed", False


def _default_execution_policy() -> CapabilityExecutionPolicy:
    from app.core.config import settings

    return CapabilityExecutionPolicy(
        max_attempts=settings.CAPABILITY_MAX_ATTEMPTS,
        attempt_timeout_seconds=settings.CAPABILITY_ATTEMPT_TIMEOUT_SECONDS,
        initial_backoff_seconds=settings.CAPABILITY_INITIAL_BACKOFF_SECONDS,
        max_backoff_seconds=settings.CAPABILITY_MAX_BACKOFF_SECONDS,
    )


def _default_prompt_context_budget() -> CapabilityPromptBudget:
    from app.core.config import settings

    return CapabilityPromptBudget(
        max_tokens=settings.CAPABILITY_PROMPT_MAX_TOKENS,
        input_max_tokens=settings.CAPABILITY_PROMPT_INPUT_MAX_TOKENS,
        artifact_max_tokens=settings.CAPABILITY_PROMPT_ARTIFACT_MAX_TOKENS,
    )
