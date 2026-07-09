import httpx
import pytest

from app.services.sop_llm_client import SOPLLMClient, SOPLLMError


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code not in (401, 402, 429):
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


def test_multikeys_failover_hits_valid_key():
    seq = {1: _FakeResp({"error": "unauth"}, status=401),
           2: _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})}

    def handler(n, url, headers, body):
        return seq[n]

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["bad", "good"],
                     http_client=_FakeClient(handler))
    out = c.chat("sys", "usr")
    assert out["content"] == '{"answer":"ok"}'


def test_multikeys_exhausted_raises():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "unauth"}, status=401)

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["k1", "k2"],
                     http_client=_FakeClient(handler))
    with pytest.raises(SOPLLMError):
        c.chat("sys", "usr")


def test_multikeys_5xx_also_failover():
    seq = {1: _FakeResp({"error": "boom"}, status=500),
           2: _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})}

    def handler(n, url, headers, body):
        return seq[n]

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["bad", "good"],
                     http_client=_FakeClient(handler))
    assert c.chat("sys", "usr")["content"] == '{"answer":"ok"}'


def test_multikeys_without_single_api_key_ok():
    # 多 Key 设计:仅提供 keys、不提供单 key 时也应可构造(keys 优先于单 api_key)
    c = SOPLLMClient(provider="deepseek", keys=["k1", "k2"])
    assert c.keys == ["k1", "k2"]
