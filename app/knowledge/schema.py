"""知识库表结构（4 张新表 + FTS5 虚表），与现有 knowledge_index/entities 并存。"""
from __future__ import annotations
from typing import Any

_SCHEMA = [
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
]

def ensure_schema(repo: Any) -> None:
    for sql in _SCHEMA:
        repo._execute(sql)
    try:
        repo._execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
            "content, doc_id UNINDEXED, chunk_id UNINDEXED, tokenize='trigram')")
    except Exception:
        # FTS5 不可用（极端环境）：keyword 后端将降级为空，不影响其他后端
        pass
    # 幂等加列：knowledge_docs 增加 RAG 增强所需字段，列已存在时静默忽略
    for col_sql in (
        "ALTER TABLE knowledge_docs ADD COLUMN doc_format TEXT",
        "ALTER TABLE knowledge_docs ADD COLUMN content_hash TEXT",
        "ALTER TABLE knowledge_docs ADD COLUMN version INTEGER DEFAULT 1",
    ):
        try:
            repo._execute(col_sql)
        except Exception:
            pass
    repo._commit()
