"""Phase 4 - Reflection Engine + Gap Analyzer + Gap Resolver.

ADR-010 Reflection Loop (three stages):
  1. ReflectionEngine   — counterfactual reasoning, find gaps
  2. GapAnalyzer        — classify gaps (Type A/B/C)
  3. GapResolver        — execute resolution strategy

Type A (EVIDENCE_MISSING)    → RequestEvidence via evidence_validation
Type B (ANALYSIS_INSUFFICIENT) → AddCapability via replan
Type C (MODEL_FAILED)        → GenerateAlternative via replan

This is the "autonomous thinking loop" — the AI consultant reviews
its own judgments and improves the analysis iteratively.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.artifacts.types import (
    ArtifactType,
    AssumptionArtifact,
    BaseArtifact,
    BusinessModelArtifact,
    CoverageArtifact,
    DecisionArtifact,
    EvidenceArtifact,
    GapArtifact,
    GapCategory,
    RiskArtifact,
    Severity,
)
from app.artifacts.store import ArtifactGraphStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 1: Reflection Engine
# ---------------------------------------------------------------------------

class ReflectionEngine:
    """Counterfactual reasoning to discover gaps.

    The engine asks hard questions:
      - "If assumption X is wrong, does the conclusion still hold?"
      - "Which risks have no mitigation?"
      - "Which decisions lack coverage analysis?"
    """

    def __init__(self, store: ArtifactGraphStore):
        self.store = store
        self._findings: list[str] = []

    def reflect(self) -> list[GapArtifact]:
        """Run all reflection checks and return discovered gaps."""
        self._findings = []
        gaps: list[GapArtifact] = []

        gaps.extend(self._check_unvalidated_assumptions())
        gaps.extend(self._check_missing_risk_coverage())
        gaps.extend(self._check_decision_quality())
        gaps.extend(self._check_coverage_completeness())
        gaps.extend(self._check_counterfactual_integrity())

        logger.info("Reflection complete: %d gaps found", len(gaps))
        for g in gaps:
            logger.debug("  Gap: %s [%s]", g.gap_statement, g.category.value)

        return gaps

    def _check_unvalidated_assumptions(self) -> list[GapArtifact]:
        """Find assumptions that have no supporting evidence."""
        gaps = []
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        evidences = self.store.get_by_type(ArtifactType.EVIDENCE)
        evidenced_ids = {
            e.supports_assumption_id
            for e in evidences
            if isinstance(e, EvidenceArtifact) and e.supports_assumption_id
        }

        for a in assumptions:
            if not isinstance(a, AssumptionArtifact):
                continue
            if a.validated:
                continue
            if a.artifact_id in evidenced_ids:
                continue

            # Check counterfactual
            cf_msg = ""
            if a.counterfactual and a.counterfactual_holds is False:
                cf_msg = f" Counterfactual FAILS: {a.counterfactual}"

            gap = GapArtifact(
                gap_statement=f"Assumption '{a.statement}' has no evidence{cf_msg}",
                category=GapCategory.EVIDENCE_MISSING,
                severity=a.criticality,
                affected_artifact_ids=[a.artifact_id],
                parent_ids=[a.artifact_id],
            )
            self.store.add(gap)
            gaps.append(gap)
            self._findings.append(f"Unvalidated assumption: {a.statement}")

        return gaps

    def _check_missing_risk_coverage(self) -> list[GapArtifact]:
        """Check if business model has risk analysis coverage."""
        gaps = []
        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)
        risks = self.store.get_by_type(ArtifactType.RISK)

        if biz_models and not risks:
            gap = GapArtifact(
                gap_statement="Business model has no risk analysis",
                category=GapCategory.ANALYSIS_INSUFFICIENT,
                severity=Severity.HIGH,
                affected_artifact_ids=[bm.artifact_id for bm in biz_models],
            )
            self.store.add(gap)
            gaps.append(gap)

        # Check: risks without mitigation
        for r in risks:
            if not isinstance(r, RiskArtifact):
                continue
            if r.severity in (Severity.HIGH, Severity.CRITICAL) and not r.mitigation:
                gap = GapArtifact(
                    gap_statement=f"High-severity risk '{r.risk_statement}' has no mitigation",
                    category=GapCategory.ANALYSIS_INSUFFICIENT,
                    severity=r.severity,
                    affected_artifact_ids=[r.artifact_id],
                    parent_ids=[r.artifact_id],
                )
                self.store.add(gap)
                gaps.append(gap)

        return gaps

    def _check_decision_quality(self) -> list[GapArtifact]:
        """Check if decisions are well-supported."""
        gaps = []
        decisions = self.store.get_by_type(ArtifactType.DECISION)
        coverages = self.store.get_by_type(ArtifactType.COVERAGE)

        has_coverage = len(coverages) > 0

        for d in decisions:
            if not isinstance(d, DecisionArtifact):
                continue
            if not has_coverage:
                gap = GapArtifact(
                    gap_statement=f"Decision '{d.decision_statement}' lacks coverage analysis",
                    category=GapCategory.ANALYSIS_INSUFFICIENT,
                    severity=Severity.MEDIUM,
                    affected_artifact_ids=[d.artifact_id],
                    parent_ids=[d.artifact_id],
                )
                self.store.add(gap)
                gaps.append(gap)

            if d.assumption_confidence < 0.6:
                gap = GapArtifact(
                    gap_statement=f"Decision '{d.decision_statement}' has low assumption confidence ({d.assumption_confidence:.0%})",
                    category=GapCategory.EVIDENCE_MISSING,
                    severity=Severity.HIGH,
                    affected_artifact_ids=[d.artifact_id],
                    parent_ids=[d.artifact_id],
                )
                self.store.add(gap)
                gaps.append(gap)

        return gaps

    def _check_coverage_completeness(self) -> list[GapArtifact]:
        """Check coverage artifacts for missed dimensions."""
        gaps = []
        coverages = self.store.get_by_type(ArtifactType.COVERAGE)

        for c in coverages:
            if not isinstance(c, CoverageArtifact):
                continue
            if c.dimensions_missed:
                gap = GapArtifact(
                    gap_statement=f"Coverage missed dimensions: {', '.join(c.dimensions_missed)}",
                    category=GapCategory.ANALYSIS_INSUFFICIENT,
                    severity=Severity.MEDIUM,
                    affected_artifact_ids=[c.artifact_id],
                    parent_ids=[c.artifact_id],
                )
                self.store.add(gap)
                gaps.append(gap)

        return gaps

    def _check_counterfactual_integrity(self) -> list[GapArtifact]:
        """Evaluate counterfactuals on assumptions."""
        gaps = []
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)

        for a in assumptions:
            if not isinstance(a, AssumptionArtifact):
                continue
            if a.counterfactual and a.counterfactual_holds is False:
                gap = GapArtifact(
                    gap_statement=f"Counterfactual check FAILED: {a.counterfactual}",
                    category=GapCategory.MODEL_FAILED if a.criticality == Severity.CRITICAL else GapCategory.EVIDENCE_MISSING,
                    severity=a.criticality,
                    affected_artifact_ids=[a.artifact_id],
                    parent_ids=[a.artifact_id],
                )
                self.store.add(gap)
                gaps.append(gap)

        return gaps


# ---------------------------------------------------------------------------
# Stage 2: Gap Analyzer
# ---------------------------------------------------------------------------

class GapAnalyzer:
    """Classify gaps and determine resolution strategy.

    Type A: EVIDENCE_MISSING     → RequestEvidence
    Type B: ANALYSIS_INSUFFICIENT → AddCapability
    Type C: MODEL_FAILED         → GenerateAlternative
    """

    def analyze(self, gaps: list[GapArtifact]) -> dict[str, Any]:
        """Analyze gaps and produce a resolution plan.

        Returns:
            {
                "total": N,
                "by_category": { "evidence_missing": N, ... },
                "by_severity": { "critical": N, ... },
                "requires_replan": bool,
                "recommendations": [...],
            }
        """
        by_category: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        recommendations: list[str] = []

        for gap in gaps:
            cat = gap.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

            sev = gap.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            if gap.category == GapCategory.EVIDENCE_MISSING:
                recommendations.append(f"Invoke evidence_validation for: {gap.gap_statement[:80]}")
            elif gap.category == GapCategory.ANALYSIS_INSUFFICIENT:
                recommendations.append(f"Add capability for: {gap.gap_statement[:80]}")
            elif gap.category == GapCategory.MODEL_FAILED:
                recommendations.append(f"CRITICAL — Generate alternative for: {gap.gap_statement[:80]}")

        requires_replan = any(
            g.category in (GapCategory.ANALYSIS_INSUFFICIENT, GapCategory.MODEL_FAILED)
            for g in gaps
        )

        return {
            "total": len(gaps),
            "by_category": by_category,
            "by_severity": by_severity,
            "requires_replan": requires_replan,
            "recommendations": recommendations,
        }


# ---------------------------------------------------------------------------
# Stage 3: Gap Resolver
# ---------------------------------------------------------------------------

class GapResolver:
    """Execute gap resolution strategies.

    Three resolution paths:
      - Type A → evidence_validation capability
      - Type B → replan (add missing capability)
      - Type C → replan (generate alternative model)
    """

    def __init__(self, store: ArtifactGraphStore, capability_registry=None):
        self.store = store
        self.registry = capability_registry

    def resolve(self, gaps: list[GapArtifact]) -> tuple[int, bool]:
        """Resolve gaps. Returns (resolved_count, needs_replan).

        Args:
            gaps: List of GapArtifacts to resolve.

        Returns:
            (number of gaps resolved, whether replanning is needed)
        """
        resolved = 0
        needs_replan = False

        for gap in gaps:
            if gap.resolved:
                resolved += 1
                continue

            resolution, should_replan = self._resolve_one(gap)
            gap.resolution = resolution
            gap.resolved = True
            self.store.update(gap)
            resolved += 1

            if should_replan:
                needs_replan = True

            logger.info(
                "Gap resolved [%s]: %s → %s",
                gap.category.value, gap.gap_statement[:60], gap.resolution,
            )

        return resolved, needs_replan

    def _resolve_one(self, gap: GapArtifact) -> tuple[str, bool]:
        """Resolve a single gap. Returns (resolution_message, needs_replan)."""
        if gap.category == GapCategory.EVIDENCE_MISSING:
            return self._resolve_evidence(gap)
        elif gap.category == GapCategory.ANALYSIS_INSUFFICIENT:
            return self._resolve_analysis(gap)
        elif gap.category == GapCategory.MODEL_FAILED:
            return self._resolve_model_failure(gap)
        return "unknown category", False

    def _resolve_evidence(self, gap: GapArtifact) -> tuple[str, bool]:
        """Type A: Request evidence validation."""
        if self.registry:
            cap = self.registry.get("evidence_validation")
            if cap and cap.executor_key:
                return f"Queued evidence_validation via {cap.executor_key}", False
        return "Evidence validation not available — flagged for manual review", False

    def _resolve_analysis(self, gap: GapArtifact) -> tuple[str, bool]:
        """Type B: Add missing capability via replan."""
        return "Additional analysis capability queued for next iteration", True

    def _resolve_model_failure(self, gap: GapArtifact) -> tuple[str, bool]:
        """Type C: Generate alternative model.

        This is the most severe — the business model itself has a flaw.
        """
        return "Model failure detected — alternative generation required", True


# ---------------------------------------------------------------------------
# Unified Reflection Pipeline
# ---------------------------------------------------------------------------

class ReflectionPipeline:
    """Convenience: runs all three stages in sequence.

    Usage:
        pipeline = ReflectionPipeline(store, registry)
        report = pipeline.run()
        print(report["summary"])
    """

    def __init__(self, store: ArtifactGraphStore, capability_registry=None):
        self.engine = ReflectionEngine(store)
        self.analyzer = GapAnalyzer()
        self.resolver = GapResolver(store, capability_registry)

    def run(self) -> dict[str, Any]:
        """Execute full reflection pipeline.

        Returns a structured report dict.
        """
        # Stage 1: Reflect
        gaps = self.engine.reflect()

        # Stage 2: Analyze
        analysis = self.analyzer.analyze(gaps)

        # Stage 3: Resolve
        resolved, needs_replan = self.resolver.resolve(gaps)

        return {
            "stages": {
                "reflect": {"gaps_found": len(gaps)},
                "analyze": analysis,
                "resolve": {"resolved": resolved, "needs_replan": needs_replan},
            },
            "summary": (
                f"Reflection found {len(gaps)} gaps "
                f"({analysis['by_category']}), "
                f"resolved {resolved}, "
                f"replan={'YES' if needs_replan else 'no'}."
            ),
            "gaps": [
                {
                    "statement": g.gap_statement,
                    "category": g.category.value,
                    "severity": g.severity.value,
                    "resolution": g.resolution,
                    "resolved": g.resolved,
                }
                for g in gaps
            ],
        }

# ---------------------------------------------------------------------------
# LLM Reflection Engine (counterfactual reasoning)
# ---------------------------------------------------------------------------

class LLMReflectionEngine:
    """LLM-driven counterfactual reasoning for gap discovery.

    Unlike the rule-based ReflectionEngine, this sends the full
    Artifact Graph to an LLM with specialized prompts that ask
    hard counterfactual questions:

      - "If assumption X is wrong, what breaks first?"
      - "What risks are implicitly assumed away?"
      - "Which stakeholder perspective is missing?"

    Falls back to rule-based ReflectionEngine if LLM is unavailable.
    """

    COUNTERFACTUAL_PROMPT = """You are a Business Critic — an AI that reviews business analysis for hidden gaps.

