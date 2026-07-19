"""PDF Exporter - 生成PDF文档报告"""
from typing import Any
import logging

logger = logging.getLogger(__name__)


class PDFExporter:
    """PDF文档导出器"""

    def __init__(self):
        self._pdfkit_available = False
        self._weasyprint_available = False
        self._reportlab_available = False
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

        try:
            import reportlab  # noqa: F401
            self._reportlab_available = True
        except ImportError:
            pass

    def export(self, report: Any) -> bytes:
        """导出为PDF文档。report 为 CanonicalReport。"""
        from exporters.canonical import CanonicalReport, normalize
        if not isinstance(report, CanonicalReport):
            report = normalize(report)
        html_content = self._generate_html_content(report)

        if self._weasyprint_available:
            return self._export_with_weasyprint(html_content)
        elif self._pdfkit_available:
            return self._export_with_pdfkit(html_content)
        elif self._reportlab_available:
            return self._export_with_reportlab(report)
        else:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("pdf", "weasyprint", "pip install weasyprint")

    def _export_with_reportlab(self, report) -> bytes:
        """使用 reportlab 生成 PDF（纯 Python，跨平台，无需系统 GTK）。"""
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from exporters.canonical import CanonicalReport, normalize
        if not isinstance(report, CanonicalReport):
            report = normalize(report)

        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font = "STSong-Light"
        except Exception:
            font = "Helvetica"

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Title"], fontName=font, fontSize=18, spaceAfter=10)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=font, fontSize=13,
                            textColor=colors.HexColor("#2c3e50"), spaceBefore=14, spaceAfter=6)
        body = ParagraphStyle("body", parent=styles["BodyText"], fontName=font, fontSize=10, leading=15)
        small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#95a5a6"))

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=48, bottomMargin=48,
                                leftMargin=56, rightMargin=56, title="业务系统分析报告")
        story = []

        story.append(Paragraph(report.title, h1))
        if report.executive_summary:
            story.append(Paragraph(report.executive_summary, ParagraphStyle("sub", parent=body,
                                                             alignment=1, textColor=colors.HexColor("#7f8c8d"))))

        def section(t, items):
            story.append(Paragraph(t, h2))
            if not items:
                story.append(Paragraph("暂无", body))
                return
            flow = [ListItem(Paragraph(str(i), body), leftIndent=12) for i in items]
            story.append(ListFlowable(flow, bulletType="bullet"))

        objectives = [f"{o.priority_label} {o.objective}"
                      + (f" - 目标: {o.target}" if o.target else "")
                      for o in report.objectives]
        section("一、业务目标", objectives)

        if report.roles:
            story.append(Paragraph("二、角色定义", h2))
            data = [["角色名称", "部门", "级别", "人数"]] + [
                [r.role, r.department, r.level, str(r.headcount)]
                for r in report.roles
            ]
            tbl = Table(data, colWidths=[120, 120, 80, 80])
            tbl.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdc3c7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(tbl)

        workflow = [f"<b>{s.name}</b>"
                    + (f"<br/>动作: {s.action}" if s.action else "")
                    + (f"<br/>负责角色: {s.role}" if s.role else "")
                    for s in report.workflow]
        section("三、业务流程", workflow)

        if report.risks:
            story.append(Paragraph("四、风险分析", h2))
            for rk in report.risks:
                txt = f"<b>{rk.severity_label}: {rk.risk}</b>"
                if rk.mitigation:
                    txt += f"<br/>应对措施: {rk.mitigation}"
                story.append(Paragraph(txt, body))
                story.append(Spacer(1, 4))

        section("五、战略建议", [str(r) for r in report.strategy.recommendations])

        story.append(Spacer(1, 24))
        story.append(Paragraph("业务系统分析报告", small))
        doc.build(story)
        return buf.getvalue()

    def _generate_html_content(self, report) -> str:
        """生成PDF所需的HTML内容（委托统一 generate_html）。"""
        from exporters.html_exporter import generate_html
        from exporters.canonical import CanonicalReport, normalize
        if not isinstance(report, CanonicalReport):
            report = normalize(report)
        return generate_html(report, {}, None)

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
