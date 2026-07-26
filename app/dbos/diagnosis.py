"""Evidence-aware, deterministic diagnosis for Dynamic Business OS missions."""

from __future__ import annotations

from typing import Any

from app.artifacts import (
    AssumptionArtifact,
    DiagnosisArtifact,
    EvidenceArtifact,
    GapArtifact,
    GapCategory,
    RiskArtifact,
    RiskDimension,
    Severity,
)


_REQUIRED_CONTEXT = ("role", "industry", "organization_stage", "goal")
_COMMERCE_TERMS = ("ecommerce", "e-commerce", "retail", "commerce", "\u7535\u5546", "\u96f6\u552e", "\u8f6c\u5316", "gmv")
_RESTAURANT_TERMS = ("restaurant", "food service", "\u9910\u996e", "\u95e8\u5e97", "\u5ba2\u6d41")
_PRODUCT_TERMS = ("saas", "product", "ai", "software", "\u4ea7\u54c1", "\u8f6f\u4ef6", "\u4eba\u5de5\u667a\u80fd")
_CONSULTING_TERMS = ("consult", "client", "delivery", "\u54a8\u8be2", "\u5ba2\u6237\u4ea4\u4ed8")


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _severity(value: Any) -> Severity:
    normalized = str(value or "").strip().lower()
    return {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "low": Severity.LOW,
    }.get(normalized, Severity.MEDIUM)


