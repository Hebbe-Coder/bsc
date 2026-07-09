# Knowledge API 端点实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一组 REST 端点（ingest / documents / retrieve / delete），让外部能通过 HTTP 灌入、列出、检索、删除知识库语料。

**Architecture:** 新建 `app/api/knowledge_api.py`（FastAPI `APIRouter(prefix="/knowledge")`），通过 `Depends(get_knowledge_service)` 注入 `KnowledgeService`（默认连主库 `app/bsc_cloud.db`）。给 `KnowledgeService` 增加 `list_documents` / `delete_document` 两个方法。必须修改 `app/main.py:205` 的显式 router 列表把 `app.api.knowledge_api` 加进去（否则端点不生效）。

**Tech Stack:** FastAPI（APIRouter / Depends / UploadFile / Form）、pytest + `fastapi.testclient.TestClient`、SQLite（复用既有 `KnowledgeService` / `DocumentParser` / `ApiResponse`）。

---

## 关键约定（务必遵守）

- **测试可测试性**：端点一律 `service: KnowledgeService = Depends(get_knowledge_service)`。测试用 `app.dependency_overrides[get_knowledge_service] = lambda: KnowledgeService(db_path=tmp)` 指向临时库，**绝不污染主库**。
- **响应信封**：统一用 `ApiResponse.ok / error / partial / not_found`，HTTP 始终 200，语义码在 `body.code`（`partial` → 207，`not_found` → 404，`error` → 400）。
- **`main.py` 改动不提交**：`app/main.py` 当前是未提交漂移文件，本次只在其 router 列表追加一行 `app.api.knowledge_api` 让其生效，**该改动保持为工作区漂移、不 `git add`**（与 RAG 的 `langchain_agent.py` 注册改动处理方式一致）。每次提交仅 `git add` 计划列出的精确文件。
- 运行器：`.venv/Scripts/python.exe -m pytest`（在仓库根目录运行）。

---

### Task 1: KnowledgeService 增加 list_documents / delete_document

**Files:**
- Modify: `app/knowledge/service.py`（末尾追加两个方法）
- Test: `tests/knowledge/test_service.py`（末尾追加 4 个测试）

- [ ] **Step 1: 写失败测试**（追加到 `tests/knowledge/test_service.py` 末尾，已有 `_tmp_service()` helper）

```python
def test_list_documents():
    svc = _tmp_service()
    svc.ingest("内容安全平台过滤违规信息。", project_id="p1", title="A")
    svc.ingest("咖啡烘焙风味分析。", project_id="p2", title="B")
    res = svc.list_documents()
    assert res["total"] == 2
    assert all(d["chunk_count"] >= 1 for d in res["documents"])
    assert {d["title"] for d in res["documents"]} == {"A", "B"}

def test_list_documents_project_filter():
    svc = _tmp_service()
    svc.ingest("x", project_id="p1", title="A")
    svc.ingest("y", project_id="p2", title="B")
    res = svc.list_documents(project_id="p1")
    assert res["total"] == 1 and res["documents"][0]["title"] == "A"

def test_delete_document():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台过滤违规信息。", title="A")
    assert svc.delete_document(doc_id) is True
    assert svc.list_documents()["total"] == 0

def test_delete_missing_returns_false():
    svc = _tmp_service()
    assert svc.delete_document("nope") is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_service.py::test_list_documents -q
```
Expected: FAIL（`AttributeError: 'KnowledgeService' object has no attribute 'list_documents'`）

- [ ] **Step 3: 写最小实现**（在 `app/knowledge/service.py` 末尾、`retrieve` 方法之后追加）

