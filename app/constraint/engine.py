from __future__ import annotations
from typing import Optional
from app.constraint.models import (Constraint, ConstraintResult, CoverageReport,
                                    ElementCoverage, GateDecision)
from app.constraint.audit import AuditChain

HIGH = {"high"}


def build_constraints(requirements: list) -> list[Constraint]:
    out = []
    for r in (requirements or []):
        if isinstance(r, dict):
            out.append(Constraint(id=r.get("id", ""), text=r.get("text", ""),
                                  priority=r.get("priority", "mid"),
                                  source=r.get("source", "")))
    return out


def _elements(bm: dict) -> list[tuple]:
    els = []
    for f in bm.get("flows", []) or []:
        els.append(("flow", str(f.get("id", "")), f.get("name", ""),
                    f.get("covers_constraints", []) or []))
    for r in bm.get("roles", []) or []:
        if isinstance(r, dict):
            els.append(("role", str(r.get("id", "")), r.get("name", ""),
                        r.get("covers_constraints", []) or []))
    for ru in bm.get("rules", []) or []:
        if isinstance(ru, dict):
            els.append(("rule", str(ru.get("id", "")), ru.get("statement", ""),
                        ru.get("covers_constraints", []) or []))
    return els


def evaluate(business_model: dict, sop: Optional[dict] = None,
             requirements: Optional[list] = None,
             risk_payload: Optional[dict] = None) -> ConstraintResult:
    bm = business_model or {}
    constraints = build_constraints(requirements)
    sop = sop or {}
    sop_covers = set()
    for s in sop.get("sops", []) or []:
        for cid in (s.get("covers_constraints", []) or []):
            sop_covers.add(cid)

    elements = _elements(bm)
    constraint_ids = {constraint.id for constraint in constraints if constraint.id}
    referenced: set[str] = set()
    ecov: list[ElementCoverage] = []
    uncovered_elements: list[str] = []
    for (etype, eid, ename, explicit_covers) in elements:
        low_id, low_name = eid.lower(), ename.lower()
        governed = [c.id for c in constraints
                    if c.id and (c.id in low_id or c.id in low_name)]
        for cid in explicit_covers:
            if cid in constraint_ids and cid not in governed:
                governed.append(cid)
        covered = bool(governed)
        referenced.update(governed)
        ecov.append(ElementCoverage(element_type=etype, element_id=eid,
                                     element_name=ename, governed_by=governed,
                                     covered=covered))
        if not covered:
            uncovered_elements.append(f"{etype}:{eid or ename}")

    # 约束满足度（驱动 coverage_pct 与门禁）：被某元素引用 或 被 SOP 显式覆盖
    satisfied = referenced | sop_covers
    unsatisfied = [c for c in constraints if c.id and c.id not in satisfied]
    unsatisfied_high = [c for c in unsatisfied if c.priority in HIGH]

    total_req = len(constraints)
    satisfied_n = total_req - len(unsatisfied)
    cov_pct = round(satisfied_n / total_req * 100) if total_req else 100

    reasons: list[str] = []
    decision = "pass"
    if unsatisfied:
        reasons.append(f"{len(unsatisfied)} 个约束未被任何业务元素满足")
        decision = "warn"
    if unsatisfied_high:
        decision = "block"
        reasons.append("存在高危优先级约束未被满足")
    rp = risk_payload or {}
    risk_score = rp.get("overall_score", "low")
    risks = rp.get("risks", [])
    if risk_score == "high":
        decision = "block"
        reasons.append("风险评估为 high")
    elif risk_score == "medium" and decision == "pass":
        decision = "warn"

    chain = AuditChain()
    chain.append("constraint_engine", "coverage_check",
                 {"input": {"elements": len(ecov), "constraints": total_req},
                  "output": {"coverage_pct": cov_pct,
                             "uncovered_elements": uncovered_elements,
                             "unsatisfied": [c.id for c in unsatisfied]}})
    chain.append("constraint_engine", "gate_decision",
                 {"input": {"coverage_pct": cov_pct, "risk_score": risk_score},
                  "output": {"decision": decision}})

    return ConstraintResult(
        overall_score=risk_score,
        risks=risks,
        coverage=CoverageReport(elements=ecov, total=total_req, covered=satisfied_n,
                                coverage_pct=cov_pct,
                                uncovered_ids=[c.id for c in unsatisfied]),
        gate=GateDecision(decision=decision, reasons=reasons),
        audit=chain.entries,
    )
