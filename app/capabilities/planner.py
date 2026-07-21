"""Phase 2 - Mission Planner: LLM-driven business mission planning.

ADR-010: Planner selects Capability, not Agent.
Outputs a MissionGraph — a structured plan of what capabilities are needed
and in what execution order, rather than a fixed agent DAG.

Three-level fallback:
  L0: LLM generates MissionGraph from PRD
  L1: Template-based (domain → capabilities mapping)
  L2: Full static DAG (existing pipeline — ultimate safety net)

Usage:
    from app.capabilities.planner import MissionPlanner, MissionGraph
    from app.capabilities import build_default_registry

    planner = MissionPlanner(registry=build_default_registry())
    mission = await planner.plan("PRD: AI SaaS 订阅业务...")
    print(mission.required_capabilities)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from .registry import Capability, CapabilityRegistry
from app.artifacts.types import ArtifactType
from app.core.llm_policy import ensure_fallback_allowed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mission Graph models
# ---------------------------------------------------------------------------

class MissionGoal(BaseModel):
    """A single goal within a mission."""
    goal_id: str = ""
    description: str = ""
    priority: str = "medium"       # high | medium | low
    success_criteria: list[str] = Field(default_factory=list)


class MissionStep(BaseModel):
    """A single execution step in the mission graph."""
    step_id: str = ""
    capability_name: str = ""       # references Capability.name
    depends_on: list[str] = Field(default_factory=list)  # step_ids this depends on
    artifact_inputs: list[str] = Field(default_factory=list)     # ArtifactType values
    artifact_outputs: list[str] = Field(default_factory=list)    # ArtifactType values
    reasoning: str = ""             # why this capability was selected
    parallel_group: int = 0         # steps with same group can run in parallel


class MissionGraph(BaseModel):
    """The output of Mission Planning — a structured execution plan.

    This replaces the old Planner output dict:
      {"agents": [...], "execution_order": [...]}
    """
    mission_id: str = ""
    mission: str = ""               # e.g. "evaluate_business_model"
    title: str = ""
    domain: str = ""

    # Strategic intent
    goals: list[MissionGoal] = Field(default_factory=list)

    # Execution plan
    steps: list[MissionStep] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)

    # Metadata
    planning_mode: str = "llm"      # llm | template | static
    confidence: float = 0.8
    reasoning: str = ""

    def get_parallel_groups(self) -> dict[int, list[MissionStep]]:
        """Group steps by parallel_group for concurrent execution."""
        groups: dict[int, list[MissionStep]] = {}
        for step in self.steps:
            groups.setdefault(step.parallel_group, []).append(step)
        return groups

    def get_execution_order(self) -> list[MissionStep]:
        """Topological sort of steps by dependency."""
        order: list[MissionStep] = []
        completed: set[str] = set()
        remaining = list(self.steps)

        while remaining:
            ready = [
                s for s in remaining
                if all(d in completed for d in s.depends_on)
            ]
            if not ready:
                # circular dependency fallback: take remaining in order
                order.extend(remaining)
                break
            order.extend(ready)
            for s in ready:
                completed.add(s.step_id)
            remaining = [s for s in remaining if s.step_id not in completed]

        return order


# ---------------------------------------------------------------------------
# Mission Planner
# ---------------------------------------------------------------------------

# Domain → capability mapping for L1 template fallback
_DOMAIN_TEMPLATES: dict[str, list[str]] = {
    "ecommerce": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "constraint_generation",
        "sop_design", "coverage_analysis",
        "gap_detection", "decision_support",
        "report_composition",
    ],
    "fintech": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "constraint_generation",
        "coverage_analysis", "gap_detection",
        "decision_support", "report_composition",
    ],
    "healthcare": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "constraint_generation",
        "sop_design", "coverage_analysis",
        "gap_detection", "decision_support",
        "report_composition",
    ],
    "saas": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "strategy_analysis",
        "optimization_recommendations",
        "coverage_analysis", "gap_detection",
        "decision_support", "report_composition",
    ],
    "education": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "constraint_generation",
        "sop_design", "coverage_analysis",
        "gap_detection", "decision_support",
        "report_composition",
    ],
    "default": [
        "business_understanding", "assumption_reasoning",
        "risk_analysis", "constraint_generation",
        "coverage_analysis", "gap_detection",
        "decision_support", "report_composition",
    ],
}

# Static DAG fallback (L2) — maps to original pipeline stages
_STATIC_STEPS: list[dict[str, Any]] = [
    {"capability_name": "business_understanding", "depends_on": [], "parallel_group": 0},
    {"capability_name": "assumption_reasoning", "depends_on": ["business_understanding"], "parallel_group": 1},
    {"capability_name": "risk_analysis", "depends_on": ["business_understanding"], "parallel_group": 1},
    {"capability_name": "constraint_generation", "depends_on": ["risk_analysis"], "parallel_group": 2},
    {"capability_name": "coverage_analysis", "depends_on": ["risk_analysis", "assumption_reasoning"], "parallel_group": 3},
    {"capability_name": "gap_detection", "depends_on": ["coverage_analysis"], "parallel_group": 4},
    {"capability_name": "decision_support", "depends_on": ["coverage_analysis"], "parallel_group": 5},
    {"capability_name": "report_composition", "depends_on": ["decision_support"], "parallel_group": 6},
]


class MissionPlanner:
    """LLM-driven mission planner with 3-level fallback.

    Usage:
        planner = MissionPlanner(registry=build_default_registry())
        mission = await planner.plan(prd_text="...")
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        llm_service: Any = None,  # lazy-load LLMService
        mode: str = "llm",        # llm | template | static
    ):
        self.registry = registry
        self._llm = llm_service
        self.mode = mode

    async def plan(
        self,
        prd_text: str,
        domain_hint: str = "",
        goals: list[str] | None = None,
    ) -> MissionGraph:
        """Generate a MissionGraph from a PRD document.

        Args:
            prd_text: The PRD / business document text.
            domain_hint: Optional domain (ecommerce, fintech, saas, etc).
            goals: Optional explicit goals to guide planning.

        Returns:
            MissionGraph ready for execution.
        """
        if self.mode == "static":
            return self._plan_static(prd_text, domain_hint, goals)

        if self.mode == "template":
            return self._plan_template(prd_text, domain_hint, goals)

        # L0: try LLM
        try:
            return await self._plan_llm(prd_text, domain_hint, goals)
        except Exception as exc:
            logger.warning("LLM planning failed (%s), falling back to template", exc)
            ensure_fallback_allowed("Mission Planner")

        # L1 fallback
        try:
            return self._plan_template(prd_text, domain_hint, goals)
        except Exception as exc:
            logger.warning("Template planning failed (%s), falling back to static", exc)

        # L2 ultimate fallback
        return self._plan_static(prd_text, domain_hint, goals)

    # ------------------------------------------------------------------
    # L0: LLM planning
    # ------------------------------------------------------------------

    async def _plan_llm(
        self, prd_text: str, domain_hint: str, goals: list[str] | None
    ) -> MissionGraph:
        """Use LLM to generate a MissionGraph."""
        llm = self._get_llm()

        capability_catalog = self._build_capability_prompt()
        prompt = self._build_planning_prompt(prd_text, domain_hint, goals, capability_catalog)

        response_text = await llm.generate(prompt)
        return self._parse_llm_response(response_text, prd_text)

    def _get_llm(self) -> Any:
        if self._llm is not None:
            return self._llm
        from app.services.llm_adapter import get_llm_adapter
        self._llm = get_llm_adapter()
        return self._llm

    def _build_capability_prompt(self) -> str:
        """Build a structured catalog description for the LLM prompt."""
        lines = []
        for cap in self.registry.list_all():
            lines.append(
                f"- {cap.name}: {cap.description} "
                f"(inputs: {[t.value for t in cap.input_artifact_types]}, "
                f"outputs: {[t.value for t in cap.output_artifact_types]})"
            )
        return "\n".join(lines)

    def _build_planning_prompt(
        self, prd_text: str, domain_hint: str, goals: list[str] | None,
        capability_catalog: str,
    ) -> str:
        domain_line = f"Domain: {domain_hint}\n" if domain_hint else ""
        goals_line = f"Goals: {', '.join(goals)}\n" if goals else ""

        return f"""You are a Business Mission Planner for an Agent OS.

Your task: analyze a business PRD and produce a MISSION GRAPH — a structured execution plan that selects BUSINESS CAPABILITIES (not agents).

{domain_line}{goals_line}
AVAILABLE CAPABILITIES:
{capability_catalog}

ARTIFACT TYPES (knowledge units):
- business_model: core business description
- assumption: hidden assumptions behind the model
- risk: identified risks
- constraint: boundaries and limitations
- evidence: empirical data
- coverage: dimension coverage analysis
- gap: identified gaps
- decision: business decisions with rationale

PRD TEXT:
{prd_text[:4000]}

OUTPUT FORMAT (JSON only, no markdown):
{{
  "mission": "evaluate_business_model",
  "title": "short descriptive title",
  "domain": "inferred domain",
  "goals": [
    {{"goal_id": "g1", "description": "...", "priority": "high|medium|low"}}
  ],
  "steps": [
    {{
      "step_id": "s1",
      "capability_name": "business_understanding",
      "depends_on": [],
      "parallel_group": 0,
      "reasoning": "why this capability"
    }}
  ],
  "confidence": 0.85,
  "reasoning": "overall planning rationale"
}}

RULES:
1. Select ONLY from available capabilities.
2. Every step MUST produce or consume artifact types declared in the capability.
3. Steps with the same parallel_group can run concurrently.
4. depends_on must reference step_ids (not capability names).
5. Start with business_understanding (parallel_group=0).
6. End with report_composition (last step).
7. Mark domain-specific steps: saas→strategy, operations→sop_design, etc.
"""

    def _parse_llm_response(self, response_text: str, prd_text: str) -> MissionGraph:
        """Parse LLM JSON output into a MissionGraph."""
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the text
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}")

        # Validate capabilities exist
        valid_steps = []
        for step_data in data.get("steps", []):
            cap_name = step_data.get("capability_name", "")
            if self.registry.get(cap_name):
                valid_steps.append(MissionStep(**{
                    "step_id": step_data.get("step_id", f"s{len(valid_steps)}"),
                    "capability_name": cap_name,
                    "depends_on": step_data.get("depends_on", []),
                    "artifact_inputs": step_data.get("artifact_inputs", []),
                    "artifact_outputs": step_data.get("artifact_outputs", []),
                    "reasoning": step_data.get("reasoning", ""),
                    "parallel_group": step_data.get("parallel_group", len(valid_steps)),
                }))
            else:
                logger.warning("LLM suggested unknown capability: %s", cap_name)

        if not valid_steps:
            raise ValueError("LLM mission plan has no executable capability steps")

        goals = [
            MissionGoal(**g) for g in data.get("goals", [])
        ]

        return MissionGraph(
            mission_id=data.get("mission", "evaluate"),
            mission=data.get("mission", "evaluate_business_model"),
            title=data.get("title", "Business Analysis"),
            domain=data.get("domain", ""),
            goals=goals,
            steps=valid_steps,
            required_capabilities=[s.capability_name for s in valid_steps],
            planning_mode="llm",
            confidence=data.get("confidence", 0.8),
            reasoning=data.get("reasoning", ""),
        )

    # ------------------------------------------------------------------
    # L1: Template-based planning
    # ------------------------------------------------------------------

    def _plan_template(
        self, prd_text: str, domain_hint: str, goals: list[str] | None
    ) -> MissionGraph:
        """Template-based mission plan using domain→capability mapping."""
        domain = domain_hint or self._infer_domain(prd_text)
        cap_names = _DOMAIN_TEMPLATES.get(domain, _DOMAIN_TEMPLATES["default"])

        # Filter to only registered capabilities
        valid_caps = [c for c in cap_names if self.registry.get(c)]

        # Look up each capability to get artifact I/O
        steps = []
        for i, cap_name in enumerate(valid_caps):
            cap = self.registry.get(cap_name)
            if cap is None:
                continue
            depends = [f"s{j}" for j in range(i) if j < i and j < i - 2 < 4][:2]
            steps.append(MissionStep(
                step_id=f"s{i}",
                capability_name=cap_name,
                depends_on=depends if i > 0 else [],
                artifact_inputs=[t.value for t in cap.input_artifact_types],
                artifact_outputs=[t.value for t in cap.output_artifact_types],
                reasoning=f"Template: domain={domain} includes {cap_name}",
                parallel_group=i,
            ))

        return MissionGraph(
            mission_id=f"template_{domain}",
            mission="evaluate_business_model",
            title=f"{domain.title()} Business Analysis",
            domain=domain,
            goals=[MissionGoal(goal_id="g1", description="Comprehensive business analysis")],
            steps=steps,
            required_capabilities=valid_caps,
            planning_mode="template",
            confidence=0.6,
            reasoning=f"Template plan for domain: {domain}",
        )

    # ------------------------------------------------------------------
    # L2: Static DAG (ultimate fallback)
    # ------------------------------------------------------------------

    def _plan_static(
        self, prd_text: str, domain_hint: str, goals: list[str] | None
    ) -> MissionGraph:
        """Static DAG — always works, used as ultimate fallback."""
        steps = []
        for i, step_def in enumerate(_STATIC_STEPS):
            cap = self.registry.get(step_def["capability_name"])
            if cap is None:
                continue
            steps.append(MissionStep(
                step_id=f"static_s{i}",
                capability_name=step_def["capability_name"],
                depends_on=step_def["depends_on"],
                artifact_inputs=[t.value for t in cap.input_artifact_types],
                artifact_outputs=[t.value for t in cap.output_artifact_types],
                reasoning="Static fallback DAG",
                parallel_group=step_def["parallel_group"],
            ))

        return MissionGraph(
            mission_id="static_fallback",
            mission="evaluate_business_model",
            title="Business Analysis (Static Plan)",
            domain=domain_hint or "general",
            goals=[MissionGoal(goal_id="g1", description="Comprehensive business analysis")],
            steps=steps,
            required_capabilities=[s.capability_name for s in steps],
            planning_mode="static",
            confidence=1.0,
            reasoning="Static DAG fallback — guaranteed to produce valid output",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_domain(self, prd_text: str) -> str:
        """Simple keyword-based domain inference."""
        lower = prd_text.lower()
        domain_keywords = {
            "ecommerce": ["电商", "ecommerce", "商城", "订单", "支付"],
            "fintech": ["金融", "支付", "贷款", "理财", "保险", "fintech", "bank"],
            "healthcare": ["医疗", "医院", "患者", "诊断", "healthcare", "药"],
            "saas": ["saas", "订阅", "subscription", "平台", "云服务", "api"],
            "education": ["教育", "课程", "培训", "学习", "education", "讲师", "学生"],
        }
        for domain, keywords in domain_keywords.items():
            if any(kw in lower for kw in keywords):
                return domain
        return "default"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_planner(
    registry: Optional[CapabilityRegistry] = None,
    mode: str = "llm",
) -> MissionPlanner:
    """Create a MissionPlanner with default registry if none provided."""
    if registry is None:
        from .registry import build_default_registry
        registry = build_default_registry()
    return MissionPlanner(registry=registry, mode=mode)
