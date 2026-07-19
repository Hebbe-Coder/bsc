"""Query Rewrite 层：将用户口语化问题转换为知识库语言。

生产级 RAG 的核心：
- 同义词扩展：投诉 ≈ 客诉 ≈ 用户反馈
- 意图分类：判断问题属于哪个知识域
- Query Expansion：将单一问题扩展为多个检索词
- Query Decomposition：复杂问题拆分为子问题
- Query Router：根据意图路由到不同知识库
- LLM智能扩展：接入大模型进行语义级别的查询优化
"""
from __future__ import annotations
import hashlib
import json
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

_CACHE_SIZE = 500

SYNONYM_MAP = {
    "投诉": ["客诉", "用户反馈", "问题反馈", "抱怨", "不满"],
    "客服": ["客户服务", "支持", "帮助中心", "服务台"],
    "违规": ["违法", "不合规", "违反规定", "违纪"],
    "审核": ["审查", "检查", "审批", "复核"],
    "流失": ["离职", "离开", "跳槽", "人才流失"],
    "培训": ["教育", "学习", "训练", "进修"],
    "绩效": ["考核", "评估", "业绩", "成效"],
    "流程": ["步骤", "程序", "环节", "操作流程"],
    "温度": ["热度", "温区", "烘焙温度"],
    "阶段": ["步骤", "阶段", "环节", "流程"],
    "风味": ["口感", "味道", "香气", "风味特征"],
    "咖啡": ["咖啡豆", "咖啡粉", "浓缩咖啡"],
    "烘焙": ["烘烤", "炒制", "烘焙工艺"],
    "教师": ["老师", "教员", "导师", "讲师"],
    "招聘": ["招募", "录用", "入职", "人才引进"],
    "标准": ["规范", "准则", "要求", "条件"],
    "机制": ["体系", "系统", "流程", "方法"],
    "管理": ["治理", "管控", "运营", "监管"],
}

INTENT_PATTERNS = [
    ("content_safety", r"违规|违法|审查|审核|内容安全|风控"),
    ("teacher_management", r"教师|师资|招聘|培训|绩效|流失|离职"),
    ("coffee", r"咖啡|烘焙|温度|风味|工艺"),
    ("business_process", r"流程|步骤|操作|处理|SOP"),
    ("compliance", r"合规|规范|制度|政策|规定"),
    ("quality", r"质量|验收|标准|评估|检测"),
    ("risk", r"风险|预警|异常|错误|故障"),
    ("general", r".*"),
]

QUERY_REWRITE_PROMPT = """你是一个专业的查询改写助手，负责将用户的原始问题转换为适合知识库检索的形式。

任务：
1. 同义词扩展：将问题中的关键词替换为知识库中可能出现的同义词
2. 查询分解：如果问题涉及多个主题，拆分为多个子问题
3. 术语对齐：将口语化表达转换为专业术语

请输出 JSON 格式：
{
  "expanded_queries": ["扩展后的查询1", "扩展后的查询2", "..."],
  "intent": "意图分类（content_safety/teacher_management/coffee/business_process/compliance/quality/risk/general）",
  "keywords": ["提取的关键词列表"],
  "sub_queries": ["子问题1", "子问题2", "..."],
  "rewritten_query": "合并后的改写查询"
}

示例：
输入："怎么降低客服投诉率？"
输出：{
  "expanded_queries": ["客诉闭环管理机制", "用户反馈处理流程", "投诉率优化方法"],
  "intent": "general",
  "keywords": ["客服", "投诉", "客诉"],
  "sub_queries": [],
  "rewritten_query": "客诉闭环管理机制 用户反馈处理流程 投诉率优化"
}

现在处理用户问题：
"""


