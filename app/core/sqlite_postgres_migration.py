"""Guarded migration of the BSC runtime SQLite database into PostgreSQL.

This is intentionally an operator-run bridge rather than a startup side
effect. Switching a runtime from SQLite to PostgreSQL must not silently drop
or partially copy its durable knowledge and orchestration records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any

from app.core.database import PostgreSQLBackend, init_database
from app.knowledge.growth_repository import GrowthRepository


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SYSTEM_TABLES = {"schema_migrations"}
_TABLE_ORDER = {
    "projects": 10,
    "project_assets": 20,
    "project_documents": 20,
    "knowledge_entities": 30,
    "knowledge_members": 40,
    "graph_snapshots": 50,
    "graph_nodes": 60,
    "graph_edges": 60,
    "knowledge_projects": 70,
    "project_keys": 80,
}


class SQLitePostgresMigrationError(RuntimeError):
    """Raised when the migration cannot prove a non-destructive copy."""


@dataclass(frozen=True)
class TableMigration:
    table: str
    source_rows: int
    target_rows: int
    copied_rows: int
    columns: tuple[str, ...]


@dataclass(frozen=True)
class SQLitePostgresMigrationReport:
    source_path: str
    target_url_configured: bool
    applied: bool
    backup_path: str | None
    migrated_tables: tuple[TableMigration, ...]
    skipped_source_tables: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def migrate_sqlite_to_postgres(
    source_path: str | Path,
    target_url: str,
    *,
    apply: bool = False,
    backup_dir: str | Path | None = None,
    allow_nonempty_target: bool = False,
) -> SQLitePostgresMigrationReport:
    """Copy compatible durable rows after initializing the PostgreSQL schema.

    The target is required to be empty by default. A dry run initializes no
    target schema and writes no backup, allowing operators to inspect exactly
    what will be copied before a cutover.
    """

    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise SQLitePostgresMigrationError(f"SQLite source does not exist: {source}")
    if not target_url.strip():
        raise SQLitePostgresMigrationError("PostgreSQL target URL is required")

    source_connection = _open_sqlite(source)
    target: PostgreSQLBackend | None = None
    try:
        if not apply:
            source_tables = _sqlite_tables(source_connection)
            return SQLitePostgresMigrationReport(
                source_path=str(source),
                target_url_configured=True,
                applied=False,
                backup_path=None,
                migrated_tables=tuple(
                    TableMigration(
                        table=table,
                        source_rows=_sqlite_row_count(source_connection, table),
                        target_rows=0,
                        copied_rows=0,
                        columns=tuple(_sqlite_columns(source_connection, table)),
                    )
                    for table in source_tables
                ),
                skipped_source_tables=(),
                created_at=_now(),
            )

        backup_path = _backup_sqlite(source_connection, source, backup_dir)
        source_connection.close()
        source_connection = _open_sqlite(backup_path)
        source_tables = _sqlite_tables(source_connection)
        target = PostgreSQLBackend(target_url)
        init_database(target)
        GrowthRepository(backend=target).close()
        target_tables = _postgres_tables(target)
        migration_tables = tuple(
            sorted(
                (
                    table
                    for table in source_tables
                    if table in target_tables and table not in _SYSTEM_TABLES
                ),
                key=lambda table: (_TABLE_ORDER.get(table, 100), table),
            )
        )
        skipped_tables = tuple(
            table for table in source_tables if table not in target_tables or table in _SYSTEM_TABLES
        )
        if not allow_nonempty_target:
            occupied = [table for table in migration_tables if _postgres_row_count(target, table)]
            if occupied:
                raise SQLitePostgresMigrationError(
                    "PostgreSQL target already contains migration tables: " + ", ".join(occupied)
                )

        results: list[TableMigration] = []
        for table in migration_tables:
            columns = _shared_columns(source_connection, target, table)
            source_rows = _sqlite_row_count(source_connection, table)
            before_rows = _postgres_row_count(target, table)
            _copy_table(source_connection, target, table, columns)
            target_rows = _postgres_row_count(target, table)
            copied_rows = target_rows - before_rows
            if target_rows < source_rows:
                raise SQLitePostgresMigrationError(
                    f"row-count verification failed for {table}: {target_rows} < {source_rows}"
                )
            results.append(
                TableMigration(
                    table=table,
                    source_rows=source_rows,
                    target_rows=target_rows,
                    copied_rows=copied_rows,
                    columns=columns,
                )
            )
        target.commit()
        return SQLitePostgresMigrationReport(
            source_path=str(source),
            target_url_configured=True,
            applied=True,
            backup_path=str(backup_path),
            migrated_tables=tuple(results),
            skipped_source_tables=skipped_tables,
            created_at=_now(),
        )
    except Exception:
        if target is not None:
            target.rollback()
        raise
    finally:
        source_connection.close()
        if target is not None:
            target.close()


def write_migration_report(report: SQLitePostgresMigrationReport, path: str | Path) -> Path:
    """Persist only operational metadata, never source row bodies or credentials."""

    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def _sqlite_tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return tuple(str(row["name"]) for row in rows if _safe_identifier(str(row["name"])))


def _sqlite_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row["name"]) for row in connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall())


def _sqlite_row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) AS count FROM {_quote(table)}").fetchone()["count"])


def _postgres_tables(target: PostgreSQLBackend) -> set[str]:
    rows = target.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=current_schema() AND table_type='BASE TABLE'"
    ).fetchall()
    return {str(row["table_name"]) for row in rows}


def _postgres_columns(target: PostgreSQLBackend, table: str) -> tuple[str, ...]:
    rows = target.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    return tuple(str(row["column_name"]) for row in rows)


def _postgres_row_count(target: PostgreSQLBackend, table: str) -> int:
    row = target.execute(f"SELECT COUNT(*) AS count FROM {_quote(table)}").fetchone()
    return int(row["count"])


def _shared_columns(
    source: sqlite3.Connection,
    target: PostgreSQLBackend,
    table: str,
) -> tuple[str, ...]:
    source_columns = _sqlite_columns(source, table)
    target_columns = set(_postgres_columns(target, table))
    columns = tuple(column for column in source_columns if column in target_columns)
    if not columns:
        raise SQLitePostgresMigrationError(f"No compatible columns for {table}")
    return columns


def _copy_table(
    source: sqlite3.Connection,
    target: PostgreSQLBackend,
    table: str,
    columns: tuple[str, ...],
) -> None:
    rows = source.execute(
        f"SELECT {', '.join(_quote(column) for column in columns)} FROM {_quote(table)}"
    ).fetchall()
    if not rows:
        return
    target.connect()
    if target._connection is None:  # pragma: no cover - defensive protocol guard
        raise SQLitePostgresMigrationError("PostgreSQL connection was not initialized")
    sql = (
        f"INSERT INTO {_quote(table)} ({', '.join(_quote(column) for column in columns)}) "
        f"VALUES ({', '.join('%s' for _ in columns)}) ON CONFLICT DO NOTHING"
    )
    values = [tuple(row[column] for column in columns) for row in rows]
    with target._connection.cursor() as cursor:
        cursor.executemany(sql, values)


def _backup_sqlite(
    source_connection: sqlite3.Connection,
    source: Path,
    backup_dir: str | Path | None,
) -> Path:
    root = Path(backup_dir).expanduser().resolve() if backup_dir else source.parent / "backups"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{source.stem}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite"
    snapshot = sqlite3.connect(destination)
    try:
        # SQLite's backup API includes committed WAL state in one coherent file.
        source_connection.backup(snapshot)
    finally:
        snapshot.close()
    shutil.copystat(source, destination)
    return destination


def _open_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _safe_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.fullmatch(value))


def _quote(value: str) -> str:
    if not _safe_identifier(value):
        raise SQLitePostgresMigrationError(f"unsafe SQL identifier: {value}")
    return f'"{value}"'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
