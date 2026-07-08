# 导出层依赖与可用性 — 设计文档

- 日期：2026-07-08
- 方向：导出层健壮性 → 优先子问题「依赖与可用性」
- 决策：两者结合（最稳）—— 统一惰性导入 + 结构化错误 + 能力门禁 + 422/207 语义
- 状态：已与用户对齐（认可）

---

## 1. 背景与目标

`bsc-backend` 的 `export_results` 端点（`app/api/bsc_api.py:396`）支持 6 种输出格式：`json / html / ppt / word / markdown / pdf`。其中 `word`/`pdf`/`xlsx` 依赖第三方库，缺失时处理不一致，且存在一个隐蔽的**包级崩溃**会让所有导出器都无法导入。

### 1.1 当前真实状态（已核对代码，非旧笔记）

| 格式 | API 内实现 | 依赖 | 缺失时的当前行为 |
|---|---|---|---|
| `json` | 直接返回 `bs` 字典 | 无 | 始终可用 |
| `html` | `_generate_html`（bsc_api.py:458） | 无 | 始终可用 |
| `ppt` | `_generate_ppt_spec`（返回 JSON 规格） | 无 | 始终可用 |
| `markdown` | `MarkdownExporter` | 无重依赖 | 始终可用 |
| `word` | `WordExporter`（word_exporter.py:9） | `python-docx` | 惰性标志 + 清晰 `RuntimeError("python-docx未安装，请运行: pip install python-docx")` |
| `pdf` | `PDFExporter`（pdf_exporter.py:9） | `weasyprint`/`pdfkit`/`reportlab` | 惰性 `available` 标志 + 清晰 `RuntimeError`（pdf_exporter.py:45） |
| `xlsx` | `export_xlsx`（xlsx_exporter.py:17，**未被 API output_types 使用**） | `openpyxl` | 惰性 + `ImportError("openpyxl required: pip install openpyxl")`（xlsx_exporter.py:24） |

**两个真问题：**

1. **包级崩溃（最严重）**：`exporters/__init__.py:1-2` 在模块顶层 `from exporters.ppt_exporter import ...` 和 `from exporters.ppt_exporter_v2 import ...`。而 `ppt_exporter.py:14-18` 与 `ppt_exporter_v2.py:21-27` 都在文件顶层 `from pptx import ...`。
   结果：导入**任意**导出器子模块都会先执行 `exporters/__init__.py`，进而触发 `ppt_exporter` 的顶层 `from pptx import`，一旦 `python-pptx` 缺失，整个 `import exporters.xxx` 链崩溃 —— 连 `html`/`markdown`/`json` 都导不出去。
   当前 API 里 `word`/`pdf`/`markdown` 块有 `try/except`，会把崩溃吞进 `errors[]`，但报错信息会误导（例如请求 word 却报 `No module named 'pptx'`），并且仍然返回 `success:true`。

2. **静默成功**：`export_results` 末尾固定 `return ApiResponse.ok(...)`（bsc_api.py:450），把格式失败塞进 `errors[]` 却始终 `success:true`；只有缺参数才返回 400。调用方（前端/CI）无法据此判断导出是否真正成功。

### 1.2 非目标（本次不做）

- 不改 6 种格式的实际渲染逻辑（html/word/ppt/pdf/xlsx/md 内容生成）。
- 不引入新的导出格式。
- 不做跨格式内容一致性（那是「导出层健壮性」的另一子问题，后续单独做）。
- 不处理 `python-pptx` 在 API 输出路径上的实际用途（API 当前 `ppt` 输出是 JSON 规格、不依赖 pptx；惰性化仅为防御性 + 消除崩溃）。

---

## 2. 设计总览

```
请求 export_results(output_types=[...])
   │
   ├─ 1) 能力校验：req.output_types ∩ EXPORT_CAPABILITIES
   │      └─ 任一请求格式不可用 → HTTP 422 + 每格式缺失包名与 pip 命令
   │
   ├─ 2) 逐格式导出（每个包 try/except）
   │      └─ 单个失败 → 收进 structured errors[]
   │
   ├─ 3) 汇总返回：
   │      ├─ 全成功            → HTTP 200 + success:true
   │      └─ 部分/全部失败     → HTTP 207 + success:false + errors[]（结构化）
   │
   GET /api/bsc/exports/capabilities → 返回 EXPORT_CAPABILITIES（运维/前端自检）
```

