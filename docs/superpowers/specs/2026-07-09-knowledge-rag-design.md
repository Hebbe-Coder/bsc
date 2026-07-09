---
title: 导出与生成增强 · 统一知识中台（RAG）
status: approved
created: 2026-07-09
author: WorkBuddy
direction: 统一知识中台 / 检索增强生成（RAG）
---

# 统一知识中台（RAG）设计文档

## 1. 背景与目标

BSC Engine v7 的 PRD → business_system 生成管线当前**无任何检索增强**：每个请求都从零让 LLM 凭空生成，缺乏对企业历史报告、制度文档、SOP、模板等事实资产的复用，易出现幻觉、与企业规范不一致、重复造轮。

项目已具备部分基础但未打通：
- `app/repositories/knowledge_repository.py`：已有 `KnowledgeRepository`（`knowledge_index` 表 + `index_knowledge`/`search_knowledge`），但检索是**纯 SQL `LIKE` 子串匹配**，无向量、无语义。
- `app/schemas/graph_schema.py`：企业知识图谱模型（process/role/metric/system/strategy/risk 节点），但尚未接入检索。
- `app/services/llm_service.py`：已有 **numpy TF-IDF 域向量机制**（构建词表/IDF、cosine 相似度做域分类）——证明项目偏好「零重依赖、可离线」的向量方案。
- `app/core/document_parser.py`：已能解析上传文档/资产为纯文本。

**本方向目标**：把历史报告 + 上传文档 + 模板 + 知识图谱，打通成一个**统一可检索的知识层**（中台愿景），首版本轮落地「摄取 → 混合检索 → agent 工具注入」的完整骨架，检索管线一步到位（BM25 + TF-IDF + RRF 重排），语料先接**上传文档/资产**。

### 目标（In Scope）
- 统一 `KnowledgeService` 门面 + 可插拔后端注册表。
- 混合检索：KeywordBackend（FTS5/BM25） + TfidfBackend（numpy TF-IDF cosine） + HybridReranker（RRF）。
- 上传文档 → `document_parser` → `Chunker` → 双后端索引 → SQLite 落库。
- `RetrieveTool`：LangChain tool，agent 自主调用，格式化上下文回流 prompt。
- 全离线、确定性测试矩阵（14 例）。

### 非目标（Out of Scope，本版不做）
- 稠密 embedding 模型（sentence-transformers / Ollama embedding）——首版用 numpy TF-IDF，接口预留 Vector 后端。
- 知识图谱（graph_schema）接入检索——图谱表保留不动，后续作第三类后端。
- 分节精准注入 / 引用补全 / 自动评估 RAG 质量——首版仅全局工具注入 + 出处标注。
- 多语言分词优化（jieba）——trigram tokenizer 对中英文子串已有效，分词优化留扩展。
- 实时/流式摄取、增量 TF-IDF 更新——首版全量重算模型。

## 2. 决策摘要

| 决策点 | 选择 | 理由 |
|---|---|---|
| 核心目标 | 统一知识中台 | 历史报告+文档+模板+图谱统一可检索 |
| 检索路线 | 混合（BM25 + TF-IDF + RRF） | 语义+关键词互补，零新依赖 |
| 向量语义 | numpy TF-IDF（复用 llm_service） | 零重依赖、可离线，与现有 infra 一致 |
| 首版语料 | 上传文档/资产为主（复用 document_parser） | 数据现成，对应「补全领域知识」 |
| 注入位置 | 检索即工具（agent 自主调用） | 检索层与生成层解耦 |
| 架构形态 | 统一 Service + 可插拔后端注册表 | 中台骨架，后端可增量接入 |
| Reranker | RRF 倒数排名融合 | 对分数尺度不敏感、稳定 |
| 向量存储 | BLOB（numpy `tobytes()`） | 热路径省空间、读取快 |
| 无结果行为 | 注入「未检索到相关知识」提示 | 透明，便于显式无引用声明 |
| 测试语料 | 内联样例文本 | 零外部文件依赖、最快最稳 |

## 3. 架构总览（§1）

