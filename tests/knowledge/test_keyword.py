import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.keyword import KeywordBackend

def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo

def test_keyword_backend_bm25():
    repo = _tmp_repo()
    kb = KeywordBackend(repo)
    recs = [
        {"id": "c1", "content": "内容安全平台用于过滤违规信息", "doc_id": "d1"},
        {"id": "c2", "content": "今天天气真好适合出游", "doc_id": "d1"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    kb.index(recs)
    res = kb.search("内容安全平台")
    assert res and res[0] == "c1"


def test_postgresql_keyword_search_uses_scoped_like_without_sqlite_fts():
    class _PostgresBackend:
        dialect = "postgresql"

    class _Rows:
        def fetchall(self):
            return [{"chunk_id": "chunk-1"}]

    class _Repository:
        def __init__(self):
            self.backend = _PostgresBackend()
            self.calls = []

        def _get_connection(self):
            return self.backend

        def _execute(self, sql, params=()):
            self.calls.append((sql, params))
            return _Rows()

    repo = _Repository()

    result = KeywordBackend(repo).search("knowledge growth", project_id="project-a", limit=7)

    assert result == ["chunk-1"]
    assert len(repo.calls) == 1
    sql, params = repo.calls[0]
    assert "MATCH" not in sql
    assert "bm25" not in sql
    assert "c.content LIKE ?" in sql
    assert params == ("%knowledge growth%", "project-a", 7)
