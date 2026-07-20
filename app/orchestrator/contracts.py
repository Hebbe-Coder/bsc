from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
})


def is_terminal(status: JobStatus | str) -> bool:
    try:
        value = status if isinstance(status, JobStatus) else JobStatus(status)
    except ValueError:
        return False
    return value in TERMINAL_STATUSES


class EventType(str, Enum):
    PIPELINE_STARTED = "pipeline.started"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_LOOPBACK = "stage.loopback"
    CAPABILITY_STARTED = "capability.started"
    CAPABILITY_COMPLETED = "capability.completed"
    CAPABILITY_FAILED = "capability.failed"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_CANCELLED = "pipeline.cancelled"


class OrchestratorEvent(BaseModel):
    session_id: str = Field(min_length=1)
    seq: int = Field(gt=0)
    type: EventType
    stage: str = "pipeline"
    status: str
    message: str = ""
    terminal: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    session_id: str
    status: JobStatus
    terminal: bool
