"""导出层包入口。

惰性导入（PEP 562）：访问某导出器属性时才导入其子模块，
避免任一格式的第三方依赖缺失导致整个包无法导入。
"""
import importlib

_LAZY = {
    "PPTExporter": ("exporters.ppt_exporter", "PPTExporter"),
    "PPTExporterV7": ("exporters.ppt_exporter", "PPTExporter"),
    "export_impeccable": ("exporters.ppt_exporter", "export_impeccable"),
    "export_with_qa": ("exporters.ppt_exporter", "export_with_qa"),
    "qa_check": ("exporters.ppt_exporter", "qa_check"),
    "PPTExporterV2": ("exporters.ppt_exporter_v2", "PPTExporterV2"),
    "Theme": ("exporters.ppt_exporter_v2", "Theme"),
    "ChartGenerator": ("exporters.ppt_exporter_v2", "ChartGenerator"),
    "export_professional": ("exporters.ppt_exporter_v2", "export_professional"),
    "export_with_theme": ("exporters.ppt_exporter_v2", "export_with_theme"),
    "export_for_industry": ("exporters.ppt_exporter_v2", "export_for_industry"),
    "HTMLExporter": ("exporters.html_exporter", "HTMLExporter"),
    "HTMLTheme": ("exporters.html_exporter", "HTMLTheme"),
    "HTMLChartGenerator": ("exporters.html_exporter", "HTMLChartGenerator"),
    "export_html": ("exporters.html_exporter", "export_html"),
    "export_html_dark": ("exporters.html_exporter", "export_html_dark"),
    "export_xlsx": ("exporters.xlsx_exporter", "export_xlsx"),
}

__all__ = list(_LAZY.keys())


def __getattr__(name: str):
    if name in _LAZY:
        mod, attr = _LAZY[name]
        return getattr(importlib.import_module(mod), attr)
    raise AttributeError(f"module 'exporters' has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
