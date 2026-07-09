# 知识库 API 端点设计（Knowledge API Endpoint）

> 日期：2026-07-09
> 关联：RAG 统一知识中台（KnowledgeService + RetrieveKnowledgeTool）

## 1. 背景与目标

RAG 统一知识中台已实现 `KnowledgeService`（`ingest` / `retrieve`）与 `RetrieveKnowledgeTool`
（注入 agent 对话）。但目前 `ingest` 仅能在代码层调用，缺少通过 HTTP 接口灌入语料的入口。
本设计新增一组 REST 端点，让外部（前端 / 脚本 / 自动化）能**上传文档或文本灌入知识库**，
并能**列出、检索、删除**已入库文档，形成完整的知识库生命周期闭环。

## 2. 架构

- 新建 `app/api/knowledge_api.py`：`APIRouter(prefix="/knowledge", tags=["Knowledge"])`。
- **必须修改 `app/main.py:205` 的 router 注册列表**，加入 `"app.api.knowledge_api"`
  （`main.py` 是显式模块列表，不在此列表则端点不生效）。
- 复用既有组件，不重复造轮子：
  - `KnowledgeService`（默认 `db_path = app/bsc_cloud.db` 主库，由 `BaseRepository` 默认决定）
  - `DocumentParser.parse_document(file_bytes, filename) -> {"success","text","filename","error"}`
  - `ApiResponse` 统一信封（HTTP 始终 200，语义码在 body `code` 字段）
- `KnowledgeService` 新增两个方法：
  - `list_documents(project_id=None, limit=100, offset=0) -> List[dict]`
  - `delete_document(doc_id) -> bool`（级联删除 `knowledge_chunks` / `knowledge_fts` / `knowledge_tfidf` 中关联行）

## 3. 端点详述

### 3.1 POST /knowledge/ingest
- Content-Type：`multipart/form-data`
- Form 字段：
  - `files: List[UploadFile]`（可选，支持多文件）
  - `text: str`（可选，纯文本直接灌入）
  - `project_id: str`（可选，默认 `""`）
  - `asset_id: str`（可选，默认 `""`）
  - `title: str`（可选，默认 `""`，覆盖自动标题）
  - `source: str`（可选，默认 `"upload"`）
- 逻辑：
  - 收集待入库单元：每个 `file` → `parse_document` → `text`；`text` 字段（非空）→ 一个单元。
  - 若没有任何有效文本 → 返回 `ApiResponse.error(code=400)`。
  - 每个单元调用 `service.ingest(text, project_id, asset_id, title or filename, source)`，
    记录成功 / 失败。
  - 单文件解析失败（不支持格式 / 超大 / OCR 失败）→ 该单元标记 `failed`，**不中断**其余单元。
- 响应（HTTP 200）：
  ```json
  { "code": 200, "message": "...", "data": { "docs": [{"doc_id":"..","title":"..","status":"ok|failed","error":""}], "count": 1 } }
  ```
  - 全部成功 `code=200`；存在部分失败 `code="partial"`（仍 HTTP 200）。

### 3.2 GET /knowledge/documents
- Query：`project_id`（可选）、`limit`（默认 100）、`offset`（默认 0）
- 响应（HTTP 200）：
  ```json
  { "code": 200, "data": { "documents": [{"id","title","source","project_id","created_at","chunk_count"}], "total": N } }
  ```

### 3.3 POST /knowledge/retrieve
- JSON：`{ "query": str, "top_k": int = 5, "project_id": str = "" }`
- 响应（HTTP 200）：
  ```json
  { "code": 200, "data": { "results": [{"content","section","doc_title"}] } }
  ```
  - 复用已实现混合检索（FTS5 BM25 + TF-IDF + RRF），与 agent 工具同源。

### 3.4 DELETE /knowledge/documents/{doc_id}
- 成功：`{ "code": 200 }`
- `doc_id` 不存在：`{ "code": 404 }`

## 4. 依赖注入与可测试性

- 定义模块级依赖工厂：
  ```python
  def get_knowledge_service() -> KnowledgeService:
      return KnowledgeService()
  ```
- 端点签名：`service: KnowledgeService = Depends(get_knowledge_service)`
- **测试通过 `client.app.dependency_overrides[get_knowledge_service]` 指向临时库**
  （`lambda: KnowledgeService(db_path=tmp)`），避免污染主库 `app/bsc_cloud.db`。
  这是 FastAPI 标准可测模式，也便于日后切换 db 路径（如按 project 分库）。

## 5. 错误处理（统一信封）

| 场景 | HTTP | body.code |
|------|------|-----------|
| 无 file 且无 text | 200 | 400 |
| 单文件解析失败 | 200 | partial（该单元 failed） |
| ingest 空文本（被跳过） | 200 | partial / 标记 skipped |
| 删除不存在 doc_id | 200 | 404 |
| 正常 | 200 | 200 |

## 6. 测试（TDD，`tests/knowledge/test_api.py`，TestClient + 临时 db）

- 文件 ingest 成功（doc 入库、可列出）
- 纯文本 ingest 成功
- 多文件批量（2 文件 → 2 doc）
- 不支持格式（`*.xyz`）→ 该单元 failed、整体 partial
- 空内容（无 file 无 text）→ 400
- 列出文档（数量正确、字段完整、chunk_count 正确）
- 检索（ingest 后 retrieve 命中且带出处）
- 删除成功（删除后列表不再包含）
- 删除不存在 → 404

## 7. 任务拆分（实现计划参考）

- T1 `KnowledgeService.list_documents` + `delete_document`（含单测）
- T2 `knowledge_api.py` 骨架 + `get_knowledge_service` + 注册 `main.py`
- T3 `POST /knowledge/ingest`（文件 + 文本）
- T4 `GET /knowledge/documents`
- T5 `POST /knowledge/retrieve`
- T6 `DELETE /knowledge/documents/{doc_id}`
- T7 `tests/knowledge/test_api.py` 全量（红 → 绿）
- T8 全量回归

## 8. 提交与收尾

新增文件：`app/api/knowledge_api.py`、`tests/knowledge/test_api.py`；
修改：`app/knowledge/service.py`（两方法）、`app/main.py`（加一行注册）。
完成后本地合并 `master`（与导出层 / RAG 收尾方式一致）。

## 9. 不做的范围（YAGNI）

- 不做鉴权（沿用现有 auth 中间件，必要时后续接入）
- 不做增量 / 版本化 / 冲突合并（每个 ingest 是一次独立 doc）
- 不做异步 / 队列（文档解析同步完成，文件体积受 `MAX_FILE_SIZE` 限制）
- 不新建独立数据库（复用主库 `bsc_cloud.db`）
