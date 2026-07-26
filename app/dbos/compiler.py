"""Composable compiler for diagnosis-specific Dynamic SOPs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import re

from app.artifacts import (
    CapabilitySelectionArtifact,
    DiagnosisArtifact,
    DynamicSOPArtifact,
    DynamicSOPPhase,
    DynamicSOPTask,
)


@dataclass(frozen=True)
class OperatingProfile:
    name: str
    baseline: str
    intervention: str
    workstreams: tuple[str, ...]
    stopping_risk: str


_PROFILES = {
    "commerce": OperatingProfile(
        "commerce", "traffic -> product view -> cart -> payment -> repeat order", "a bounded conversion or retention experiment",
        ("demand", "funnel", "merchandising", "promotion economics", "fulfillment"), "do not scale spend until the baseline and incremental outcome are measurable",
    ),
    "restaurant": OperatingProfile(
        "restaurant", "store traffic -> order conversion -> average ticket -> repeat visit", "a store-level growth experiment",
        ("traffic", "menu", "labor", "local marketing", "store economics"), "do not roll out chain-wide before one store has a reviewed result",
    ),
    "product": OperatingProfile(
        "product", "user problem -> product decision -> delivery milestone -> adoption signal", "a staged product ownership plan",
        ("user evidence", "stakeholder alignment", "product scope", "delivery", "adoption"), "do not commit delivery before decision rights and user evidence are explicit",
    ),
    "consulting": OperatingProfile(
        "consulting", "client question -> evidence -> alternatives -> accepted recommendation", "an evidence-backed client decision brief",
        ("client objective", "evidence", "alternatives", "recommendation", "delivery review"), "do not present a recommendation as fact when the evidence gap remains open",
    ),
    "general": OperatingProfile(
        "general", "current state -> bottleneck -> decision -> operating rhythm", "a bounded operating improvement",
        ("baseline", "ownership", "constraints", "execution", "review"), "do not expand the workstream without a reviewed outcome",
    ),
}


def _has(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if term.isascii() and term.isalpha() and len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
        elif term in text:
            return True
    return False


def _phase_for(task_family: str) -> tuple[str, str, str]:
    if task_family in {"context_mapping", "assumption_validation", "evidence_validation", "coverage_review", "gap_resolution"}:
        return ("diagnose", "Diagnose the real bottleneck", "Turn declared context and evidence into a shared, testable problem frame.")
    if task_family in {"risk_control", "resource_guardrail", "decision_design"}:
        return ("govern", "Set decision and safety gates", "Make authority, constraints, stop conditions, and escalation explicit before action.")
    return ("operate", "Run and learn", "Execute a bounded workstream, measure the result, and retain an auditable learning loop.")


class DynamicSOPCompiler:
    """Compile a work system from diagnostic signals rather than a named SOP."""

    def compile(self, diagnosis: DiagnosisArtifact, selection: CapabilitySelectionArtifact) -> DynamicSOPArtifact:
        profile = self._profile(diagnosis)
        objective = diagnosis.goal or "validate the requested outcome"
        owner = diagnosis.role or "mission owner"
        decision_owner = diagnosis.decision_rights[0] if diagnosis.decision_rights else owner
        primary_risk = diagnosis.risk_summary[0] if diagnosis.risk_summary else profile.stopping_risk
        metrics = diagnosis.success_metrics or [f"reviewed baseline for {objective}"]
        grouped: dict[str, list[DynamicSOPTask]] = defaultdict(list)
        phase_details: dict[str, tuple[str, str]] = {}

        for index, item in enumerate(selection.selected, start=1):
            phase_id, phase_title, phase_objective = _phase_for(item.task_family)
            phase_details[phase_id] = (phase_title, phase_objective)
            details = self._task_details(
                profile=profile,
                diagnosis=diagnosis,
                task_family=item.task_family,
                objective=objective,
                owner=owner,
                decision_owner=decision_owner,
                metric=metrics[(index - 1) % len(metrics)],
                risk=primary_risk,
                knowledge_refs=self._knowledge_refs(selection, item.task_family),
            )
            stable_key = f"{diagnosis.mission_id}:{item.capability_name}:{item.task_family}:{profile.name}:{objective}"
            grouped[phase_id].append(DynamicSOPTask(
                task_id=f"task-{sha256(stable_key.encode('utf-8')).hexdigest()[:12]}",
                task_family=item.task_family,
                capability_name=item.capability_name,
                parent_refs=list(dict.fromkeys([
                    diagnosis.artifact_id,
                    selection.artifact_id,
                    *diagnosis.evidence_refs,
                    *self._knowledge_refs(selection, item.task_family),
                ])),
                **details,
            ))

        phases: list[DynamicSOPPhase] = []
        for phase_id in ("diagnose", "govern", "operate"):
            tasks = grouped.get(phase_id, [])
            if tasks:
                title, phase_objective = phase_details[phase_id]
                phases.append(DynamicSOPPhase(phase_id=phase_id, title=title, objective=phase_objective, tasks=tasks))

        stakeholder_text = ", ".join(diagnosis.stakeholders) if diagnosis.stakeholders else "stakeholders to be confirmed"
        return DynamicSOPArtifact(
            project_id=diagnosis.project_id,
            label=f"Dynamic SOP: {objective}"[:140],
            mission_id=diagnosis.mission_id,
            diagnosis_id=diagnosis.artifact_id,
            selection_id=selection.artifact_id,
            title=f"{objective}: {profile.name} execution system"[:180],
            objective=objective,
            diagnostic_summary=(
                f"{owner} is addressing {objective} in a {diagnosis.organization_stage or 'declared'} "
                f"{diagnosis.industry or profile.name} setting. Primary workstreams: {', '.join(profile.workstreams)}. "
                f"Review participants: {stakeholder_text}."
            ),
            quality_gates=self._quality_gates(diagnosis, metrics, decision_owner, profile, selection),
            phases=phases,
            compilation_reasoning=(
                "The compiler combined the persisted diagnostic profile, success metrics, evidence references, "
                "constraints, stakeholders, decision rights, selected capability task families, and matching "
                "governed knowledge signals without reading knowledge bodies."
            ),
            metadata={"knowledge_reuse": self._knowledge_reuse(selection)},
            parent_ids=[diagnosis.artifact_id, selection.artifact_id],
            source_agent="dbos_dynamic_sop_compiler",
        )

    @staticmethod
    def _profile(diagnosis: DiagnosisArtifact) -> OperatingProfile:
        text = " ".join([diagnosis.industry, diagnosis.problem_statement, *diagnosis.diagnostic_dimensions]).lower()
        if _has(text, ("restaurant", "food service", "\u9910\u996e", "\u95e8\u5e97")):
            return _PROFILES["restaurant"]
        if _has(text, ("ecommerce", "e-commerce", "retail", "\u7535\u5546", "\u96f6\u552e", "conversion", "gmv", "\u8f6c\u5316")):
            return _PROFILES["commerce"]
        if _has(text, ("saas", "product", "ai", "software", "\u4ea7\u54c1", "\u8f6f\u4ef6", "\u4eba\u5de5\u667a\u80fd")):
            return _PROFILES["product"]
        if _has(text, ("consult", "client", "delivery", "\u54a8\u8be2", "\u5ba2\u6237\u4ea4\u4ed8")):
            return _PROFILES["consulting"]
        return _PROFILES["general"]

    @staticmethod
    def _task_details(
        *,
        profile: OperatingProfile,
        diagnosis: DiagnosisArtifact,
        task_family: str,
        objective: str,
        owner: str,
        decision_owner: str,
        metric: str,
        risk: str,
        knowledge_refs: list[str],
    ) -> dict[str, str]:
        evidence_needed = "source-backed baseline" if not diagnosis.evidence_refs else "declared evidence and its measurement window"
        first_hypothesis = diagnosis.operating_hypotheses[0] if diagnosis.operating_hypotheses else f"the bottleneck for {objective}"
        first_constraint = diagnosis.constraints[0] if diagnosis.constraints else "the declared operating boundary"
        details = {
            "context_mapping": (
                f"Map {profile.baseline} for {objective}",
                f"{profile.name} baseline map across {', '.join(profile.workstreams[:3])}",
                f"{metric} is quantified with an owner and measurement window",
            ),
            "assumption_validation": (
                f"Test the critical assumption behind {objective}",
                "assumption register with counterfactuals and validation owners",
                f"'{first_hypothesis}' is confirmed, rejected, or escalated",
            ),
            "evidence_validation": (
                f"Close the evidence gap for {objective}",
                "evidence ledger with source, finding, freshness, and limitation",
                f"A {evidence_needed} is available for the next decision",
            ),
            "coverage_review": (
                f"Review diagnostic coverage before acting on {objective}",
                "coverage matrix for business dimensions, evidence, owners, and constraints",
                "Every critical dimension is covered or has an explicit gap owner",
            ),
            "gap_resolution": (
                f"Sequence the unresolved gaps for {objective}",
                "gap resolution queue with priority, owner, and decision impact",
                "High-impact unknowns are closed or accepted by the decision owner",
            ),
            "risk_control": (
                f"Define stop conditions for {profile.name} execution",
                "risk and control register with triggers, mitigation, and contingency",
                f"The team can stop before this risk materializes: {risk}",
            ),
            "decision_design": (
                f"Align {decision_owner} on the decision path for {objective}",
                "decision brief with options, evidence threshold, authority, and escalation path",
                "The decision owner accepts the next action and the condition for reversal",
            ),
            "resource_guardrail": (
                f"Protect the constraint while pursuing {objective}",
                "resource guardrail with non-negotiables, budget/time boundary, and exception path",
                f"The work remains inside '{first_constraint}' or is explicitly re-approved",
            ),
            "conversion_experiment": (
                f"Run a bounded {profile.name} experiment for {objective}",
                f"experiment portfolio across {', '.join(profile.workstreams[:3])}",
                f"{metric} moves against a documented baseline without violating a guardrail",
            ),
            "strategy_design": (
                f"Choose the {profile.name} operating path for {objective}",
                f"strategy option set for {', '.join(profile.workstreams[:3])}",
                "A named owner accepts a path, alternative, and stop condition",
            ),
            "operating_cadence": (
                f"Run the review cadence for {objective}",
                "owner-led cadence with daily signals, weekly decisions, and retrospective",
                f"{metric} and open risks are reviewed at the declared cadence",
            ),
            "decision_brief": (
                f"Deliver an evidence-backed decision brief for {objective}",
                "client-ready recommendation, alternatives, evidence limits, and implementation handoff",
                "The intended audience can accept, reject, or request a bounded revision",
            ),
        }
        title, deliverable, completion = details.get(
            task_family,
            (f"Advance {task_family.replace('_', ' ')} for {objective}", "reviewable work product", "Review criteria are met"),
        )
        check = f"Verify the completion condition against {evidence_needed} and the declared constraint."
        if knowledge_refs:
            check += " Review the linked governed knowledge signals for applicability; they are not a substitute for the current baseline."
        return {
            "title": title,
            "owner": owner,
            "deliverable": deliverable,
            "metric": completion,
            "trigger": diagnosis.time_horizon or "after the Mission confirmation gate is passed",
            "decision_point": f"{decision_owner} confirms evidence threshold, option, and next action before execution.",
            "risk": risk,
            "check": check,
            "retrospect": "Record the observed outcome, rejected assumption, correction, and reusable insight with source references.",
        }

    @staticmethod
    def _quality_gates(
        diagnosis: DiagnosisArtifact,
        metrics: list[str],
        decision_owner: str,
        profile: OperatingProfile,
        selection: CapabilitySelectionArtifact,
    ) -> list[str]:
        gates = [
            f"A source-backed baseline exists for: {metrics[0]}.",
            f"{decision_owner} accepts the decision criteria and reversal condition.",
            f"The active workstream respects: {diagnosis.constraints[0] if diagnosis.constraints else profile.stopping_risk}.",
            "No task is marked complete without a persisted execution result or manual review record.",
        ]
        if diagnosis.stakeholders:
            gates.insert(1, f"Review participants are named: {', '.join(diagnosis.stakeholders)}.")
        knowledge_reuse = DynamicSOPCompiler._knowledge_reuse(selection)
        if knowledge_reuse["reference_count"]:
            gates.insert(
                1,
                f"Matching governed knowledge signals ({knowledge_reuse['reference_count']} references across "
                f"{knowledge_reuse['task_family_count']} task families) are checked for applicability before reuse.",
            )
        return gates

    @staticmethod
    def _knowledge_refs(selection: CapabilitySelectionArtifact, task_family: str) -> list[str]:
        metadata = selection.metadata if isinstance(selection.metadata, dict) else {}
        context = metadata.get("knowledge_context") if isinstance(metadata.get("knowledge_context"), dict) else {}
        signals = context.get("signals") if isinstance(context.get("signals"), dict) else {}
        by_family = signals.get("by_task_family") if isinstance(signals.get("by_task_family"), dict) else {}
        match = by_family.get(task_family) if isinstance(by_family.get(task_family), dict) else {}
        return list(dict.fromkeys(
            str(item)
            for field in ("source_ids", "page_ids", "output_ids", "method_ids")
            for item in match.get(field, [])
            if str(item)
        ))

    @staticmethod
    def _knowledge_reuse(selection: CapabilitySelectionArtifact) -> dict[str, int | list[str] | str]:
        metadata = selection.metadata if isinstance(selection.metadata, dict) else {}
        context = metadata.get("knowledge_context") if isinstance(metadata.get("knowledge_context"), dict) else {}
        signals = context.get("signals") if isinstance(context.get("signals"), dict) else {}
        by_family = signals.get("by_task_family") if isinstance(signals.get("by_task_family"), dict) else {}
        task_families = [str(value) for value in by_family if str(value)]
        reference_count = sum(
            len(value.get(field) or [])
            for value in by_family.values()
            if isinstance(value, dict)
            for field in ("source_ids", "page_ids", "output_ids", "method_ids")
        )
        return {
            "revision": str(signals.get("revision") or "dbos-knowledge-signals-v1"),
            "task_families": sorted(task_families),
            "task_family_count": len(task_families),
            "reference_count": reference_count,
        }
