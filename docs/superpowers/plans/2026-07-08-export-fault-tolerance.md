# 导出层容错与降级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/bsc/export` 在任意格式无法产出时默认走「容错与降级」：先尝试替代格式，无替代或替代也失败则丢弃其余成功格式，并在响应里用 `formats_status` 逐格式说明处理结果（produced / substituted / dropped + 原因）。

**Architecture:** 抽出 `exporters/orchestrator.py` 作为统一编排器，对每个请求格式做「实现检查 → 统一 try/except 产出 → 按 `DEGRADATION_RULES` 候补替换 → 丢弃并分类原因」；html/ppt/markdown 生成器迁入 `exporters/` 并接入 `DegradeContext` 做组件级跳过；`bsc_api.py` 只负责参数校验、调编排器、把 `ExportOutcome` 映射成 200/207/422/400。复用已有的 `ExportDependencyError` / `EXPORT_CAPABILITIES` / `ApiResponse.partial`。

**Tech Stack:** Python 3.13、FastAPI、Pydantic v2、pytest。复用 `exporters.errors.ExportDependencyError`、`app/api/response.py:ApiResponse`。

**设计文档：** `docs/superpowers/specs/2026-07-08-export-fault-tolerance-design.md`

---

## 文件结构

**新建：**
- `exporters/degrade.py` — `DEGRADATION_RULES` / `VALID_OUTPUT_TYPES` / `IMPLEMENTED_FORMATS` / `is_implemented()` / `classify_failure()`（纯逻辑）
- `exporters/_degrade_ctx.py` — `DegradeContext`（组件级跳过上下文）
- `exporters/html_exporter.py` — 从 `bsc_api._generate_html` 迁入，增加 `ctx` 参数做组件级降级
- `exporters/ppt_spec_exporter.py` — 从 `bsc_api._generate_ppt_spec` 迁入，增加 `ctx` 参数
- `exporters/orchestrator.py` — `ExportOutcome` + `run_export()`
- `tests/test_export_degrade.py` — 单元测试 + 端点集成测试

**修改：**
- `exporters/markdown_exporter.py` — `export()` 增加 `ctx=None` 参数，各区块包 `ctx.component()`
- `app/api/bsc_api.py` — 删除 `_generate_html` / `_generate_ppt_spec` 定义（已迁入）与 `export_results` 内的 422 门禁 + 分散 try/except；改为调 `run_export` 并映射 HTTP

---

### Task 1: `exporters/degrade.py` — 降级规则与失败分类

**Files:**
- Create: `exporters/degrade.py`
- Test: `tests/test_export_degrade.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_export_degrade.py
import pytest
from exporters.degrade import (
    DEGRADATION_RULES,
    IMPLEMENTED_FORMATS,
    VALID_OUTPUT_TYPES,
    is_implemented,
    classify_failure,
)
from exporters.errors import ExportDependencyError


def test_degradation_rules_present():
    assert DEGRADATION_RULES["pptx"] == ["ppt", "html", "markdown"]
    assert DEGRADATION_RULES["word"] == ["html", "markdown"]
    assert DEGRADATION_RULES["pdf"] == ["html", "markdown"]
    assert DEGRADATION_RULES["xlsx"] == []          # 默认 unimplemented
    assert DEGRADATION_RULES["ppt"] == []
    assert DEGRADATION_RULES["json"] == []


def test_is_implemented():
    assert is_implemented("html") is True
    assert is_implemented("word") is True
    assert is_implemented("visuals") is True
    assert is_implemented("pptx") is False          # 可请求但需降级
    assert is_implemented("xlsx") is False


def test_valid_output_types_includes_degradable():
    assert "pptx" in VALID_OUTPUT_TYPES
    assert "xlsx" in VALID_OUTPUT_TYPES
    assert "html" in VALID_OUTPUT_TYPES
    assert "zzz" not in VALID_OUTPUT_TYPES


def test_classify_dependency_missing():
    err = ExportDependencyError("word", "python-docx", "pip install python-docx")
    r = classify_failure("word", err)
    assert r["type"] == "dependency_missing"
    assert r["missing_package"] == "python-docx"
    assert r["pip_install"] == "pip install python-docx"


def test_classify_runtime_error():
    r = classify_failure("html", ValueError("boom"))
    assert r["type"] == "runtime_error"
    assert r["message"] == "boom"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py -v`
