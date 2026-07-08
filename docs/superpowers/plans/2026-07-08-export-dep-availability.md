# 导出层依赖与可用性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除导出层的包级崩溃与静默成功，缺失依赖时给出结构化错误、能力门禁（422）、部分失败（207）与自检端点。

**Architecture:** 新增统一异常 `ExportDependencyError` 与能力登记表 `EXPORT_CAPABILITIES`；把 `exporters/__init__.py` 改为 PEP 562 惰性导入，并把 pptx 顶层导入下沉；`export_results` 端点在导出前做能力校验（422），全成功 200、部分失败 207；新增 `GET /bsc/exports/capabilities`。

**Tech Stack:** Python 3.13、FastAPI、Pydantic v2、pytest；测试用 `.venv/Scripts/python.exe -m pytest`。

**Spec:** `docs/superpowers/specs/2026-07-08-export-dep-availability-design.md`

**基线:** master `8909976`，测试 66 passed, 2 skipped。所有命令的工作目录为 `C:/Users/34216/Documents/New project 3/bsc-backend`。

> **通用注意（每个提交都适用）：** 用**定向 `git add <明确路径>`**，绝不用 `git add -A`/`git commit -a`，以免带入被跟踪的 `app/bsc_cloud.db`（测试副作用）。每步测试用 `.venv/Scripts/python.exe -m pytest`。

---

## File Structure

- Create: `exporters/errors.py` — 统一异常 `ExportDependencyError`（携带 format / missing_package / pip_install）。
- Create: `exporters/capabilities.py` — 能力探测 `_probe` + 登记表 `EXPORT_CAPABILITIES` + 辅助函数 `format_available` / `unavailable_formats`。
- Modify: `exporters/__init__.py` — 删除顶层 eager import，改 PEP 562 `__getattr__` 惰性。
- Modify: `exporters/ppt_exporter.py` — pptx 顶层 import 下沉（若有）+ 缺失抛 `ExportDependencyError`。
- Modify: `exporters/ppt_exporter_v2.py` — 同上。
- Modify: `exporters/word_exporter.py` / `pdf_exporter.py` / `xlsx_exporter.py` — 缺失分支改抛 `ExportDependencyError`。
- Modify: `app/api/response.py` — 新增 `ApiResponse.partial(...)`（code=207, success=False）。
- Modify: `app/api/bsc_api.py` — `export_results` 加能力门禁 + 207 语义；新增 `GET /bsc/exports/capabilities`。
- Create: `tests/test_export_dependencies.py` — 锁定全部新行为。

---

## Task 1: 统一异常 `ExportDependencyError`

**Files:**
- Create: `exporters/errors.py`
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_export_dependencies.py` 新建文件，写入：

```python
"""导出层依赖与可用性测试。"""
import pytest


def test_export_dependency_error_fields():
    from exporters.errors import ExportDependencyError
    err = ExportDependencyError("word", "python-docx", "pip install python-docx")
    assert err.format == "word"
    assert err.missing_package == "python-docx"
    assert err.pip_install == "pip install python-docx"
    msg = str(err)
    assert "word" in msg
    assert "python-docx" in msg
    assert "pip install python-docx" in msg
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_export_dependency_error_fields -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'exporters.errors'`

- [ ] **Step 3: 实现 `exporters/errors.py`**

```python
"""导出层统一异常。"""


