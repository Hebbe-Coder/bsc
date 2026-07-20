"""Shared production guards for explicit LLM execution modes."""

from __future__ import annotations

from app.core.config import settings


def ensure_mock_allowed(component: str) -> None:
    """Reject development-only mock output when production has not opted in."""
    if settings.is_production and not settings.ALLOW_MOCK_LLM_IN_PRODUCTION:
        raise RuntimeError(f"{component} mock LLM output is disabled in production")


def ensure_fallback_allowed(component: str) -> None:
    """Reject synthetic fallback output when production has not opted in."""
    if settings.is_production and not settings.ALLOW_LLM_FALLBACK:
        raise RuntimeError(f"{component} LLM fallback is disabled in production")
