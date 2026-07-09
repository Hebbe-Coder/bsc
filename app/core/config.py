import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "BSC · Business System Compiler"
    APP_VERSION: str = "5.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    ALLOWED_ORIGINS: List[str] = ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]

    RATE_LIMIT_RATE: int = 30
    RATE_LIMIT_BURST: int = 60
    RATE_LIMIT_ENABLED: bool = True

    SIGNATURE_ENABLED: bool = False
    SIGNATURE_TTL: int = 300

    MAX_FILE_SIZE_MB: int = 10

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    DOUBAO_MODEL: str = "doubao-pro-32k"

    YUANBAO_API_KEY: str = ""
    YUANBAO_BASE_URL: str = "https://api.hunyuan.cloud.tencent.com/v1"
    YUANBAO_MODEL: str = "hunyuan-pro"

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    VLLM_MODEL: str = ""

    LOCALAI_BASE_URL: str = "http://localhost:8080/v1"
    LOCALAI_MODEL: str = "gpt-4"

    LLM_PROVIDER: str = "mock"
    ANALYSIS_PROVIDER: str = "deepseek"
    GENERATION_PROVIDER: str = "doubao"
    OCR_PROVIDER: str = "doubao"

    SOP_LLM_PROVIDER: str = "mock"  # SOP AI 段使用的 LLM provider (deepseek/doubao/qwen/kimi/mock)

    LLM_TIMEOUT: int = 60
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 8000

    USE_LANGCHAIN: bool = True
    USE_AGENT: bool = False

    API_KEY: str = ""
    # 仅具「读取/检索」权限的 Key；配置后 API_KEY 退居为 admin（写入/删除）权限。
    # 仅对 /knowledge/* 端点生效，且不授予非知识库端点的访问权。
    API_KEY_READER: str = ""

    LOG_LEVEL: str = "INFO"

    ENVIRONMENT: str = "development"

    CACHE_TYPE: str = "memory"
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL: int = 3600
    L1_CACHE_TTL: int = 60
    L2_CACHE_TTL: int = 3600

    DB_TYPE: str = "sqlite"
    DB_PATH: str = "bsc_cloud.db"
    DB_URL: str = ""

    CELERY_ENABLED: bool = False
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_TIMEOUT: int = 3600
    CELERY_TASK_SOFT_TIMEOUT: int = 3000

    EVENT_BACKEND: str = "inprocess"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ["production", "prod"]


def _validate_settings(settings: Settings):
    """验证配置安全性"""
    if settings.is_production:
        if not settings.API_KEY:
            logger.critical("生产环境必须配置API_KEY，否则服务将拒绝请求")
        
        secrets_to_check = [
            ("DEEPSEEK_API_KEY", settings.DEEPSEEK_API_KEY),
            ("DOUBAO_API_KEY", settings.DOUBAO_API_KEY),
            ("YUANBAO_API_KEY", settings.YUANBAO_API_KEY),
            ("QWEN_API_KEY", settings.QWEN_API_KEY),
        ]
        
        for name, value in secrets_to_check:
            if value and len(value) < 10:
                logger.warning(f"检测到{name}可能设置不正确（长度过短）")

        if settings.LOG_LEVEL.lower() not in ["warning", "error"]:
            logger.warning("生产环境建议将LOG_LEVEL设置为WARNING或ERROR")
        
        if settings.DB_TYPE == "postgresql" and not settings.DB_URL:
            logger.critical("使用PostgreSQL时必须配置DB_URL")
        
        if "*" in settings.ALLOWED_ORIGINS:
            logger.critical("生产环境不允许使用通配符(*)作为ALLOWED_ORIGINS，请明确指定允许的域名")


settings = Settings()
_validate_settings(settings)
