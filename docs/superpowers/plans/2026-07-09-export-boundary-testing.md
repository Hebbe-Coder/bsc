# 导出层「边界与测试」实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让导出层对极端/非法输入（超长文本、超大列表、特殊字符、HTML 注入、控制字符、BOM/代理对、缺字段、类型错、`None`、全空、嵌套异常）做到"不崩溃 + 输出有界 + 转义正确"，并用一份边界测试矩阵守护不回归。

**Architecture:** 新增独立 `exporters/boundary.py` 纯函数库（定界：`truncate_text`/`cap_list`/`coerce_str`/`strip_control`/`normalize_text` + 转义：`escape_html`）。`canonical.normalize()` 在构造 `CanonicalReport` 时调用定界函数，使四渲染器零改动即获得有界、类型安全、编码干净的数据；超列表封顶时追加一条"其余 X 条已省略"的合成条目，渲染器无需感知。HTML 渲染复用 `boundary.escape_html`（现有 `_esc` 已做转义，本次收敛为单一来源）防注入。整体沿用既有 `degrade` 层（基础设施失败）与一致性方向（单一规范模型）。

**Tech Stack:** Python 3.13、pytest 9.x、现有 `exporters` 模块（canonical / html_exporter / markdown_exporter / word_exporter / ppt_spec_exporter / orchestrator）。

> 约定：所有边界函数**永不抛异常**，不可强制的值产出安全占位（`—` / `?`）。封顶阈值常量集中在 `boundary.py` 顶部，便于调参。

---

## 文件结构

- **Create `exporters/boundary.py`** — 纯函数库：常量 + 定界/转义函数，无副作用、易单测。
- **Create `tests/test_boundary.py`** — T1 单元测试，逐函数覆盖。
- **Modify `exporters/canonical.py`** — 顶部 `import` boundary；`_norm_*` 构造字段时调 `truncate_text`/`cap_list`；`normalize()` 对 title/summary 定界。
- **Modify `exporters/html_exporter.py`** — `generate_html` 的 `_esc` 改为委托 `boundary.escape_html`（DRY，行为不变）。
- **Create `tests/test_export_boundary.py`** — T2 的 normalize 级边界测试 + T4 的 12 例跨渲染器矩阵（同一文件，T4 追加）。
- **运行** 全量回归：`pytest -q`（T5）。

---

### Task 1: 新增 `exporters/boundary.py` 纯函数库

**Files:**
- Create: `exporters/boundary.py`
- Test: `tests/test_boundary.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_boundary.py
import pytest
from exporters.boundary import (
    MAX_TEXT_LEN, MAX_LIST_ITEMS, coerce_str, strip_control,
    truncate_text, cap_list, normalize_text, escape_html,
)


def test_coerce_str_none_becomes_placeholder():
    assert coerce_str(None) == "—"


def test_coerce_str_int_becomes_str():
    assert coerce_str(123) == "123"


def test_coerce_str_bytes_decoded():
    assert coerce_str(b"hello") == "hello"


def test_strip_control_removes_invisible():
    s = "a\x00b\rc\x1fd\t\nez"
    assert strip_control(s) == "abcz"   # \x00 \r \x1f 删除；\n \t 保留


def test_strip_control_removes_bom():
    assert strip_control("\ufeffx") == "x"


def test_truncate_text_short_unchanged():
    assert truncate_text("hello") == "hello"


def test_truncate_text_long_gets_marker():
    long = "x" * (MAX_TEXT_LEN + 50)
    out = truncate_text(long)
    assert out.startswith("x" * MAX_TEXT_LEN)
    assert "已截断" in out
    assert "已截断，原文" in out


def test_truncate_text_none_coerced():
    assert truncate_text(None) == "—"


def test_cap_list_under_limit_unchanged():
    items = list(range(10))
    capped, omitted = cap_list(items)
    assert capped == items and omitted == 0


def test_cap_list_over_limit_capped_with_count():
    items = list(range(MAX_LIST_ITEMS + 25))
    capped, omitted = cap_list(items)
    assert len(capped) == MAX_LIST_ITEMS
    assert omitted == 25


def test_normalize_text_decodes_bytes_and_strips():
    assert normalize_text(b"\x00abc") == "abc"


def test_escape_html_quotes_angle_brackets():
    out = escape_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_escape_html_preserves_text():
    assert escape_html("正常 文本") == "正常 文本"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_boundary.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'exporters.boundary'`）

