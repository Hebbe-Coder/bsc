"""ensure_schema 幂等加列迁移测试（doc_format / content_hash / version）。"""
import tempfile
import os

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema


def test_ensure_schema_idempotent_adds_columns():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        repo = KnowledgeRepository(f.name)
        ensure_schema(repo)
        ensure_schema(repo)  # 二次调用不报错（幂等）
        rows = repo._execute("PRAGMA table_info(knowledge_docs)").fetchall()
        cols = [r["name"] for r in rows]
        for c in ("doc_format", "content_hash", "version"):
            assert c in cols
    finally:
        repo.close()
        os.remove(f.name)
