from app.core.config import settings


def test_sop_llm_provider_default_is_mock():
    assert hasattr(settings, "SOP_LLM_PROVIDER")
    assert settings.SOP_LLM_PROVIDER == "mock"


def test_kimi_config_defaults():
    assert settings.KIMI_BASE_URL == "https://api.moonshot.cn/v1"
    assert settings.KIMI_MODEL == "moonshot-v1-8k"
    assert settings.KIMI_API_KEY == ""
