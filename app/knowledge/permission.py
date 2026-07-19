"""权限控制层：三级权限体系（知识域 -> 文档 -> 章节）。

生产级 RAG 的核心安全组件：
- 角色定义：admin、editor、viewer、guest
- 三级权限粒度：知识域级别 -> 文档级别 -> 章节级别
- 每级可独立设置访问级别，低级权限不能超过高级（向下收敛）
- 基于角色的访问控制（RBAC）
"""
from __future__ import annotations
import logging
from typing import Dict, Optional, List, Tuple

from app.knowledge.knowledge_domains import get_domain_registry

logger = logging.getLogger(__name__)

# ── 角色定义 ────────────────────────────────────────────────────
ROLES = {
    "admin":    {"name": "管理员",  "permissions": ["read", "write", "delete", "manage"]},
    "editor":   {"name": "编辑者",  "permissions": ["read", "write"]},
    "viewer":   {"name": "查看者",  "permissions": ["read"]},
    "guest":    {"name": "访客",    "permissions": ["read"]},
}

ROLE_HIERARCHY = {"admin": 4, "editor": 3, "viewer": 2, "guest": 1}

# ── 访问级别（数值越大越严格）────────────────────────────────────
ACCESS_LEVELS = {
    "public":       0,  # 所有人可见
    "internal":     1,  # 内部员工可见
    "private":      2,  # 编辑以上可见
    "confidential": 3,  # 仅管理员可见
}

# 每个访问级别对应的可访问角色
ACCESS_LEVEL_ROLES = {
    "public":       ["admin", "editor", "viewer", "guest"],
    "internal":     ["admin", "editor", "viewer"],
    "private":      ["admin", "editor"],
    "confidential": ["admin"],
}

# 默认域权限（与知识域配置中心保持一致）
DEFAULT_DOMAIN_ACCESS = {
    "content_safety":    "private",
    "teacher_management": "internal",
    "coffee":            "public",
    "business_process":   "internal",
    "compliance":        "private",
    "quality":           "internal",
    "risk":              "private",
    "general":           "public",
}


def _compare_access_level(a: str, b: str) -> int:
    """比较两个访问级别：a > b 返回 1，a == b 返回 0，a < b 返回 -1。"""
    la = ACCESS_LEVELS.get(a, 99)
    lb = ACCESS_LEVELS.get(b, 99)
    if la > lb:
        return 1
    if la < lb:
        return -1
    return 0


def _restrict_access_level(parent: str, child: str) -> str:
    """子级权限不能超过父级（向下收敛）。
    如果子级比父级更宽松，返回父级；否则返回子级。
    """
    if _compare_access_level(child, parent) < 0:
        return parent
    return child


class PermissionManager:
    """权限管理器：三级权限检查（域 -> 文档 -> 章节）。"""

    def __init__(self):
        self._user_roles: Dict[str, str] = {}

    # ── 用户角色 ────────────────────────────────────────────────

    def get_user_role(self, user_id: str) -> str:
        return self._user_roles.get(user_id, "guest")

    def set_user_role(self, user_id: str, role: str):
        if role not in ROLES:
            raise ValueError(f"未知角色: {role}")
        self._user_roles[user_id] = role

    def check_permission(self, user_id: str, permission: str) -> bool:
        role = self.get_user_role(user_id)
        return permission in ROLES.get(role, {}).get("permissions", [])

    def role_can_access_level(self, role: str, access_level: str) -> bool:
        """判断角色是否可以访问指定访问级别。"""
        allowed_roles = ACCESS_LEVEL_ROLES.get(access_level, ["admin"])
        return role in allowed_roles

    # ── 域级别权限 ──────────────────────────────────────────────

    def get_domain_access_level(self, domain: str) -> str:
        """获取知识域的默认访问级别。"""
        return DEFAULT_DOMAIN_ACCESS.get(domain, "public")

    def can_access_domain(self, user_id: str, domain: str) -> bool:
        role = self.get_user_role(user_id)
        access_level = self.get_domain_access_level(domain)
        return self.role_can_access_level(role, access_level)

    def list_allowed_domains(self, user_id: str) -> List[str]:
        """列出用户可访问的所有知识域。"""
        registry = get_domain_registry()
        allowed = []
        for domain_id in registry.list_ids():
            if self.can_access_domain(user_id, domain_id):
                allowed.append(domain_id)
        return allowed

    # ── 文档级别权限 ────────────────────────────────────────────

    def effective_doc_access_level(self, domain: str, doc_access: Optional[str] = None) -> str:
        """文档有效访问级别 = max(域级别, 文档级别)。
        文档级别不能比域级别更宽松。
        """
        domain_level = self.get_domain_access_level(domain)
        if not doc_access:
            return domain_level
        return _restrict_access_level(domain_level, doc_access)

    def can_access_document(self, user_id: str, domain: str,
                            doc_access: Optional[str] = None) -> bool:
        role = self.get_user_role(user_id)
        effective_level = self.effective_doc_access_level(domain, doc_access)
        return self.role_can_access_level(role, effective_level)

    # ── 章节级别权限 ────────────────────────────────────────────

    def effective_chunk_access_level(self, domain: str,
                                      doc_access: Optional[str] = None,
                                      chunk_access: Optional[str] = None) -> str:
        """章节有效访问级别 = max(域级别, 文档级别, 章节级别)。
        章节级别不能比文档级别更宽松。
        """
        doc_level = self.effective_doc_access_level(domain, doc_access)
        if not chunk_access:
            return doc_level
        return _restrict_access_level(doc_level, chunk_access)

    def can_access_chunk(self, user_id: str, domain: str,
                         doc_access: Optional[str] = None,
                         chunk_access: Optional[str] = None) -> bool:
        role = self.get_user_role(user_id)
        effective_level = self.effective_chunk_access_level(domain, doc_access, chunk_access)
        return self.role_can_access_level(role, effective_level)

    # ── 批量过滤 ────────────────────────────────────────────────

    def filter_chunks_by_permission(self, user_id: str, chunks: List[Dict]) -> List[Dict]:
        """对 chunk 列表进行三级权限过滤。

        每个 chunk 需要包含：domain, doc_access(可选), chunk_access(可选)
        """
        result = []
        for chunk in chunks:
            domain = chunk.get("domain", "general")
            doc_access = chunk.get("doc_access")
            chunk_access = chunk.get("chunk_access")
            if self.can_access_chunk(user_id, domain, doc_access, chunk_access):
                result.append(chunk)
        return result

    def get_permission_filters(self, user_id: str) -> Dict:
        """获取权限过滤参数，供检索层使用。"""
        role = self.get_user_role(user_id)
        allowed_domains = self.list_allowed_domains(user_id)

        return {
            "user_id": user_id,
            "role": role,
            "allowed_domains": allowed_domains,
        }


class MockPermissionManager(PermissionManager):
    """Mock 权限管理器：预置 4 个测试用户。"""

    def __init__(self):
        super().__init__()
        self._user_roles = {
            "user-001": "admin",    # 管理员 - 可访问所有
            "user-002": "editor",   # 编辑者 - 可访问 internal 及以上
            "user-003": "viewer",   # 查看者 - 可访问 public + internal
            "user-004": "guest",    # 访客 - 只能访问 public
        }


def get_permission_manager(mock: bool = True) -> PermissionManager:
    if mock:
        return MockPermissionManager()
    return PermissionManager()
