# app/evaluation/compiler_evaluator.py
"""
方案 C — Phase 1：编译器产物评测器（Evals）

把 A（方法论引用）/ B（约束覆盖与门禁）/ E（SHA-256 可信审计链）已经攒下的
质量信号，聚合成一份带维度的质量评分报告（QualityReport），让编译器每次产出
都有可量化的质量分。

设计约束：
- 纯规则评分，确定性、无 LLM 依赖、可单测（测试走 venv 解释器）。
- 复用 app.core.prd_quality_scorer 的 QualityReport / QualityDimension 模型，不重复造轮子。
- 入参缺字段时对应维度给 0 分并标注「未提供」，优雅降级不崩。
- 不持久化、不改 ProjectDraft schema；由仪表盘端点即时计算（同方案 E 的 trusted_audit）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.core.prd_quality_scorer import QualityDimension, QualityReport
from app.audit import build_trusted_audit

# 门禁决策 -> 健康分映射
_GATE_SCORE = {"pass": 100, "warn": 70, "block": 40}


def _safe(v) -> float:
    """把可能是 None / 非数值的值安全转成 float；None 返回 0.0。"""
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0


class CompilerOutputEvaluator:
    """对编译产物 state（ProjectDraft.to_dict()）做带维度质量评分。"""

    def __init__(self, threshold: int = 70):
        self.threshold = threshold

    # ---------- 公共入口 ----------
    def evaluate(self, state: Optional[dict], trusted_audit: Optional[dict] = None) -> QualityReport:
        state = state or {}
        sop = state.get("sop") or {}
        risk = state.get("risk") or {}
        business_model = state.get("business_model") or {}

        dimensions: List[QualityDimension] = [
            self._methodology_dimension(sop, business_model),
            self._constraint_dimension(risk),
            self._gate_dimension(risk),
            self._audit_dimension(state, trusted_audit),
            self._structure_dimension(sop, business_model, risk),
        ]

        overall = sum(d.score * d.weight for d in dimensions)
        suggestions = [f"{d.name}不足：{d.feedback}" for d in dimensions if d.score < 60]
        level = self._level(overall)
        return QualityReport(
            overall_score=int(overall),
            dimensions=dimensions,
            summary=f"编译器产物综合评分：{int(overall)}分（{level}）",
            suggestions=suggestions,
            is_passed=int(overall) >= self.threshold,
            improvement_points=len(suggestions),
        )

    # ---------- 维度 1：方法论采用度（A）----------
    def _methodology_dimension(self, sop: dict, business_model: dict) -> QualityDimension:
        sop_cov = (sop.get("_citation_coverage") or {}).get("coverage")
        bm_cov = (business_model.get("_citation_coverage") or {}).get("coverage")
        vals = [v for v in (sop_cov, bm_cov) if isinstance(v, (int, float))]
        if not vals:
            return QualityDimension(
                name="方法论采用度",
                score=0,
                weight=0.25,
                feedback="未提供方法论引用（source_ref）",
                details="sop / business_model 均无 _citation_coverage",
            )
        score = int(sum(vals) / len(vals) * 100)
        return QualityDimension(
            name="方法论采用度",
            score=score,
            weight=0.25,
            feedback=f"方法论引用覆盖率 {score}%",
            details=f"引用覆盖率 {score}%（sop/bm 均值）",
        )

    # ---------- 维度 2：约束覆盖率（B）----------
    def _constraint_dimension(self, risk: dict) -> QualityDimension:
        cov = risk.get("coverage") or {}
        pct = cov.get("coverage_pct")
        if not isinstance(pct, (int, float)):
            return QualityDimension(
                name="约束覆盖率",
                score=0,
                weight=0.20,
                feedback="未提供约束覆盖率",
                details="risk.coverage.coverage_pct 缺失",
            )
        score = int(_safe(pct))
        uncovered = cov.get("uncovered_ids") or []
        detail = f"约束覆盖率 {score}%（{cov.get('covered', '?')}/{cov.get('total', '?')}）"
        if uncovered:
            detail += f"，{len(uncovered)} 项未覆盖"
        return QualityDimension(
            name="约束覆盖率",
            score=score,
            weight=0.20,
            feedback=detail,
            details=detail,
        )

    # ---------- 维度 3：风险门禁健康（B）----------
    def _gate_dimension(self, risk: dict) -> QualityDimension:
        gate = risk.get("gate") or {}
        decision = gate.get("decision")
        if decision not in _GATE_SCORE:
            return QualityDimension(
                name="风险门禁健康",
                score=0,
                weight=0.20,
                feedback="未提供风险门禁决策",
                details="risk.gate.decision 缺失",
            )
        score = _GATE_SCORE[decision]
        return QualityDimension(
            name="风险门禁健康",
            score=score,
            weight=0.20,
            feedback=f"门禁决策：{decision}",
            details=f"门禁决策 {decision} -> {score} 分",
        )

    # ---------- 维度 4：审计完整性（E）----------
    def _audit_dimension(self, state: dict, trusted_audit: Optional[dict]) -> QualityDimension:
        if trusted_audit is None:
            trusted_audit = build_trusted_audit(state)
        verified = bool((trusted_audit or {}).get("verified"))
        return QualityDimension(
            name="审计完整性",
            score=100 if verified else 0,
            weight=0.15,
            feedback="SHA-256 审计链校验通过" if verified else "SHA-256 审计链校验失败（可能遭篡改）",
            details=f"审计链 verified={verified}",
        )

    # ---------- 维度 5：结构完整度 ----------
    def _structure_dimension(self, sop: dict, business_model: dict, risk: dict) -> QualityDimension:
        sop_ok = bool((sop.get("sops") or []) or sop.get("sop_steps") or sop.get("steps"))
        bm_segs = business_model.get("flows") or business_model.get("roles") or business_model.get("rules")
        bm_ok = bool(bm_segs)
        risk_ok = bool((risk.get("gate") or risk.get("coverage") or risk.get("risks")))
        filled = [sop_ok, bm_ok, risk_ok]
        count = sum(1 for f in filled if f)
        score = int(count / 3 * 100)
        present = []
        if sop_ok:
            present.append("SOP")
        if bm_ok:
            present.append("业务模型")
        if risk_ok:
            present.append("风险")
        detail = f"产出段完整度 {count}/3：" + ("、".join(present) if present else "均无")
        return QualityDimension(
            name="结构完整度",
            score=score,
            weight=0.20,
            feedback=detail if count == 3 else f"{detail}，缺失段需补全",
            details=detail,
        )

    # ---------- 工具 ----------
    @staticmethod
    def _level(score: float) -> str:
        if score >= 90:
            return "优秀"
        if score >= 80:
            return "良好"
        if score >= 70:
            return "合格"
        if score >= 60:
            return "待改进"
        return "不合格"
