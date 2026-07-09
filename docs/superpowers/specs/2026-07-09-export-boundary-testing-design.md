# 导出层「边界与测试」设计文档

- 日期：2026-07-09
- 分支：`feat/export-fault-tolerance`
- 上游方向：① 依赖与可用性 → ② 容错与降级 → ③ 跨格式一致性 → **④ 边界与测试（本文）**
- 状态：设计已认可，待写实现计划

---

## 1. 背景与目标

导出层（`exporters/`）已具备：
- 统一信封（HTTP 始终 200，语义码在 body `code`）；
- 容错与降级（`degrade.py` + `DegradeContext` + 逐格式状态表）；
- 跨格式一致性（`canonical.py` 单一 `CanonicalReport` 规范模型 + 四瘦渲染器，六段段落集字节级统一、标签词表统一）。

但当前对**极端/非法输入**的健壮性仍缺失：超长文本、超大列表、特殊字符、HTML/Markdown 注入、控制字符、BOM/代理对编码、缺字段、类型错、`None` 值、全空输入、嵌套结构异常等，都可能让某个渲染器产生溢出、乱码、或（HTML 路径）可执行注入。

本文目标：在归一化阶段集中做**定界**（有界、类型安全、编码干净），在 HTML 渲染阶段按格式做**转义**（防注入），并配套一份**边界测试矩阵**守护不回归。

### 非目标
- 不做"拒绝即降级"：边界输入不被当作失败触发 `degrade`，而是被定界成安全值后照常产出。
- 不引入 property/模糊测试：本次用可读、可定位的边界测试矩阵。
- 不改 `orchestrator` 与四文档渲染器（除 `html_exporter` 增加 `escape_html` 调用）。
- 不新增导出格式，不碰 json / visuals 渲染路径（它们不属四文档格式范围）。

---

## 2. 方案对比

### 方案 A（采用）—「归一化时定界 + 渲染时按格式转义」
新增独立 `exporters/boundary.py` 纯函数库，分两层：
- **定界类**（与格式无关，在 `canonical.normalize()` 构造 `CanonicalReport` 时调用）：`truncate_text`、`cap_list`、`coerce_str`、`strip_control`、`normalize_text`。
- **转义类**（与格式相关，由对应渲染器调用）：`escape_html` 供 `html_exporter` 在插值每个字段时调用（PDF 经 `generate_html` 自然继承）。

**关键洞察**：转义**绝不**放在 `normalize()` 里。同一份 `CanonicalReport` 要喂给 markdown/html/word/ppt 四种渲染器；若在归一化阶段把 `<` 变成 `&lt;`，markdown/word/ppt 会原样显示 `&lt;`，破坏合法内容。只有 HTML/PDF 有"浏览器执行"风险，转义只在该处做。定界（长度/数量/类型/编码）才是格式无关的，可集中。

### 方案 B（排除）—「归一化时连转义一起做」
会污染其他三格式，否决。

### 方案 C（排除）—「各渲染器内联防御」
分散、易与一致性方向分叉、重复，否决。

---

## 3. 架构与数据流

```
原始 business_system
   → normalize()  [构造 CanonicalReport 时调用 boundary 定界函数]
   → CanonicalReport（已定界：有界、类型安全、编码干净）
   → 四渲染器
        · html_exporter 额外对每个插值字段调 escape_html（PDF 经 generate_html 继承）
        · markdown / word / ppt 直接消费定界后的值
   → orchestrator 零改动（已 normalize 一次）
```

`boundary.py` 是纯函数库，无副作用、易单测；`canonical.py` 在 `_norm_*` 里 `import` 并调用；渲染器除 HTML 外零改动。`orchestrator` 维持现状（先 `normalize` 一次再 dispatch）。

---

## 4. 边界策略表（定界，在 normalize 内统一应用）

| 维度 | 触发条件 | 处理 | 占位/标记 |
|---|---|---|---|
| 超长文本 | 单字段字符数 > `MAX_TEXT_LEN`(默认 2000) | 截断并在尾部追加 `…（已截断，原文 N 字）` | — |
| 超大列表 | 列表长度 > `MAX_LIST_ITEMS`(默认 200) | 取前 200 条，列表末尾追加 `其余 X 条已省略` | — |
| `None`/缺字段 | 期望 `str` 收到 `None` 或字段缺失 | 替换为 `—`；优先级/等级标签缺失用默认 `🟢` | `—` |
| 类型错 | 收到 `int`/`list`/`dict` 等非 `str` | `coerce_str` 转 `str()` | — |
| 控制字符 | `\x00`–`\x1f` 中除 `\n` `\t` 之外 | `strip_control` 删除 | — |
| 编码/BOM | 含 `\ufeff`、代理对、或 `bytes` | 去 BOM；`bytes` 按 UTF-8 安全解码；不可解码字符替换 | 解码失败处用 `?` |
| 空输入 | 全空 `business_system` | 各段出"暂无…"标记，不崩 | `暂无` |

