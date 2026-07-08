"""Unified API Response Format"""
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一API响应格式"""
    success: bool
    data: Optional[T] = None
    message: str = ""
    errors: List[str] = []
    code: int = 200

    @classmethod
    def ok(cls, data: T = None, message: str = "操作成功") -> "ApiResponse[T]":
        """成功响应"""
        return cls(success=True, data=data, message=message, code=200)

    @classmethod
    def error(cls, message: str, errors: List[str] = None, code: int = 400) -> "ApiResponse[T]":
        """错误响应"""
        return cls(success=False, message=message, errors=errors or [], code=code)

    @classmethod
    def unauthorized(cls, message: str = "未授权") -> "ApiResponse[T]":
        """未授权响应"""
        return cls(success=False, message=message, code=401)

    @classmethod
    def not_found(cls, message: str = "资源未找到") -> "ApiResponse[T]":
        """资源未找到响应"""
        return cls(success=False, message=message, code=404)

    @classmethod
    def server_error(cls, message: str = "服务器错误") -> "ApiResponse[T]":
        """服务器错误响应"""
        return cls(success=False, message=message, code=500)