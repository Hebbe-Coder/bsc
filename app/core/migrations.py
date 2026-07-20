"""Non-destructive persistence migrations shared by SQLite and PostgreSQL."""

from __future__ import annotations

import time
from typing import Any


_DRAFT_COLUMNS = {
    "tenant_id": "tenant_id TEXT NOT NULL DEFAULT ''",
    "project_id": "project_id TEXT NOT NULL DEFAULT ''",
    "owner_session_id": "owner_session_id TEXT NOT NULL DEFAULT ''",
    "idea": "idea TEXT NOT NULL DEFAULT ''",
    "project": "project TEXT NOT NULL DEFAULT '{}'",
    "requirements": "requirements TEXT NOT NULL DEFAULT '[]'",
    "business_model": "business_model TEXT NOT NULL DEFAULT '{}'",
    "sop": "sop TEXT NOT NULL DEFAULT '{}'",
    "risk": "risk TEXT NOT NULL DEFAULT '{}'",
    "review": "review TEXT NOT NULL DEFAULT '{}'",
    "presentation": "presentation TEXT NOT NULL DEFAULT '{}'",
    "status": "status TEXT NOT NULL DEFAULT 'queued'",
    "current_stage": "current_stage TEXT NOT NULL DEFAULT ''",
    "error_code": "error_code TEXT",
    "error_message": "error_message TEXT",
    "event_seq": "event_seq INTEGER NOT NULL DEFAULT 0",
    "messages": "messages TEXT NOT NULL DEFAULT '[]'",
    "created_at": "created_at TEXT NOT NULL DEFAULT ''",
    "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
    "completed_at": "completed_at TEXT",
}


