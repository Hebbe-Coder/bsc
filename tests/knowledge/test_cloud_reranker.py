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
