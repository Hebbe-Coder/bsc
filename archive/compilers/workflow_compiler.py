"""Workflow Compiler: Business System JSON -> SOP Swimlane Flow with repair loop."""
from compilers.llm_service import chat_json as _llm
from validators import validate
import uuid, json as _json

PROMPT = """You are a Workflow Compiler. Convert a Business System JSON into a SOP swimlane diagram.

OUTPUT ONLY valid JSON:
{
  "workflow_id": "generated-id",
  "title": "Process Name",
  "swimlanes": [
    {"id":"s1","label":"User","role":"end_user"},
    {"id":"s2","label":"System","role":"automation"},
    {"id":"s3","label":"Admin","role":"operator"}
  ],
  "nodes": [
    {"id":"n1","swimlane":"s1","label":"Submit Request","type":"start","sla_hours":null},
    {"id":"n2","swimlane":"s2","label":"Auto-validate","type":"action","sla_hours":0.1},
    {"id":"n3","swimlane":"s2","label":"Valid?","type":"decision","sla_hours":null},
    {"id":"n4","swimlane":"s3","label":"Manual Review","type":"action","sla_hours":4},
    {"id":"n5","swimlane":"s2","label":"Complete","type":"end","sla_hours":null}
  ],
  "edges": [
    {"from":"n1","to":"n2","label":"submitted"},
    {"from":"n2","to":"n3","label":"validated"},
    {"from":"n3","to":"n4","label":"no","condition":"!valid"},
    {"from":"n3","to":"n5","label":"yes","condition":"valid"},
    {"from":"n4","to":"n5","label":"reviewed"}
  ]
}
RULES:
- 1 swimlane per actor role from structure
- At least 5 nodes including start and end
- Nodes must have type: start, end, action, decision, wait
- Match workflow steps from structure JSON
- Every node belongs to a swimlane
NO MARKDOWN. JSON ONLY."""

def compile_workflow(structure: dict) -> dict:
    """Business System JSON -> SOP Swimlane Flow. Auto-repairs on validation failure."""
    wf_id = str(uuid.uuid4())[:12]
    input_text = _json.dumps(structure, ensure_ascii=False)
    max_repairs = 2
    for repair_attempt in range(max_repairs + 1):
        result = _llm(PROMPT, input_text[:8000], temperature=0.1)
        if result.get("fallback"):
            return _fallback(structure, wf_id)
        result["workflow_id"] = wf_id
        is_valid, issues, repaired = validate(result, "workflow.json")
        if is_valid:
            return repaired
        if repair_attempt < max_repairs:
            input_text = input_text + "\n\n[REPAIR] Fix: " + ", ".join(issues[:5])
    return repaired if repaired else _fallback(structure, wf_id)

def _fallback(structure: dict, wid: str) -> dict:
    actors = structure.get("actors", [])
    lanes = []
    for i, actor in enumerate(actors[:5]):
        lanes.append({
            "id": "s" + str(i+1),
            "label": actor.get("role", "Role " + str(i+1)),
            "role": actor.get("id", "a" + str(i+1))
        })
    if not lanes:
        lanes = [
            {"id":"s1","label":"User","role":"a1"},
            {"id":"s2","label":"System","role":"a2"},
            {"id":"s3","label":"Admin","role":"a3"}
        ]
    return {
        "workflow_id": wid,
        "title": structure.get("objective", "Business Workflow")[:80],
        "swimlanes": lanes,
        "nodes": [
            {"id":"n1","swimlane":lanes[0]["id"],"label":"Submit","type":"start","sla_hours":None},
            {"id":"n2","swimlane":lanes[1]["id"] if len(lanes)>1 else lanes[0]["id"],"label":"Process","type":"action","sla_hours":4},
            {"id":"n3","swimlane":lanes[1]["id"] if len(lanes)>1 else lanes[0]["id"],"label":"Decision","type":"decision","sla_hours":None},
            {"id":"n4","swimlane":lanes[2]["id"] if len(lanes)>2 else lanes[-1]["id"],"label":"Review","type":"action","sla_hours":8},
            {"id":"n5","swimlane":lanes[-1]["id"],"label":"Complete","type":"end","sla_hours":None}
        ],
        "edges": [
            {"from":"n1","to":"n2","label":"submitted"},
            {"from":"n2","to":"n3","label":"processed"},
            {"from":"n3","to":"n4","label":"needs review","condition":"!ok"},
            {"from":"n3","to":"n5","label":"ok","condition":"ok"},
            {"from":"n4","to":"n5","label":"reviewed"}
        ]
    }
