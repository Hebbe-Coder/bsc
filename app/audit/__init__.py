"""可信审计整合：把 A 的方法论引用与 B 的约束覆盖缝合成单一可验证审计链。"""
from __future__ import annotations

from .trusted_chain import (
    build_trusted_audit,
    verify_trusted_audit,
    collect_source_refs,
)

__all__ = ["build_trusted_audit", "verify_trusted_audit", "collect_source_refs"]
