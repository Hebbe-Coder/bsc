"""Word Exporter - 生成Word文档报告"""
from typing import Dict, Any
import io
import logging

logger = logging.getLogger(__name__)


class WordExporter:
    """Word文档导出器"""

    def __init__(self):
        self._docx_available = False
        try:
            import docx
            self._docx_available = True
        except ImportError:
            logger.warning("python-docx not installed, Word export will be disabled")

    def export(self, business_system: Dict[str, Any]) -> bytes:
        """导出为Word文档"""
        if not self._docx_available:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")

        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.section import WD_SECTION
        from docx.oxml.ns import qn

        doc = Document()

        style = doc.styles['Normal']
        style.font.name = '微软雅黑'
        style.font.size = Pt(11)
        style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

        section = doc.sections[0]
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)

        title = business_system.get("business_domain", "业务系统分析报告")
        title_para = doc.add_heading(title, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        subtitle = business_system.get("report", {}).get("executive_summary", "")
        if subtitle:
            doc.add_paragraph(subtitle, style='Intense Quote')

        doc.add_heading('一、业务目标', level=1)
        objectives = business_system.get("objectives", [])
        if objectives:
            for obj in objectives:
                priority = obj.get("priority", "medium")
                priority_label = {"high": "【高】", "medium": "【中】", "low": "【低】"}.get(priority, "")
                p = doc.add_paragraph(f"{priority_label}{obj.get('objective', '')}")
                if obj.get("target"):
                    p.add_run(f" - 目标: {obj.get('target')}")
        else:
            doc.add_paragraph("暂无业务目标")

        doc.add_heading('二、角色定义', level=1)
        roles = business_system.get("roles", [])
        if roles:
            table = doc.add_table(rows=1, cols=4)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = '角色名称'
            hdr_cells[1].text = '所属部门'
            hdr_cells[2].text = '级别'
            hdr_cells[3].text = '人数'
            for role in roles:
                row_cells = table.add_row().cells
                row_cells[0].text = role.get('role', '')
                row_cells[1].text = role.get('department', '')
                row_cells[2].text = role.get('level', '')
                row_cells[3].text = str(role.get('headcount', ''))
        else:
            doc.add_paragraph("暂无角色定义")

        doc.add_heading('三、业务流程', level=1)
        workflow = business_system.get("workflow", [])
        if workflow:
            for step in workflow:
                step_num = step.get('step', '')
                name = step.get('name', '')
                action = step.get('action', '')
                role = step.get('role', '')
                p = doc.add_paragraph(f"{step_num}. {name}", style='List Number')
                if action:
                    p.add_run(f"\n   动作: {action}")
                if role:
                    p.add_run(f"\n   负责角色: {role}")
        else:
            doc.add_paragraph("暂无业务流程")

        doc.add_heading('四、风险分析', level=1)
        risks = business_system.get("risks", [])
        if risks:
            for risk in risks:
                level = risk.get("level", "medium")
                level_label = {"high": "【高风险】", "medium": "【中风险】", "low": "【低风险】"}.get(level, "")
                p = doc.add_paragraph(f"{level_label}{risk.get('risk', '')}")
                if risk.get("mitigation"):
                    p.add_run(f"\n   应对措施: {risk.get('mitigation')}")
        else:
            doc.add_paragraph("暂无风险分析")

        doc.add_heading('五、战略建议', level=1)
        strategy = business_system.get("strategy", {})
        recommendations = strategy.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                doc.add_paragraph(rec, style='List Bullet')
        else:
            doc.add_paragraph("暂无战略建议")

        output = io.BytesIO()
        doc.save(output)
        output.seek(0)

        return output.read()
