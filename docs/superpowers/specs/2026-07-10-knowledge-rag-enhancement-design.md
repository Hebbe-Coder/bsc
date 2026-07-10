# 知识库 RAG 后端增强 · 设计规格

- **日期**: 2026-07-10
- **状态**: 设计已通过（待落地规划）
- **关联**: `2026-07-09-knowledge-rag-design.md`（RAG 基础）、`2026-07-09-knowledge-rag-citation-qa.md`（引用溯源 QA）
- **范围**: 检索重排 Rerank + 更多文档类型接入 + 增量更新

---

## 1. 背景与目标

上一轮已建成知识库 RAG 基础：`/knowledge/ingest`、`/retrieve`、`/ask`、`/evaluate`，以及 `RAGEvaluator`（`precision@k`/`recall@k`）与引用溯源 QA。本次在**不重构核心**的前提下做两线增强：

1. **检索重排（Rerank）**：当前 `retrieve()` 用 `keyword/tfidf/vector` 三路召回后做 RRF 融合，没有「语义重排」环节。加入 Rerank 可显著提升 top-k 相关性，减少无关片段进入 LLM。
2. **更多文档类型 + 增量更新**：当前 `ingest(text)` 只吃纯文本。扩展到 PDF(含 OCR)/Word/Markdown/PPT/Excel，并支持同一文件多次入库时的**幂等原地更新**（不重复堆积）。

设计风格延续项目既有约定：**可插拔接口 + 默认降级 + 测试用 mock + 门面永不上抛 + 严守漂移文件纪律**。

---

## 2. 设计决策汇总（头脑风暴收敛结果）

| 维度 | 决策 |
|------|------|
| 方向 | 知识库 RAG 后端增强 |
| 增强块 | ① 检索重排 Rerank ② 更多文档类型 + 增量更新 |
| Reranker 形态 | **混合可切换**：抽象 `Reranker` 接口 + 默认本地 cross-encoder + settings 切云端 + 测试 mock |
| 文档格式 | PDF（**含 OCR**）+ Word + Markdown/纯文本 + PPT/Excel（**不含**网页抓取，守离线） |
| 增量身份 | doc_id **显式优先**，否则 `hash(source + project_id)` 派生 |
| 变更检测 | 归一化正文 `content_hash`（sha256）；未变→skipped，变更→级联替换 + version+1 |
| 验收口径 | **C 级**：功能正确 + `RAGEvaluator` 前后对比（precision@k/recall@k）+ 性能预算（延迟 P95 守护） |
| 架构方案 | 方案 A（分层扩展），按方案 C 节奏**分片交付** |
| reranker.py 复用 | 现有 `reranker.py` 仅含 `rrf_fuse`（RRF 融合，非重排模型）；**新 Reranker 类并入同文件**（同职责域） |

---

## 3. 架构总览

```
=== 入库线 (ingest) ===
 file / bytes
    │
    ▼
 DocumentParser.parse(path_or_bytes, filename)   # 按扩展名分派, 依赖全懒导入
    ├─ PDFParser   (pypdf/pdfplumber; 可选 pytesseract OCR)
    ├─ WordParser  (python-docx)
    ├─ MarkdownParser / PlainText  (零依赖)
    └─ OfficeParser (python-pptx / openpyxl)
    │
    ▼  归一化文本
 doc_id / content_hash 计算
    ├─ 显式 doc_id 优先, 否则 sha256(f"{source}|{project_id}")[:16]
    ├─ content_hash = sha256(归一化正文)
    │
    ▼  幂等决策
 ├─ 命中旧记录 且 hash 相同  → {"status":"skipped", "doc_id":...}
 └─ 未命中 / hash 不同       → delete_document(doc_id) 级联清理旧 chunk
                              → 重新 chunk / 索引  → version+1
                              → {"status":"ingested"|"updated", "doc_id":..., "version":N}

=== 检索线 (retrieve) ===
 query
   │
   ▼
 keyword / tfidf / vector 三路召回 (各自容错)
   │
   ▼
 rrf_fuse(...)  →  候选池 top_n  (top_n 默认 20, 大于最终 top_k)
   │
   ▼
 Reranker.rerank(query, candidates, top_k)   # rerank=None 时读 settings.RERANK_ENABLED
   ├─ LocalCrossEncoderReranker  (懒加载 sentence-transformers; 失败降级原序)
   ├─ CloudReranker                (Cohere/Jina, RERANK_KEYS 多 key 故障转移)
   └─ MockReranker                 (测试确定性重排)
   │
   ▼
 截 top_k → 结果列表 (附 rerank_score)
```

---

## 4. 组件详细设计

### 4.1 Reranker（并入 `app/knowledge/reranker.py`）

