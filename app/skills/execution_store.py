"""Durable Skill execution state shared by API workers and restarts."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from app.core.migrations import ensure_persistence_schema
from app.db import get_db


logger = logging.getLogger(__name__)
CompletionHook = Callable[[dict[str, Any]], Any]


class SkillExecutionStore:
    def __init__(
        self,
        connection: Any | None = None,
        *,
        completion_hook: CompletionHook | None = None,
    ) -> None:
        self.db = connection or get_db()
        self.completion_hook = completion_hook
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
        previous_status = str(current.get("status") or "")
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
        previous_registration = (current.get("params") or {}).get(
            "_growth_output_registration", {}
        )
        should_retry_registration = (
            isinstance(previous_registration, dict)
            and previous_registration.get("status") == "registration_failed"
        )
        if current.get("status") == "completed" and (
            previous_status != "completed" or should_retry_registration
        ):
            outcome = self._run_completion_hook(current)
            if outcome is not None:
                params = dict(current.get("params") or {})
                params["_growth_output_registration"] = outcome
                self.db.execute(
                    "UPDATE skill_executions SET params=? WHERE execution_id=?",
                    (json.dumps(params, ensure_ascii=False), execution_id),
                )
                self.db.commit()
                current["params"] = params
        return current

    def _run_completion_hook(self, execution: dict[str, Any]) -> dict[str, Any] | None:
        try:
            hook = self.completion_hook or self._default_growth_completion_hook
            result = hook(dict(execution))
            if result is None:
                return None
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            if not isinstance(result, dict):
                raise TypeError("Skill completion hook must return a mapping")
            return result
        except Exception as exc:
            logger.exception("Skill output completion hook failed")
            return {
                "status": "registration_failed",
                "producer_type": "skill",
                "producer_id": str(execution.get("execution_id") or ""),
                "output_id": "",
                "audit_run_id": "",
                "error": str(exc) or exc.__class__.__name__,
            }

    def _default_growth_completion_hook(
        self, execution: dict[str, Any]
    ) -> dict[str, Any] | None:
        from app.core.config import settings

        if not settings.KNOWLEDGE_GROWTH_ENABLED:
            return None
        params = dict(execution.get("params") or {})
        if not str(params.get("project_id") or "").strip():
            return None
        from app.knowledge.growth_repository import GrowthRepository
        from app.knowledge.output_bridges import OutputCompletionBridge

        repository = GrowthRepository(backend=self.db)
        # The execution store owns the shared backend; the short-lived facade
        # must not close it when garbage-collected.
        repository._owns_connection = False
        context = {
            **params,
            "project_id": str(params.get("project_id") or ""),
            "goal": str(params.get("goal") or params.get("input") or ""),
            "audience": str(params.get("audience") or ""),
            "channel": str(params.get("channel") or "skill"),
            "provider": str(execution.get("provider") or ""),
            "model": str(execution.get("model_name") or ""),
            "prompt_revision": str(execution.get("manifest_revision") or ""),
            "metadata": {
                "skill_id": str(execution.get("skill_id") or ""),
                "from_cache": bool(execution.get("from_cache")),
            },
        }
        return OutputCompletionBridge(
            repository, settings.OBSIDIAN_VAULT_ROOT
        ).register_skill_completion(
            execution_id=str(execution.get("execution_id") or ""),
            skill_id=str(execution.get("skill_id") or ""),
            status=str(execution.get("status") or ""),
            result=execution.get("result"),
            context=context,
        ).to_dict()

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
