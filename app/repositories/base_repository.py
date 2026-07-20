"""Shared repository helpers backed by the configured database abstraction."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import DatabaseBackend, SQLiteBackend
from app.db import get_db


class BaseRepository:
    """Base class for repositories that must honor ``DB_TYPE`` consistently."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        backend: Optional[DatabaseBackend] = None,
    ) -> None:
        # Explicit paths remain available for isolated SQLite tests. Normal
        # application repositories share the configured backend from app.db.
        self._connection = backend or (SQLiteBackend(db_path) if db_path else get_db())
        self._owns_connection = backend is not None or db_path is not None

    def _get_connection(self) -> DatabaseBackend:
        self._connection.connect()
        return self._connection

    def _close_connection(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _execute(self, sql: str, params: tuple = ()) -> Any:
        return self._get_connection().execute(sql, params)

    def _executemany(self, sql: str, params: List[tuple]) -> Any:
        return self._get_connection().executemany(sql, params)

    def _commit(self) -> None:
        self._get_connection().commit()

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        return dict(row) if row else {}

    def _rows_to_list(self, cursor: Any) -> List[Dict[str, Any]]:
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:12]

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def _json_dumps(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False)

    def _json_loads(self, data: str) -> Any:
        return json.loads(data) if data else {}

    def close(self) -> None:
        self._close_connection()

    def __del__(self) -> None:
        self._close_connection()

    @classmethod
    def test_connection(cls) -> bool:
        try:
            repo = cls()
            repo._execute("SELECT 1")
            repo.close()
            return True
        except Exception:
            return False