```python
class Reranker:
    """基类: 只重排, 不改内容; 返回带 rerank_score 的候选列表。"""
    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        raise NotImplementedError

class LocalCrossEncoderReranker(Reranker):
    """懒加载 cross-encoder (如 BAAI/bge-reranker-v2-m3)。
    导入失败 / 无权重 → 自动降级返回原序, 绝不抛异常。"""

class CloudReranker(Reranker):
    """Cohere/Jina API; 读 RERANK_PROVIDER / RERANK_KEYS;
    复用既有多 key 故障转移; 全部 key 失败 → 降级原序。"""

class MockReranker(Reranker):
    """确定性重排 (如按 query 词命中数排序); 供测试离线断言。"""

def get_reranker() -> Reranker:
    """按 settings.RERANK_PROVIDER 返回实例 (默认 'mock'/'none')。"""
```

- `rerank()` 入参 `candidates` 为 `retrieve()` 产出的字典列表（含 `chunk_id`/`content`/`score` 等）；返回同结构列表，额外加 `rerank_score`。
- 降级语义：**任何异常都回退到「原融合顺序」**，检索因重排失败而中断是禁止的。

### 4.2 DocumentParser（**扩展现有 `app/core/document_parser.py`**，非新建）

> **实现备注（偏差修正）**：代码核查发现 `app/core/document_parser.py` 的 `DocumentParser` + `parse_document()` **已存在且被 `/ingest` 使用**，已支持 `.docx`/`.pdf`/`.txt`/图片，且 PDF 的 OCR 回退已通过 **LLM 视觉服务**（`llm_service.ocr_image`，非 `pytesseract`）实现。因此本设计的「更多文档类型」工作**不是从零新建 parser**，而是**扩展现有 `document_parser`**：
> - 新增格式：`.md`/`.markdown`（当作纯文本）、`.pptx`（python-pptx）、`.xlsx`/`.xls`（openpyxl）。
> - PDF/OCR/Word/纯文本/图片 **已具备**，无需重做；OCR 沿用既有 LLM 视觉路径（故 `pytesseract` 从依赖中移除）。
> - 在所有 parser 返回中补充 `doc_format` 字段，供 `ingest` 落库。

```python
# 扩展点（在现有 DocumentParser 内新增方法 + 更新 SUPPORTED_EXTENSIONS 与 dispatch）
SUPPORTED_EXTENSIONS = [".docx", ".pdf", ".txt", ".md", ".markdown",
                        ".pptx", ".xlsx", ".xls",
                        ".png", ".jpg", ".jpeg", ".gif", ".webp"]

def _parse_md(self, file_bytes, filename) -> dict:   # 同 _parse_txt
def _parse_pptx(self, file_bytes, filename) -> dict:  # python-pptx 懒导入
def _parse_xlsx(self, file_bytes, filename) -> dict:  # openpyxl 懒导入
# 每个方法返回 {"success","text","filename","error","doc_format": "<ext>"}
```

- 全部**新增依赖懒导入**：`python-pptx`、`openpyxl`；缺依赖 → 该格式返回 `success=False` + warning（延续「门面永不上抛」）。
- Office 表格（PPT/Excel）：抽取文本框/单元格文本，保留自然阅读顺序。

### 4.3 KnowledgeService 改动（`app/knowledge/service.py`）

- `ingest(text, project_id, asset_id, title, source, doc_id=None)`（**返回值保持 `str` = doc_id，向后兼容现有 310 测试与调用方**）内部增加幂等逻辑：
  - `doc_id` 解析规则（优先级）：
    1. 显式传入 `doc_id` → 直接用；
    2. 否则若有 `source` → `sha256(f"{source}|{project_id}")[:16]`；
    3. 否则（纯文本且无 source）→ 退回 `_generate_id()` 随机 id（**保持当前文本入库「每次新建、不去重」行为**）。
  - 计算 `content_hash`（归一化正文 sha256）。
  - 命中旧 `doc_id` 且 `content_hash` 相同 → 跳过重建（幂等），仍返回该 `doc_id`。
  - 命中旧 `doc_id` 但 `content_hash` 不同 → 调 `delete_document(doc_id)` 级联清理 → 重新 `chunk`/索引 → `version+1`。
  - 新文档 → 现状插入 + `version=1`。
  - 说明：`ingest` 本身只返回 `doc_id`；命中「skipped / updated / ingested」的状态信息由下面的 `ingest_file` 负责返回，避免改动 `ingest` 签名波及既有调用。
