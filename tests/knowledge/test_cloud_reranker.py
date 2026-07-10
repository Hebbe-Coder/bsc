from app.knowledge.cloud_reranker import CloudReranker


def _fake_response(payload):
    class R:
        def json(self):
            results = [{"index": i, "relevance_score": s} for i, s in enumerate(payload["_scores"])]
            return {"results": results}
    return R()


def test_cloud_rerank_orders_and_failover(monkeypatch):
    scores = [0.1, 0.9, 0.3]
    called = {"n": 0}

    def fake_post(url, headers, json):
        called["n"] += 1
        if called["n"] == 1:
            raise RuntimeError("key1 dead")
        json["_scores"] = scores
        return _fake_response(json)

    r = CloudReranker(keys=["bad", "good"])
    monkeypatch.setattr(r, "_post", fake_post)
    cands = [{"chunk_id": f"c{i}", "content": f"doc {i}"} for i in range(3)]
    out = r.rerank("q", cands, top_k=3)
    assert called["n"] == 2
    assert [c["chunk_id"] for c in out] == ["c1", "c2", "c0"]


def test_cloud_rerank_no_keys_degrades():
    r = CloudReranker(keys=[])
    cands = [{"chunk_id": "x", "content": "a"}]
    out = r.rerank("q", cands, top_k=1)
    assert out == cands


def test_cloud_rerank_respects_index_order():
    """真实 API 风格：results 按相关度降序返回，index 指回原文位置。
    必须按 index 对齐分数，而非依赖返回列表顺序。"""
    class R:
        def json(self):
            # 相关度降序：原文 index=2 最相关，其次 index=0，最后 index=1
            return {"results": [
                {"index": 2, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.50},
                {"index": 1, "relevance_score": 0.10},
            ]}

    r = CloudReranker(keys=["good"])
    r._post = lambda url, headers, json: R()
    cands = [
        {"chunk_id": "c0", "content": "doc0"},
        {"chunk_id": "c1", "content": "doc1"},
        {"chunk_id": "c2", "content": "doc2"},
    ]
    out = r.rerank("q", cands, top_k=3)
    # 期望按相关度：c2(0.95) > c0(0.50) > c1(0.10)
    assert [c["chunk_id"] for c in out] == ["c2", "c0", "c1"]
    assert out[0]["rerank_score"] == 0.95 and out[0]["content"] == "doc2"
