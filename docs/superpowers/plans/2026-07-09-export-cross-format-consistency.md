# 导出层 · 跨格式一致性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `CanonicalReport` 单一规范化模型，让 markdown / html（PDF 派生）/ ppt / word 四渲染器只消费它，从而跨格式字节级统一（段落集、顺序、等级/优先级标签）。

**Architecture:** 新增 `exporters/canonical.py` 产出 `CanonicalReport`；orchestrator 在 dispatch 前调一次 `normalize()` 并把 `CanonicalReport` 传给四个渲染器；四渲染器退化为纯模板，删除所有字段别名猜测。与「容错与降级」方向正交（`DegradeContext` 仍包裹组件）。

**Tech Stack:** Python 3.13 + pytest 9.1.1；`python-docx`（已装）、`reportlab`（已装，PDF 走此路径）；`weasyprint`/`pdfkit` 未装（PDF 自动回退 reportlab）。

---

## File Structure

- **Create** `exporters/canonical.py` — `CanonicalReport` 及全部 `_norm_*` 归一层（唯一真相源）。
- **Modify** `exporters/orchestrator.py` — `run_export` 调 `normalize()`，`_produce` 向四渲染器传 `CanonicalReport`（`json`/`visuals` 仍用原始 `bs`）。
- **Modify** `exporters/markdown_exporter.py` — `MarkdownExporter.export(self, report, ctx)` 消费 `CanonicalReport`；补 `metrics` 段；标签取自规范字段。
- **Modify** `exporters/html_exporter.py` — `generate_html(report, pipeline_info, ctx)` 消费 `CanonicalReport`；`PDFExporter.export` 委托它。PDF 自动跟随。
- **Modify** `exporters/ppt_spec_exporter.py` — `generate_ppt_spec(report, ctx)` 消费 `CanonicalReport`；补 `roles` 幻灯片；风险改用 `severity_label`。
- **Modify** `exporters/word_exporter.py` — `WordExporter.export(self, report)` 消费 `CanonicalReport`；统一标签词表。
- **Create** `tests/test_export_canonical.py` — 归一化单测 + 跨格式一致性集成测试。

> 依赖现状（已确认）：`docx=True`、`reportlab=True`、`weasyprint=False`、`pdfkit=False`。Word/PDF 可在测试环境真实渲染；PDF 经 reportlab 路径由 HTML 派生。

---

### Task 1: 规范化模型 `canonical.py`

**Files:**
- Create: `exporters/canonical.py`
- Test: `tests/test_export_canonical.py`

- [ ] **Step 1: 写失败的归一化测试**