- [ ] **Step 3: 写最小实现**

```python
# exporters/boundary.py
"""导出层边界纯函数库：定界（有界/类型安全/编码干净）+ HTML 转义。
所有函数永不抛异常；不可强制的值产出安全占位。"""
from __future__ import annotations

import html as _html
from typing import Any, List, Tuple

MAX_TEXT_LEN = 2000
MAX_LIST_ITEMS = 200
PLACEHOLDER_NONE = "—"


def _decode_bytes(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("utf-8", "replace")


def coerce_str(v: Any) -> str:
    """任意值安全转 str：None→占位符，bytes→UTF-8 解码，其余 str()。"""
    if v is None:
        return PLACEHOLDER_NONE
    if isinstance(v, bytes):
        return _decode_bytes(v)
    return str(v)


def strip_control(s: Any) -> str:
    """删控制字符（\\x00-\\x1f 除 \\n \\t），去 BOM；非 str 先 coerce。"""
    s = coerce_str(s)
    s = s.replace("\ufeff", "")
    return "".join(
        ch for ch in s
        if not (ord(ch) <= 0x1f and ch not in ("\n", "\t"))
    )


def truncate_text(s: Any, max_len: int = MAX_TEXT_LEN) -> str:
    """定界文本：coerce + 去控制字符，超阈值截断并加标记。"""
    s = strip_control(s)
    n = len(s)
    if n > max_len:
        return s[:max_len] + f"…（已截断，原文 {n} 字）"
    return s


def cap_list(items: List[Any], max_items: int = MAX_LIST_ITEMS) -> Tuple[List[Any], int]:
    """定界列表：超过阈值取前 N 条，返回 (capped, omitted_count)。"""
    if len(items) <= max_items:
        return items, 0
    return list(items[:max_items]), len(items) - max_items


def normalize_text(s: Any) -> str:
    """编码清洗：去 BOM、bytes 安全解码、控制字符剥离（不截断）。"""
    return strip_control(s)


def escape_html(s: Any) -> str:
    """HTML 转义，供 html_exporter 插值使用（quote=True）。"""
    return _html.escape(str(s), quote=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_boundary.py -q`
Expected: PASS（11 passed）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add exporters/boundary.py tests/test_boundary.py
git commit -m "feat(exporters): add boundary pure-function library"
```

---

### Task 2: 将 boundary 接入 `canonical.normalize()`

**Files:**
- Modify: `exporters/canonical.py`（顶部 import；`_norm_objectives` / `_norm_roles` / `_norm_workflow` / `_norm_metrics` / `_norm_risks` / `_norm_strategy` / `normalize`）
- Test: `tests/test_export_boundary.py`（新建，先放 normalize 级边界测试）

- [ ] **Step 1: 写失败测试（normalize 级）**

```python
# tests/test_export_boundary.py
import io
from docx import Document
from exporters.canonical import normalize
from exporters.boundary import MAX_LIST_ITEMS, MAX_TEXT_LEN


def test_normalize_huge_list_capped():
    bs = {"objectives": [{"objective": f"o{i}", "priority": "high"} for i in range(500)]}
    r = normalize(bs)
    assert len(r.objectives) == MAX_LIST_ITEMS
    assert any("其余" in o.objective and "已省略" in o.objective for o in r.objectives)


def test_normalize_long_text_truncated():
    bs = {"business_domain": "x" * (MAX_TEXT_LEN + 100)}
    r = normalize(bs)
    assert "已截断" in r.title