```
上传文档/资产
   → document_parser 解析为纯文本（复用 app/core/document_parser.py）
   → Chunker 切分为 chunk（带 metadata: doc_id / section / offset）
   → KnowledgeService.ingest()
        ├─ KeywordBackend  → 写入 FTS5 虚拟表（BM25 评分）
        └─ TfidfBackend    → numpy TF-IDF 向量 → 存入 vectors 表
   → 落库（SQLite，复用 KnowledgeRepository 基类）

Agent 运行时自主调用 retrieve 工具
   → KnowledgeService.retrieve(query)
        = KeywordBackend.search(BM25) + TfidfBackend.search(cosine)
        → HybridReranker 融合重排（RRF） → top-k chunks
   → 格式化为上下文文本回流给 agent
```

**两个关键解耦点**：
1. **检索层与生成层解耦**：检索是纯库（`KnowledgeService`），生成是 agent，两者只通过「`retrieve` 工具」连接，互不侵入。
2. **摄取与检索解耦**：ingest 一次建好两类索引，retrieve 时再融合，新增后端不影响已有逻辑。

**依赖约束**：FTS5 为 SQLite 内置（已验证运行环境 SQLite 3.45.3 启用 FTS5），TF-IDF 走 numpy（已装 2.5.1）。整体**零新依赖、可离线**。旧 `knowledge_index`（LIKE 表）保留不删作兼容，新摄取只写新表。

## 4. 组件（§2）

**摄取侧（ingest 时调用）**
- **`Chunker`** (`app/knowledge/chunker.py`)：输入 `document_parser` 产出的纯文本，按段落/标题结构 + 长度上限（默认 500 字）切分为 `Chunk(content, section, meta)`。不破坏语义边界（不在句子中间切）。
- **`KeywordBackend`** (`app/knowledge/backends/keyword.py`)：把 chunk 写入 FTS5 虚拟表（`tokenize=trigram`），提供 `search(query) -> [(chunk_id, bm25_score)]`。FTS5 不可用则退回 LIKE（复用现有 `search_knowledge` 逻辑），仍提供同一接口。
- **`TfidfBackend`** (`app/knowledge/backends/tfidf.py`)：复用 `llm_service` 现有 TF-IDF 模式——构建全局 vocab/IDF，chunk 与 query 各算 numpy 向量，`search(query) -> [(chunk_id, cosine)]`。向量存 SQLite BLOB。模型未建时优雅返回空。

**检索侧（agent 运行时调用）**
- **`HybridReranker`** (`app/knowledge/reranker.py`)：实现 **RRF**（Reciprocal Rank Fusion）：
  `RRF(d) = Σ_i 1 / (k + rank_i(d))`，`k` 默认 60。对分数尺度不敏感，对部分缺失的 ranklist 鲁棒（缺失后端贡献 0）。
- **`KnowledgeService`** (`app/knowledge/service.py`)：门面 `ingest(raw_doc)` / `retrieve(query, top_k, filters)`；后端用**可插拔注册表**（首版注册 Keyword + Tfidf，后续加 Vector 后端不改门面）。
- **`RetrieveTool`** (`app/knowledge/tool.py`)：LangChain tool `knowledge_retrieve(query: str, top_k: int = 5) -> str`，把 top-k chunk 格式化成上下文文本，注册到 `unified_agent` / `studio_orchestrator` 工具集，agent 自主决定何时查。

## 5. 存储（§3）

新增 4 张表，挂在同一 SQLite 库（复用 `KnowledgeRepository` 基类）。现有的 `knowledge_entities` / `knowledge_versions`（图谱）完全不动；旧 `knowledge_index`（LIKE 表）保留不删。

```sql
CREATE TABLE knowledge_docs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    asset_id    TEXT,
    title       TEXT,
    source      TEXT,
    created_at  TEXT
);

CREATE TABLE knowledge_chunks (
    id            TEXT PRIMARY KEY,
    doc_id        TEXT REFERENCES knowledge_docs(id),
    idx           INTEGER,
    content       TEXT,
    section       TEXT,
    metadata_json TEXT
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    content, doc_id UNINDEXED, chunk_id UNINDEXED, tokenize='trigram'
);

CREATE TABLE knowledge_tfidf (
    chunk_id TEXT PRIMARY KEY REFERENCES knowledge_chunks(id),
    vector   BLOB
);

CREATE TABLE tfidf_model (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    vocab_json TEXT,
    idf_json   TEXT
);
```