常量集中定义于 `boundary.py` 顶部（`MAX_TEXT_LEN`、`MAX_LIST_ITEMS`），便于单测与调参。

---

## 5. 转义策略（仅 HTML/PDF，渲染时）

`html_exporter` 对每个被插进 HTML 的字段值调用 `escape_html`（基于标准库 `html.escape`，`quote=True`），确保 `<script>alert(1)</script>` 变成 `&lt;script&gt;…`，不被浏览器执行。PDF 由 `generate_html` 派生，自然继承该保护。

Markdown / Word / PPT 文本天然惰性（导出为文件/文档对象，无 JS 执行环境），仅享用定界后的有界值即可，不做额外转义（避免破坏合法 Markdown 语法如 `<` 比较符）。

---

## 6. 错误处理

`boundary.py` 内所有函数**永不抛异常**——任何不可强制转换的值都产出安全占位字符串（`—` / `?`）。这样内容层绝不会让渲染器崩溃；基础设施级失败（缺依赖、运行异常）仍由已有 `degrade` 层按格式级/组件级 skip 兜底。两层正交：

- `boundary` 管"内容合法有界"（输入是脏的但能定界）；
- `degrade` 管"依赖/运行失败"（环境/组件不可用）。

渲染器内部既有的 `if not isinstance(report, CanonicalReport): report = normalize(report)` 兜底保持不变。

---

## 7. 测试矩阵（`tests/test_export_boundary.py`，12+ 用例）

逐条断言**不崩溃 + 输出有界 + 转义正确 + 跨格式段落集完整**：

1. **超长文本** → 输出含 `（已截断，原文` 标记，长度 ≤ 阈值 + 标记长。
2. **超大列表**（1000 条 metrics）→ 四格式均封顶 200 且含 `其余 X 条已省略`。
3. **特殊字符**（`</>&%`、emoji、零宽 `\u200b`、RTL `\u202e`）→ 四格式均不崩、不报异常。
4. **HTML 注入** `<script>alert(1)</script>` → HTML 输出为 `&lt;script&gt;…`，不含裸 `<script>` 可执行标签；PDF 同源。
5. **控制字符/换行**（`\x00` `\r` `\x1f`）→ 被剥离，输出无 `\x00`。
6. **缺字段**（objective 无 `priority_label`）→ 容错为默认 `🟢` 或占位，不崩。
7. **类型错**（metric.name 为 `int`）→ 转 `str`，渲染正常。
8. **`None` 值**（role.department=None）→ 显示为 `—`。
9. **编码/BOM**（`\ufeff` 前缀、surrogate `\ud800`）→ 干净 `str`，无 BOM 残留。
10. **全空输入**（空 `business_system`）→ 各段"暂无"，段落集仍完整，不崩。
11. **嵌套异常**（risk 为 `str` 而非 list/dict）→ `normalize` 优雅归一，不抛。
12. **跨格式一致**：同一样本经 `boundary` 定界后，四格式段落集仍与一致性测试一致（复用 `test_renderers_same_sections` 思路）。

---

## 8. 任务拆分（TDD，每任务独立 commit）

- **T1** `exporters/boundary.py`：常量 + `truncate_text` / `cap_list` / `coerce_str` / `strip_control` / `normalize_text` / `escape_html`，纯函数，自带单测 `tests/test_boundary.py`。
- **T2** `canonical.py` 接线：`_norm_*` 在构造各字段时调用定界函数（文本截断/列表封顶/类型容错/控制字符剥离/编码清洗）。
- **T3** `html_exporter.py` 接线：插值字段统一经 `escape_html`，新增单测验证注入被转义（复用 §7 用例 4）。
- **T4** `tests/test_export_boundary.py`：落地 §7 测试矩阵 12 例（含超长/超大/特殊字符/注入/控制字符/缺字段/类型错/None/编码/全空/嵌套/跨格式一致）。
- **T5** 全量回归：`pytest -q`，确认 99 passed / 2 skipped 基线之上无新增回归；边界测试全绿。

---

## 9. 风险与缓解

- **阈值误伤合法长内容**：`MAX_TEXT_LEN=2000` / `MAX_LIST_ITEMS=200` 为经验默认值，集中常量便于调参；截断带"原文 N 字"标记不静默丢失。
- **HTML 转义遗漏新插值点**：T3 接线后由 §7 用例 4 守护；后续新增 HTML 插值必须过 `escape_html`，可加 lint/约定注释。
- **与一致性方向耦合**：boundary 在 `normalize` 内运行，一致性测试（段落集/字段值）仍应全绿；T4 用例 12 显式守护两者不冲突。
- **控制字符剥离影响换行**：仅剥离 `\x00`–`\x1f` 除 `\n`/`\t`，保留正常换行与缩进。
