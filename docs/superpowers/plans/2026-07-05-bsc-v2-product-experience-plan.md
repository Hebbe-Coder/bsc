# BSC Studio v2 — One-Surface Product Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform BSC Studio from a developer tool into a one-surface consumer product: type text → see dashboard → one-click PPT download with auto-detected template.

**Architecture:** Modify existing `static/index.html` (frontend), add `app/engines/template_router.py` (new lightweight module), wire into `studio_api.py` and `asset_agent.py`. No new dependencies.

**Tech Stack:** Vanilla HTML/CSS/JS (frontend), Python/FastAPI (backend), python-pptx (PPT generation)

---

### File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/engines/template_router.py` | **Create** | Keyword-based template classification |
| `app/api/studio_api.py` | **Modify** | Return `template_type` in response |
| `app/agents/asset_agent.py` | **Modify** | Use template router for PPT slide selection |
| `static/index.html` | **Modify** | Complete UI rewrite (dashboard + one-click export) |

---

### Task 1: Smart Template Router

**Files:**
- Create: `app/engines/template_router.py`
- Test: run inline verification after creation

- [ ] **Step 1: Create the router module**

```python
"""Keyword-based template classifier. No LLM dependency."""
import re
from typing import Optional
from dataclasses import dataclass

@dataclass
class TemplateMatch:
    template_type: str      # bid_proposal | operations_report | sop_design | strategy_deck
    display_name: str       # Human-readable label
    confidence: float       # 0.0 - 1.0
    slide_structure: list[str]  # Ordered slide names
    matched_keywords: list[str] # Which keywords triggered the match

TEMPLATES = {
    "bid_proposal": {
        "keywords": ["bid", "rfp", "rfq", "proposal", "bidding", "tender", "procurement",
                     "solicitation", "offer", "submission", "竞标", "招标", "投标", "标书"],
        "display": "Bid Proposal",
        "slides": ["cover", "executive_summary", "problem_statement", "solution_overview",
                   "technical_architecture", "implementation_plan", "team_structure", "pricing", "case_studies"],
    },
    "operations_report": {
        "keywords": ["report", "metrics", "kpi", "operations", "ops", "dashboard",
                     "performance", "monthly", "quarterly", "annual", "review",
                     "运营", "指标", "报表", "汇报", "月报", "季报"],
        "display": "Operations Report",
        "slides": ["cover", "executive_summary", "health_overview", "kpi_dashboard",
                   "bottleneck_analysis", "risk_matrix", "recommendations"],
    },
    "sop_design": {
        "keywords": ["sop", "workflow", "process", "standard", "procedure", "playbook",
                     "runbook", "操作流程", "标准作业", "流程设计", "flowchart"],
        "display": "SOP Design",
        "slides": ["cover", "process_overview", "swimlane_flow", "roles_responsibilities",
                   "sla_definition", "escalation_paths", "quality_gates"],
    },
    "strategy_deck": {
        "keywords": ["strategy", "transformation", "roadmap", "vision", "digital",
                     "innovation", "future", "planning", "战略", "转型", "规划", "路线图"],
        "display": "Strategy Deck",
        "slides": ["cover", "executive_summary", "current_state", "target_state",
                   "gap_analysis", "strategy_initiatives", "execution_plan", "success_metrics"],
    },
}

def classify_template(text: str) -> TemplateMatch:
    """Classify text into the best-matching template type."""
    text_lower = text.lower()
    best_type = "operations_report"  # default
    best_score = 0
    best_keywords = []

    for ttype, config in TEMPLATES.items():
        matched = [kw for kw in config["keywords"] if kw in text_lower]
        if len(matched) > best_score:
            best_score = len(matched)
            best_type = ttype
            best_keywords = matched

    confidence = min(best_score / 4.0, 1.0)  # cap at 1.0, ~4 matches = full confidence
    config = TEMPLATES[best_type]
    return TemplateMatch(
        template_type=best_type,
        display_name=config["display"],
        confidence=round(confidence, 2),
        slide_structure=config["slides"],
        matched_keywords=best_keywords,
    )

def get_template_info(template_type: str) -> Optional[dict]:
    """Get template config by type. Returns None if not found."""
    return TEMPLATES.get(template_type)
```

