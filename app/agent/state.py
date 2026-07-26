"""Durable task projection with explicit tenant, project, and browser-session scope."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from app.core.migrations import ensure_persistence_schema
from app.db import get_db


SEGMENTS = (
    "project",
    "requirements",
    "business_model",
    "sop",
    "risk",
    "review",
    "presentation",
)
DRAFT_COLUMNS = (
    "session_id",
    "tenant_id",
    "project_id",
    "owner_session_id",
    "idea",
    "project",
    "requirements",
    "business_model",
    "sop",
    "risk",
    "review",
    "presentation",
    "status",
    "current_stage",
    "error_code",
    "error_message",
    "event_seq",
    "messages",
    "created_at",
    "updated_at",
    "completed_at",
)

WORKER_RESTARTED_ERROR_CODE = "worker_restarted"
WORKER_RESTARTED_ERROR_MESSAGE = "Task interrupted by worker restart"


class ProjectDraft:
    def __init__(
        self,
        session_id: str | None = None,
        tenant_id: str = "",
        project_id: str = "",
        owner_session_id: str = "",
        idea: str = "",
        project: Optional[dict] = None,
        requirements: Optional[list] = None,
        business_model: Optional[dict] = None,
        sop: Optional[dict] = None,
        risk: Optional[dict] = None,
        review: Optional[dict] = None,
        presentation: Optional[dict] = None,
        status: str = "queued",
        messages: Optional[list] = None,
        current_stage: str = "",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        event_seq: int = 0,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.tenant_id = tenant_id or ""
        self.project_id = project_id or ""
        self.owner_session_id = owner_session_id or ""
        self.idea = idea
        self.project = project or {}
        self.requirements = requirements or []
        self.business_model = business_model or {}
        self.sop = sop or {}
        self.risk = risk or {}
        self.review = review or {}
        self.presentation = presentation or {}
        self.status = status
        self.messages = messages or []
        self.current_stage = current_stage or ""
        self.error_code = error_code or None
        self.error_message = error_message or None
        self.event_seq = max(int(event_seq or 0), 0)
        self.created_at = created_at or _timestamp()
        self.updated_at = updated_at or _timestamp()
        self.completed_at = completed_at or None

    def to_dict(self) -> Dict[str, Any]:
        return {column: getattr(self, column) for column in DRAFT_COLUMNS}

    @classmethod
    def from_row(cls, row: Any) -> "ProjectDraft":
        data = dict(row)
        for segment in SEGMENTS:
            value = data.get(segment)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    value = [] if segment == "requirements" else {}
            data[segment] = value or ([] if segment == "requirements" else {})
        messages = data.get("messages")
        data["messages"] = (
            json.loads(messages) if isinstance(messages, str) else (messages or [])
        )
        data["error_code"] = data.get("error_code") or None
        data["error_message"] = data.get("error_message") or None
        data["completed_at"] = data.get("completed_at") or None
        return cls(**{column: data.get(column) for column in DRAFT_COLUMNS})


class ProjectDraftRepository:
    def __init__(self, connection: Any = None) -> None:
        self._db = connection or get_db()
        self._ensure_table()

    def _ensure_table(self) -> None:
        ensure_persistence_schema(self._db)

    def save(self, draft: ProjectDraft) -> None:
        from app.orchestrator.contracts import JobStatus, is_terminal

        existing = self.get(draft.session_id)
        try:
            JobStatus(draft.status)
        except ValueError as exc:
            raise ValueError(f"invalid task status: {draft.status}") from exc
        if existing is not None:
            self._preserve_scope(existing, draft)
            if is_terminal(existing.status):
                if _same_terminal_projection(existing, draft):
                    return
                raise ValueError(
                    f"session {draft.session_id} already terminal: {existing.status}"
                )
            draft.created_at = existing.created_at
            draft.current_stage = draft.current_stage or existing.current_stage
            draft.event_seq = max(draft.event_seq, existing.event_seq)
            draft.error_code = draft.error_code or existing.error_code
            draft.error_message = draft.error_message or existing.error_message
            draft.completed_at = draft.completed_at or existing.completed_at
        draft.updated_at = _timestamp()
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, tenant_id, project_id, owner_session_id, idea, project,
                requirements, business_model, sop, risk, review, presentation, status,
                current_stage, error_code, error_message, event_seq, messages, created_at,
                updated_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               tenant_id=excluded.tenant_id, project_id=excluded.project_id,
               owner_session_id=excluded.owner_session_id, idea=excluded.idea,
               project=excluded.project, requirements=excluded.requirements,
               business_model=excluded.business_model, sop=excluded.sop, risk=excluded.risk,
               review=excluded.review, presentation=excluded.presentation, status=excluded.status,
               current_stage=excluded.current_stage, error_code=excluded.error_code,
               error_message=excluded.error_message, event_seq=excluded.event_seq,
               messages=excluded.messages, created_at=excluded.created_at,
               updated_at=excluded.updated_at, completed_at=excluded.completed_at""",
            (
                draft.session_id,
                draft.tenant_id,
                draft.project_id,
                draft.owner_session_id,
                draft.idea,
                json.dumps(draft.project, ensure_ascii=False),
                json.dumps(draft.requirements, ensure_ascii=False),
                json.dumps(draft.business_model, ensure_ascii=False),
                json.dumps(draft.sop, ensure_ascii=False),
                json.dumps(draft.risk, ensure_ascii=False),
                json.dumps(draft.review, ensure_ascii=False),
                json.dumps(draft.presentation, ensure_ascii=False),
                draft.status,
                draft.current_stage,
                draft.error_code,
                draft.error_message,
                draft.event_seq,
                json.dumps(draft.messages, ensure_ascii=False),
                draft.created_at,
                draft.updated_at,
                draft.completed_at,
            ),
        )
        self._db.commit()

    @staticmethod
    def _preserve_scope(existing: ProjectDraft, draft: ProjectDraft) -> None:
        for field in ("tenant_id", "project_id", "owner_session_id"):
            prior = getattr(existing, field)
            requested = getattr(draft, field)
            if prior and requested and prior != requested:
                raise ValueError(f"session scope cannot change: {field}")
            setattr(draft, field, prior or requested)

    def get(self, session_id: str) -> ProjectDraft | None:
        row = self._db.execute(
            "SELECT * FROM agent_project_drafts WHERE session_id=?", (session_id,)
        ).fetchone()
        return ProjectDraft.from_row(row) if row else None

    def transition(
        self,
        session_id: str,
        status: Any,
        *,
        current_stage: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ProjectDraft:
        from app.orchestrator.contracts import JobStatus, is_terminal

        target = status if isinstance(status, JobStatus) else JobStatus(status)
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        if is_terminal(draft.status):
            raise ValueError(f"session {session_id} already terminal: {draft.status}")
        draft.status = target.value
        if current_stage is not None:
            draft.current_stage = current_stage
        if error_code is not None:
            draft.error_code = error_code
        if error_message is not None:
            draft.error_message = error_message
        if is_terminal(target):
            draft.completed_at = _timestamp()
        self.save(draft)
        return draft

    def record_event(self, event: Any) -> None:
        # PostgreSQL does not coerce SQLite-style integer parameters to boolean
        # inside CASE WHEN. Resolve the terminal branch before executing the
        # shared qmark SQL so both database backends preserve the same stage.
        stage = self.get(event.session_id).current_stage if event.terminal else event.stage
        self._db.execute(
            """UPDATE agent_project_drafts
               SET current_stage = ?,
                   event_seq = ?, updated_at = ?
               WHERE session_id = ? AND event_seq < ?""",
            (
                stage,
                event.seq,
                _timestamp(),
                event.session_id,
                event.seq,
            ),
        )
        self._db.commit()

    def recover_orphaned_jobs(self) -> list[ProjectDraft]:
        rows = self._db.execute(
            "SELECT session_id FROM agent_project_drafts WHERE status = ?", ("running",)
        ).fetchall()
        return [
            self.transition(
                _row_value(row, "session_id", 0),
                "failed",
                error_code=WORKER_RESTARTED_ERROR_CODE,
                error_message=WORKER_RESTARTED_ERROR_MESSAGE,
            )
            for row in rows
        ]

    def patch(self, session_id: str, segment: str, value: Any) -> ProjectDraft:
        from app.orchestrator.contracts import is_terminal

        if segment not in SEGMENTS:
            raise ValueError(f"unknown state segment: {segment}")
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        if is_terminal(draft.status):
            raise ValueError(f"session {session_id} already terminal: {draft.status}")
        setattr(draft, segment, value)
        self.save(draft)
        return draft


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return row[index]


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _same_terminal_projection(existing: ProjectDraft, requested: ProjectDraft) -> bool:
    """Allow idempotent delivery retries without reopening a terminal task."""
    immutable_columns = (
        "tenant_id",
        "project_id",
        "owner_session_id",
        "idea",
        *SEGMENTS,
        "status",
        "current_stage",
        "error_code",
        "error_message",
        "event_seq",
        "messages",
    )
    return all(
        getattr(existing, column) == getattr(requested, column)
        for column in immutable_columns
    )
