"""Standalone Agent OS API server — no middleware dependencies."""
import sys, json, time
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Business Agent OS", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class AgentRequest(BaseModel):
    input: str
    mode: str = "llm"
    domain: str = ""
    board: bool = False


from fastapi.responses import RedirectResponse, HTMLResponse

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/agent/analyze", include_in_schema=False)
async def analyze_page():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>Business Agent OS</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0d1117; color: #c9d1d9; display: flex;
               justify-content: center; align-items: center; min-height: 100vh; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
                padding: 40px; max-width: 600px; text-align: center; }
        h1 { color: #58a6ff; margin-bottom: 8px; font-size: 28px; }
        .sub { color: #8b949e; margin-bottom: 24px; }
        .badge { display: inline-block; background: #1f6feb22; color: #58a6ff;
                 border: 1px solid #1f6feb44; border-radius: 20px; padding: 4px 12px;
                 font-size: 13px; margin: 4px; }
        .endpoint { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
                    padding: 16px; margin: 12px 0; text-align: left; font-family: monospace; }
        .method { display: inline-block; padding: 2px 8px; border-radius: 4px;
                  font-weight: bold; font-size: 12px; margin-right: 8px; }
        .get { background: #1f6feb; color: #fff; }
        .post { background: #238636; color: #fff; }
        .path { color: #c9d1d9; }
        a { color: #58a6ff; }
        .btn { display: inline-block; background: #238636; color: #fff; padding: 12px 24px;
               border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 16px; }
        .btn:hover { background: #2ea043; }
    </style>
</head>
<body>
<div class="card">
    <h1>Business Agent OS</h1>
    <p class="sub">ADR-010 Architecture | Nanobot Kernel | BSC Reasoning Engine</p>
    <div>
        <span class="badge">12 Capabilities</span>
        <span class="badge">DeepSeek Ready</span>
        <span class="badge">Multi-Agent Board</span>
    </div>
    <div class="endpoint">
        <span class="method get">GET</span><span class="path">/agent/health</span>
        <div style="color:#8b949e;margin-top:4px;">Health check</div>
    </div>
    <div class="endpoint">
        <span class="method post">POST</span><span class="path">/agent/analyze</span>
        <div style="color:#8b949e;margin-top:4px;">Run full business analysis pipeline</div>
    </div>
    <a class="btn" href="/docs">Open Swagger UI</a>
</div>
</body>
</html>
""")


@app.get("/agent/health")
async def health():
    from app.services.llm_adapter import get_llm_adapter, reset_llm_adapter
    from app.capabilities import build_default_registry
    reset_llm_adapter()
    llm = get_llm_adapter()
    reg = build_default_registry()
    return {
        "status": "ok", "version": "2.0.0",
        "architecture": "ADR-010 Business Agent OS",
        "capabilities": reg.count(), "llm_ready": llm.is_ready,
        "endpoints": {"analyze": "POST /agent/analyze", "health": "GET /agent/health"},
    }

@app.post("/agent/analyze")
async def analyze(req: AgentRequest):
    from app.artifacts import ArtifactGraphStore, BusinessModelArtifact
    from app.capabilities import build_default_registry, MissionPlanner, ReflectionPipeline

    store = ArtifactGraphStore(data_dir="./data/artifacts")
    reg = build_default_registry()
    planner = MissionPlanner(registry=reg, mode=req.mode)

    async def run():
        mission = await planner.plan(req.input, domain_hint=req.domain)
        bm = BusinessModelArtifact(label=mission.title, project_id="api", domain=mission.domain)
        store.add(bm)
        pipe = ReflectionPipeline(store, reg)
        reflection = pipe.run()
        board_result = None
        if req.board:
            from app.capabilities.board import MultiAgentBoard
            board = MultiAgentBoard(store)
            board_result = await board.convene(project_id="api")

        return {
            "status": "completed",
            "mission": {"title": mission.title, "steps": len(mission.steps), "mode": mission.planning_mode},
            "artifacts": store.count(),
            "gaps": reflection["stages"]["reflect"]["gaps_found"],
            "gap_details": reflection["gaps"],
            "board": {
                "verdict": board_result.final_verdict,
                "consensus": board_result.consensus,
                "votes": board_result.votes,
            } if board_result else None,
            "report": store.export(),
        }

    result = await run()
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