chunk 向量用 **BLOB**（numpy `tobytes()`）——检索热路径省空间、读取快。所有写入走 `KnowledgeRepository`（`BaseRepository`），不绕开事务。

## 6. 数据流（§4）

**摄取流（ingest，离线/事件触发）**
```
上传资产到达 API
   → document_parser.parse(asset)               # 复用 app/core/document_parser.py
   → Chunker.chunk(text)                        # List[Chunk]
   → KnowledgeService.ingest(doc_meta, chunks)
        ├─ KnowledgeRepository 写 knowledge_docs 一行
        ├─ 批量写 knowledge_chunks（含 metadata_json）
        ├─ KeywordBackend.index(chunks)          # 写 knowledge_fts
        ├─ TfidfBackend.index(chunks)            # 重算 tfidf_model（vocab/idf 全局）+ 写 knowledge_tfidf
        └─ 返回 doc_id
```
TF-IDF 为全局模型：每 ingest 一篇新文档，vocab/IDF 重算并覆盖 `tfidf_model` 表。首版语料规模小，重算成本可忽略。

**检索流（retrieve，agent 运行时）**
```
agent 调 knowledge_retrieve(query, top_k=5)
   → RetrieveTool.knowledge_retrieve
        → KnowledgeService.retrieve(query, top_k, filters)
             ├─ KeywordBackend.search(query)     # FTS5 BM25
             ├─ TfidfBackend.search(query)       # numpy cosine
             ├─ HybridReranker.fuse(ranklists, method="rrf")
             └─ top-k chunk_id → 回查 knowledge_chunks 得 content
        → 格式化为带出处标注的上下文文本
   → 回流给 agent 注入 prompt
```

**格式化上下文形态（agent 拿到的样子）**
```
[知识 1] 出处：<doc_title> / 第 N 段
<chunk.content>

[知识 2] 出处：<doc_title> / 第 N 段
<chunk.content>
```
带出处标注，便于 agent 引用、也便于后续「引用补全」扩展。

**默认约定（已确认）**：retrieve 支持 `project_id` 过滤（多租户隔离）；`section`/`tag` 过滤留扩展。触发粒度由 agent 自主决定（检索即工具）。

## 7. 错误处理（§5）

设计哲学与现有 `degrade` 层一致：**检索层只保证「内容合法、不崩溃」，基础设施级失败由上层兜底**。检索是「增强」而非「必需」——拼不上知识库，生成也应照常进行。

**摄取侧**
| 场景 | 处理 |
|---|---|
| 解析失败（不支持格式 / document_parser 抛错） | 跳过该文档，记日志 + 返回 doc_id=None，不影响其他 |
| 空文本（解析出 0 字符） | 跳过，不建索引 |
| FTS5 写入失败 | 捕获，keyword 后端标记不可用，仍继续建 TF-IDF |
| TF-IDF 模型重算失败 | 捕获，复用上一版 tfidf_model；新 chunk 用旧模型兜底 |

**检索侧**
| 场景 | 处理 |
|---|---|
| 空语料 / 库无数据 | 返回空 + 提示「未检索到相关知识」，agent 无上下文继续 |
| 查询过短 / 空 query | 直接返回空，不查 |
| TF-IDF 模型未建 | TfidfBackend 返回空，Reranker 只吃 keyword |
| FTS5 虚表不可用 | KeywordBackend 返回空，Reranker 只吃 TF-IDF |
| 两后端都空 | 返回空提示，agent 不中断 |
| 工具调用异常 | 捕获并返回安全提示文本，agent 不崩 |

