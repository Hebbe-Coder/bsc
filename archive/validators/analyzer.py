"""
Post-Generation Analyzer - insights kept SEPARATE from Business System JSON.

Analyzes a compiled Business System JSON and returns:
  1. complexity_level    - "low" | "medium" | "high"
  2. difficulty_score    - 1-10 with breakdown
  3. missing_roles       - roles present in workflow but missing from modules
  4. optimization_hints  - actionable suggestions

These are advisory insights - NEVER merged into the output JSON.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter


# ============================================================
# STANDARD ROLE CATALOG
# ============================================================

STANDARD_ROLES = {
    "admin": "System Administrator",
    "user": "End User",
    "customer": "Customer",
    "agent": "Support Agent",
    "reviewer": "Content Reviewer",
    "analyst": "Business Analyst",
    "manager": "Team Manager",
    "qa": "Quality Assurance",
    "devops": "DevOps Engineer",
    "developer": "Software Developer",
    "auditor": "Auditor",
    "moderator": "Content Moderator",
    "operator": "System Operator",
    "viewer": "Read-only Viewer",
    "superadmin": "Super Administrator",
    "compliance": "Compliance Officer",
    "risk_analyst": "Risk Analyst",
    "data_scientist": "Data Scientist",
    "product_owner": "Product Owner",
    "scrum_master": "Scrum Master",
}


# ============================================================
# COMPLEXITY SCORING
# ============================================================

def _complexity_breakdown(bs: dict) -> dict:
    """Score each dimension and return breakdown."""
    modules = bs.get("modules", []) or []
    workflow = bs.get("workflow", []) or []
    metrics = bs.get("metrics", []) or []
    risks = bs.get("risk", []) or []

    # Module complexity: count + dependencies
    mod_count = len(modules)
    dep_count = sum(len(m.get("dependencies", [])) for m in modules if isinstance(m, dict))
    mod_score = min(10, (mod_count * 1.5) + (dep_count * 0.5))

    # Workflow complexity: nodes + branches
    wf_count = len(workflow)
    branch_count = sum(len(n.get("conditions", [])) for n in workflow if isinstance(n, dict))
    decision_count = sum(1 for n in workflow if isinstance(n, dict) and n.get("type") == "decision")
    wf_score = min(10, (wf_count * 1.0) + (branch_count * 0.8) + (decision_count * 0.5))

    # Metric complexity: count + variety
    met_count = len(metrics)
    branches = set()
    for m in metrics:
        if isinstance(m, dict) and m.get("branch"):
            branches.add(m["branch"])
    met_score = min(10, (met_count * 0.8) + (len(branches) * 0.5))

    # Risk complexity: count + score sum
    risk_count = len(risks)
    risk_sum = sum(r.get("score", 0) for r in risks if isinstance(r, dict))
    risk_score = min(10, (risk_count * 1.0) + (risk_sum * 0.3))

    total = (mod_score + wf_score + met_score + risk_score) / 4

    if total <= 3.5:
        level = "low"
    elif total <= 6.5:
        level = "medium"
    else:
        level = "high"

    return {
        "level": level,
        "score": round(total, 1),
        "breakdown": {
            "modules": round(mod_score, 1),
            "workflow": round(wf_score, 1),
            "metrics": round(met_score, 1),
            "risk": round(risk_score, 1),
        }
    }


# ============================================================
# DIFFICULTY ESTIMATION
# ============================================================

def _difficulty_breakdown(bs: dict) -> dict:
    """Estimate implementation difficulty from 4 angles."""
    workflow = bs.get("workflow", []) or []
    modules = bs.get("modules", []) or []
    metrics = bs.get("metrics", []) or []
    risks = bs.get("risk", []) or []

    # Integration difficulty: inter-module dependencies
    dep_count = sum(len(m.get("dependencies", [])) for m in modules if isinstance(m, dict))
    integration = min(10, dep_count * 2.5 + 2)

    # Process difficulty: decision points, branching
    decisions = sum(1 for n in workflow if isinstance(n, dict) and n.get("type") == "decision")
    branches = sum(len(n.get("conditions", [])) for n in workflow if isinstance(n, dict))
    process = min(10, 2 + decisions * 1.5 + branches * 0.8)

    # Data difficulty: metrics that need instrumentation
    data = min(10, 1 + len(metrics) * 0.8)

    # Risk difficulty: high-impact risks
    high_risks = sum(1 for r in risks if isinstance(r, dict) and r.get("impact") == "high")
    risk = min(10, 1 + high_risks * 2.0)

    total = (integration + process + data + risk) / 4

    if total <= 3.5:
        tier = "straightforward"
    elif total <= 6.5:
        tier = "moderate"
    else:
        tier = "complex"

    return {
        "score": round(total, 1),
        "tier": tier,
        "breakdown": {
            "integration": round(integration, 1),
            "process": round(process, 1),
            "data": round(data, 1),
            "risk": round(risk, 1),
        },
        "estimated_weeks": _estimate_weeks(total, len(workflow), len(modules)),
    }


def _estimate_weeks(score: float, wf_nodes: int, modules: int) -> dict:
    """Crude week estimate based on difficulty and size."""
    base = 2
    per_node = wf_nodes * 0.3
    per_module = modules * 0.5
    factor = score / 5.0
    weeks = (base + per_node + per_module) * factor

    return {
        "minimum": max(1, round(weeks * 0.7)),
        "likely": max(2, round(weeks)),
        "maximum": max(3, round(weeks * 1.5)),
    }


# ============================================================
# MISSING ROLE DETECTION
# ============================================================

def _find_missing_roles(bs: dict) -> list[dict]:
    """Find roles used in workflow but not defined in modules."""
    workflow = bs.get("workflow", []) or []
    modules = bs.get("modules", []) or []

    # Roles from workflow
    wf_roles = set()
    for n in workflow:
        if isinstance(n, dict) and n.get("owner"):
            wf_roles.add(n["owner"].strip().lower())

    # Roles from modules
    mod_roles = set()
    for m in modules:
        if isinstance(m, dict) and m.get("owner"):
            mod_roles.add(m["owner"].strip().lower())

    # Roles that appear in workflow but NOT in any module
    missing = wf_roles - mod_roles

    if not missing:
        return []

    results = []
    for role in sorted(missing):
        # Find which workflow nodes use this role
        used_in = [
            n.get("name", n.get("id", "?"))
            for n in workflow
            if isinstance(n, dict) and (n.get("owner") or "").strip().lower() == role
        ]
        results.append({
            "role": role,
            "used_in_nodes": used_in[:5],  # max 5 nodes
            "suggestion": f"Define '{role}' as a module owner or add a dedicated module",
        })

    return results


# ============================================================
# OPTIMIZATION SUGGESTIONS
# ============================================================

def _generate_optimizations(bs: dict) -> list[dict]:
    """Generate actionable optimization hints."""
    hints = []

    workflow = bs.get("workflow", []) or []
    metrics = bs.get("metrics", []) or []
    modules = bs.get("modules", []) or []
    risks = bs.get("risk", []) or []

    # Hint 1: Long chains without decision points
    chain_length = 0
    for n in workflow:
        if isinstance(n, dict) and n.get("type") == "action":
            chain_length += 1
        else:
            if chain_length >= 4:
                hints.append({
                    "type": "bottleneck_risk",
                    "detail": f"Long sequential chain of {chain_length} actions without decision gates. "
                              f"Consider adding parallel branches or early-exit conditions.",
                    "severity": "medium" if chain_length >= 6 else "low",
                })
            chain_length = 0

    # Hint 2: Missing metric branches
    present_branches = set()
    for m in metrics:
        if isinstance(m, dict) and m.get("branch"):
            present_branches.add(m["branch"])
    expected = {"Efficiency", "Quality", "Capacity", "Cost", "Risk"}
    missing_branches = expected - present_branches
    if missing_branches:
        hints.append({
            "type": "metric_gap",
            "detail": f"Missing metric coverage for: {', '.join(sorted(missing_branches))}. "
                      f"Add KPIs in these areas for balanced observability.",
            "severity": "medium",
        })

    # Hint 3: Modules without owners
    unowned = [m.get("name", "?") for m in modules if isinstance(m, dict) and m.get("owner") in (None, "unassigned", "")]
    if unowned:
        hints.append({
            "type": "ownership_gap",
            "detail": f"Modules without clear owner: {', '.join(unowned[:3])}. Assign owners for accountability.",
            "severity": "high" if len(unowned) > 2 else "medium",
        })

    # Hint 4: High-risk items without mitigations
    unmitigated = [
        r.get("name", "?") for r in risks
        if isinstance(r, dict)
        and r.get("impact") == "high"
        and (not r.get("mitigation") or (isinstance(r.get("mitigation"), dict) and not r["mitigation"].get("action")))
    ]
    if unmitigated:
        hints.append({
            "type": "unmitigated_risk",
            "detail": f"High-impact risks without concrete mitigation: {', '.join(unmitigated[:3])}",
            "severity": "high",
        })

    # Hint 5: SLA coverage
    nodes_with_sla = sum(1 for n in workflow if isinstance(n, dict) and n.get("sla_hours") is not None)
    if nodes_with_sla == 0 and len(workflow) > 2:
        hints.append({
            "type": "sla_gap",
            "detail": "No SLA targets defined on workflow nodes. Add SLA for accountability.",
            "severity": "medium",
        })
    elif nodes_with_sla < len(workflow) * 0.5 and len(workflow) > 3:
        hints.append({
            "type": "sla_partial",
            "detail": f"Only {nodes_with_sla}/{len(workflow)} nodes have SLA. Consider broader coverage.",
            "severity": "low",
        })

    # Hint 6: Entry/exit points
    starts = sum(1 for n in workflow if isinstance(n, dict) and n.get("type") == "start")
    ends = sum(1 for n in workflow if isinstance(n, dict) and n.get("type") == "end")
    if starts > 1:
        hints.append({
            "type": "multiple_starts",
            "detail": f"Multiple start nodes ({starts}). Consider consolidating entry points for clarity.",
            "severity": "low",
        })

    return hints


# ============================================================
# MAIN ANALYZER
# ============================================================

@dataclass
class AnalysisReport:
    complexity: dict
    difficulty: dict
    missing_roles: list[dict]
    optimizations: list[dict]

    def to_dict(self) -> dict:
        return {
            "complexity": self.complexity,
            "difficulty": self.difficulty,
            "missing_roles": self.missing_roles,
            "optimizations": self.optimizations,
        }


def analyze(business_system: dict) -> AnalysisReport:
    """
    Analyze a compiled Business System JSON.
    Returns insights SEPARATE from the data - never merged.
    """
    bs = business_system.get("business_system", business_system)

    return AnalysisReport(
        complexity=_complexity_breakdown(bs),
        difficulty=_difficulty_breakdown(bs),
        missing_roles=_find_missing_roles(bs),
        optimizations=_generate_optimizations(bs),
    )


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    import json

    # Sample compiled data (from mock compiler)
    sample = {
        "modules": [
            {"id": "ingest", "name": "Content Ingestion", "description": "Accepts content via API", "owner": "Platform Team", "priority": "high"},
            {"id": "screen", "name": "AI Screening", "description": "Automated review", "owner": "ML Team", "priority": "critical"},
            {"id": "review", "name": "Human Review", "description": "Manual review queue", "owner": "Operations", "priority": "high",
             "dependencies": [{"module_name": "screen", "type": "process"}]},
            {"id": "analytics", "name": "Analytics", "description": "Dashboards", "owner": "", "priority": "medium"},
        ],
        "workflow": [
            {"id": "submit", "name": "Submit", "type": "start", "owner": "Content Creator", "next_node_id": "screen"},
            {"id": "screen", "name": "AI Screen", "type": "action", "owner": "AI System", "next_node_id": "classify"},
            {"id": "classify", "name": "Classify Risk", "type": "decision", "owner": "AI System",
             "conditions": [{"condition": "high", "next_node_id": "review"}, {"condition": "low", "next_node_id": "publish"}]},
            {"id": "review", "name": "Human Review", "type": "action", "owner": "Human Reviewer", "next_node_id": "decide", "sla_hours": 24},
            {"id": "decide", "name": "Review Decision", "type": "decision", "owner": "Human Reviewer",
             "conditions": [{"condition": "approve", "next_node_id": "publish"}, {"condition": "reject", "next_node_id": "notify"}]},
            {"id": "publish", "name": "Publish", "type": "end", "owner": "System"},
            {"id": "notify", "name": "Notify Rejection", "type": "end", "owner": "System"},
        ],
        "metrics": [
            {"name": "Throughput", "formula": "processed/day", "target": ">4000", "branch": "Efficiency"},
            {"name": "Accuracy", "formula": "correct/total", "target": ">99%", "branch": "Quality"},
            {"name": "Queue Length", "formula": "count(pending)", "target": "<200", "branch": "Capacity"},
        ],
        "risk": [
            {"name": "False Negatives", "impact": "high", "score": 6, "mitigation": {"action": "Regular model retraining"}},
            {"name": "Reviewer Burnout", "impact": "medium", "score": 4, "mitigation": {}},
            {"name": "Peak Overload", "impact": "high", "score": 3},
        ],
    }

    report = analyze(sample)

    print("=" * 50)
    print("COMPLEXITY")
    print("  Level:", report.complexity["level"])
    print("  Score:", report.complexity["score"])
    print("  Breakdown:", report.complexity["breakdown"])

    print("\nDIFFICULTY")
    print("  Tier:", report.difficulty["tier"])
    print("  Score:", report.difficulty["score"])
    print("  Breakdown:", report.difficulty["breakdown"])
    print("  Estimated weeks:", report.difficulty["estimated_weeks"])

    print("\nMISSING ROLES")
    for r in report.missing_roles:
        print(f"  - {r['role']}: used in {r['used_in_nodes']}")

    print("\nOPTIMIZATIONS")
    for h in report.optimizations:
        print(f"  [{h['severity']}] {h['type']}: {h['detail'][:80]}...")

    # Verify output is separate - no business_system key
    d = report.to_dict()
    assert "business_system" not in d, "Analysis leaked into business_system!"
    assert "modules" not in d, "Analysis leaked modules!"
    print("\nVERIFIED: Analysis output is SEPARATE from business_system JSON.")
