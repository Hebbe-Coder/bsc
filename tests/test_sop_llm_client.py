import httpx
import pytest

from app.services.sop_llm_client import (
    PROVIDER_REGISTRY,
    SOPLLMClient,
    SOPLLMError,
    _parse_json,
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


def test_registry_has_four_providers():
    for p in ("deepseek", "doubao", "qwen", "kimi"):
        assert p in PROVIDER_REGISTRY


def test_mock_returns_valid_summary_dict():
    c = SOPLLMClient(provider="mock")
    out = c.chat_structured("你是分析师", "数据")
    assert isinstance(out, dict)
    assert set(["executive_summary", "key_findings", "recommendations", "risk_highlights"]) <= set(out.keys())


def test_mock_returns_valid_reco_dict():
    c = SOPLLMClient(provider="mock")
    out = c.chat_structured("请给优化建议", "数据")
    assert isinstance(out, dict)
    assert "optimization_suggestions" in out
    assert "prioritized_actions" in out


def test_request_construction_deepseek():
    captured = {}

    def handler(n, url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return _FakeResp({"choices": [{"message": {"content": '{"executive_summary":"ok","key_findings":[],"recommendations":[],"risk_highlights":[]}'}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk-test", http_client=_FakeClient(handler))
    out = c.chat_structured("你是分析师", "数据")
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert out["executive_summary"] == "ok"


def test_parse_strips_code_fence():
    content = '```json\n{"a": 1}\n```'
    assert _parse_json(content) == {"a": 1}


def test_parse_extracts_embedded_json():
    content = "好的,结果是 {\"a\": 1} 完毕"
    assert _parse_json(content) == {"a": 1}


def test_retry_on_dirty_then_valid():
    state = {"n": 0}

    def handler(n, url, headers, body):
        state["n"] = n
        if n == 1:
            return _FakeResp({"choices": [{"message": {"content": "不是 json"}}]})
        return _FakeResp({"choices": [{"message": {"content": '{"executive_summary":"ok","key_findings":[],"recommendations":[],"risk_highlights":[]}'}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    out = c.chat_structured("你是分析师", "数据")
    assert out["executive_summary"] == "ok"
    assert state["n"] == 2  # 重试了一次


def test_http_5xx_raises_sopllmerror():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "boom"}, status=500)

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    with pytest.raises(SOPLLMError):
        c.chat("你是分析师", "数据")


def test_chat_structured_returns_none_on_persistent_failure():
    def handler(n, url, headers, body):
        return _FakeResp({"choices": [{"message": {"content": "no json"}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    assert c.chat_structured("你是分析师", "数据") is None


def test_unknown_provider_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="nope", api_key="x")


def test_missing_api_key_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="kimi")  # settings.KIMI_API_KEY 默认空
