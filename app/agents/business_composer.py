"""Business Composer — synthesizes all agent outputs into a unified workspace."""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger("bsc.studio.composer")

@dataclass
class Workspace:
    """Unified business workspace — the final output of BSC Studio."""
    business_model: dict = field(default_factory=dict)
    sop: dict = field(default_factory=dict)
    risks: dict = field(default_factory=dict)
    strategy: dict = field(default_factory=dict)
    optimization: dict = field(default_factory=dict)
    dashboard: dict = field(default_factory=dict)
    summary: str = ""
    health_score: int = 0

    def to_dict(self) -> dict:
        return {
            "business_model": self.business_model,
            "sop": self.sop,
            "risks": self.risks,
            "strategy": self.strategy,
            "optimization": self.optimization,
            "dashboard": self.dashboard,
            "summary": self.summary,
            "health_score": self.health_score,
        }

class BusinessComposer:
    """Synthesizes outputs from all specialized agents into a unified workspace."""

    def compose(self, business_model: dict, sop_output: dict, risk_output: dict,
                strategy_output: dict, optimization_output: dict, domain: str = "general") -> Workspace:
        ws = Workspace(business_model=business_model, sop=sop_output, risks=risk_output, strategy=strategy_output, optimization=optimization_output)

        # Compute dashboard
        ws.dashboard = self._build_dashboard(business_model, sop_output, risk_output, optimization_output)

        # Compute health score
        ws.health_score = self._compute_health(business_model, risk_output, optimization_output)

        # Generate summary
        ws.summary = self._generate_summary(business_model, sop_output, risk_output, strategy_output, optimization_output, domain)

        return ws

    def _build_dashboard(self, bm, sop, risk, opt):
        processes = bm.get("processes", [])
        metrics = bm.get("metrics", [])
        sop_steps = sop.get("sop", [])
        risks = risk.get("risks", [])
        bottlenecks = opt.get("bottlenecks", [])

        return {
            "overview": {
                "processes": len(processes),
                "sop_steps": len(sop_steps),
                "risks_identified": risk.get("summary", {}).get("total", len(risks)),
                "bottlenecks": len(bottlenecks),
                "automation_rate": opt.get("automation_potential", {}).get("automation_rate", 0),
            },
            "kpi_cards": _build_kpi_cards(metrics),
            "risk_summary": _build_risk_cards(risks),
            "bottleneck_list": [{"step": b.get("step", ""), "name": b.get("name", ""), "fix": b.get("suggestion", "")} for b in bottlenecks[:5]],
        }

    def _compute_health(self, bm, risk, opt):
        score = 80  # base
        # Penalties
        risk_count = risk.get("summary", {}).get("total", 0)
        high_risks = risk.get("summary", {}).get("high", 0)
        bottlenecks = len(opt.get("bottlenecks", []))
        score -= min(risk_count * 3, 20)
        score -= min(high_risks * 5, 15)
        score -= min(bottlenecks * 3, 10)
        # Bonus
        auto_rate = opt.get("automation_potential", {}).get("automation_rate", 0)
        score += int(auto_rate * 10)
        return max(0, min(100, score))

    def _generate_summary(self, bm, sop, risk, strategy, opt, domain):
        objectives = bm.get("objectives", [])
        processes = bm.get("processes", [])
        risk_summary = risk.get("summary", {})
        recs = strategy.get("recommendations", [])

        parts = []
        if objectives:
            parts.append(f"Analyzed {len(objectives)} business objectives in {domain} domain")
        parts.append(f"Designed {sop.get('total_steps', len(processes))}-step SOP workflow")
        if risk_summary:
            parts.append(f"Identified {risk_summary.get('total',0)} risks ({risk_summary.get('high',0)} high-priority)")
        if recs:
            parts.append(f"Generated {len(recs)} strategic recommendations")
        return " | ".join(parts) if parts else "Business analysis complete"

def _build_kpi_cards(metrics):
    cards = []
    for m in metrics[:6]:
        name = m.get("name", "") if isinstance(m, dict) else str(m)
        target = m.get("target", "—") if isinstance(m, dict) else "—"
        cards.append({"name": str(name)[:40], "value": str(target)[:20], "trend": "stable"})
    return cards

def _build_risk_cards(risks):
    return [{"name": r.get("name", "")[:60], "severity": r.get("severity", "medium"), "category": r.get("category", "operational")} for r in risks[:6]]
