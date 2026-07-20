# app/api/orchestrate.py
from __future__ import annotations
import asyncio
import inspect
import json
import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.core.config import settings
from app.db import get_db
from app.orchestrator.contracts import EventType, JobStatus, is_terminal
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.event_store import SQLiteEventStore
from app.orchestrator.runtime_engine import RuntimeOrchestratorEngine
from app.orchestrator.sse import SessionEventBus
from app.core.context_policy import ContextPolicy
from app.services.llm_service import LLMService
from app.audit import build_trusted_audit
from app.evaluation import CompilerOutputEvaluator
from app.evolution import get_default_bridge

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])


def build_event_bus() -> SessionEventBus:
    return SessionEventBus(event_store=SQLiteEventStore(get_db()))


_bus = build_event_bus()
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
                    async def publish_cancellation() -> None:
                        event = await _bus.publish(
                            session_id,
                            EventType.PIPELINE_CANCELLED,
                            status=JobStatus.CANCELLED.value,
                            message="Pipeline cancelled",
                            terminal=True,
                        )
                        repo.record_event(event)

                    completed.get_loop().create_task(publish_cancellation())
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
    try:
        context_policy = ContextPolicy(str(body.get("context_policy") or ContextPolicy.FRESH.value))
    except ValueError as exc:
        raise HTTPException(400, "invalid context_policy") from exc
    context_items: list[dict] = []
    parent_session_id = str(body.get("parent_session_id") or "")
    tenant_id, project_id, owner_session_id = _creation_scope(request, body, sid)
    if context_policy is not ContextPolicy.FRESH:
        if not parent_session_id:
            raise HTTPException(400, "parent_session_id required for inherited context")
        parent = _get_scoped_draft(request, parent_session_id, repo=ProjectDraftRepository())
        requested_project = str(
            body.get("project_id")
            or getattr(request.state, "project_id", None)
            or ""
        )
        if requested_project:
            if parent.project_id and parent.project_id != project_id:
                raise HTTPException(status_code=404, detail="session not found")
        else:
            project_id = parent.project_id or project_id
        if context_policy is ContextPolicy.RESUME and not is_terminal(parent.status):
            raise HTTPException(409, "resume source must be terminal")
        context_items = [
            {"role": "user", "content": parent.idea, "source_session_id": parent.session_id, "priority": 80},
            {
                "role": "runtime",
                "content": json.dumps(
                    {"project": parent.project, "business_model": parent.business_model, "risk": parent.risk},
                    ensure_ascii=False,
                ),
                "source_session_id": parent.session_id,
                "priority": 50,
            },
        ]
    repo = ProjectDraftRepository()
    if repo.get(sid) is not None:
        raise HTTPException(status_code=409, detail="session already exists")
    # 立即落库，保证客户端拿到的 session_id 可立即查询（流水线在后台跑）
    repo.save(ProjectDraft(
        session_id=sid,
        tenant_id=tenant_id,
        project_id=project_id,
        owner_session_id=owner_session_id,
        idea=idea.strip(),
        status=JobStatus.QUEUED.value,
    ))
    if settings.BSC_RUNTIME_MODE == "business_runtime":
        engine = RuntimeOrchestratorEngine(repo=repo, bus=_bus)
        runtime_kwargs = {"project_id": project_id}
        if _accepts_keyword(engine.run_pipeline, "tenant_id"):
            runtime_kwargs["tenant_id"] = tenant_id
        if _accepts_keyword(engine.run_pipeline, "owner_session_id"):
            runtime_kwargs["owner_session_id"] = owner_session_id
        if _accepts_keyword(engine.run_pipeline, "context_policy"):
            runtime_kwargs["context_policy"] = context_policy.value
            runtime_kwargs["context_items"] = context_items
        _retain_task(
            sid,
            engine.run_pipeline(
                sid,
                idea.strip(),
                **runtime_kwargs,
            ),
        )
    else:
        llm = LLMService(force_mock=settings.LLM_PROVIDER == "mock")
        engine = OrchestratorEngine(agents=build_agents(llm), repo=repo, bus=_bus)
        _retain_task(sid, engine.run_pipeline(sid, idea.strip()))
    return {
        "session_id": sid,
        "status": JobStatus.QUEUED.value,
        "status_url": f"/api/orchestrate/{sid}",
        "events_url": f"/api/orchestrate/{sid}/events",
        "context_policy": context_policy.value,
        "parent_session_id": parent_session_id or None,
    }


