from app.knowledge.reranker import (
    get_reranker, MockReranker, NoOpReranker, LocalCrossEncoderReranker, rrf_fuse,
)
from app.core.config import settings


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


def test_get_reranker_falls_back_when_repository_has_no_project_configuration(monkeypatch):
    """Wiki storage is searchable but does not own the legacy project table."""
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")

    reranker = get_reranker(project_id="project-a", repo=object())

    assert isinstance(reranker, MockReranker)


def test_local_degrades_when_model_load_fails():
    r = LocalCrossEncoderReranker()
    r._model = False  # 模拟加载失败
    out = r.rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]  # 降级原序


# --- rrf_fuse 回归覆盖（Task 2 重构时保留，勿删）---

def test_reranker_rrf_agreement():
    fused = rrf_fuse([["a", "b", "c"], ["a", "b", "c"]])
    assert fused[0][0] == "a" and fused[1][0] == "b"
    # 返回 (cid, score) 元组
    assert isinstance(fused[0], tuple) and isinstance(fused[0][1], float)


def test_reranker_rrf_scale_invariant():
    # 只吃排名不吃分数；a 在两榜都靠前 → 总体靠前
    fused = rrf_fuse([["a", "b"], ["c", "a"]])
    assert fused[0][0] == "a"
    # 缺失后端（空榜）仍鲁棒
    fused2 = rrf_fuse([["a", "b"], []])
    assert fused2[0][0] == "a"
