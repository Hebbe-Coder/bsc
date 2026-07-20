from __future__ import annotations

from app.agent.state import ProjectDraftRepository
from app.orchestrator.contracts import EventType, JobStatus
from app.orchestrator.sse import SessionEventBus


async def recover_orphaned_jobs(
    *,
    repo: ProjectDraftRepository,
    bus: SessionEventBus,
) -> list[str]:
    """Fail tasks interrupted by a process restart and close their SSE history."""
    recovered = repo.recover_orphaned_jobs()
    for draft in recovered:
        event = await bus.publish(
            draft.session_id,
            EventType.PIPELINE_FAILED,
            stage="pipeline",
            status=JobStatus.FAILED.value,
            message=draft.error_message or "Pipeline failed",
            terminal=True,
            data={"error_code": draft.error_code},
        )
        repo.record_event(event)
    return [draft.session_id for draft in recovered]
