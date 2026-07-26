"""Deterministic regression evidence for Dynamic SOP capability routing."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
from typing import Any, Iterable

from app.artifacts import (
    CapabilitySelectionArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    MissionArtifact,
    SOPRoutingCaseResult,
    SOPRoutingEvaluationArtifact,
)

from .capabilities import CapabilitySelector
from .compiler import DynamicSOPCompiler
from .diagnosis import DiagnosisService


SOP_ROUTING_EVALUATOR_REVISION = "dbos-sop-routing-evaluator-v1"


@dataclass(frozen=True)
class SOPRoutingCase:
    """A non-production fixture used to guard routing behavior across releases."""

    case_id: str
    split: str
    title: str
    intent: str
    context: dict[str, Any]
    expected_profile: str
    must_select: tuple[str, ...] = ()
    must_exclude: tuple[str, ...] = ()
    must_include_task_families: tuple[str, ...] = ()
    expected_workstream: str = ""


_CASES: tuple[SOPRoutingCase, ...] = (
    SOPRoutingCase(
        case_id="commerce-conversion-positive",
        split="positive",
        title="Conversion recovery",
        intent="Recover ecommerce conversion before a constrained campaign closes.",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
            "time_horizon": "30 days",
            "constraints": ["limited budget"],
            "stakeholders": ["merchandising lead"],
            "decision_rights": ["operations director approves spend changes"],
            "evidence": [{"source": "trading dashboard", "finding": "cart conversion fell 12%", "strength": "high"}],
        },
        expected_profile="commerce",
        must_select=("optimization_recommendations",),
        must_exclude=("strategy_analysis", "report_composition"),
        must_include_task_families=("conversion_experiment",),
        expected_workstream="traffic -> product view -> cart -> payment -> repeat order",
    ),
    SOPRoutingCase(
        case_id="product-ownership-positive",
        split="positive",
        title="Product ownership",
        intent="Lead an AI product decision from user evidence through staged delivery.",
        context={
            "role": "AI product manager",
            "industry": "AI SaaS",
            "organization_stage": "new hire",
            "goal": "independently lead a product decision",
            "time_horizon": "90 days",
            "stakeholders": ["product director", "engineering lead"],
            "decision_rights": ["product director approves scope changes"],
            "evidence": [{"source": "customer interviews", "finding": "activation value is unclear", "strength": "medium"}],
        },
        expected_profile="product",
        must_select=("strategy_analysis",),
        must_exclude=("optimization_recommendations", "report_composition"),
        must_include_task_families=("strategy_design",),
        expected_workstream="user problem -> product decision -> delivery milestone -> adoption signal",
    ),
    SOPRoutingCase(
        case_id="consulting-delivery-positive",
        split="positive",
        title="Client decision brief",
        intent="Prepare an evidence-backed client delivery recommendation.",
        context={
            "role": "consultant",
            "industry": "professional services consulting",
            "organization_stage": "delivery",
            "goal": "client-ready recommendation",
            "stakeholders": ["client sponsor"],
            "decision_rights": ["client sponsor accepts the recommendation"],
            "evidence": [{"source": "client interviews", "finding": "three options remain", "strength": "high"}],
        },
        expected_profile="consulting",
        must_select=("report_composition",),
        must_exclude=("optimization_recommendations",),
        must_include_task_families=("decision_brief",),
        expected_workstream="client question -> evidence -> alternatives -> accepted recommendation",
    ),
    SOPRoutingCase(
        case_id="general-operations-near-negative",
        split="near_negative",
        title="Internal operating review",
        intent="Improve the internal work handoff rhythm without a commercial program.",
        context={
            "role": "operations lead",
            "industry": "internal operations",
            "organization_stage": "established",
            "goal": "reduce handoff delays",
            "stakeholders": ["team lead"],
            "decision_rights": ["team lead accepts the operating change"],
            "evidence": [{"source": "retrospective", "finding": "handoffs wait for ownership", "strength": "medium"}],
        },
        expected_profile="general",
        must_exclude=("optimization_recommendations", "strategy_analysis", "report_composition"),
        expected_workstream="current state -> bottleneck -> decision -> operating rhythm",
    ),
    SOPRoutingCase(
        case_id="product-not-commerce-near-negative",
        split="near_negative",
        title="Product adoption decision",
        intent="Prioritize a product adoption decision rather than a sales acquisition campaign.",
        context={
            "role": "product manager",
            "industry": "software product",
            "organization_stage": "growth",
            "goal": "improve product adoption",
            "stakeholders": ["product lead"],
            "decision_rights": ["product lead accepts the experiment scope"],
            "evidence": [{"source": "product analytics", "finding": "activation is inconsistent", "strength": "high"}],
        },
        expected_profile="product",
        must_select=("strategy_analysis",),
        must_exclude=("optimization_recommendations",),
        must_include_task_families=("strategy_design",),
        expected_workstream="user problem -> product decision -> delivery milestone -> adoption signal",
    ),
    SOPRoutingCase(
        case_id="restaurant-holdout",
        split="holdout",
        title="Store experiment",
        intent="Improve a restaurant store's repeat visits before any chain-wide rollout.",
        context={
            "role": "restaurant operations lead",
            "industry": "restaurant",
            "organization_stage": "multi-store growth",
            "goal": "improve repeat visits",
            "stakeholders": ["store manager"],
            "decision_rights": ["regional manager approves rollout"],
            "evidence": [{"source": "store dashboard", "finding": "repeat visits declined", "strength": "high"}],
        },
        expected_profile="restaurant",
        must_select=("strategy_analysis",),
        must_exclude=("optimization_recommendations",),
        must_include_task_families=("strategy_design",),
        expected_workstream="store traffic -> order conversion -> average ticket -> repeat visit",
    ),
    SOPRoutingCase(
        case_id="commerce-evidence-gap-holdout",
        split="holdout",
        title="Unmeasured conversion request",
        intent="Improve ecommerce conversion without a declared source-backed baseline.",
        context={
            "role": "ecommerce operations lead",
            "industry": "ecommerce",
            "organization_stage": "growth",
            "goal": "restore conversion",
            "constraints": ["limited campaign budget"],
        },
        expected_profile="commerce",
        must_select=("optimization_recommendations", "evidence_validation"),
        must_exclude=("strategy_analysis",),
        must_include_task_families=("conversion_experiment", "evidence_validation"),
        expected_workstream="traffic -> product view -> cart -> payment -> repeat order",
    ),
)


class SOPRoutingEvaluator:
    """Replay a versioned capability-routing suite without a model or external I/O."""

    def __init__(
        self,
        *,
        diagnosis_service: DiagnosisService | None = None,
        selector: CapabilitySelector | None = None,
        compiler: DynamicSOPCompiler | None = None,
        cases: Iterable[SOPRoutingCase] | None = None,
    ) -> None:
        self.diagnosis_service = diagnosis_service or DiagnosisService()
        self.selector = selector or CapabilitySelector()
        self.compiler = compiler or DynamicSOPCompiler()
        self.cases = tuple(cases or _CASES)

    def evaluate(
        self,
        *,
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact,
        selection: CapabilitySelectionArtifact,
        sop: DynamicSOPArtifact,
    ) -> SOPRoutingEvaluationArtifact:
        results = [self._evaluate_case(case) for case in self.cases]
        findings = [
            f"{result.case_id}: {finding}"
            for result in results
            for finding in result.findings
        ]
        counts = {split: sum(case.split == split for case in self.cases) for split in ("positive", "near_negative", "holdout")}
        protocol_findings = self._protocol_findings(counts)
        findings.extend(protocol_findings)
        holdouts = [result for result in results if result.split == "holdout"]
        holdout_passed = bool(holdouts) and all(result.passed for result in holdouts)
        passed = not findings and all(result.passed for result in results) and holdout_passed
        return SOPRoutingEvaluationArtifact(
            project_id=mission.project_id,
            label=f"Dynamic SOP routing evaluation: {mission.title}"[:140],
            mission_id=mission.artifact_id,
            diagnosis_id=diagnosis.artifact_id,
            selection_id=selection.artifact_id,
            dynamic_sop_id=sop.artifact_id,
            evaluator_revision=SOP_ROUTING_EVALUATOR_REVISION,
            selector_fingerprint=self._fingerprint(),
            evaluation_status="passed" if passed else "failed",
            positive_case_count=counts["positive"],
            near_negative_case_count=counts["near_negative"],
            holdout_case_count=counts["holdout"],
            holdout_passed=holdout_passed,
            case_results=results,
            findings=findings,
            metadata={
                "protocol": {
                    "revision": SOP_ROUTING_EVALUATOR_REVISION,
                    "positive_minimum": 3,
                    "near_negative_minimum": 2,
                    "holdout_minimum": 2,
                    "runner": "deterministic_no_model_no_external_io",
                },
                "actual_route": {
                    "selected_capabilities": selection.selected_names,
                    "selected_task_families": [item.task_family for item in selection.selected],
                    "diagnostic_profile": str(selection.metadata.get("diagnostic_profile") or ""),
                },
            },
            parent_ids=[mission.artifact_id, diagnosis.artifact_id, selection.artifact_id, sop.artifact_id],
            source_agent="dbos_sop_routing_evaluator",
            tags=["dbos", "routing_evaluation", "deterministic"],
        )

    def _evaluate_case(self, case: SOPRoutingCase) -> SOPRoutingCaseResult:
        mission = MissionArtifact(
            project_id="__dbos_routing_evaluation__",
            label=case.title,
            title=case.title,
            intent=case.intent,
            context=case.context,
        )
        mission.mission_id = f"routing-evaluation-{case.case_id}"
        diagnosis, *_ = self.diagnosis_service.diagnose(mission)
        selection = self.selector.select(diagnosis, knowledge_context={})
        sop = self.compiler.compile(diagnosis, selection)
        selected = set(selection.selected_names)
        task_families = {item.task_family for item in selection.selected}
        observed_profile = str(selection.metadata.get("diagnostic_profile") or "")
        findings: list[str] = []
        if observed_profile != case.expected_profile:
            findings.append(f"expected profile {case.expected_profile}, observed {observed_profile or 'missing'}")
        missing = sorted(set(case.must_select) - selected)
        if missing:
            findings.append("missing required capabilities: " + ", ".join(missing))
        unexpected = sorted(set(case.must_exclude) & selected)
        if unexpected:
            findings.append("selected excluded capabilities: " + ", ".join(unexpected))
        missing_families = sorted(set(case.must_include_task_families) - task_families)
        if missing_families:
            findings.append("missing required task families: " + ", ".join(missing_families))
        compiled_text = json.dumps(sop.model_dump(mode="json"), ensure_ascii=False)
        if case.expected_workstream and case.expected_workstream not in compiled_text:
            findings.append("compiled SOP does not preserve the expected operating workstream")
        return SOPRoutingCaseResult(
            case_id=case.case_id,
            split=case.split,
            passed=not findings,
            observed_profile=observed_profile,
            selected_capabilities=sorted(selected),
            selected_task_families=sorted(task_families),
            findings=findings,
        )

    def _protocol_findings(self, counts: dict[str, int]) -> list[str]:
        findings: list[str] = []
        if counts["positive"] < 3:
            findings.append("routing protocol requires at least three positive cases")
        if counts["near_negative"] < 2:
            findings.append("routing protocol requires at least two near-negative cases")
        if counts["holdout"] < 2:
            findings.append("routing protocol requires at least two isolated holdout cases")
        prompts: dict[str, str] = {}
        for case in self.cases:
            prompt = " ".join(case.intent.lower().split())
            existing_split = prompts.get(prompt)
            if existing_split and existing_split != case.split:
                findings.append("routing protocol reuses an intent across evaluation splits")
            prompts[prompt] = case.split
        return findings

    def _fingerprint(self) -> str:
        """Make routing-code changes visible in every persisted evaluation."""
        components: list[str] = []
        for target in (
            CapabilitySelector._rules,
            CapabilitySelector._signals,
            DynamicSOPCompiler.compile,
            DynamicSOPCompiler._profile,
            DynamicSOPCompiler._task_details,
        ):
            try:
                components.append(inspect.getsource(target))
            except OSError:
                components.append(getattr(target, "__qualname__", repr(target)))
        components.append(json.dumps([case.case_id for case in self.cases], separators=(",", ":")))
        return sha256("\n".join(components).encode("utf-8")).hexdigest()


__all__ = [
    "SOP_ROUTING_EVALUATOR_REVISION",
    "SOPRoutingCase",
    "SOPRoutingEvaluator",
]
