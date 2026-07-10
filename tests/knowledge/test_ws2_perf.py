import os, tempfile
import pytest
from app.knowledge.backends.tfidf import TfidfBackend


@pytest.fixture
def tf_env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    yield repo, p
    repo.close()
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def _ingest(repo, records):
    """Mirror the real ingest flow: chunks must live in knowledge_chunks
    because _build_and_store_model() reads the corpus from that table."""
    for r in records:
        repo._execute(
            "INSERT OR REPLACE INTO knowledge_chunks "
            "(id, doc_id, idx, content, section, metadata_json) "
            "VALUES (?,?,?,?,?,?)",
            (r["id"], "d", 0, r["content"], "", "{}"))
    repo._commit()


def test_tfidf_incremental_skips_full_revectorize(tf_env):
    repo, p = tf_env
    backend = TfidfBackend(repo)
    calls = {"n": 0}
    orig = backend._vectorize
    def spy(text, vocab, idf):
        calls["n"] += 1
        return orig(text, vocab, idf)
    backend._vectorize = spy

    _ingest(repo, [{"id": "c1", "content": "hello world"},
                   {"id": "c2", "content": "foo bar"}])
    backend.index([{"id": "c1", "content": "hello world"},
                   {"id": "c2", "content": "foo bar"}])
    assert calls["n"] == 2  # 首次：全量向量化
    # 第二次仅追加内容，且用词均在已有词表内 -> 不应触发全量重向量化
    _ingest(repo, [{"id": "c3", "content": "hello foo"}])
    backend.index([{"id": "c3", "content": "hello foo"}])
    assert calls["n"] == 3  # 仅新增 1 个 chunk，而非 2+3=5


def test_tfidf_incremental_add_keeps_search_consistent(tf_env):
    repo, p = tf_env
    backend = TfidfBackend(repo)
    # index() 依赖 knowledge_chunks 已落地（真实 ingest 流程如此），先镜像 ingest
    _ingest(repo, [{"id": "c1", "content": "hello world"},
                    {"id": "c2", "content": "foo bar"}])
    backend.index([{"id": "c1", "content": "hello world"},
                   {"id": "c2", "content": "foo bar"}])
    # 增量追加：仅用已有词表（hello/foo/world/bar），不应触发全量重向量化
    _ingest(repo, [{"id": "c3", "content": "hello foo"}])
    backend.index([{"id": "c3", "content": "hello foo"}])
    # 检索 "hello" 必须能召回 c3（且整体不崩溃、返回非空）
    hits = backend.search("hello", limit=10)
    assert hits, "增量追加后检索不应为空"
    assert "c3" in hits, "增量追加的 chunk 必须可被检索到（idf 一致）"


import os as _os
import tempfile as _tempfile
from app.knowledge.service import KnowledgeService
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.backends.keyword import KeywordBackend


@pytest.fixture
def svc_env():
    fd, p = _tempfile.mkstemp(suffix=".db"); _os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = KnowledgeService(db_path=p)
    svc.ingest_text("alpha 专属内容 检索词X", project_id="PA", title="a")
    svc.ingest_text("beta 专属内容 检索词Y", project_id="PB", title="b")
    yield svc, repo, p
    svc.repo.close(); repo.close()
    _os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: _os.remove(p + suf)
        except OSError: pass


def test_retrieve_isolates_projects(svc_env):
    svc, repo, p = svc_env
    res = svc.retrieve("alpha", project_id="PA", top_k=5)
    assert res, "应至少召回 PA 的文档"
    # 核心断言：PA 检索结果不得包含 PB 的内容
    pb_hit = any("beta" in (r.get("content") or "") for r in res)
    assert not pb_hit, "跨项目泄漏：PA 检索不应包含 PB 内容"


def test_backend_search_respects_project_id(svc_env):
    svc, repo, p = svc_env
    for backend in (KeywordBackend(repo), TfidfBackend(repo), VectorBackend(repo)):
        got = backend.search("专属内容", project_id="PA", limit=20)
        # 所有返回 chunk 必须属于 PA
        for cid in got:
            row = repo._execute(
                "SELECT d.project_id FROM knowledge_chunks c "
                "JOIN knowledge_docs d ON c.doc_id=d.id WHERE c.id=?",
                (cid,)).fetchone()
            assert row["project_id"] == "PA", f"{type(backend).__name__} 跨越了项目边界"
