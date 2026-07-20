"""Multi-Agent Board: Parallel role-based business analysis.

CEO/CFO/CTO/Operations agents analyze the same Artifact Graph
from different perspectives, then the Board Review Agent synthesizes.

This is true Agent OS capability — not a pipeline, but autonomous
agents with distinct personas collaborating on analysis.

Usage:
    board = MultiAgentBoard(store, registry)
    result = await board.convene(project_id="p1")
    print(result.board_decision)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.artifacts.store import ArtifactGraphStore
from app.artifacts.types import (
    ArtifactType, BaseArtifact, DecisionArtifact, GapArtifact,
    GapCategory, Severity, BusinessModelArtifact, RiskArtifact,
    AssumptionArtifact,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------

class BoardRole(BaseModel):
    """A role on the business analysis board."""
    role_id: str
    title: str                      # "CEO", "CFO", "CTO", "COO"
    perspective: str                # what this role focuses on
    questions: list[str] = Field(default_factory=list)  # key questions to answer
    decision_weight: float = 1.0    # voting weight in board review
    red_lines: list[str] = Field(default_factory=list)  # deal-breakers


BOARD_ROLES: dict[str, BoardRole] = {
    "ceo": BoardRole(
        role_id="ceo",
        title="CEO Agent",
        perspective="战略视角：关注市场机会、竞争格局、增长路径、长期愿景",
        questions=[
            "这个商业机会的市场天花板在哪里？",
            "竞争壁垒是什么？能维持多久？",
            "团队和资源是否匹配这个战略方向？",
            "6个月/1年/3年的里程碑是什么？",
        ],
        decision_weight=1.5,  # CEO has weighted vote
        red_lines=["市场空间<10亿", "没有差异化壁垒"],
    ),
    "cfo": BoardRole(
        role_id="cfo",
        title="CFO Agent",
        perspective="财务视角：关注单位经济、现金流、ROI、资金效率、成本结构",
        questions=[
            "单位经济是否成立？（LTV/CAC > 3?）",
            "现金流何时转正？需要多少轮融资？",
            "最大的财务风险是什么？",
            "成本结构是否可规模化？",
        ],
        decision_weight=1.2,
        red_lines=["单位经济不成立", "18个月内现金耗尽"],
    ),
    "cto": BoardRole(
        role_id="cto",
        title="CTO Agent",
        perspective="技术视角：关注技术可行性、架构风险、技术债务、研发效率",
        questions=[
            "核心技术是否自主可控？",
            "技术架构能否支撑规模化？",
            "技术团队能力是否匹配需求？",
            "有没有技术层面的单点故障风险？",
        ],
        decision_weight=1.0,
        red_lines=["核心技术依赖第三方且不可替代", "安全合规无法满足"],
    ),
    "coo": BoardRole(
        role_id="coo",
        title="COO Agent",
        perspective="运营视角：关注供应链、执行可行性、SOP、质量管理、客户成功",
        questions=[
            "供应链是否稳定？关键环节是否有备份？",
            "SOP是否清晰可执行？",
            "客户成功体系是否健全？",
            "运营瓶颈在哪里？",
        ],
        decision_weight=1.0,
        red_lines=["供应链单点依赖", "客户留存率预测<50%"],
    ),
    "compliance": BoardRole(
        role_id="compliance",
        title="合规 Agent",
        perspective="合规视角：关注监管风险、合规成本、法律风险、数据安全",
        questions=[
            "需要哪些资质和许可？",
            "合规成本占收入比例？",
            "最大的法律风险是什么？",
            "数据安全是否达标？",
        ],
        decision_weight=1.0,
        red_lines=["无法取得必要资质", "法律风险不可控"],
    ),
}

# Prompt templates for each role
ROLE_PROMPTS: dict[str, str] = {
    "ceo": """你是 CEO Agent，负责从战略高度审视商业方案。

你的视角：市场机会、竞争格局、增长路径、长期愿景。
你必须回答：
1. 市场天花板在哪里？
2. 竞争壁垒是什么？
3. 团队/资源是否匹配？
4. 里程碑是否清晰？

{artifacts}

输出 JSON:
{{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "strategic_analysis": "2-3句核心判断",
  "key_opportunities": ["..."],
  "key_risks": ["..."],
  "red_line_triggered": false,
  "recommendations": ["..."]
}}""",

    "cfo": """你是 CFO Agent，负责从财务视角审视商业方案。

你的视角：单位经济、现金流、ROI、资金效率、成本结构。
你必须回答：
1. 单位经济是否成立？
2. 现金流何时转正？
3. 最大财务风险是什么？
4. 成本可规模化吗？

{artifacts}

