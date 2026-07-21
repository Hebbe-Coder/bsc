import asyncio

import pytest

from app.core.config import settings
from app.core.langchain_agent import LangChainAgentService
from app.core.prd_quality_scorer import PRDQualityScorer
from app.core.prd_refiner import PRDRefiner
from app.knowledge.query_rewrite import LLMQueryRewriter, MockQueryRewriter
from app.knowledge.self_rag import SelfRAG
from app.services.langchain_service import LangChainService
from app.services.llm_service import LLMService
from app.services.sop_llm_client import SOPLLMClient


def test_production_rejects_implicit_mock_output(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_LLM_IN_PRODUCTION", False)
    service = LLMService(provider="mock", force_mock=True)

    with pytest.raises(RuntimeError, match="mock LLM output is disabled"):
        service.chat("test", "input", use_cache=False)
    with pytest.raises(RuntimeError, match="mock LLM output is disabled"):
        service._mock("test", "input")


def test_production_rejects_provider_failure_instead_of_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "configured-test-key")
    service = LLMService(provider="deepseek")
    monkeypatch.setattr(
        service,
        "_call_api_with_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="mock fallback is disabled"):
        service.chat("test", "input", use_cache=False)


def test_development_fallback_is_marked_explicitly(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "configured-test-key")
    service = LLMService(provider="deepseek")
    monkeypatch.setattr(
        service,
        "_call_api_with_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("provider unavailable")),
    )

    result = service.chat("test", "input", use_cache=False)

    assert result["_meta"]["mode"] == "fallback"


def test_cached_fallback_remains_visible_and_is_rechecked_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "configured-test-key")
    service = LLMService(provider="deepseek")
    monkeypatch.setattr(
        service,
        "_call_api_with_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("provider unavailable")),
    )

    first = service.chat("test", "cached input")
    cached = service.chat("test", "cached input")

    assert first["_meta"]["mode"] == "fallback"
    assert cached["_meta"]["mode"] == "fallback"
    assert cached["_meta"]["cache_hit"] is True

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)
    with pytest.raises(RuntimeError, match="fallback is disabled"):
        service.chat("test", "cached input")


def test_production_rejects_sop_and_langchain_mock_clients(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_LLM_IN_PRODUCTION", False)

    with pytest.raises(RuntimeError, match="SOP mock LLM output is disabled"):
        SOPLLMClient(provider="mock")
    with pytest.raises(RuntimeError, match="LangChain mock LLM output is disabled"):
        LangChainService(provider="mock")
    with pytest.raises(RuntimeError, match="LangChain Agent mock LLM output is disabled"):
        LangChainAgentService(provider="mock")


def test_production_rejects_langchain_provider_and_template_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")

    service = LangChainService(provider="deepseek", use_mock=False)
    with pytest.raises(RuntimeError, match="LangChain LLM fallback is disabled"):
        _ = service.llm
    with pytest.raises(RuntimeError, match="LangChain LLM fallback is disabled"):
        service._fallback_prd_markdown("input", "general", {})

    agent = LangChainAgentService(provider="deepseek", use_mock=False)
    with pytest.raises(RuntimeError, match="LangChain Agent LLM fallback is disabled"):
        _ = agent.llm


def test_production_rejects_legacy_and_adapter_fallbacks(monkeypatch):
    from app.core.bsc_pipeline import _generate_fallback_business_system
    from app.core.llm_adapters import OpenAICompatibleAdapter

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)

    with pytest.raises(RuntimeError, match="Legacy BSC LLM fallback is disabled"):
        _generate_fallback_business_system("input")
    with pytest.raises(RuntimeError, match="LLM adapter LLM fallback is disabled"):
        OpenAICompatibleAdapter("key", "http://example.invalid", "model")._fallback_result(
            "system", "input", 1, "provider unavailable", "deepseek", "model"
        )


def test_production_rejects_query_rewrite_mock_and_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_LLM_IN_PRODUCTION", False)
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)

    with pytest.raises(RuntimeError, match="Query Rewrite mock LLM output is disabled"):
        MockQueryRewriter().rewrite("query")

    class EmptyLLM:
        def chat_structured(self, *args, **kwargs):
            return None

    rewriter = LLMQueryRewriter(provider="deepseek")
    monkeypatch.setattr(rewriter, "_get_llm", lambda: EmptyLLM())
    with pytest.raises(RuntimeError, match="Query Rewrite LLM fallback is disabled"):
        rewriter.rewrite("query")


def test_production_rejects_self_rag_mock_and_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_LLM_IN_PRODUCTION", False)
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)

    with pytest.raises(RuntimeError, match="Self-RAG mock LLM output is disabled"):
        SelfRAG(provider="mock", service=object())._evaluate_relevance("question", [{}])

    class EmptyLLM:
        def chat_structured(self, *args, **kwargs):
            return None

    self_rag = SelfRAG(provider="deepseek", service=object())
    monkeypatch.setattr(self_rag, "_get_llm", lambda: EmptyLLM())
    with pytest.raises(RuntimeError, match="Self-RAG LLM fallback is disabled"):
        self_rag._evaluate_relevance("question", [{}])


def test_production_rejects_prd_quality_and_refiner_mock_output(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_LLM_IN_PRODUCTION", False)

    with pytest.raises(RuntimeError, match="PRD Quality mock LLM output is disabled"):
        PRDQualityScorer(provider="mock").score("short PRD")
    with pytest.raises(RuntimeError, match="PRD Refiner mock LLM output is disabled"):
        _ = PRDRefiner(provider="mock").llm


def test_production_rejects_mission_planner_and_dialog_template_fallback(monkeypatch):
    from app.capabilities import MissionPlanner, build_default_registry
    from app.core.dialog_engine import DialogEngine

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)

    class FailingLLM:
        async def generate(self, prompt):
            raise OSError("planner provider unavailable")

    planner = MissionPlanner(
        registry=build_default_registry(),
        llm_service=FailingLLM(),
        mode="llm",
    )
    with pytest.raises(RuntimeError, match="Mission Planner LLM fallback is disabled"):
        asyncio.run(planner.plan("production planning input"))

    class EmptyPlanLLM:
        async def generate(self, prompt):
            return '{"mission":"evaluate","steps":[]}'

    empty_plan_planner = MissionPlanner(
        registry=build_default_registry(),
        llm_service=EmptyPlanLLM(),
        mode="llm",
    )
    with pytest.raises(RuntimeError, match="Mission Planner LLM fallback is disabled"):
        asyncio.run(empty_plan_planner.plan("production planning input"))

    dialog = DialogEngine.__new__(DialogEngine)
    with pytest.raises(RuntimeError, match="Dialog PRD LLM fallback is disabled"):
        dialog._generate_fallback_prd({"input_text": "fallback input"})
