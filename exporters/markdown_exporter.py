"""Markdown Exporter - 生成Markdown格式报告"""
import logging

logger = logging.getLogger(__name__)


class MarkdownExporter:
    """Markdown文档导出器"""

    def export(self, report, ctx=None) -> str:
        """导出为 Markdown 格式。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
        from exporters.canonical import CanonicalReport, normalize
        if not isinstance(report, CanonicalReport):
            report = normalize(report)
        lines = []

        def _block(name, render):
            if ctx is None:
                render()
            else:
                with ctx.component(name):
                    render()

        lines.append(f"# {report.title}")
        lines.append("")

        if report.executive_summary:
            lines.append(f"> {report.executive_summary}")
            lines.append("")

        lines.append("---")
        lines.append("")

        def _objectives():
            lines.append("## 一、业务目标")
            if report.objectives:
                for o in report.objectives:
                    line = f"{o.priority_label} **{o.objective}**"
                    if o.target:
                        line += f" - 目标: {o.target}"
                    lines.append(line)
            else:
                lines.append("暂无业务目标")
            lines.append("")

        def _roles():
            lines.append("## 二、角色定义")
            if report.roles:
                lines.append("| 角色名称 | 所属部门 | 级别 | 人数 |")
                lines.append("|----------|----------|------|------|")
                for r in report.roles:
                    lines.append(f"| {r.role} | {r.department} | {r.level} | {r.headcount} |")
            else:
                lines.append("暂无角色定义")
            lines.append("")

        def _workflow():
            lines.append("## 三、业务流程")
            if report.workflow:
                for s in report.workflow:
                    lines.append(f"{s.step}. **{s.name}**")
                    if s.action:
                        lines.append(f"   - 动作: {s.action}")
                    if s.role:
                        lines.append(f"   - 负责角色: {s.role}")
                    lines.append("")
            else:
                lines.append("暂无业务流程")
            lines.append("")

        def _metrics():
            lines.append("## 四、关键指标")
            if report.metrics:
                for m in report.metrics:
                    line = f"- **{m.name}**"
                    if m.formula:
                        line += f"（公式: {m.formula}）"
                    if m.target:
                        line += f" 目标: {m.target}"
                    lines.append(line)
            else:
                lines.append("暂无关键指标")
            lines.append("")

        def _risks():
            lines.append("## 五、风险分析")
            if report.risks:
                for rk in report.risks:
                    lines.append(f"### {rk.severity_label}: {rk.risk}")
                    if rk.mitigation:
                        lines.append(f"- **应对措施**: {rk.mitigation}")
                    if rk.impact:
                        lines.append(f"- **影响**: {rk.impact}")
                    lines.append("")
            else:
                lines.append("暂无风险分析")
            lines.append("")

        def _strategy():
            lines.append("## 六、战略建议")
            if report.strategy.recommendations:
                for i, rec in enumerate(report.strategy.recommendations, 1):
                    lines.append(f"{i}. {rec}")
            if report.strategy.growth_opportunities:
                lines.append("**增长机会**")
                for g in report.strategy.growth_opportunities:
                    lines.append(f"- {g['opportunity']}: {g['potential']}")
            if report.strategy.roadmap:
                lines.append("**实施路线**")
                for step in report.strategy.roadmap:
                    lines.append(f"- {step}")
            if not (report.strategy.recommendations or report.strategy.growth_opportunities or report.strategy.roadmap):
                lines.append("暂无战略建议")
            lines.append("")

        _block("objectives", _objectives)
        _block("roles", _roles)
        _block("workflow", _workflow)
        _block("metrics", _metrics)
        _block("risks", _risks)
        _block("strategy", _strategy)

        lines.append("---")
        if report.generated_at:
            lines.append(f"> 报告生成时间: {report.generated_at}")

        return "\n".join(lines)
