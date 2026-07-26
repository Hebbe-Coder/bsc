"""Explainable, diagnosis-driven capability composition for Dynamic Business OS."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from app.artifacts import CapabilitySelectionArtifact, CapabilitySelectionItem
from app.capabilities import CapabilityRegistry, build_default_registry
from app.knowledge.method_routing import MethodRouter


_COMMERCE = ("ecommerce", "e-commerce", "retail", "commerce", "\u7535\u5546", "\u96f6\u552e", "conversion", "gmv", "\u8f6c\u5316")
_RESTAURANT = ("restaurant", "food service", "\u9910\u996e", "\u95e8\u5e97", "\u5ba2\u6d41")
_PRODUCT = ("saas", "product", "ai", "software", "\u4ea7\u54c1", "\u8f6f\u4ef6", "\u4eba\u5de5\u667a\u80fd")
_CONSULTING = ("consult", "client", "delivery", "\u54a8\u8be2", "\u5ba2\u6237\u4ea4\u4ed8")
_URGENCY = ("30 day", "30 days", "week", "launch", "618", "\u5927\u4fc3", "\u5929", "\u5468")


@dataclass(frozen=True)
class CapabilityRule:
    capability_name: str
    task_family: str
    base_score: float
    explanation: str
    scorer: Callable[[dict[str, float]], float]


def _has(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        # Short ASCII identifiers such as ``ai`` and ``gmv`` must be complete
        # words. A substring check turns words like ``constraints`` into an AI
        # product signal and silently routes a general mission to the wrong SOP.
        if term.isascii() and term.isalpha() and len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
        elif term in text:
            return True
    return False


def _profile(text: str) -> str:
    if _has(text, _RESTAURANT):
        return "restaurant"
    if _has(text, _COMMERCE):
        return "commerce"
    if _has(text, _PRODUCT):
        return "product"
    if _has(text, _CONSULTING):
        return "consulting"
    return "general"


def _cap(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 2)


class CapabilitySelector:
    """Compose capabilities from operational signals, never an SOP title lookup."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()

    def select(self, diagnosis, *, knowledge_context: dict | None = None) -> CapabilitySelectionArtifact:
        registered = {capability.name for capability in self.registry.list_all()}
        context = self._signals(diagnosis)
        knowledge_context = knowledge_context or {}
        selected: list[CapabilitySelectionItem] = []
        rejected: list[CapabilitySelectionItem] = []
        for rule in self._rules():
            components = self._components(rule, context, knowledge_context)
            score = _cap(sum(components.values()))
            reasons = self._reasons(rule, context, components, knowledge_context)
            item = CapabilitySelectionItem(
                capability_name=rule.capability_name,
                task_family=rule.task_family,
                score=score,
                reasons=reasons,
                score_components=components,
                executable=rule.capability_name in registered,
            )
            if rule.capability_name not in registered:
                item.reasons.insert(0, "Capability is not registered in the current runtime.")
                rejected.append(item)
            elif score >= 0.55:
                selected.append(item)
            else:
                item.reasons.append("Not selected because its diagnostic relevance did not reach the execution threshold.")
                rejected.append(item)

        return CapabilitySelectionArtifact(
            project_id=diagnosis.project_id,
            label=f"Capability selection: {diagnosis.label}"[:140],
            mission_id=diagnosis.mission_id,
            diagnosis_id=diagnosis.artifact_id,
            selected=selected,
            rejected=rejected,
            selection_reasoning=(
                "Capabilities were scored from the declared business profile, evidence coverage, "
                "stakeholders, decision rights, time horizon, constraints, approved methods, and "
                "governed knowledge signals matched to the task family."
            ),
            metadata={
                "diagnostic_profile": context["profile"],
                "signal_summary": {key: value for key, value in context.items() if isinstance(value, (bool, int, float))},
                "knowledge_context": {
                    "availability": str(knowledge_context.get("availability") or "unavailable"),
                    "method_ids": [str(value) for value in knowledge_context.get("method_ids") or [] if str(value)],
                    "output_ids": [str(value) for value in knowledge_context.get("output_ids") or [] if str(value)],
                    "page_ids": [str(value) for value in knowledge_context.get("page_ids") or [] if str(value)],
                    "source_ids": [str(value) for value in knowledge_context.get("source_ids") or [] if str(value)],
                    "signals": CapabilitySelector._knowledge_signal_view(knowledge_context),
                },
            },
            parent_ids=[diagnosis.artifact_id],
            source_agent="dbos_capability_selector",
        )

    @staticmethod
    def _signals(diagnosis) -> dict[str, float | bool | str]:
        text = " ".join([
            diagnosis.role,
            diagnosis.industry,
            diagnosis.organization_stage,
            diagnosis.goal,
            diagnosis.problem_statement,
            diagnosis.time_horizon,
            *diagnosis.constraints,
            *diagnosis.stakeholders,
            *diagnosis.decision_rights,
            *diagnosis.success_metrics,
            *diagnosis.diagnostic_dimensions,
            *diagnosis.operating_hypotheses,
        ]).lower()
        profile = _profile(text)
        missing = len(diagnosis.missing_fields)
        no_evidence = not diagnosis.evidence_refs
        return {
            "profile": profile,
            "commerce": profile == "commerce",
            "restaurant": profile == "restaurant",
            "product": profile == "product",
            "consulting": profile == "consulting",
            "constraints": bool(diagnosis.constraints),
            "stakeholders": bool(diagnosis.stakeholders),
            "decision_rights": bool(diagnosis.decision_rights),
            "evidence_gap": no_evidence,
            "incomplete_context": missing > 0,
            "urgency": _has(text, _URGENCY),
            "growth_goal": _has(text, ("growth", "conversion", "gmv", "revenue", "\u589e\u957f", "\u8f6c\u5316", "\u589e\u6536")),
            "ownership_goal": _has(text, ("ownership", "lead", "onboarding", "\u4e3b\u5bfc", "\u72ec\u7acb", "\u5165\u804c")),
            "missing_count": float(missing),
            "risk_count": float(len(diagnosis.risk_summary)),
        }

    @staticmethod
    def _rules() -> tuple[CapabilityRule, ...]:
        return (
            CapabilityRule("business_understanding", "context_mapping", 0.58, "Creates a shared operating frame before action.", lambda s: 0.08 if s["urgency"] or s["growth_goal"] else 0.0),
            CapabilityRule("assumption_reasoning", "assumption_validation", 0.26, "Turns critical unknowns into testable assumptions.", lambda s: 0.36 if s["incomplete_context"] or s["evidence_gap"] else 0.2),
            CapabilityRule("evidence_validation", "evidence_validation", 0.08, "Closes the evidence gap before the operating system scales.", lambda s: 0.58 if s["evidence_gap"] else 0.12),
            CapabilityRule("risk_analysis", "risk_control", 0.22, "Sets explicit stop conditions for material operating risk.", lambda s: 0.26 + (0.18 if s["constraints"] else 0.0) + (0.1 if s["urgency"] else 0.0)),
            CapabilityRule("decision_support", "decision_design", 0.18, "Makes authority, options, and acceptance criteria reviewable.", lambda s: (0.32 if s["stakeholders"] or s["decision_rights"] else 0.18) + (0.12 if s["product"] or s["consulting"] else 0.0)),
            CapabilityRule("optimization_recommendations", "conversion_experiment", 0.05, "Builds measurable experiments around a commercial bottleneck.", lambda s: (0.58 if s["commerce"] else 0.0) + (0.16 if s["growth_goal"] else 0.0)),
            CapabilityRule("strategy_analysis", "strategy_design", 0.05, "Frames strategic choices for product, store, or client delivery work.", lambda s: (0.56 if s["product"] or s["restaurant"] or s["consulting"] else 0.0) + (0.12 if s["ownership_goal"] else 0.0)),
            CapabilityRule("constraint_generation", "resource_guardrail", 0.05, "Converts declared limits into operating boundaries.", lambda s: 0.66 if s["constraints"] else 0.0),
            CapabilityRule("coverage_analysis", "coverage_review", 0.06, "Checks whether critical dimensions and evidence are covered.", lambda s: 0.52 if s["incomplete_context"] or s["evidence_gap"] else 0.08),
            CapabilityRule("gap_detection", "gap_resolution", 0.05, "Prioritizes missing evidence and unresolved analysis before expansion.", lambda s: 0.56 if s["incomplete_context"] or s["evidence_gap"] else 0.05),
            CapabilityRule("sop_design", "operating_cadence", 0.32, "Turns reviewed choices into an owner-led operating cadence.", lambda s: 0.2 + (0.08 if s["urgency"] else 0.0) + (0.05 if s["stakeholders"] else 0.0)),
            CapabilityRule("report_composition", "decision_brief", 0.05, "Produces a reviewable decision brief for a client or leadership audience.", lambda s: 0.64 if s["consulting"] else 0.0),
        )

    @staticmethod
    def _components(rule: CapabilityRule, signals: dict[str, float | bool | str], knowledge_context: dict) -> dict[str, float]:
        relevance = float(rule.scorer(signals))
        components = {"base": rule.base_score}
        if relevance:
            components["diagnostic_relevance"] = round(relevance, 2)
        method_matches = CapabilitySelector._matching_methods(knowledge_context, rule.task_family)
        if method_matches:
            components["approved_method"] = 0.1
        knowledge_evidence = CapabilitySelector._matching_knowledge_evidence(knowledge_context, rule.task_family)
        if any(knowledge_evidence.values()):
            components["knowledge_evidence"] = round(min(
                0.1,
                len(knowledge_evidence["source_ids"]) * 0.02
                + len(knowledge_evidence["page_ids"]) * 0.03
                + len(knowledge_evidence["output_ids"]) * 0.04,
            ), 2)
        return {key: value for key, value in components.items() if value > 0}

    @staticmethod
    def _reasons(rule: CapabilityRule, signals: dict[str, float | bool | str], components: dict[str, float], knowledge_context: dict) -> list[str]:
        reasons = [rule.explanation]
        profile = str(signals["profile"])
        if components.get("diagnostic_relevance"):
            reasons.append(f"Diagnostic profile '{profile}' materially raises relevance for this task family.")
        if signals["evidence_gap"] and rule.task_family in {"evidence_validation", "assumption_validation", "coverage_review", "gap_resolution"}:
            reasons.append("No source-backed baseline is currently declared, so evidence closure is required.")
        if signals["constraints"] and rule.task_family in {"resource_guardrail", "risk_control"}:
            reasons.append("Declared constraints require explicit guardrails and stop conditions.")
        if signals["stakeholders"] or signals["decision_rights"]:
            if rule.task_family in {"decision_design", "strategy_design", "operating_cadence"}:
                reasons.append("Declared stakeholders or decision rights change the ownership and review path.")
        for method in CapabilitySelector._matching_methods(knowledge_context, rule.task_family)[:3]:
            reasons.append(f"Supported by approved method: {str(method.get('name') or method.get('id') or 'method')}.")
        evidence = CapabilitySelector._matching_knowledge_evidence(knowledge_context, rule.task_family)
        if any(evidence.values()):
            parts = [
                f"{len(evidence['source_ids'])} source" if evidence["source_ids"] else "",
                f"{len(evidence['page_ids'])} Wiki page" if evidence["page_ids"] else "",
                f"{len(evidence['output_ids'])} verified output" if evidence["output_ids"] else "",
            ]
            reasons.append(
                "Governed knowledge evidence is available for this task family: "
                + ", ".join(part for part in parts if part)
                + "."
            )
        return reasons

    @staticmethod
    def _matching_methods(knowledge_context: dict, task_family: str) -> list[dict]:
        methods = [item for item in knowledge_context.get("methods") or [] if isinstance(item, dict)]
        decision = MethodRouter().select(methods, task_family.replace("_", " "))
        by_slug = {str(item.get("slug") or ""): item for item in methods}
        return [by_slug[match.slug] for match in decision.matches if match.slug in by_slug]

    @staticmethod
    def _matching_knowledge_evidence(knowledge_context: dict, task_family: str) -> dict[str, list[str]]:
        signals = knowledge_context.get("signals") if isinstance(knowledge_context.get("signals"), dict) else {}
        by_family = signals.get("by_task_family") if isinstance(signals.get("by_task_family"), dict) else {}
        value = by_family.get(task_family) if isinstance(by_family.get(task_family), dict) else {}
        return {
            field: [str(item) for item in value.get(field) or [] if str(item)]
            for field in ("source_ids", "page_ids", "output_ids", "method_ids")
        }

    @staticmethod
    def _knowledge_signal_view(knowledge_context: dict) -> dict:
        signals = knowledge_context.get("signals") if isinstance(knowledge_context.get("signals"), dict) else {}
        by_family = signals.get("by_task_family") if isinstance(signals.get("by_task_family"), dict) else {}
        return {
            "revision": str(signals.get("revision") or "dbos-knowledge-signals-v1"),
            "by_task_family": {
                str(family): {
                    field: [str(item) for item in value.get(field) or [] if str(item)][:100]
                    for field in ("source_ids", "page_ids", "output_ids", "method_ids")
                }
                for family, value in by_family.items()
                if str(family) and isinstance(value, dict)
            },
            "eligible_source_count": int(signals.get("eligible_source_count") or 0),
            "published_page_count": int(signals.get("published_page_count") or 0),
            "verified_output_count": int(signals.get("verified_output_count") or 0),
        }