class ExportDependencyError(Exception):
    """某导出格式所需的第三方依赖缺失时抛出。

    携带结构化字段，便于 API 层直接序列化给调用方。
    """

    def __init__(self, fmt: str, missing_package: str, pip_install: str):
        self.format = fmt
        self.missing_package = missing_package
        self.pip_install = pip_install
        super().__init__(
            f"格式 {fmt} 不可用：缺少依赖 {missing_package}，请执行 `{pip_install}`"
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_export_dependency_error_fields -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add exporters/errors.py tests/test_export_dependencies.py
git commit -m "feat(exporters): add structured ExportDependencyError"
```

---

## Task 2: 能力登记表 `capabilities.py`

**Files:**
- Create: `exporters/capabilities.py`
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_export_dependencies.py`：

```python
def test_capabilities_zero_dep_formats_available():
    from exporters.capabilities import EXPORT_CAPABILITIES, format_available
    for fmt in ("json", "html", "ppt", "markdown"):
        assert EXPORT_CAPABILITIES[fmt]["available"] is True
        assert format_available(fmt) is True


def test_capabilities_probe_reflects_installed_state():
    import importlib.util
    from exporters.capabilities import EXPORT_CAPABILITIES
    # openpyxl 在 .venv 中已安装，应为 available
    expected = importlib.util.find_spec("openpyxl") is not None
    assert EXPORT_CAPABILITIES["xlsx"]["available"] is expected


def test_unavailable_formats_shape():
    from exporters.capabilities import unavailable_formats
    result = unavailable_formats(["json", "html"])
    assert result == []  # 零依赖格式永远可用
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py -k capabilities -v`
Expected: FAIL，`No module named 'exporters.capabilities'`

- [ ] **Step 3: 实现 `exporters/capabilities.py`**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py -k capabilities -v`
Expected: PASS

同时运行形状测试：
Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_unavailable_formats_shape -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add exporters/capabilities.py tests/test_export_dependencies.py
git commit -m "feat(exporters): add capability registry with dependency probing"
```

---

## Task 3: 惰性 `exporters/__init__.py` + pptx 下沉

**Files:**
- Modify: `exporters/__init__.py`（当前为顶层 eager import，见 line 1-4）
- Modify: `exporters/ppt_exporter.py`
- Modify: `exporters/ppt_exporter_v2.py:21-27`（顶层 `from pptx import ...`）
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_export_dependencies.py`（用 `sys.modules` 模拟 pptx 缺失，验证包仍可导入、零依赖导出器仍可用）：

```python
def test_package_imports_without_pptx(monkeypatch):
    import sys, importlib
    # 让 import pptx 失败
    monkeypatch.setitem(sys.modules, "pptx", None)
    for name in [n for n in list(sys.modules) if n == "exporters" or n.startswith("exporters.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    # 包本身可导入（不再因 pptx 顶层 import 崩溃）
    pkg = importlib.import_module("exporters")
    # 零依赖导出器可通过惰性属性访问
    assert callable(getattr(pkg, "export_html"))
    # word 导出器子模块可导入（不依赖 pptx）
    wmod = importlib.import_module("exporters.word_exporter")
    assert hasattr(wmod, "WordExporter")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_package_imports_without_pptx -v`
Expected: FAIL —— 当前 `exporters/__init__.py` 顶层 `from exporters.ppt_exporter import ...` 会触发 pptx import，在 pptx 被置 None 时抛错。

- [ ] **Step 3a: 改写 `exporters/__init__.py` 为惰性**

用以下完整内容替换 `exporters/__init__.py`：

```python
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
```

- [ ] **Step 3b: 下沉 `ppt_exporter_v2.py` 的 pptx 顶层 import**

`exporters/ppt_exporter_v2.py:21-27` 现为：

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.fill import FillFormat
from pptx.oxml.xmlchemy import OxmlElement
```

将这 7 行替换为一个惰性加载帮助函数（放在文件顶层 import 区之后、任何类定义之前）：

```python
def _load_pptx():
    """惰性导入 python-pptx；缺失时抛结构化错误。"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.dml.fill import FillFormat
        from pptx.oxml.xmlchemy import OxmlElement
    except ImportError as e:
        from exporters.errors import ExportDependencyError
        raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx matplotlib") from e
    return {
        "Presentation": Presentation, "Inches": Inches, "Pt": Pt, "Emu": Emu,
        "RGBColor": RGBColor, "PP_ALIGN": PP_ALIGN, "MSO_SHAPE": MSO_SHAPE,
        "FillFormat": FillFormat, "OxmlElement": OxmlElement,
    }
```

然后在实际用到这些符号的函数/方法体内，于首行调用 `_p = _load_pptx()` 并改用 `_p["Presentation"]` 等引用。

> **实现者注意：** 若 `ppt_exporter_v2.py` 中这些符号在模块级被大量直接引用（类属性、装饰器、模块级常量），改造量可能较大。此时采用**更小侵入**的等价做法：保留原有 `from pptx import ...` 但整体包进 `try/except ImportError`，在 except 分支内把这些名字设为 `None`，并在每个 `export_*` 入口函数首行加：
> ```python
> if Presentation is None:
>     from exporters.errors import ExportDependencyError
>     raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx matplotlib")
> ```
> 关键目标只有一个：**模块顶层 import pptx 失败不再让整个文件导入崩溃**。选侵入最小的方案即可。

- [ ] **Step 3c: 同法处理 `exporters/ppt_exporter.py`**

先检查其顶层是否 `import pptx`：

Run: `grep -n "^from pptx\|^import pptx" exporters/ppt_exporter.py`

若有，按 Step 3b 的「更小侵入」做法用 `try/except ImportError` 包住顶层 pptx import，并在其 `export_*` 入口处加缺失守卫抛 `ExportDependencyError("pptx", "python-pptx", "pip install python-pptx matplotlib")`。若无顶层 pptx import（例如它本身不生成 pptx 文件），则本步跳过。

- [ ] **Step 4: 运行新测试 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_package_imports_without_pptx -v`
Expected: PASS

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `68 passed, 2 skipped`（原 66 + Task1/2/3 新增用例；数字以实际为准，关键是**无 FAIL、2 skipped 不变**）

- [ ] **Step 5: 提交**

```bash
git add exporters/__init__.py exporters/ppt_exporter.py exporters/ppt_exporter_v2.py tests/test_export_dependencies.py
git commit -m "feat(exporters): lazy package init + defer pptx imports

Eliminates package-level crash when python-pptx is missing; zero-dep
exporters (html/markdown/json) remain importable."
```

---

## Task 4: `word/pdf/xlsx` 缺失分支改抛 `ExportDependencyError`

**Files:**
- Modify: `exporters/word_exporter.py:22-23`
- Modify: `exporters/pdf_exporter.py:45`
- Modify: `exporters/xlsx_exporter.py:23-24`
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_word_exporter_missing_dep_raises_structured(monkeypatch):
    import sys
    from exporters.errors import ExportDependencyError
    monkeypatch.setitem(sys.modules, "docx", None)
    from exporters.word_exporter import WordExporter
    exp = WordExporter()
    with pytest.raises(ExportDependencyError) as ei:
        exp.export({})
    assert ei.value.missing_package == "python-docx"
    assert "pip install python-docx" in ei.value.pip_install
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_word_exporter_missing_dep_raises_structured -v`
Expected: FAIL —— 当前抛的是 `RuntimeError` 而非 `ExportDependencyError`。

- [ ] **Step 3a: 改 `exporters/word_exporter.py`**

将 line 22-23：

```python
        if not self._docx_available:
            raise RuntimeError("python-docx未安装，请运行: pip install python-docx")
```

替换为：

```python
        if not self._docx_available:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
```

- [ ] **Step 3b: 改 `exporters/pdf_exporter.py`**

将 line 44-45：

```python
        else:
            raise RuntimeError("需要安装weasyprint、pdfkit或reportlab来生成PDF")
```

替换为：

```python
        else:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("pdf", "weasyprint", "pip install weasyprint")
```

- [ ] **Step 3c: 改 `exporters/xlsx_exporter.py`**

将 line 23-24：

```python
    except ImportError:
        raise ImportError("openpyxl required: pip install openpyxl")
```

替换为：

```python
    except ImportError as e:
        from exporters.errors import ExportDependencyError
        raise ExportDependencyError("xlsx", "openpyxl", "pip install openpyxl") from e
```

- [ ] **Step 4: 运行新测试 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_word_exporter_missing_dep_raises_structured -v`
Expected: PASS

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 无 FAIL，2 skipped 不变。

- [ ] **Step 5: 提交**

```bash
git add exporters/word_exporter.py exporters/pdf_exporter.py exporters/xlsx_exporter.py tests/test_export_dependencies.py
git commit -m "feat(exporters): raise ExportDependencyError from word/pdf/xlsx"
```

---

## Task 5: `ApiResponse.partial`（207）

**Files:**
- Modify: `app/api/response.py`
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_apiresponse_partial():
    from app.api.response import ApiResponse
    resp = ApiResponse.partial(
        data={"exports": {}}, message="部分格式失败",
        errors=[{"format": "word", "missing_package": "python-docx"}],
    )
    assert resp.success is False
    assert resp.code == 207
    assert resp.message == "部分格式失败"
    assert resp.errors and resp.errors[0]["format"] == "word"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_apiresponse_partial -v`
Expected: FAIL —— `ApiResponse` 无 `partial`；且 `errors: List[str]` 类型不接受 dict。

- [ ] **Step 3: 改 `app/api/response.py`**

将 line 13 的 errors 类型放宽（当前 `errors: List[str] = []`）为：

```python
    errors: List = []
```

在 `error` 分类方法之后（line 24 之后）新增：

```python
    @classmethod
    def partial(cls, data: T = None, message: str = "部分成功", errors: List = None) -> "ApiResponse[T]":
        """部分成功响应（如多格式导出中个别失败）。"""
        return cls(success=False, data=data, message=message, errors=errors or [], code=207)
```

- [ ] **Step 4: 运行新测试 + 回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py::test_apiresponse_partial -v`
Expected: PASS

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 无 FAIL，2 skipped 不变。

- [ ] **Step 5: 提交**

```bash
git add app/api/response.py tests/test_export_dependencies.py
git commit -m "feat(api): add ApiResponse.partial (HTTP 207)"
```

---

## Task 6: `export_results` 能力门禁 + 207 + `/capabilities` 端点

**Files:**
- Modify: `app/api/bsc_api.py`（`export_results` 见 line 396-455；router `prefix="/bsc"` 见 line 10）
- Test: `tests/test_export_dependencies.py`

- [ ] **Step 1: 写失败测试**

追加（用 FastAPI `TestClient`，参考现有测试的 app 装载方式）：

```python
def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_capabilities_endpoint():
    resp = _client().get("/bsc/exports/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    caps = body["data"]["capabilities"] if "data" in body else body["capabilities"]
    assert caps["json"]["available"] is True
    assert "word" in caps


def test_export_gate_422_when_format_unavailable(monkeypatch):
    from exporters import capabilities as cap
    # 强制把 word 标记为不可用
    patched = dict(cap.EXPORT_CAPABILITIES)
    patched["word"] = {"available": False, "deps": ["docx"], "missing": "python-docx",
                       "pip_install": "pip install python-docx", "format": "word"}
    monkeypatch.setattr(cap, "EXPORT_CAPABILITIES", patched)
    resp = _client().post("/bsc/export_results", json={
        "business_system": {"business_domain": "x"},
        "output_types": ["json", "word"],
    })
    assert resp.status_code == 200  # FastAPI 包装层返回 200，body.code 反映 422
    body = resp.json()
    assert body["code"] == 422
    assert any(u["format"] == "word" for u in body["data"]["unavailable"])
```

> **实现者注意：** 现有端点通过 `ApiResponse` 返回，HTTP 层可能恒为 200 而业务码在 `body["code"]`。先运行一个现有导出测试确认该项目的返回约定（`grep -rn "export_results\|/bsc/export" tests/`），并据此把上面断言里的 `status_code` 调整为与项目一致（若项目用 `JSONResponse(status_code=...)` 则直接断 422/207）。保持与既有约定一致，不要新引入不一致的返回风格。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py -k "capabilities_endpoint or export_gate" -v`
Expected: FAIL —— 端点不存在 / 无门禁。

- [ ] **Step 3a: 在 `export_results` 开头加能力门禁**

在 `app/api/bsc_api.py` 的 `export_results` 内，参数校验（line 400-407 的 if/elif/else）**之后**、`exports = {}`（line 409）**之前**插入：

```python
    from exporters.capabilities import unavailable_formats
    unavail = unavailable_formats(req.output_types)
    if unavail:
        return ApiResponse.error(
            "以下导出格式当前不可用，请先安装对应依赖",
            code=422,
        ).model_copy(update={"data": {"unavailable": unavail}})
```

> 若项目里 `ApiResponse.error` 不支持携带 data，则改为直接构造：`ApiResponse(success=False, code=422, message="...", data={"unavailable": unavail})`。以实际 `ApiResponse` 签名为准（见 `app/api/response.py`）。

- [ ] **Step 3b: 结尾按成败返回 200/207**

将 `export_results` 结尾（line 450-455）的：

```python
    return ApiResponse.ok({
        "exports": exports,
        "formats": list(exports.keys()),
        "summary": result["summary"],
        "errors": errors,
    })
```

替换为：

```python
    payload = {
        "exports": exports,
        "formats": list(exports.keys()),
        "summary": result["summary"],
        "errors": errors,
    }
    if errors:
        return ApiResponse.partial(payload, message="部分格式导出失败", errors=errors)
    return ApiResponse.ok(payload)
```

- [ ] **Step 3c: 新增 `/capabilities` 端点**

在 `export_results` 函数定义之后新增（router 前缀已是 `/bsc`，故路径写 `/exports/capabilities`）：

```python
@router.get(
    "/exports/capabilities",
    summary="导出能力自检",
    description="返回各导出格式当前是否可用及缺失依赖的安装命令。",
)
async def export_capabilities():
    from exporters.capabilities import EXPORT_CAPABILITIES
    return ApiResponse.ok({"capabilities": EXPORT_CAPABILITIES})
```

- [ ] **Step 4: 运行新测试 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export_dependencies.py -v`
Expected: 全 PASS

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 无 FAIL；2 skipped 不变。

- [ ] **Step 5: 提交**

```bash
git add app/api/bsc_api.py tests/test_export_dependencies.py
git commit -m "feat(api): export capability gate (422) + partial (207) + /capabilities"
```

---

## Final Verification

- [ ] 全量测试：`.venv/Scripts/python.exe -m pytest -q` → 无 FAIL，2 skipped 不变。
- [ ] `git status --short` 确认 `app/bsc_cloud.db` 未被任何提交带入（应仅显示为未暂存的 M）。
- [ ] `git log --oneline -8` 确认 6 段提交齐整。
- [ ] 手动 smoke（可选）：启动 app 后 `GET /bsc/exports/capabilities` 返回各格式可用状态。

---

## Self-Review（作者已核对）

- **Spec 覆盖**：§3.1→Task1、§3.4→Task2、§3.2/3.3→Task3、§3.1 落到各导出器→Task4、§3.5(207)→Task5、§3.5(422)+§3.6→Task6、§3.7→贯穿各 Task 的测试。全覆盖。
- **占位符**：无 TBD；唯二「实现者注意」是**基于真实代码不确定性**（pptx 模块级引用范围、项目 ApiResponse 返回约定）给出的判定指引，且都给了可执行的判断命令与两种确定写法，非占位。
- **类型一致**：`ExportDependencyError(fmt, missing_package, pip_install)` 三参签名在 Task1 定义、Task3/4 调用一致；`unavailable_formats` 返回项键 `format/missing_package/pip_install` 在 Task2 定义、Task6 断言一致；`EXPORT_CAPABILITIES[fmt]` 键 `available/deps/missing/pip_install/format` 全表统一。
