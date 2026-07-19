"""
BSC 统一枚举定义

消除项目中散布的魔法字符串，提供类型安全的常量引用。

使用方式:
    from app.enums import PipelineStage, LLMProvider, BrainstormMode

    # 替换前
    if stage_key == "business_understanding":

    # 替换后
    if stage_key == PipelineStage.BUSINESS_UNDERSTANDING:
"""

from enum import StrEnum


class PipelineStage(StrEnum):
    """BSC Pipeline 阶段标识"""
    BUSINESS_UNDERSTANDING = "business_understanding"
    SOP = "sop"
    RISK = "risk"
    STRATEGY = "strategy"
    OPTIMIZATION = "optimization"
    ROOT_CAUSE = "root_cause"
    COMPOSER = "composer"
    ASSET = "asset"


class LLMProvider(StrEnum):
    """LLM 提供商"""
    DEEPSEEK = "deepseek"
    DOUBAO = "doubao"
    QWEN = "qwen"
    KIMI = "kimi"
    YUANBAO = "yuanbao"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LOCALAI = "localai"
    OPENAI = "openai"
    MOCK = "mock"
    NONE = "none"
    SILICONFLOW = "siliconflow"


class BrainstormMode(StrEnum):
    """头脑风暴模式"""
    DIVERGENT = "divergent"
    CONVERGENT = "convergent"
    HYBRID = "hybrid"


class CacheType(StrEnum):
    """缓存类型"""
    MEMORY = "memory"
    REDIS = "redis"


class Environment(StrEnum):
    """运行环境"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    PROD = "prod"


class ExportFormat(StrEnum):
    """导出格式"""
    JSON = "json"
    HTML = "html"
    PPT = "ppt"
    WORD = "word"
    PDF = "pdf"
    XLSX = "xlsx"
    MARKDOWN = "markdown"


class EmbeddingProvider(StrEnum):
    """向量嵌入提供商"""
    MOCK = "mock"
    OPENAI = "openai"
    SILICONFLOW = "siliconflow"


class RerankProvider(StrEnum):
    """重排序提供商"""
    NONE = "none"
    MOCK = "mock"
    LOCAL = "local"
    CLOUD = "cloud"


class EventBackend(StrEnum):
    """事件后端"""
    INPROCESS = "inprocess"
    REDIS = "redis"


class DBType(StrEnum):
    """数据库类型"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class AgentStatus(StrEnum):
    """Agent 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    CACHED = "cached"
