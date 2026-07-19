"""通用 admin 鉴权依赖（非知识库端点使用）。
与 knowledge_api.require_admin 不同：不读取 request.state.knowledge_role
（该字段仅由 AuthMiddleware 在 /knowledge/* 路径设置），直接比对全局 API_KEY。
"""
import hmac
import logging
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Query, Request

from app.core.config import settings

logger = logging.getLogger(__name__)

_DOWNLOAD_TOKENS = {}


def _extract_bearer(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _check_admin(api_key: Optional[str]) -> bool:
    """校验 admin API_KEY；返回 True 或通过 HTTPException 拒绝。
    开发模式（API_KEY 未配置且非生产）放行，与中间件既有行为一致。"""
    if not api_key:
        if not settings.API_KEY and not settings.is_production:
            return True
        raise HTTPException(status_code=401, detail="未提供认证信息，请在请求头添加 Authorization: Bearer <API_KEY>")
    if not settings.API_KEY:
        if settings.is_production:
            raise HTTPException(status_code=500, detail="服务配置不完整，请联系管理员")
        return True
    if not hmac.compare_digest(api_key, settings.API_KEY):
        raise HTTPException(status_code=401, detail="无效的API密钥")
    return True


def verify_admin_key(request: Request) -> bool:
    """路由级 admin 鉴权依赖（如 /dashboard/*）。"""
    return _check_admin(_extract_bearer(request))


def _validate_download_token(token: str) -> Optional[str]:
    """验证一次性下载token，返回对应的文件名或None。"""
    if token in _DOWNLOAD_TOKENS:
        entry = _DOWNLOAD_TOKENS[token]
        if time.time() < entry["expires"]:
            filename = entry["filename"]
            del _DOWNLOAD_TOKENS[token]
            return filename
        else:
            del _DOWNLOAD_TOKENS[token]
    return None


def verify_download_auth(request: Request, token: Optional[str] = Query(default=None)) -> bool:
    """下载端点鉴权：Bearer API_KEY 或一次性 ?token= 二选一。"""
    if token:
        if _validate_download_token(token):
            return True
    return _check_admin(_extract_bearer(request))


def download_url(filename: str) -> str:
    """构建受保护下载 URL，使用一次性token代替API_KEY明文。"""
    import os
    safe = os.path.basename(filename)
    token = secrets.token_urlsafe(32)
    _DOWNLOAD_TOKENS[token] = {
        "filename": safe,
        "expires": time.time() + 3600
    }
    return f"/api/files/{safe}?token={token}"