Expected: ERROR/FAIL（`ModuleNotFoundError: No module named 'exporters.degrade'`）

- [ ] **Step 3: 写最小实现**

```python
# exporters/degrade.py
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add exporters/degrade.py tests/test_export_degrade.py
git commit -m "feat(exporters): add degradation rules + failure classification"
```

---

### Task 2: `exporters/_degrade_ctx.py` — 组件级跳过上下文

**Files:**
- Create: `exporters/_degrade_ctx.py`
- Test: `tests/test_export_degrade.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_export_degrade.py
from exporters._degrade_ctx import DegradeContext


def test_component_failure_is_captured_not_raised():
    ctx = DegradeContext()
    with ctx.component("chart"):
        raise ValueError("chart broke")
    assert ctx.component_failures == [
        {"type": "component_failed", "component": "chart", "message": "chart broke"}
    ]


def test_component_success_no_failure():
    ctx = DegradeContext()
    with ctx.component("table"):
        pass
    assert ctx.component_failures == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py::test_component_failure_is_captured_not_raised -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'exporters._degrade_ctx'`）

- [ ] **Step 3: 写最小实现**

```python
# exporters/_degrade_ctx.py
"""组件级「跳过上下文」：子组件渲染失败时记录并继续，而非整格式中止。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import List


class DegradeContext:
    def __init__(self) -> None:
        self.component_failures: List[dict] = []

    @contextmanager
    def component(self, name: str):
        try:
            yield
        except Exception as e:  # noqa: BLE001
            self.component_failures.append(
                {"type": "component_failed", "component": name, "message": str(e)}
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add exporters/_degrade_ctx.py tests/test_export_degrade.py
git commit -m "feat(exporters): add DegradeContext for component-level skip"
```

---

### Task 3: 迁入 html/ppt 生成器并接入 `ctx`

把 `bsc_api._generate_html` 与 `bsc_api._generate_ppt_spec` 迁入 `exporters/`，增加 `ctx` 参数，每个区块用 `ctx.component()` 包裹（无 `ctx` 时行为不变）。

