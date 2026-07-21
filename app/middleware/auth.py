"""Bearer and same-origin signed-session authentication middleware."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.knowledge import metrics as _metrics


logger = logging.getLogger(__name__)


def _normalize_path(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


@dataclass(frozen=True)
class AuthPrincipal:
    role: str
    tenant_id: str
    project_id: str | None
    principal_id: str
    browser_session_id: str


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate APIs and bind each request to a scoped principal."""

    async def dispatch(self, request: Request, call_next):
        # CORS preflight has no bearer token and never reaches an application
        # handler. Let CORSMiddleware attach its policy response first.
        if request.method == "OPTIONS":
            return await call_next(request)
        if self._is_whitelisted(request):
            return await call_next(request)

        bearer = _extract_bearer(request)
        supports_browser_session = (
            request.url.path.startswith("/api/orchestrate")
            or request.url.path == "/agent/analyze"
        )
        principal = (
            _principal_from_bearer(bearer)
            if bearer
            else _principal_from_cookie(request) if supports_browser_session else None
        )
        issued_cookie = False

        if principal is None and request.url.path.startswith("/knowledge/"):
            _metrics.metrics.record_auth_failure()
            return _auth_error(401, "authentication required")
        if principal is None and not settings.API_KEY and not settings.is_production:
            principal = _development_principal()
            issued_cookie = True
        elif principal is None:
            _metrics.metrics.record_auth_failure()
            return _auth_error(401, "authentication required")

        if bearer and supports_browser_session:
            # A successful bearer authentication always renews the browser session.
            principal = _with_browser_session(principal, request.cookies.get(settings.AUTH_SESSION_COOKIE))
            issued_cookie = True

        if principal.role == "reader" and not request.url.path.startswith("/knowledge/"):
            return _auth_error(403, "read-only key cannot access this endpoint")
        if principal.role.startswith("project_") and not (
            request.url.path.startswith("/knowledge/")
            or request.url.path.startswith("/api/orchestrate")
            or request.url.path.startswith("/api/mcp")
        ):
            return _auth_error(403, "project key is not valid for this endpoint")

        _set_request_principal(request, principal)
        response = await call_next(request)
        if issued_cookie:
            _set_session_cookie(response, principal)
        return response

    def _resolve_knowledge_role(self, api_key: str) -> Optional[str]:
        return _global_role(api_key)

    def _is_whitelisted(self, request: Request) -> bool:
        path = _normalize_path(request.url.path)
        if ".." in path:
            logger.warning("path traversal attempt rejected: %s", request.url.path)
            return False
        if path in settings.AUTH_WHITELIST_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in settings.AUTH_WHITELIST_PREFIXES)


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else None


def _auth_error(status_code: int, detail: str) -> JSONResponse:
    """Return auth failures directly; HTTPException escapes BaseHTTPMiddleware."""
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _global_role(api_key: str) -> Optional[str]:
    if settings.API_KEY and hmac.compare_digest(api_key, settings.API_KEY):
        return "admin"
    reader_key = settings.API_KEY_READER
    if reader_key and hmac.compare_digest(api_key, reader_key):
        return "reader"
    return None


def _resolve_project_key(api_key: str, repo=None):
    from app.repositories.knowledge_repository import KnowledgeRepository

    repo = repo or KnowledgeRepository()
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    try:
        return repo.get_project_key_by_hash(key_hash)
    except Exception:
        logger.warning("project key lookup failed; rejecting request", exc_info=True)
        return None


def resolve_knowledge_auth(api_key: str, repo=None) -> Optional[Tuple[str, str]]:
    if not api_key:
        return None
    role = _global_role(api_key)
    if role in ("admin", "reader"):
        return role, None
    return _resolve_project_key(api_key, repo=repo)


def _principal_from_bearer(api_key: str | None) -> AuthPrincipal | None:
    if not api_key:
        return None
    auth = resolve_knowledge_auth(api_key)
    if auth is None:
        return None
    role, project_id = auth
    return AuthPrincipal(
        role=role,
        tenant_id=settings.DEFAULT_TENANT_ID,
        project_id=project_id,
        principal_id=hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
        browser_session_id="",
    )


def _development_principal() -> AuthPrincipal:
    return AuthPrincipal(
        role="admin",
        tenant_id=settings.DEFAULT_TENANT_ID,
        project_id=None,
        principal_id="development",
        browser_session_id=secrets.token_urlsafe(18),
    )


def _with_browser_session(principal: AuthPrincipal, cookie: str | None) -> AuthPrincipal:
    existing = _decode_session(cookie or "")
    if existing and _same_principal(existing, principal):
        session_id = str(existing.get("sid", ""))
    else:
        session_id = secrets.token_urlsafe(18)
    return AuthPrincipal(
        role=principal.role,
        tenant_id=principal.tenant_id,
        project_id=principal.project_id,
        principal_id=principal.principal_id,
        browser_session_id=session_id,
    )


def _principal_from_cookie(request: Request) -> AuthPrincipal | None:
    payload = _decode_session(request.cookies.get(settings.AUTH_SESSION_COOKIE, ""))
    if payload is None:
        return None
    return AuthPrincipal(
        role=str(payload["role"]),
        tenant_id=str(payload["tenant_id"]),
        project_id=payload.get("project_id") or None,
        principal_id=str(payload["principal_id"]),
        browser_session_id=str(payload["sid"]),
    )


def _set_request_principal(request: Request, principal: AuthPrincipal) -> None:
    request.state.auth_principal = principal
    request.state.auth_role = principal.role
    request.state.tenant_id = principal.tenant_id
    request.state.project_id = principal.project_id
    request.state.principal_id = principal.principal_id
    request.state.browser_session_id = principal.browser_session_id
    if request.url.path.startswith("/knowledge/"):
        request.state.knowledge_role = principal.role
        request.state.knowledge_project_id = principal.project_id


def _set_session_cookie(response: Any, principal: AuthPrincipal) -> None:
    response.set_cookie(
        key=settings.AUTH_SESSION_COOKIE,
        value=_encode_session(principal),
        max_age=settings.AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE or settings.is_production,
        samesite="lax",
        path="/",
    )


def _encode_session(principal: AuthPrincipal) -> str:
    payload = {
        "role": principal.role,
        "tenant_id": principal.tenant_id,
        "project_id": principal.project_id or "",
        "principal_id": principal.principal_id,
        "sid": principal.browser_session_id,
        "exp": int(time.time()) + settings.AUTH_SESSION_TTL_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_session_secret(), encoded, hashlib.sha256).hexdigest().encode("ascii")
    return f"{encoded.decode('ascii')}.{signature.decode('ascii')}"


def _decode_session(value: str) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    encoded_text, signature_text = value.rsplit(".", 1)
    encoded = encoded_text.encode("ascii", "ignore")
    expected = hmac.new(_session_secret(), encoded, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature_text, expected):
        return None
    try:
        padded = encoded + b"=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    required = {"role", "tenant_id", "principal_id", "sid", "exp"}
    if not required.issubset(payload) or int(payload["exp"]) < int(time.time()):
        return None
    return payload


def _session_secret() -> bytes:
    secret = settings.AUTH_SESSION_SECRET or settings.API_KEY or "development-session-secret"
    return secret.encode("utf-8")


def _same_principal(payload: dict[str, Any], principal: AuthPrincipal) -> bool:
    return (
        payload.get("principal_id") == principal.principal_id
        and payload.get("tenant_id") == principal.tenant_id
        and (payload.get("project_id") or None) == principal.project_id
        and payload.get("role") == principal.role
    )
