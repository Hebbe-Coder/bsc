"""
Rate Limiter Middleware - protects API from abuse.

Implements token bucket algorithm per IP and API key.

配置方式：
    RATE_LIMIT_RATE=30          # 每秒允许请求数
    RATE_LIMIT_BURST=60         # 最大突发请求数
    RATE_LIMIT_ENABLED=True     # 是否启用限流
"""
from __future__ import annotations
import time
import asyncio
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class TokenBucket:
    """Token bucket for rate limiting."""
    
    def __init__(self, rate: int = 30, burst: int = 60):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()
    
    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_remaining(self) -> int:
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens = min(self.burst, self.tokens + elapsed * self.rate)
        return int(tokens)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with per-IP and per-API-key buckets."""
    
    _WHITELIST_PATHS = {
        "/health", "/docs", "/redoc", "/openapi.json",
        "/metrics", "/metrics/prometheus",
    }
    
    _PATH_RATE_LIMITS = {
        "/bsc/compile": {"rate": 10, "burst": 20},
        "/bsc/compile/sync": {"rate": 5, "burst": 10},
        "/bsc/stage": {"rate": 15, "burst": 30},
        # 知识库端点：ingest 为重操作（解析+向量化文件，且可灌入语料），限速从严；
        # retrieve 为高频查询，documents 含列出/删除，均细于全局默认 30/60。
        "/knowledge/ingest": {"rate": 5, "burst": 10},
        "/knowledge/retrieve": {"rate": 20, "burst": 40},
        "/knowledge/documents": {"rate": 15, "burst": 30},
    }
    
    def __init__(self, app, rate: int = None, burst: int = None):
        super().__init__(app)
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._rate = rate or settings.RATE_LIMIT_RATE
        self._burst = burst or settings.RATE_LIMIT_BURST
        self._enabled = settings.RATE_LIMIT_ENABLED
    
    async def _get_bucket(self, key: str, path: str = "") -> TokenBucket:
        async with self._lock:
            rate = self._rate
            burst = self._burst
            
            path_config = self._PATH_RATE_LIMITS.get(path)
            if path_config:
                rate = path_config["rate"]
                burst = path_config["burst"]
            
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(rate, burst)
            
            if len(self._buckets) > 10000:
                cutoff = time.monotonic() - 300
                self._buckets = {
                    k: v for k, v in self._buckets.items()
                    if v.last_refill > cutoff
                }
            
            return self._buckets[key]
    
    def _get_identifier(self, request: Request) -> str:
        """获取请求标识（优先API key，其次IP）"""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
            if api_key:
                return f"key_{api_key[:16]}"
        
        client_ip = request.client.host if request.client else "unknown"
        return f"ip_{client_ip}"
    
    def _is_whitelisted(self, path: str) -> bool:
        """检查路径是否在白名单中"""
        if path in self._WHITELIST_PATHS:
            return True
        if path.startswith("/dashboard"):
            return True
        if path.startswith("/static"):
            return True
        if path.startswith("/output"):
            return True
        return False
    
    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)
        
        path = request.url.path
        if self._is_whitelisted(path):
            return await call_next(request)
        
        identifier = self._get_identifier(request)
        bucket = await self._get_bucket(identifier, path)
        
        if not bucket.consume():
            remaining = bucket.get_remaining()
            retry_after = max(1, int((1 - remaining / bucket.burst) * 60))
            
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please retry later.",
                        "retry_after_sec": retry_after,
                        "rate_limit": {
                            "rate": bucket.rate,
                            "burst": bucket.burst,
                            "remaining": remaining,
                        },
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Rate": str(bucket.rate),
                    "X-RateLimit-Burst": str(bucket.burst),
                    "X-RateLimit-Remaining": str(remaining),
                },
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Rate"] = str(bucket.rate)
        response.headers["X-RateLimit-Burst"] = str(bucket.burst)
        response.headers["X-RateLimit-Remaining"] = str(bucket.get_remaining())
        return response