**Files:**
- Create: `exporters/html_exporter.py`
- Create: `exporters/ppt_spec_exporter.py`
- Test: `tests/test_export_degrade.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_export_degrade.py
from exporters.html_exporter import generate_html
from exporters.ppt_spec_exporter import generate_ppt_spec
from exporters._degrade_ctx import DegradeContext


def _bs_with(metrics):
    return {"business_domain": "D", "report": {"executive_summary": "S"},
            "objectives": [{"objective": "O", "target": "T", "priority": "high"}],
            "workflow": [{"step": 1, "name": "N", "action": "A"}],
            "metrics": metrics, "risks": [{"risk": "R", "severity": "high", "mitigation": "M"}]}


def test_generate_html_basic():
    html = generate_html(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]), {})
    assert "<html>" in html and "业务目标" in html and "<table>" in html


def test_generate_html_skips_failing_component():
    ctx = DegradeContext()
    bs = _bs_with("BROKEN")  # metrics 不是 list，区块渲染会出错
    html = generate_html(bs, {}, ctx)
    # 即便 metrics 区块失败，整体 HTML 仍产出
    assert "<html>" in html
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "metrics"


def test_generate_ppt_spec_basic():
    spec = generate_ppt_spec(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    assert "slides" in spec and spec["slide_count"] >= 1


def test_generate_ppt_spec_skips_failing_component():
    ctx = DegradeContext()
    spec = generate_ppt_spec(_bs_with("BROKEN"), ctx)
    assert "slides" in spec
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "metrics"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py -k "generate_html or generate_ppt_spec" -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 写实现（迁入 + ctx 包裹）**

```python
# exporters/html_exporter.py
"""HTML 报告生成器（含组件级降级）。从 bsc_api._generate_html 迁入。"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, Optional

from exporters._degrade_ctx import DegradeContext


def generate_html(
    business_system: dict,
    pipeline_info: dict,
    ctx: Optional[DegradeContext] = None,
) -> str:
    """生成 HTML 报告。ctx 非空时单个区块渲染失败会被跳过而非整页崩溃。"""
    sections: list[str] = []

    def _block(name: str, render):
        if ctx is None:
            render()
        else:
            with ctx.component(name):
                render()

    def _header():
        sections.append(f"<h1>{html.escape(business_system.get('business_domain', '业务系统分析'))}</h1>")
        sections.append(f"<p class='summary'>{html.escape(business_system.get('report', {}).get('executive_summary', ''))}</p>")

    _block("header", _header)

    def _objectives():
        if business_system.get("objectives"):
            sections.append("<h2>业务目标</h2>")
            sections.append("<ul>")
            for obj in business_system["objectives"]:
                priority = obj.get("priority", "medium")
                sections.append(f"<li><strong>{html.escape(obj.get('objective', ''))}</strong>: {html.escape(obj.get('target', ''))} ({html.escape(priority)})</li>")
            sections.append("</ul>")

    _block("objectives", _objectives)

    def _workflow():
        if business_system.get("workflow"):
            sections.append("<h2>流程步骤</h2>")
            sections.append("<ol>")
            for step in business_system["workflow"]:
                sections.append(f"<li><strong>步骤{html.escape(str(step.get('step', '')))}: {html.escape(step.get('name', ''))}</strong><br>{html.escape(step.get('action', ''))}</li>")
            sections.append("</ol>")

    _block("workflow", _workflow)

    def _metrics():
        if business_system.get("metrics"):
            sections.append("<h2>关键指标</h2>")
            sections.append("<table>")
            sections.append("<tr><th>指标</th><th>公式</th><th>目标</th><th>负责人</th></tr>")
            for kpi in business_system["metrics"]:
                sections.append(f"<tr><td>{html.escape(kpi.get('name', ''))}</td><td>{html.escape(kpi.get('formula', ''))}</td><td>{html.escape(kpi.get('target', ''))}</td><td>{html.escape(kpi.get('owner', ''))}</td></tr>")
            sections.append("</table>")

    _block("metrics", _metrics)

    def _risks():
        if business_system.get("risks"):
            sections.append("<h2>风险分析</h2>")
            sections.append("<ul>")
            for risk in business_system["risks"]:
                sections.append(f"<li><strong>{html.escape(risk.get('risk', ''))}</strong> ({html.escape(risk.get('severity', ''))}) - {html.escape(risk.get('mitigation', ''))}</li>")
            sections.append("</ul>")

    _block("risks", _risks)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>业务系统分析报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #12161A; color: #E8E8E8; }}
        h1 {{ color: #C9A84C; }}
        h2 {{ color: #5A9E96; margin-top: 30px; }}
        .summary {{ font-size: 1.1em; color: #B8B8B8; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
        th, td {{ border: 1px solid #2E3338; padding: 10px; text-align: left; }}
        th {{ background: #1C2024; color: #C9A84C; }}
        ul, ol {{ line-height: 1.8; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
{''.join(sections)}
<p style='margin-top: 40px; color: #8A8A86; font-size: 0.9em;'>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body>
</html>"""

    return html_content
```

```python
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
```

> 注意：`generate_ppt_spec` 的 `_metrics` 写法刻意保留对 `business_system["metrics"]` 的遍历（与原始逻辑一致）。测试里用合法 list 即可通过；若传入非 list 则被 `ctx.component` 捕获跳过。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -k "generate_html or generate_ppt_spec" -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add exporters/html_exporter.py exporters/ppt_spec_exporter.py tests/test_export_degrade.py
git commit -m "feat(exporters): relocate html/ppt generators with component-level degrade"
```

> 此时**不要**删除 `bsc_api.py` 里的旧函数——Task 6 重构端点时一并移除，避免中间态破坏其他导入。

---

### Task 4: `markdown_exporter` 接入 `ctx`

**Files:**
- Modify: `exporters/markdown_exporter.py`（仅改 `export` 方法签名与区块包裹）
- Test: `tests/test_export_degrade.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_export_degrade.py
from exporters.markdown_exporter import MarkdownExporter


def test_markdown_basic():
    md = MarkdownExporter().export(_bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}]))
    assert md.startswith("# ") and "业务目标" in md


def test_markdown_skips_failing_component():
    ctx = DegradeContext()
    bs = _bs_with([{"name": "n", "formula": "f", "target": "t", "owner": "o"}])
    bs["objectives"] = "BROKEN"  # 让 objectives 区块渲染失败（markdown 无 metrics 区块）
    md = MarkdownExporter().export(bs, ctx)
    assert md.startswith("# ")
    assert ctx.component_failures and ctx.component_failures[0]["component"] == "objectives"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py -k "markdown" -v`
Expected: FAIL（`export() got an unexpected keyword argument 'ctx'` 或 component_failures 为空）