Your job: examine a Business Model + its supporting artifacts and find what is MISSING, WRONG, or UNSAFE.

Be skeptical. Ask hard questions. Look for:
1. Unvalidated assumptions that the model depends on
2. Risks that are implicitly assumed away ("that won't happen")
3. Missing stakeholder perspectives (what would a regulator / competitor / customer say?)
4. Coverage gaps — dimensions not analyzed
5. Logical flaws — if assumption X is wrong, does conclusion Y still hold?
6. Missing evidence — claims without data

BUSINESS MODEL:
{business_model}

ASSUMPTIONS:
{assumptions}

RISKS:
{risks}

CONSTRAINTS:
{constraints}

EVIDENCE:
{evidence}

COVERAGE:
{coverage}

DECISIONS:
{decisions}

OUTPUT FORMAT (JSON only, no markdown):
{{
  "gaps": [
    {{
      "gap_statement": "specific, actionable gap description",
      "category": "evidence_missing | analysis_insufficient | model_failed",
      "severity": "critical | high | medium | low",
      "counterfactual": "if X were false, what would happen?",
      "affected_artifact_ids": [],
      "recommendation": "what capability or action would fix this"
    }}
  ],
  "overall_assessment": "1-2 sentence summary of the biggest concern",
  "confidence": 0.85
}}

