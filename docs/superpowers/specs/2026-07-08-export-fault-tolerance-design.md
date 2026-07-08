# BSC 导出层 · 容错与降级 设计文档

- **日期**：2026-07-08
- **状态**：已评审认可（头脑风暴 → 设计）
- **关联文档**：`docs/superpowers/specs/2026-07-08-export-dep-availability-design.md`（前置：依赖与可用性）

## 1. 背景与动机

前置工作「导出层依赖与可用性」已交付：

- `ExportDependencyError` 结构化异常
- `EXPORT_CAPABILITIES` 能力登记表（依赖探测）
- `exporters/__init__.py` 惰性加载（缺 pptx 不再全包崩溃）
- `ApiResponse.partial`（HTTP 207）
- `/bsc/export` 端点的能力门禁（依赖缺失 → 整请求 422）+ 部分失败（207）

但现有状态存在明确缺口：

1. **依赖缺失 = 整请求 422 硬失败**：一个格式缺依赖就全盘拒绝，不是「降级」。
2. **html / ppt 完全无 `try/except`**：这两个格式运行时抛错会直接 500 崩溃，无优雅降级（word/markdown/pdf 已有保护）。
3. **无格式级替换**：pptx 不可用时不会自动改用 ppt 规格 / html。
4. **无组件级降级**：单格式内某个子组件（图表/表格）失败会拖垮整个格式。
5. **未实现格式静默缺失**：`capabilities.py` 登记了 `xlsx`/`pptx`，但 `export` 端点根本不产出它们，请求时若依赖齐全则静默不出现在结果里。

本设计在「依赖与可用性」之上补齐**容错与降级**能力。

## 2. 目标 / 非目标

### 目标（已与用户确认）

- **语义**：两者结合（最稳）——先尝试替代格式，无替代或替代也失败则丢弃并返回其余成功格式，响应逐格式说明处理结果。
- **范围**：全部（最稳）——运行时异常 + 依赖缺失 + 组件级 + 未实现格式，统一降级框架。
- **激活**：默认降级（最稳）——去掉 422 硬失败，依赖缺失 / 未实现格式统一进 207 逐格式报告。
- **呈现**：逐格式状态表——响应新增 `formats_status`，每项含 `format` / `status` / `source_format?` / `reason?` / `missing_package?` / `pip_install?`。

### 非目标

- 不新增 xlsx / pptx 真实导出器（仅将其作为「未实现」降级处理，或可选配置降级到 html）。
- 不改 `ExportDependencyError` / `EXPORT_CAPABILITIES` / `/capabilities` 端点（仅复用）。
- 不做异步 / 并发导出（属其他主题）。

## 3. 架构

### 3.1 新增模块

**`exporters/degrade.py`**（纯逻辑，无副作用）

- `DEGRADATION_RULES: dict[str, list[str]]` 候补链（可配置）：
  - `pptx → ["ppt", "html", "markdown"]`
  - `word → ["html", "markdown"]`
  - `pdf → ["html", "markdown"]`
  - `xlsx → ["html"]`（可选；默认留空 → 直接 `unimplemented`，见 §6）
  - `html → ["markdown"]`、`markdown → ["html"]`、`ppt → []`、`json → []`
- `classify_failure(fmt: str, exc: Exception) -> dict`：
  - `ExportDependencyError` → `{type:"dependency_missing", missing_package, pip_install}`
  - 其它 `Exception` → `{type:"runtime_error", message}`
  - （组件级由 `DegradeContext` 单独记录 `component_failed`）
- `IMPLEMENTED_FORMATS = {"json","html","ppt","word","markdown","pdf","visuals"}`
- `is_implemented(fmt) -> bool`

**`exporters/_degrade_ctx.py`**（组件级「跳过上下文」）

- `class DegradeContext`：`component(name)` 作为 contextmanager；子组件异常被捕获并加入 `self.component_failures`（每项 `{component, type:"component_failed", message}`），不影响其余渲染。
- 供 `html_exporter` / `ppt_exporter(_v2)` / `markdown_exporter` 接入；`word` / `pdf` 若难以分段保持整格式 all-or-nothing（不强求）。

**`exporters/orchestrator.py`**（编排核心）

- `dataclass ExportOutcome`：`exports: dict`、`formats_status: list[dict]`、`errors: list[dict]`（仅不可恢复技术错误）
- `run_export(bs, output_types, result) -> ExportOutcome`：
  - 对每个请求格式：
    1. `if not is_implemented(fmt):` → `dropped` / `unimplemented`
    2. 尝试 `produce(fmt, bs, result, ctx)`（**统一 try/except，含 html/ppt**）
    3. 成功 → `produced`
    4. 失败 → `classify_failure`；若 `dependency_missing` 或 `runtime_error` 且有候补链 → 逐候补重试 `produce`，首个成功 → `substituted`（`source_format`=候补格式）
    5. 全部失败 / 无候补 → `dropped` + 原因
  - `visuals` 特殊处理（`bind_visuals` 已有 try/except，保持不变；纳入 `formats_status` 为 `produced` / `dropped`）

