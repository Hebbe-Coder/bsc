from app.core.config import settings


def test_rag_llm_provider_default_is_mock():
    assert hasattr(settings, "RAG_LLM_PROVIDER")
    assert settings.RAG_LLM_PROVIDER == "mock"


def test_rag_config_defaults():
    assert settings.RAG_LLM_KEYS == []
    assert settings.RAG_TWO_PHASE is False
