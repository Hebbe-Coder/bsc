"""Authentication Middleware - API密钥认证"""
import logging
import hmac
import hashlib
import sqlite3
from typing import Optional, Tuple

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.knowledge import metrics as _metrics

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

        # ---- 知识库端点：始终需有效 Key；支持 admin / reader / project_* 多种角色 ----
        if path.startswith("/knowledge/"):
            if not has_bearer:
                _metrics.metrics.record_auth_failure()
                raise HTTPException(
                    status_code=401,
                    detail="知识库端点已强制鉴权：请在请求头携带 Authorization: Bearer <API_KEY>",
                )
            auth = resolve_knowledge_auth(api_key)
            if auth is None:
                _metrics.metrics.record_auth_failure()
                raise HTTPException(status_code=401, detail="无效的API密钥")
            request.state.knowledge_role = auth[0]
            request.state.knowledge_project_id = auth[1]
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
        兼容旧调用方：仅返回全局角色（不含 project key）。
        """
        return _global_role(api_key)

    def _is_whitelisted(self, request: Request) -> bool:
        """判断请求路径是否在白名单中"""
        path = request.url.path
        for whitelist_path in _WHITELIST_PATHS:
            if path == whitelist_path or path.startswith(whitelist_path):
                return True
        return False


def _global_role(api_key: str) -> Optional[str]:
    """解析全局角色：admin（API_KEY）或 reader（API_KEY_READER）。

    使用 hmac.compare_digest 进行常量时间比较，避免时序侧信道。
    """
    if settings.API_KEY and hmac.compare_digest(api_key, settings.API_KEY):
        return "admin"
    reader_key = getattr(settings, "API_KEY_READER", "") or ""
    if reader_key and hmac.compare_digest(api_key, reader_key):
        return "reader"
    return None


def _resolve_project_key(api_key: str, repo=None):
    """按 key 哈希在知识库项目中解析项目级角色。

    返回 (role, project_id) 或 None。
    若项目密钥表/数据库不可用（如 schema 未迁移），按“无项目密钥”失败关闭返回 None，
    避免将鉴权路径变成 500。
    """
    from app.repositories.knowledge_repository import KnowledgeRepository

    repo = repo or KnowledgeRepository()
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    try:
        return repo.get_project_key_by_hash(key_hash)
    except sqlite3.Error:
        logger.warning("项目密钥查询失败（可能 schema 未迁移），按无项目密钥处理")
        return None


def resolve_knowledge_auth(api_key: str, repo=None) -> Optional[Tuple[str, str]]:
    """统一解析知识库鉴权：返回 (role, project_id) 或 None。

    role ∈ {admin, reader, project_admin, project_reader}；
    admin / reader 的 project_id 为 None。
    """
    if not api_key:
        return None
    role = _global_role(api_key)
    if role in ("admin", "reader"):
        return (role, None)
    proj = _resolve_project_key(api_key, repo=repo)
    if proj:
        return proj
    return None