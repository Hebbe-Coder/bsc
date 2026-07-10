import os, tempfile
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
