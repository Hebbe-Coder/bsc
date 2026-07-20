import asyncio

from app.agent.state import ProjectDraft
from app.orchestrator.contracts import EventType, JobStatus
from app.orchestrator.sse import SessionEventBus


def test_restart_recovery_fails_orphaned_running_job_and_emits_terminal(draft_repo):
    from app.orchestrator.recovery import recover_orphaned_jobs

    draft_repo.save(ProjectDraft(
        session_id="orphaned-1",
        idea="x",
        status=JobStatus.RUNNING.value,
        current_stage="sop",
    ))
    bus = SessionEventBus()

    recovered = asyncio.run(recover_orphaned_jobs(repo=draft_repo, bus=bus))

    draft = draft_repo.get("orphaned-1")
    events = list(bus._history["orphaned-1"])
    assert recovered == ["orphaned-1"]
    assert draft.status == JobStatus.FAILED.value
    assert draft.current_stage == "sop"
    assert draft.error_code == "worker_restarted"
    assert draft.error_message == "Task interrupted by worker restart"
    assert draft.completed_at
    assert draft.event_seq == 1
    assert events[-1].type == EventType.PIPELINE_FAILED
    assert events[-1].terminal is True
    assert events[-1].data["error_code"] == "worker_restarted"


def test_lifespan_invokes_orchestrator_recovery(monkeypatch):
    from app import main

    calls = []

    async def fake_recovery():
        calls.append(True)
        return ["recovered-1"]

    monkeypatch.setattr(main, "recover_orchestrator_jobs_on_startup", fake_recovery)

    async def scenario():
        async with main.lifespan(main.app):
            pass

    asyncio.run(scenario())

    assert calls == [True]
