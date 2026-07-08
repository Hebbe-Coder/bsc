"""
Report Composer - 报告生成Agent

职责：整合所有Agent的结果，生成最终的业务分析报告。

使用豆包模型（生成类Agent），适合创意写作和报告生成。
"""
from __future__ import annotations
import json
from app.agents.base_agent import BaseAgent


class ReportComposer(BaseAgent):
    """Report Composer - 整合所有Agent结果生成报告"""

    @property
    def name(self) -> str:
        return "Report Composer"

    @property
    def system_prompt(self) -> str:
        return """你是Report Composer。职责：整合所有Agent的分析结果，生成专业的业务分析报告。

输入包含（通过context传递）：
- business_understanding: 业务理解（业务领域、核心目标、关键实体、流程步骤）
- sop: SOP流程设计（workflow、roles、responsibilities、sla、kpi）
- risk: 风险分析（process_risks、organization_risks、system_risks、compliance_risks）
- optimization: 优化建议（recommendations、roi_estimation）

请生成：
1. title - 报告标题
2. executive_summary - 执行摘要（100-200字）
3. sections - 章节列表，每项含 section/content
4. key_findings - 关键发现列表

必须输出JSON：
{
  "title": "",
  "executive_summary": "",
  "sections": [{"section": "", "content": ""}],
  "key_findings": ["发现1", "发现2", "..."]
}"""

    @property
    def output_schema(self) -> dict:
        return {
            "required": ["title", "executive_summary", "sections", "key_findings"],
        }

    def _build_user_prompt(self, chunks: list[dict], context: dict = None) -> str:
        """组装LLM输入 - 包含所有Agent的结果"""
        parts = []

        parts.append("## PRD文档内容")
        for c in chunks:
            parts.append(f"\n### 段落 {c['chunk_id']}\n{c['content']}")

        if context:
            full_history = context.get("full_history", context)

            parts.append("\n## 业务理解")
            parts.append(json.dumps(full_history.get("business_understanding", {}), ensure_ascii=False, indent=2))

            parts.append("\n## SOP流程")
            parts.append(json.dumps(full_history.get("sop", {}), ensure_ascii=False, indent=2))

            parts.append("\n## 风险分析")
            parts.append(json.dumps(full_history.get("risk", {}), ensure_ascii=False, indent=2))

            parts.append("\n## 优化建议")
            parts.append(json.dumps(full_history.get("optimization", {}), ensure_ascii=False, indent=2))

        parts.append("\n请根据以上内容生成业务分析报告。")

        return "\n".join(parts)
