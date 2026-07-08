"""Structure Compiler: PRD -> Business System JSON with repair loop."""
from compilers.llm_service import chat_json as _llm
from validators import validate
import uuid, json as _json

PROMPT = """You are a Structure Compiler. Convert a PRD into a strict Business System JSON.

OUTPUT ONLY valid JSON:
{
  "system_id": "generated-uuid",
  "objective": "1 sentence business goal",
  "domain": "ecommerce|saas|logistics|fintech|healthcare|general",
  "actors": [{"id":"a1","role":"Role name","responsibilities":["task"],"inputs":["data"],"outputs":["result"]}],
  "workflow": [{"step":1,"actor":"Role","action":"Action","condition":"if any","input":"data","output":"result","next":2,"sla_hours":24}],
  "states": [{"name":"state_name","is_initial":true,"is_terminal":false,"transitions":[{"to":"next_state","trigger":"event","guard":"condition"}]}],
  "rules": [{"id":"R1","condition":"when X","action":"do Y","exception":"unless Z","priority":"high|medium|low"}],
  "exceptions": [{"trigger":"error condition","path":"alternate flow","fallback":"backup plan"}],
  "constraints": ["max 24h","min 3 actors"]
}
RULES: At least 3 actors, 4 workflow steps, 3 states, 3 rules, 2 exceptions. NO MARKDOWN."""

def compile_structure(prd_text: str) -> dict:
    """PRD -> Business System JSON. Auto-repairs via LLM retry on validation failure."""
    system_id = str(uuid.uuid4())[:12]
    max_repairs = 2
    for repair_attempt in range(max_repairs + 1):
        result = _llm(PROMPT, prd_text[:8000], temperature=0.1)
        if result.get("fallback"):
            return _fallback(prd_text, system_id)
        result["system_id"] = system_id
        is_valid, issues, repaired = validate(result, "structure.json")
        if is_valid:
            return repaired
        if repair_attempt < max_repairs:
            prd_text = prd_text + "\n\n[REPAIR] Fix these JSON issues: " + ", ".join(issues[:5])
    return repaired if repaired else _fallback(prd_text, system_id)

def _fallback(text: str, sid: str) -> dict:
    return {
        "system_id": sid, "objective": text[:200], "domain": "general",
        "actors": [{"id":"a1","role":"User","responsibilities":["Submit request"],"inputs":["Data"],"outputs":["Result"]},
                    {"id":"a2","role":"System","responsibilities":["Process request"],"inputs":["Request"],"outputs":["Response"]},
                    {"id":"a3","role":"Admin","responsibilities":["Oversee operations"],"inputs":["Reports"],"outputs":["Decisions"]}],
        "workflow": [{"step":1,"actor":"User","action":"Submit","condition":"","input":"Data","output":"Request","next":2,"sla_hours":24},
                      {"step":2,"actor":"System","action":"Process","condition":"Valid input","input":"Request","output":"Result","next":3,"sla_hours":4},
                      {"step":3,"actor":"System","action":"Notify","condition":"","input":"Result","output":"Notification","next":4,"sla_hours":1},
                      {"step":4,"actor":"Admin","action":"Review","condition":"Escalated","input":"Result","output":"Decision","next":"end","sla_hours":48}],
        "states": [{"name":"idle","is_initial":True,"is_terminal":False,"transitions":[{"to":"processing","trigger":"request","guard":""}]},
                    {"name":"processing","is_initial":False,"is_terminal":False,"transitions":[{"to":"completed","trigger":"done","guard":""}]},
                    {"name":"completed","is_initial":False,"is_terminal":True,"transitions":[]}],
        "rules": [{"id":"R1","condition":"Invalid input","action":"Reject with error","exception":"Retry allowed","priority":"high"},
                   {"id":"R2","condition":"Timeout","action":"Escalate","exception":"","priority":"medium"},
                   {"id":"R3","condition":"Duplicate request","action":"Merge","exception":"","priority":"low"}],
        "exceptions": [{"trigger":"System down","path":"Queue and retry","fallback":"Manual processing"},
                        {"trigger":"SLA breach","path":"Escalate to manager","fallback":"Overtime allocation"}],
        "constraints": ["24h SLA","Max 1000 concurrent requests"]
    }
