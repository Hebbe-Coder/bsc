from app.knowledge.reranker import (
    get_reranker, MockReranker, NoOpReranker, LocalCrossEncoderReranker,
)


def _cands():
    return [
        {"chunk_id": "a", "content": "苹果 香蕉 水果", "score": 0.3},
        {"chunk_id": "b", "content": "苹果 蔬菜", "score": 0.2},
        {"chunk_id": "c", "content": "汽车 引擎", "score": 0.1},
    ]


def test_mock_rerank_orders_by_query_hits():
    out = MockReranker().rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]
    assert "rerank_score" in out[0]


def test_noop_passthrough():
    out = NoOpReranker().rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]


def test_get_reranker_none_returns_noop():
    assert isinstance(get_reranker("none"), NoOpReranker)


def test_local_degrades_when_model_load_fails():
    r = LocalCrossEncoderReranker()
    r._model = False  # 模拟加载失败
    out = r.rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]  # 降级原序