- 新增 `ingest_file(path, project_id, ..., doc_id=None, source=None)`：先 `DocumentParser.parse` → 再 `ingest(...)`；`source` 默认取文件路径；返回 `{"doc_id", "status":"ingested"|"updated"|"skipped", "version":N}`（供 API 层透出）。
- `retrieve(query, top_k=5, project_id=None, rerank: Optional[bool]=None, rerank_top_n: int=20)`：
  - `rerank=None` → 取 `settings.RERANK_ENABLED`。
  - 召回池 `top_n = rerank_top_n`（默认 20，须 ≥ top_k）。
  - 若 `rerank` 开启：`rrf_fuse` 后取 top_n 候选 → `get_reranker().rerank(query, candidates, top_k)` → 截 top_k。
  - 若关闭：保持现行为（融合后直接截 top_k）。
- `delete_document` 已具备级联清理（fts/tfidf/vectors/chunks），复用即可。

---

## 5. 数据模型与迁移

`knowledge_docs` 表新增 3 列，**放进 `ensure_schema`**（`app/knowledge/schema.py`），用 `ALTER TABLE … ADD COLUMN` + try/except 实现幂等（老 SQLite 无 `ADD COLUMN IF NOT EXISTS`）：

```sql
ALTER TABLE knowledge_docs ADD COLUMN doc_format TEXT;   -- 'pdf'/'docx'/'md'/'ppt'/'xlsx'/'text'
ALTER TABLE knowledge_docs ADD COLUMN content_hash TEXT; -- 归一化正文 sha256
ALTER TABLE knowledge_docs ADD COLUMN version INTEGER DEFAULT 1;
```

- `source` 列已存在，复用。
- 旧库升级：已有行 `version` 默认 1、`doc_format` 默认 `text`、`content_hash` 默认 NULL（首次重入库时补齐）。
- 幂等：重复执行 `ensure_schema` 时 `ADD COLUMN` 抛 `DuplicateColumn` → 捕获吞掉。

`doc_id` 派生规则（优先级）：显式传入 > `sha256(f"{source}|{project_id}")[:16]`（有 source 时）> 退回随机 `_generate_id()`（纯文本无 source、无显式 id 时，保持每次新建不去重）。
`content_hash` 规则：`sha256(归一化正文)`，归一化 = 去多余空白 + 统一换行。

---

## 6. 接口/API 变更（`app/api/knowledge_api.py`）

- `POST /ingest`：新增可选 `file`/路径或 `doc_id` 字段；为兼容旧调用，保留 `text` 直传。新增 `doc_format` 由后端推断。
  - 返回体在 `data` 中携带 `status`（`ingested`/`updated`/`skipped`）与 `version`（沿用 `ApiResponse.ok` 信封，`success`/`data`/`code`，HTTP 始终 200）。
- `POST /retrieve` / `POST /ask`：新增可选 `rerank`（bool，默认读 settings）、`rerank_top_n`（int）。`/ask` 的 `RAGAnswerGenerator` 透传 rerank 开关。
- 受 `AuthMiddleware` 强制鉴权（既有行为不变）；测试仍用 `monkeypatch` 注入 `API_KEY` + `TestClient` 带 `Authorization: Bearer`。

---

## 7. 配置项（`app/core/config.py`）

| 配置 | 默认 | 说明 |
|------|------|------|
| `RERANK_PROVIDER` | `"none"` | `none`/`mock`/`local`/`cloud` |
| `RERANK_KEYS` | `""` | 云端 rerank 多 key（故障转移，复用既有模式） |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | 本地 cross-encoder 模型名 |
| `RERANK_TOP_N` | `20` | 重排候选池大小（须 ≥ top_k） |
| `RERANK_ENABLED` | `False` | `retrieve` 默认是否重排（None 时的兜底） |
| `OCR_ENABLED` | `True` | PDF OCR 总开关；关闭则纯文本层 |

---

## 8. 错误处理（延续「门面永不上抛」）

- 解析失败 / 缺依赖 → 返回 `""` + warning，`ingest` 走既有空文本短路（返回 None）。
- reranker 任何异常 → 降级「返回原融合顺序」；检索绝不因重排失败中断。
- DB `ADD COLUMN` 重复 → 捕获吞掉。
- 云 rerank 全部 key 失败 → 降级本地或原顺序。
- `rerank_top_n < top_k` → 内部 clamp 到 `top_k`，不报错。

---

## 9. 测试策略（对齐 C 级验收）

- **单测**：
  - 每个 parser（用小样本文件/字节构造）；缺依赖时降级返回空。
  - `Reranker` 三实现：`LocalCrossEncoderReranker` 失败降级、`CloudReranker` key 失败降级、`MockReranker` 确定性。
  - `doc_id` 派生 / `content_hash` 计算 / 幂等 `skipped` 与 `updated` 分支。
- **集成测**（沿用 `dependency_overrides` 注入临时库 + `monkeypatch` 注入 `API_KEY` + `RAG_LLM_PROVIDER=mock`）：
  - `ingest_file` → `retrieve` 全链路。
  - rerank on/off 对结果顺序的影响（`MockReranker` 确定性断言）。