```python
# tests/test_export_canonical.py
import pytest
from exporters.canonical import normalize, CanonicalReport


RAW_CANONICAL = {
    "business_domain": "内容安全平台",
    "generated_at": "2026-07-09",
    "report": {"executive_summary": "保障内容安全。"},
    "objectives": [{"objective": "内容安全", "target": "99%准确率", "priority": "high"}],
    "roles": [{"role": "审核员", "department": "运营", "level": "L2", "headcount": 10}],
    "workflow": [{"step": 1, "name": "接入", "action": "接收内容", "role": "网关"}],
    "metrics": [{"name": "准确率", "formula": "tp/(tp+fp)", "target": "99%"}],
    "risks": [{"risk": "误杀", "severity": "high", "mitigation": "人工复核", "impact": "体验"}],
    "strategy": {
        "recommendations": ["引入大模型"],
        "growth_opportunities": [{"opportunity": "出海", "potential": "高"}],
        "strategic_path": ["试点", "推广"],
    },
}


def test_normalize_basic_fields():
    r = normalize(RAW_CANONICAL)
    assert isinstance(r, CanonicalReport)
    assert r.title == "内容安全平台"
    assert r.executive_summary == "保障内容安全。"
    assert len(r.objectives) == 1
    assert len(r.roles) == 1
    assert len(r.workflow) == 1
    assert len(r.metrics) == 1
    assert len(r.risks) == 1
    assert r.strategy.recommendations == ["引入大模型"]
    assert r.strategy.growth_opportunities == [{"opportunity": "出海", "potential": "高"}]
    assert r.strategy.roadmap == ["试点", "推广"]


def test_normalize_field_aliases():
    # 旧别名：kpi / process_flow / risk(列表)
    legacy = {
        "business_domain": "X",
        "kpi": [{"name": "a", "formula": "f", "target": "t"}],
        "process_flow": [{"step": 1, "name": "s"}],
        "risk": [{"risk": "r", "level": "high"}],
    }
    r = normalize(legacy)
    assert len(r.metrics) == 1 and r.metrics[0].name == "a"
    assert len(r.workflow) == 1 and r.workflow[0].name == "s"
    assert len(r.risks) == 1 and r.risks[0].severity == "high"


def test_normalize_severity_variants():
    for raw in ["high", "高", "🔴", {"severity": "high"}, {"level": "high"}]:
        sev_src = raw if isinstance(raw, dict) else {"severity": raw}
        r = normalize({"risks": [{"risk": "x", **sev_src}]})
        assert r.risks[0].severity == "high", f"raw={raw}"
        assert r.risks[0].severity_label == "🔴 高风险"


def test_normalize_missing_section_safe():
    r = normalize({"business_domain": "X"})  # 无任何段落
    assert r.objectives == [] and r.risks == [] and r.metrics == []
    assert r.strategy.recommendations == []
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: FAIL（`ModuleNotFoundError: exporters.canonical`）。

- [ ] **Step 3: 写最小实现 `exporters/canonical.py`**

```python
"""导出层单一规范化模型：所有渲染器只消费 CanonicalReport。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

SEVERITY_LABELS = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}
PRIORITY_LABELS = {"high": "🔴", "medium": "🟡", "low": "🟢"}

_SEV_MAP = {
    "high": "high", "h": "high", "高": "high", "🔴": "high", "high risk": "high",
    "medium": "medium", "m": "medium", "中": "medium", "🟡": "medium", "medium risk": "medium",
    "low": "low", "l": "low", "低": "low", "🟢": "low", "low risk": "low",
}


@dataclass
class CanonicalObjective:
    objective: str = ""
    target: str = ""
    priority: str = "medium"
    priority_label: str = PRIORITY_LABELS["medium"]


@dataclass
class CanonicalRole:
    role: str = ""
    department: str = ""
    level: str = ""
    headcount: str = ""


@dataclass
class CanonicalStep:
    step: object = ""
    name: str = ""
    action: str = ""
    role: str = ""


@dataclass
class CanonicalMetric:
    name: str = ""
    formula: str = ""
    target: str = ""


@dataclass
class CanonicalRisk:
    risk: str = ""
    severity: str = "medium"
    severity_label: str = SEVERITY_LABELS["medium"]
    mitigation: str = ""
    impact: str = ""
    category: Optional[str] = None


@dataclass
class CanonicalStrategy:
    recommendations: List[str] = field(default_factory=list)
    growth_opportunities: List[dict] = field(default_factory=list)
    roadmap: List[str] = field(default_factory=list)


@dataclass
class CanonicalReport:
    title: str = ""
    executive_summary: str = ""
    generated_at: str = ""
    objectives: List[CanonicalObjective] = field(default_factory=list)
    roles: List[CanonicalRole] = field(default_factory=list)
    workflow: List[CanonicalStep] = field(default_factory=list)
    metrics: List[CanonicalMetric] = field(default_factory=list)
    risks: List[CanonicalRisk] = field(default_factory=list)
    strategy: CanonicalStrategy = field(default_factory=CanonicalStrategy)


def _norm_level(raw) -> str:
    if raw is None:
        return "medium"
    return _SEV_MAP.get(str(raw).strip().lower(), "medium")


def _norm_severity(raw) -> tuple:
    sev = _norm_level(raw)
    return sev, SEVERITY_LABELS[sev]


def _norm_risks(bs: dict) -> List[CanonicalRisk]:
    risks = bs.get("risks") or []
    out = []
    if risks:
        for r in risks:
            if not isinstance(r, dict):
                continue
            sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
            out.append(CanonicalRisk(
                risk=str(r.get("risk", r.get("description", r.get("name", "")))),
                severity=sev, severity_label=label,
                mitigation=str(r.get("mitigation", r.get("response", r.get("action", "")))),
                impact=str(r.get("impact", r.get("consequence", ""))),
                category=r.get("category"),
            ))
        return out
    nested = bs.get("risk", {})
    if isinstance(nested, dict):
        for cat, items in nested.items():
            if not isinstance(items, list):
                continue
            cat_name = cat.replace("_risks", "").replace("_", " ")
            for r in items:
                if not isinstance(r, dict):
                    continue
                sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
                out.append(CanonicalRisk(
                    risk=str(r.get("risk", r.get("description", r.get("name", "")))),
                    severity=sev, severity_label=label,
                    mitigation=str(r.get("mitigation", "")),
                    impact=str(r.get("impact", "")),
                    category=cat_name,
                ))
    return out


def _norm_metrics(bs: dict) -> List[CanonicalMetric]:
    raw = bs.get("metrics") or bs.get("kpi") or bs.get("success_metrics") or []
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        out.append(CanonicalMetric(
            name=str(m.get("name", m.get("kpi", ""))),
            formula=str(m.get("formula", m.get("expression", ""))),
            target=str(m.get("target", m.get("goal", ""))),
        ))
    return out


def _norm_workflow(bs: dict) -> List[CanonicalStep]:
    raw = bs.get("workflow") or bs.get("process_flow") or bs.get("sop") or []
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            continue
        out.append(CanonicalStep(
            step=s.get("step", i),
            name=str(s.get("name", "")),
            action=str(s.get("action", "")),
            role=str(s.get("role", "")),
        ))
    return out


def _norm_objectives(bs: dict) -> List[CanonicalObjective]:
    raw = bs.get("objectives") or bs.get("core_objectives") or []
    out = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        sev, label = _norm_severity(o.get("priority", "medium"))
        out.append(CanonicalObjective(
            objective=str(o.get("objective", "")),
            target=str(o.get("target", "")),
            priority=sev, priority_label=label,
        ))
    return out


def _norm_roles(bs: dict) -> List[CanonicalRole]:
    raw = bs.get("roles") or (bs.get("sop", {}) or {}).get("roles") or []
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        out.append(CanonicalRole(
            role=str(r.get("role", "")),
            department=str(r.get("department", "")),
            level=str(r.get("level", "")),
            headcount=str(r.get("headcount", "")),
        ))
    return out


def _norm_strategy(bs: dict) -> CanonicalStrategy:
    raw = bs.get("strategy") or {}
    if not isinstance(raw, dict):
        raw = {}
    recs = raw.get("recommendations") or []
    growth = raw.get("growth_opportunities") or []
    roadmap = raw.get("strategic_path") or raw.get("milestones") or []
    return CanonicalStrategy(
        recommendations=[str(x) for x in recs],
        growth_opportunities=[
            {"opportunity": str(g.get("opportunity", "")), "potential": str(g.get("potential", ""))}
            for g in growth if isinstance(g, dict)
        ],
        roadmap=[str(x) for x in roadmap],
    )


def normalize(business_system: dict) -> CanonicalReport:
    bs = business_system or {}
    report = bs.get("report")
    exec_sum = ""
    if isinstance(report, dict):
        exec_sum = str(report.get("executive_summary", ""))
    return CanonicalReport(
        title=str(bs.get("business_domain", bs.get("objective", "业务系统分析报告"))),
        executive_summary=exec_sum,
        generated_at=str(bs.get("generated_at", "")),
        objectives=_norm_objectives(bs),
        roles=_norm_roles(bs),
        workflow=_norm_workflow(bs),
        metrics=_norm_metrics(bs),
        risks=_norm_risks(bs),
        strategy=_norm_strategy(bs),
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS（4 个测试）。

- [ ] **Step 5: 提交**

```bash
git add exporters/canonical.py tests/test_export_canonical.py
git commit -m "feat(exporters): add CanonicalReport normalize layer"
```

---

### Task 2: Markdown 渲染器改造

**Files:**
- Modify: `exporters/markdown_exporter.py`
- Test: `tests/test_export_canonical.py`（追加）

- [ ] **Step 1: 写失败测试（markdown 消费 CanonicalReport，含 metrics 段与规范标签）**

```python
from exporters.canonical import normalize
from exporters.markdown_exporter import MarkdownExporter


def test_markdown_consumes_canonical_and_includes_metrics():
    r = normalize(RAW_CANONICAL)
    md = MarkdownExporter().export(r, None)
    assert "## 一、业务目标" in md
    assert "## 二、角色定义" in md
    assert "## 三、业务流程" in md
    assert "## 四、关键指标" in md          # 之前缺失，现在必须出现
    assert "## 五、风险分析" in md
    assert "## 六、战略建议" in md
    assert "🔴 高风险" in md                  # 规范标签，字节级统一
    assert "准确率" in md                     # metrics 内容
```

- [ ] **Step 2: 运行，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py::test_markdown_consumes_canonical_and_includes_metrics -v
```
Expected: FAIL（当前 `export` 读 `business_system` 字典、无 metrics 段、用 🔴🟡🟢 硬编码）。

- [ ] **Step 3: 改写 `MarkdownExporter.export`**

把 `exporters/markdown_exporter.py` 的 `export` 方法替换为：

```python
    def export(self, report, ctx=None) -> str:
        """导出为 Markdown。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
        from exporters.canonical import CanonicalReport
        if not isinstance(report, CanonicalReport):
            # 兼容：允许直接传原始 dict（极少数调用方）
            report = normalize(report)
        lines = []

        def _block(name, render):
            if ctx is None:
                render()
            else:
                with ctx.component(name):
                    render()

        lines.append(f"# {report.title}")
        lines.append("")
        if report.executive_summary:
            lines.append(f"> {report.executive_summary}")
            lines.append("")

        def _objectives():
            lines.append("## 一、业务目标")
            if report.objectives:
                for o in report.objectives:
                    line = f"{o.priority_label} **{o.objective}**"
                    if o.target:
                        line += f" - 目标: {o.target}"
                    lines.append(line)
            else:
                lines.append("暂无业务目标")
            lines.append("")

        def _roles():
            lines.append("## 二、角色定义")
            if report.roles:
                lines.append("| 角色名称 | 所属部门 | 级别 | 人数 |")
                lines.append("|----------|----------|------|------|")
                for r in report.roles:
                    lines.append(f"| {r.role} | {r.department} | {r.level} | {r.headcount} |")
            else:
                lines.append("暂无角色定义")
            lines.append("")

        def _workflow():
            lines.append("## 三、业务流程")
            if report.workflow:
                for s in report.workflow:
                    lines.append(f"{s.step}. **{s.name}**")
                    if s.action:
                        lines.append(f"   - 动作: {s.action}")
                    if s.role:
                        lines.append(f"   - 负责角色: {s.role}")
                    lines.append("")
            else:
                lines.append("暂无业务流程")
            lines.append("")

        def _metrics():
            lines.append("## 四、关键指标")
            if report.metrics:
                for m in report.metrics:
                    line = f"- **{m.name}**"
                    if m.formula:
                        line += f"（公式: {m.formula}）"
                    if m.target:
                        line += f" 目标: {m.target}"
                    lines.append(line)
            else:
                lines.append("暂无关键指标")
            lines.append("")

            def _risks():
                lines.append("## 五、风险分析")
                if report.risks:
                    for rk in report.risks:
                        lines.append(f"### {rk.severity_label}: {rk.risk}")
                        if rk.mitigation:
                            lines.append(f"- **应对措施**: {rk.mitigation}")
                        if rk.impact:
                            lines.append(f"- **影响**: {rk.impact}")
                        lines.append("")
                else:
                    lines.append("暂无风险分析")
                lines.append("")

        def _strategy():
            lines.append("## 六、战略建议")
            if report.strategy.recommendations:
                for i, rec in enumerate(report.strategy.recommendations, 1):
                    lines.append(f"{i}. {rec}")
            if report.strategy.growth_opportunities:
                lines.append("**增长机会**")
                for g in report.strategy.growth_opportunities:
                    lines.append(f"- {g['opportunity']}: {g['potential']}")
            if report.strategy.roadmap:
                lines.append("**实施路线**")
                for step in report.strategy.roadmap:
                    lines.append(f"- {step}")
            if not (report.strategy.recommendations or report.strategy.growth_opportunities or report.strategy.roadmap):
                lines.append("暂无战略建议")
            lines.append("")

        _block("objectives", _objectives)
        _block("roles", _roles)
        _block("workflow", _workflow)
        _block("metrics", _metrics)
        _block("risks", _risks)
        _block("strategy", _strategy)
        return "\n".join(lines)
