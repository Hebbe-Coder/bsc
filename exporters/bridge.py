"""
ExportBridge — 统一导出调度层

借鉴 Grok Build 的 ToolBridge → ToolRegistry → ToolDefinition 三层架构,
将 BSC 的 7 个独立 exporter 统一为可发现、可注册、可扩展的导出调度器。

使用方式:
    from exporters.bridge import ExportBridge

    # 单一格式
    result = ExportBridge.export("html", business_system)

    # 批量导出
    results = ExportBridge.export_all(business_system, ["html", "ppt", "json"])

    # 注册自定义导出器
    ExportBridge.register("myformat", MyCustomExporter)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, ClassVar, Optional

logger = logging.getLogger(__name__)


class ExportFormat(StrEnum):
    """导出格式枚举 — 与 app.enums.ExportFormat 对齐"""
    JSON = "json"
    HTML = "html"
    PPT = "ppt"
    WORD = "word"
    PDF = "pdf"
    XLSX = "xlsx"
    MARKDOWN = "markdown"


@dataclass
class ExportResult:
    """统一导出结果"""
    format: str
    success: bool
    path: str = ""
    content: Optional[Any] = None
    error: str = ""
    size_bytes: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "success": self.success,
            "path": self.path,
            "error": self.error,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


class ExportBridge:
    """
    统一导出调度器 — Grok Build ToolBridge 模式

    三层架构:
      ExportBridge.export(format, data)     # 统一入口 (ToolBridge)
        → _registry[format]                 # 动态查找 (ToolRegistry)
        → Exporter.export(data)             # 多态执行 (ToolDefinition)
    """

    # 格式 → (模块路径, 导出函数名, 描述)
    _registry: ClassVar[dict[str, tuple[str, str, str]]] = {
        ExportFormat.JSON: (
            "exporters.prd_exporters", "export_json",
            "JSON 结构化数据导出"
        ),
        ExportFormat.HTML: (
            "exporters.html_exporter", "export_html",
            "HTML 交互式报告"
        ),
        ExportFormat.PPT: (
            "exporters.ppt_exporter", "export_impeccable",
            "PPT 专业演示文稿 (v7)"
        ),
        ExportFormat.WORD: (
            "exporters.word_exporter", "WordExporter.export",
            "Word 文档报告"
        ),
        ExportFormat.PDF: (
            "exporters.pdf_exporter", "PDFExporter.export",
            "PDF 文档报告"
        ),
        ExportFormat.XLSX: (
            "exporters.xlsx_exporter", "export_xlsx",
            "Excel 数据报告 (6 sheets)"
        ),
        ExportFormat.MARKDOWN: (
            "exporters.markdown_exporter", "MarkdownExporter.export",
            "Markdown 格式报告"
        ),
    }

    # 格式别名
    _aliases: ClassVar[dict[str, str]] = {
        "docx": ExportFormat.WORD,
        "doc": ExportFormat.WORD,
        "pptx": ExportFormat.PPT,
        "excel": ExportFormat.XLSX,
        "xls": ExportFormat.XLSX,
        "md": ExportFormat.MARKDOWN,
    }

    # 自定义导出器注册表
    _custom: ClassVar[dict[str, Callable]] = {}

    @classmethod
    def register(cls, fmt: str, exporter: Callable, description: str = ""):
        """注册自定义导出器"""
        cls._custom[fmt] = exporter
        logger.info(f"ExportBridge: registered custom exporter '{fmt}'")

    @classmethod
    def unregister(cls, fmt: str):
        """注销导出器"""
        cls._custom.pop(fmt, None)

    @classmethod
    def list_formats(cls) -> list[dict]:
        """列出所有可用格式"""
        result = []
        for fmt, (mod, func, desc) in cls._registry.items():
            result.append({
                "format": fmt,
                "module": mod,
                "function": func,
                "description": desc,
                "aliases": [a for a, t in cls._aliases.items() if t == fmt],
            })
        for fmt, _ in cls._custom.items():
            result.append({"format": fmt, "module": "custom", "description": "自定义导出器"})
        return result

    @classmethod
    def resolve_format(cls, fmt: str) -> str:
        """解析格式别名 → 规范格式名"""
        fmt = fmt.lower().strip()
        if fmt in cls._aliases:
            return cls._aliases[fmt]
        return fmt

    @classmethod
    def supports(cls, fmt: str) -> bool:
        """检查是否支持某格式"""
        fmt = cls.resolve_format(fmt)
        return fmt in cls._registry or fmt in cls._custom

    @classmethod
    def export(cls, fmt: str, business_system: dict, **opts) -> ExportResult:
        """
        统一导出入口

        Args:
            fmt: 格式名称 (html/ppt/json/word/pdf/xlsx/markdown 或别名)
            business_system: BusinessSystem 字典
            **opts: 格式特定选项

        Returns:
            ExportResult: 统一结果对象
        """
        import time
        t0 = time.perf_counter()

        fmt = cls.resolve_format(fmt)

        try:
            # 优先自定义
            if fmt in cls._custom:
                result = cls._custom[fmt](business_system, **opts)
                elapsed = (time.perf_counter() - t0) * 1000
                return ExportResult(
                    format=fmt, success=True,
                    content=result,
                    metadata={"elapsed_ms": round(elapsed, 1), "source": "custom"}
                )

            # 内置导出器
            if fmt not in cls._registry:
                return ExportResult(
                    format=fmt, success=False,
                    error=f"不支持的导出格式: {fmt}。可用: {list(cls._registry.keys())}"
                )

            module_path, func_path, _ = cls._registry[fmt]
            exporter = cls._resolve_exporter(module_path, func_path)
            if exporter is None:
                return ExportResult(
                    format=fmt, success=False,
                    error=f"无法加载导出器: {module_path}.{func_path}"
                )

            result = exporter(business_system, **opts)

            elapsed = (time.perf_counter() - t0) * 1000

            # 处理不同返回类型
            if isinstance(result, str):
                return ExportResult(
                    format=fmt, success=True, path=result,
                    metadata={"elapsed_ms": round(elapsed, 1)}
                )
            elif isinstance(result, dict):
                return ExportResult(
                    format=fmt, success=result.get("success", True),
                    path=result.get("path", ""), error=result.get("error", ""),
                    metadata={"elapsed_ms": round(elapsed, 1), **result.get("metadata", {})}
                )
            else:
                return ExportResult(
                    format=fmt, success=True,
                    content=result,
                    metadata={"elapsed_ms": round(elapsed, 1)}
                )

        except Exception as e:
            logger.exception(f"ExportBridge: {fmt} 导出失败")
            return ExportResult(
                format=fmt, success=False,
                error=f"{type(e).__name__}: {e}"
            )

    @classmethod
    def export_all(
        cls, business_system: dict, formats: list[str], **opts
    ) -> dict[str, ExportResult]:
        """
        批量导出到多种格式

        Returns:
            {format: ExportResult} 字典
        """
        results = {}
        for fmt in formats:
            results[fmt] = cls.export(fmt, business_system, **opts)
        return results

    @classmethod
    def export_with_fallback(
        cls, formats: list[str], business_system: dict, **opts
    ) -> dict[str, ExportResult]:
        """
        依次尝试多种格式, 返回第一个成功的结果后继续导出其余格式

        用于"至少保证一种格式成功"的场景 (Grok Build 降级模式)
        """
        results = {}
        has_success = False
        for fmt in formats:
            result = cls.export(fmt, business_system, **opts)
            results[fmt] = result
            if result.success:
                has_success = True
        if not has_success:
            logger.warning("ExportBridge: 所有格式导出均失败")
        return results

    # ── 内部方法 ─────────────────────────────────────────

    @classmethod
    def _resolve_exporter(cls, module_path: str, func_path: str) -> Optional[Callable]:
        """解析导出器函数 (支持 Class.method 语法)"""
        import importlib

        try:
            mod = importlib.import_module(module_path)

            if "." in func_path:
                # Class.method 语法: "WordExporter.export"
                class_name, method_name = func_path.split(".", 1)
                cls_obj = getattr(mod, class_name)
                instance = cls_obj()
                return getattr(instance, method_name)
            else:
                return getattr(mod, func_path)

        except ImportError:
            logger.warning(f"ExportBridge: 模块 {module_path} 加载失败 (缺少依赖?)")
            return None
        except AttributeError:
            logger.warning(f"ExportBridge: {module_path}.{func_path} 不存在")
            return None


# ── 便捷函数 ──────────────────────────────────────────────

def export(fmt: str, bs: dict, **opts) -> ExportResult:
    """便捷函数: ExportBridge.export() 的简写"""
    return ExportBridge.export(fmt, bs, **opts)


def export_all(bs: dict, formats: list[str], **opts) -> dict[str, ExportResult]:
    """便捷函数: ExportBridge.export_all() 的简写"""
    return ExportBridge.export_all(bs, formats, **opts)
