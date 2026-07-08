"""Risk Agent — identifies and assesses business risks."""
from .protocol import BaseAgent, AgentContext
import logging

logger = logging.getLogger("bsc.studio.risk")

RISK_CATEGORIES = {
    "operational": ["process", "workflow", "throughput", "backlog", "delay", "bottleneck"],
    "quality": ["accuracy", "error", "precision", "false positive", "false negative"],
    "compliance": ["regulation", "gdpr", "compliance", "legal", "audit", "privacy"],
    "resource": ["staffing", "turnover", "training", "fatigue", "burnout", "capacity"],
    "technical": ["downtime", "latency", "scalability", "integration", "api", "security"],
}

SEVERITY_KEYWORDS = {
    "critical": ["fail", "crash", "breach", "loss", "block", "denial"],
    "high": ["delay", "error", "miss", "overload", "backlog", "downtime"],
    "medium": ["slow", "inefficient", "limited", "risk", "concern"],
    "low": ["minor", "small", "rare", "occasional"],
}

IMPACT_LEVELS = {"critical": 5, "high": 4, "medium": 3, "low": 2, "minimal": 1}


class RiskAgent(BaseAgent):
    name = "risk"
    description = "Identifies and assesses business risks across operational, quality, compliance, resource, and technical dimensions"
    capabilities = ["analyze", "assess", "risk"]

    def on_analyze(self, ctx: AgentContext, **params) -> dict:
        """
        Analyze business risks from the business system context.
        
        Args:
            ctx: AgentContext containing business_system data
            params: Additional parameters with business_system as fallback
        
        Returns:
            dict: Risk analysis results with detected risks, summary stats, and affected categories
        """
        if ctx is None:
            return {
                "risks": [],
                "summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
                "categories_affected": [],
            }

        bs = ctx.business_system or params.get("business_system", {})
        processes = bs.get("processes", [])
        metrics = bs.get("metrics", [])
        risks_input = bs.get("risks", [])
        objectives = bs.get("objectives", [])

        all_risks = []

        text_input = self._build_text_input(processes, metrics, risks_input, objectives)

        for category, keywords in RISK_CATEGORIES.items():
            matched = [kw for kw in keywords if kw in text_input]
            if matched:
                severity = self._calculate_severity(category, matched, text_input)
                risk_count = len(matched)
                all_risks.append({
                    "name": f"{category.title()} Risk: {', '.join(matched[:3])}",
                    "category": category,
                    "severity": severity,
                    "impact_score": IMPACT_LEVELS.get(severity, 3),
                    "affected_processes": [p.get("name", "")[:40] for p in processes[:3] if isinstance(p, dict)],
                    "mitigation": self._generate_mitigation(category, severity),
                    "source": "detected",
                    "detection_confidence": min(risk_count * 0.2, 0.9),
                })

        for r in risks_input[:5]:
            name = r.get("name", "") if isinstance(r, dict) else str(r)
            if name:
                severity = r.get("severity", self._infer_severity_from_name(name))
                all_risks.append({
                    "name": name[:100],
                    "category": r.get("category", "operational"),
                    "severity": severity,
                    "impact_score": IMPACT_LEVELS.get(severity, 3),
                    "affected_processes": [],
                    "mitigation": r.get("mitigation", ""),
                    "source": "input",
                    "detection_confidence": 1.0,
                })

        if not all_risks:
            all_risks = self._generate_default_risks(processes)

        high = sum(1 for r in all_risks if r["severity"] in ("critical", "high"))
        medium = sum(1 for r in all_risks if r["severity"] == "medium")

        return {
            "risks": all_risks,
            "summary": {
                "total": len(all_risks),
                "critical": sum(1 for r in all_risks if r["severity"] == "critical"),
                "high": sum(1 for r in all_risks if r["severity"] == "high"),
                "medium": medium,
                "low": len(all_risks) - high - medium,
            },
            "categories_affected": list(set(r["category"] for r in all_risks)),
        }

    def _build_text_input(self, processes, metrics, risks_input, objectives):
        """Build combined text input for risk detection (single pass)."""
        text_parts = []
        
        for p in processes:
            if isinstance(p, dict):
                text_parts.append(str(p.get("name", "")))
                text_parts.append(str(p.get("action", "")))
            else:
                text_parts.append(str(p))
        
        for m in metrics:
            if isinstance(m, dict):
                text_parts.append(str(m.get("name", "")))
                text_parts.append(str(m.get("target", "")))
            else:
                text_parts.append(str(m))
        
        for r in risks_input:
            if isinstance(r, dict):
                text_parts.append(str(r.get("name", "")))
            else:
                text_parts.append(str(r))
        
        for o in objectives:
            if isinstance(o, dict):
                text_parts.append(str(o.get("name", "")))
                text_parts.append(str(o.get("target", "")))
            else:
                text_parts.append(str(o))
        
        return " ".join(text_parts).lower()

    def _calculate_severity(self, category, matched_keywords, text_input):
        """Calculate severity based on category, matched keywords, and text context."""
        base_severity = {
            "compliance": "high",
            "technical": "medium",
            "operational": "medium",
            "quality": "medium",
            "resource": "low",
        }.get(category, "medium")

        for severity_level, keywords in SEVERITY_KEYWORDS.items():
            if any(kw in text_input for kw in keywords):
                if IMPACT_LEVELS.get(severity_level, 0) > IMPACT_LEVELS.get(base_severity, 0):
                    return severity_level

        if len(matched_keywords) >= 3:
            return "high" if base_severity == "medium" else "critical"

        return base_severity

    def _infer_severity_from_name(self, name):
        """Infer severity from risk name using keyword matching."""
        name_lower = str(name).lower()
        for severity, keywords in SEVERITY_KEYWORDS.items():
            if any(kw in name_lower for kw in keywords):
                return severity
        return "medium"

    def _generate_mitigation(self, category, severity):
        """Generate context-aware mitigation strategies."""
        mitigations = {
            "operational": {
                "high": "Implement monitoring dashboards and automated alerts; add redundant capacity",
                "medium": "Establish performance baselines and implement trend analysis",
                "low": "Document current state and schedule periodic reviews",
            },
            "compliance": {
                "high": "Engage legal counsel; implement automated compliance scanning; establish audit trail",
                "medium": "Conduct gap analysis; implement policy controls",
                "low": "Review current compliance posture; schedule training",
            },
            "technical": {
                "high": "Implement redundancy; conduct load testing; establish disaster recovery",
                "medium": "Monitor system health; implement failover mechanisms",
                "low": "Document architecture; schedule performance reviews",
            },
            "quality": {
                "high": "Implement automated testing; establish quality gates; conduct root cause analysis",
                "medium": "Implement sampling inspection; establish quality metrics",
                "low": "Conduct periodic quality audits; document findings",
            },
            "resource": {
                "high": "Develop contingency staffing plan; implement cross-training; review workload distribution",
                "medium": "Monitor workload levels; plan capacity expansion",
                "low": "Conduct resource utilization analysis; document gaps",
            },
        }
        return mitigations.get(category, {}).get(severity, f"Implement {category} monitoring and controls")

    def _generate_default_risks(self, processes):
        """Generate default risks based on process complexity."""
        default_risks = []
        process_count = len(processes)
        
        if process_count == 0:
            default_risks.append({
                "name": "Unknown process landscape",
                "category": "operational",
                "severity": "medium",
                "impact_score": 3,
                "affected_processes": [],
                "mitigation": "Map current processes and establish baseline",
                "source": "inferred",
                "detection_confidence": 0.5,
            })
        elif process_count > 5:
            default_risks.append({
                "name": "Process complexity risk",
                "category": "operational",
                "severity": "medium",
                "impact_score": 3,
                "affected_processes": [],
                "mitigation": "Simplify or parallelize complex process chains",
                "source": "inferred",
                "detection_confidence": 0.7,
            })
        
        return default_risks
