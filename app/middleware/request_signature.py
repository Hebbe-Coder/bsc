"""
Request Signature Middleware - 验证请求签名

实现基于HMAC的请求签名验证，防止请求被篡改。

签名格式：
    Authorization: Signature key=<API_KEY>,timestamp=<TIMESTAMP>,signature=<SIGNATURE>

签名算法：
    signature = HMAC-SHA256(api_key, timestamp + method + path + body_md5)

配置方式：
    SIGNATURE_ENABLED=True      # 是否启用签名验证
    SIGNATURE_TTL=300           # 签名有效期（秒）
"""
from __future__ import annotations
import hashlib
import hmac
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class RequestSignatureMiddleware(BaseHTTPMiddleware):
    """请求签名验证中间件"""
    
    def __init__(self, app):
        super().__init__(app)
        self._enabled = settings.effective_signature_enabled if hasattr(settings, 'effective_signature_enabled') else False
        self._ttl = settings.SIGNATURE_TTL
    
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
    
    def _parse_signature(self, auth_header: str) -> dict:
        """解析签名头"""
        parts = {}
        try:
            for part in auth_header.split(","):
                key_value = part.strip().split("=")
                if len(key_value) == 2:
                    parts[key_value[0].strip()] = key_value[1].strip()
        except Exception as e:
            logger.warning(f"解析签名头失败: {e}")
        return parts
    
    def _compute_signature(self, api_key: str, timestamp: str, 
                          method: str, path: str, body_md5: str) -> str:
        """计算签名"""
        message = f"{timestamp}{method.upper()}{path}{body_md5}"
        return hmac.new(
            api_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
    
    def _compute_body_md5(self, body: bytes) -> str:
        """计算请求体MD5（用于内容标识，非安全用途）"""
        return hashlib.md5(body, usedforsecurity=False).hexdigest()
    
    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)
        
        path = request.url.path
        if self._is_whitelisted(path):
            return await call_next(request)
        
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Signature "):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_SIGNATURE",
                        "message": "无效的签名格式，请使用 Authorization: Signature key=<API_KEY>,timestamp=<TIMESTAMP>,signature=<SIGNATURE>",
                    }
                },
            )
        
        sig_parts = self._parse_signature(auth_header[10:])
        api_key = sig_parts.get("key", "")
        timestamp = sig_parts.get("timestamp", "")
        signature = sig_parts.get("signature", "")
        
        if not api_key or not timestamp or not signature:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "MISSING_SIGNATURE_PARAMS",
                        "message": "缺少签名参数，请提供key、timestamp和signature",
                    }
                },
            )
        
        try:
            ts = int(timestamp)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_TIMESTAMP",
                        "message": "无效的时间戳格式",
                    }
                },
            )
        
        now = int(time.time())
        if abs(now - ts) > self._ttl:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "EXPIRED_SIGNATURE",
                        "message": f"签名已过期，请重新生成（有效期{self._ttl}秒）",
                        "current_time": now,
                        "signature_time": ts,
                    }
                },
            )
        
        if not hmac.compare_digest(api_key, settings.API_KEY):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_API_KEY",
                        "message": "无效的API密钥",
                    }
                },
            )
        
        body = await request.body()
        body_md5 = self._compute_body_md5(body)
        
        expected_signature = self._compute_signature(api_key, timestamp, 
                                                    request.method, path, body_md5)
        
        if not hmac.compare_digest(signature, expected_signature):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "SIGNATURE_MISMATCH",
                        "message": "签名验证失败，请求可能被篡改",
                    }
                },
            )
        
        return await call_next(request)