"""
Tracing Middleware - 请求追踪与结构化日志

提供：
1. 请求级trace_id生成与传递
2. 结构化JSON日志格式
3. 线程本地上下文存储
4. 统一的日志记录接口
"""
from __future__ import annotations
import uuid
import time
import logging
import json
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import threading

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def get_trace_id() -> str:
    """获取当前请求的trace_id"""
    return getattr(_thread_local, 'trace_id', 'unknown')


def set_trace_id(trace_id: str):
    """设置当前请求的trace_id"""
    _thread_local.trace_id = trace_id


def get_request_context() -> dict:
    """获取当前请求上下文"""
    return getattr(_thread_local, 'request_context', {})


def set_request_context(ctx: dict):
    """设置当前请求上下文"""
    _thread_local.request_context = ctx


class TracingMiddleware(BaseHTTPMiddleware):
    """请求追踪中间件 - 为每个请求生成唯一trace_id"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = str(uuid.uuid4())[:16]
        set_trace_id(trace_id)
        
        ctx = {
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        }
        set_request_context(ctx)
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                json.dumps({
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code if 'response' in locals() else 500,
                    "duration_ms": elapsed_ms,
                    "client_ip": ctx["client_ip"],
                }, ensure_ascii=False)
            )
        
        response.headers["X-Trace-Id"] = trace_id
        return response


class StructuredLogger:
    """结构化日志记录器"""
    
    @staticmethod
    def log(level: str, message: str, **kwargs):
        """
        记录结构化日志
        
        Args:
            level: 日志级别 (debug, info, warning, error)
            message: 日志消息
            **kwargs: 额外的结构化数据
        """
        trace_id = get_trace_id()
        ctx = get_request_context()
        
        log_entry = {
            "trace_id": trace_id,
            "level": level.upper(),
            "message": message,
            **ctx,
            **kwargs,
        }
        
        log_func = getattr(logger, level, logger.info)
        log_func(json.dumps(log_entry, ensure_ascii=False))
    
    @staticmethod
    def debug(message: str, **kwargs):
        StructuredLogger.log("debug", message, **kwargs)
    
    @staticmethod
    def info(message: str, **kwargs):
        StructuredLogger.log("info", message, **kwargs)
    
    @staticmethod
    def warning(message: str, **kwargs):
        StructuredLogger.log("warning", message, **kwargs)
    
    @staticmethod
    def error(message: str, **kwargs):
        StructuredLogger.log("error", message, **kwargs)
    
    @staticmethod
    def exception(message: str, exc: Exception, **kwargs):
        """记录异常日志"""
        StructuredLogger.log(
            "error",
            message,
            exception=str(exc),
            exc_type=type(exc).__name__,
            **kwargs,
        )