---
title: 知识库 RAG 增强 · 稠密向量检索后端（远程 embedding API）
status: approved
created: 2026-07-09
author: WorkBuddy
direction: 知识库 RAG 增强 / 稠密向量检索（Dense Vector Retrieval）
depends_on: 2026-07-09-knowledge-rag-design.md
---

# 稠密向量检索后端设计文档

## 1. 背景与目标

`2026-07-09-knowledge-rag-design.md` 已落地统一知识中台的混合检索骨架：
`KeywordBackend`（FTS5 BM25）+ `TfidfBackend`（numpy TF-IDF cosine）+ `HybridReranker`（RRF）。
但 TF-IDF 是**词面稀疏向量**，对**同义改写、跨语言、语义近义**召回弱——这是设计文档自己列出的头号风险。

本方向目标：在既有 `KnowledgeService` 可插拔后端注册表里，**新增第三类后端 `VectorBackend`**，
用**稠密 embedding 向量**补足语义召回。embedding 来源采用**远程 OpenAI 兼容 `/v1/embeddings` 端点**
（OpenAI / 自托管 vLLM / 任意兼容服务），即用户选定的「远程 embedding API」路线。

### 目标（In Scope）
- 抽象 `EmbeddingProvider`：默认 `MockEmbeddingProvider`（离线、确定性，用于测试与零配置运行）+ `RemoteEmbeddingProvider`（远程真语义）。
- `VectorBackend`：与 `KeywordBackend`/`TfidfBackend` **同接口**（`index(chunk_records)` / `search(query) -> List[chunk_id]`），按余弦排序返回 chunk_id。
- 接入 `KnowledgeService`：注册为 `"vector"` 后端；`retrieve()` 将 `vec_ids` 作为第三路并入 `rrf_fuse([kw_ids, tf_ids, vec_ids])`。
- 增量索引：embedding 是 per-chunk 独立计算（无全局词表），`index` 仅处理传入的新 chunk，优于 TF-IDF 全量重算。
- 新存储表 `knowledge_vectors`（BLOB 存 `np.float32` 向量 + model 名 + dim）。
- 全离线、确定性测试矩阵（8 例），远程 provider 用注入式 fake client 测（与 `sop_llm_client` 测试方式一致）。

### 非目标（Out of Scope，本版不做）
- 本地 sentence-transformers / Ollama 模型：本期只做远程 + mock；但 `EmbeddingProvider` 接口已预留，未来加本地 provider 不破架构。
- 知识图谱（graph_schema）检索后端：仍为独立后续方向。
- RRF 升级为学习式/cross-encoder 重排：本期维持 RRF（对分数尺度不敏感、稳定）。
- 引用溯源 / 分节精准注入 / RAG 质量自动评估：沿用既有「带出处标注」格式，不扩展。
- embedding 维度自适应 / 量化压缩：本期用 `float32` 原样存储。
- 切换 embedding 模型后的自动 reindex：本期仅「按 model 名隔离旧向量（优雅降级）」，reindex 留接口。

## 2. 决策摘要

| 决策点 | 选择 | 理由 |
|---|---|---|
| 增强方向 | 稠密向量检索后端 | 补齐 TF-IDF 同义/改写召回短板 |
| embedding 来源 | 远程 OpenAI 兼容 `/v1/embeddings` | 用户选定；高质量、无需本地算力 |
| 默认 provider | `mock`（确定性哈希向量） | 零配置可跑、266 测试离线不受影响 |
| 真实 provider 启用 | `EMBEDDING_PROVIDER=openai` + key/url/model | 与 SOP 客户端多厂商+mock 模式一致 |
| 向量存储 | BLOB（`np.float32.tobytes()`） | 热路径省空间、读取快，与 TF-IDF 表一致 |
| 索引策略 | 增量（仅新 chunk） | embedding 无全局词表，无需重算 |
| 模型隔离 | 按 model 名过滤 | 切换模型后旧向量自动忽略，不崩 |
| 远程失败行为 | 降级回 mock，不向上抛 | 与既有 degrade 哲学一致 |
| 搜索融合 | RRF 第三路 | 复用现有重排，对分数尺度不敏感 |

## 3. 架构总览