输出 JSON:
{{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "financial_analysis": "2-3句核心判断",
  "unit_economics_assessment": "...",
  "funding_requirements": "...",
  "red_line_triggered": false,
  "recommendations": ["..."]
}}""",

    "cto": """你是 CTO Agent，负责从技术视角审视商业方案。

你的视角：技术可行性、架构风险、技术债务、研发效率。
你必须回答：
1. 核心技术自主可控吗？
2. 架构能支撑规模化吗？
3. 团队能力匹配吗？
4. 有单点故障风险吗？

{artifacts}

输出 JSON:
{{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "technical_analysis": "2-3句核心判断",
  "architecture_risks": ["..."],
  "scalability_assessment": "...",
  "red_line_triggered": false,
  "recommendations": ["..."]
}}""",

    "coo": """你是 COO Agent，负责从运营执行视角审视商业方案。

你的视角：供应链、执行可行性、SOP、质量管理、客户成功。
你必须回答：
1. 供应链稳定吗？
2. SOP清晰可执行吗？
3. 客户成功体系健全吗？
4. 运营瓶颈在哪？

{artifacts}

输出 JSON:
{{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "operational_analysis": "2-3句核心判断",
  "supply_chain_risk": "...",
  "execution_bottlenecks": ["..."],
  "red_line_triggered": false,
  "recommendations": ["..."]
}}""",

    "compliance": """你是合规 Agent，负责从监管合规视角审视商业方案。

你的视角：监管风险、合规成本、法律风险、数据安全。
你必须回答：
1. 需要哪些资质？
2. 合规成本占比？
3. 最大法律风险？
4. 数据安全达标吗？

{artifacts}