def ensure_persistence_schema(database: Any) -> None:
    """Apply idempotent, additive migrations without dropping existing data."""
    database.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )"""
    )
    completed = {
        _row_value(row, "version", 0)
        for row in database.execute("SELECT version FROM schema_migrations").fetchall()
    }
    _create_or_upgrade_runtime_tables(database)
    if 1 not in completed:
        database.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (1, "runtime_persistence_boundaries", _timestamp()),
        )
    if 2 not in completed:
        _normalize_legacy_job_statuses(database)
        database.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (2, "canonical_orchestrator_job_statuses", _timestamp()),
        )
    database.commit()


def _create_or_upgrade_runtime_tables(database: Any) -> None:
    database.execute(
        """CREATE TABLE IF NOT EXISTS agent_project_drafts (
            session_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            owner_session_id TEXT NOT NULL DEFAULT '',
            idea TEXT NOT NULL DEFAULT '',
            project TEXT NOT NULL DEFAULT '{}',
            requirements TEXT NOT NULL DEFAULT '[]',
            business_model TEXT NOT NULL DEFAULT '{}',
            sop TEXT NOT NULL DEFAULT '{}',
            risk TEXT NOT NULL DEFAULT '{}',
            review TEXT NOT NULL DEFAULT '{}',
            presentation TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued',
            current_stage TEXT NOT NULL DEFAULT '',
            error_code TEXT,
            error_message TEXT,
            event_seq INTEGER NOT NULL DEFAULT 0,
            messages TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT
        )"""
    )
    _validate_draft_primary_key(database)
    _add_missing_columns(database, "agent_project_drafts", _DRAFT_COLUMNS)
    database.execute(
        """CREATE INDEX IF NOT EXISTS idx_drafts_tenant_project_session
           ON agent_project_drafts (tenant_id, project_id, session_id)"""
    )
    database.execute(
        """CREATE INDEX IF NOT EXISTS idx_drafts_owner_session
           ON agent_project_drafts (owner_session_id, session_id)"""
    )

    database.execute(
        """CREATE TABLE IF NOT EXISTS orchestrator_events (
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL CHECK (seq > 0),
            tenant_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            terminal INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (session_id, seq)
        )"""
    )
    _add_missing_columns(
        database,
        "orchestrator_events",
        {
            "tenant_id": "tenant_id TEXT NOT NULL DEFAULT ''",
            "project_id": "project_id TEXT NOT NULL DEFAULT ''",
        },
    )
    database.execute(
        """CREATE INDEX IF NOT EXISTS idx_events_tenant_project_session_seq
           ON orchestrator_events (tenant_id, project_id, session_id, seq)"""
    )

    database.execute(
        """CREATE TABLE IF NOT EXISTS skill_executions (
            execution_id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            error TEXT NOT NULL DEFAULT '',
            streaming INTEGER NOT NULL DEFAULT 0,
            params TEXT NOT NULL DEFAULT '{}',
            provider TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            from_cache INTEGER NOT NULL DEFAULT 0,
            manifest_revision TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )"""
    )
    database.execute(
        """CREATE INDEX IF NOT EXISTS idx_skill_executions_skill_created
           ON skill_executions (skill_id, created_at)"""
    )

    # Legacy repositories also use this configured backend. These tables are
    # additive so a clean checkout and an upgraded installation share a schema.
    database.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            label TEXT DEFAULT '',
            version INTEGER DEFAULT 1,
            data TEXT NOT NULL DEFAULT '{}',
            source_prd TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            tags TEXT DEFAULT '[]',
            uploaded_at TEXT DEFAULT ''
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_index (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            asset_id TEXT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            category TEXT DEFAULT ''
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            entity_type TEXT DEFAULT 'general',
            description TEXT DEFAULT '',
            attributes TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS graph_snapshots (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            snapshot_type TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT ''
        )"""
    )
    _add_missing_columns(
        database,
        "knowledge_entities",
        {
            "name": "name TEXT NOT NULL DEFAULT ''",
            "entity_type": "entity_type TEXT DEFAULT 'general'",
            "attributes": "attributes TEXT DEFAULT '{}'",
            "project_id": "project_id TEXT DEFAULT ''",
            "category": "category TEXT NOT NULL DEFAULT 'general'",
            "title": "title TEXT NOT NULL DEFAULT ''",
            "version_number": "version_number INTEGER DEFAULT 1",
            "data": "data TEXT NOT NULL DEFAULT '{}'",
            "status": "status TEXT DEFAULT 'active'",
            "domain": "domain TEXT DEFAULT 'general'",
            "tags": "tags TEXT DEFAULT '[]'",
        },
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_versions (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    _add_missing_columns(
        database,
        "graph_snapshots",
        {
            "snapshot_type": "snapshot_type TEXT NOT NULL DEFAULT 'snapshot'",
            "name": "name TEXT NOT NULL DEFAULT ''",
            "domain": "domain TEXT DEFAULT 'general'",
            "version": "version TEXT DEFAULT '1.0.0'",
            "node_count": "node_count INTEGER DEFAULT 0",
            "edge_count": "edge_count INTEGER DEFAULT 0",
        },
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS graph_nodes_persistent (
            id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            owner TEXT DEFAULT '',
            domain TEXT DEFAULT 'general',
            project_id TEXT DEFAULT '',
            entity_ref TEXT DEFAULT '',
            properties TEXT DEFAULT '{}',
            weight REAL DEFAULT 1.0,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ''
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS graph_edges_persistent (
            id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            label TEXT DEFAULT '',
            weight REAL DEFAULT 1.0,
            properties TEXT DEFAULT '{}',
            created_at TEXT DEFAULT ''
        )"""
    )

    database.execute(
        """CREATE TABLE IF NOT EXISTS artifact_records (
            artifact_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    database.execute(
        """CREATE INDEX IF NOT EXISTS idx_artifacts_tenant_project_session
           ON artifact_records (tenant_id, project_id, session_id, artifact_id)"""
    )


def _normalize_legacy_job_statuses(database: Any) -> None:
    """Map historical projection labels into the orchestrator state machine."""
    database.execute(
        """UPDATE agent_project_drafts
           SET status = CASE
               WHEN status = 'done' THEN 'completed'
               WHEN status = 'planned' OR status LIKE 'edited:%' THEN 'queued'
               ELSE 'failed'
           END,
           error_code = CASE
               WHEN status NOT IN ('queued', 'running', 'completed', 'failed', 'cancelled',
                                   'done', 'planned')
                    AND status NOT LIKE 'edited:%'
                    THEN COALESCE(error_code, 'legacy_invalid_status')
               ELSE error_code
           END,
           error_message = CASE
               WHEN status NOT IN ('queued', 'running', 'completed', 'failed', 'cancelled',
                                   'done', 'planned')
                    AND status NOT LIKE 'edited:%'
                    THEN COALESCE(error_message, 'Legacy task status was normalized')
               ELSE error_message
           END
           WHERE status NOT IN ('queued', 'running', 'completed', 'failed', 'cancelled')"""
    )
    database.execute(
        """UPDATE agent_project_drafts
           SET completed_at = COALESCE(completed_at, ?)
           WHERE status IN ('completed', 'failed', 'cancelled')""",
        (_timestamp(),),
    )


def _add_missing_columns(database: Any, table: str, definitions: dict[str, str]) -> None:
    existing = _columns(database, table)
    for name, definition in definitions.items():
        if name not in existing:
            database.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _validate_draft_primary_key(database: Any) -> None:
    dialect = getattr(database, "dialect", "sqlite")
    if dialect == "postgresql":
        rows = database.execute(
            """SELECT kcu.column_name
               FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu
                 ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
               WHERE tc.table_schema = current_schema()
                 AND tc.table_name = 'agent_project_drafts'
                 AND tc.constraint_type = 'PRIMARY KEY'"""
        ).fetchall()
        primary_columns = {str(_row_value(row, "column_name", 0)) for row in rows}
    else:
        rows = database.execute("PRAGMA table_info(agent_project_drafts)").fetchall()
        primary_columns = {
            str(_row_value(row, "name", 1))
            for row in rows
            if int(_row_value(row, "pk", 5) or 0) > 0
        }
    if primary_columns != {"session_id"}:
        raise RuntimeError(
            "agent_project_drafts requires a session_id primary key; "
            "automatic destructive migration is refused"
        )


def _columns(database: Any, table: str) -> set[str]:
    dialect = getattr(database, "dialect", "sqlite")
    if dialect == "postgresql":
        rows = database.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = ?""",
            (table,),
        ).fetchall()
        return {str(_row_value(row, "column_name", 0)) for row in rows}
    rows = database.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(_row_value(row, "name", 1)) for row in rows}


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return row[index]


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
