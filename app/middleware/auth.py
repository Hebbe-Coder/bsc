"""Authentication Middleware - API密钥认证"""
import logging
import hmac
import hashlib
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

logger = logging.getLogger(__name__)

_WHITELIST_PATHS = {
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/metrics",
    "/metrics/prometheus",
    "/dashboard/",
    "/static/",
    "/output/",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """API密钥认证中间件
    
    安全策略：
    - 如果API_KEY未设置且环境为生产模式，拒绝所有请求
    - 如果API_KEY未设置且环境为开发模式，允许访问但记录警告
    - 如果API_KEY已设置，强制验证Bearer Token（白名单路径除外）
    """

    async def dispatch(self, request: Request, call_next):
        if self._is_whitelisted(request):
            return await call_next(request)

        if not settings.API_KEY:
            if settings.is_production:
                logger.critical("API_KEY未配置，生产环境拒绝所有请求")
                raise HTTPException(status_code=500, detail="服务配置不完整，请联系管理员")
            else:
                logger.warning("API_KEY未配置，所有请求将被允许（仅开发环境）")
                return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            raise HTTPException(status_code=401, detail="未提供认证信息，请在请求头中添加 Authorization: Bearer <API_KEY>")

        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="认证格式错误，应为 Bearer token")

        api_key = auth_header[7:]
        if not hmac.compare_digest(api_key, settings.API_KEY):
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            logger.warning(f"无效的API密钥尝试，密钥哈希: {api_key_hash}")
            raise HTTPException(status_code=401, detail="无效的API密钥")

        return await call_next(request)

    def _is_whitelisted(self, request: Request) -> bool:
        """判断请求路径是否在白名单中"""
        path = request.url.path
        for whitelist_path in _WHITELIST_PATHS:
            if path == whitelist_path or path.startswith(whitelist_path):
                return True
        return False