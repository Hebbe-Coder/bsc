"""
BSC Config Types — 纯类型定义模块

借鉴 Grok Build 的 xai-grok-config-types 模式:
  配置类型与加载逻辑分离, 零运行时依赖。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMProviderConfig:
    """单个 LLM Provider 配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@dataclass
class CacheConfig:
    """缓存配置"""
    cache_type: str = "memory"   # memory / redis
    redis_url: str = "redis://localhost:6379"
    l1_ttl: int = 60             # L1 内存缓存 TTL
    l2_ttl: int = 3600           # L2 Redis 缓存 TTL


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_type: str = "sqlite"      # sqlite / postgresql
    db_path: str = "bsc_cloud.db"
    db_url: str = ""


@dataclass
class SecurityConfig:
    """安全配置"""
    api_key: str = ""
    api_key_reader: str = ""
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:8000"])
    rate_limit_rate: int = 30
    rate_limit_burst: int = 60
    rate_limit_enabled: bool = True
    signature_enabled: bool = False
    signature_ttl: int = 300
    max_file_size_mb: int = 10


@dataclass
class LLMRoutingConfig:
    """LLM 路由配置 — 按阶段分配不同模型"""
    default_provider: str = "deepseek"
    analysis_provider: str = "deepseek"     # SOP/Risk/Strategy/Optimization
    generation_provider: str = "deepseek"   # BU/Composer
    ocr_provider: str = "deepseek"          # OCR
    sop_provider: str = "deepseek"          # SOP AI
    rag_provider: str = "deepseek"          # RAG 问答
    embedding_provider: str = "mock"
    rerank_provider: str = "none"
    rag_two_phase: bool = False
    rerank_enabled: bool = False
    rerank_top_n: int = 20
    vector_fuse_enabled: bool = True
    ocr_enabled: bool = True


@dataclass
class PipelineConfig:
    """Pipeline 配置"""
    use_langchain: bool = True
    use_agent: bool = False
    celery_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_timeout: int = 3600
    celery_task_soft_timeout: int = 3000
    event_backend: str = "inprocess"


@dataclass
class KnowledgeWikiConfig:
    """Configuration values for the optional project-scoped LLM Wiki."""

    enabled: bool = False
    obsidian_vault_root: str = ""
    horizon_enabled: bool = False
    horizon_api_base_url: str = ""
    horizon_timeout_seconds: int = 20


@dataclass
class AppConfig:
    """应用基础配置"""
    app_name: str = "BSC · Business System Compiler"
    app_version: str = "5.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")
