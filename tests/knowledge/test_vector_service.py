import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.embeddings import EmbeddingProvider


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_service_registers_vector_backend():
    svc = _tmp_service()
    assert "vector" in svc.backends
    assert isinstance(svc.backends["vector"], VectorBackend)


def test_retrieve_fuses_three_ways():
    # 用自定义 provider：让「改写 query」仅向量路命中，验证 vector 已并入 rrf_fuse。
    class ParaphraseProvider(EmbeddingProvider):
        name = "paraphrase"
        dim = 3

        def embed(self, texts):
            out = []
            for t in texts:
                if "用户反馈" in t or "投诉" in t or "处理" in t:
                    out.append([1.0, 0.0, 0.0])
                else:
                    out.append([0.0, 0.0, 1.0])
            return out

    svc = _tmp_service()
    svc.backends["vector"] = VectorBackend(svc.repo, provider=ParaphraseProvider())
    svc.ingest("用户反馈应对流程 与 售后 客服 安抚", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 产地", project_id="p1", title="B")
    res = svc.retrieve("客户投诉处理")  # 字面无交集，仅向量命中 A
    assert res and res[0]["doc_title"] == "A"


def test_remote_unavailable_retrieve_still_works():
    class FailingProvider(EmbeddingProvider):
        name = "failing"

        def embed(self, texts):
            raise RuntimeError("embedding down")

    svc = _tmp_service()
    svc.backends["vector"] = VectorBackend(svc.repo, provider=FailingProvider())
    svc.ingest("内容安全平台 过滤 违规 信息", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 分析", project_id="p1", title="B")
    # 向量后端整批失败 → 不写向量 → 检索退化为 keyword+tfidf，仍可用
    res = svc.retrieve("内容安全 违规")
    assert res and res[0]["doc_title"] == "A"


def test_delete_clears_vectors():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台 过滤 违规 信息", title="A")
    repo = svc.repo
    before = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert before > 0
    assert svc.delete_document(doc_id) is True
    after = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert after == 0


def test_empty_query_returns_empty():
    svc = _tmp_service()
    assert svc.retrieve("") == []
    assert svc.retrieve("   ") == []