```
摄取（ingest，离线/事件触发）
   → Chunker.chunk(text)                      # 复用现有
   → KnowledgeService.ingest(doc_meta, chunks)
        ├─ KeywordBackend.index(records)      # FTS5（不变）
        ├─ TfidfBackend.index(records)        # 全局 TF-IDF 重算（不变）
        └─ VectorBackend.index(records)       # 新增：批量 embed 新 chunk → knowledge_vectors
   → 任一后端失败不影响其他（各自容错）

检索（retrieve，agent 运行时）
   → KnowledgeService.retrieve(query, top_k, project_id)
        ├─ KeywordBackend.search(query)       # BM25 → chunk_id 排名
        ├─ TfidfBackend.search(query)         # cosine → chunk_id 排名
        ├─ VectorBackend.search(query)        # 新增：embed query → cosine → chunk_id 排名
        └─ rrf_fuse([kw_ids, tf_ids, vec_ids]) → top-k chunk_id → 回查 content
   → 格式化为带出处标注的上下文（不变）

EmbeddingProvider 抽象（隔离「文本→向量」）
   MockEmbeddingProvider   → 确定性哈希向量（离线）
   RemoteEmbeddingProvider → POST {base_url}/embeddings（远程真语义，失败降级 mock）
```

**关键解耦点**（与既有一致）：
1. 检索层与生成层解耦：`VectorBackend` 仍是纯库，只通过 `retrieve` 工具回流。
2. 摄取与检索解耦：ingest 建好三类索引，retrieve 时再融合，新增后端不改门面。
3. **embedding 来源与后端解耦**：`VectorBackend` 只依赖 `EmbeddingProvider` 接口，换远程/本地/mock 不碰后端代码。

**依赖约束**：numpy 已装（TF-IDF 在用）；`httpx` 已装（sop_llm_client 在用）。远程调用走注入式 `httpx.Client`（与 client 测试一致）。**零新重依赖**。

## 4. 组件

**Embedding 层（新增 `app/knowledge/embeddings.py`）**
- `EmbeddingProvider`（抽象基类）：
  - `embed(texts: List[str]) -> List[List[float]]`：批量将文本转为向量。
  - `dim: int`：向量维度（mock 固定 256；remote 在首次成功响应后确定，或从配置推断）。
  - `name: str`：provider 标识（用于 `knowledge_vectors.model` 隔离）。
  - `batch_embed(texts)` 为 `embed` 的别名/默认实现。
- `MockEmbeddingProvider`：
  - 确定性：对文本做 tokenize → 词哈希映射到固定 `dim`（默认 256）桶 → 计数 → L2 归一化。
  - 相同输入恒得相同向量；无外部依赖；`name="mock"`。
  - 注意：mock 非真语义，仅保证架构可跑与测试确定性；真实语义靠 RemoteProvider。
- `RemoteEmbeddingProvider`：
  - 构造：`base_url`、`api_key`、`model`、`timeout=30.0`、`http_client=None`（可注入）。
  - `embed(texts)`：`POST {base_url}/embeddings`，`json={"model": model, "input": texts}`，`headers={"Authorization": "Bearer {api_key}", "Content-Type": "application/json"}`。
  - 解析 `resp.json()["data"][i]["embedding"]`（按 `index` 对齐顺序）。
  - **失败降级**：`httpx.HTTPError` / 非 2xx / 解析异常 → `logger.warning` 后用 `MockEmbeddingProvider` 兜底返回向量（不抛），保证检索不中断。
  - `name="openai"`（协议标识；端点可指向任意兼容服务）。
- 工厂 `get_embedding_provider(provider=None, **kw)`：
  - `provider=None` → 读 `settings.EMBEDDING_PROVIDER`（默认 `"mock"`）。
  - `"mock"` → `MockEmbeddingProvider()`；`"openai"` → `RemoteEmbeddingProvider(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL, model=settings.EMBEDDING_MODEL)`。
  - 其余值 → 抛 `ValueError`（与 SOP 客户端一致，明确报错）。

**向量后端（新增 `app/knowledge/backends/vector.py`）**
- `VectorBackend`：
  - `__init__(self, repo, provider=None)`：懒加载 provider（首次 `index`/`search` 时 `get_embedding_provider()`）。
  - `index(self, chunk_records: List[dict]) -> None`：
    - 入参同 `KeywordBackend`（`id`/`content`/`doc_id`）。
    - 仅对传入 chunk 计算向量（增量）：`texts = [r["content"] for r in chunk_records]`；`vectors = provider.embed(texts)`。
    - 逐条写入 `knowledge_vectors(chunk_id, model=provider.name, dim, vector=np.float32(v).tobytes())`，`INSERT OR REPLACE`。
    - 单条 embed 失败 → 跳过该 chunk，其余照常（不中断）。
    - 整批失败（provider 彻底不可用）→ 捕获，`logger.warning`，返回（向量后端为空，不影响其他后端）。
  - `search(self, query: str, limit: int = 20) -> List[str]`：
    - 空 query → 返回 `[]`。
    - `qv = np.array(provider.embed([query])[0], dtype=np.float64)`。
    - 取 `knowledge_vectors WHERE model = provider.name` 的全部向量，逐条 `np.frombuffer(..., np.float32)` → 余弦 → 收集 `(chunk_id, sim)`。
    - 按 sim 降序，返回 top `limit` 的 `chunk_id` 列表（与 keyword/tfidf 返回形态一致）。
    - provider 不可用 → 返回 `[]`（RRF 退化为两路）。