---

## 3. 设计组件

### 3.1 统一结构化错误 `exporters/errors.py`（新增）

```python
class ExportDependencyError(Exception):
    def __init__(self, fmt: str, missing_package: str, pip_install: str):
        self.format = fmt
        self.missing_package = missing_package
        self.pip_install = pip_install
        super().__init__(
            f"格式 {fmt} 不可用：缺少依赖 {missing_package}，请执行 `{pip_install}`"
        )
```

各导出器原各自抛 `RuntimeError`/`ImportError` 处统一改为抛 `ExportDependencyError`，携带 `missing_package` 与 `pip_install`，调用方拿到的信息一致、可直接复制安装。

### 3.2 惰性包初始化 `exporters/__init__.py`（改写）

删除顶层 `from exporters.ppt_exporter import ...` / `from exporters.ppt_exporter_v2 import ...`，改用 PEP 562 惰性 `__getattr__`：

```python
import importlib

_LAZY = {
    "PPTExporter": ("exporters.ppt_exporter", "PPTExporter"),
    "PPTExporterV2": ("exporters.ppt_exporter_v2", "PPTExporterV2"),
    "Theme": ("exporters.ppt_exporter_v2", "Theme"),
    "ChartGenerator": ("exporters.ppt_exporter_v2", "ChartGenerator"),
    "export_impeccable": ("exporters.ppt_exporter", "export_impeccable"),
    "export_with_qa": ("exporters.ppt_exporter", "export_with_qa"),
    "qa_check": ("exporters.ppt_exporter", "qa_check"),
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

def __getattr__(name: str):
    if name in _LAZY:
        mod, attr = _LAZY[name]
        return getattr(importlib.import_module(mod), attr)
    raise AttributeError(f"module 'exporters' has no attribute {name!r}")
```

效果：`import exporters` 或 `import exporters.word_exporter` **不再**触发 `pptx` 顶层导入；只有真正访问 `exporters.PPTExporter` 时才导入 pptx，缺失则抛 `ExportDependencyError`。

### 3.3 惰性 pptx 导入（防御性，消除残余崩溃）

- `ppt_exporter.py:14-18` 与 `ppt_exporter_v2.py:21-27` 的 `from pptx import ...` 移至实际使用处（如 `PPTExporter.__init__` / 各 `export_*` 函数首行），缺失时抛 `ExportDependencyError(missing_package="python-pptx", pip_install="pip install python-pptx")`。
- 由于 API 的 `ppt` 输出是 JSON 规格、不依赖 pptx，这一步主要保证 `exporters` 包在任何依赖缺失下都可被导入，并为将来新增 pptx 文件输出铺路。

### 3.4 格式能力登记表 `exporters/capabilities.py`（新增）

```python
EXPORT_CAPABILITIES: dict[str, dict] = {
    "json":     {"available": True,  "deps": []},
    "html":     {"available": True,  "deps": []},
    "ppt":      {"available": True,  "deps": []},          # JSON 规格，无 pptx 依赖
    "markdown": {"available": True,  "deps": []},
    "word":     _probe("word", ["docx"], "pip install python-docx"),
    "pdf":      _probe("pdf", ["weasyprint", "pdfkit", "reportlab"], "pip install weasyprint"),
    "xlsx":     _probe("xlsx", ["openpyxl"], "pip install openpyxl"),
    "pptx":     _probe("pptx", ["pptx", "matplotlib"], "pip install python-pptx matplotlib"),
}
```

提供：
- `format_available(fmt: str) -> bool`
- `unavailable_formats(requested: list[str]) -> list[dict]`（返回每格式缺失包 + 安装命令）
- `_probe` 在模块加载时 `importlib.util.find_spec` 探测依赖，避免真的 import 副作用。

`pptx` 键虽非当前 API output_type，仍登记以便自检与未来扩展。

### 3.5 API 错误语义修正 `app/api/bsc_api.py`（`export_results`）

在导出前做能力校验：

