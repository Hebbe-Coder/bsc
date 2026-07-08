"""Markdown Exporter - 生成Markdown格式报告"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class MarkdownExporter:
    """Markdown文档导出器"""

    def export(self, business_system: Dict[str, Any]) -> str:
        """导出为Markdown格式"""
        lines = []

        title = business_system.get("business_domain", "业务系统分析报告")
        lines.append(f"# {title}")
        lines.append("")

        subtitle = business_system.get("report", {}).get("executive_summary", "")
        if subtitle:
            lines.append(f"> {subtitle}")
            lines.append("")

        lines.append("---")
        lines.append("")

        lines.append("## 一、业务目标")
        objectives = business_system.get("objectives", [])
        if objectives:
            for obj in objectives:
                priority = obj.get("priority", "medium")
                priority_label = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                line = f"{priority_label} **{obj.get('objective', '')}**"
                if obj.get("target"):
                    line += f" - 目标: {obj.get('target')}"
                lines.append(line)
        else:
            lines.append("暂无业务目标")
        lines.append("")

        lines.append("## 二、角色定义")
        roles = business_system.get("roles", [])
        if roles:
            lines.append("| 角色名称 | 所属部门 | 级别 | 人数 |")
            lines.append("|----------|----------|------|------|")
            for role in roles:
                lines.append(f"| {role.get('role', '')} | {role.get('department', '')} | {role.get('level', '')} | {role.get('headcount', '')} |")
        else:
            lines.append("暂无角色定义")
        lines.append("")

        lines.append("## 三、业务流程")
        workflow = business_system.get("workflow", [])
        if workflow:
            for step in workflow:
                step_num = step.get('step', '')
                name = step.get('name', '')
                action = step.get('action', '')
                role = step.get('role', '')
                lines.append(f"{step_num}. **{name}**")
                if action:
                    lines.append(f"   - 动作: {action}")
                if role:
                    lines.append(f"   - 负责角色: {role}")
                lines.append("")
        else:
            lines.append("暂无业务流程")
        lines.append("")

        lines.append("## 四、风险分析")
        risks = business_system.get("risks", [])
        if risks:
            for risk in risks:
                level = risk.get("level", "medium")
                level_label = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}.get(level, "⚪ 未知")
                lines.append(f"### {level_label}: {risk.get('risk', '')}")
                if risk.get("mitigation"):
                    lines.append(f"- **应对措施**: {risk.get('mitigation')}")
                lines.append("")
        else:
            lines.append("暂无风险分析")
        lines.append("")

        lines.append("## 五、战略建议")
        strategy = business_system.get("strategy", {})
        recommendations = strategy.get("recommendations", [])
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")
        else:
            lines.append("暂无战略建议")
        lines.append("")

        lines.append("---")
        lines.append(f"> 报告生成时间: {business_system.get('generated_at', '')}")

        return "\n".join(lines)
