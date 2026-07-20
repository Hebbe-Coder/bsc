import asyncio

from app.core.llm_usage import ModelUsage, extract_model_usage
from app.services.llm_adapter import LLMAdapter
from app.services.llm_service import LLMService


def test_extract_model_usage_keeps_provider_values_and_completeness():
    usage = extract_model_usage(
        {
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 45,
                "total_tokens": 165,
                "prompt_tokens_details": {"cached_tokens": 30},
                "completion_tokens_details": {"reasoning_tokens": 12},
            }
        },
        provider="deepseek",
        model="deepseek-chat",
    )

    assert usage.reported is True
    assert usage.complete is True
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 45
    assert usage.total_tokens == 165
    assert usage.cached_tokens == 30
    assert usage.reasoning_tokens == 12


def test_extract_model_usage_does_not_invent_missing_values():
    usage = extract_model_usage(
        {"usage": {"prompt_tokens": 120}},
        provider="provider",
        model="model",
    )
    missing = extract_model_usage({}, provider="provider", model="model")

    assert usage.reported is True
    assert usage.complete is False
    assert usage.completion_tokens is None
    assert usage.total_tokens is None
    assert missing.reported is False
    assert missing.total_tokens is None


def test_llm_service_preserves_provider_usage_in_meta(monkeypatch):
    service = LLMService(provider="deepseek")
    expected = ModelUsage(
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        reported=True,
        complete=True,
    )
    monkeypatch.setattr(service, "_validate_execution_mode", lambda provider: None)
    monkeypatch.setattr(service, "_get_provider_for_agent", lambda prompt: "deepseek")
    monkeypatch.setattr(
        service,
        "_call_api_with_provider",
        lambda *args: ({"result": "ok"}, expected),
    )

    result = service.chat("system", "user", use_cache=False)

    assert result["_meta"]["mode"] == "api"
    assert result["_meta"]["usage"] == expected.model_dump(mode="json")


def test_llm_adapter_exposes_last_provider_usage():
    class FakeService:
        def chat(self, **kwargs):
            return {
                "answer": "ok",
                "_meta": {
                    "mode": "api",
                    "usage": ModelUsage(
                        provider="deepseek",
                        model="deepseek-chat",
                        prompt_tokens=9,
                        completion_tokens=3,
                        total_tokens=12,
                        reported=True,
                        complete=True,
                    ).model_dump(mode="json"),
                },
            }

    adapter = LLMAdapter()
    adapter._sync_service = FakeService()

    response = asyncio.run(adapter.generate("prompt"))

    assert '"answer": "ok"' in response
    assert adapter.last_usage is not None
    assert adapter.last_usage.total_tokens == 12
