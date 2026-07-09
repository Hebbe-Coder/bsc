# 导出层 · 跨格式一致性 设计文档

- 日期：2026-07-09
- 分支：`feat/export-fault-tolerance`（接续「容错与降级」方向）
- 关联设计：[export-fault-tolerance-design.md](./2026-07-08-export-fault-tolerance-design.md)

## 1. 背景与问题

导出层当前有 markdown / html（PDF 由其派生）/ ppt / word 四个文本文档渲染器，外加 json（原始源）与 visuals（图表）。经代码审查，四渲染器**各自为政**，没有单一规范化模型驱动，导致同一份 `business_system` 在不同格式里内容实质性不一致：

| 维度 | Markdown | PPT | Word | HTML |
|---|---|---|---|---|
| 段落集合 | 缺 `metrics` | 缺 `roles` | 同 MD | 缺 `roles`（疑似） |
| 风险字段 | `risk.level` | `risk.severity` | — | `risk`/`risks` 混用 |
| 指标字段 | 整段缺失 | `metrics` | — | `kpi`/`metrics`/`success_metrics` |
| 战略子字段 | `recommendations` | `growth_opportunities` | — | 两者混用 |
| 优先级标签 | 🔴🟡🟢 | 无 | 【高】【中】【低】 | — |

**根因**：业务系统的权威结构在 `app/core/async_pipeline.py:565` 构建（规范字段 `objectives/roles/metrics(=sop.kpi)/risks/workflow/strategy/report/business_domain`），但每个渲染器自己挑段落、自己兜底字段别名、自己定派生标签。没有"单一真相源"。

## 2. 目标与非目标

**目标（本次范围）**
- 建立 `CanonicalReport` 单一规范化模型，作为四文档格式（markdown / html→pdf / ppt / word）的唯一真相源。
- 四渲染器改造为只消费 `CanonicalReport` 的瘦展示器，从构造上消除"漏段落 / 取错字段 / 标签分叉"。
- 段落集、顺序、等级标签、优先级标签**四格式字节级统一**。
- 用一致性测试守护回归。

**非目标（本次不做）**
- `json` 仍直接返回原始 `business_system`（它是源，不应被重排）。
- `visuals`（图表绑定）不在本次范围，后续单议。
- 不新增运行时一致性自检（与「容错与降级」的 `formats_status` 解耦，零开销）。

## 3. 方案概述（方案 A：单一规范化模型）

新增 `exporters/canonical.py`：
- `normalize(business_system: dict) -> CanonicalReport`：把原始 dict 一次性归一成结构化模型。
- orchestrator 在 dispatch 前调用一次 `normalize()`，将 `CanonicalReport` 传给每个 `_produce`；四渲染器签名由 `(business_system: dict, ...)` 改为 `(report: CanonicalReport, ...)`。
- 渲染器退化为纯模板，删除所有 `bs.get("x", bs.get("y"))` 猜测。

与「容错与降级」方向正交：`DegradeContext` 仍包裹各组件渲染；`normalize()` 的容错（缺段→空列表、坏值→默认）与组件级 skip 互不冲突。

## 4. 架构

```
原始 business_system (dict)
        │
        ▼
 normalize()  ── exporters/canonical.py  ← 唯一真相源
        │
        ▼
 CanonicalReport  ── 有序段落 + 规范字段名 + 规范派生标签
        │
        ├─► _produce("markdown", report, ...)  → MarkdownExporter.export(report, ctx)
        ├─► _produce("html",    report, ...)  → generate_html(report, ctx)  → PDF 自动跟随
        ├─► _produce("ppt",     report, ...)  → generate_ppt_spec(report, ctx)
        └─► _produce("word",    report, ...)  → WordExporter.export(report)
```

变更点：
- `exporters/orchestrator.py::run_export`：进入循环前 `canonical = normalize(bs)`；`_produce(fmt, canonical, result, ctx)`。
- `exporters/orchestrator.py::_produce`：各分支调用改为传 `report`。
- 四渲染器：签名与内部实现改写（见 §6）。

## 5. 规范模型（一致性契约）

```python
@dataclass
class CanonicalReport:
    title: str                              # business_domain
    executive_summary: str                  # report.executive_summary
    objectives: list[CanonicalObjective]    # 业务目标
    roles: list[CanonicalRole]              # 角色定义
    workflow: list[CanonicalStep]           # 业务流程
    metrics: list[CanonicalMetric]          # 关键指标
    risks: list[CanonicalRisk]              # 风险分析
    strategy: CanonicalStrategy             # 战略建议

CanonicalObjective = {objective: str, target: str,
                      priority: "high"|"medium"|"low", priority_label: str}
CanonicalRole      = {role: str, department: str, level: str, headcount: str}
CanonicalStep      = {step: str|int, name: str, action: str, role: str}
CanonicalMetric    = {name: str, formula: str, target: str}
CanonicalRisk      = {risk: str, severity: "high"|"medium"|"low", severity_label: str,
                      mitigation: str, impact: str, category: str | None}
CanonicalStrategy  = {recommendations: list[str],
                      growth_opportunities: list[{opportunity: str, potential: str}],
                      roadmap: list[str]}     # 来自 strategic_path | milestones
```

**渲染顺序（四格式统一）**：title + executive_summary → objectives → roles → workflow → metrics → risks → strategy。

**规范化规则（集中在 `canonical.py`，全格式复用，杜绝分叉）**：

