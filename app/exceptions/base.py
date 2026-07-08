"""统一业务异常类

提供清晰的错误层次结构，便于错误处理和API响应统一。
"""
from typing import Optional, Dict, Any


class BSCError(Exception):
    """基础异常类"""

    def __init__(
        self,
        message: str,
        code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": {
                "message": self.message,
                "code": self.code,
                "details": self.details,
            }
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code})"


class ValidationError(BSCError):
    """验证错误（400）"""

    def __init__(
        self,
        message: str = "请求参数验证失败",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=400, details=details)


class NotFoundError(BSCError):
    """资源不存在（404）"""

    def __init__(
        self,
        message: str = "资源不存在",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(message, code=404, details=details)


class AuthenticationError(BSCError):
    """认证错误（401）"""

    def __init__(
        self,
        message: str = "未授权访问",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=401, details=details)


class AuthorizationError(BSCError):
    """授权错误（403）"""

    def __init__(
        self,
        message: str = "禁止访问",
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
    ):
        details = {}
        if action:
            details["action"] = action
        if resource_type:
            details["resource_type"] = resource_type
        super().__init__(message, code=403, details=details)


class LLMError(BSCError):
    """LLM调用错误"""

    def __init__(
        self,
        message: str = "大模型调用失败",
        provider: Optional[str] = None,
        error_code: Optional[str] = None,
        retryable: bool = False,
    ):
        details = {}
        if provider:
            details["provider"] = provider
        if error_code:
            details["error_code"] = error_code
        details["retryable"] = retryable
        super().__init__(message, code=503, details=details)


class DatabaseError(BSCError):
    """数据库错误"""

    def __init__(
        self,
        message: str = "数据库操作失败",
        operation: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        details = {}
        if operation:
            details["operation"] = operation
        if error_code:
            details["error_code"] = error_code
        super().__init__(message, code=500, details=details)


class ServiceError(BSCError):
    """服务错误"""

    def __init__(
        self,
        message: str = "服务不可用",
        service_name: Optional[str] = None,
        retryable: bool = False,
    ):
        details = {}
        if service_name:
            details["service_name"] = service_name
        details["retryable"] = retryable
        super().__init__(message, code=503, details=details)