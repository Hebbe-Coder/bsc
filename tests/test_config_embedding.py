from app.core.config import settings


def test_embedding_provider_default_is_mock():
    assert hasattr(settings, "EMBEDDING_PROVIDER")
    assert settings.EMBEDDING_PROVIDER == "mock"


def test_embedding_config_defaults():
    assert settings.EMBEDDING_BASE_URL == "https://api.openai.com/v1"
    assert settings.EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.EMBEDDING_API_KEY == ""