```python
SEVERITY_LABELS = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}
PRIORITY_LABELS = {"high": "🔴", "medium": "🟡", "low": "🟢"}   # 含 word，字节级统一

_norm_severity(raw): 接受 severity 或 level（兼容旧数据）→ "high"|"medium"|"low" + 标签
_norm_priority(raw): 同上 → 等级值 + 标签
_norm_metrics(raw):  metrics / kpi / success_metrics
_norm_workflow(raw): workflow / process_flow / sop
_norm_risks(raw):    优先 risks 列表；每项规整 risk/severity/mitigation/impact/category；
                     仅存在嵌套 risk{process_risks, organization_risks, system_risks, compliance_risks}
                     时扁平化并标注 category
_norm_strategy(raw): recommendations + growth_opportunities
                     + roadmap(来自 strategic_path | milestones)
```

**关键不变量**：四渲染器只读 `severity_label` / `priority_label` 等规范字段，标签与排序从构造上统一。

## 6. 四个渲染器改造（瘦展示器）

| 渲染器 | 文件 | 主要改造 |
|---|---|---|
| Markdown | `exporters/markdown_exporter.py` | 按 `CanonicalReport` 顺序渲染六段；**补 `metrics` 段**（当前缺失）；删除硬编码 🔴🟡🟢，改用 `priority_label`/`severity_label`；保留 `ctx` 组件级降级 |
| HTML | `exporters/html_exporter.py` | 把全部 `bs.get("x", bs.get("y"))` 改为读 `report.*`；PDF（`PDFExporter._generate_html_content`）由 HTML 派生自动跟随 |
| PPT | `exporters/ppt_spec_exporter.py` | **补 `roles` 幻灯片**（当前缺失）；风险改用 `report.risks[].severity_label`（修掉 `severity` 字段错位 bug）；战略统一从 `report.strategy` 取（recommendations + growth_opportunities + roadmap）；保留 `ctx` |
| Word | `exporters/word_exporter.py` | 风险/优先级改用规范标签函数（替换原 `【高】【中】【低】` 硬编码），保证字节级一致；保留 `ctx` |

四渲染器均保留 `ctx: DegradeContext` 组件级降级（与 §3 正交）。

## 7. 数据流

原始 `business_system` → `normalize()` → `CanonicalReport` → orchestrator 分发给 markdown/html/ppt/word（四者拿到**同一份** `CanonicalReport`）→ 各自产物。`json` 仍直接返回原始 `business_system`；`visuals` 不受影响。

## 8. 错误处理

- `normalize()` 容错：缺失段落 → 空列表（不抛异常）；未知等级值（如脏数据）→ 回落 `medium` + 对应标签；字段缺省 → 空串。
- 与「容错与降级」正交：组件渲染失败仍由 `DegradeContext` 捕获并记入 `components_degraded`，单个区块失败不影响整格式；`normalize()` 失败（极罕见的结构损坏）由 orchestrator 现有 try/except 兜底为 `dropped`。
- 不引入新的 HTTP 语义变化；沿用统一信封（`code` 字段 200/207/422）。

## 9. 测试策略

新增 `tests/test_export_canonical.py`：

- `test_normalize_field_aliases`：`risk`/`risks`、`kpi`/`metrics`/`success_metrics`、`workflow`/`process_flow` 均正确归一到规范字段。
- `test_normalize_severity_variants`：`"high"`/`"高"`/`"🔴"`/`{level: "high"}` 全部 → 规范 `high` + 同一 `severity_label`。
- `test_renderers_same_sections`：同一 fixture 下，四渲染器覆盖**相同段落集**（含 markdown 的 `metrics`、ppt 的 `roles`）。
- `test_renderers_same_field_values`：抽取四产物中风险等级标签等，断言**逐字节一致**（验证字节级统一）。
- `test_canonical_order`：段落按 §5 顺序出现。
- `test_missing_section_safe`：缺 `metrics` 时四格式均安全跳过、不崩、不抛。

回归目标：在「容错与降级」基线（99 passed / 2 skipped）之上新增上述用例，全绿。

## 10. 实施任务拆分（细化见 plan）

1. `exporters/canonical.py`：`CanonicalReport` 及全部 `_norm_*` 归一层。
2. `exporters/orchestrator.py`：`run_export` 调 `normalize()` 并传递 `CanonicalReport`。
3. `exporters/markdown_exporter.py`：改写消费 `CanonicalReport`，补 `metrics`。
4. `exporters/html_exporter.py`：改写消费 `CanonicalReport`，PDF 跟随。
5. `exporters/ppt_spec_exporter.py`：改写消费 `CanonicalReport`，补 `roles`，修 `severity`。
6. `exporters/word_exporter.py`：改写消费 `CanonicalReport`，统一标签。
7. `tests/test_export_canonical.py`：上述一致性测试。

## 11. 风险与权衡

- **改动面较大**：四渲染器全部改写。缓解：每个渲染器改动独立、可单测；沿用现有 `ctx` 与 orchestrator 门禁。
- **旧别名兼容**：`_norm_*` 保留对 `level`/`kpi`/`process_flow` 等旧字段的兼容读取，避免破坏既有数据结构。
- **标签字节级统一**：word 文档将出现 emoji 标签（如 `🔴`），与文档惯例略有差异，但满足"全部统一"的硬约束，且更直观。
