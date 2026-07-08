"""异常处理模块

提供统一的业务异常类：
- BSCError: 基础异常类
- ValidationError: 验证错误
- NotFoundError: 资源不存在
- AuthenticationError: 认证错误
- AuthorizationError: 授权错误
- LLMError: LLM调用错误
- DatabaseError: 数据库错误
- ServiceError: 服务错误

以及FastAPI全局异常处理器。
"""
from .base import (
    BSCError,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    AuthorizationError,
    LLMError,
    DatabaseError,
    ServiceError,
)

from .handler import register_exception_handlers