**三层原则**：
1. **绝不向上抛**——`retrieve`/`ingest` 所有异常在 `KnowledgeService` 内层捕获，对外只返回「合法结果或空」。
2. **降级而非中断**——单后端挂了，另一后端结果仍可用（Reranker 对部分缺失的 ranklist 鲁棒）。
3. **与现有 degrade 正交**——若整个知识库依赖（SQLite/磁盘）不可用，那是基础设施失败，由上游 orchestrator 的现有 degrade 机制兜底；知识层自身只管内容层健壮。

无结果时**注入提示**（「未检索到相关知识」），而非静默空串——更透明，便于显式无引用声明。

## 8. 测试（§6）

全离线、确定性（无网络、无 LLM 调用），落 `tests/knowledge/`。语料用**内联样例文本**（测试中直接构造中英文样例，零外部文件依赖）。

**单元测试**
1. `test_chunker_basic`：多段落/标题样例 → 切分数量正确、不切断句子、section 标注正确。
2. `test_chunker_long_paragraph`：超长单段 → 按上限切分、offset 连续。
3. `test_keyword_backend_bm25`：摄取若干 chunk → 相关 query BM25 排序合理（命中词 > 未命中词）。
4. `test_tfidf_backend_cosine`：已知 vocab → 相似 chunk cosine 高、无关低。
5. `test_tfidf_idf`：稀有词 IDF 高于常见词。
6. `test_reranker_rrf`：两份 ranklist → RRF 融合顺序符合倒数排名公式、对分数尺度不敏感。

**集成测试**
7. `test_ingest_then_retrieve`：摄取样例文档 → retrieve(相关 query) 命中正确 chunk。
8. `test_retrieve_project_filter`：retrieve(query, project_id=X) 只返回 X 项目 chunk，隔离生效。
9. `test_hybrid_beats_single`：混合检索 top-1 命中，优于单独 keyword 或单独 tfidf 的某些 case。

**工具测试**
10. `test_retrieve_tool_format`：`knowledge_retrieve(query)` 返回带 `[知识 N] 出处：...` 标注文本。
11. `test_retrieve_tool_empty`：空语料 → 返回「未检索到相关知识」安全提示、不崩。

**健壮性测试**
12. `test_ingest_parse_failure_skips`：喂解析失败文档 → ingest 跳过、不抛、其他正常。
13. `test_retrieve_no_model_safe`：未摄取（无 tfidf_model）→ retrieve 返回空提示、不崩。
14. `test_backend_failure_degrades`：模拟某后端抛错 → 另一后端结果仍返回、Reranker 鲁棒。

## 9. 任务拆分（供 writing-plans 参考）

| 任务 | 内容 | 测试 |
|---|---|---|
| T1 | `Chunker`（`app/knowledge/chunker.py`） | 单元测试 1–2 |
| T2 | `KeywordBackend` + FTS5 表（`app/knowledge/backends/keyword.py`） | 单元测试 3 |
| T3 | `TfidfBackend` + 模型/向量表（`app/knowledge/backends/tfidf.py`） | 单元测试 4–5 |
| T4 | `HybridReranker`（RRF，`app/knowledge/reranker.py`） | 单元测试 6 |
| T5 | `KnowledgeService` 门面 + 可插拔注册表（`app/knowledge/service.py`） | 集成 7–9 |
| T6 | `RetrieveTool` + 接入 agent 工具集（`app/knowledge/tool.py`） | 工具 10–11 |
| T7 | 错误处理加固（摄取/检索降级、无结果注入） | 健壮性 12–14 |
| T8 | 全量回归（既有套件无回归） | — |

## 10. 风险与权衡

- **TF-IDF 非真稠密语义**：对同义/改写召回弱。接口已预留 Vector 后端，后续接入不破架构。
- **全局 TF-IDF 重算**：语料变大后 ingest 变慢。首版规模小可接受；后续可改增量更新。
- **FTS5 依赖 SQLite 编译**：运行环境已验证可用（3.45.3）。若部署环境无 FTS5，KeywordBackend 退回 LIKE，接口不变。
- **agent 工具自主性的不可控**：agent 可能不调或滥调。首版不限制；可在 tool 描述里写清用途，后续加调用预算/审计。
- **摄取与现有 knowledge_index 并存**：短期双写冗余，长期迁移后废弃旧表。
