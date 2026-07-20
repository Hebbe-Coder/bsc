import asyncio
import threading
import time

import pytest

from app.agent.state import ProjectDraft
from app.orchestrator.contracts import EventType
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.sse import SessionEventBus


class Stub:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def run(self, **kwargs):
        if self.error:
            raise self.error
        return self.payload


def _agents(planner_error=None):
    return {
        "planner": Stub(
            {"project": {"name": "x"}, "requirements": []},
            error=planner_error,
        ),
        "architect": Stub({"business_model": {}}),
        "sop": Stub({"sop": {}}),
        "risk": Stub({"risk": {}}),
        "reviewer": Stub({"review": {"approved": True, "gaps": []}}),
        "presenter": Stub({"presentation": {}}),
    }


def test_success_persists_completed_and_emits_terminal(draft_repo):
    draft_repo.save(ProjectDraft(session_id="ok-1", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = OrchestratorEngine(_agents(), repo=draft_repo, bus=bus)

    asyncio.run(engine.run_pipeline("ok-1", "x"))

    draft = draft_repo.get("ok-1")
    assert draft.status == "completed"
    assert draft.current_stage == "presenter"
    assert draft.completed_at
    events = list(bus._history["ok-1"])
    assert events[-1].type == EventType.PIPELINE_COMPLETED
    assert events[-1].terminal is True
    assert draft.event_seq == events[-1].seq


def test_failure_persists_failed_and_emits_terminal(draft_repo):
    draft_repo.save(ProjectDraft(session_id="bad-1", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = OrchestratorEngine(
        _agents(planner_error=RuntimeError("planner exploded")),
        repo=draft_repo,
        bus=bus,
    )

    with pytest.raises(RuntimeError, match="planner exploded"):
        asyncio.run(engine.run_pipeline("bad-1", "x"))

    draft = draft_repo.get("bad-1")
    assert draft.status == "failed"
    assert draft.current_stage == "planner"
    assert draft.error_code == "pipeline_failed"
    assert draft.error_message == "Pipeline failed"
    assert draft.completed_at
    events = list(bus._history["bad-1"])
    assert events[-1].type == EventType.PIPELINE_FAILED
    assert events[-1].terminal is True
    assert draft.event_seq == events[-1].seq
    assert "planner exploded" not in events[-1].message


def test_cancellation_persists_cancelled_and_emits_terminal(draft_repo):
    class BlockingPlanner:
        async def run(self, **kwargs):
            await asyncio.sleep(60)

    async def scenario():
        agents = _agents()
        agents["planner"] = BlockingPlanner()
        draft_repo.save(ProjectDraft(
            session_id="cancel-1",
            idea="x",
            status="queued",
        ))
        bus = SessionEventBus()
        engine = OrchestratorEngine(agents, repo=draft_repo, bus=bus)
        task = asyncio.create_task(engine.run_pipeline("cancel-1", "x"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return bus

    bus = asyncio.run(scenario())
    assert draft_repo.get("cancel-1").status == "cancelled"
    events = list(bus._history["cancel-1"])
    assert events[-1].type == EventType.PIPELINE_CANCELLED
    assert events[-1].terminal is True


def test_sync_agent_does_not_block_event_loop(draft_repo):
    release = threading.Event()

    class BlockingPlanner:
        def run(self, **kwargs):
            release.wait(timeout=0.5)
            return {"project": {"name": "x"}, "requirements": []}

    async def scenario():
        agents = _agents()
        agents["planner"] = BlockingPlanner()
        draft_repo.save(ProjectDraft(
            session_id="nonblocking-1",
            idea="x",
            status="queued",
        ))
        engine = OrchestratorEngine(
            agents,
            repo=draft_repo,
            bus=SessionEventBus(),
        )
        started = time.perf_counter()
        task = asyncio.create_task(engine.run_pipeline("nonblocking-1", "x"))
        await asyncio.sleep(0.05)
        elapsed = time.perf_counter() - started
        release.set()
        await task
        return elapsed

    assert asyncio.run(scenario()) < 0.2