def test_normalize_none_field_becomes_placeholder():
    bs = {"roles": [{"role": "CEO", "department": None}]}
    r = normalize(bs)
    assert r.roles[0].department == "—"


def test_normalize_type_error_coerced():
    bs = {"metrics": [{"name": 12345, "formula": "x", "target": "y"}]}
    r = normalize(bs)
    assert r.metrics[0].name == "12345"


def test_normalize_control_chars_stripped():
    bs = {"business_domain": "a\x00b\x1fc"}
    r = normalize(bs)
    assert "\x00" not in r.title and "\x1f" not in r.title


def test_normalize_bom_stripped():
    bs = {"business_domain": "\ufeff项目"}
    r = normalize(bs)
    assert "\ufeff" not in r.title


def test_normalize_empty_input_safe():
    r = normalize({})
    assert r.title == "业务系统分析报告"
    assert r.objectives == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_export_boundary.py -q`
Expected: FAIL（`AssertionError`：列表未封顶 / None 变 "None" 等）

- [ ] **Step 3: 改造 `canonical.py`（在构造各字段时调用定界函数）**

在 `exporters/canonical.py` 顶部 import 之后加入：

```python
from exporters.boundary import truncate_text, cap_list, normalize_text
```

将以下函数整体替换为新实现（其余 `_norm_*` 不变）：

```python
def _norm_objectives(bs: dict) -> List[CanonicalObjective]:
    raw = bs.get("objectives") or bs.get("core_objectives") or []
    raw, omitted = cap_list(raw)
    out = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        sev, label = _norm_severity(o.get("priority", "medium"))
        out.append(CanonicalObjective(
            objective=truncate_text(o.get("objective", "")),
            target=truncate_text(o.get("target", "")),
            priority=sev, priority_label=label,
        ))
    if omitted:
        out.append(CanonicalObjective(objective=f"其余 {omitted} 条已省略", priority="low", priority_label="🟢"))
    return out


def _norm_roles(bs: dict) -> List[CanonicalRole]:
    raw = bs.get("roles") or (bs.get("sop", {}) or {}).get("roles") or []
    raw, omitted = cap_list(raw)
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        out.append(CanonicalRole(
            role=truncate_text(r.get("role", "")),
            department=truncate_text(r.get("department", "")),
            level=truncate_text(r.get("level", "")),
            headcount=truncate_text(r.get("headcount", "")),
        ))
    if omitted:
        out.append(CanonicalRole(role=f"其余 {omitted} 条已省略", department="", level="", headcount=""))
    return out


def _norm_workflow(bs: dict) -> List[CanonicalStep]:
    raw = bs.get("workflow") or bs.get("process_flow") or bs.get("sop") or []
    raw, omitted = cap_list(raw)
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            continue
        out.append(CanonicalStep(
            step=s.get("step", i),
            name=truncate_text(s.get("name", "")),
            action=truncate_text(s.get("action", "")),
            role=truncate_text(s.get("role", "")),
        ))
    if omitted:
        out.append(CanonicalStep(step=len(out) + 1, name=f"其余 {omitted} 条已省略", action="", role=""))
    return out


def _norm_metrics(bs: dict) -> List[CanonicalMetric]:
    raw = bs.get("metrics") or bs.get("kpi") or bs.get("success_metrics") or []
    raw, omitted = cap_list(raw)
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        out.append(CanonicalMetric(
            name=truncate_text(m.get("name", m.get("kpi", ""))),
            formula=truncate_text(m.get("formula", m.get("expression", ""))),
            target=truncate_text(m.get("target", m.get("goal", ""))),
        ))
    if omitted:
        out.append(CanonicalMetric(name=f"其余 {omitted} 条已省略", formula="", target=""))
    return out