- [ ] **Step 3: 修改实现**

把 `exporters/markdown_exporter.py` 的 `export` 方法改为接收 `ctx=None`，并用 `with ctx.component(...)` 包裹每个 `lines.append` 区块（区块渲染异常时跳过，继续产出其余部分）。`ctx is None` 时行为完全不变。

完整改写后的文件：

```python
# exporters/markdown_exporter.py
"""Markdown Exporter - 生成Markdown格式报告（含组件级降级）"""
from typing import Dict, Any, Optional
import logging

from exporters._degrade_ctx import DegradeContext

logger = logging.getLogger(__name__)


class MarkdownExporter:
    """Markdown文档导出器"""

    def export(self, business_system: Dict[str, Any], ctx: Optional[DegradeContext] = None) -> str:
        """导出为Markdown格式。ctx 非空时单个区块失败被跳过。"""
        lines: list[str] = []

        def _block(name: str, render):
            if ctx is None:
                render()
            else:
                with ctx.component(name):
                    render()

        def _header():
            title = business_system.get("business_domain", "业务系统分析报告")
            lines.append(f"# {title}")
            lines.append("")
            subtitle = business_system.get("report", {}).get("executive_summary", "")
            if subtitle:
                lines.append(f"> {subtitle}")
                lines.append("")
            lines.append("---")
            lines.append("")

        _block("header", _header)

        def _objectives():
            lines.append("## 一、业务目标")
            objectives = business_system.get("objectives", [])
            if objectives:
                for obj in objectives:
                    priority = obj.get("priority", "medium")
                    priority_label = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                    line = f"{priority_label} **{obj.get('objective', '')}**"
                    if obj.get("target"):
                        line += f" - 目标: {obj.get('target')}"
                    lines.append(line)
            else:
                lines.append("暂无业务目标")
            lines.append("")

        _block("objectives", _objectives)

        def _roles():
            lines.append("## 二、角色定义")
            roles = business_system.get("roles", [])
            if roles:
                lines.append("| 角色名称 | 所属部门 | 级别 | 人数 |")
                lines.append("|----------|----------|------|------|")
                for role in roles:
                    lines.append(f"| {role.get('role', '')} | {role.get('department', '')} | {role.get('level', '')} | {role.get('headcount', '')} |")
            else:
                lines.append("暂无角色定义")
            lines.append("")

        _block("roles", _roles)

        def _workflow():
            lines.append("## 三、业务流程")
            workflow = business_system.get("workflow", [])
            if workflow:
                for step in workflow:
                    step_num = step.get('step', '')
                    name = step.get('name', '')
                    action = step.get('action', '')
                    role = step.get('role', '')
                    lines.append(f"{step_num}. **{name}**")
                    if action:
                        lines.append(f"   - 动作: {action}")
                    if role:
                        lines.append(f"   - 负责角色: {role}")
                    lines.append("")
            else:
                lines.append("暂无业务流程")
            lines.append("")

        _block("workflow", _workflow)

        def _risks():
            lines.append("## 四、风险分析")
            risks = business_system.get("risks", [])
            if risks:
                for risk in risks:
                    level = risk.get("level", "medium")
                    level_label = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}.get(level, "⚪ 未知")
                    lines.append(f"### {level_label}: {risk.get('risk', '')}")
                    if risk.get("mitigation"):
                        lines.append(f"- **应对措施**: {risk.get('mitigation')}")
                    lines.append("")
            else:
                lines.append("暂无风险分析")
            lines.append("")

        _block("risks", _risks)

        def _strategy():
            lines.append("## 五、战略建议")
            strategy = business_system.get("strategy", {})
            recommendations = strategy.get("recommendations", [])
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    lines.append(f"{i}. {rec}")
            else:
                lines.append("暂无战略建议")
            lines.append("")

        _block("strategy", _strategy)

        def _footer():
            lines.append("---")
            lines.append(f"> 报告生成时间: {business_system.get('generated_at', '')}")

        _block("footer", _footer)

        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -k "markdown" -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add exporters/markdown_exporter.py tests/test_export_degrade.py
git commit -m "feat(exporters): markdown exporter component-level degrade"
```

---

### Task 5: `exporters/orchestrator.py` — 统一编排器

**Files:**
- Create: `exporters/orchestrator.py`
- Test: `tests/test_export_degrade.py`（追加编排单测）

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_export_degrade.py
import exporters.orchestrator as orchestrator
from exporters.orchestrator import run_export, ExportOutcome
from exporters.errors import ExportDependencyError