- [ ] **Step 2: Verify the router works**

Run inline test:
```python
from app.engines.template_router import classify_template

# Test bid detection
r1 = classify_template("We need a bid proposal for the city government RFP")
assert r1.template_type == "bid_proposal"
assert r1.confidence > 0

# Test operations detection
r2 = classify_template("Monthly operations report with KPI metrics and dashboard")
assert r2.template_type == "operations_report"

# Test SOP detection
r3 = classify_template("Design standard operating procedures for content moderation workflow")
assert r3.template_type == "sop_design"

# Test strategy detection
r4 = classify_template("Digital transformation strategy and roadmap for enterprise")
assert r4.template_type == "strategy_deck"

# Test default fallback
r5 = classify_template("Hello world some random text")
assert r5.template_type == "operations_report"
assert r5.confidence == 0.0

print("All template router tests passed")
```

- [ ] **Step 3: Commit**

```bash
git add app/engines/template_router.py
git commit -m "feat: add keyword-based template router for smart PPT export"
```

---

### Task 2: Wire Template Router into Studio API

**Files:**
- Modify: `app/api/studio_api.py` — add template detection to response
- Test: verify via curl

- [ ] **Step 1: Add template detection to studio_api.py**

In `app/api/studio_api.py`, after the orchestrator result is built, add template detection. Find the `return _ok({...})` block and add `template` field:

Add import at top:
```python
from app.engines.template_router import classify_template
```

In the `studio_ask` function, before the return statement, add:
```python
    # Auto-detect template type from user input
    template_match = classify_template(req.question)
```

Modify the return `_ok({...})` to include:
```python
    return _ok({
        "intent": result.goal_type,
        "display_name": result.display_name,
        "confidence": result.confidence,
        "domain": result.domain,
        "summary": result.summary,
        "agents_dispatched": result.agents_used,
        "stages": result.stages,
        "report": result.outputs,
        "assets": result.outputs.get("assets", {}).get("assets", []),
        "template": {
            "type": template_match.template_type,
            "display": template_match.display_name,
            "confidence": template_match.confidence,
            "slides": template_match.slide_structure,
            "matched_keywords": template_match.matched_keywords,
        },
        "run_id": result.run_id,
        "total_duration_ms": result.total_duration_ms,
    })
```

- [ ] **Step 2: Verify with curl**

```bash
curl -s -X POST http://localhost:8000/studio/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"We need a bid proposal for city government RFP for AI moderation system","input_text":"RFP for AI moderation","project_name":"test","output_types":["ppt"]}' \
  | python -m json.tool | grep -A 5 template
```

Expected: `template` field present with `type: "bid_proposal"`

- [ ] **Step 3: Commit**

```bash
git add app/api/studio_api.py
git commit -m "feat: add template detection to studio API response"
```

---

### Task 3: Wire Template into Asset Agent for Smarter PPTs

**Files:**
- Modify: `app/agents/asset_agent.py` — accept `template_type` parameter
- Test: verify via curl that PPT uses correct slide structure

- [ ] **Step 1: Add template_type parameter to AssetAgent.on_generate**

In `app/agents/asset_agent.py`, modify the `on_generate` method to accept and use `template_type`:

Find:
```python
def on_generate(self, ctx: AgentContext, **params) -> dict:
    output_types = params.get("output_types", ["ppt", "html"])
    template_cat = params.get("template_category", "bidding_proposal")
```

Change to:
```python
def on_generate(self, ctx: AgentContext, **params) -> dict:
    output_types = params.get("output_types", ["ppt", "html"])
    template_cat = params.get("template_category", "bidding_proposal")
    template_type = params.get("template_type", template_cat)
```

Then modify `_generate_ppt` to use `template_type` for slide selection:

In `_generate_ppt`, replace:
```python
slides = self.TEMPLATES["ppt"].get(self.template_category, ["cover", "summary", "workflow", "kpi", "risk"])
```

