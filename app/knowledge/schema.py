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


_WIKI_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_vaults (
        project_id TEXT PRIMARY KEY, vault_path TEXT NOT NULL, status TEXT NOT NULL,
        configured_by TEXT DEFAULT '', metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_sources (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_type TEXT NOT NULL,
        origin TEXT DEFAULT '', vault_path TEXT DEFAULT '', content_hash TEXT NOT NULL,
        raw_content TEXT NOT NULL DEFAULT '',
        trust_level TEXT NOT NULL DEFAULT 'untrusted', status TEXT NOT NULL,
        metadata_json TEXT DEFAULT '{}', supersedes_id TEXT,
        captured_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_wiki_pages (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, path TEXT NOT NULL,
        title TEXT DEFAULT '', page_kind TEXT DEFAULT 'general', content_hash TEXT DEFAULT '',
        version INTEGER NOT NULL DEFAULT 1, metadata_json TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'published', published_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, path))""",
    """CREATE TABLE IF NOT EXISTS knowledge_wiki_page_revisions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wiki_page_id TEXT NOT NULL,
        version INTEGER NOT NULL, content_hash TEXT NOT NULL, content TEXT NOT NULL,
        proposal_id TEXT DEFAULT '', created_at TEXT NOT NULL,
        UNIQUE(wiki_page_id, version))""",
    """CREATE TABLE IF NOT EXISTS knowledge_proposals (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, base_revision TEXT DEFAULT '',
        source_ids_json TEXT DEFAULT '[]', operations_json TEXT NOT NULL DEFAULT '[]',
        rationale TEXT DEFAULT '', status TEXT NOT NULL, eval_summary_json TEXT DEFAULT '{}',
        manual INTEGER NOT NULL DEFAULT 0, actor_id TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_proposal_operations (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, project_id TEXT NOT NULL,
        operation_index INTEGER NOT NULL, operation_type TEXT NOT NULL, target_path TEXT NOT NULL,
        destination_path TEXT DEFAULT '', expected_content_hash TEXT DEFAULT '', content TEXT DEFAULT '',
        source_ids_json TEXT DEFAULT '[]', UNIQUE(proposal_id, operation_index))""",
    """CREATE TABLE IF NOT EXISTS knowledge_citations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wiki_page_id TEXT NOT NULL,
        source_id TEXT NOT NULL, anchor TEXT DEFAULT '', claim_text TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_type TEXT NOT NULL,
        trigger TEXT NOT NULL, status TEXT NOT NULL, actor_id TEXT DEFAULT '',
        input_refs_json TEXT DEFAULT '{}', output_refs_json TEXT DEFAULT '{}', error TEXT DEFAULT '',
        retry_of TEXT, started_at TEXT, completed_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_run_events (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT NOT NULL,
        sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        UNIQUE(run_id, sequence))""",
    """CREATE TABLE IF NOT EXISTS knowledge_schedules (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL,
        cron TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, timezone TEXT NOT NULL,
        last_run_at TEXT, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_schedule_claims (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, run_id TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(project_id, job_type, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS knowledge_distillations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, week TEXT NOT NULL,
        knowledge_path TEXT NOT NULL, content_path TEXT NOT NULL, context_path TEXT NOT NULL,
        source_cutoff TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(project_id, week, source_cutoff))""",
    """CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, from_id TEXT NOT NULL,
        to_id TEXT NOT NULL, edge_type TEXT NOT NULL, metadata_json TEXT DEFAULT '{}',
        revision TEXT DEFAULT '', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_eval_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, proposal_id TEXT,
        wiki_revision TEXT DEFAULT '', status TEXT NOT NULL, summary_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_eval_cases (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, case_id TEXT NOT NULL,
        case_type TEXT NOT NULL, expected_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, case_id))""",
]


def ensure_schema(repo: Any) -> None:
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    for sql in _COMMON_SCHEMA:
        repo._execute(sql)
    for sql in _WIKI_SCHEMA:
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
    _ensure_columns(
        repo,
        "knowledge_sources",
        ("ALTER TABLE knowledge_sources ADD COLUMN raw_content TEXT NOT NULL DEFAULT ''",),
    )
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_pm_project_user ON project_members(project_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_project ON knowledge_docs(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_domain ON knowledge_docs(domain)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_access ON knowledge_docs(access_level)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON knowledge_chunks(doc_id)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_access ON knowledge_chunks(access_level)",
        "CREATE INDEX IF NOT EXISTS idx_kw_sources_project_status ON knowledge_sources(project_id,status,captured_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_sources_project_hash ON knowledge_sources(project_id,content_hash)",
        "CREATE INDEX IF NOT EXISTS idx_kw_pages_project_path ON knowledge_wiki_pages(project_id,path)",
        "CREATE INDEX IF NOT EXISTS idx_kw_page_revisions_page_version ON knowledge_wiki_page_revisions(wiki_page_id,version)",
        "CREATE INDEX IF NOT EXISTS idx_kw_proposals_project_status ON knowledge_proposals(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_runs_project_created ON knowledge_runs(project_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_run_events_project_run_sequence ON knowledge_run_events(project_id,run_id,sequence)",
        "CREATE INDEX IF NOT EXISTS idx_kw_schedules_project_job ON knowledge_schedules(project_id,job_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_graph_project_type ON knowledge_graph_edges(project_id,edge_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_eval_cases_project ON knowledge_eval_cases(project_id,case_type)",
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