```python
    def list_documents(self, project_id: Optional[str] = None,
                       limit: int = 100, offset: int = 0) -> dict:
        where = ""
        params: list = []
        if project_id:
            where = "WHERE d.project_id=? "
            params.append(project_id)
        rows = self.repo._execute(
            f"SELECT d.id, d.title, d.source, d.project_id, d.created_at, "
            f"COUNT(c.id) AS chunk_count "
            f"FROM knowledge_docs d LEFT JOIN knowledge_chunks c ON c.doc_id=d.id "
            f"{where}GROUP BY d.id ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
            tuple(params + [limit, offset])).fetchall()
        docs = [dict(r) for r in rows]
        total_row = self.repo._execute(
            f"SELECT COUNT(*) AS cnt FROM knowledge_docs d {where}", tuple(params)
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        return {"documents": docs, "total": total}

    def delete_document(self, doc_id: str) -> bool:
        if not self.repo._execute(
                "SELECT id FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone():
            return False
        chunk_ids = [r["id"] for r in self.repo._execute(
            "SELECT id FROM knowledge_chunks WHERE doc_id=?", (doc_id,)).fetchall()]
        for cid in chunk_ids:
            self.repo._execute("DELETE FROM knowledge_fts WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_tfidf WHERE chunk_id=?", (cid,))
        self.repo._execute("DELETE FROM knowledge_chunks WHERE doc_id=?", (doc_id,))
        self.repo._execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
        self.repo._commit()
        return True
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_service.py -q
```
Expected: PASS（含新增 4 例，总计 9 passed）

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/service.py tests/knowledge/test_service.py
git commit -m "feat(knowledge): add list_documents and delete_document to service"
```

---

### Task 2: knowledge_api.py 骨架 + 依赖工厂 + 注册 main.py + GET /documents

**Files:**
- Create: `app/api/knowledge_api.py`
- Create: `tests/knowledge/conftest.py`（共享 `client` fixture）
- Create: `tests/knowledge/test_api_documents.py`
- Modify: `app/main.py`（仅 router 列表追加一行，**不提交**，保持漂移）

- [ ] **Step 1: 写失败测试**

`tests/knowledge/conftest.py`：
```python
import pytest, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def client():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    tmp = f.name
    app.dependency_overrides[get_knowledge_service] = (
        lambda: KnowledgeService(db_path=tmp))
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
```

`tests/knowledge/test_api_documents.py`：
```python
def test_list_documents_endpoint(client):
    client.post("/knowledge/ingest",
                data={"text": "内容安全平台过滤违规信息。", "title": "A"})
    resp = client.get("/knowledge/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["documents"][0]["title"] == "A"
    assert body["data"]["documents"][0]["chunk_count"] >= 1

def test_list_documents_empty(client):
    resp = client.get("/knowledge/documents")
    assert resp.json()["data"]["total"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_documents.py -q
```
Expected: FAIL（import error / 404，模块或端点不存在）

- [ ] **Step 3: 修改 main.py 注册（不提交）**

在 `app/main.py` 的 router 列表（第 205 行那一长串）末尾追加 `"app.api.knowledge_api"`。
原片段：`[..., "app.api.sop_report_api","app.api.brainstorm_api"]`
改为：`[..., "app.api.sop_report_api","app.api.brainstorm_api","app.api.knowledge_api"]`
（Edit 即可，**不要 `git add` 此文件**）

- [ ] **Step 4: 写最小实现** `app/api/knowledge_api.py`

```python
"""知识库 API 端点：上传/文本灌入、列出、检索、删除。"""
from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Depends
from app.api.response import ApiResponse
from app.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


@router.get("/documents")
def list_documents(
    project_id: str = "",
    limit: int = 100,
    offset: int = 0,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    result = service.list_documents(
        project_id=project_id or None, limit=limit, offset=offset)
    return ApiResponse.ok(result)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_documents.py -q
```
Expected: PASS（2 passed）

- [ ] **Step 6: 提交（仅以下两个新文件，不含 main.py）**

```bash
git add app/api/knowledge_api.py tests/knowledge/conftest.py tests/knowledge/test_api_documents.py
git commit -m "feat(knowledge): add knowledge_api router, DI factory, GET /documents"
```

---

### Task 3: POST /knowledge/ingest（文件 + 文本）

**Files:**
- Modify: `app/api/knowledge_api.py`（追加端点 + import）
- Create: `tests/knowledge/test_api_ingest.py`

- [ ] **Step 1: 写失败测试** `tests/knowledge/test_api_ingest.py`

```python
def test_ingest_file(client):
    resp = client.post(
        "/knowledge/ingest",
        files={"files": ("doc.txt", "内容安全平台过滤违规信息。审核效率提升。", "text/plain")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["count"] == 1
    lst = client.get("/knowledge/documents").json()
    assert lst["data"]["total"] == 1


def test_ingest_text(client):
    resp = client.post("/knowledge/ingest", data={"text": "咖啡烘焙风味分析流程。"})
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["count"] == 1


def test_ingest_multi_file(client):
    resp = client.post(
        "/knowledge/ingest",
        files=[
            ("files", ("a.txt", "内容安全。", "text/plain")),
            ("files", ("b.txt", "咖啡烘焙。", "text/plain")),
        ])
    assert resp.json()["data"]["count"] == 2


def test_ingest_unsupported_format(client):
    resp = client.post(
        "/knowledge/ingest",
        files={"files": ("x.xyz", "hello", "application/octet-stream")})
    # 单文件解析失败且无成功单元 → 400
    assert resp.json()["code"] == 400


def test_ingest_empty(client):
    resp = client.post("/knowledge/ingest", data={})
    assert resp.json()["code"] == 400
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_ingest.py -q
```
Expected: FAIL（404，端点不存在）

- [ ] **Step 3: 写实现**（在 `app/api/knowledge_api.py` 顶部 import 追加，并追加端点）

import 区改为：
```python
from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.core.document_parser import parse_document
```

追加端点：
```python
@router.post("/ingest")
async def ingest(
    files: Optional[List[UploadFile]] = File(None),
    text: str = Form(default=""),
    project_id: str = Form(default=""),
    asset_id: str = Form(default=""),
    title: str = Form(default=""),
    source: str = Form(default="upload"),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    units = []          # (display_title, text)
    parse_errors = []
    for f in (files or []):
        content = await f.read()
        parsed = parse_document(content, f.filename or "unknown")
        if parsed["success"]:
            units.append((title or f.filename or "unknown", parsed["text"]))
        else:
            parse_errors.append({"filename": f.filename, "error": parsed["error"]})
    if text and text.strip():
        units.append((title or "text", text))
    if not units:
        return ApiResponse.error("请提供文件或文本内容", code=400)
    docs = []
    for disp_title, t in units:
        doc_id = service.ingest(
            t, project_id=project_id, asset_id=asset_id,
            title=disp_title, source=source)
        docs.append({"doc_id": doc_id, "title": disp_title,
                     "status": "ok" if doc_id else "skipped"})
    if parse_errors:
        return ApiResponse.partial(
            data={"docs": docs, "count": len(docs)},
            message="部分文件解析失败", errors=parse_errors)
    return ApiResponse.ok({"docs": docs, "count": len(docs)})
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_ingest.py -q
```
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_api_ingest.py
git commit -m "feat(knowledge): add POST /knowledge/ingest (file + text)"
```

---

### Task 4: POST /knowledge/retrieve

**Files:**
- Modify: `app/api/knowledge_api.py`（追加端点 + `BaseModel` import）
- Create: `tests/knowledge/test_api_retrieve.py`

- [ ] **Step 1: 写失败测试** `tests/knowledge/test_api_retrieve.py`

```python
def test_retrieve_hit(client):
    client.post("/knowledge/ingest",
                data={"text": "内容安全平台用于过滤违规信息。审核效率需要提升。",
                      "title": "A"})
    resp = client.post("/knowledge/retrieve", json={"query": "内容安全 审核"})
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["results"]
    assert "内容安全" in body["data"]["results"][0]["content"]
    assert body["data"]["results"][0]["doc_title"] == "A"


def test_retrieve_empty_query(client):
    resp = client.post("/knowledge/retrieve", json={"query": ""})
    assert resp.json()["code"] == 400
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_retrieve.py -q
```
Expected: FAIL（404）

- [ ] **Step 3: 写实现**（import 区加 `BaseModel`，追加端点）

import 区改为：
```python
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
```

追加：
```python
class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    project_id: str = ""


@router.post("/retrieve")
def retrieve(
    req: RetrieveRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    if not req.query or not req.query.strip():
        return ApiResponse.error("请提供查询语句", code=400)
    results = service.retrieve(
        req.query, top_k=req.top_k, project_id=req.project_id or None)
    return ApiResponse.ok({"results": results})
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_retrieve.py -q
```
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_api_retrieve.py
git commit -m "feat(knowledge): add POST /knowledge/retrieve"
```

---

### Task 5: DELETE /knowledge/documents/{doc_id}

**Files:**
- Modify: `app/api/knowledge_api.py`（追加端点）
- Create: `tests/knowledge/test_api_delete.py`

- [ ] **Step 1: 写失败测试** `tests/knowledge/test_api_delete.py`

```python
def test_delete_success(client):
    r = client.post("/knowledge/ingest",
                    data={"text": "内容安全平台过滤违规信息。", "title": "A"}).json()
    doc_id = r["data"]["docs"][0]["doc_id"]
    resp = client.delete(f"/knowledge/documents/{doc_id}")
    assert resp.json()["code"] == 200
    assert client.get("/knowledge/documents").json()["data"]["total"] == 0


def test_delete_missing(client):
    resp = client.delete("/knowledge/documents/nope")
    assert resp.json()["code"] == 404
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_delete.py -q
```
Expected: FAIL（404）

- [ ] **Step 3: 写实现**（追加端点）

```python
@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    if not service.delete_document(doc_id):
        return ApiResponse.not_found("文档不存在")
    return ApiResponse.ok({"deleted": doc_id})
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_delete.py -q
```
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_api_delete.py
git commit -m "feat(knowledge): add DELETE /knowledge/documents/{doc_id}"
```

---

### Task 6: API 边界测试补充

**Files:**
- Create: `tests/knowledge/test_api_edge.py`

- [ ] **Step 1: 写测试**（覆盖边界，纯黑盒走 HTTP）

```python
def test_ingest_partial_failure(client):
    # 一个成功 + 一个不支持格式 → partial(207)
    resp = client.post(
        "/knowledge/ingest",
        files=[
            ("files", ("ok.txt", "内容安全平台。", "text/plain")),
            ("files", ("bad.xyz", "x", "application/octet-stream")),
        ])
    body = resp.json()
    assert body["code"] == 207
    assert body["data"]["count"] == 1
    assert client.get("/knowledge/documents").json()["data"]["total"] == 1


def test_ingest_project_filter_end_to_end(client):
    client.post("/knowledge/ingest",
                data={"text": "内容安全。", "project_id": "p1", "title": "A"})
    client.post("/knowledge/ingest",
                data={"text": "咖啡。", "project_id": "p2", "title": "B"})
    resp = client.get("/knowledge/documents", params={"project_id": "p1"})
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["documents"][0]["title"] == "A"


def test_retrieve_empty_corpus(client):
    resp = client.post("/knowledge/retrieve", json={"query": "任意"})
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["results"] == []


def test_ingest_oversized_text_skipped_not_crash(client):
    # 巨大文本仍应入库（KnowledgeService 内部有定界），不崩
    big = "内容安全。" * 5000
    resp = client.post("/knowledge/ingest", data={"text": big, "title": "BIG"})
    assert resp.json()["code"] == 200
    assert client.get("/knowledge/documents").json()["data"]["total"] == 1
```

- [ ] **Step 2: 运行测试确认通过**（这些测试依赖前面已实现的端点，应直接 PASS）

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_edge.py -q
```
Expected: PASS（4 passed）

- [ ] **Step 3: 提交**

```bash
git add tests/knowledge/test_api_edge.py
git commit -m "test(knowledge): add API edge-case coverage"
```

---

### Task 7: 全量回归

- [ ] **Step 1: 运行知识层全量**

```bash
.venv/Scripts/python.exe -m pytest tests/knowledge/ -q
```
Expected: 全部 PASS（service 9 + 各 api 测试 2+5+2+2+4 = 15，合计 24 passed）

- [ ] **Step 2: 运行全量套件（忽略真实 LLM e2e）**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_real_e2e.py
```
Expected: 与基线一致（218 passed, 2 failed 为既有的非 RAG 问题），**无新增失败**。
若发现由本分支引入的失败，定位修复后提交；否则仅确认绿灯，结束。

---

## 自审要点（实现时对照）

- `get_knowledge_service` 在 T2 定义，T3–T6 端点均 `Depends` 复用——签名一致。
- `ApiResponse.ok / error / partial / not_found` 返回 pydantic 模型，FastAPI 自动序列化为 HTTP 200。
- `parse_document` 返回 `{"success","text","filename","error"}`，ingest 端点的解析失败分支严格据此判断。
- `list_documents` 返回 `{"documents":[...],"total":N}`，端点直接 `ApiResponse.ok(result)`。
- `delete_document` 返回 `bool`，端点据其映射 200 / 404。
- 所有 `git add` 精确列出，绝不碰 `app/main.py`、`.db*` 等漂移文件。
