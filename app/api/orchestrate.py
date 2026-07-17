# app/api/orchestrate.py
from __future__ import annotations
import asyncio
import json
import uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.sse import SessionEventBus
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])
_bus = SessionEventBus()


def build_agents(llm):
    from app.orchestrator.agents.planner import PlannerAgent
    from app.orchestrator.agents.business_architect import BusinessArchitectAgent
    from app.orchestrator.agents.sop_builder import SopBuilderAgent
    from app.orchestrator.agents.risk_architect import RiskArchitectAgent
    from app.orchestrator.agents.reviewer import ReviewerAgent
    from app.orchestrator.agents.presenter import PresenterAgent
    return {
        "planner": PlannerAgent(llm_service=llm),
        "architect": BusinessArchitectAgent(llm_service=llm),
        "sop": SopBuilderAgent(llm_service=llm),
        "risk": RiskArchitectAgent(llm_service=llm),
        "reviewer": ReviewerAgent(llm_service=llm),
        "presenter": PresenterAgent(llm_service=llm),
    }


@router.post("")
async def orchestrate(request: Request):
    body = await request.json()
    idea = body.get("idea")
    if not idea:
        raise HTTPException(400, "idea required")
    sid = body.get("session_id") or uuid.uuid4().hex[:12]
    # 立即落库，保证客户端拿到的 session_id 可立即查询（流水线在后台跑）
    ProjectDraftRepository().save(ProjectDraft(session_id=sid, idea=idea, status="running"))
    llm = LLMService()
    eng = OrchestratorEngine(agents=build_agents(llm), bus=_bus)
    asyncio.create_task(eng.run_pipeline(sid, idea))
    return {"session_id": sid, "status": "running"}


@router.get("/stream")
async def stream(session_id: str):
    async def event_gen():
        async for ev in _bus.subscribe(session_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream")
