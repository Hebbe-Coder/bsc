"""
Rate Limiter Middleware - protects API from abuse.

Implements token bucket algorithm per IP and API key.

配置方式：
    RATE_LIMIT_RATE=30          # 每秒允许请求数
    RATE_LIMIT_BURST=60         # 最大突发请求数
    RATE_LIMIT_ENABLED=True     # 是否启用限流
"""
from __future__ import annotations
import hashlib
import logging
import time
import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


_REDIS_TOKEN_BUCKET_SCRIPT = """
local value = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local tokens = tonumber(value[1]) or burst
local updated_at = tonumber(value[2]) or now
tokens = math.min(burst, tokens + math.max(0, now - updated_at) * rate)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', KEYS[1], ttl)
return {allowed, math.floor(tokens)}
"""


class RedisTokenBucket:
    """Atomic token buckets shared by every application worker."""

    def __init__(self, redis_url: str) -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)

    def consume(self, identifier: str, path: str, rate: int, burst: int) -> tuple[bool, int]:
        key_hash = hashlib.sha256(f"{identifier}\n{path}".encode("utf-8")).hexdigest()
        ttl_seconds = max(60, int((max(1, burst) / max(1, rate)) * 2) + 1)
        result = self._client.eval(
            _REDIS_TOKEN_BUCKET_SCRIPT,
            1,
            f"bsc:rate-limit:{key_hash}",
            time.time(),
            rate,
            burst,
            ttl_seconds,
        )
        return bool(int(result[0])), max(0, int(result[1]))


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
        self._backend = str(settings.RATE_LIMIT_BACKEND).lower()
        self._distributed_bucket = (
            RedisTokenBucket(settings.REDIS_URL) if self._backend == "redis" else None
        )

    def _limits_for_path(self, path: str) -> tuple[int, int]:
        path_config = self._PATH_RATE_LIMITS.get(path)
        if path_config:
            return path_config["rate"], path_config["burst"]
        return self._rate, self._burst
    
    async def _get_bucket(self, key: str, path: str = "") -> TokenBucket:
        async with self._lock:
            rate, burst = self._limits_for_path(path)
            
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
                return f"key_{hashlib.sha256(api_key.encode('utf-8')).hexdigest()}"
        signed_api_key = getattr(request.state, "signed_api_key", "")
        if signed_api_key:
            return f"key_{hashlib.sha256(signed_api_key.encode('utf-8')).hexdigest()}"
        
        client_ip = request.client.host if request.client else "unknown"
        return f"ip_{client_ip}"
    
    def _is_whitelisted(self, path: str) -> bool:
        """检查路径是否在白名单中"""
        whitelist_paths = settings.AUTH_WHITELIST_PATHS if hasattr(settings, 'AUTH_WHITELIST_PATHS') else ['/health', '/docs', '/openapi.json', '/agent/']
        whitelist_prefixes = settings.AUTH_WHITELIST_PREFIXES if hasattr(settings, 'AUTH_WHITELIST_PREFIXES') else ['/health', '/docs', '/openapi', '/agent', '/static']
        if path in whitelist_paths:
            return True
        for prefix in whitelist_prefixes:
            if path.startswith(prefix):
                return True
        if path.startswith("/api/files"):
            return True
        return False

    async def _consume(self, identifier: str, path: str) -> tuple[bool, int, int, int] | None:
        rate, burst = self._limits_for_path(path)
        if self._distributed_bucket is not None:
            try:
                allowed, remaining = await asyncio.to_thread(
                    self._distributed_bucket.consume, identifier, path, rate, burst
                )
                return allowed, remaining, rate, burst
            except Exception:
                logger.exception("distributed rate limiter is unavailable")
                if settings.is_production:
                    return None

        bucket = await self._get_bucket(identifier, path)
        return bucket.consume(), bucket.get_remaining(), bucket.rate, bucket.burst
    
    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)
        
        path = request.url.path
        if self._is_whitelisted(path):
            return await call_next(request)
        
        identifier = self._get_identifier(request)
        limit = await self._consume(identifier, path)
        if limit is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_UNAVAILABLE",
                        "message": "Request protection is temporarily unavailable.",
                    },
                },
            )
        allowed, remaining, rate, burst = limit
        
        if not allowed:
            retry_after = max(1, int((1 - remaining / burst) * 60))
            
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please retry later.",
                        "retry_after_sec": retry_after,
                        "rate_limit": {
                            "rate": rate,
                            "burst": burst,
                            "remaining": remaining,
                        },
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Rate": str(rate),
                    "X-RateLimit-Burst": str(burst),
                    "X-RateLimit-Remaining": str(remaining),
                },
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Rate"] = str(rate)
        response.headers["X-RateLimit-Burst"] = str(burst)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
