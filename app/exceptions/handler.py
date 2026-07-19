"""FastAPI全局异常处理器

将业务异常类转换为统一的API响应格式。
"""
import logging
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

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
from app.core.config import settings

logger = logging.getLogger(__name__)


def register_exception_handlers(app):
    """注册全局异常处理器"""

    @app.exception_handler(BSCError)
    async def bsc_error_handler(request: Request, exc: BSCError):
        logger.error(f"BSCError: {exc.message} (code={exc.code})")
        return JSONResponse(
            status_code=exc.code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        logger.warning(f"ValidationError: {exc.message}")
        return JSONResponse(
            status_code=400,
            content={
                "code": 400,
                "message": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        logger.warning(f"NotFoundError: {exc.message}")
        return JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "message": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        logger.warning(f"AuthenticationError: {exc.message}")
        return JSONResponse(
            status_code=401,
            content={
                "code": 401,
                "message": exc.message,
                "data": None,
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        logger.warning(f"AuthorizationError: {exc.message}")
        return JSONResponse(
            status_code=403,
            content={
                "code": 403,
                "message": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError):
        logger.error(f"LLMError: {exc.message}")
        return JSONResponse(
            status_code=exc.code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request: Request, exc: DatabaseError):
        logger.error(f"DatabaseError: {exc.message}")
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "数据库操作失败",
                "data": exc.details,
            },
        )

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        logger.error(f"ServiceError: {exc.message}")
        return JSONResponse(
            status_code=exc.code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": exc.details,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning(f"HTTPException: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail,
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        
        response_data = {
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
        }
        
        if not settings.is_production:
            response_data["detail"] = str(exc)
            response_data["traceback"] = traceback.format_exc()[:2000]
        
        return JSONResponse(
            status_code=500,
            content=response_data,
        )