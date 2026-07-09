# exporters/ppt_spec_exporter.py
"""PPT 规格生成器（含组件级降级）。从 bsc_api._generate_ppt_spec 迁入。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from exporters._degrade_ctx import DegradeContext


def generate_ppt_spec(report, ctx: Optional[DegradeContext] = None) -> dict:
    """生成 PPT 规格（JSON）。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
    from exporters.canonical import CanonicalReport, normalize
    if not isinstance(report, CanonicalReport):
        report = normalize(report)
    slides: list[dict] = []

    def _block(name: str, build):
        if ctx is None:
            build()
        else:
            with ctx.component(name):
                build()

    def _title():
        slides.append({
            "slide_type": "title",
            "title": report.title,
            "subtitle": "基于PRD的业务系统分析报告",
        })

    _block("title", _title)

    def _objectives():
        slides.append({
            "slide_type": "list",
            "title": "业务目标",
            "items": [f"{o.priority_label} {o.objective}: {o.target}" for o in report.objectives],
        })

    _block("objectives", _objectives)

    def _roles():
        slides.append({
            "slide_type": "table",
            "title": "角色定义",
            "headers": ["角色", "部门", "级别", "人数"],
            "data": [[r.role, r.department, r.level, r.headcount] for r in report.roles],
        })

    _block("roles", _roles)

    def _workflow():
        slides.append({
            "slide_type": "flow",
            "title": "业务流程",
            "steps": [s.name for s in report.workflow],
        })

    _block("workflow", _workflow)

    def _metrics():
        slides.append({
            "slide_type": "table",
            "title": "关键指标",
            "headers": ["指标", "公式", "目标"],
            "data": [[m.name, m.formula, m.target] for m in report.metrics],
        })

    _block("metrics", _metrics)

    def _risks():
        slides.append({
            "slide_type": "list",
            "title": "风险分析",
            "items": [f"{rk.severity_label}: {rk.risk}" for rk in report.risks[:5]],
        })

    _block("risks", _risks)

    def _strategy():
        items = list(report.strategy.recommendations)
        items += [f"{g['opportunity']}: {g['potential']}" for g in report.strategy.growth_opportunities]
        items += list(report.strategy.roadmap)
        slides.append({
            "slide_type": "list",
            "title": "战略建议",
            "items": items,
        })

    _block("strategy", _strategy)

    def _report():
        if report.executive_summary:
            slides.append({
                "slide_type": "content",
                "title": "执行摘要",
                "content": report.executive_summary,
            })

    _block("report", _report)

    return {"slides": slides, "theme": "dark", "slide_count": len(slides)}