输出 JSON:
{{
  "verdict": "go | conditional_go | no_go",
  "confidence": 0.85,
  "compliance_analysis": "2-3句核心判断",
  "required_licenses": ["..."],
  "legal_risks": ["..."],
  "red_line_triggered": false,
  "recommendations": ["..."]
}}""",
}


# ---------------------------------------------------------------------------
# Role Opinion
# ---------------------------------------------------------------------------

class RoleOpinion(BaseModel):
    """Output from a single board role agent."""
    role_id: str = ""
    role_title: str = ""
    verdict: str = "conditional_go"       # go | conditional_go | no_go
    confidence: float = 0.8
    analysis: str = ""                     # core analysis text
    key_points: list[str] = Field(default_factory=list)
    red_line_triggered: bool = False
    red_line_detail: str = ""
    recommendations: list[str] = Field(default_factory=list)
    raw_response: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Board Decision
# ---------------------------------------------------------------------------

class BoardDecision(BaseModel):
    """Final synthesized board decision."""
    decision_id: str = ""
    project_id: str = ""
    convened_at: str = ""

    # Votes
    votes: dict[str, str] = Field(default_factory=dict)    # {role_id: verdict}
    weighted_score: float = 0.0                             # weighted average
    consensus: str = "split"                                # unanimous | majority | split
    final_verdict: str = "conditional_go"                   # go | conditional_go | no_go

    # Synthesis
    aligned_on: list[str] = Field(default_factory=list)     # what everyone agrees
    conflicts: list[dict] = Field(default_factory=list)     # [{role_a, role_b, issue}]
    key_conditions: list[str] = Field(default_factory=list) # conditions for go
    executive_summary: str = ""
    minority_report: str = ""                               # dissenting view if any


# ---------------------------------------------------------------------------
# Multi-Agent Board
# ---------------------------------------------------------------------------

class MultiAgentBoard:
    """Orchestrates parallel analysis by multiple role agents.

    Usage:
        board = MultiAgentBoard(store)
        result = await board.convene(project_id="p1")
        print(result.final_verdict)
    """

    def __init__(self, store: ArtifactGraphStore, llm_service=None):
        self.store = store
        self._llm = llm_service
        self._opinions: dict[str, RoleOpinion] = {}

    async def convene(
        self,
        project_id: str = "",
        roles: list[str] | None = None,
    ) -> BoardDecision:
        """Convene the board — all roles analyze and vote.

        Args:
            project_id: Project to analyze.
            roles: Which roles to include (default: all).

        Returns:
            BoardDecision with final verdict.
        """
        active_roles = roles or list(BOARD_ROLES.keys())
        role_objects = [BOARD_ROLES[r] for r in active_roles if r in BOARD_ROLES]

        logger.info("Board convening: %d roles for project %s", len(role_objects), project_id)

        # Phase 1: Parallel role analysis
        tasks = [self._analyze_role(role, project_id) for role in role_objects]
        opinions = await asyncio.gather(*tasks)

        for opinion in opinions:
            self._opinions[opinion.role_id] = opinion

        # Phase 2: Board review — synthesize
        decision = self._synthesize(project_id, opinions)

        # Phase 3: Record the board decision as an artifact
        self._record_decision(decision, project_id)

        return decision

    async def _analyze_role(
        self, role: BoardRole, project_id: str
    ) -> RoleOpinion:
        """Have a single role agent analyze the artifacts."""
        logger.info("Board: %s analyzing...", role.title)

        # Build role-specific context
        artifacts_text = self._build_artifact_context(project_id)

        # Use the provider path; any rule-based fallback is policy-gated below.
        try:
            llm = self._get_llm()
            prompt = ROLE_PROMPTS.get(role.role_id, "").format(artifacts=artifacts_text)
            response = await llm.generate(prompt)
            data = self._parse_response(response)
        except (Exception, AttributeError) as exc:
            # Rule-based analysis is a development fallback, not a silent
            # substitute for a failed production model invocation.
            from app.core.llm_policy import ensure_fallback_allowed

            ensure_fallback_allowed("MultiAgentBoard role analysis")
            logger.warning(
                "Board role %s using rule-based fallback: %s",
                role.role_id,
                exc,
            )
            data = self._rule_based_role_analysis(role, project_id)

        return RoleOpinion(
            role_id=role.role_id,
            role_title=role.title,
            verdict=data.get("verdict", "conditional_go"),
            confidence=data.get("confidence", 0.8),
            analysis=data.get(
                f"{role.role_id}_analysis",
                data.get("strategic_analysis",
                data.get("financial_analysis",
                data.get("technical_analysis",
                data.get("operational_analysis",
                data.get("compliance_analysis", ""))))),
            ),
            key_points=data.get("key_opportunities", data.get("key_risks", [])),
            red_line_triggered=data.get("red_line_triggered", False),
            recommendations=data.get("recommendations", []),
            raw_response=data,
        )

    def _build_artifact_context(self, project_id: str) -> str:
        """Serialize Artifact Graph for Board, excluding prior Decisions to prevent feedback loops."""
        artifacts = (
            self.store.get_by_project(project_id)
            if project_id
            else [self.store.get(aid) for aid in self.store.list_all()]
        )

        lines = []
        for art in artifacts:
            if art is None:
                continue
            # ADR-010 fix: skip prior Board Decision artifacts to prevent self-reinforcing feedback
            if art.artifact_type.value == "decision" and "Board Decision" in (art.label or ""):
                continue
            d = art.model_dump()
            lines.append(f"\n[{art.artifact_type.value.upper()}] {art.label}")
            for key in ("value_proposition", "statement", "risk_statement",
                        "decision_statement", "constraint_statement",
                        "gap_statement", "finding", "rationale",
                        "mitigation", "severity", "description"):
                val = d.get(key, "")
                if val:
                    lines.append(f"  {key}: {val}")

        return "\n".join(lines) if lines else "(no artifacts)"

    def _rule_based_role_analysis(
        self, role: BoardRole, project_id: str
    ) -> dict[str, Any]:
        """Deterministic development fallback based on Artifact Graph data.

        It is only reachable when the shared fallback policy allows it.
        """
        risks = self.store.get_by_type(ArtifactType.RISK)
        assumptions = self.store.get_by_type(ArtifactType.ASSUMPTION)
        decisions = self.store.get_by_type(ArtifactType.DECISION)
        biz_models = self.store.get_by_type(ArtifactType.BUSINESS_MODEL)

        critical_risks = [
            r for r in risks
            if isinstance(r, RiskArtifact) and r.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        unvalidated = [
            a for a in assumptions
            if isinstance(a, AssumptionArtifact) and not a.validated
        ]
        has_decision = len(decisions) > 0

        red_line = False
        if role.role_id == "ceo":
            analysis = f"市场机会存在，但需验证{len(unvalidated)}个关键假设。竞争差异化是核心。"
            verdict = "conditional_go" if unvalidated else "go"
        elif role.role_id == "cfo":
            analysis = f"商业模式清晰，但需验证单位经济。注意{len(critical_risks)}个高风险项的资金影响。"
            verdict = "conditional_go"
        elif role.role_id == "cto":
            analysis = f"技术架构需评估规模化能力。冷链系统是技术关键路径。"
            verdict = "conditional_go"
        elif role.role_id == "coo":
            analysis = f"供应链稳定性是关键。{len(critical_risks)}个高风险项涉及运营。需要SOP和备份方案。"
            verdict = "conditional_go" if critical_risks else "go"
            if any("冷链" in str(getattr(r, 'risk_statement', '')) for r in critical_risks):
                red_line = True
        else:  # compliance
            analysis = f"需要取得食品经营许可等资质。合规成本可控但不可忽略。"
            verdict = "conditional_go"

        return {
            "verdict": verdict,
            "confidence": 0.75,
            f"{role.role_id}_analysis": analysis,
            "red_line_triggered": red_line,
            "recommendations": [
                f"验证{len(unvalidated)}个假设",
                f"建立{len(critical_risks)}个高风险项的缓解方案",
            ],
        }

    def _synthesize(
        self, project_id: str, opinions: list[RoleOpinion]
    ) -> BoardDecision:
        """Board Review: synthesize all role opinions into a final decision."""
        from collections import Counter

        # Count votes
        votes = {o.role_id: o.verdict for o in opinions}
        verdict_counts = Counter(votes.values())
        total_weight = sum(
            BOARD_ROLES[o.role_id].decision_weight for o in opinions
            if o.role_id in BOARD_ROLES
        )

        # Weighted score: go=1, conditional_go=0.5, no_go=0
        score_map = {"go": 1.0, "conditional_go": 0.5, "no_go": 0.0}
        weighted = sum(
            score_map.get(o.verdict, 0.5) * BOARD_ROLES.get(o.role_id, BoardRole(
                role_id=o.role_id, title="", perspective="", decision_weight=1.0
            )).decision_weight
            for o in opinions
        )
        weighted_score = weighted / max(total_weight, 1)

        # Consensus level
        if len(set(votes.values())) == 1:
            consensus = "unanimous"
        elif verdict_counts.most_common(1)[0][1] >= len(opinions) / 2:
            consensus = "majority"
        else:
            consensus = "split"

        # Final verdict
        if weighted_score >= 0.75:
            final_verdict = "go"
        elif weighted_score >= 0.35:
            final_verdict = "conditional_go"
        else:
            final_verdict = "no_go"

        # Find aligned points and conflicts
        aligned = []
        conflicts = []

        # Any red lines triggered?
        red_line_roles = [o for o in opinions if o.red_line_triggered]
        for rlo in red_line_roles:
            conflicts.append({
                "role": rlo.role_title,
                "issue": "RED LINE triggered",
                "detail": rlo.red_line_detail or "Critical risk identified",
            })

        # All agree on: need more evidence
        all_recommendations = []
        for o in opinions:
            all_recommendations.extend(o.recommendations)
        rec_counter = Counter(all_recommendations)
        for rec, count in rec_counter.most_common(3):
            if count >= 2:
                aligned.append(rec)

        # Key conditions
        conditions = []
        for o in opinions:
            if o.verdict == "conditional_go":
                conditions.append(f"[{o.role_title}] {o.analysis[:80]}")

        # Executive summary
        go_count = verdict_counts.get("go", 0)
        cond_count = verdict_counts.get("conditional_go", 0)
        no_count = verdict_counts.get("no_go", 0)

        summary = (
            f"Board投票: {go_count} Go / {cond_count} Conditional / {no_count} No-Go. "
            f"加权得分: {weighted_score:.2f}. "
            f"共识: {consensus}. "
            f"最终裁决: {final_verdict.upper()}. "
        )

        # Minority report (if any dissenting)
        minority = ""
        if no_count > 0:
            dissenters = [o for o in opinions if o.verdict == "no_go"]
            minority = f"反对意见 ({len(dissenters)}票): " + "; ".join(
                f"{o.role_title}: {o.analysis[:60]}" for o in dissenters
            )

        return BoardDecision(
            decision_id=f"board_{project_id}_{int(time.time())}",
            project_id=project_id,
            convened_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            votes=votes,
            weighted_score=round(weighted_score, 2),
            consensus=consensus,
            final_verdict=final_verdict,
            aligned_on=aligned,
            conflicts=conflicts,
            key_conditions=conditions,
            executive_summary=summary,
            minority_report=minority,
        )

    def _record_decision(
        self, decision: BoardDecision, project_id: str
    ) -> str:
        """Record the board decision as a DecisionArtifact."""
        art = DecisionArtifact(
            label=f"Board Decision: {decision.final_verdict.upper()}",
            decision_statement=(
                f"董事会裁决: {decision.final_verdict.upper()} "
                f"(加权得分: {decision.weighted_score}, 共识: {decision.consensus})"
            ),
            alternatives=[
                f"Go ({decision.votes.get('go', 0)} 票)",
                f"No-Go ({decision.votes.get('no_go', 0)} 票)",
            ],
            rationale=decision.executive_summary,
            assumption_confidence=decision.weighted_score,
            risk_acceptable=decision.final_verdict != "no_go",
            coverage_pct=100.0,
            recommendation="; ".join(decision.aligned_on),
            decision_makers=[o.role_title for o in self._opinions.values()],
            source_agent="board_review",
            project_id=project_id,
        )
        self.store.add(art)
        logger.info("Board decision recorded: %s", art.artifact_id)
        return art.artifact_id

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from app.services.llm_adapter import get_llm_adapter
        self._llm = get_llm_adapter()
        return self._llm

    def _parse_response(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"verdict": "conditional_go", "confidence": 0.5}
