"""导出编排器：统一 try/except + 候补替换 + 逐格式状态表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from exporters.degrade import DEGRADATION_RULES, classify_failure, is_implemented
from exporters._degrade_ctx import DegradeContext
from exporters.canonical import normalize


@dataclass
class ExportOutcome:
    exports: Dict[str, Any] = field(default_factory=dict)
    formats_status: List[dict] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)


def _produce(fmt: str, bs: dict, canonical, result: dict, ctx: DegradeContext):
    """产出单个格式。成功返回产出物；失败抛异常。
    json/visuals 仍用原始 bs；四文档格式消费规范化后的 canonical。"""
    if fmt == "json":
        return bs
    if fmt == "html":
        from exporters.html_exporter import generate_html
        return generate_html(canonical, result.get("pipeline", {}), ctx)
    if fmt == "ppt":
        from exporters.ppt_spec_exporter import generate_ppt_spec
        return generate_ppt_spec(canonical, ctx)
    if fmt == "word":
        from exporters.word_exporter import WordExporter
        return {
            "content_base64": WordExporter().export(canonical).hex(),
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    if fmt == "markdown":
        from exporters.markdown_exporter import MarkdownExporter
        return MarkdownExporter().export(canonical, ctx)
    if fmt == "pdf":
        from exporters.pdf_exporter import PDFExporter
        return {"content_base64": PDFExporter().export(canonical).hex(), "mime_type": "application/pdf"}
    if fmt == "visuals":
        from app.engines.visual_binding import bind_visuals
        try:
            return bind_visuals(bs)
        except Exception:  # noqa: BLE001
            return []
    raise RuntimeError(f"未知导出格式: {fmt}")


def run_export(bs: dict, output_types: List[str], result: dict) -> ExportOutcome:
    outcome = ExportOutcome()
    canonical = normalize(bs)
    for fmt in output_types:
        # 1. 未实现且无候补链 → dropped/unimplemented
        #    （pptx 等非直接产出但有候补链的格式，仍进入候补尝试流程）
        if not is_implemented(fmt) and not DEGRADATION_RULES.get(fmt):
            outcome.formats_status.append({
                "format": fmt,
                "status": "dropped",
                "reason": "unimplemented",
                "message": f"格式 {fmt} 当前版本未实现，可用 /bsc/exports/capabilities 查看可用格式",
            })
            continue

        # 2. 尝试产出 + 候补替换
        candidates = [fmt] + DEGRADATION_RULES.get(fmt, [])
        produced_as = None
        value = None
        last_exc = None
        component_failures: List[dict] = []
        for cand in candidates:
            ctx = DegradeContext()
            try:
                value = _produce(cand, bs, canonical, result, ctx)
                produced_as = cand
                component_failures = ctx.component_failures
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e

        if produced_as is not None:
            outcome.exports[produced_as] = value
            if produced_as == fmt:
                entry = {"format": fmt, "status": "produced"}
            else:
                entry = {"format": fmt, "status": "substituted", "source_format": produced_as}
            if component_failures:
                entry["components_degraded"] = component_failures
            outcome.formats_status.append(entry)
        else:
            reason = classify_failure(fmt, last_exc or RuntimeError(f"{fmt} 导出失败"))
            entry = {"format": fmt, "status": "dropped", "reason": reason["type"]}
            for k, v in reason.items():
                if k not in ("type", "format"):
                    entry[k] = v
            outcome.formats_status.append(entry)

    return outcome
