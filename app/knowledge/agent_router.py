"""Agent Router：基于意图分类，将查询路由到不同知识域或工具。

生产级 RAG 的核心组件：
- 根据 QueryRewriter 的意图分类结果选择知识源
- 支持路由到：知识库、数据库、API、工具
- 智能判断查询是否需要多步骤处理
- 支持 Agentic RAG：Planner → Tool Call → Summary
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.knowledge.query_rewrite import QueryRewriter, get_query_rewriter
from app.knowledge.knowledge_domains import get_domain_registry, DEFAULT_DOMAINS

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "database": {"name": "数据库查询", "description": "查询业务数据库获取实时数据"},
    "api": {"name": "外部API调用", "description": "调用外部服务获取信息"},
    "calculator": {"name": "计算器", "description": "执行数学计算"},
    "search": {"name": "知识库检索", "description": "从知识库中检索相关文档"},
}

# 从统一域配置中心获取知识域定义
KNOWLEDGE_DOMAINS = DEFAULT_DOMAINS


class ToolCall:
    def __init__(self, tool_name: str, params: Dict):
        self.tool_name = tool_name
        self.params = params
        self.result = None
        self.status = "pending"

    def execute(self):
        self.status = "executed"
        self.result = {"mock": f"Tool {self.tool_name} executed with params {self.params}"}
        return self.result


class AgentRouter:
    def __init__(self, rewriter: Optional[QueryRewriter] = None):
        self.rewriter = rewriter or get_query_rewriter(mock=True)
        self._history = []

    def route(self, query: str) -> Dict:
        rewrite_result = self.rewriter.rewrite(query)
        intent = rewrite_result["intent"]
        domain = KNOWLEDGE_DOMAINS.get(intent, KNOWLEDGE_DOMAINS["general"])

        tools = self._select_tools(intent, query)
        metadata_filters = domain.get("metadata_filters", {})

        plan = self._build_plan(query, rewrite_result, tools)

        result = {
            "query": query,
            "rewrite": rewrite_result,
            "intent": intent,
            "domain": domain,
            "tools": tools,
            "metadata_filters": metadata_filters,
            "plan": plan,
            "router_decision": self._explain_decision(intent, tools),
        }

        logger.info("Agent Router: query='%s' → intent='%s' → tools=%s", query, intent, [t.tool_name for t in tools])
        return result

    def _select_tools(self, intent: str, query: str) -> List[ToolCall]:
        domain = KNOWLEDGE_DOMAINS.get(intent, KNOWLEDGE_DOMAINS["general"])
        available_tools = domain.get("tools", ["search"])

        tools = []
        if "search" in available_tools:
            tools.append(ToolCall("search", {"query": query}))

        if "database" in available_tools and ("查询" in query or "统计" in query or "数据" in query):
            tools.append(ToolCall("database", {"query": query}))

        if "api" in available_tools and ("调用" in query or "接口" in query):
            tools.append(ToolCall("api", {"endpoint": "auto_detect", "params": {"query": query}}))

        if "calculator" in available_tools and self._contains_math(query):
            tools.append(ToolCall("calculator", {"expression": query}))

        return tools if tools else [ToolCall("search", {"query": query})]

    def _contains_math(self, query: str) -> bool:
        math_patterns = ["加", "减", "乘", "除", "等于", "计算", "总和", "平均", "百分比"]
        for pattern in math_patterns:
            if pattern in query:
                return True
        return False

    def _build_plan(self, query: str, rewrite_result: Dict, tools: List[ToolCall]) -> List[Dict]:
        plan = []

        if rewrite_result.get("sub_queries"):
            plan.append({
                "step": 1,
                "action": "分解问题",
                "description": f"将复杂问题拆分为子问题: {rewrite_result['sub_queries']}",
            })

        for i, tool in enumerate(tools, start=len(plan) + 1):
            plan.append({
                "step": i,
                "action": f"调用 {tool.tool_name}",
                "description": f"使用 {tool.tool_name} 工具处理查询",
                "params": tool.params,
            })

        plan.append({
            "step": len(plan) + 1,
            "action": "综合回答",
            "description": "整合所有工具返回结果，生成最终回答",
        })

        return plan

    def _explain_decision(self, intent: str, tools: List[ToolCall]) -> str:
        domain = KNOWLEDGE_DOMAINS.get(intent, KNOWLEDGE_DOMAINS["general"])
        tool_names = [t.tool_name for t in tools]

        if len(tool_names) == 1 and tool_names[0] == "search":
            return f"查询属于「{domain['name']}」知识域，使用知识库检索"
        elif len(tool_names) > 1:
            return f"查询属于「{domain['name']}」知识域，需要多工具协作: {', '.join(tool_names)}"
        else:
            return f"查询属于「{domain['name']}」知识域，使用 {tool_names[0]} 工具处理"

    def execute_plan(self, plan: List[Dict], context: Optional[Dict] = None) -> List[Dict]:
        results = []
        for step in plan:
            action = step["action"]
            if action.startswith("调用"):
                tool_name = action.split(" ")[1]
                params = step.get("params", {})
                tool = ToolCall(tool_name, params)
                result = tool.execute()
                results.append({"step": step["step"], "action": action, "result": result})
            else:
                results.append({"step": step["step"], "action": action, "result": "OK"})
        return results


class MockAgentRouter(AgentRouter):
    def route(self, query: str) -> Dict:
        result = super().route(query)
        result["is_mock"] = True
        return result


def get_agent_router(mock: bool = True, rewriter: Optional[QueryRewriter] = None) -> AgentRouter:
    if mock:
        return MockAgentRouter(rewriter=rewriter)
    return AgentRouter(rewriter=rewriter)
