"""Phase 3 - Business Runtime: Three-loop execution engine.

ADR-010 principle #3: Business Runtime must have a Loop.
while mission: plan → execute → reflect (max 3 rounds)

Three loops:
  Mission Loop:   plan() → replan() based on reflection
  Execution Loop: execute() capabilities → update Artifact Graph
  Reflection Loop: evaluate() gaps → classify → resolve

Dual-track: Legacy pipeline (static) and Adaptive Runtime coexist.
"""

from __future__ import annotations

import asyncio
import inspect
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.artifacts.store import ArtifactGraphStore
from app.artifacts.types import (
    ArtifactType, BaseArtifact, Severity,
    BusinessModelArtifact, AssumptionArtifact, RiskArtifact,
    GapArtifact, GapCategory, DecisionArtifact,
)
from .registry import CapabilityRegistry, Capability
from .executor import CapabilityExecutor, ExecutionResult
from .memory import BusinessMemory
from .planner import MissionPlanner, MissionGraph, MissionStep

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runtime status
# ---------------------------------------------------------------------------

class RuntimePhase:
    """Named lifecycle phases for the Business Runtime."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    RESOLVING = "resolving"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass
class RuntimeState:
    """Mutable state tracked across loops (NOT a global state dict).

    The Artifact Graph is the source of truth — this just tracks
    loop-level metadata.
    """
    phase: str = RuntimePhase.IDLE
    input_text: str = ""
    iteration: int = 0
    max_iterations: int = 3
    mission_active: bool = False
    mission: Optional[MissionGraph] = None
    step_index: int = 0
    errors: list[str] = field(default_factory=list)
    gaps_found: int = 0
    gaps_resolved: int = 0

    @property
    def can_continue(self) -> bool:
        return self.mission_active and self.iteration < self.max_iterations


@dataclass
class RuntimeResult:
    """Final output of a Business Runtime execution."""
    status: str = RuntimePhase.COMPLETED
    artifact_graph: Optional[ArtifactGraphStore] = None
    export: dict[str, Any] = field(default_factory=dict)
    mission: dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    elapsed_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    stage_modes: dict[str, str] = field(default_factory=dict)
    capability_executions: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Business Runtime
# ---------------------------------------------------------------------------

class BusinessRuntime:
    """Three-loop execution engine for the Business Agent OS.

    Usage:
        store = ArtifactGraphStore("./data/artifacts")
        registry = build_default_registry()
        planner = MissionPlanner(registry, mode="template")

        runtime = BusinessRuntime(store=store, registry=registry, planner=planner)
        result = await runtime.run(prd_text="...")
        print(result.export)
    """

    def __init__(
        self,
        store: ArtifactGraphStore,
        registry: CapabilityRegistry,
        planner: MissionPlanner,
        max_iterations: int = 3,
        executor: Optional[CapabilityExecutor] = None,
        executor_backend: str = "local",
        execution_context: Optional[dict[str, Any]] = None,
        event_sink: Optional[Callable[[dict[str, Any]], Awaitable[None] | None]] = None,
    ):
        self.store = store
        self.registry = registry
        self.planner = planner
        self.max_iterations = max_iterations
        if executor:
            self._executor = executor
        else:
            self._executor = CapabilityExecutor(store, backend=executor_backend)
        self._memory: Optional[BusinessMemory] = None
        self._agent_pool = None
        self._execution_context = dict(execution_context or {})
        self._event_sink = event_sink

    @property
    def agent_pool(self):
        if self._agent_pool is None:
            from app.core.agent_pool import AgentPool
            self._agent_pool = AgentPool(max_workers=4)
        return self._agent_pool

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        prd_text: str,
        domain_hint: str = "",
        project_id: str = "",
    ) -> RuntimeResult:
        """Execute the full Business Runtime loop.

        Args:
            prd_text: The business document / PRD.
            domain_hint: Optional domain classification.
            project_id: Project identifier for artifact scoping.

        Returns:
            RuntimeResult with final artifact graph export.
        """
        t0 = time.perf_counter()
        state = RuntimeState(input_text=prd_text, max_iterations=self.max_iterations)
        errors: list[str] = []
        self._stage_modes: dict[str, str] = {}
        self._capability_executions: list[dict[str, Any]] = []

        try:
            # ── Mission Loop ──
            state.phase = RuntimePhase.PLANNING
            state.mission = await self.planner.plan(
                prd_text, domain_hint=domain_hint,
            )
            state.mission_active = True
            logger.info(
                "Mission planned: %s (%d steps, mode=%s)",
                state.mission.title,
                len(state.mission.steps),
                state.mission.planning_mode,
            )

            while state.can_continue:
                state.iteration += 1
                logger.info("=== Iteration %d/%d ===", state.iteration, self.max_iterations)

                # ── Execution Loop ──
                state.phase = RuntimePhase.EXECUTING
                await self._execute_loop(state, project_id)

                # ── Reflection Loop ──
                state.phase = RuntimePhase.REFLECTING
                gaps = self._reflect(state)
                state.gaps_found = len(gaps)

                if not gaps:
                    logger.info("No gaps found — mission complete")
                    state.mission_active = False
                    break

                logger.info("Reflection found %d gaps", len(gaps))

                # ── Resolve gaps ──
                state.phase = RuntimePhase.RESOLVING
                resolved = self._resolve_gaps(gaps, state)
                state.gaps_resolved += resolved

                if not self._should_replan(gaps, state):
                    state.mission_active = False
                    break

        except Exception as exc:
            logger.exception("Runtime error in iteration %d", state.iteration)
            errors.append(str(exc))
            state.phase = RuntimePhase.ERROR

        # Finalize without masking runtime errors.
        if errors:
            state.phase = RuntimePhase.ERROR
        elif state.mission_active and state.iteration >= state.max_iterations:
            state.phase = RuntimePhase.MAX_ITERATIONS
        else:
            state.phase = RuntimePhase.COMPLETED
        elapsed = (time.perf_counter() - t0) * 1000

        return RuntimeResult(
            status=state.phase,
            artifact_graph=self.store,
            export=self.store.export(project_id=project_id) if project_id else self.store.export(),
            mission={
                "title": state.mission.title if state.mission else "",
                "steps": len(state.mission.steps) if state.mission else 0,
                "mode": state.mission.planning_mode if state.mission else "",
            },
            iterations=state.iteration,
            elapsed_ms=elapsed,
            errors=errors,
            gaps=[f"iteration={state.iteration}, found={state.gaps_found}, resolved={state.gaps_resolved}"],
            stage_modes=dict(self._stage_modes),
            capability_executions=list(self._capability_executions),
        )

    # ------------------------------------------------------------------
    # Execution Loop
    # ------------------------------------------------------------------

    async def _execute_loop(self, state: RuntimeState, project_id: str) -> None:
        """Execute all capability steps in dependency order.

        Steps within the same parallel_group are dispatched concurrently.
        """
        if not state.mission:
            return

        order = state.mission.get_execution_order()
        groups = state.mission.get_parallel_groups()

        for group_id in sorted(groups.keys()):
            steps = groups[group_id]
            if len(steps) == 1:
                await self._execute_step(steps[0], state, project_id)
            else:
                # Parallel execution
                tasks = [
                    self._execute_step(step, state, project_id)
                    for step in steps
                ]
                await asyncio.gather(*tasks)

    async def _execute_step(
        self, step: MissionStep, state: RuntimeState, project_id: str
    ) -> None:
        """Execute a single capability step and persist results to Artifact Graph."""
        cap = self.registry.get(step.capability_name)
        if cap is None:
            logger.warning("Capability not found: %s", step.capability_name)
            return

        logger.info("Executing: %s → %s", step.step_id, step.capability_name)
        terminal_event_emitted = False
        await self._emit_runtime_event({
            "kind": "capability",
            "status": "started",
            "capability_name": cap.name,
            "step_id": step.step_id,
            "iteration": state.iteration,
        })

        # Try direct callable first
        if cap.executor_fn:
            try:
                invocation = await self._executor.execute_callable(
                    cap,
                    lambda: self._invoke_executor_fn(
                        cap.executor_fn,
                        capability=cap,
                        input_text=state.input_text,
                        project_id=project_id,
                        store=self.store,
                        state=state,
                        step=step,
                        execution_context=self._execution_context,
                    ),
                    backend="compatibility",
                )
                self._record_capability_execution(invocation.execution)
                if invocation.execution.status != "success":
                    raise RuntimeError(invocation.execution.error or "capability execution failed")
                result = invocation.value
                if isinstance(result, BaseArtifact):
                    result.project_id = project_id or result.project_id
                    self.store.add(result)
                elif isinstance(result, list):
                    for item in result:
                        if isinstance(item, BaseArtifact):
                            item.project_id = project_id or item.project_id
                            self.store.add(item)
                elif isinstance(result, dict):
                    # Try to deserialize into correct artifact type
                    self._persist_dict_result(result, cap, project_id)
                self._stage_modes[cap.name] = "compatibility"
                await self._emit_runtime_event({
                    "kind": "capability",
                    "status": "completed",
                    "capability_name": cap.name,
                    "step_id": step.step_id,
                    "iteration": state.iteration,
                    "execution": invocation.execution.model_dump(mode="json"),
                })
                terminal_event_emitted = True
            except Exception as exc:
                logger.error("Executor failed for %s: %s", cap.name, exc)
                if not terminal_event_emitted:
                    await self._emit_runtime_event({
                        "kind": "capability",
                        "status": "failed",
                        "capability_name": cap.name,
                        "step_id": step.step_id,
                        "iteration": state.iteration,
                        "error": str(exc),
                    })
                raise RuntimeError(f"capability failed: {cap.name}") from exc
            return

        # Use CapabilityExecutor
        try:
            result = await self._executor.execute(
                cap,
                input_text=state.input_text,
                project_id=project_id,
            )
            self._record_capability_execution(result)
            if result.status == "success":
                self._stage_modes[cap.name] = result.mode or "real"
                logger.info("Executor: %s produced %d artifacts via %s",
                            cap.name, len(result.artifacts_produced), result.backend)
                await self._emit_runtime_event({
                    "kind": "capability",
                    "status": "completed",
                    "capability_name": cap.name,
                    "step_id": step.step_id,
                    "iteration": state.iteration,
                    "execution": result.model_dump(mode="json"),
                })
                terminal_event_emitted = True
            else:
                logger.warning("Executor failed for %s: %s", cap.name, result.error)
                await self._emit_runtime_event({
                    "kind": "capability",
                    "status": "failed",
                    "capability_name": cap.name,
                    "step_id": step.step_id,
                    "iteration": state.iteration,
                    "execution": result.model_dump(mode="json"),
                    "error": result.error,
                })
                terminal_event_emitted = True
                raise RuntimeError(f"capability failed: {cap.name}: {result.error}")
        except Exception as exc:
            logger.error("Executor error for %s: %s", cap.name, exc)
            if not terminal_event_emitted:
                await self._emit_runtime_event({
                    "kind": "capability",
                    "status": "failed",
                    "capability_name": cap.name,
                    "step_id": step.step_id,
                    "iteration": state.iteration,
                    "error": str(exc),
                })
            raise

    async def _emit_runtime_event(self, event: dict[str, Any]) -> None:
        """Send live lifecycle data without coupling runtime to SSE transport."""
        if self._event_sink is None:
            return
        result = self._event_sink(event)
        if inspect.isawaitable(result):
            await result

    def _record_capability_execution(self, result: ExecutionResult) -> None:
        self._capability_executions.append(result.model_dump(mode="json"))

    async def _invoke_executor_fn(self, executor_fn, **kwargs):
        """Call direct capability executors with only the kwargs they accept."""
        signature = inspect.signature(executor_fn)
        accepts_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        if accepts_var_kwargs:
            result = executor_fn(**kwargs)
        else:
            allowed = {
                name: value
                for name, value in kwargs.items()
                if name in signature.parameters
            }
            result = executor_fn(**allowed)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _execute_via_agent(
        self, cap: Capability, step: MissionStep, project_id: str
    ) -> None:
        """Execute a capability by invoking the underlying agent."""
        from app.agents.unified_agent import AgentContext, AgentFactory

        # Gather input from existing artifacts
        input_artifacts = []
        for at in cap.input_artifact_types:
            input_artifacts.extend(self.store.get_by_type(at))

        # Build context
        ctx = AgentContext(
            project_name=project_id or "default",
            business_system=self.store.export(project_id=project_id) if project_id else self.store.export(),
            params={"capability": cap.name, "step_id": step.step_id},
        )

        # Execute via AgentFactory
        try:
            agent = AgentFactory.create_agent(cap.executor_key)
            result = agent.run(ctx)

            if result.status == "completed" and result.data:
                self._persist_dict_result(result.data, cap, project_id)
        except Exception as exc:
            logger.error("Agent %s failed: %s", cap.executor_key, exc)

    def _persist_dict_result(
        self, data: dict, cap: Capability, project_id: str
    ) -> None:
        """Convert agent output dict into typed Artifacts and store them."""
        if not cap.output_artifact_types:
            return

        for at in cap.output_artifact_types:
            artifact = self._dict_to_artifact(at, data, project_id)
            if artifact:
                self.store.add(artifact)

    def _dict_to_artifact(
        self, at: ArtifactType, data: dict, project_id: str
    ) -> Optional[BaseArtifact]:
        """Try to construct a typed artifact from a flat dict."""
        from app.artifacts.types import ARTIFACT_CLASS_MAP
        cls = ARTIFACT_CLASS_MAP.get(at)
        if cls is None:
            return None

        try:
            # Map common dict keys to artifact fields
            field_map = {
                ArtifactType.BUSINESS_MODEL: {
                    "domain": data.get("business_domain", data.get("domain", "")),
                    "objectives": data.get("objectives", []),
                },
                ArtifactType.RISK: {
                    "risk_statement": data.get("risk", data.get("risk_statement", "")),
                    "severity": _parse_severity(data.get("severity", "medium")),
                    "probability": _parse_severity(data.get("probability", "medium")),
                    "mitigation": data.get("mitigation", ""),
                },
                ArtifactType.ASSUMPTION: {
                    "statement": data.get("assumption", data.get("statement", "")),
                },
                ArtifactType.GAP: {
                    "gap_statement": data.get("gap", data.get("gap_statement", "")),
                    "category": GapCategory(data.get("category", "evidence_missing")),
                },
                ArtifactType.DECISION: {
                    "decision_statement": data.get("decision", data.get("decision_statement", "")),
                    "rationale": data.get("rationale", ""),
                },
            }

            kwargs = {
                "artifact_type": at,
                "project_id": project_id,
                "label": data.get("label", data.get("title", at.value)),
                "description": data.get("description", ""),
            }
            kwargs.update(field_map.get(at, {}))

            return cls(**kwargs)
        except Exception as exc:
            logger.debug("Could not map dict to %s: %s", at.value, exc)
            return None

    # ------------------------------------------------------------------
    # Reflection Loop
    # ------------------------------------------------------------------

    def _reflect(self, state: RuntimeState) -> list[GapArtifact]:
        """Evaluate artifacts for gaps, inconsistencies, and missing evidence.

        Returns list of GapArtifacts found.
        """
        gaps: list[GapArtifact] = []

        # Check 1: Assumptions without evidence
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        for a in assumptions:
            if isinstance(a, AssumptionArtifact) and not a.validated:
                existing_gaps = self.store.get_by_type(ArtifactType.GAP)
                already_reported = any(
                    isinstance(g, GapArtifact)
                    and a.artifact_id in g.affected_artifact_ids
                    for g in existing_gaps
                )
                if not already_reported:
                    gap = GapArtifact(
                        gap_statement=f"Assumption '{a.statement}' lacks evidence",
                        category=GapCategory.EVIDENCE_MISSING,
                        severity=Severity.MEDIUM,
                        affected_artifact_ids=[a.artifact_id],
                        parent_ids=[a.artifact_id],
                    )
                    self.store.add(gap)
                    gaps.append(gap)

        # Check 2: Business model without risk analysis
        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)
        risks = self.store.get_by_type(ArtifactType.RISK)
        if biz_models and not risks:
            gap = GapArtifact(
                gap_statement="No risk analysis performed",
                category=GapCategory.ANALYSIS_INSUFFICIENT,
                severity=Severity.HIGH,
                affected_artifact_ids=[bm.artifact_id for bm in biz_models],
            )
            self.store.add(gap)
            gaps.append(gap)

        # Check 3: Decisions without coverage
        decisions = self.store.get_by_type(ArtifactType.DECISION)
        coverages = self.store.get_by_type(ArtifactType.COVERAGE)
        if decisions and not coverages:
            gap = GapArtifact(
                gap_statement="Decision made without coverage analysis",
                category=GapCategory.ANALYSIS_INSUFFICIENT,
                severity=Severity.MEDIUM,
            )
            self.store.add(gap)
            gaps.append(gap)

        return gaps

    # ------------------------------------------------------------------
    # Gap Resolution
    # ------------------------------------------------------------------

    def _resolve_gaps(self, gaps: list[GapArtifact], state: RuntimeState) -> int:
        """Attempt to resolve gaps. Returns number resolved."""
        resolved = 0
        for gap in gaps:
            if gap.resolved:
                resolved += 1
                continue

            if gap.category == GapCategory.EVIDENCE_MISSING:
                logger.info("Gap (evidence): %s — requesting evidence validation", gap.gap_statement)
                # In full implementation: invoke evidence_validation capability
                cap = self.registry.get("evidence_validation")
                if cap and cap.executor_key:
                    logger.info("Would invoke: %s", cap.executor_key)
                gap.resolution = "evidence_validation capability queued"

            elif gap.category == GapCategory.ANALYSIS_INSUFFICIENT:
                logger.info("Gap (analysis): %s — queuing additional capability", gap.gap_statement)
                gap.resolution = "additional analysis queued"

            elif gap.category == GapCategory.MODEL_FAILED:
                logger.warning("Gap (model): %s — generating alternative", gap.gap_statement)
                gap.resolution = "alternative model generation queued"

            gap.resolved = True
            self.store.update(gap)
            resolved += 1

        return resolved

    def _should_replan(self, gaps: list[GapArtifact], state: RuntimeState) -> bool:
        """Decide whether to trigger another iteration."""
        if state.iteration >= self.max_iterations:
            return False

        # Type C gaps (model_failed) always warrant replanning
        if any(g.category == GapCategory.MODEL_FAILED for g in gaps):
            return True

        # Type B gaps may benefit
        if any(g.category == GapCategory.ANALYSIS_INSUFFICIENT for g in gaps):
            return True

        # Type A (evidence) — don't replan, just queue validation
        return False
    def set_memory(self, memory: BusinessMemory) -> None:
        """Inject a BusinessMemory instance for cross-run learning."""
        self._memory = memory

    def enable_memory(self, data_dir: str = "./data/memory") -> BusinessMemory:
        """Create and enable a BusinessMemory with default data dir."""
        mem = BusinessMemory(data_dir)
        self._memory = mem
        return mem



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_severity(value: str) -> Severity:
    """Parse severity from common string representations."""
    mapping = {
        "critical": Severity.CRITICAL, "crit": Severity.CRITICAL,
        "high": Severity.HIGH, "h": Severity.HIGH,
        "medium": Severity.MEDIUM, "med": Severity.MEDIUM, "m": Severity.MEDIUM,
        "low": Severity.LOW, "l": Severity.LOW,
    }
    return mapping.get(value.lower().strip(), Severity.MEDIUM)
