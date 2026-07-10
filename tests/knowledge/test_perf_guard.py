import time
from app.knowledge.reranker import MockReranker


def _big_cands(n=100):
    return [{"chunk_id": f"c{i}", "content": f"文档内容片段 {i} 关于主题关键词", "score": 1.0 - i * 0.001}
            for i in range(n)]


def test_mock_rerank_100_candidates_within_budget():
    cands = _big_cands(100)
    start = time.perf_counter()
    out = MockReranker().rerank("主题关键词", cands, top_k=5)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(out) == 5
    assert elapsed_ms < 50.0
