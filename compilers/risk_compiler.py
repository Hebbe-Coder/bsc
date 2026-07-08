"""Risk Compiler: Business System JSON -> Risk Analysis with repair loop."""
from compilers.llm_service import chat_json as _llm
from validators import validate
import uuid, json as _json

PROMPT = """You are a Risk Compiler. Convert a Business System JSON into a risk analysis.

OUTPUT ONLY valid JSON:
{
  "risk_id": "generated-id",
  "risk_matrix": [
    {
      "id": "R1",
      "risk": "Data validation failure",
      "category": "operational",
      "probability": "medium",
      "impact": "high",
      "score": 6,
      "trigger": "Invalid input received",
      "owner": "System Admin"
    }
  ],
  "bottlenecks": [
    {"node": "Manual Review", "cause": "Limited reviewers", "impact": "Queue builds up", "severity": "high"}
  ],
  "mitigations": [
    {"risk_id": "R1", "action": "Add input validation layer", "owner": "Dev Team", "priority": "high", "cost_estimate": "2 weeks dev", "timeline": "Q2"}
  ],
  "optimizations": [
    {"id": "O1", "suggestion": "Auto-approve low-risk items", "expected_impact": "Reduce manual load by 40%", "effort": "medium", "category": "efficiency"}
  ]
}
RULES:
- At least 3 risk items in risk_matrix
- Score = probability_weight * impact_weight (high=3, medium=2, low=1)
- At least 2 bottlenecks
- At least 1 mitigation per risk
- At least 2 optimizations
- Every mitigation must reference a risk_id
NO MARKDOWN. JSON ONLY."""

def compile_risk(structure: dict) -> dict:
    """Business System JSON -> Risk Analysis. Auto-repairs on validation failure."""
    risk_id = str(uuid.uuid4())[:12]
    input_text = _json.dumps(structure, ensure_ascii=False)
    max_repairs = 2
    for repair_attempt in range(max_repairs + 1):
        result = _llm(PROMPT, input_text[:8000], temperature=0.1)
        if result.get("fallback"):
            return _fallback(structure, risk_id)
        result["risk_id"] = risk_id
        is_valid, issues, repaired = validate(result, "risk.json")
        if is_valid:
            return repaired
        if repair_attempt < max_repairs:
            input_text = input_text + "\n\n[REPAIR] Fix: " + ", ".join(issues[:5])
    return repaired if repaired else _fallback(structure, risk_id)

def _fallback(structure: dict, rid: str) -> dict:
    return {
        "risk_id": rid,
        "risk_matrix": [
            {"id":"R1","risk":"Input validation failure","category":"operational","probability":"medium","impact":"high","score":6,"trigger":"Bad data received","owner":"System"},
            {"id":"R2","risk":"Human error in review","category":"quality","probability":"low","impact":"high","score":3,"trigger":"Fatigue or oversight","owner":"Team Lead"},
            {"id":"R3","risk":"System downtime","category":"technical","probability":"low","impact":"high","score":3,"trigger":"Infrastructure failure","owner":"DevOps"}
        ],
        "bottlenecks": [
            {"node":"Manual Review","cause":"Single reviewer bottleneck","impact":"Queue backlog","severity":"high"},
            {"node":"Decision","cause":"Ambiguous rules","impact":"Inconsistent output","severity":"medium"}
        ],
        "mitigations": [
            {"risk_id":"R1","action":"Add schema validation","owner":"Dev","priority":"high","cost_estimate":"1 week","timeline":"Sprint 1"},
            {"risk_id":"R2","action":"Implement double-check for critical items","owner":"Team Lead","priority":"medium","cost_estimate":"Process change","timeline":"Sprint 2"},
            {"risk_id":"R3","action":"Setup failover cluster","owner":"DevOps","priority":"high","cost_estimate":"$2k/mo","timeline":"Q2"}
        ],
        "optimizations": [
            {"id":"O1","suggestion":"Auto-route low-risk items straight to completion","expected_impact":"40% throughput increase","effort":"medium","category":"efficiency"},
            {"id":"O2","suggestion":"Parallelize review for high-volume periods","expected_impact":"50% latency reduction","effort":"high","category":"capacity"}
        ]
    }
