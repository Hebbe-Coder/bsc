import httpx
import pytest

from app.services.sop_llm_client import (
    PROVIDER_REGISTRY,
    SOPLLMClient,
    SOPLLMError,
    _parse_json,
    _request_rejection_category,
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

    c = SOPLLMClient(
        provider="deepseek",
        api_key="sk-test",
        model="deepseek-chat",
        http_client=_FakeClient(handler),
    )
    out = c.chat_structured("你是分析师", "数据")
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert out["executive_summary"] == "ok"


def test_structured_chat_retries_without_json_mode_when_provider_rejects_it():
    bodies = []

    def handler(n, url, headers, body):
        bodies.append(body)
        if n == 1:
            return _FakeResp(
                {"error": {"message": "response_format json_object is not supported"}},
                status=400,
            )
        return _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

    client = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))

    assert client.chat_structured("return JSON", "data") == {"answer": "ok"}
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in bodies[1]
    assert client.last_structured_failure == ""


def test_structured_chat_accepts_segmented_text_content():
    def handler(n, url, headers, body):
        return _FakeResp(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"answer":'},
                                {"type": "text", "text": '"segmented"}'},
                            ]
                        }
                    }
                ]
            }
        )

    client = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))

    assert client.chat_structured("return JSON", "data") == {"answer": "segmented"}


def test_parse_strips_code_fence():
    content = '```json\n{"a": 1}\n```'
    assert _parse_json(content) == {"a": 1}


def test_request_rejection_category_is_safe_and_actionable():
    response = httpx.Response(
        400,
        json={"error": {"message": "maximum context length exceeded"}},
    )

    assert _request_rejection_category(response) == "request_too_large"


def test_parse_extracts_embedded_json():
    content = "好的,结果是 {\"a\": 1} 完毕"
    assert _parse_json(content) == {"a": 1}


def test_retry_on_dirty_then_valid():
    state = {"n": 0}
    bodies = []

    def handler(n, url, headers, body):
        state["n"] = n
        bodies.append(body)
        if n == 1:
            return _FakeResp({"choices": [{"message": {"content": "不是 json"}}]})
        return _FakeResp({"choices": [{"message": {"content": '{"executive_summary":"ok","key_findings":[],"recommendations":[],"risk_highlights":[]}'}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    out = c.chat_structured("你是分析师", "数据")
    assert out["executive_summary"] == "ok"
    assert state["n"] == 2  # 重试了一次


def test_structured_retry_repairs_dirty_json_in_json_mode():
    bodies = []

    def handler(n, url, headers, body):
        bodies.append(body)
        if n == 1:
            return _FakeResp({"choices": [{"message": {"content": "not json"}}]})
        return _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

    client = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))

    assert client.chat_structured("return JSON", "data") == {"answer": "ok"}
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[1]["response_format"] == {"type": "json_object"}


def test_structured_chat_preserves_each_provider_usage_across_json_repair_attempts():
    def handler(n, url, headers, body):
        if n == 1:
            return _FakeResp(
                {
                    "choices": [{"message": {"content": "not json"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13},
                }
            )
        return _FakeResp(
            {
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }
        )

    client = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))

    assert client.chat_structured("return JSON", "data") == {"answer": "ok"}
    assert [usage.total_tokens for usage in client.last_call_usages] == [13, 10]
    assert client.last_usage is not None
    assert client.last_usage.total_tokens == 10


def test_http_5xx_raises_sopllmerror():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "boom"}, status=500)

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    with pytest.raises(SOPLLMError) as exc_info:
        c.chat("你是分析师", "数据")
    assert exc_info.value.category == "server_error"


def test_rate_limited_provider_failure_has_a_retryable_category():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "slow down"}, status=429)

    client = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))

    with pytest.raises(SOPLLMError) as exc_info:
        client.chat("return JSON", "data")

    assert exc_info.value.category == "rate_limited"


def test_missing_provider_configuration_is_not_reported_as_transient_failure(monkeypatch):
    monkeypatch.setattr("app.services.sop_llm_client.settings.KIMI_API_KEY", "")

    with pytest.raises(SOPLLMError) as exc_info:
        SOPLLMClient(provider="kimi")

    assert exc_info.value.category == "provider_not_configured"


def test_chat_structured_returns_none_on_persistent_failure():
    def handler(n, url, headers, body):
        return _FakeResp({"choices": [{"message": {"content": "no json"}}]})

    c = SOPLLMClient(provider="deepseek", api_key="sk", http_client=_FakeClient(handler))
    assert c.chat_structured("你是分析师", "数据") is None
    assert c.last_structured_failure == "response_payload_invalid"
    assert c.last_response_shape == {
        "payload_type": "dict",
        "payload_keys": ["choices"],
        "choices_type": "list",
        "choice_type": "dict",
        "choice_keys": ["message"],
        "message_type": "dict",
        "message_keys": ["content"],
        "content_type": "str",
    }


def test_unknown_provider_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="nope", api_key="x")


def test_missing_api_key_raises():
    with pytest.raises(SOPLLMError):
        SOPLLMClient(provider="kimi")  # settings.KIMI_API_KEY 默认空
