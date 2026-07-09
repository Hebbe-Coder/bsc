"""Authentication Middleware - API密钥认证"""
import logging
import hmac
import hashlib
from typing import Optional

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
    - /knowledge/* 端点：无论环境都强制鉴权，且支持 admin / reader 两种角色
      （admin = 全局 API_KEY；reader = API_KEY_READER，仅可读/检索）。
    - 非知识库端点：仅全局 API_KEY 有效；API_KEY 未配置时开发模式放行、生产模式拒绝。
    - 白名单路径（/docs、/health 等）跳过鉴权。
    """

    async def dispatch(self, request: Request, call_next):
        if self._is_whitelisted(request):
            return await call_next(request)

        path = request.url.path
        auth_header = request.headers.get("Authorization", "")
        has_bearer = auth_header.startswith("Bearer ")
        api_key = auth_header[7:] if has_bearer else None

        # ---- 知识库端点：始终需有效 Key；支持 admin / reader 两种角色 ----
        if path.startswith("/knowledge/"):
            if not has_bearer:
                raise HTTPException(
                    status_code=401,
                    detail="知识库端点已强制鉴权：请在请求头携带 Authorization: Bearer <API_KEY>",
                )
            role = self._resolve_knowledge_role(api_key)
            if role is None:
                raise HTTPException(status_code=401, detail="无效的API密钥")
            request.state.knowledge_role = role
            return await call_next(request)

        # ---- 非知识库端点：原鉴权逻辑（仅 admin key 有效；dev 未配置则放行）----
        if not has_bearer:
            if not settings.API_KEY and not settings.is_production:
                logger.warning("API_KEY未配置，非知识库请求将被允许（仅开发环境）")
                return await call_next(request)
            raise HTTPException(status_code=401, detail="未提供认证信息，请在请求头中添加 Authorization: Bearer <API_KEY>")

        if not settings.API_KEY:
            if settings.is_production:
                logger.critical("API_KEY未配置，生产环境拒绝所有请求")
                raise HTTPException(status_code=500, detail="服务配置不完整，请联系管理员")
            logger.warning("API_KEY未配置，非知识库请求将被允许（仅开发环境）")
            return await call_next(request)

        if not hmac.compare_digest(api_key, settings.API_KEY):
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            logger.warning(f"无效的API密钥尝试，密钥哈希: {api_key_hash}")
            raise HTTPException(status_code=401, detail="无效的API密钥")

        return await call_next(request)

    def _resolve_knowledge_role(self, api_key: str) -> Optional[str]:
        """解析知识库端点的角色：admin（全局 API_KEY）或 reader（API_KEY_READER）。

        reader key 仅对 /knowledge/* 生效，且不授予非知识库端点的访问权。
        """
        if settings.API_KEY and hmac.compare_digest(api_key, settings.API_KEY):
            return "admin"
        reader_key = getattr(settings, "API_KEY_READER", "") or ""
        if reader_key and hmac.compare_digest(api_key, reader_key):
            return "reader"
        return None

    def _is_whitelisted(self, request: Request) -> bool:
        """判断请求路径是否在白名单中"""
        path = request.url.path
        for whitelist_path in _WHITELIST_PATHS:
            if path == whitelist_path or path.startswith(whitelist_path):
                return True
        return False