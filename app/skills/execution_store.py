"""Durable Skill execution state shared by API workers and restarts."""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.migrations import ensure_persistence_schema
from app.db import get_db


class SkillExecutionStore:
    def __init__(self, connection: Any | None = None) -> None:
        self.db = connection or get_db()
        ensure_persistence_schema(self.db)

    def create(self, execution: dict[str, Any]) -> None:
        now = _timestamp()
        self.db.execute(
            """INSERT INTO skill_executions
               (execution_id, skill_id, status, result, error, streaming, params,
                provider, model_name, from_cache, manifest_revision, created_at,
                updated_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution["execution_id"],
                execution["skill_id"],
                execution.get("status", "running"),
                execution.get("result"),
                execution.get("error", ""),
                int(bool(execution.get("streaming", False))),
                json.dumps(execution.get("params", {}), ensure_ascii=False),
                execution.get("provider", ""),
                execution.get("model_name", ""),
                int(bool(execution.get("from_cache", False))),
                execution.get("manifest_revision", ""),
                execution.get("created_at", now),
                now,
                execution.get("completed_at"),
            ),
        )
        self.db.commit()

    def update(self, execution_id: str, **changes: Any) -> dict[str, Any] | None:
        current = self.get(execution_id)
        if current is None:
            return None
        current.update(changes)
        current["updated_at"] = _timestamp()
        if current.get("status") in {"completed", "failed", "cancelled"}:
            current["completed_at"] = current.get("completed_at") or current["updated_at"]
        self.db.execute(
            """UPDATE skill_executions
               SET status=?, result=?, error=?, from_cache=?, updated_at=?, completed_at=?
               WHERE execution_id=?""",
            (
                current.get("status", "running"),
                current.get("result"),
                current.get("error", ""),
                int(bool(current.get("from_cache", False))),
                current["updated_at"],
                current.get("completed_at"),
                execution_id,
            ),
        )
        self.db.commit()
        return current

    def get(self, execution_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM skill_executions WHERE execution_id=?",
            (execution_id,),
        ).fetchone()
        return _row_to_execution(row)

    def delete_by_skill(self, skill_id: str) -> int:
        cursor = self.db.execute(
            "DELETE FROM skill_executions WHERE skill_id=?",
            (skill_id,),
        )
        self.db.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def list_recent(self, *, skill_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 200))
        if skill_id:
            cursor = self.db.execute(
                """SELECT * FROM skill_executions WHERE skill_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (skill_id, bounded_limit),
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM skill_executions ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            )
        return [execution for row in cursor.fetchall() if (execution := _row_to_execution(row))]


def _row_to_execution(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["streaming"] = bool(data.get("streaming"))
    data["from_cache"] = bool(data.get("from_cache"))
    try:
        data["params"] = json.loads(data.get("params") or "{}")
    except (TypeError, json.JSONDecodeError):
        data["params"] = {}
    return data


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
