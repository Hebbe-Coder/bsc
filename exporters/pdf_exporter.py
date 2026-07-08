"""PDF Exporter - 生成PDF文档报告"""
from typing import Dict, Any
import io
import logging

logger = logging.getLogger(__name__)


class PDFExporter:
    """PDF文档导出器"""

    def __init__(self):
        self._pdfkit_available = False
        self._weasyprint_available = False
        try:
            import pdfkit
            self._pdfkit_available = True
        except ImportError:
            pass

        try:
            import weasyprint
            self._weasyprint_available = True
        except ImportError:
            pass

    def export(self, business_system: Dict[str, Any]) -> bytes:
        """导出为PDF文档"""
        html_content = self._generate_html_content(business_system)

        if self._weasyprint_available:
            return self._export_with_weasyprint(html_content)
        elif self._pdfkit_available:
            return self._export_with_pdfkit(html_content)
        else:
            raise RuntimeError("需要安装weasyprint或pdfkit来生成PDF")

    def _generate_html_content(self, business_system: Dict[str, Any]) -> str:
        """生成PDF所需的HTML内容"""
        title = business_system.get("business_domain", "业务系统分析报告")
        subtitle = business_system.get("report", {}).get("executive_summary", "")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @page {{ margin: 2cm; }}
        body {{ font-family: 'Microsoft YaHei', 'SimHei', sans-serif; font-size: 11pt; line-height: 1.6; }}
        h1 {{ text-align: center; font-size: 18pt; margin-bottom: 10px; }}
        h2 {{ font-size: 14pt; margin-top: 20px; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        h3 {{ font-size: 12pt; margin-top: 15px; color: #34495e; }}
        .subtitle {{ text-align: center; color: #7f8c8d; font-style: italic; margin-bottom: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #bdc3c7; padding: 8px; text-align: left; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
        ul, ol {{ margin: 10px 0; padding-left: 25px; }}
        li {{ margin-bottom: 5px; }}
        .priority-high {{ color: #c0392b; font-weight: bold; }}
        .priority-medium {{ color: #f39c12; }}
        .priority-low {{ color: #27ae60; }}
        .risk-high {{ color: #c0392b; }}
        .risk-medium {{ color: #f39c12; }}
        .risk-low {{ color: #27ae60; }}
        .footer {{ text-align: center; font-size: 9pt; color: #95a5a6; margin-top: 30px; }}
    </style>
</head>
<body>
"""

        html += f"<h1>{title}</h1>"
        if subtitle:
            html += f"<p class='subtitle'>{subtitle}</p>"

        html += "<h2>一、业务目标</h2>"
        objectives = business_system.get("objectives", [])
        if objectives:
            html += "<ul>"
            for obj in objectives:
                priority = obj.get("priority", "medium")
                priority_class = f"priority-{priority}"
                priority_label = {"high": "【高】", "medium": "【中】", "low": "【低】"}.get(priority, "")
                html += f"<li><span class='{priority_class}'>{priority_label}{obj.get('objective', '')}</span>"
                if obj.get("target"):
                    html += f" - 目标: {obj.get('target')}"
                html += "</li>"
            html += "</ul>"
        else:
            html += "<p>暂无业务目标</p>"

        html += "<h2>二、角色定义</h2>"
        roles = business_system.get("roles", [])
        if roles:
            html += """
<table>
    <thead>
        <tr><th>角色名称</th><th>所属部门</th><th>级别</th><th>人数</th></tr>
    </thead>
    <tbody>"""
            for role in roles:
                html += f"""
        <tr>
            <td>{role.get('role', '')}</td>
            <td>{role.get('department', '')}</td>
            <td>{role.get('level', '')}</td>
            <td>{role.get('headcount', '')}</td>
        </tr>"""
            html += """
    </tbody>
</table>"""
        else:
            html += "<p>暂无角色定义</p>"

        html += "<h2>三、业务流程</h2>"
        workflow = business_system.get("workflow", [])
        if workflow:
            html += "<ol>"
            for step in workflow:
                html += f"<li><strong>{step.get('name', '')}</strong>"
                if step.get('action'):
                    html += f"<br/>动作: {step.get('action')}"
                if step.get('role'):
                    html += f"<br/>负责角色: {step.get('role')}"
                html += "</li>"
            html += "</ol>"
        else:
            html += "<p>暂无业务流程</p>"

        html += "<h2>四、风险分析</h2>"
        risks = business_system.get("risks", [])
        if risks:
            for risk in risks:
                level = risk.get("level", "medium")
                level_class = f"risk-{level}"
                level_label = {"high": "高风险", "medium": "中风险", "low": "低风险"}.get(level, "未知")
                html += f"<h3><span class='{level_class}'>{level_label}: {risk.get('risk', '')}</span></h3>"
                if risk.get("mitigation"):
                    html += f"<p><strong>应对措施:</strong> {risk.get('mitigation')}</p>"
        else:
            html += "<p>暂无风险分析</p>"

        html += "<h2>五、战略建议</h2>"
        strategy = business_system.get("strategy", {})
        recommendations = strategy.get("recommendations", [])
        if recommendations:
            html += "<ul>"
            for i, rec in enumerate(recommendations, 1):
                html += f"<li>{i}. {rec}</li>"
            html += "</ul>"
        else:
            html += "<p>暂无战略建议</p>"

        html += """
<div class='footer'>
    业务系统分析报告
</div>
</body>
</html>"""

        return html

    def _export_with_weasyprint(self, html_content: str) -> bytes:
        """使用WeasyPrint生成PDF"""
        import weasyprint
        html = weasyprint.HTML(string=html_content)
        pdf_bytes = html.write_pdf()
        return pdf_bytes

    def _export_with_pdfkit(self, html_content: str) -> bytes:
        """使用pdfkit生成PDF"""
        import pdfkit
        options = {
            'encoding': 'UTF-8',
            'page-size': 'A4',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
        }
        pdf_bytes = pdfkit.from_string(html_content, False, options=options)
        return pdf_bytes