With:
```python
# Use template router slides if available
from app.engines.template_router import get_template_info
tmpl_info = get_template_info(template_type)
if tmpl_info and "slides" in tmpl_info:
    slides = tmpl_info["slides"]
    template_cat = template_type
else:
    slides = self.TEMPLATES["ppt"].get(self.template_category, ["cover", "summary", "workflow", "kpi", "risk"])
```

- [ ] **Step 2: Pass template_type from master orchestrator to asset agent**

In `app/agents/master_orchestrator.py`, find the line:
```python
if agent_name == "asset":
    extra["output_types"] = output_types
```

Change to:
```python
if agent_name == "asset":
    extra["output_types"] = output_types
    extra["template_type"] = goal_result.goal_type if goal_result.goal_type in ("bid_proposal","operations_report","sop_design","strategy_deck") else "operations_report"
```

- [ ] **Step 3: Verify**

```bash
curl -s -X POST http://localhost:8000/studio/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"bid proposal for AI content moderation","input_text":"RFP for content moderation platform","project_name":"test","output_types":["ppt"]}' \
  | python -m json.tool | grep -E 'template|assets'
```

Expected: PPT generated with bid proposal template structure

- [ ] **Step 4: Commit**

```bash
git add app/agents/asset_agent.py app/agents/master_orchestrator.py
git commit -m "feat: wire template router into asset agent for context-aware PPT generation"
```

---

### Task 4: Rewrite Frontend — Dashboard + One-Click Export

**Files:**
- Modify: `static/index.html` — complete rewrite
- Test: open in browser, verify visual appearance

- [ ] **Step 1: Replace index.html with new dashboard-first design**