def _norm_risks(bs: dict) -> List[CanonicalRisk]:
    risks = bs.get("risks") or []
    if not risks and isinstance(bs.get("risk"), list):
        risks = bs.get("risk")
    risks, omitted = cap_list(risks)
    out = []
    if risks:
        for r in risks:
            if not isinstance(r, dict):
                continue
            sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
            out.append(CanonicalRisk(
                risk=truncate_text(r.get("risk", r.get("description", r.get("name", "")))),
                severity=sev, severity_label=label,
                mitigation=truncate_text(r.get("mitigation", r.get("response", r.get("action", "")))),
                impact=truncate_text(r.get("impact", r.get("consequence", ""))),
                category=r.get("category"),
            ))
        if omitted:
            out.append(CanonicalRisk(risk=f"其余 {omitted} 条已省略", severity="low",
                                     severity_label="🟢 低风险", mitigation="", impact="", category=None))
        return out
    nested = bs.get("risk", {})
    if isinstance(nested, dict):
        for cat, items in nested.items():
            if not isinstance(items, list):
                continue
            cat_name = cat.replace("_risks", "").replace("_", " ")
            items, omitted = cap_list(items)
            for r in items:
                if not isinstance(r, dict):
                    continue
                sev, label = _norm_severity(r.get("severity", r.get("level", "medium")))
                out.append(CanonicalRisk(
                    risk=truncate_text(r.get("risk", r.get("description", r.get("name", "")))),
                    severity=sev, severity_label=label,
                    mitigation=truncate_text(r.get("mitigation", "")),
                    impact=truncate_text(r.get("impact", "")),
                    category=cat_name,
                ))
            if omitted:
                out.append(CanonicalRisk(risk=f"其余 {omitted} 条已省略", severity="low",
                                         severity_label="🟢 低风险", mitigation="", impact="", category=cat_name))
    return out


def _norm_strategy(bs: dict) -> CanonicalStrategy:
    raw = bs.get("strategy") or {}
    if not isinstance(raw, dict):
        raw = {}
    recs = raw.get("recommendations") or []
    growth = raw.get("growth_opportunities") or []
    roadmap_raw = raw.get("strategic_path") or raw.get("milestones") or []
    roadmap_raw, r_omitted = cap_list(roadmap_raw)
    recs = [truncate_text(x) for x in recs]
    growth = [
        {"opportunity": truncate_text(g.get("opportunity", "")), "potential": truncate_text(g.get("potential", ""))}
        for g in growth if isinstance(g, dict)
    ]
    roadmap = [truncate_text(x) for x in roadmap_raw]
    if r_omitted:
        roadmap.append(f"其余 {r_omitted} 条已省略")
    return CanonicalStrategy(
        recommendations=recs,
        growth_opportunities=growth,
        roadmap=roadmap,
    )


def normalize(business_system: dict) -> CanonicalReport:
    bs = business_system or {}
    report = bs.get("report")
    exec_sum = ""
    if isinstance(report, dict):
        exec_sum = truncate_text(str(report.get("executive_summary", "")))
    return CanonicalReport(
        title=truncate_text(bs.get("business_domain", bs.get("objective", "业务系统分析报告"))),
        executive_summary=exec_sum,
        generated_at=normalize_text(bs.get("generated_at", "")),
        objectives=_norm_objectives(bs),
        roles=_norm_roles(bs),
        workflow=_norm_workflow(bs),
        metrics=_norm_metrics(bs),
        risks=_norm_risks(bs),
        strategy=_norm_strategy(bs),
    )
```

> 注意：`_norm_level` / `_norm_severity` / `Canonical*` 数据类 / `SEVERITY_LABELS` / `PRIORITY_LABELS` 保持不变。优先级/等级标签沿用既有 canonical 约定（缺失→medium→🟡），与跨格式一致性方向一致；本任务仅在列表封顶时合成条目用 🟢 低风险标注省略项，不改既有标签映射。

- [ ] **Step 4: 运行测试确认通过（含既有 canonical 测试不回归）**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_export_boundary.py tests/test_export_canonical.py -q`
Expected: PASS（新增 7 passed；既有 canonical 13 passed 不回归）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add exporters/canonical.py tests/test_export_boundary.py
git commit -m "feat(exporters): wire boundary into canonical normalize"
```

---

### Task 3: HTML 渲染转义收敛到 `boundary.escape_html`

**Files:**
- Modify: `exporters/html_exporter.py:1767-1780`（`generate_html` 顶部 `_esc` 定义）
- Test: `tests/test_export_boundary.py`（追加 HTML 注入用例）

> 现有 `generate_html` 已用 `_esc = _html.escape(str(s))` 对每个插值字段转义；本次仅将来源收敛为 `boundary.escape_html`，行为不变、单一真相源。

- [ ] **Step 1: 写失败测试（注入应被转义）**

```python
# 追加到 tests/test_export_boundary.py
from exporters.html_exporter import generate_html