**服务门面改动（`app/knowledge/service.py`）**
- `__init__`：`self.backends` 增加 `"vector": VectorBackend(self.repo)`。
- `ingest`：`try: self.backends["vector"].index(chunk_records) except Exception as e: logger.warning(...)`（排在所有后端之后，容错包裹）。
- `retrieve`：
  ```python
  kw_ids = self.backends["keyword"].search(query)
  tf_ids = self.backends["tfidf"].search(query)
  vec_ids = self.backends["vector"].search(query)
  fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
  ```
- `delete_document`：循环 `chunk_ids` 时增 `DELETE FROM knowledge_vectors WHERE chunk_id=?`。

## 5. 存储

在 `app/knowledge/schema.py` 的 `_SCHEMA` 列表中新增一张表（与现有 4 张并存，不动旧表）：

```sql
CREATE TABLE IF NOT EXISTS knowledge_vectors (
    chunk_id TEXT PRIMARY KEY,
    model     TEXT,
    dim       INTEGER,
    vector    BLOB
);
```

- `model` 用于隔离不同 embedding 模型产生的向量（切换模型后旧向量不匹配，搜索时按当前 `provider.name` 过滤，自动忽略）。
- `vector` 存 `np.float32.tobytes()`；搜索时 `np.frombuffer(..., np.float32)` 还原。
- 写入走 `KnowledgeRepository`（`BaseRepository`），不绕开事务。

## 6. 数据流

**摄取流（增量，仅新 chunk）**
```
KnowledgeService.ingest(text, project_id, ...)
   → chunk_text(text) → chunks
   → 写 knowledge_docs 一行 + knowledge_chunks（含 metadata_json）
   → KeywordBackend.index(records)     # FTS5
   → TfidfBackend.index(records)       # 全局 TF-IDF 重算
   → VectorBackend.index(records)      # 批量 embed 仅这些 records → knowledge_vectors
   → 返回 doc_id
```

**检索流（三路融合）**
```
agent 调 knowledge_retrieve(query, top_k=5)
   → KnowledgeService.retrieve(query, top_k, project_id)
        ├─ keyword.search → kw_ids（BM25 排名）
        ├─ tfidf.search   → tf_ids（cosine 排名）
        ├─ vector.search  → vec_ids（cosine 排名，语义）
        └─ rrf_fuse([kw_ids, tf_ids, vec_ids]) → top-k chunk_id
   → 回查 knowledge_chunks 得 content + doc_title → 带出处标注文本回流
```

**默认约定（沿用）**：retrieve 支持 `project_id` 过滤（多租户隔离）；`section`/`tag` 过滤留扩展。向量后端同样受 `project_id` 过滤（在 `retrieve` 回查阶段统一过滤，不在向量表内做，保持后端纯粹）。

## 7. 错误处理

哲学与既有 `degrade` 层一致：**向量层只保证「内容合法、不崩溃」，基础设施级失败由上层兜底**。
检索是「增强」而非「必需」——拼不上向量库，生成也应照常进行。

**摄取侧**
| 场景 | 处理 |
|---|---|
| 单 chunk embed 失败 | 跳过该 chunk，记录 warning，其余正常建索引 |
| 整批 embed 失败（provider 不可用） | 捕获，记录 warning，向量后端为空，不影响 keyword/tfidf |
| 远程 HTTP 错误 / 超时 | `RemoteEmbeddingProvider` 内部降级回 mock 返回向量（不抛） |

**检索侧**
| 场景 | 处理 |
|---|---|
| 空语料 / 库无向量 | 返回空，RRF 退化为 keyword+tfidf 两路 |
| 空 query / 过短 | 直接返回空，不查 |
| 远程调用失败 | provider 降级 mock，向量可能相关性差但仍返回；或返回空 → RRF 退化 |
| model 不匹配（切换了 embedding 模型） | 按 `provider.name` 过滤，旧向量忽略，返回空（降级） |
| 工具调用异常 | 捕获返回安全提示文本，agent 不崩（沿用现有 tool 容错） |