def _bs():
    return {"business_domain": "D", "report": {"executive_summary": "S"}}


def test_run_export_substitutes_pptx_to_ppt(monkeypatch):
    def fake_produce(fmt, bs, result, ctx):
        if fmt == "pptx":
            raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx")
        if fmt == "ppt":
            return {"slides": []}
        raise AssertionError("unexpected fmt " + fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["pptx"], {})
    assert out.formats_status[0] == {"format": "pptx", "status": "substituted", "source_format": "ppt"}
    assert "ppt" in out.exports


def test_run_export_drops_unimplemented(monkeypatch):
    def fake_produce(fmt, bs, result, ctx):
        raise AssertionError("xlsx 不应进入 _produce")
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["xlsx"], {})
    st = out.formats_status[0]
    assert st["status"] == "dropped"
    assert st["reason"] == "unimplemented"


def test_run_export_drops_dependency_missing(monkeypatch):
    def fake_produce(fmt, bs, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["word"], {})
    st = out.formats_status[0]
    assert st["status"] == "dropped"
    assert st["reason"] == "dependency_missing"
    assert st["missing_package"] == "python-docx"


def test_run_export_component_failures_attached(monkeypatch):
    def fake_produce(fmt, bs, result, ctx):
        with ctx.component("metrics"):
            raise ValueError("bad metric")
        return f"content-{fmt}"
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["html"], {})
    st = out.formats_status[0]
    assert st["status"] == "produced"
    assert st["components_degraded"][0]["type"] == "component_failed"
    assert st["components_degraded"][0]["component"] == "metrics"


