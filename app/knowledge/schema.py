"""Portable knowledge-store schema initialization."""

from __future__ import annotations

from typing import Any


_COMMON_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_docs (
        id TEXT PRIMARY KEY, project_id TEXT, asset_id TEXT,
        title TEXT, source TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY, doc_id TEXT, idx INTEGER,
        content TEXT, section TEXT, metadata_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_tfidf (
        chunk_id TEXT PRIMARY KEY, vector BLOB)""",
    """CREATE TABLE IF NOT EXISTS tfidf_model (
        id INTEGER PRIMARY KEY CHECK (id=1), vocab_json TEXT, idf_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_vectors (
        chunk_id TEXT PRIMARY KEY, model TEXT, dim INTEGER, vector BLOB)""",
    """CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
        role TEXT NOT NULL, joined_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}', rerank_config TEXT DEFAULT '{}')""",
    """CREATE TABLE IF NOT EXISTS project_keys (
        key_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
        label TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES knowledge_projects(id))""",
]


def ensure_schema(repo: Any) -> None:
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    for sql in _COMMON_SCHEMA:
        repo._execute(sql)
    if dialect == "postgresql":
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
                id BIGSERIAL PRIMARY KEY, project_id TEXT,
                query TEXT NOT NULL, expected_chunk_ids TEXT DEFAULT '[]',
                notes TEXT, created_at TEXT NOT NULL)"""
        )
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_fts (
                content TEXT, doc_id TEXT, chunk_id TEXT PRIMARY KEY)"""
        )
    else:
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
                query TEXT NOT NULL, expected_chunk_ids TEXT DEFAULT '[]',
                notes TEXT, created_at TEXT NOT NULL)"""
        )
        try:
            repo._execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
                "content, doc_id UNINDEXED, chunk_id UNINDEXED, tokenize='trigram')"
            )
        except Exception:
            pass

    _ensure_columns(
        repo,
        "knowledge_docs",
        (
            "ALTER TABLE knowledge_docs ADD COLUMN doc_format TEXT",
            "ALTER TABLE knowledge_docs ADD COLUMN content_hash TEXT",
            "ALTER TABLE knowledge_docs ADD COLUMN version INTEGER DEFAULT 1",
            "ALTER TABLE knowledge_docs ADD COLUMN domain TEXT DEFAULT 'general'",
            "ALTER TABLE knowledge_docs ADD COLUMN access_level TEXT DEFAULT 'public'",
        ),
    )
    _ensure_columns(
        repo,
        "knowledge_chunks",
        ("ALTER TABLE knowledge_chunks ADD COLUMN access_level TEXT DEFAULT 'public'",),
    )
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_pm_project_user ON project_members(project_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_project ON knowledge_docs(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_domain ON knowledge_docs(domain)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_access ON knowledge_docs(access_level)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON knowledge_chunks(doc_id)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_access ON knowledge_chunks(access_level)",
    ):
        repo._execute(idx_sql)
    repo._commit()


def _ensure_columns(repo: Any, table: str, statements: tuple[str, ...]) -> None:
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    if dialect == "postgresql":
        rows = repo._execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = ?""",
            (table,),
        ).fetchall()
        existing = {row["column_name"] for row in rows}
    else:
        rows = repo._execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row[1] for row in rows}
    for statement in statements:
        column = statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
        if column not in existing:
            repo._execute(statement)
