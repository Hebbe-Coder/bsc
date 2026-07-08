# exporters/ppt_spec_exporter.py
"""PPT 规格生成器（含组件级降级）。从 bsc_api._generate_ppt_spec 迁入。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from exporters._degrade_ctx import DegradeContext


def generate_ppt_spec(business_system: dict, ctx: Optional[DegradeContext] = None) -> dict:
    """生成 PPT 规格（JSON）。ctx 非空时单个区块失败被跳过。"""
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
            "title": business_system.get("business_domain", "业务系统分析"),
            "subtitle": "基于PRD的业务系统分析报告",
        })

    _block("title", _title)

    def _objectives():
        if business_system.get("objectives"):
            slides.append({
                "slide_type": "list",
                "title": "业务目标",
                "items": [f"{obj.get('objective', '')}: {obj.get('target', '')}" for obj in business_system["objectives"]],
            })

    _block("objectives", _objectives)

    def _workflow():
        if business_system.get("workflow"):
            slides.append({
                "slide_type": "flow",
                "title": "流程设计",
                "steps": [step.get("name", "") for step in business_system["workflow"]],
            })

    _block("workflow", _workflow)

    def _metrics():
        if business_system.get("metrics"):
            slides.append({
                "slide_type": "table",
                "title": "关键指标",
                "headers": ["指标", "公式", "目标"],
                "data": [[kpi.get("name", ""), kpi.get("formula", ""), kpi.get("target", "")] for kpi in business_system["metrics"]],
            })

    _block("metrics", _metrics)

    def _risks():
        if business_system.get("risks"):
            slides.append({
                "slide_type": "list",
                "title": "风险分析",
                "items": [f"{risk.get('risk', '')} ({risk.get('severity', '')})" for risk in business_system["risks"][:5]],
            })

    _block("risks", _risks)

    def _strategy():
        if business_system.get("strategy"):
            ops = business_system["strategy"].get("growth_opportunities", [])
            slides.append({
                "slide_type": "list",
                "title": "战略机会",
                "items": [f"{op.get('opportunity', '')}: {op.get('potential', '')}" for op in ops],
            })

    _block("strategy", _strategy)

    def _report():
        if business_system.get("report"):
            slides.append({
                "slide_type": "content",
                "title": "执行摘要",
                "content": business_system["report"].get("executive_summary", ""),
            })

    _block("report", _report)

    return {"slides": slides, "theme": "dark", "slide_count": len(slides)}