```

> 注意：原文件 import 行 `from typing import Dict, Any` 与顶部 `logger` 保留不动，只替换 `export` 方法体与类签名（`class MarkdownExporter:` 不变，签名改为 `def export(self, report, ctx=None) -> str:`）。

- [ ] **Step 4: 运行，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add exporters/markdown_exporter.py tests/test_export_canonical.py
git commit -m "feat(exporters): markdown consumes CanonicalReport + metrics section"
```

---

### Task 3: HTML 渲染器改造（PDF 委托跟随）

**Files:**
- Modify: `exporters/html_exporter.py`（`generate_html` 函数 + `PDFExporter.export`/`_export_with_reportlab`）
- Test: `tests/test_export_canonical.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
from exporters.html_exporter import generate_html


def test_html_consumes_canonical_and_uniform_labels():
    r = normalize(RAW_CANONICAL)
    html = generate_html(r, {}, None)
    assert "内容安全平台" in html
    for marker in ["业务目标", "角色定义", "业务流程", "关键指标", "风险分析", "战略建议"]:
        assert marker in html, marker
    assert "🔴 高风险" in html
    assert "准确率" in html
```

- [ ] **Step 2: 运行，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py::test_html_consumes_canonical_and_uniform_labels -v
```
Expected: FAIL（`generate_html` 当前读 `bs.get("x")` 且不含 roles/统一标签）。

- [ ] **Step 3: 替换 `generate_html` 为消费 `CanonicalReport` 的版本**

在 `exporters/html_exporter.py` 中，定位模块级 `def generate_html(business_system, pipeline_info, ctx=None):`（即 Task 3「容错与降级」迁入的那个函数），整体替换为：

```python
def generate_html(report, pipeline_info=None, ctx=None) -> str:
    """生成 HTML 报告。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
    from exporters.canonical import CanonicalReport, normalize
    if not isinstance(report, CanonicalReport):
        report = normalize(report)
    import html as _html

    def _esc(s):
        return _html.escape(str(s))

    parts = [f"<h1>{_esc(report.title)}</h1>"]
    if report.executive_summary:
        parts.append(f"<p class='summary'>{_esc(report.executive_summary)}</p>")
    parts.append("<hr/>")

    def _block(name, build):
        if ctx is None:
            build()
        else:
            with ctx.component(name):
                build()

    def _objectives():
        items = "".join(
            f"<li>{o.priority_label} <b>{_esc(o.objective)}</b>"
            + (f" - 目标: {_esc(o.target)}" if o.target else "") + "</li>"
            for o in report.objectives
        )
        parts.append(f"<h2>一、业务目标</h2><ul>{items or '<li>暂无业务目标</li>'}</ul>")

    def _roles():
        rows = "".join(
            f"<tr><td>{_esc(r.role)}</td><td>{_esc(r.department)}</td>"
            f"<td>{_esc(r.level)}</td><td>{_esc(r.headcount)}</td></tr>"
            for r in report.roles
        )
        head = "<tr><th>角色</th><th>部门</th><th>级别</th><th>人数</th></tr>"
        parts.append(f"<h2>二、角色定义</h2><table>{head}{rows or ''}</table>")

    def _workflow():
        items = "".join(
            f"<li><b>{_esc(s.name)}</b>"
            + (f" - 动作: {_esc(s.action)}" if s.action else "")
            + (f" - 角色: {_esc(s.role)}" if s.role else "") + "</li>"
            for s in report.workflow
        )
        parts.append(f"<h2>三、业务流程</h2><ul>{items or '<li>暂无业务流程</li>'}</ul>")

    def _metrics():
        rows = "".join(
            f"<tr><td>{_esc(m.name)}</td><td>{_esc(m.formula)}</td><td>{_esc(m.target)}</td></tr>"
            for m in report.metrics
        )
        head = "<tr><th>指标</th><th>公式</th><th>目标</th></tr>"
        parts.append(f"<h2>四、关键指标</h2><table>{head}{rows or ''}</table>")

    def _risks():
        items = "".join(
            f"<li><b>{_esc(rk.severity_label)}</b>: {_esc(rk.risk)}"
            + (f" - 应对: {_esc(rk.mitigation)}" if rk.mitigation else "")
            + (f" - 影响: {_esc(rk.impact)}" if rk.impact else "") + "</li>"
            for rk in report.risks
        )
        parts.append(f"<h2>五、风险分析</h2><ul>{items or '<li>暂无风险分析</li>'}</ul>")

    def _strategy():
        items = ""
        for rec in report.strategy.recommendations:
            items += f"<li>{_esc(rec)}</li>"
        for g in report.strategy.growth_opportunities:
            items += f"<li>{_esc(g['opportunity'])}: {_esc(g['potential'])}</li>"
        for step in report.strategy.roadmap:
            items += f"<li>{_esc(step)}</li>"
        parts.append(f"<h2>六、战略建议</h2><ul>{items or '<li>暂无战略建议</li>'}</ul>")

    _block("objectives", _objectives)
    _block("roles", _roles)
    _block("workflow", _workflow)
    _block("metrics", _metrics)
    _block("risks", _risks)
    _block("strategy", _strategy)
    return "\n".join(parts)
```

同时把 `PDFExporter` 改为委托 `generate_html`：将 `PDFExporter.export(self, business_system)` 的签名改为 `export(self, report)`，并在 reportlab 分支里用 `generate_html(report, {}, None)` 生成 HTML 再转 PDF。最小改动示例（替换 `export` 与 `_export_with_reportlab` 签名）：

```python
    def export(self, report: "CanonicalReport") -> bytes:
        """导出为 PDF（reportlab 路径）。report 为 CanonicalReport。"""
        if not self._reportlab_available:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("pdf", "reportlab", "pip install reportlab")
        return self._export_with_reportlab(report)

    def _export_with_reportlab(self, report) -> bytes:
        from exporters.html_exporter import generate_html
        html_content = generate_html(report, {}, None)
        # ... 原有 reportlab 渲染逻辑保持不变，仅用 html_content 替代自构建 ...
```

> 若 `PDFExporter` 内部有独立的 `_generate_html_content`，将其改为直接 `return generate_html(report, {}, None)`；其余 reportlab/styles 代码原样保留。

- [ ] **Step 4: 运行，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add exporters/html_exporter.py tests/test_export_canonical.py
git commit -m "feat(exporters): html consumes CanonicalReport; pdf delegates"
```

---

### Task 4: PPT 渲染器改造（补 roles、修 severity）

**Files:**
- Modify: `exporters/ppt_spec_exporter.py`
- Test: `tests/test_export_canonical.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
from exporters.ppt_spec_exporter import generate_ppt_spec


def test_ppt_includes_roles_and_uniform_severity():
    r = normalize(RAW_CANONICAL)
    spec = generate_ppt_spec(r, None)
    titles = [s["title"] for s in spec["slides"]]
    assert "角色定义" in titles          # 之前缺失
    risk_slide = next(s for s in spec["slides"] if s["title"] == "风险分析")
    assert any("🔴 高风险" in it for it in risk_slide["items"])
```

- [ ] **Step 2: 运行，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py::test_ppt_includes_roles_and_uniform_severity -v
```
Expected: FAIL（当前无 roles 幻灯片、风险读 `severity` 旧字段）。

- [ ] **Step 3: 替换 `generate_ppt_spec`**

把 `exporters/ppt_spec_exporter.py` 的 `generate_ppt_spec(business_system, ctx=None)` 整体替换为：

```python
def generate_ppt_spec(report, ctx=None) -> dict:
    """生成 PPT 规格（JSON）。report 为 CanonicalReport；ctx 非空时单区块失败被跳过。"""
    from exporters.canonical import CanonicalReport, normalize
    if not isinstance(report, CanonicalReport):
        report = normalize(report)
    slides = []

    def _block(name, build):
        if ctx is None:
            build()
        else:
            with ctx.component(name):
                build()

    def _title():
        slides.append({"slide_type": "title", "title": report.title,
                       "subtitle": "基于PRD的业务系统分析报告"})

    def _objectives():
        if report.objectives:
            slides.append({"slide_type": "list", "title": "业务目标",
                           "items": [f"{o.priority_label} {o.objective}: {o.target}" for o in report.objectives]})

    def _roles():
        if report.roles:
            slides.append({"slide_type": "table", "title": "角色定义",
                           "headers": ["角色", "部门", "级别", "人数"],
                           "data": [[r.role, r.department, r.level, r.headcount] for r in report.roles]})

    def _workflow():
        if report.workflow:
            slides.append({"slide_type": "flow", "title": "流程设计",
                           "steps": [s.name for s in report.workflow]})

    def _metrics():
        if report.metrics:
            slides.append({"slide_type": "table", "title": "关键指标",
                           "headers": ["指标", "公式", "目标"],
                           "data": [[m.name, m.formula, m.target] for m in report.metrics]})

    def _risks():
        if report.risks:
            slides.append({"slide_type": "list", "title": "风险分析",
                           "items": [f"{rk.severity_label}: {rk.risk}" for rk in report.risks[:5]]})

    def _strategy():
        items = list(report.strategy.recommendations)
        items += [f"{g['opportunity']}: {g['potential']}" for g in report.strategy.growth_opportunities]
        items += list(report.strategy.roadmap)
        if items:
            slides.append({"slide_type": "list", "title": "战略建议", "items": items})

    def _report():
        if report.executive_summary:
            slides.append({"slide_type": "content", "title": "执行摘要", "content": report.executive_summary})

    _block("title", _title)
    _block("objectives", _objectives)
    _block("roles", _roles)
    _block("workflow", _workflow)
    _block("metrics", _metrics)
    _block("risks", _risks)
    _block("strategy", _strategy)
    _block("report", _report)
    return {"slides": slides, "theme": "dark", "slide_count": len(slides)}
```

- [ ] **Step 4: 运行，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add exporters/ppt_spec_exporter.py tests/test_export_canonical.py
git commit -m "feat(exporters): ppt consumes CanonicalReport + roles slide"
```

---

### Task 5: Word 渲染器改造（统一标签）

**Files:**
- Modify: `exporters/word_exporter.py`
- Test: `tests/test_export_canonical.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
from exporters.word_exporter import WordExporter


def test_word_consumes_canonical_and_uniform_labels():
    pytest.importorskip("docx")  # 环境已装，仍守卫
    r = normalize(RAW_CANONICAL)
    data = WordExporter().export(r)
    assert isinstance(data, bytes)
    text = data.decode("utf-8", "ignore")
    assert "内容安全平台" in text
    assert "🔴 高风险" in text        # 替换原【高】【中】【低】
    assert "准确率" in text
```

- [ ] **Step 2: 运行，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py::test_word_consumes_canonical_and_uniform_labels -v
```
Expected: FAIL（当前 `export` 读 dict、风险用 【高】）。

- [ ] **Step 3: 改写 `WordExporter.export`**

把 `WordExporter.export(self, business_system)` 改为消费 `CanonicalReport`（保留 docx 可用性探测与 `ExportDependencyError` 兜底；仅替换渲染主体）：

```python
    def export(self, report) -> bytes:
        """导出为 Word 文档。report 为 CanonicalReport。"""
        if not self._docx_available:
            from exporters.errors import ExportDependencyError
            raise ExportDependencyError("word", "python-docx", "pip install python-docx")
        from exporters.canonical import CanonicalReport, normalize
        if not isinstance(report, CanonicalReport):
            report = normalize(report)

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

        title_para = doc.add_heading(report.title, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if report.executive_summary:
            doc.add_paragraph(report.executive_summary, style='Intense Quote')

        doc.add_heading('一、业务目标', level=1)
        if report.objectives:
            for o in report.objectives:
                p = doc.add_paragraph(f"{o.priority_label}{o.objective}")
                if o.target:
                    p.add_run(f" - 目标: {o.target}")
        else:
            doc.add_paragraph("暂无业务目标")

        doc.add_heading('二、角色定义', level=1)
        if report.roles:
            table = doc.add_table(rows=1, cols=4)
            hdr = table.rows[0].cells
            for i, h in enumerate(['角色名称', '所属部门', '级别', '人数']):
                hdr[i].text = h
            for r in report.roles:
                c = table.add_row().cells
                c[0].text = r.role
                c[1].text = r.department
                c[2].text = r.level
                c[3].text = str(r.headcount)
        else:
            doc.add_paragraph("暂无角色定义")

        doc.add_heading('三、业务流程', level=1)
        if report.workflow:
            for s in report.workflow:
                p = doc.add_paragraph(f"{s.step}. {s.name}")
                if s.action:
                    p.add_run(f" - 动作: {s.action}")
                if s.role:
                    p.add_run(f" - 负责角色: {s.role}")
        else:
            doc.add_paragraph("暂无业务流程")

        doc.add_heading('四、关键指标', level=1)
        if report.metrics:
            for m in report.metrics:
                line = m.name
                if m.formula:
                    line += f"（公式: {m.formula}）"
                if m.target:
                    line += f" 目标: {m.target}"
                doc.add_paragraph(line)
        else:
            doc.add_paragraph("暂无关键指标")

        doc.add_heading('五、风险分析', level=1)
        if report.risks:
            for rk in report.risks:
                p = doc.add_paragraph(f"{rk.severity_label}: {rk.risk}")
                if rk.mitigation:
                    p.add_run(f" - 应对: {rk.mitigation}")
                if rk.impact:
                    p.add_run(f" - 影响: {rk.impact}")
        else:
            doc.add_paragraph("暂无风险分析")

        doc.add_heading('六、战略建议', level=1)
        for rec in report.strategy.recommendations:
            doc.add_paragraph(rec, style='List Number')
        for g in report.strategy.growth_opportunities:
            doc.add_paragraph(f"{g['opportunity']}: {g['potential']}")
        for step in report.strategy.roadmap:
            doc.add_paragraph(step, style='List Bullet')

        return doc2bytes(doc)
```

并在文件底部新增辅助函数（避免重复 import 逻辑）：

```python
def doc2bytes(doc) -> bytes:
    import io
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: 运行，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add exporters/word_exporter.py tests/test_export_canonical.py
git commit -m "feat(exporters): word consumes CanonicalReport + uniform labels"
```

---

### Task 6: Orchestrator 接线（normalize → 传 CanonicalReport）

**Files:**
- Modify: `exporters/orchestrator.py`
- Test: `tests/test_export_canonical.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
from exporters.orchestrator import run_export


def test_run_export_uses_canonical_end_to_end():
    outcome = run_export(RAW_CANONICAL, ["markdown", "html", "ppt", "word"], {})
    assert "markdown" in outcome.exports
    assert "html" in outcome.exports
    assert "ppt" in outcome.exports
    assert "word" in outcome.exports
    # 逐格式状态均为 produced（无 dropped）
    assert all(s["status"] == "produced" for s in outcome.formats_status)
    # 跨格式字节级标签一致
    md = outcome.exports["markdown"]
    html = outcome.exports["html"]
    ppt_items = [it for s in outcome.exports["ppt"]["slides"] for it in s.get("items", [])]
    assert "🔴 高风险" in md and "🔴 高风险" in html
    assert any("🔴 高风险" in it for it in ppt_items)
```

- [ ] **Step 2: 运行，确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py::test_run_export_uses_canonical_end_to_end -v
```
Expected: FAIL（`_produce` 仍向渲染器传原始 `bs`）。

- [ ] **Step 3: 修改 `orchestrator.py`**

在 `exporters/orchestrator.py` 顶部 import 增加：

```python
from exporters.canonical import normalize
```

把 `_produce` 签名改为 `def _produce(fmt, bs, canonical, result, ctx):`，并将四渲染器分支改为传 `canonical`（json/visuals 仍用 `bs`）：

```python
def _produce(fmt, bs, canonical, result, ctx):
    """产出单个格式。成功返回产出物；失败抛异常。"""
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
        return {"content_base64": WordExporter().export(canonical).hex(),
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
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
```

在 `run_export` 内、循环之前加一行 `canonical = normalize(bs)`，并把循环里的 `_produce(cand, bs, result, ctx)` 改为 `_produce(cand, bs, canonical, result, ctx)`。

- [ ] **Step 4: 运行，确认通过（含既有降级测试不回归）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py tests/test_export_degrade.py -v
```
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add exporters/orchestrator.py tests/test_export_canonical.py
git commit -m "refactor(orchestrator): normalize once, dispatch CanonicalReport"
```

---

### Task 7: 跨格式一致性集成测试（守护回归）

**Files:**
- Test: `tests/test_export_canonical.py`（追加最终集成用例）

- [ ] **Step 1: 写集成测试**

```python
def _render_all(bs):
    r = normalize(bs)
    from exporters.markdown_exporter import MarkdownExporter
    from exporters.html_exporter import generate_html
    from exporters.ppt_spec_exporter import generate_ppt_spec
    from exporters.word_exporter import WordExporter
    md = MarkdownExporter().export(r, None)
    html = generate_html(r, {}, None)
    ppt = generate_ppt_spec(r, None)
    word = WordExporter().export(r).decode("utf-8", "ignore")
    return md, html, ppt, word


def test_renderers_same_sections():
    md, html, ppt, word = _render_all(RAW_CANONICAL)
    section_markers = ["业务目标", "角色定义", "业务流程", "关键指标", "风险分析", "战略建议"]
    for m in section_markers:
        assert m in md and m in html and m in word, f"markdown/html/word 缺 {m}"
    ppt_titles = [s["title"] for s in ppt["slides"]]
    for m in section_markers:
        assert m in ppt_titles, f"ppt 缺 {m}"


def test_renderers_same_field_values():
    md, html, ppt, word = _render_all(RAW_CANONICAL)
    ppt_items = [it for s in ppt["slides"] for it in s.get("items", [])]
    for label in ["🔴 高风险"]:  # 字节级统一标签
        assert label in md and label in html and label in word
        assert any(label in it for it in ppt_items)


def test_canonical_order():
    md, _, _, _ = _render_all(RAW_CANONICAL)
    idx = {m: md.index(f"## {i}、{m}") for i, m in enumerate(
        ["业务目标", "角色定义", "业务流程", "关键指标", "风险分析", "战略建议"], 1)}
    assert idx["业务目标"] < idx["角色定义"] < idx["业务流程"] < idx["关键指标"] < idx["风险分析"] < idx["战略建议"]


def test_missing_section_safe():
    bs = {"business_domain": "X", "objectives": [{"objective": "o", "priority": "high"}]}
    md, html, ppt, word = _render_all(bs)
    assert "业务目标" in md and "暂无关键指标" in md
    assert "关键指标" in html  # 段落标题仍在，仅内容为空
    assert any(s["title"] == "关键指标" for s in ppt["slides"])
```

- [ ] **Step 2: 运行，确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_canonical.py -v
```
Expected: PASS（全部用例绿）。

- [ ] **Step 3: 全量回归**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: 在「容错与降级」基线（99 passed / 2 skipped）之上新增用例全绿，无回归。

- [ ] **Step 4: 提交**

```bash
git add tests/test_export_canonical.py
git commit -m "test(exporters): cross-format consistency integration guard"
```

---

## Self-Review Checklist

1. **Spec coverage**: 规范模型（§5）→ Task 1；四渲染器（§6）→ Tasks 2–5；orchestrator 接线（§4/§7）→ Task 6；一致性测试（§9）→ Tasks 1&7；段落顺序（§5）→ `test_canonical_order`；字节级标签（§5）→ `test_renderers_same_field_values`；缺失安全（§8）→ `test_normalize_missing_section_safe` / `test_missing_section_safe`。覆盖完整。
2. **Placeholder scan**: 无 TBD/TODO；每步均含完整代码或精确命令；PDF 改动给出最小示例并指明"其余 reportlab 逻辑原样保留"，非占位。
3. **Type consistency**: `CanonicalReport` / `CanonicalRisk.severity_label` / `CanonicalStrategy.recommendations|growth_opportunities|roadmap` 在 Task 1 定义，Tasks 2–7 均一致引用；`_produce(fmt, bs, canonical, result, ctx)` 签名在 Task 6 统一，调用处同步更新。
