import sqlite3

import pytest

from app.knowledge import schema
from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_repository import WikiRepository


def test_wiki_schema_is_additive_and_idempotent(tmp_path):
    db_path = tmp_path / "wiki-schema.db"
    repo = WikiRepository(db_path=str(db_path))
    try:
        ensure_schema(repo)
        ensure_schema(repo)

        connection = sqlite3.connect(db_path)
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'knowledge_%'"
            )
        }
        expected = {
            "knowledge_vaults",
            "knowledge_sources",
            "knowledge_wiki_pages",
            "knowledge_proposals",
            "knowledge_proposal_operations",
            "knowledge_citations",
            "knowledge_runs",
            "knowledge_schedules",
            "knowledge_distillations",
            "knowledge_graph_edges",
            "knowledge_eval_runs",
        }
        assert expected <= names

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_kw_%'"
            )
        }
        assert {"idx_kw_sources_project_status", "idx_kw_runs_project_created"} <= indexes
    finally:
        repo.close()
        connection.close()


class _PostgresSchemaBackend:
    dialect = "postgresql"

    def __init__(self):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class _PostgresSchemaRepo:
    def __init__(self, backend):
        self.backend = backend

    def _get_connection(self):
        return self.backend

    def _execute(self, sql, params=()):
        self.backend.executed.append((sql, params))

    def _commit(self):
        self.backend.commits += 1


def test_postgres_schema_initialization_uses_one_session_lock_and_caches_success(monkeypatch):
    backend = _PostgresSchemaBackend()
    repo = _PostgresSchemaRepo(backend)
    calls = []
    monkeypatch.setattr(schema, "_ensure_schema_unlocked", lambda value, dialect: calls.append((value, dialect)))

    ensure_schema(repo)
    ensure_schema(repo)

    assert backend.executed == [
        ("SELECT pg_advisory_lock(?)", (schema._POSTGRES_SCHEMA_ADVISORY_LOCK,)),
        ("SELECT pg_advisory_unlock(?)", (schema._POSTGRES_SCHEMA_ADVISORY_LOCK,)),
    ]
    assert calls == [(repo, "postgresql")]
    assert backend.commits == 2
    assert backend.rollbacks == 0


def test_postgres_schema_initialization_rolls_back_and_allows_retry(monkeypatch):
    backend = _PostgresSchemaBackend()
    repo = _PostgresSchemaRepo(backend)
    calls = []

    def fail_once(*_args):
        calls.append("called")
        if len(calls) == 1:
            raise RuntimeError("migration failed")

    monkeypatch.setattr(schema, "_ensure_schema_unlocked", fail_once)

    with pytest.raises(RuntimeError, match="migration failed"):
        ensure_schema(repo)
    ensure_schema(repo)

    assert len(calls) == 2
    assert backend.rollbacks == 1
    assert backend.commits == 3
