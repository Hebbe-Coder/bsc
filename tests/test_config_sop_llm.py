from app.core.config import settings


def test_sop_llm_provider_default_is_mock():
    assert hasattr(settings, "SOP_LLM_PROVIDER")
    # 代码默认应为 mock(安全离线默认);.env 可覆盖为具体 provider,
    # 故断言 *代码默认值* 而非运行时值,避免被环境配置影响。
    assert type(settings).model_fields["SOP_LLM_PROVIDER"].default == "mock"


def test_kimi_config_defaults():
    assert settings.KIMI_BASE_URL == "https://api.moonshot.cn/v1"
    assert settings.KIMI_MODEL == "moonshot-v1-8k"
    assert settings.KIMI_API_KEY == ""
