"""知识域统一配置中心。

将原先分散在 service.py / reranker.py / agent_router.py 中的域定义集中管理，
并提供文档→域、查询→域的统一推断接口。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── 默认知识域定义 ──────────────────────────────────────────────
# 每个域包含：名称、描述、关键词、可用工具、默认 metadata 过滤器
DEFAULT_DOMAINS: Dict[str, dict] = {
    "content_safety": {
        "name": "内容安全",
        "description": "内容审核、违规处理、安全策略",
        "keywords": ["内容安全", "违规", "审核", "风控", "色情", "暴力", "谣言", "敏感词", "封禁"],
        "tools": ["search"],
        "metadata_filters": {"domain": "content_safety"},
    },
    "teacher_management": {
        "name": "师资管理",
        "description": "教师招聘、培训、绩效、流失预警",
        "keywords": ["教师", "师资", "招聘", "培训", "绩效", "流失", "离职", "讲师", "教员"],
        "tools": ["search", "database"],
        "metadata_filters": {"domain": "teacher_management"},
    },
    "coffee": {
        "name": "咖啡工艺",
        "description": "咖啡烘焙、温度控制、风味特征",
        "keywords": ["咖啡", "烘焙", "温度", "风味", "工艺", "咖啡豆", "脱水", "梅纳", "焦糖"],
        "tools": ["search"],
        "metadata_filters": {"domain": "coffee"},
    },
    "business_process": {
        "name": "业务流程",
        "description": "流程自动化、SOP、工作流",
        "keywords": ["流程", "SOP", "自动化", "工作流", "编排", "工序", "审批流"],
        "tools": ["search", "api"],
        "metadata_filters": {"domain": "business_process"},
    },
    "compliance": {
        "name": "合规管理",
        "description": "合规规范、政策制度、审计",
        "keywords": ["合规", "规范", "制度", "政策", "审计", "法规", "法律"],
        "tools": ["search"],
        "metadata_filters": {"domain": "compliance"},
    },
    "quality": {
        "name": "质量管理",
        "description": "质量标准、验收检测、评估",
        "keywords": ["质量", "验收", "标准", "评估", "检测", "测试", "QA"],
        "tools": ["search", "database"],
        "metadata_filters": {"domain": "quality"},
    },
    "risk": {
        "name": "风险管理",
        "description": "风险预警、异常处理、故障排查",
        "keywords": ["风险", "预警", "异常", "故障", "隐患", "应急", "排查"],
        "tools": ["search", "api"],
        "metadata_filters": {"domain": "risk"},
    },
    "general": {
        "name": "通用知识",
        "description": "综合知识查询",
        "keywords": [],
        "tools": ["search"],
        "metadata_filters": {},
    },
}


class DomainRegistry:
    """知识域注册表：管理域定义、推断文档/查询所属域。

    支持运行时动态注册自定义域（如项目级别的专属域）。
    """

    def __init__(self):
        self._domains: Dict[str, dict] = {k: dict(v) for k, v in DEFAULT_DOMAINS.items()}

    def register(self, domain_id: str, config: dict) -> None:
        """注册或更新一个知识域。"""
        self._domains[domain_id] = config
        logger.info("注册知识域: %s (%s)", domain_id, config.get("name", ""))

    def get(self, domain_id: str) -> Optional[dict]:
        return self._domains.get(domain_id)

    def all(self) -> Dict[str, dict]:
        return self._domains

    def list_ids(self) -> List[str]:
        return list(self._domains.keys())

    # ── 推断接口 ────────────────────────────────────────────────

    def infer_from_text(self, text: str) -> str:
        """根据文本内容推断所属知识域（用于文档入库时自动标注）。"""
        if not text:
            return "general"
        text_lower = text.lower()
        best_domain = "general"
        best_score = 0
        for domain_id, config in self._domains.items():
            if domain_id == "general":
                continue
            keywords = config.get("keywords", [])
            score = sum(1 for kw in keywords if kw in text_lower or kw.lower() in text_lower)
            if score > best_score:
                best_score = score
                best_domain = domain_id
        return best_domain

    def infer_from_query(self, query: str) -> List[str]:
        """根据查询推断可能的知识域（可多选），返回域 ID 列表。"""
        if not query:
            return ["general"]
        query_lower = query.lower()
        matched = []
        for domain_id, config in self._domains.items():
            if domain_id == "general":
                continue
            keywords = config.get("keywords", [])
            if any(kw in query_lower or kw.lower() in query_lower for kw in keywords):
                matched.append(domain_id)
        if not matched:
            return ["general"]
        return matched

    def infer_from_doc_title(self, title: str) -> str:
        """根据文档标题推断知识域。"""
        return self.infer_from_text(title)

    def get_domain_name(self, domain_id: str) -> str:
        config = self._domains.get(domain_id)
        return config["name"] if config else domain_id

    def get_domain_tools(self, domain_id: str) -> List[str]:
        config = self._domains.get(domain_id)
        return config.get("tools", ["search"]) if config else ["search"]


# ── 全局单例 ────────────────────────────────────────────────────
_registry: Optional[DomainRegistry] = None


def get_domain_registry() -> DomainRegistry:
    global _registry
    if _registry is None:
        _registry = DomainRegistry()
    return _registry


def reset_domain_registry() -> None:
    """重置为默认域配置（主要用于测试）。"""
    global _registry
    _registry = DomainRegistry()
