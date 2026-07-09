"""导出层单一规范化模型：所有渲染器只消费 CanonicalReport。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

SEVERITY_LABELS = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}
PRIORITY_LABELS = {"high": "🔴", "medium": "🟡", "low": "🟢"}

_SEV_MAP = {
    "high": "high", "h": "high", "高": "high", "🔴": "high", "high risk": "high",
    "medium": "medium", "m": "medium", "中": "medium", "🟡": "medium", "medium risk": "medium",
    "low": "low", "l": "low", "低": "low", "🟢": "low", "low risk": "low",
}


@dataclass
class CanonicalObjective:
    objective: str = ""
    target: str = ""
    priority: str = "medium"
    priority_label: str = PRIORITY_LABELS["medium"]


@dataclass
class CanonicalRole:
    role: str = ""
    department: str = ""
    level: str = ""
    headcount: str = ""


@dataclass
class CanonicalStep:
    step: object = ""
    name: str = ""
    action: str = ""
    role: str = ""


@dataclass
class CanonicalMetric:
    name: str = ""
    formula: str = ""
    target: str = ""


@dataclass
class CanonicalRisk:
    risk: str = ""
    severity: str = "medium"
    severity_label: str = SEVERITY_LABELS["medium"]
    mitigation: str = ""
    impact: str = ""
    category: Optional[str] = None


@dataclass
class CanonicalStrategy:
    recommendations: List[str] = field(default_factory=list)
    growth_opportunities: List[dict] = field(default_factory=list)
    roadmap: List[str] = field(default_factory=list)


@dataclass
class CanonicalReport:
    title: str = ""
    executive_summary: str = ""
    generated_at: str = ""
    objectives: List[CanonicalObjective] = field(default_factory=list)
    roles: List[CanonicalRole] = field(default_factory=list)
    workflow: List[CanonicalStep] = field(default_factory=list)
    metrics: List[CanonicalMetric] = field(default_factory=list)
    risks: List[CanonicalRisk] = field(default_factory=list)
    strategy: CanonicalStrategy = field(default_factory=CanonicalStrategy)


def _norm_level(raw) -> str:
    if raw is None:
        return "medium"
    return _SEV_MAP.get(str(raw).strip().lower(), "medium")


def _norm_severity(raw) -> tuple:
    sev = _norm_level(raw)
    return sev, SEVERITY_LABELS[sev]


def _norm_risks(bs: dict) -> List[CanonicalRisk]:
    risks = bs.get("risks") or []
    if not risks and isinstance(bs.get("risk"), list):
        risks = bs.get("risk")
    out = []
    if risks:
        for r in risks:
            if not isinstance(r, dict):
                continue
            sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
            out.append(CanonicalRisk(
                risk=str(r.get("risk", r.get("description", r.get("name", "")))),
                severity=sev, severity_label=label,
                mitigation=str(r.get("mitigation", r.get("response", r.get("action", "")))),
                impact=str(r.get("impact", r.get("consequence", ""))),
                category=r.get("category"),
            ))
        return out
    nested = bs.get("risk", {})
    if isinstance(nested, dict):
        for cat, items in nested.items():
            if not isinstance(items, list):
                continue
            cat_name = cat.replace("_risks", "").replace("_", " ")
            for r in items:
                if not isinstance(r, dict):
                    continue
                sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
                out.append(CanonicalRisk(
                    risk=str(r.get("risk", r.get("description", r.get("name", "")))),
                    severity=sev, severity_label=label,
                    mitigation=str(r.get("mitigation", "")),
                    impact=str(r.get("impact", "")),
                    category=cat_name,
                ))
    return out


def _norm_metrics(bs: dict) -> List[CanonicalMetric]:
    raw = bs.get("metrics") or bs.get("kpi") or bs.get("success_metrics") or []
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        out.append(CanonicalMetric(
            name=str(m.get("name", m.get("kpi", ""))),
            formula=str(m.get("formula", m.get("expression", ""))),
            target=str(m.get("target", m.get("goal", ""))),
        ))
    return out


def _norm_workflow(bs: dict) -> List[CanonicalStep]:
    raw = bs.get("workflow") or bs.get("process_flow") or bs.get("sop") or []
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            continue
        out.append(CanonicalStep(
            step=s.get("step", i),
            name=str(s.get("name", "")),
            action=str(s.get("action", "")),
            role=str(s.get("role", "")),
        ))
    return out


def _norm_objectives(bs: dict) -> List[CanonicalObjective]:
    raw = bs.get("objectives") or bs.get("core_objectives") or []
    out = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        sev, label = _norm_severity(o.get("priority", "medium"))
        out.append(CanonicalObjective(
            objective=str(o.get("objective", "")),
            target=str(o.get("target", "")),
            priority=sev, priority_label=label,
        ))
    return out


def _norm_roles(bs: dict) -> List[CanonicalRole]:
    raw = bs.get("roles") or (bs.get("sop", {}) or {}).get("roles") or []
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        out.append(CanonicalRole(
            role=str(r.get("role", "")),
            department=str(r.get("department", "")),
            level=str(r.get("level", "")),
            headcount=str(r.get("headcount", "")),
        ))
    return out


def _norm_strategy(bs: dict) -> CanonicalStrategy:
    raw = bs.get("strategy") or {}
    if not isinstance(raw, dict):
        raw = {}
    recs = raw.get("recommendations") or []
    growth = raw.get("growth_opportunities") or []
    roadmap = raw.get("strategic_path") or raw.get("milestones") or []
    return CanonicalStrategy(
        recommendations=[str(x) for x in recs],
        growth_opportunities=[
            {"opportunity": str(g.get("opportunity", "")), "potential": str(g.get("potential", ""))}
            for g in growth if isinstance(g, dict)
        ],
        roadmap=[str(x) for x in roadmap],
    )


def normalize(business_system: dict) -> CanonicalReport:
    bs = business_system or {}
    report = bs.get("report")
    exec_sum = ""
    if isinstance(report, dict):
        exec_sum = str(report.get("executive_summary", ""))
    return CanonicalReport(
        title=str(bs.get("business_domain", bs.get("objective", "业务系统分析报告"))),
        executive_summary=exec_sum,
        generated_at=str(bs.get("generated_at", "")),
        objectives=_norm_objectives(bs),
        roles=_norm_roles(bs),
        workflow=_norm_workflow(bs),
        metrics=_norm_metrics(bs),
        risks=_norm_risks(bs),
        strategy=_norm_strategy(bs),
    )
