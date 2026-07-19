import httpx
import numpy as np
import pytest

from app.knowledge.embeddings import (
    MockEmbeddingProvider,
    RemoteEmbeddingProvider,
    get_embedding_provider,
)


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        return self._handler(self.calls, url, headers, json)

    def close(self):
        pass


def test_mock_provider_deterministic():
    p = MockEmbeddingProvider()
    a = p.embed(["内容安全平台过滤违规"])
    b = p.embed(["内容安全平台过滤违规"])
    c = p.embed(["咖啡烘焙风味分析"])
    assert a == b
    assert a != c
    assert len(a[0]) == p.dim


def test_mock_provider_normalized():
    p = MockEmbeddingProvider()
    v = np.array(p.embed(["用户反馈 投诉 处理"])[0])
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-6


def test_remote_provider_request():
    captured = {}

    def handler(n, url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return _FakeResp({"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    p = RemoteEmbeddingProvider(
        api_key="sk-test", base_url="https://emb.example.com/v1",
        model="emb-model", http_client=_FakeClient(handler))
    out = p.embed(["hello"])
    assert captured["url"] == "https://emb.example.com/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "emb-model"
    assert captured["body"]["input"] == ["hello"]
    assert out == [[0.1, 0.2, 0.3]]
    assert p.dim == 3


def test_remote_provider_parse_by_index():
    def handler(n, url, headers, body):
        return _FakeResp({"data": [
            {"index": 1, "embedding": [9, 9]},
            {"index": 0, "embedding": [1, 1]},
        ]})

    p = RemoteEmbeddingProvider(
        api_key="k", base_url="https://x/v1", model="m",
        http_client=_FakeClient(handler))
    out = p.embed(["a", "b"])
    assert out == [[1, 1], [9, 9]]


def test_remote_provider_raises_on_error():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "boom"}, status=500)

    p = RemoteEmbeddingProvider(
        api_key="k", base_url="https://x/v1", model="m",
        http_client=_FakeClient(handler))
    with pytest.raises(Exception):
        p.embed(["x"])


def test_factory_mock_and_remote():
    assert isinstance(get_embedding_provider("mock"), MockEmbeddingProvider)
    rp = get_embedding_provider(
        "openai", api_key="k", base_url="https://x/v1", model="m")
    assert isinstance(rp, RemoteEmbeddingProvider)
    assert rp.name == "openai"


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_embedding_provider("nope")