### 3.2 端点重构（`app/api/bsc_api.py`）

`export_results` 改为：

1. 参数校验（未知格式名、缺 `business_system` / `input`）→ 400（保持硬校验，不降级）
2. 调 `run_export(bs, req.output_types, result)`
3. 映射 outcome：
   - 全部 `produced` → `ApiResponse.ok(payload)`
   - ≥1 `produced` 且存在 `substituted` / `dropped` → `ApiResponse.partial(payload, ...)`
   - 零 `produced`（全 `dropped`）→ `ApiResponse.error(..., code=422).model_copy(update={"data":{"formats_status":...}})`（说明为何一无所有）
4. `payload` 新增顶层 `formats_status`；保留 `exports` / `errors` / `summary` / `formats`

> **删除**现有内联 422 门禁（第 409–415 行）与分散的 word/markdown/pdf `try/except`（第 441–462 行），统一交给编排器。

## 4. 响应结构（`formats_status` 示例）

```json
{
  "success": false,
  "code": 207,
  "message": "部分格式经降级处理",
  "data": {
    "exports": { "ppt": { }, "html": "...", "word": { } },
    "formats": ["ppt", "html", "word"],
    "formats_status": [
      { "format": "pptx", "status": "substituted", "source_format": "ppt" },
      { "format": "html", "status": "produced" },
      { "format": "word", "status": "produced" }
    ],
    "summary": "...",
    "errors": []
  }
}
```

- `status` 取值：`produced` | `substituted` | `dropped`
- `dropped` 条目附加：`reason`（`dependency_missing` / `runtime_error` / `component_failed` / `unimplemented`）+ 对应字段（`missing_package` / `pip_install` / `message` / `component`）

## 5. HTTP 语义汇总

| 场景 | 状态码 |
|---|---|
| 全部 requested 格式直接产出 | 200 |
| ≥1 产出，且有替换 / 丢弃 | 207 |
| 零产出（全 dropped） | 422（带 formats_status） |
| 请求非法（未知格式 / 缺参） | 400 |

旧的「依赖缺失即整请求 422」被取代为降级；`/bsc/exports/capabilities` 保留供调用方预检。

## 6. 边界与默认值

- **xlsx 处理**：默认 `is_implemented("xlsx")=False` → `dropped/unimplemented`。可选把 `xlsx → ["html"]` 让其降级到 HTML 表格（配置项，默认关）。
- **零产出 422**：仅当所有请求格式都 `dropped` 时返回 422，且 `formats_status` 清楚说明每个的丢弃原因，调用方不会「以为成功却空手」。
- **组件级**：仅 html/ppt/markdown 接入 `DegradeContext`；不强制 word/pdf 分段。
- **verbose**：`classify_failure` 的 `runtime_error` 默认只带 `message`；堆栈仅在 `verbose=true` 时附（可选，先不实现，留接口）。

## 7. 测试

`tests/test_export_degrade.py`（预计新增 ~12 例）：

- **单元**：`classify_failure` 四原因；`DEGRADATION_RULES` 解析；`is_implemented` 识别 xlsx/pptx
- **编排**：mock 各导出器抛错 → 验证 `substituted`(pptx→ppt)、`dropped`+原因、组件级 skip、零产出→422
- **端点集成（TestClient）**：
  - `[pptx, html]` + pptx 缺失 → 207 + pptx `substituted(→ppt)`、html `produced`
  - `[word]` + docx 缺失 + html 可用 → 207 + word `substituted(→html)`
  - `[word]` + docx 缺失 + 候补均失败 → 422 + 零产出说明
  - `[unknown]` → 400
  - 组件级：mock html 内某组件抛错 → 该格式 `produced`(degraded) 且 `formats_status` 含 `component_failed`
- 全量回归保持 `76 passed, 2 skipped`（2 skipped = 真实 LLM e2e）

## 8. 实现顺序（给 writing-plans 的提示）

1. `exporters/degrade.py`（规则 + 分类 + 实现集）
2. `exporters/_degrade_ctx.py`（组件跳过上下文）
3. `exporters/orchestrator.py`（`run_export` + `ExportOutcome`）
4. 接入导出器（html/ppt/markdown 包统一 try/except；html/ppt/markdown 接 `DegradeContext`）
5. 重构 `bsc_api.py` 的 `export_results`（删内联门禁与分散 try/except，改调 orchestrator + 映射 HTTP）
6. `tests/test_export_degrade.py` + 全量回归