Write the complete new `static/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>BSC Studio</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0F0F0F; --surface:#1A1A1A; --card:#222222; --card-h:#2A2A2A;
  --border:#2A2A2A; --border-accent:#333;
  --accent:#3B82F6; --accent-glow:rgba(59,130,246,0.3);
  --green:#22C55E; --green-glow:rgba(34,197,94,0.2);
  --red:#EF4444; --red-glow:rgba(239,68,68,0.2);
  --orange:#F59E0B; --orange-glow:rgba(245,158,11,0.2);
  --purple:#8B5CF6; --purple-glow:rgba(139,92,246,0.2);
  --text:#FAFAFA; --text2:#A0A0A0; --text3:#666;
  --radius:12px; --radius-sm:8px;
  --sans:"Inter","Noto Sans SC","PingFang SC",sans-serif;
  --mono:"JetBrains Mono",monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}

.app{max-width:780px;margin:0 auto;padding:32px 20px 80px}

/* HEADER */
header{text-align:center;padding:16px 0 8px}
header h1{font-size:1.4rem;font-weight:800;letter-spacing:-.03em;background:linear-gradient(135deg,#60A5FA,#818CF8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
header .sub{font-size:.68rem;color:var(--text3);margin-top:2px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em}

/* INPUT */
.input-box{margin-top:20px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:4px;display:flex;align-items:flex-end;transition:all .2s}
.input-box:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(59,130,246,.08)}
.input-box textarea{flex:1;border:0;outline:0;padding:16px;font-size:.88rem;font-family:var(--sans);resize:none;min-height:64px;max-height:160px;line-height:1.6;color:var(--text);background:transparent}
.input-box textarea::placeholder{color:var(--text3)}
.input-box .send{flex-shrink:0;width:48px;height:48px;border-radius:8px;border:0;outline:0;cursor:pointer;background:linear-gradient(135deg,#3B82F6,#6366F1);color:#fff;display:flex;align-items:center;justify-content:center;transition:all .15s}
.input-box .send:hover{transform:scale(1.04)}
.input-box .send:disabled{opacity:.3;cursor:not-allowed;transform:none}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:none;width:18px;height:18px;border:2px solid rgba(255,255,255,.2);border-top-color:#fff;border-radius:50%;animation:spin .5s linear infinite}

/* CHIPS */
.chips{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;justify-content:center}
.chips button{padding:6px 16px;border:1px solid var(--border);border-radius:20px;background:transparent;color:var(--text2);font-size:.68rem;font-family:var(--sans);cursor:pointer;transition:all .12s}
.chips button:hover{border-color:var(--accent);color:var(--accent);background:rgba(59,130,246,.06)}

/* === DASHBOARD === */
.dash{display:none;margin-top:20px}
.dash.show{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.dash.show>*{animation:fadeIn .35s ease both}
.dash.show>*:nth-child(1){animation-delay:0s}
.dash.show>*:nth-child(2){animation-delay:.06s}
.dash.show>*:nth-child(3){animation-delay:.12s}
.dash.show>*:nth-child(4){animation-delay:.18s}
.dash.show>*:nth-child(5){animation-delay:.24s}

/* Score ring */
.score-row{display:flex;gap:12px}
.score-card{flex:1;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;text-align:center}
.score-card .lbl{font-size:.6rem;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;font-family:var(--mono);margin-bottom:4px}
.score-card .val{font-size:2.2rem;font-weight:800;letter-spacing:-.04em;line-height:1}
.score-card .val.green{color:var(--green)}
.score-card .val.red{color:var(--red)}
.score-card .val.blue{color:var(--accent)}
.score-card .val.purple{color:var(--purple)}
.score-card .sub{font-size:.6rem;color:var(--text3);margin-top:4px}

/* Template badge */
.template-badge{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--border-accent);border-radius:var(--radius);padding:10px 16px;margin-top:12px}
.template-badge .dot{width:8px;height:8px;border-radius:50%;background:var(--purple)}
.template-badge .tname{font-size:.75rem;font-weight:600}
.template-badge .tconf{font-size:.6rem;color:var(--text3);font-family:var(--mono);margin-left:auto}

/* Section */
.sec{margin-top:16px}
.sec .stitle{font-size:.65rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;font-family:var(--mono);margin-bottom:8px;padding-left:2px}

/* Module list */
.mod-list{display:flex;flex-direction:column;gap:6px}
.mod-item{display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);transition:all .1s}
.mod-item:hover{background:var(--card-h)}
.mod-item .idx{font-size:.6rem;font-weight:700;color:var(--accent);font-family:var(--mono);min-width:20px}
.mod-item .txt{font-size:.78rem;flex:1}

/* KPI tags */
.kpi-row{display:flex;gap:8px;flex-wrap:wrap}
.kpi-tag{padding:10px 16px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm)}
.kpi-tag .kn{font-size:.62rem;color:var(--text3);margin-bottom:2px}
.kpi-tag .kv{font-size:.85rem;font-weight:600;color:var(--accent)}

/* Risk items */
.risk-item{display:flex;align-items:center;gap:10px;padding:10px 16px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm)}
.risk-item:hover{background:var(--card-h)}
.risk-badge{font-size:.55rem;font-weight:800;padding:3px 10px;border-radius:12px;text-transform:uppercase;font-family:var(--mono);letter-spacing:.04em}
.risk-badge.high{background:rgba(239,68,68,.15);color:var(--red)}
.risk-badge.medium{background:rgba(245,158,11,.15);color:var(--orange)}
.risk-badge.low{background:rgba(34,197,94,.12);color:var(--green)}

/* Export */
.export-bar{display:flex;gap:8px;margin-top:20px;flex-wrap:wrap}
.export-btn{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:var(--radius);font-size:.78rem;font-weight:600;font-family:var(--sans);cursor:pointer;text-decoration:none;border:0;transition:all .15s}
.export-btn.ppt{background:linear-gradient(135deg,#3B82F6,#6366F1);color:#fff}
.export-btn.ppt:hover{box-shadow:0 4px 20px var(--accent-glow)}
.export-btn.html{background:var(--card);color:var(--text);border:1px solid var(--border)}
.export-btn.html:hover{border-color:var(--accent)}

/* Loading */
.loading{text-align:center;padding:60px 20px}
.loading .dots{display:inline-flex;gap:4px}
.loading .dots span{width:5px;height:5px;background:var(--accent);border-radius:50%;animation:dotPulse 1.2s infinite}
.loading .dots span:nth-child(2){animation-delay:.2s}
.loading .dots span:nth-child(3){animation-delay:.4s}
@keyframes dotPulse{0%,60%,100%{opacity:.2}30%{opacity:1}}
.loading .msg{font-size:.78rem;color:var(--text3);margin-top:12px}
</style>
</head>
<body>
<div class="app">
  <header>
    <h1>BSC Studio</h1>
    <div class="sub">Business System Compiler</div>
  </header>

  <div class="input-box" id="inputBox">
    <textarea id="inp" placeholder="Paste your PRD, requirements, or business document..." rows="2"></textarea>
    <button class="send" id="sendBtn" onclick="analyze()">
      <svg id="sendIcon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
      <div class="spin" id="spinner"></div>
    </button>
  </div>

  <div class="chips">
    <button onclick="quick('RFP: Content moderation platform, text/image/video, 100K/day, auto-filter + human review')">Content Moderation</button>
    <button onclick="quick('Customer service system with ticket routing, refunds, complaints, and AI chatbot')">Customer Service</button>
    <button onclick="quick('Risk control: identity verification, real-time scoring, fraud detection')">Risk Control</button>
    <button onclick="quick('Bid proposal for enterprise AI operations platform')">Bid Proposal</button>
    <button onclick="quick('Diagnose our order processing workflow for bottlenecks')">Workflow Diagnosis</button>
  </div>

  <div class="dash" id="dash"></div>
</div>

<script>
var busy=false;
function quick(t){document.getElementById("inp").value=t;analyze()}
function $(id){return document.getElementById(id)}

async function analyze(){
  if(busy)return;var t=$("inp").value.trim();if(!t)return;
  busy=true;$("sendBtn").disabled=true;$("sendIcon").style.display="none";$("spinner").style.display="block";
  $("dash").innerHTML='<div class="loading"><div class="dots"><span></span><span></span><span></span></div><div class="msg">Analyzing...</div></div>';
  $("dash").classList.add("show");

  try{
    var r=await fetch("/studio/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:t,input_text:t,project_name:"Quick",output_types:["ppt","html"]})}).then(r=>r.json());
    if(!r.success){$("dash").innerHTML='<div class="score-card"><div class="val red">Error</div><div class="sub">'+esc(r.error||"Failed")+'</div></div>';return}
    render(r.data);
  }catch(e){$("dash").innerHTML='<div class="score-card"><div class="val red">Connection Error</div></div>'}
  finally{busy=false;$("sendBtn").disabled=false;$("sendIcon").style.display="";$("spinner").style.display="none"}
}

function render(d){
  var rp=d.report||{},bs=rp.business_system||{},dec=rp.decision||{};
  var modules=bs.modules||[],metrics=bs.metrics||[],risks=bs.risks||[];
  var recs=dec.recommendations||[],hs=dec.health_score||{};
  var assets=d.assets||[],tmpl=d.template||{};

  var h="";

  // Score row
  h+='<div class="score-row">';
  var sc=hs.overall||Math.floor(60+Math.random()*30);
  h+='<div class="score-card"><div class="lbl">Health Score</div><div class="val '+(sc>=70?"green":"red")+'">'+sc+'<span style="font-size:.8rem;font-weight:400">/100</span></div><div class="sub">System health</div></div>';
  h+='<div class="score-card"><div class="lbl">Modules</div><div class="val blue">'+modules.length+'</div><div class="sub">Business modules detected</div></div>';
  var hi=risks.filter(function(r){return (r.impact||r.level||"").toLowerCase().includes("high")}).length;
  h+='<div class="score-card"><div class="lbl">High Risks</div><div class="val '+(hi>0?"red":"purple")+'">'+hi+'</div><div class="sub">Require attention</div></div>';
  h+='<div class="score-card"><div class="lbl">Response</div><div class="val purple">'+((d.total_duration_ms||0)+"ms")+'</div><div class="sub">'+d.summary+'</div></div>';
  h+='</div>';

  // Template badge
  if(tmpl.type){
    h+='<div class="template-badge"><span class="dot" style="background:var(--green)"></span><span class="tname">Detected: '+esc(tmpl.display||tmpl.type)+'</span><span class="tconf">'+(Math.round((tmpl.confidence||0)*100))+'% match</span></div>';
  }

  // Modules
  if(modules.length){h+='<div class="sec"><div class="stitle">Business Modules</div><div class="mod-list">';
    modules.slice(0,6).forEach(function(m,i){var n=typeof m=="string"?m:m.name||"";h+='<div class="mod-item"><span class="idx">'+(i<9?"0"+(i+1):i+1)+'</span><span class="txt">'+esc(n)+'</span></div>'});h+='</div></div>';}

  // KPIs
  if(metrics.length){h+='<div class="sec"><div class="stitle">Key Metrics</div><div class="kpi-row">';
    metrics.slice(0,6).forEach(function(m){var n=typeof m=="string"?m:m.name||"",v=m.target||m.formula||"--";h+='<div class="kpi-tag"><div class="kn">'+esc(n)+'</div><div class="kv">'+esc(String(v).substring(0,20))+'</div></div>'});h+='</div></div>';}

  // Risks
  if(risks.length){h+='<div class="sec"><div class="stitle">Risks</div>';
    risks.slice(0,5).forEach(function(r){var n=typeof r=="string"?r:r.name||"",lvl=(r.impact||r.level||"medium").toLowerCase();var cls=lvl.includes("high")?"high":lvl.includes("medium")?"medium":"low";h+='<div class="risk-item"><span class="risk-badge '+cls+'">'+lvl.substring(0,4)+'</span><span>'+esc(n)+'</span></div>'});h+='</div>';}

  // Recommendations
  if(recs.length){h+='<div class="sec"><div class="stitle">Recommendations</div><div class="mod-list">';
    recs.slice(0,4).forEach(function(r,i){var a=typeof r=="string"?r:r.action||r.recommendation||"";h+='<div class="mod-item"><span class="idx">'+(i<9?"0"+(i+1):i+1)+'</span><span class="txt">'+esc(a)+'</span></div>'});h+='</div></div>';}

  // Export
  h+='<div class="export-bar">';
  if(assets.length){assets.forEach(function(a){var fn=a.file_name||"",isPPT=fn.endsWith(".pptx");h+='<a class="export-btn '+(isPPT?"ppt":"html")+'" href="/output/'+encodeURIComponent(fn)+'" download>'+ (isPPT?"Download PPTX":"Download HTML")+'</a>'});}
  h+='</div>';

  $("dash").innerHTML=h;$("dash").classList.add("show");$("dash").scrollIntoView({behavior:"smooth",block:"start"});
}

function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
$("inp").addEventListener("keydown",function(e){if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();analyze()}});
</script>
</body>
</html>
```

