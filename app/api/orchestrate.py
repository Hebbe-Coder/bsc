# app/api/orchestrate.py
from __future__ import annotations
import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.core.config import settings
from app.orchestrator.contracts import EventType, JobStatus, is_terminal
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.sse import SessionEventBus
from app.services.llm_service import LLMService
from app.audit import build_trusted_audit
from app.evaluation import CompilerOutputEvaluator
from app.evolution import get_default_bridge

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])
_bus = SessionEventBus()
_tasks: dict[str, asyncio.Task] = {}
logger = logging.getLogger(__name__)


def _retain_task(session_id: str, coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks[session_id] = task

    def done(completed: asyncio.Task):
        if _tasks.get(session_id) is completed:
            _tasks.pop(session_id, None)
        if completed.cancelled():
            repo = ProjectDraftRepository()
            draft = repo.get(session_id)
            if draft is not None and not is_terminal(draft.status):
                try:
                    repo.transition(session_id, JobStatus.CANCELLED)
                except (KeyError, ValueError):
                    logger.exception(
                        "failed to persist pre-start orchestrator cancellation"
                    )
                else:
                    completed.get_loop().create_task(_bus.publish(
                        session_id,
                        EventType.PIPELINE_CANCELLED,
                        status=JobStatus.CANCELLED.value,
                        message="Pipeline cancelled",
                        terminal=True,
                    ))
            return
        error = completed.exception()
        if error is not None:
            logger.error(
                "orchestrator background task failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(done)
    return task


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


@router.post("", status_code=202)
async def orchestrate(request: Request):
    body = await request.json()
    idea = body.get("idea")
    if not isinstance(idea, str) or not idea.strip():
        raise HTTPException(400, "idea required")
    sid = body.get("session_id") or uuid.uuid4().hex[:12]
    repo = ProjectDraftRepository()
    if repo.get(sid) is not None:
        raise HTTPException(status_code=409, detail="session already exists")
    # 立即落库，保证客户端拿到的 session_id 可立即查询（流水线在后台跑）
    repo.save(ProjectDraft(
        session_id=sid,
        idea=idea.strip(),
        status=JobStatus.QUEUED.value,
    ))
    llm = LLMService(force_mock=settings.LLM_PROVIDER == "mock")
    engine = OrchestratorEngine(agents=build_agents(llm), repo=repo, bus=_bus)
    _retain_task(sid, engine.run_pipeline(sid, idea.strip()))
    return {
        "session_id": sid,
        "status": JobStatus.QUEUED.value,
        "status_url": f"/api/orchestrate/{sid}",
        "events_url": f"/api/orchestrate/{sid}/events",
    }


@router.get("/stream")
async def stream(request: Request, session_id: str, after: int = 0):
    if ProjectDraftRepository().get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _event_response(session_id, _resume_after(request, after))


@router.get("/{session_id}")
async def get_status(session_id: str):
    draft = ProjectDraftRepository().get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session_id,
        "status": draft.status,
        "terminal": is_terminal(draft.status),
    }


@router.delete("/{session_id}", status_code=202)
async def cancel(session_id: str):
    draft = ProjectDraftRepository().get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    if is_terminal(draft.status):
        return {
            "session_id": session_id,
            "status": draft.status,
            "cancel_requested": False,
        }
    task = _tasks.get(session_id)
    if task is None:
        raise HTTPException(status_code=409, detail="task is not active")
    task.cancel()
    return {
        "session_id": session_id,
        "status": draft.status,
        "cancel_requested": True,
    }


def _resume_after(request: Request, after: int) -> int:
    raw = request.headers.get("last-event-id")
    if raw is None:
        return after
    try:
        return max(after, int(raw))
    except ValueError:
        return after


def _event_response(session_id: str, after: int):
    async def event_gen():
        async for event in _bus.subscribe(session_id, after=after):
            payload = event.model_dump(mode="json")
            yield (
                f"id: {event.seq}\n"
                f"event: {event.type.value}\n"
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{session_id}/events")
async def events(request: Request, session_id: str, after: int = 0):
    if ProjectDraftRepository().get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _event_response(session_id, _resume_after(request, after))


@router.get("/dashboard/{session_id}")
async def dashboard(session_id: str):
    """将编译后的 ProjectDraft 重塑为仪表盘可用的负载。"""
    repo = ProjectDraftRepository()
    draft = repo.get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    state = draft.to_dict()
    # sop 段可能缺失，采用空字典兜底
    sop = state.get("sop") or {}
    risk = state.get("risk") or {}
    # 方案 E：把 A 的方法论引用 + B 的约束覆盖缝合成单一可验证审计链
    trusted_audit = build_trusted_audit(state)
    # 方案 C Phase 1：把 A/B/E 的质量信号聚合成编译器产物评分（QualityReport）
    evaluation = CompilerOutputEvaluator().evaluate(state, trusted_audit=trusted_audit).model_dump()
    # 方案 C Phase 2：把评测结果接进现有 FeedbackStore 自进化闭环
    bridge = get_default_bridge()
    bridge.record(evaluation, state, session_id)
    evolution = {"recent_feedback": bridge.recent(limit=5), "stats": bridge.stats()}
    return {
        "session_id": session_id,
        "sop": {
            "sops": sop.get("sops", []),
            "_citation_coverage": sop.get("_citation_coverage", {}),
        },
        "risk": {
            "overall_score": risk.get("overall_score"),
            "gate": risk.get("gate", {}),
            "coverage": risk.get("coverage", {}),
            "risks": risk.get("risks", []),
        },
        "business_model": state.get("business_model", {}),
        "trusted_audit": trusted_audit,
        "evaluation": evaluation,
        "evolution": evolution,
    }