**三层原则**（与既有一致）：
1. 绝不向上抛——`index`/`search` 内层捕获，对外只返回「合法结果或空」。
2. 降级而非中断——单后端挂了，其他后端结果仍可用（RRF 对部分缺失 ranklist 鲁棒）。
3. 与现有 degrade 正交——若 SQLite/磁盘不可用，由上游 orchestrator 既有 degrade 兜底。

## 8. 测试

全离线、确定性（无网络、无真实 LLM/embedding 调用）。远程 provider 用**注入式 fake `httpx.Client`**（与 `test_sop_llm_client.py` 一致）。语料用内联样例文本。落 `tests/knowledge/`。

**Embedding 层单元测试**
1. `test_mock_provider_deterministic`：相同文本两次 `embed` 得完全相同向量；不同文本向量不同。
2. `test_mock_provider_normalized`：输出向量 L2 范数 ≈ 1。
3. `test_remote_provider_request`：注入 fake client，断言请求 URL 为 `{base_url}/embeddings`、含 `Authorization: Bearer <key>`、`json.model == settings.EMBEDDING_MODEL`、`input` 为文本列表。
4. `test_remote_provider_parse`：fake 返回 `{"data":[{"index":0,"embedding":[...]},...]}` → `embed` 返回按 index 对齐的向量列表。
5. `test_remote_provider_fallback_on_error`：fake 抛 `httpx.HTTPError` 或返回 500 → `embed` 不抛，降级回 mock 向量（形态合法）。

**VectorBackend 测试**
6. `test_vector_index_and_search_cosine`：摄取若干 chunk → `search(相关 query)` 返回余弦降序的 chunk_id；相关 chunk 排名高于无关。
7. `test_vector_beats_keyword_on_paraphrase`：构造同义/改写 query（如「客户投诉处理」vs chunk 原文「用户反馈应对流程」），断言 vector 路能命中而 keyword 路漏召回，验证补齐 TF-IDF 短板。
8. `test_vector_incremental`：ingest 第二篇文档后，第一篇 chunk 的向量仍可被搜到（验证增量，不重建旧向量）。

**集成 / 容错测试**
9. `test_retrieve_fuses_three_ways`：摄取后 `retrieve(query)` 结果中 `rrf_fuse` 实际吃到 `vec_ids`（可用 mock provider 制造可控向量验证三路融合顺序）。
10. `test_remote_unavailable_retrieve_still_works`：模拟 remote provider 全失败 → vector 返回空 → `retrieve` 仍返回 keyword+tfidf 结果，不崩。
11. `test_delete_clears_vectors`：`delete_document` 后对应 chunk 的 `knowledge_vectors` 行被清除。

**健壮性**
12. `test_empty_query_returns_empty`：`search("")` / `retrieve("")` 返回空列表。

## 9. 任务拆分（供 writing-plans 参考）

| 任务 | 内容 | 测试 |
|---|---|---|
| T1 | `EmbeddingProvider` 抽象 + `MockEmbeddingProvider` + 工厂（`app/knowledge/embeddings.py`） | 1–2 |
| T2 | `RemoteEmbeddingProvider`（请求构造/解析/降级） | 3–5 |
| T3 | `VectorBackend`（`app/knowledge/backends/vector.py`，增量 index / cosine search） | 6–8 |
| T4 | `knowledge_vectors` 表 + `schema.py` 扩展 | — |
| T5 | `KnowledgeService` 接入（注册/ingest/retrieve/delete 四处改动） | 9–12 |
| T6 | config.py 新增 `EMBEDDING_*` 配置 | — |
| T7 | 全量回归（既有套件无回归） | — |

## 10. 风险与权衡

- **依赖网络/key**：真实语义需远程 embedding 服务可用；`mock` 默认保证离线不崩、测试确定性。切换为 `openai` 且 key 无效时，provider 内部降级 mock（相关性差但不崩）。
- **远程延迟**：ingest 批量 embed 摊薄成本；检索单次 query 一次 embed 调用。对超大语料可后续加并发/缓存。
- **model 切换需重建**：改 `EMBEDDING_MODEL` 后旧向量失配，按 model 名隔离自动忽略旧向量（降级为空）。reindex 接口本期留待后续（提供 `VectorBackend.reindex(repo)` 可后续加）。
- **mock 非真语义**：mock 是哈希向量，仅架构演示与测试；真实语义必须配置远程 provider。这是设计取舍，非缺陷。
- **BLOB 读取开销**：向量规模大时全表读入内存计算余弦；首版语料规模小可接受，后续可加 ANN 索引（sqlite-vss / hnswlib）作第四类后端。
- **与 SOP 客户端模式一致性**：远程调用、mock 默认、注入式测试均复用已验证范式，降低风险。