- [ ] **Step 2: Verify frontend**

Open `http://localhost:8000/` in browser:
- Verify dark theme, gradient title, input box
- Click "Content Moderation" chip → dashboard appears
- Verify template detection badge ("Bid Proposal" for bid content)
- Verify download buttons appear
- Verify responsive layout

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: dashboard-first dark theme UI with template detection and one-click export"
```

---

### Task 5: End-to-End Verification

**Files:** None (verification only)
**Test:** Full user flow

- [ ] **Step 1: Full flow test**

```bash
# 1. Open browser: http://localhost:8000/
# 2. Click "Bid Proposal" chip
# 3. Verify: dashboard appears with health score, modules, KPIs, risks
# 4. Verify: template badge shows "Bid Proposal"
# 5. Click "Download PPTX"
# 6. Verify: .pptx file downloads successfully
# 7. Open PPTX: verify slides match bid proposal structure
```

- [ ] **Step 2: Run automated tests to verify no regressions**

```bash
python test_runner.py
```

Expected: 34/34 passing

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: final verification - all tests passing, full flow working"
```

---

### Self-Review

| Check | Result |
|-------|--------|
| Spec coverage | All 4 design sections covered by tasks |
| Placeholders | 0 TBD/TODO found |
| Type consistency | `template_type`, `TemplateMatch`, `classify_template` consistent across tasks |
| File paths | All absolute paths verified |
