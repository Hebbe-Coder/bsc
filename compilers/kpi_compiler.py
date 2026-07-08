"""KPI Compiler: Business System JSON -> KPI Tree with repair loop."""
from compilers.llm_service import chat_json as _llm
from validators import validate
import uuid, json as _json

PROMPT = """You are a KPI Compiler. Convert a Business System JSON into a KPI tree with metrics.

OUTPUT ONLY valid JSON:
{
  "kpi_id": "generated-id",
  "tree": {
    "name": "Business Health",
    "branches": [
      {"name": "Efficiency", "weight": 0.25},
      {"name": "Quality", "weight": 0.25},
      {"name": "Capacity", "weight": 0.20},
      {"name": "Cost", "weight": 0.15},
      {"name": "Risk", "weight": 0.15}
    ]
  },
  "metrics": [
    {
      "id": "M1",
      "name": "Throughput",
      "description": "Items processed per day",
      "formula": "total_processed / days",
      "unit": "items/day",
      "target": "> 500",
      "warning": "< 400",
      "critical": "< 300",
      "branch": "Efficiency",
      "direction": "higher_better"
    }
  ],
  "alerts": [
    {"condition": "throughput < 300 for 2h", "severity": "critical", "message": "Processing backlog critical"}
  ],
  "health_formula": "weighted_avg(efficiency * 0.25 + quality * 0.25 + capacity * 0.20 - cost_penalty * 0.15 - risk_penalty * 0.15)"
}
RULES:
- 5 branches: Efficiency, Quality, Capacity, Cost, Risk (weights sum to 1.0)
- At least 8 metrics spread across branches
- At least 3 alerts with condition+severity+message
- Each metric must have: id, name, formula, target, branch
- health_formula must reference all 5 branches
NO MARKDOWN. JSON ONLY."""

def compile_kpi(structure: dict) -> dict:
    """Business System JSON -> KPI Tree. Auto-repairs on validation failure."""
    kpi_id = str(uuid.uuid4())[:12]
    input_text = _json.dumps(structure, ensure_ascii=False)
    max_repairs = 2
    for repair_attempt in range(max_repairs + 1):
        result = _llm(PROMPT, input_text[:8000], temperature=0.1)
        if result.get("fallback"):
            return _fallback(structure, kpi_id)
        result["kpi_id"] = kpi_id
        is_valid, issues, repaired = validate(result, "kpi.json")
        if is_valid:
            return repaired
        if repair_attempt < max_repairs:
            input_text = input_text + "\n\n[REPAIR] Fix: " + ", ".join(issues[:5])
    return repaired if repaired else _fallback(structure, kpi_id)

def _fallback(structure: dict, kid: str) -> dict:
    return {
        "kpi_id": kid,
        "tree": {
            "name": "Business Health",
            "branches": [
                {"name": "Efficiency", "weight": 0.25},
                {"name": "Quality", "weight": 0.25},
                {"name": "Capacity", "weight": 0.20},
                {"name": "Cost", "weight": 0.15},
                {"name": "Risk", "weight": 0.15}
            ]
        },
        "metrics": [
            {"id":"M1","name":"Throughput","description":"Items processed per day","formula":"total_processed/days","unit":"items/day","target":"> 500","warning":"< 400","critical":"< 300","branch":"Efficiency","direction":"higher_better"},
            {"id":"M2","name":"Avg Handling Time","description":"Average time per item","formula":"total_time/total_items","unit":"minutes","target":"< 5","warning":"> 8","critical":"> 12","branch":"Efficiency","direction":"lower_better"},
            {"id":"M3","name":"Accuracy Rate","description":"Correct decisions ratio","formula":"correct/total","unit":"%","target":"> 99","warning":"< 97","critical":"< 95","branch":"Quality","direction":"higher_better"},
            {"id":"M4","name":"Error Rate","description":"Incorrect decisions ratio","formula":"errors/total","unit":"%","target":"< 1","warning":"> 2","critical":"> 3","branch":"Quality","direction":"lower_better"},
            {"id":"M5","name":"Queue Length","description":"Pending items in queue","formula":"pending_count","unit":"items","target":"< 100","warning":"> 200","critical":"> 500","branch":"Capacity","direction":"lower_better"},
            {"id":"M6","name":"Utilization Rate","description":"Resource usage ratio","formula":"busy_time/total_time","unit":"%","target":"70-85","warning":"> 90","critical":"> 95","branch":"Capacity","direction":"optimal_range"},
            {"id":"M7","name":"Cost Per Item","description":"Average cost per processed item","formula":"total_cost/total_items","unit":"CNY","target":"< 2","warning":"> 3","critical":"> 5","branch":"Cost","direction":"lower_better"},
            {"id":"M8","name":"SLA Compliance","description":"SLA met percentage","formula":"sla_met/total","unit":"%","target":"> 99.5","warning":"< 98","critical":"< 95","branch":"Risk","direction":"higher_better"}
        ],
        "alerts": [
            {"condition":"throughput < 300 && queue > 200","severity":"critical","message":"Processing bottleneck - escalate immediately"},
            {"condition":"accuracy < 97% for 1h","severity":"warning","message":"Quality drop detected - review recent decisions"},
            {"condition":"sla_compliance < 95%","severity":"critical","message":"SLA breach risk - allocate additional resources"}
        ],
        "health_formula": "weighted_avg(efficiency*0.25 + quality*0.25 + capacity*0.20 - cost_penalty*0.15 - risk_penalty*0.15)"
    }