```python
unavail = unavailable_formats(req.output_types)
if unavail:
    return ApiResponse.error(
        "以下格式当前不可用", code=422,
        data={"unavailable": unavail},   # 每格式含 missing_package + pip_install
    )
```

逐格式导出逻辑不变（已 try/except），但异常统一捕获为 `ExportDependencyError` 并序列化为结构化项。汇总返回：

| 情况 | HTTP | success |
|---|---|---|
| 全成功 | 200 | true |
| 部分/全部失败（格式可用但导出抛错） | 207 Partial Content | false |

需在 `app/core/response.py`（或现有 `ApiResponse`）新增 `ApiResponse.partial(data)` 返回 207；复用 `ApiResponse.error(code=422)`。`errors[]` 每项形如 `{"format": "word", "missing_package": "python-docx", "pip_install": "pip install python-docx", "message": "..."}`。

### 3.6 自检端点（新增）

```
GET /api/bsc/exports/capabilities
→ 200, { "capabilities": EXPORT_CAPABILITIES }
```

便于前端/运维在调用前探测可用格式。

### 3.7 测试锁定行为 `tests/test_export_dependencies.py`（新增）

用 `sys.modules["pptx"] = None`（让 `import pptx` 抛 `ImportError`）模拟缺失，离线验证：

1. `EXPORT_CAPABILITIES` 中 `word`/`pdf`/`xlsx`/`pptx` 的 `available` 与依赖探测一致。
2. `ExportDependencyError` 携带正确的 `missing_package` 与 `pip_install`。
3. 惰性初始化：模拟 pptx 缺失时 `import exporters` 成功、`from exporters.word_exporter import WordExporter` 成功，仅访问 `exporters.PPTExporter` 抛 `ExportDependencyError`。
4. API：请求 `word` 且 `docx` 缺失 → 返回 422，body 含该格式安装命令；模拟某可用格式导出中抛错 → 返回 207 + `success:false` + 结构化 `errors[]`。
5. 现有 `xlsx_exporter` 的 `ImportError("openpyxl required: ...")` 仍符合新契约（不回归）。

---

## 4. 预期行为对照

| 场景 | 当前 | 目标 |
|---|---|---|
| `python-pptx` 缺失，请求 `html` | 整条链因 `__init__` 崩溃，被 try/except 吞成误导 errors + success:true | 正常返回 html（__init__ 不再 import pptx） |
| `python-docx` 缺失，请求 `word` | errors=["Word导出失败: No module named 'pptx'"]（误导）+ success:true | HTTP 422，明确「word 缺 python-docx，pip install python-docx」 |
| `word` 可用但渲染抛错 | errors=[...] + success:true | HTTP 207 + success:false + 结构化 errors |
| 全部成功 | 200 + success:true | 200 + success:true（不变） |
| 运维想知道哪些格式可用 | 无 | `GET /exports/capabilities` |

---

## 5. 影响面与风险

- **新增文件**：`exporters/errors.py`、`exporters/capabilities.py`、`tests/test_export_dependencies.py`。
- **改写**：`exporters/__init__.py`（惰性化）、`ppt_exporter.py` / `ppt_exporter_v2.py`（pptx 惰性）、`app/api/bsc_api.py`（`export_results` 语义 + 新端点）、`app/core/response.py`（新增 `partial`）。
- **不改**：6 种格式的实际内容生成逻辑；`html`/`markdown`/`json`/`ppt` 零依赖路径。
- **风险**：惰性 `__getattr__` 需确认没有别处依赖 `from exporters import PPTExporter` 之外的导入方式（如 `importlib` 反射）。实现时 grep `exporters\.` 引用确认。
- **回归**：现有 66 passed/2 skipped 不受影响（新增用例另算）；`xlsx` 惰性契约不回归。

---

## 6. 提交策略（按段提交，便于 review）

1. `feat(exporters): add ExportDependencyError + lazy __init__`（errors.py + __init__.py + pptx 惰性）
2. `feat(exporters): add capability registry` (capabilities.py)
3. `feat(api): 422 gate + 207 partial + /capabilities endpoint` (bsc_api.py + response.py)
4. `test: export dependency availability` (tests/test_export_dependencies.py)

每段提交后跑 `pytest -q` 确认绿灯。
