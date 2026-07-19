"""
Planner - 根据PRD内容决定执行哪些Agent

输入：知识切片
输出：Agent执行计划
"""
from __future__ import annotations


class Planner:
    """Planner - Agent执行链规划器"""

    ALL_AGENTS = ["sop", "risk", "strategy", "root_cause", "optimization"]

    DEPENDENCIES = {
        "sop": [],
        "risk": ["sop"],
        "strategy": ["sop"],
        "root_cause": ["sop", "risk"],
        "optimization": ["sop", "risk", "strategy"],
    }

    AGENT_TRIGGERS = {
        "sop": ["流程", "SOP", "审核", "客服", "风控", "电商", "运营", "订单",
                "审批", "工单", "流程设计", "工作流", "步骤", "环节", "操作"],
        "risk": ["风险", "合规", "安全", "隐患", "危险", "合规",
                 "威胁", "漏洞", "风险评估", "风险分析", "安全保障", "数据安全", "隐私"],
        "strategy": ["战略", "增长", "扩展", "市场", "竞争", "扩张",
                     "规划", "蓝图", "愿景", "目标", "方向", "机会", "定位"],
        "root_cause": ["为什么", "原因", "根因", "诊断", "分析",
                       "问题", "故障", "失败", "错误", "瓶颈", "痛点"],
        "optimization": ["优化", "提升", "改进", "效率", "降低成本", "ROI",
                         "增效", "改善", "精简", "自动化", "智能化", "数字化"],
    }

    def plan(self, chunks: list[dict]) -> dict:
        """
        根据PRD内容决定执行哪些Agent
        
        Returns:
            {
                "agents": ["sop", "risk", "strategy", ...],
                "execution_order": [...],
                "reasoning": "..."
            }
        """
        combined = " ".join([c["content"] for c in chunks])

        required = []
        for agent, triggers in self.AGENT_TRIGGERS.items():
            score = sum(1 for kw in triggers if kw in combined)
            if score > 0:
                required.append(agent)

        required = list(set(required + ["sop", "risk", "strategy"]))
        required = self._resolve_dependencies(required)
        execution_order = self._topological_sort(required)

        return {
            "agents": required,
            "execution_order": execution_order,
            "reasoning": f"PRD包含关键词触发: {', '.join(required)}",
        }

    def _resolve_dependencies(self, required: list) -> list:
        """自动补全依赖的Agent"""
        resolved = set(required)
        for agent in required:
            deps = self.DEPENDENCIES.get(agent, [])
            resolved.update(deps)
        return list(resolved)

    def _topological_sort(self, agents: list) -> list:
        """拓扑排序（按依赖关系）"""
        order = []
        visited = set()

        def visit(agent):
            if agent in visited:
                return
            visited.add(agent)
            for dep in self.DEPENDENCIES.get(agent, []):
                if dep in agents:
                    visit(dep)
            order.append(agent)

        for agent in agents:
            visit(agent)

        return order


def get_planner() -> Planner:
    """获取Planner实例（无状态，每次返回新实例）"""
    return Planner()


__all__ = ["Planner", "get_planner"]