class DiagnosisService:
    """Normalize declared facts without upgrading unknowns into evidence."""

    def diagnose(
        self,
        mission,
    ) -> tuple[
        DiagnosisArtifact,
        list[AssumptionArtifact],
        list[GapArtifact],
        list[RiskArtifact],
        list[EvidenceArtifact],
    ]:
        context = mission.context if isinstance(mission.context, dict) else {}
        values = {key: str(context.get(key) or "").strip() for key in _REQUIRED_CONTEXT}
        constraints = _list(context.get("constraints"))
        stakeholders = _list(context.get("stakeholders"))
        decision_rights = _list(context.get("decision_rights"))
        success_metrics = _list(context.get("success_metrics"))
        horizon = str(context.get("time_horizon") or "").strip()
        profile = self._profile(values, mission.intent)
        missing = [key for key, value in values.items() if not value]
        evidence = self._evidence(mission.project_id, context.get("evidence"))
        dimensions = self._dimensions(profile, stakeholders, decision_rights, evidence)
        hypotheses = self._hypotheses(profile, values, constraints, mission.intent)
        metrics = success_metrics or self._default_metrics(profile, values["goal"])
        coverage_points = (
            sum(bool(values[key]) for key in _REQUIRED_CONTEXT)
            + bool(horizon)
            + bool(constraints)
            + bool(stakeholders)
            + bool(decision_rights)
            + bool(evidence)
        )
        diagnosis = DiagnosisArtifact(
            project_id=mission.project_id,
            label=f"Diagnosis: {mission.title}"[:120],
            mission_id=mission.artifact_id,
            role=values["role"],
            industry=values["industry"],
            organization_stage=values["organization_stage"],
            goal=values["goal"],
            time_horizon=horizon,
            constraints=constraints,
            stakeholders=stakeholders,
            decision_rights=decision_rights,
            problem_statement=mission.intent,
            risk_summary=self._risk_summary(profile, values, constraints, mission.intent),
            success_metrics=metrics,
            operating_hypotheses=hypotheses,
            diagnostic_dimensions=dimensions,
            coverage=round(coverage_points / 9, 2),
            missing_fields=missing,
            evidence_refs=[item.artifact_id for item in evidence],
            parent_ids=[mission.artifact_id],
            source_agent="dbos_diagnosis",
        )
        assumptions = [
            AssumptionArtifact(
                project_id=mission.project_id,
                label=f"Confirm {field}",
                statement=f"The missing {field} can be safely inferred for this mission.",
                category="context",
                criticality=Severity.MEDIUM,
                validation_method="owner confirmation",
                counterfactual=f"If {field} is different, the selected operating system may need recompilation.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "missing_context"],
            )
            for field in missing
        ]
        for hypothesis in hypotheses:
            assumptions.append(AssumptionArtifact(
                project_id=mission.project_id,
                label=f"Test: {hypothesis}"[:140],
                statement=hypothesis,
                category="operating",
                criticality=Severity.HIGH if profile in {"commerce", "restaurant"} else Severity.MEDIUM,
                validation_method="evidence review",
                counterfactual="If this does not hold, stop the affected workstream and record an alternative.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "operating_hypothesis", profile],
            ))
        gaps = self._gaps(diagnosis, evidence, stakeholders, decision_rights)
        risks = self._risks(diagnosis, profile)
        return diagnosis, assumptions, gaps, risks, evidence

    @staticmethod
    def _profile(values: dict[str, str], intent: str) -> str:
        searchable = " ".join([*values.values(), intent]).lower()
        if _contains(searchable, _RESTAURANT_TERMS):
            return "restaurant"
        if _contains(searchable, _COMMERCE_TERMS):
            return "commerce"
        if _contains(searchable, _PRODUCT_TERMS):
            return "product"
        if _contains(searchable, _CONSULTING_TERMS):
            return "consulting"
        return "general"

    @staticmethod
    def _dimensions(profile: str, stakeholders: list[str], decision_rights: list[str], evidence: list[EvidenceArtifact]) -> list[str]:
        dimensions = {
            "commerce": ["demand", "funnel", "merchandising", "economics", "fulfillment"],
            "restaurant": ["store traffic", "menu", "labor", "local marketing", "unit economics"],
            "product": ["user problem", "product value", "stakeholder alignment", "delivery", "adoption"],
            "consulting": ["client decision", "evidence", "recommendation", "delivery quality"],
            "general": ["current state", "decision rights", "constraints", "execution rhythm"],
        }[profile].copy()
        if stakeholders:
            dimensions.append("stakeholder ownership")
        if decision_rights:
            dimensions.append("decision authority")
        if evidence:
            dimensions.append("observed evidence")
        return dimensions

    @staticmethod
    def _hypotheses(profile: str, values: dict[str, str], constraints: list[str], intent: str) -> list[str]:
        objective = values["goal"] or intent
        hypotheses = {
            "commerce": [
                f"The largest controllable loss in {objective} can be isolated in the customer funnel.",
                "A constrained experiment can improve conversion before additional acquisition spend is justified.",
            ],
            "restaurant": [
                f"Store-level traffic, menu conversion, or labor execution is limiting {objective}.",
                "A local store experiment can be measured before it is rolled out across the chain.",
            ],
            "product": [
                f"The next ownership decision for {objective} depends on validated user and stakeholder evidence.",
                "A staged delivery plan can increase ownership without exceeding current decision authority.",
            ],
            "consulting": [
                f"The client decision for {objective} can be narrowed with an evidence-backed option set.",
                "A reviewable decision brief can make assumptions and tradeoffs explicit before delivery.",
            ],
            "general": [
                f"The operating bottleneck for {objective} can be isolated before a broad workflow change is made.",
                "The declared constraints can be converted into explicit stop conditions and review cadence.",
            ],
        }[profile]
        if constraints:
            hypotheses.append(f"The constraint '{constraints[0]}' remains binding throughout execution.")
        return hypotheses[:3]

    @staticmethod
    def _default_metrics(profile: str, goal: str) -> list[str]:
        objective = goal or "the requested outcome"
        return {
            "commerce": [f"funnel baseline for {objective}", "conversion or repeat-order movement", "experiment cost per incremental outcome"],
            "restaurant": [f"store baseline for {objective}", "traffic-to-order conversion", "store contribution or labor impact"],
            "product": [f"evidence-backed milestone for {objective}", "stakeholder decision latency", "user adoption or delivery outcome"],
            "consulting": [f"decision readiness for {objective}", "evidence coverage", "client acceptance of recommendation"],
            "general": [f"baseline and target for {objective}", "owner completion rate", "reviewed outcome quality"],
        }[profile]

    @staticmethod
    def _risk_summary(profile: str, values: dict[str, str], constraints: list[str], intent: str) -> list[str]:
        searchable = " ".join([*constraints, intent]).lower()
        summary = {
            "commerce": ["Demand, inventory, conversion, and promotion economics can move together."],
            "restaurant": ["Store execution can vary by location; chain-wide rollout before a local baseline is risky."],
            "product": ["Stakeholder alignment and decision authority can block a technically valid product plan."],
            "consulting": ["Recommendation quality is limited by source coverage and client decision rights."],
            "general": ["Evidence and constraint coverage should be reviewed before execution."],
        }[profile].copy()
        if any(term in searchable for term in ("budget", "limited", "\u9884\u7b97", "\u6709\u9650")):
            summary.append("Resource allocation may limit intervention options.")
        if not values["organization_stage"]:
            summary.append("Organization stage is unknown; the operating cadence may be misfit.")
        return summary

    @staticmethod
    def _evidence(project_id: str, raw: Any) -> list[EvidenceArtifact]:
        records = raw if isinstance(raw, list) else []
        evidence: list[EvidenceArtifact] = []
        for index, item in enumerate(records[:20], start=1):
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            finding = str(item.get("finding") or item.get("statement") or "").strip()
            if not source or not finding:
                continue
            evidence.append(EvidenceArtifact(
                project_id=project_id,
                label=f"Evidence {index}: {source}"[:140],
                evidence_type=str(item.get("type") or "declared_source")[:80],
                source=source[:500],
                finding=finding[:4_000],
                strength=_severity(item.get("strength")),
                parent_ids=[],
                source_agent="dbos_intake_evidence",
                tags=["dbos", "declared_evidence"],
            ))
        return evidence

    @staticmethod
    def _gaps(
        diagnosis: DiagnosisArtifact,
        evidence: list[EvidenceArtifact],
        stakeholders: list[str],
        decision_rights: list[str],
    ) -> list[GapArtifact]:
        gaps = [
            GapArtifact(
                project_id=diagnosis.project_id,
                label=f"Missing {field}",
                gap_statement=f"Mission cannot validate {field} from the declared intake.",
                category=GapCategory.EVIDENCE_MISSING,
                severity=Severity.MEDIUM,
                affected_artifact_ids=[diagnosis.artifact_id],
                resolution=f"Confirm {field} before expanding autonomous execution.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "evidence_gap"],
            )
            for field in diagnosis.missing_fields
        ]
        if not evidence:
            gaps.append(GapArtifact(
                project_id=diagnosis.project_id,
                label="Missing observable baseline",
                gap_statement="No source-backed baseline was declared for the requested outcome.",
                category=GapCategory.EVIDENCE_MISSING,
                severity=Severity.HIGH,
                affected_artifact_ids=[diagnosis.artifact_id],
                resolution="Record a source, current signal, and measurement window before scaling an intervention.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "evidence_gap", "baseline"],
            ))
        if not stakeholders:
            gaps.append(GapArtifact(
                project_id=diagnosis.project_id,
                label="Stakeholder ownership not declared",
                gap_statement="The responsible stakeholders are not explicit for this mission.",
                category=GapCategory.ANALYSIS_INSUFFICIENT,
                severity=Severity.MEDIUM,
                affected_artifact_ids=[diagnosis.artifact_id],
                resolution="Name the affected owners and review participants before execution.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "ownership_gap"],
            ))
        if not decision_rights:
            gaps.append(GapArtifact(
                project_id=diagnosis.project_id,
                label="Decision authority not declared",
                gap_statement="The mission has no declared decision owner or escalation path.",
                category=GapCategory.ANALYSIS_INSUFFICIENT,
                severity=Severity.MEDIUM,
                affected_artifact_ids=[diagnosis.artifact_id],
                resolution="Declare who can accept, stop, or escalate the planned work.",
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "decision_rights_gap"],
            ))
        return gaps

    @staticmethod
    def _risks(diagnosis: DiagnosisArtifact, profile: str) -> list[RiskArtifact]:
        dimension = {
            "commerce": RiskDimension.MARKET,
            "restaurant": RiskDimension.OPERATIONAL,
            "product": RiskDimension.ORGANIZATION,
            "consulting": RiskDimension.STRATEGIC,
            "general": RiskDimension.PROCESS,
        }[profile]
        risks: list[RiskArtifact] = []
        for summary in diagnosis.risk_summary:
            risks.append(RiskArtifact(
                project_id=diagnosis.project_id,
                label=f"Risk: {summary}"[:140],
                risk_statement=summary,
                dimension=dimension,
                severity=Severity.HIGH if "Resource" in summary or "block" in summary else Severity.MEDIUM,
                probability=Severity.MEDIUM,
                mitigation="Use the Dynamic SOP decision gate and stop criteria before expanding the affected workstream.",
                contingency="Pause the affected task, record the observed result, and request a new reviewed decision.",
                trigger_signals=["metric moves outside the declared threshold", "evidence contradicts the active hypothesis"],
                affected_artifact_ids=[diagnosis.artifact_id],
                parent_ids=[diagnosis.artifact_id],
                source_agent="dbos_diagnosis",
                tags=["dbos", "diagnostic_risk", profile],
            ))
        return risks