def test_html_injection_escaped():
    bs = {"business_domain": "<script>alert(1)</script>",
          "objectives": [{"objective": "<img src=x onerror=alert(1)>", "priority": "high"}]}
    r = normalize(bs)
    html = generate_html(r, {}, None)
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_export_boundary.py::test_html_injection_escaped -q`
Expected: PASS（现有 `_esc` 已转义，此步本应通过——确认行为不变；若改完后仍通过即达标）

- [ ] **Step 3: 改造 `html_exporter.py` 收敛转义来源**

将 `generate_html` 顶部：

```python
    from exporters.canonical import CanonicalReport, normalize
    import html as _html
    if not isinstance(report, CanonicalReport):
        report = normalize(report)

    def _esc(s):
        return _html.escape(str(s))
```

改为：

```python
    from exporters.canonical import CanonicalReport, normalize
    from exporters.boundary import escape_html as _esc
    if not isinstance(report, CanonicalReport):
        report = normalize(report)
```

其余 `_esc(...)` 调用点保持不变。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_export_boundary.py -q`
Expected: PASS（含 test_html_injection_escaped）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add exporters/html_exporter.py tests/test_export_boundary.py
git commit -m "refactor(exporters): html escape delegates to boundary.escape_html"
```

---

### Task 4: 边界测试矩阵（12 例跨渲染器守护）

**Files:**
- Modify: `tests/test_export_boundary.py`（追加 12 例矩阵；此文件已存在，本任务仅追加函数）

- [ ] **Step 1: 写测试（覆盖 §7 全维度）**

```python
# 追加到 tests/test_export_boundary.py
from exporters.markdown_exporter import MarkdownExporter
from exporters.ppt_spec_exporter import generate_ppt_spec
from exporters.word_exporter import WordExporter


def _render_all(bs):
    r = normalize(bs)
    md = MarkdownExporter().export(r, None)
    html = generate_html(r, {}, None)
    ppt = generate_ppt_spec(r, None)
    doc = Document(io.BytesIO(WordExporter().export(r)))
    word = "\n".join(p.text for p in doc.paragraphs)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                word += "\n" + cell.text
    return md, html, ppt, word


def _ppt_has(text):
    for s in ppt["slides"]:
        if text in s.get("title", ""):
            return True
        for it in s.get("items", []):
            if text in it:
                return True
        for row in s.get("data", []):
            if any(text in str(c) for c in row):
                return True
    return False


def test_boundary_huge_list_all_formats():
    bs = {"metrics": [{"name": f"m{i}", "formula": "x", "target": "y"} for i in range(1000)]}
    md, html, ppt, word = _render_all(bs)
    for out in (md, html, word):
        assert "其余" in out and "已省略" in out
    assert _ppt_has("已省略")  # 指标省略项落在 PPT 表格 data 中


def test_boundary_long_text_truncated_marker():
    bs = {"business_domain": "超长" * 1500}
    md, html, ppt, word = _render_all(bs)
    for out in (md, html, word):
        assert "已截断" in out


def test_boundary_special_chars_no_crash():
    bs = {"business_domain": "A</>&%🚀\u200b\u202eB",
          "objectives": [{"objective": "x</>&%", "priority": "high"}]}
    md, html, ppt, word = _render_all(bs)   # 不抛即达标
    assert md and html and word