def test_run_export_zero_produced_all_dropped(monkeypatch):
    def fake_produce(fmt, bs, result, ctx):
        if fmt in ("word", "html", "markdown"):
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise RuntimeError("no")
    monkeypatch.setattr(orchestrator, "_produce", fake_produce)
    out = run_export(_bs(), ["word"], {})
    assert all(s["status"] == "dropped" for s in out.formats_status)
    assert "word" not in out.exports
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py -k "run_export" -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'exporters.orchestrator'`）

- [ ] **Step 3: 写实现**

```python
# exporters/orchestrator.py
"""导出编排器：统一 try/except + 候补替换 + 逐格式状态表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from exporters.degrade import DEGRADATION_RULES, classify_failure, is_implemented
from exporters._degrade_ctx import DegradeContext


@dataclass
class ExportOutcome:
    exports: Dict[str, Any] = field(default_factory=dict)
    formats_status: List[dict] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)


def _produce(fmt: str, bs: dict, result: dict, ctx: DegradeContext):
    """产出单个格式。成功返回产出物；失败抛异常。"""
    if fmt == "json":
        return bs
    if fmt == "html":
        from exporters.html_exporter import generate_html
        return generate_html(bs, result.get("pipeline", {}), ctx)
    if fmt == "ppt":
        from exporters.ppt_spec_exporter import generate_ppt_spec
        return generate_ppt_spec(bs, ctx)
    if fmt == "word":
        from exporters.word_exporter import WordExporter
        return {
            "content_base64": WordExporter().export(bs).hex(),
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    if fmt == "markdown":
        from exporters.markdown_exporter import MarkdownExporter
        return MarkdownExporter().export(bs, ctx)
    if fmt == "pdf":
        from exporters.pdf_exporter import PDFExporter
        return {"content_base64": PDFExporter().export(bs).hex(), "mime_type": "application/pdf"}
    if fmt == "visuals":
        from app.engines.visual_binding import bind_visuals
        try:
            return bind_visuals(bs)
        except Exception:  # noqa: BLE001
            return []
    raise RuntimeError(f"未知导出格式: {fmt}")


def run_export(bs: dict, output_types: List[str], result: dict) -> ExportOutcome:
    outcome = ExportOutcome()
    for fmt in output_types:
        # 1. 未实现格式 → dropped/unimplemented
        if not is_implemented(fmt):
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
                value = _produce(cand, bs, result, ctx)
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -k "run_export" -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add exporters/orchestrator.py tests/test_export_degrade.py
git commit -m "feat(exporters): add export orchestrator with substitution + status table"
```

---

### Task 6: 重构 `bsc_api.py` 的 `export_results`

删除旧 `_generate_html` / `_generate_ppt_spec` 定义，以及 `export_results` 内的 422 门禁 + 分散 try/except；改为校验 `VALID_OUTPUT_TYPES`、追加 `visuals`、调 `run_export`、映射 HTTP。

**Files:**
- Modify: `app/api/bsc_api.py`（删除第 491–608 行的两个生成函数；重写 `export_results` 约 396–478 行）
- Test: `tests/test_export_degrade.py`（Task 7 端点集成测试）

- [ ] **Step 1: 写端点集成测试（先红）**

```python
# 追加到 tests/test_export_degrade.py
from fastapi.testclient import TestClient
from app.main import app  # 若 main 入口不同，按项目实际导入
import exporters.orchestrator as orchestrator


def _client():
    return TestClient(app)


def _req(output_types, bs=None):
    body = {"output_types": output_types}
    if bs is not None:
        body["business_system"] = bs
    else:
        body["input"] = "# PRD\n业务目标：提升内容安全准确率到 99%。"
    return body


def test_export_pptx_substituted_to_ppt(monkeypatch):
    def fake(fmt, bs, result, ctx):
        if fmt == "pptx":
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("pptx", "python-pptx", "pip install python-pptx")
        if fmt == "ppt":
            return {"slides": []}
        if fmt == "html":
            return "<html></html>"
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["pptx", "html"]))
    assert r.status_code == 207, r.text
    data = r.json()["data"]
    by_fmt = {s["format"]: s for s in data["formats_status"]}
    assert by_fmt["pptx"]["status"] == "substituted"
    assert by_fmt["pptx"]["source_format"] == "ppt"
    assert by_fmt["html"]["status"] == "produced"


def test_export_word_dep_missing_substituted_to_html(monkeypatch):
    def fake(fmt, bs, result, ctx):
        if fmt in ("word", "markdown"):
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        if fmt == "html":
            return "<html></html>"
        raise AssertionError(fmt)
    monkeypatch.setattr(orchestrator, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["word"]))
    assert r.status_code == 207, r.text
    st = r.json()["data"]["formats_status"][0]
    assert st["status"] == "substituted" and st["source_format"] == "html"


def test_export_zero_produced_returns_422(monkeypatch):
    def fake(fmt, bs, result, ctx):
        if fmt in ("word", "html", "markdown"):
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        raise RuntimeError("no")
    monkeypatch.setattr(orchestrator, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["word"]))
    assert r.status_code == 422, r.text
    assert r.json()["data"]["formats_status"][0]["status"] == "dropped"


def test_export_unknown_format_400():
    r = _client().post("/bsc/export", json=_req(["zzz"]))
    assert r.status_code == 400, r.text


def test_export_component_degraded_reported(monkeypatch):
    orig = orchestrator._produce

    def fake(fmt, bs, result, ctx):
        if fmt == "html":
            with ctx.component("metrics"):
                raise ValueError("bad metric")
            return "<html></html>"
        return orig(fmt, bs, result, ctx)
    monkeypatch.setattr(orchestrator, "_produce", fake)
    r = _client().post("/bsc/export", json=_req(["html"]))
    assert r.status_code == 207, r.text
    st = r.json()["data"]["formats_status"][0]
    assert st["status"] == "produced"
    assert st["components_degraded"][0]["component"] == "metrics"
```

> 若 `from app.main import app` 导入失败（项目入口不同），改为项目实际的 FastAPI `app` 对象导入路径；TestClient 用法不变。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export_degrade.py -k "test_export_" -v`
Expected: FAIL（端点仍走旧的 422 硬失败 / 旧逻辑）

- [ ] **Step 3: 修改 `app/api/bsc_api.py`**

删除第 491–608 行的 `_generate_html` 与 `_generate_ppt_spec` 函数定义（已迁入 `exporters/`）。

将 `export_results`（约 396–478 行）整体替换为：

```python
@router.post(
    "/export",
    summary="导出结果（多格式，默认容错降级）",
    description="""导出编译结果为多种格式。任意格式无法产出时默认走降级：
先尝试替代格式，无替代或替代也失败则丢弃并返回其余成功格式。
响应 formats_status 逐格式说明 produced / substituted / dropped 及原因。

支持的输出格式：
- json / html / ppt / word / markdown / pdf（直接产出）
- pptx / xlsx（可请求，自动降级到可用替代格式）

