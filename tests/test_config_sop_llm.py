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


def test_semantic_growth_distillation_defaults_to_disabled():
    assert type(settings).model_fields["KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED"].default is False


def test_growth_distillation_has_an_isolated_long_request_budget():
    assert type(settings).model_fields["KNOWLEDGE_GROWTH_LLM_TIMEOUT_SECONDS"].default == 150.0


def test_pbos_compilation_has_an_isolated_bounded_request_budget():
    fields = type(settings).model_fields
    assert fields["PBOS_LLM_TIMEOUT_SECONDS"].default == 120.0
    assert fields["PBOS_LLM_MODEL"].default == ""
    assert fields["PBOS_LLM_MAX_OUTPUT_TOKENS"].default == 2_600
    assert fields["PBOS_LLM_MAX_STRUCTURED_ATTEMPTS"].default == 2
    assert fields["PBOS_LLM_MAX_CONTEXT_DOCUMENTS"].default == 4
    assert fields["PBOS_LLM_CONTEXT_DOCUMENT_MAX_TOKENS"].default == 180


def test_growth_distillation_has_a_bounded_task_lifecycle():
    assert type(settings).model_fields["KNOWLEDGE_GROWTH_TASK_SOFT_TIMEOUT_SECONDS"].default == 390
    assert type(settings).model_fields["KNOWLEDGE_GROWTH_TASK_TIMEOUT_SECONDS"].default == 420


def test_source_sync_has_a_short_independent_recovery_window():
    assert type(settings).model_fields["KNOWLEDGE_SOURCE_SYNC_RECOVERY_TIMEOUT_SECONDS"].default == 900