- **质量对比**（C 级核心）：
  - 扩展 `RAGEvaluator`：对小 gold 集分别跑 `rerank=False` 与 `rerank=True`，输出 `precision@k`/`recall@k` 前后对比，断言「**不劣化**」（mock 环境下确定性）。
- **性能守护**（C 级核心）：
  - `MockReranker` 重排 100 候选的耗时上界断言，防止实现引入意外的 O(n²)。
- **纪律**：全量回归保持绿（当前 310 passed / 2 skipped），绝不触碰漂移文件（`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`）。

---

## 10. 分片交付计划

**Slice 1（快赢，先转绿）**
- `Reranker` 接口 + `MockReranker` + `LocalCrossEncoderReranker`（降级路径）。
- `DocumentParser`：PDF（不含 OCR）/ Word / Markdown / 纯文本。
- `KnowledgeService.ingest` 幂等 + DB 加列迁移 + `ingest_file`。
- `retrieve` 接入 rerank 开关；`/ingest`、`/retrieve`、`/ask` 参数透传。
- 单测 + 集成测 + 全量回归绿。

**Slice 2（补全能力）**
- `CloudReranker`（Cohere/Jina + 多 key 故障转移）。
- PDF **OCR**（`pytesseract` 可选依赖）。
- PPT/Excel 解析器。
- `RAGEvaluator.compare_before_after` + 小 gold 集 + 性能 P95 守护测试。
- 验收报告（precision@k/recall@k 前后对比 + 延迟预算）。

---

## 11. 依赖（全部可选 / 懒导入）

| 包 | 用途 | 必需 |
|----|------|------|
| `sentence-transformers` | 本地 cross-encoder rerank | 否（缺则降级） |
| `python-pptx` | PPT 解析（**新增**） | 否（缺则 PPT 降级） |
| `openpyxl` | Excel 解析（**新增**） | 否（缺则 Excel 降级） |
| `pdfplumber` / `pymupdf` / `Pillow` / `python-docx` | PDF/OCR/Word（**已存在**） | 否（缺则对应格式降级） |

> **移除 `pytesseract`**：OCR 已通过既有 LLM 视觉服务（`llm_service.ocr_image`）实现，无需本地 tesseract。
> 所有依赖**懒导入**，不装也能跑（对应功能降级）；测试用 mock 不需要真实安装重模型。

**新增格式支持（扩展 `app/core/document_parser.py`）**：`.md`/`.markdown`（纯文本）、`.pptx`（python-pptx）、`.xlsx`/`.xls`（openpyxl）。PDF/OCR/Word/纯文本/图片沿用现有实现。

---

## 12. 验收标准（C 级）

1. `ingest_file` 对 PDF/Word/MD/纯文本 入库成功；rerank 开启后 `retrieve` 顺序相对关闭态有可解释变化。
2. 同一文件重复 `ingest_file`：hash 未变 → `status=skipped`（无新 chunk 堆积）；hash 变更 → `status=updated` 且 `version+1`，旧 chunk 被级联清理。
3. `RAGEvaluator.compare_before_after` 在 mock 环境下断言 rerank **不劣化** precision@k/recall@k。
4. `MockReranker` 重排 100 候选耗时低于 P95 预算（如 50ms，按实现微调）。
5. 全量回归 310+ passed / 0 failed，漂移文件未提交。

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 本地 cross-encoder 首次下载权重慢/无网络 | 懒加载 + 失败降级原序；默认 `RERANK_PROVIDER=none` |
| 解析依赖缺失导致某格式不可用 | 懒导入 + 缺依赖返回空 + warning；单测覆盖降级分支 |
| 加列迁移在老库上重复执行报错 | `ALTER TABLE` 包 try/except 幂等 |
| rerank 引入 O(n²) 拖慢检索 | 性能 P95 守护测试 + 候选池 clamp |
| 增量更新误删 chunk | 复用既有 `delete_document` 级联逻辑 + 单测覆盖 skipped/updated |

---

## 14. 落地规划前需最终确认的默认值

- `RERANK_PROVIDER` 默认 `"none"`（关闭）是否合理，还是默认 `"mock"` 让测试默认走 mock 重排？
- 本地 cross-encoder 默认模型：`BAAI/bge-reranker-v2-m3` 是否合适（~1.1GB，CPU 可用但慢）？或改用更轻的 `ms-marco-MiniLM-L-6-v2`（~80MB）作默认？
- `RERANK_TOP_N` 默认 20 是否合适（影响延迟与召回质量）？

> 上述默认值可在「编写实施计划」阶段结合实际环境最终敲定，不影响本设计架构。
