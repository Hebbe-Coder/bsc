import os, tempfile
import numpy as np
import pytest
from app.knowledge.service import KnowledgeService
from app.knowledge.backends.vector import VectorBackend


@pytest.fixture
def svc_env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = KnowledgeService(db_path=p)
    svc.ingest_text("机器学习 模型 训练", project_id="P1", title="ml")
    svc.ingest_text("做菜 食谱 火候", project_id="P1", title="cook")
    yield svc, repo, p
    svc.repo.close(); repo.close()
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def test_mock_vector_excluded_from_fusion(svc_env):
    svc, repo, p = svc_env
    # 默认 EMBEDDING_PROVIDER="mock"
    backend = svc.backends["vector"]
    called = {"n": 0}
    orig = backend.search
    def spy(*a, **k):
        called["n"] += 1
        return orig(*a, **k)
    backend.search = spy
    svc.retrieve("机器学习", project_id="P1", top_k=3)
    assert called["n"] == 0, "mock provider 下 VectorBackend.search 不应被调用"


def test_embedding_model_mismatch_excludes_stale(svc_env):
    svc, repo, p = svc_env
    backend = svc.backends["vector"]
    # 挂到 P1 下一个真实存在的 chunk 上，使 stale 行能经 JOIN 存活，
    # 从而真正验证 search 的 WHERE model=? 过滤（而非被孤儿 JOIN 剔除）。
    cid = backend.repo._execute(
        "SELECT c.id FROM knowledge_chunks c "
        "JOIN knowledge_docs d ON c.doc_id=d.id WHERE d.project_id='P1' LIMIT 1"
    ).fetchone()["id"]
    backend.repo._execute(
        "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, model, dim, vector) "
        "VALUES (?,?,?,?)",
        (cid, "old", 2, np.array([1.0, 0.0], dtype=np.float32).tobytes()))
    backend.repo._commit()
    # 当前 provider（test 默认 mock）查询时不得返回陈旧模型向量
    got = backend.search("anything", project_id="P1", limit=10)
    assert cid not in got


def test_reindex_stale_clears_old_model(svc_env):
    svc, repo, p = svc_env
    backend = svc.backends["vector"]
    backend.repo._execute(
        "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, model, dim, vector) "
        "VALUES (?,?,?,?)",
        ("stale-c2", "old", 2, np.array([1.0, 0.0], dtype=np.float32).tobytes()))
    backend.repo._commit()
    cleared = backend.reindex_stale(project_id="P1")
    assert cleared >= 1
    # 清除后该行不复存在
    remaining = backend.repo._execute(
        "SELECT chunk_id FROM knowledge_vectors WHERE chunk_id=?",
        ("stale-c2",)).fetchall()
    assert remaining == []