RULES:
- Be specific. Reference actual artifacts by their content, not just IDs.
- Don't invent problems that don't exist. Only flag real gaps.
- For model_failed gaps: explain WHY the model breaks, not just THAT it might fail.
- Limit to the 5 most critical gaps. Quality over quantity."""

    def __init__(self, store: ArtifactGraphStore, llm_service=None):
        self.store = store
        self._llm = llm_service
        self._fallback = ReflectionEngine(store)

    async def reflect(self, use_llm: bool = True) -> list[GapArtifact]:
        """Run LLM-powered reflection. Falls back to rules on failure."""
        if not use_llm:
            return self._fallback.reflect()

        try:
            llm = self._get_llm()
            prompt = self._build_prompt()
            response = await llm.generate(prompt)
            return self._parse_llm_response(response)
        except Exception as exc:
            logger.warning(
                "LLM reflection failed (%s), falling back to rule-based engine", exc
            )
            return self._fallback.reflect()

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from app.services.llm_adapter import get_llm_adapter
        self._llm = get_llm_adapter()
        return self._llm

    def _build_prompt(self) -> str:
        """Serialize the Artifact Graph into the prompt template."""
        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        risks = self.store.get_by_type(ArtifactType.RISK)
        constraints = self.store.get_by_type(ArtifactType.CONSTRAINT)
        evidences = self.store.get_by_type(ArtifactType.EVIDENCE)
        coverages = self.store.get_by_type(ArtifactType.COVERAGE)
        decisions = self.store.get_by_type(ArtifactType.DECISION)

        def _fmt_artifacts(arts: list) -> str:
            if not arts:
                return "(none)"
            lines = []
            for a in arts:
                d = a.model_dump()
                # Keep only the most relevant fields
                key_fields = {
                    "label": d.get("label", ""),
                    "description": d.get("description", ""),
                    "domain": d.get("domain", ""),
                    "statement": d.get("statement", ""),
                    "risk_statement": d.get("risk_statement", ""),
                    "decision_statement": d.get("decision_statement", ""),
                    "gap_statement": d.get("gap_statement", ""),
                    "constraint_statement": d.get("constraint_statement", ""),
                    "finding": d.get("finding", ""),
                    "rationale": d.get("rationale", ""),
                    "severity": str(d.get("severity", "")),
                    "criticality": str(d.get("criticality", "")),
                    "mitigation": d.get("mitigation", ""),
                    "validated": d.get("validated", ""),
                    "counterfactual": d.get("counterfactual", ""),
                    "objectives": d.get("objectives", []),
                    "value_proposition": d.get("value_proposition", ""),
                }
                relevant = {k: v for k, v in key_fields.items() if v not in ("", [], None, "None")}
                lines.append(f"  [{a.artifact_id}] {relevant}")
            return "\n".join(lines)

        return self.COUNTERFACTUAL_PROMPT.format(
            business_model=_fmt_artifacts(biz_models),
            assumptions=_fmt_artifacts(assumptions),
            risks=_fmt_artifacts(risks),
            constraints=_fmt_artifacts(constraints),
            evidence=_fmt_artifacts(evidences),
            coverage=_fmt_artifacts(coverages),
            decisions=_fmt_artifacts(decisions),
        )

    def _parse_llm_response(self, response_text: str) -> list[GapArtifact]:
        """Parse LLM JSON output into GapArtifacts."""
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        import json as _json
        try:
            data = _json.loads(text)
        except _json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = _json.loads(match.group())
            else:
                raise ValueError(f"Could not parse LLM reflection response: {text[:200]}")

        gaps = []
        for gd in data.get("gaps", []):
            gap = GapArtifact(
                gap_statement=gd.get("gap_statement", ""),
                category=GapCategory(gd.get("category", "evidence_missing")),
                severity=_parse_severity_reflection(gd.get("severity", "medium")),
                affected_artifact_ids=gd.get("affected_artifact_ids", []),
                resolution=gd.get("recommendation", ""),
            )
            self.store.add(gap)
            gaps.append(gap)

        logger.info(
            "LLM reflection: %d gaps found. Assessment: %s",
            len(gaps), data.get("overall_assessment", "")[:100],
        )
        return gaps


def _parse_severity_reflection(value: str) -> Severity:
    mapping = {
        "critical": Severity.CRITICAL, "crit": Severity.CRITICAL,
        "high": Severity.HIGH, "h": Severity.HIGH,
        "medium": Severity.MEDIUM, "med": Severity.MEDIUM, "m": Severity.MEDIUM,
        "low": Severity.LOW, "l": Severity.LOW,
    }
    return mapping.get(value.lower().strip(), Severity.MEDIUM)


# ---------------------------------------------------------------------------
# Updated ReflectionPipeline with LLM support
# ---------------------------------------------------------------------------

class LLMReflectionPipeline:
    """Reflection pipeline that prefers LLM counterfactual reasoning.

    Usage:
        pipe = LLMReflectionPipeline(store, registry)
        report = await pipe.run()
    """

    def __init__(self, store: ArtifactGraphStore, capability_registry=None, llm_service=None):
        self.llm_engine = LLMReflectionEngine(store, llm_service)
        self.rule_engine = ReflectionEngine(store)
        self.analyzer = GapAnalyzer()
        self.resolver = GapResolver(store, capability_registry)

    async def run(self, prefer_llm: bool = True) -> dict[str, Any]:
        """Execute full reflection pipeline, preferring LLM.

        Args:
            prefer_llm: If True, try LLM first, fall back to rules.

        Returns:
            Structured report dict.
        """
        # Stage 1: Reflect (LLM preferred, rule fallback)
        if prefer_llm:
            try:
                gaps = await self.llm_engine.reflect(use_llm=True)
                engine_used = "llm"
            except Exception as exc:
                logger.warning("LLM reflection unavailable: %s", exc)
                gaps = self.rule_engine.reflect()
                engine_used = "rule_fallback"
        else:
            gaps = self.rule_engine.reflect()
            engine_used = "rule"

        # Stage 2: Analyze
        analysis = self.analyzer.analyze(gaps)

        # Stage 3: Resolve
        resolved, needs_replan = self.resolver.resolve(gaps)

        return {
            "engine": engine_used,
            "stages": {
                "reflect": {"gaps_found": len(gaps), "engine": engine_used},
                "analyze": analysis,
                "resolve": {"resolved": resolved, "needs_replan": needs_replan},
            },
            "summary": (
                f"[{engine_used}] Reflection found {len(gaps)} gaps "
                f"({analysis['by_category']}), "
                f"resolved {resolved}, "
                f"replan={'YES' if needs_replan else 'no'}."
            ),
            "gaps": [
                {
                    "statement": g.gap_statement,
                    "category": g.category.value,
                    "severity": g.severity.value,
                    "resolution": g.resolution,
                    "resolved": g.resolved,
                }
                for g in gaps
            ],
        }