def test_boundary_html_injection_not_executable():
    bs = {"business_domain": "<script>alert(1)</script>"}
    _, html, _, _ = _render_all(bs)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_boundary_control_chars_stripped():
    bs = {"business_domain": "a\x00b\r\x1fc"}
    md, html, ppt, word = _render_all(bs)
    for out in (md, html, word):
        assert "\x00" not in out and "\x1f" not in out


def test_boundary_missing_field_safe():
    bs = {"objectives": [{"objective": "o"}]}  # 无 priority_label
    r = normalize(bs)
    assert r.objectives[0].priority_label  # 有默认标签，不崩


def test_boundary_type_error_coerced():
    bs = {"metrics": [{"name": 999, "formula": ["not", "str"], "target": "y"}]}
    md, html, ppt, word = _render_all(bs)
    assert "999" in md and "999" in html


def test_boundary_none_value_placeholder():
    bs = {"roles": [{"role": "CEO", "department": None, "level": None, "headcount": None}]}
    md, html, ppt, word = _render_all(bs)
    for out in (md, html, word):
        assert "—" in out


def test_boundary_bom_normalized():
    bs = {"business_domain": "\ufeff项目"}
    md, html, ppt, word = _render_all(bs)
    for out in (md, html, word):
        assert "\ufeff" not in out


def test_boundary_empty_input_safe():
    md, html, ppt, word = _render_all({})
    for out in (md, html, word):
        assert out  # 有输出、不崩、段落集完整
    assert any(s["title"] == "业务目标" for s in ppt["slides"])


def test_boundary_nested_anomaly_safe():
    bs = {"risk": "not-a-list-or-dict"}  # 异常类型
    r = normalize(bs)  # 不抛即达标
    assert isinstance(r.risks, list)


def test_boundary_cross_format_section_set_intact():
    bs = {"metrics": [{"name": f"m{i}", "formula": "x", "target": "y"} for i in range(500)]}
    md, html, ppt, word = _render_all(bs)
    markers = ["业务目标", "角色定义", "业务流程", "关键指标", "风险分析", "战略建议"]
    for m in markers:
        assert m in md and m in html and m in word
    assert all(any(s["title"] == m for s in ppt["slides"]) for m in markers)
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_export_boundary.py -q`
Expected: PASS（本任务新增 12 passed；累计约 20 passed）

- [ ] **Step 3: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add tests/test_export_boundary.py
git commit -m "test(exporters): boundary test matrix (12 cases)"
```

---

### Task 5: 全量回归

**Files:**
- 无新增；运行既有全套测试

- [ ] **Step 1: 运行全量测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过（基线 99 passed / 2 skipped 之上无新增失败；边界测试全绿）

- [ ] **Step 2: 提交（若仅测试通过、无新改动可跳过提交；如有临时改动则提交）**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git status   # 确认工作树干净（仅业务库/孤儿目录外部漂移，不提交）
```

> 若因外部漂移（app/bsc_cloud.db*、archive/orphan_fork/*、app/engines/sop_report_engine.py）出现未跟踪/修改，按本分支既有纪律**不要** `git add` 这些文件，保持 targeted add。

---

## 自检备注（实现时留意）

- `cap_list` 返回 `(capped, omitted)` 二元组；`_norm_*` 必须先解包再遍历。
- 合成"已省略"条目类型须与所在列表元素类型一致（metric→CanonicalMetric、objective→CanonicalObjective 等），否则渲染器访问 `.name`/`.objective` 会 AttributeError。
- `truncate_text(None)` 返回 `"—"`，故缺失字段经 `truncate_text` 后不会出现字面 `"None"`。
- HTML 转义仅在 `html_exporter`（`generate_html`）生效；markdown/word/ppt 文本惰性，不转义以免破坏合法语法。PDF 经 `generate_html` 派生，自然继承。
- 既有一致性测试（`test_export_canonical.py`）断言段落集与字段值，本计划不改变段落结构，应全绿。