未知格式名返回 400。可用 GET /bsc/exports/capabilities 预检依赖可用性。
""",
    response_description="导出结果，含逐格式状态表",
)
async def export_results(req: ExportRequest):
    """导出结果（多格式，默认容错降级）"""
    from app.core.bsc_pipeline import compile_to_business_system
    from exporters.orchestrator import run_export
    from exporters.degrade import VALID_OUTPUT_TYPES

    if req.business_system:
        bs = req.business_system
        result = {
            "business_system": bs,
            "summary": bs.get("report", {}).get("executive_summary", ""),
            "pipeline": {},
        }
    elif req.input:
        result = compile_to_business_system(req.input)
        bs = result["business_system"]
    else:
        return ApiResponse.error("请提供business_system或input参数", code=400)

    # 校验请求格式是否合法（未知格式名 → 400，不降级）
    unknown = [f for f in req.output_types if f not in VALID_OUTPUT_TYPES]
    if unknown:
        return ApiResponse.error(f"不支持的导出格式: {unknown}", code=400)

    # 保持原行为：始终尝试绑定 visuals
    output_types = list(req.output_types)
    if "visuals" not in output_types:
        output_types.append("visuals")

    outcome = run_export(bs, output_types, result)

    payload = {
        "exports": outcome.exports,
        "formats": list(outcome.exports.keys()),
        "formats_status": outcome.formats_status,
        "summary": result["summary"],
        "errors": outcome.errors,
    }

    any_produced = any(s["status"] in ("produced", "substituted") for s in outcome.formats_status)
    any_degraded = any(s["status"] in ("substituted", "dropped") for s in outcome.formats_status)

    if not any_produced:
        return ApiResponse.error("所有请求格式均无法产出", code=422).model_copy(
            update={"data": payload}
        )
    if any_degraded:
        return ApiResponse.partial(payload, message="部分格式经降级/替换处理", errors=outcome.errors)
    return ApiResponse.ok(payload)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export_degrade.py -k "test_export_" -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/api/bsc_api.py tests/test_export_degrade.py
git commit -m "refactor(api): export_results delegates to orchestrator with degrade + status table"
```

---

### Task 7: 全量回归

**Files:**
- Test: `tests/test_export_degrade.py`（已含全部新增用例）

- [ ] **Step 1: 运行全部新增测试**

Run: `python -m pytest tests/test_export_degrade.py -v`
Expected: PASS（约 23 例：5 degrade + 2 ctx + 4 html/ppt + 2 markdown + 5 orchestrator + 5 endpoint）

- [ ] **Step 2: 运行全量回归**

Run: `python -m pytest -q`
Expected: 全部通过（基线 76 passed, 2 skipped + 新增约 23 → 约 99 passed, 2 skipped；2 skipped = 真实 LLM e2e `test_real_e2e.py`）

- [ ] **Step 3: 提交（若上一步有修复则提交；否则跳过）**

若全量回归发现并修复了问题：

```bash
git add -A
git commit -m "fix: address regression from export degrade refactor"
```

若全量回归直接通过，无需提交，直接进入收尾。

---

## 自审结论（写计划时已对照 spec 检查）

- **spec 覆盖**：§3.1 规则/分类/实现集 → Task 1；§3.1 组件上下文 → Task 2；§3.1 html/ppt 迁入+ctx → Task 3；§3.1 markdown 接入 → Task 4；§3.1 编排器 → Task 5；§3.2 端点重构 → Task 6；§4 响应结构 → Task 5/6 的 `formats_status`；§5 HTTP 语义 → Task 6（200/207/422/400）；§6 xlsx 默认 unimplemented → Task 1（`xlsx: []`）；§7 测试 → Task 1–7。
- **占位符扫描**：无 TBD/TODO；每个代码步骤均含完整实现。
- **类型一致性**：`DEGRADATION_RULES` / `is_implemented` / `classify_failure` / `VALID_OUTPUT_TYPES` 在 Task 1 定义、后续 Task 复用，命名一致；`DegradeContext.component` 在 Task 2 定义、Task 3/4/5 复用；`ExportOutcome` / `run_export` / `_produce` 在 Task 5 定义、Task 6 端点调用，签名一致。
- **已知取舍**：xlsx 默认 `unimplemented`（spec §6）；零产出返回 422 且 `formats_status` 说明原因；`visuals` 始终追加产出（保持旧行为）；word/pdf 为整格式 all-or-nothing（spec 允许不强求组件级）。
