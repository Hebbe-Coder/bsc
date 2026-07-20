"""Durable, replayable event storage for every configured database backend."""

from __future__ import annotations

import json
import threading
from typing import Any, Protocol

from app.core.migrations import ensure_persistence_schema
from app.orchestrator.contracts import EventType, OrchestratorEvent


class EventStore(Protocol):
    def append(self, event: OrchestratorEvent) -> None: ...

    def events_after(self, session_id: str, after: int) -> list[OrchestratorEvent]: ...

    def latest_event(self, session_id: str) -> OrchestratorEvent | None: ...

    def last_seq(self, session_id: str) -> int: ...


class SQLiteEventStore:
    """Backward-compatible name for the cross-backend durable event store."""

    def __init__(self, connection: Any):
        self._connection = connection
        self._lock = threading.RLock()
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self._lock:
            ensure_persistence_schema(self._connection)

    def append(self, event: OrchestratorEvent) -> None:
        payload = event.model_dump(mode="json")
        tenant_id, project_id = self._scope_for_session(payload["session_id"])
        with self._lock:
            self._connection.execute(
                """INSERT INTO orchestrator_events
                   (session_id, seq, tenant_id, project_id, event_type, stage, status,
                    message, terminal, timestamp, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["session_id"],
                    payload["seq"],
                    tenant_id,
                    project_id,
                    payload["type"],
                    payload["stage"],
                    payload["status"],
                    payload["message"],
                    int(payload["terminal"]),
                    payload["timestamp"],
                    json.dumps(payload["data"], ensure_ascii=False),
                ),
            )
            self._connection.commit()

    def events_after(self, session_id: str, after: int) -> list[OrchestratorEvent]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT session_id, seq, event_type, stage, status, message, terminal,
                          timestamp, data
                   FROM orchestrator_events
                   WHERE session_id = ? AND seq > ?
                   ORDER BY seq ASC""",
                (session_id, after),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def latest_event(self, session_id: str) -> OrchestratorEvent | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT session_id, seq, event_type, stage, status, message, terminal,
                          timestamp, data
                   FROM orchestrator_events
                   WHERE session_id = ?
                   ORDER BY seq DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        return self._event_from_row(row) if row is not None else None

    def last_seq(self, session_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(seq), 0) AS last_seq FROM orchestrator_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(_row_value(row, "last_seq", 0))

    def _scope_for_session(self, session_id: str) -> tuple[str, str]:
        row = self._connection.execute(
            """SELECT tenant_id, project_id FROM agent_project_drafts
               WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
        if row is None:
            return "", ""
        return (
            str(_row_value(row, "tenant_id", 0) or ""),
            str(_row_value(row, "project_id", 1) or ""),
        )

    @staticmethod
    def _event_from_row(row: Any) -> OrchestratorEvent:
        return OrchestratorEvent(
            session_id=_row_value(row, "session_id", 0),
            seq=_row_value(row, "seq", 1),
            type=EventType(_row_value(row, "event_type", 2)),
            stage=_row_value(row, "stage", 3),
            status=_row_value(row, "status", 4),
            message=_row_value(row, "message", 5),
            terminal=bool(_row_value(row, "terminal", 6)),
            timestamp=_row_value(row, "timestamp", 7),
            data=json.loads(_row_value(row, "data", 8)),
        )


DatabaseEventStore = SQLiteEventStore


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return row[index]