@router.get("/stream")
async def stream(request: Request, session_id: str, after: int = 0):
    _get_scoped_draft(request, session_id)
    return _event_response(session_id, _resume_after(request, after))


@router.get("/{session_id}")
async def get_status(request: Request, session_id: str):
    draft = _get_scoped_draft(request, session_id)
    return {
        "session_id": session_id,
        "tenant_id": draft.tenant_id,
        "project_id": draft.project_id,
        "status": draft.status,
        "terminal": is_terminal(draft.status),
        "current_stage": draft.current_stage,
        "error_code": draft.error_code,
        "error_message": draft.error_message,
        "event_seq": draft.event_seq,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "completed_at": draft.completed_at,
    }


@router.delete("/{session_id}", status_code=202)
async def cancel(request: Request, session_id: str):
    _require_write_access(request)
    draft = _get_scoped_draft(request, session_id)
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
    _get_scoped_draft(request, session_id)
    return _event_response(session_id, _resume_after(request, after))


@router.get("/dashboard/{session_id}")
async def dashboard(request: Request, session_id: str):
    """将编译后的 ProjectDraft 重塑为仪表盘可用的负载。"""
    repo = ProjectDraftRepository()
    draft = _get_scoped_draft(request, session_id, repo=repo)
    if not is_terminal(draft.status):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_not_terminal",
                "status": draft.status,
                "message": "Task has not reached a terminal state",
            },
        )
    if draft.status == JobStatus.FAILED.value:
        raise HTTPException(
            status_code=422,
            detail={
                "code": draft.error_code or "task_failed",
                "status": draft.status,
                "message": draft.error_message or "Task failed",
            },
        )
    if draft.status != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_not_completed",
                "status": draft.status,
                "message": "Task did not produce a completed dashboard",
            },
        )
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
    runtime = _runtime_metadata(state)
    return {
        "session_id": session_id,
        "execution": {
            "status": draft.status,
            "degraded": bool(runtime.get("degraded")) or "fallback" in runtime.get("stage_modes", {}).values(),
            "stage_modes": runtime.get("stage_modes", {}),
            "capability_executions": runtime.get("capability_executions", []),
        },
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


def _creation_scope(request: Request, body: dict, session_id: str) -> tuple[str, str, str]:
    role = getattr(request.state, "auth_role", "")
    if role in {"reader", "project_reader"}:
        raise HTTPException(status_code=403, detail="read-only key cannot create jobs")
    tenant_id = str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))
    bound_project = getattr(request.state, "project_id", None)
    requested_project = str(body.get("project_id") or "")
    if bound_project and requested_project and requested_project != bound_project:
        raise HTTPException(status_code=403, detail="project key is bound to another project")
    project_id = str(bound_project or requested_project or session_id)
    owner_session_id = str(getattr(request.state, "browser_session_id", ""))
    if not owner_session_id:
        raise HTTPException(status_code=401, detail="secure browser session required")
    return tenant_id, project_id, owner_session_id


def _get_scoped_draft(request: Request, session_id: str, *, repo=None) -> ProjectDraft:
    repo = repo or ProjectDraftRepository()
    draft = repo.get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    tenant_id = str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))
    project_id = getattr(request.state, "project_id", None)
    owner_session_id = str(getattr(request.state, "browser_session_id", ""))
    # Legacy rows with blank boundaries stay readable to preserve the A-C
    # compatibility window. Every new execution has all three values.
    if draft.tenant_id and draft.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="session not found")
    if project_id and draft.project_id and draft.project_id != project_id:
        raise HTTPException(status_code=404, detail="session not found")
    if draft.owner_session_id and draft.owner_session_id != owner_session_id:
        raise HTTPException(status_code=404, detail="session not found")
    return draft


def _require_write_access(request: Request) -> None:
    if getattr(request.state, "auth_role", "") in {"reader", "project_reader"}:
        raise HTTPException(status_code=403, detail="read-only key cannot modify jobs")


def _runtime_metadata(state: dict) -> dict:
    for candidate in (
        state.get("business_model", {}).get("_runtime"),
        state.get("sop", {}).get("_runtime"),
        state.get("review", {}).get("runtime"),
    ):
        if isinstance(candidate, dict):
            return candidate
    for message in state.get("messages", []):
        if isinstance(message, dict) and isinstance(message.get("runtime"), dict):
            return message["runtime"]
    return {}


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    parameters = inspect.signature(callable_obj).parameters.values()
    return any(
        parameter.name == keyword or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
