"""
Business Understanding Agent - 业务理解Agent

职责：深度理解PRD内容，提取业务实体、目标、流程和约束。

输出：结构化的业务理解结果，作为后续Agent的输入上下文。

使用豆包模型（生成类Agent）。
"""
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class BusinessUnderstandingAgent(BaseAgent):
    """Business Understanding Agent - 深度理解PRD内容"""

    @property
    def name(self) -> str:
        return "Business Understanding Agent"

    @property
    def system_prompt(self) -> str:
        return """你是Business Understanding Agent。职责：深度理解PRD内容，提取业务实体、目标、流程和约束。

输入：
- PRD文档内容
- （可选）BSC Planner的规划结果（previous_output字段）

请基于输入内容分析并输出：
1. business_domain - 业务领域（如：内容审核、电商、金融等）
2. core_objectives - 核心目标列表，每项含 objective/target/priority
3. key_entities - 关键实体，每项含 entity/type/count（可选）
4. process_flow - 流程步骤列表（按顺序）
5. success_metrics - 成功指标列表
6. constraints - 约束条件列表
7. industry_context - 行业背景

必须输出JSON：
{
  "business_domain": "",
  "core_objectives": [{"objective": "", "target": "", "priority": "high|medium|low"}],
  "key_entities": [{"entity": "", "type": "", "count": 0}],
  "process_flow": ["步骤1", "步骤2", "..."],
  "success_metrics": ["指标1", "指标2", "..."],
  "constraints": ["约束1", "约束2", "..."],
  "industry_context": ""
}"""

    @property
    def output_schema(self) -> dict:
        return {
            "required": ["business_domain", "core_objectives", "key_entities",
                         "process_flow", "success_metrics", "constraints", "industry_context"],
        }
