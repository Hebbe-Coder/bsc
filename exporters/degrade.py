"""导出降级规则与失败分类。纯逻辑，无副作用。"""
from __future__ import annotations

from exporters.errors import ExportDependencyError

# 每格式的候补链（请求格式不可产出时依次尝试）。
DEGRADATION_RULES: dict[str, list[str]] = {
    "pptx": ["ppt", "html", "markdown"],
    "word": ["html", "markdown"],
    "pdf": ["html", "markdown"],
    "xlsx": [],  # 默认 unimplemented；可选配置 ["html"] 降级到 HTML 表格
    "html": ["markdown"],
    "markdown": ["html"],
    "ppt": [],
    "json": [],
}

# 端点真正能产出的格式集合（用于识别「未实现格式」）。
IMPLEMENTED_FORMATS = {"json", "html", "ppt", "word", "markdown", "pdf", "visuals"}

# 允许出现在请求里的格式（含可降级但自身未实现的 pptx/xlsx）。
VALID_OUTPUT_TYPES = IMPLEMENTED_FORMATS | {"pptx", "xlsx"}


def is_implemented(fmt: str) -> bool:
    return fmt in IMPLEMENTED_FORMATS


def classify_failure(fmt: str, exc: Exception) -> dict:
    """把异常归类为结构化失败原因。"""
    if isinstance(exc, ExportDependencyError):
        return {
            "type": "dependency_missing",
            "format": fmt,
            "missing_package": exc.missing_package,
            "pip_install": exc.pip_install,
        }
    return {"type": "runtime_error", "format": fmt, "message": str(exc)}
