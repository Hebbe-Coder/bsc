import pytest
from pydantic import ValidationError

from app.orchestrator.contracts import (
    EventType,
    JobStatus,
    OrchestratorEvent,
    is_terminal,
)


def test_terminal_statuses_are_explicit():
    assert is_terminal(JobStatus.COMPLETED)
    assert is_terminal(JobStatus.FAILED)
    assert is_terminal(JobStatus.CANCELLED)
    assert not is_terminal(JobStatus.QUEUED)
    assert not is_terminal(JobStatus.RUNNING)


def test_event_requires_positive_sequence():
    with pytest.raises(ValidationError):
        OrchestratorEvent(
            session_id="s1",
            seq=0,
            type=EventType.PIPELINE_STARTED,
            status="running",
        )


def test_terminal_event_sets_terminal_flag():
    event = OrchestratorEvent(
        session_id="s1",
        seq=1,
        type=EventType.PIPELINE_COMPLETED,
        status="completed",
        terminal=True,
    )
    assert event.terminal is True
    assert event.model_dump(mode="json")["type"] == "pipeline.completed"
