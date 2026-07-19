import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.embeddings import MockEmbeddingProvider, EmbeddingProvider


def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo


def _insert(repo, recs):
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()


def test_vector_index_and_search_cosine():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    recs = [
        {"id": "a", "content": "内容安全平台 违规信息 过滤 审核", "doc_id": "d1"},
        {"id": "b", "content": "咖啡 烘焙 风味 产地", "doc_id": "d2"},
    ]
    _insert(repo, recs)
    vb.index(recs)
    res = vb.search("内容安全 违规 审核")
    assert res and res[0] == "a"


def test_vector_empty_query_returns_empty():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    assert vb.search("") == []
    assert vb.search("   ") == []


def test_vector_incremental_keeps_old():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    recs1 = [{"id": "a", "content": "内容安全 审核", "doc_id": "d1"}]
    _insert(repo, recs1)
    vb.index(recs1)
    recs2 = [{"id": "b", "content": "咖啡 烘焙", "doc_id": "d2"}]
    _insert(repo, recs2)
    vb.index(recs2)  # 仅处理新 chunk，不重建旧
    res = vb.search("内容安全")
    assert "a" in res


def test_vector_beats_keyword_on_paraphrase():
    # 远程不可用场景下的等价离线验证：用自定义 provider 制造「语义近义但字面无交集」。
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

    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=ParaphraseProvider())
    recs = [{"id": "a", "content": "用户反馈应对流程 与 售后 客服 安抚", "doc_id": "d1"}]
    _insert(repo, recs)
    vb.index(recs)
    # 改写 query 与原文字面无交集，但语义近 → 向量命中
    res = vb.search("客户投诉处理")
    assert res and res[0] == "a"
