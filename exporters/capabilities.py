"""导出格式能力登记表。

在模块加载时用 importlib.util.find_spec 探测各格式所需依赖是否可用，
避免真正 import 带来的副作用（如 matplotlib 后端初始化）。
"""
from __future__ import annotations
import importlib.util


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _probe(fmt: str, any_of: list[str], pip_install: str) -> dict:
    """any_of 里任意一个可用即视为该格式可用（如 pdf 的多后端）。"""
    available = any(_has(m) for m in any_of)
    missing = None if available else any_of[0]
    return {
        "available": available,
        "deps": any_of,
        "missing": missing,
        "pip_install": None if available else pip_install,
        "format": fmt,
    }


EXPORT_CAPABILITIES: dict[str, dict] = {
    "json": {"available": True, "deps": [], "missing": None, "pip_install": None, "format": "json"},
    "html": {"available": True, "deps": [], "missing": None, "pip_install": None, "format": "html"},
    "ppt": {"available": True, "deps": [], "missing": None, "pip_install": None, "format": "ppt"},
    "markdown": {"available": True, "deps": [], "missing": None, "pip_install": None, "format": "markdown"},
    "word": _probe("word", ["docx"], "pip install python-docx"),
    "pdf": _probe("pdf", ["weasyprint", "pdfkit", "reportlab"], "pip install weasyprint"),
    "xlsx": _probe("xlsx", ["openpyxl"], "pip install openpyxl"),
    "pptx": _probe("pptx", ["pptx"], "pip install python-pptx matplotlib"),
}


def format_available(fmt: str) -> bool:
    cap = EXPORT_CAPABILITIES.get(fmt)
    return bool(cap and cap["available"])


def unavailable_formats(requested: list[str]) -> list[dict]:
    """返回请求格式中当前不可用的那些（含缺失包 + pip 命令）。

    未知格式忽略（由端点自身的格式校验处理）。
    """
    out = []
    for fmt in requested:
        cap = EXPORT_CAPABILITIES.get(fmt)
        if cap and not cap["available"]:
            out.append({
                "format": fmt,
                "missing_package": cap["missing"],
                "pip_install": cap["pip_install"],
            })
    return out
