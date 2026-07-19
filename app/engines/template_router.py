"""Keyword-based template classifier. No LLM dependency."""
from typing import Optional
from dataclasses import dataclass

@dataclass
class TemplateMatch:
    template_type: str
    display_name: str
    confidence: float
    slide_structure: list[str]
    matched_keywords: list[str]

TEMPLATES = {
    "bid_proposal": {
        "keywords": ["bid", "rfp", "rfq", "proposal", "bidding", "tender", "procurement",
                     "solicitation", "offer", "submission", "bidding", "tender"],
        "display": "Bid Proposal",
        "slides": ["cover", "executive_summary", "problem_statement", "solution_overview",
                   "technical_architecture", "implementation_plan", "team_structure", "pricing", "case_studies"],
    },
    "operations_report": {
        "keywords": ["report", "metrics", "kpi", "operations", "ops", "dashboard",
                     "performance", "monthly", "quarterly", "annual", "review"],
        "display": "Operations Report",
        "slides": ["cover", "executive_summary", "health_overview", "kpi_dashboard",
                   "bottleneck_analysis", "risk_matrix", "recommendations"],
    },
    "sop_design": {
        "keywords": ["sop", "workflow", "process", "standard", "procedure", "playbook", "runbook", "flowchart"],
        "display": "SOP Design",
        "slides": ["cover", "process_overview", "swimlane_flow", "roles_responsibilities",
                   "sla_definition", "escalation_paths", "quality_gates"],
    },
    "strategy_deck": {
        "keywords": ["strategy", "transformation", "roadmap", "vision", "digital",
                     "innovation", "future", "planning"],
        "display": "Strategy Deck",
        "slides": ["cover", "executive_summary", "current_state", "target_state",
                   "gap_analysis", "strategy_initiatives", "execution_plan", "success_metrics"],
    },
}

def classify_template(text: str) -> TemplateMatch:
    if not text or not isinstance(text, str):
        return TemplateMatch(template_type="operations_report", display_name="Operations Report", confidence=0.0, slide_structure=TEMPLATES["operations_report"]["slides"], matched_keywords=[])
    text_lower = text.lower()
    best_type = "operations_report"
    best_score = 0
    best_keywords = []
    for ttype, config in TEMPLATES.items():
        matched = [kw for kw in config["keywords"] if kw in text_lower]
        if len(matched) > best_score:
            best_score = len(matched)
            best_type = ttype
            best_keywords = matched
    confidence = min(best_score / 4.0, 1.0)
    config = TEMPLATES[best_type]
    return TemplateMatch(
        template_type=best_type,
        display_name=config["display"],
        confidence=round(confidence, 2),
        slide_structure=config["slides"],
        matched_keywords=best_keywords,
    )

def get_template_info(template_type: str) -> Optional[dict]:
    return TEMPLATES.get(template_type)