class QueryRewriter:
    def __init__(self):
        self.synonym_map = SYNONYM_MAP
        self.intent_patterns = INTENT_PATTERNS
        self._cache = {}
        self._cache_order = []

    def _cache_get(self, key: str):
        if key in self._cache:
            idx = self._cache_order.index(key)
            self._cache_order.pop(idx)
            self._cache_order.insert(0, key)
            return self._cache[key]
        return None

    def _cache_set(self, key: str, value):
        if key in self._cache:
            idx = self._cache_order.index(key)
            self._cache_order.pop(idx)
        elif len(self._cache_order) >= _CACHE_SIZE:
            oldest = self._cache_order.pop()
            self._cache.pop(oldest)
        self._cache_order.insert(0, key)
        self._cache[key] = value

    def expand_synonyms(self, query: str) -> List[str]:
        expanded = [query]
        for keyword, synonyms in self.synonym_map.items():
            if keyword in query:
                for synonym in synonyms:
                    if synonym not in query:
                        expanded.append(query.replace(keyword, synonym))
                        expanded.append(query + " " + synonym)
        return list(set(expanded))

    def classify_intent(self, query: str) -> str:
        query_lower = query.lower()
        for intent, pattern in self.intent_patterns:
            if re.search(pattern, query_lower):
                return intent
        return "general"

    def extract_keywords(self, query: str) -> List[str]:
        chinese_pattern = re.compile(r"[\u4e00-\u9fa5]{2,}")
        english_pattern = re.compile(r"[a-zA-Z]+")
        keywords = []
        keywords.extend(chinese_pattern.findall(query))
        keywords.extend(english_pattern.findall(query))
        return list(set(keywords))

    def decompose_query(self, query: str) -> List[str]:
        if "和" in query or "与" in query or "以及" in query:
            parts = re.split(r"[和与以及]", query)
            return [p.strip() for p in parts if p.strip()]
        if "什么共同点" in query or "有什么区别" in query:
            parts = query.replace("什么共同点", "").replace("有什么区别", "").split("和")
            return [p.strip() for p in parts if p.strip()]
        return []

    def rewrite(self, query: str) -> Dict:
        cache_key = hashlib.md5(query.encode()).hexdigest()
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        original = query
        expanded_queries = self.expand_synonyms(query)
        intent = self.classify_intent(query)
        keywords = self.extract_keywords(query)
        sub_queries = self.decompose_query(query)

        result = {
            "original_query": original,
            "expanded_queries": expanded_queries,
            "intent": intent,
            "keywords": keywords,
            "sub_queries": sub_queries,
            "rewritten_query": " ".join(expanded_queries[:3]) if expanded_queries else original,
            "from_llm": False,
        }

        self._cache_set(cache_key, result)
        return result

    def route(self, query: str) -> Dict:
        rewrite_result = self.rewrite(query)
        intent = rewrite_result["intent"]

        knowledge_domains = {
            "content_safety": ["产品知识库", "合规知识库"],
            "teacher_management": ["人力资源知识库", "培训知识库"],
            "coffee": ["产品知识库", "工艺知识库"],
            "business_process": ["流程知识库", "SOP模板库"],
            "compliance": ["合规知识库", "政策知识库"],
            "quality": ["质量知识库", "标准知识库"],
            "risk": ["风险知识库", "历史案例库"],
            "general": ["产品知识库", "行业知识库"],
        }

        return {
            **rewrite_result,
            "knowledge_domains": knowledge_domains.get(intent, ["产品知识库"]),
        }


class MockQueryRewriter(QueryRewriter):
    def rewrite(self, query: str) -> Dict:
        cache_key = hashlib.md5(query.encode()).hexdigest()
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result = super().rewrite(query)
        mock_expanded = [query]

        if "投诉" in query:
            mock_expanded.append("客诉闭环管理机制")
            mock_expanded.append("用户反馈处理流程")
        if "违规" in query:
            mock_expanded.append("内容安全违规类型")
            mock_expanded.append("违规处罚机制")
        if "烘焙" in query:
            mock_expanded.append("咖啡烘焙工艺")
            mock_expanded.append("烘焙温度控制")
        if "流失" in query:
            mock_expanded.append("教师流失预警机制")
            mock_expanded.append("人才保留策略")
        if "和" in query or "与" in query:
            result["sub_queries"] = self.decompose_query(query)

        result["expanded_queries"] = list(set(mock_expanded))
        result["rewritten_query"] = " ".join(result["expanded_queries"])

        self._cache_set(cache_key, result)
        return result


class LLMQueryRewriter(QueryRewriter):
    def __init__(self, provider: str = "mock", keys=None):
        super().__init__()
        self.provider = provider
        self.keys = keys
        self._llm_client = None

    def _get_llm(self):
        if self._llm_client is None:
            from app.services.sop_llm_client import SOPLLMClient
            self._llm_client = SOPLLMClient(self.provider, keys=self.keys)
        return self._llm_client

    def rewrite(self, query: str) -> Dict:
        cache_key = hashlib.md5(query.encode()).hexdigest()
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        llm = self._get_llm()
        if getattr(llm, "provider", "mock") == "mock":
            return self._fallback_rewrite(query, cache_key)

        try:
            prompt = QUERY_REWRITE_PROMPT + query
            raw = llm.chat_structured(prompt, query)
            if raw and isinstance(raw, dict):
                result = {
                    "original_query": query,
                    "expanded_queries": raw.get("expanded_queries", [query]),
                    "intent": raw.get("intent", "general"),
                    "keywords": raw.get("keywords", []),
                    "sub_queries": raw.get("sub_queries", []),
                    "rewritten_query": raw.get("rewritten_query", query),
                    "from_llm": True,
                }
                self._cache_set(cache_key, result)
                return result
        except Exception as e:
            logger.warning("LLM Query Rewrite 失败，降级到规则匹配: %s", e)

        return self._fallback_rewrite(query, cache_key)

    def _fallback_rewrite(self, query: str, cache_key: str) -> Dict:
        result = super().rewrite(query)
        result["from_llm"] = False
        self._cache_set(cache_key, result)
        return result


def get_query_rewriter(mock: bool = True, provider: str = "mock", keys=None) -> QueryRewriter:
    if mock:
        return MockQueryRewriter()
    return LLMQueryRewriter(provider=provider, keys=keys)
