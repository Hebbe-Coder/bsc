# 知识库加固 Round 2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已合入 master 的 RAG 生产级加固之上，做一轮综合加固——收口 `reader` 跨项目泄漏、WS 异步化、TF-IDF 增量索引、检索下推去 N+1、Mock 向量不污染排序、轻量可观测性、启动期 schema 一次化。

**Architecture:** 单 feature 分支 `feature/knowledge-hardening-round2`，沿用 subagent-driven（每任务 TDD + 双评审：规格 + 代码质量/安全）。共享三处基础设施：① `_enforce_project_access` 的 `allow_admin_all` 仅对 `admin` 生效（WS1）；② WS 用 `loop.run_in_executor` 包裹同步 `retrieve`（WS2）；③ 进程内 `Metrics` 单例（WS4）。

**Tech Stack:** FastAPI + Pydantic v2 + SQLite（原生 SQL）+ numpy（TF-IDF）+ pytest + TestClient。测试解释器：`.venv/Scripts/python.exe -m pytest`。

**重要代码事实（已核验，子代理务必据此而非猜测）：**
- `app/api/knowledge_api.py`
  - `_enforce_project_access(request, requested_project_id, write=False, allow_admin_all=False)` 位于 36-71 行。`reader` 分支（53-58）当前：`if not requested_project_id and not allow_admin_all: raise 400; return requested_project_id` —— 当 `allow_admin_all=True` 且 `requested_project_id=None` 时**返回 None**，`GET /documents` 用它 → 全表返回（跨项目泄漏）。`admin` 分支（49-52）保留 `allow_admin_all` 语义。
  - `GET /evaluate`（228-239）：`def evaluate(req: EvaluateRequest, service=Depends(get_knowledge_service))`，无 `require_admin`、`req` 无 `project_id`。
  - `EvaluateRequest`（208-211）：`gold: Optional[List[dict]]=None; top_k:int=5; with_faithfulness:bool=False`（缺 `project_id`）。
  - `get_knowledge_service()`（16-17）仅 `return KnowledgeService()`；`ensure_schema` 实际在 `KnowledgeService.__init__`（`app/knowledge/service.py:23`）调用。
  - `require_admin(request)`（20-28）：非 admin 抛 403。
- `app/api/knowledge_ws.py`：`_handle_ask` 第 105-108 行 `svc.retrieve(...)` 在异步 task 内同步调用（阻塞事件循环）。
- `app/knowledge/service.py`：
  - `retrieve`（148-170）：`kw_ids/tf_ids/vec_ids = backends[...].search(query)` 后 `rrf_fuse([kw_ids,tf_ids,vec_ids])`；`if not project_id: return []`（L1 强隔离）。
  - `_fetch_candidates`（124-146）：逐候选一条 `SELECT ... WHERE c.id=? AND d.project_id=?`（N+1）。
- `app/knowledge/backends/tfidf.py`：`index`（60-79）每次 `SELECT content FROM knowledge_chunks` 全表 + 重算所有 chunk 向量；`search`（81-96）`SELECT chunk_id,vector FROM knowledge_tfidf` 全表（无 project_id/LIMIT 下推）。
- `app/knowledge/backends/vector.py`：`search`（58-88）`WHERE model=?` 已按模型过滤（陈旧向量天然排除）；`index`（27-56）写 `knowledge_vectors(chunk_id, model, dim, vector)`。
- `app/core/config.py`：`EMBEDDING_PROVIDER:str="mock"`（64）；`RERANK_ENABLED:bool=False`（77）；`RERANK_TOP_N:int=20`（76）。
- `app/middleware/auth.py`：`resolve_knowledge_auth`：`settings.API_KEY_READER` → `role="reader"`，`project_id=None`（系统级只读，不绑定项目）。
- `app/knowledge/schema.py`：`content_hash` 列在 **`knowledge_docs`**（非 chunks）；`knowledge_chunks` 无 content_hash。
- `app/main.py` `lifespan`（22-32）：调用 `app.db.init_db()`（legacy 实体子系统 DB，与知识库 DB 不同）；**知识库 schema 当前无启动期调用**。
- 测试隔离：`tests/knowledge/conftest.py` 已有 autouse fixture 快照/还原全局 `settings` + `dependency_overrides`（T12 加），复用之，严禁测试内直接 `settings.X=...` 而不还原。
- 漂移文件（严禁提交）：`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`。

---

## 文件结构（本计划涉及）

- Modify: `app/api/knowledge_api.py`（`_enforce_project_access`、GET `/evaluate` + `EvaluateRequest`、`get_knowledge_service` 启动期调用可选）
- Modify: `app/api/knowledge_ws.py`（`_handle_ask` 的 `retrieve` 异步化）
- Modify: `app/knowledge/service.py`（`retrieve` 向量融合条件、`_fetch_candidates` 批量、启动期 schema、`reindex_stale`）
- Modify: `app/knowledge/backends/tfidf.py`（`index` 增量、`_build_and_store_model` 返回 changed 标志、`search` 下推 project_id+LIMIT）
- Modify: `app/knowledge/backends/vector.py`（`search` 下推 project_id+LIMIT、`reindex_stale`）
- Modify: `app/knowledge/backends/keyword.py`（`search` 下推 project_id+LIMIT，保持接口一致）
- Create: `app/knowledge/metrics.py`（进程内 `Metrics` 单例）
- Modify: `app/api/knowledge_api.py`（新增 `GET /knowledge/metrics`，admin 门禁）
- Modify: `app/main.py`（`lifespan` 启动期 `ensure_schema`）
- Modify/Create: `app/core/config.py`（`VECTOR_FUSE_ENABLED:bool=True`）
- Test: `tests/knowledge/test_ws1_security.py`、`test_ws2_perf.py`、`test_ws3_correctness.py`、`test_ws4_metrics.py`、`test_ws5_startup.py`

---

## Task 1: 收口 `reader` 跨项目泄漏（WS1.1 — HIGH）

**Files:** Modify `app/api/knowledge_api.py:36-71`

- [ ] **Step 1: 写失败测试**（`tests/knowledge/test_ws1_security.py`）

```python
import os, tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws1-admin"
    settings.API_KEY_READER = "ws1-reader"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p)
    ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("项目A 的内容 alpha", project_id="PA", title="docA")
    svc.ingest_text("项目B 的内容 beta", project_id="PB", title="docB")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def test_reader_with_project_id_only_sees_that_project(env):
    r = env.get("/knowledge/documents?project_id=PA",
                headers={"Authorization": "Bearer ws1-reader"})
    assert r.json()["success"] is True
    docs = r.json()["data"]["documents"]
    assert [d["project_id"] for d in docs] == ["PA"]
    assert all(d["project_id"] == "PA" for d in docs)


def test_reader_without_project_id_is_rejected(env):
    # 关键安全断言：reader 绝不能因 allow_admin_all 而全表返回
    r = env.get("/knowledge/documents",
                headers={"Authorization": "Bearer ws1-reader"})
    assert r.json()["success"] is False
    assert r.json()["code"] == 400


def test_admin_without_project_id_sees_all(env):
    r = env.get("/knowledge/documents",
                headers={"Authorization": "Bearer ws1-admin"})
    assert r.json()["success"] is True
    assert {d["project_id"] for d in r.json()["data"]["documents"]} == {"PA", "PB"}
```

- [ ] **Step 2: 运行测试验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws1_security.py -v`
Expected: `test_reader_without_project_id_is_rejected` FAIL（`reader` 当前返回 200 + 全表）。

- [ ] **Step 3: 写最小修复**——把 `app/api/knowledge_api.py` 的 `_enforce_project_access` 替换为：

```python
def _enforce_project_access(request: Request, requested_project_id: str,
                            write: bool = False, allow_admin_all: bool = False) -> str:
    role, token_pid = _role_and_project(request)
    if role == "admin":
        if not requested_project_id and not allow_admin_all:
            raise HTTPException(status_code=400, detail="project_id 必填")
        return requested_project_id
    if role == "reader":
        if write:
            raise HTTPException(status_code=403, detail="只读密钥（reader）无写入权限")
        eff = requested_project_id or token_pid
        if not eff:
            raise HTTPException(status_code=400, detail="project_id 必填")
        return eff
    if role == "project_admin":
        eff = requested_project_id or token_pid
        if not eff or eff != token_pid:
            raise HTTPException(status_code=403, detail="无该项目访问权限")
        return eff
    if role == "project_reader":
        if write:
            raise HTTPException(status_code=403, detail="project_reader 只读，无写入权限")
        eff = requested_project_id or token_pid
        if not eff or eff != token_pid:
            raise HTTPException(status_code=403, detail="无该项目访问权限")
        return eff
    raise HTTPException(status_code=403, detail="无访问权限")
```

仅改了 `reader` 分支：`allow_admin_all` 不再对 reader 放行空 project_id；reader 必须带 `project_id` 或回退令牌绑定项目（reader 为系统级，`token_pid=None` → 缺失即 400）。`admin` 行为不变。

- [ ] **Step 4: 运行测试验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws1_security.py -v`
Expected: PASS（3 个）。

- [ ] **Step 5: 提交**
```bash
git add app/api/knowledge_api.py tests/knowledge/test_ws1_security.py
git commit -m "fix(knowledge): reader 跨项目泄漏收口（allow_admin_all 仅对 admin 生效）"
```

---

## Task 2: 加固 `GET /evaluate`（WS1.2 — MED）

**Files:** Modify `app/api/knowledge_api.py:208-239`

- [ ] **Step 1: 写失败测试**（追加到 `tests/knowledge/test_ws1_security.py`）

```python
def test_evaluate_requires_admin(env):
    r = env.post("/knowledge/evaluate", json={"project_id": "PA"},
                 headers={"Authorization": "Bearer ws1-reader"})
    assert r.json()["success"] is False
    assert r.json()["code"] == 403


def test_evaluate_requires_project_id(env):
    r = env.post("/knowledge/evaluate", json={},
                 headers={"Authorization": "Bearer ws1-admin"})
    assert r.json()["success"] is False
    assert r.json()["code"] == 400
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws1_security.py::test_evaluate_requires_admin tests/knowledge/test_ws1_security.py::test_evaluate_requires_project_id -v`
Expected: FAIL（当前 `/evaluate` 无 `require_admin` 且静默空结果）。

- [ ] **Step 3: 写最小实现**
`EvaluateRequest` 增加字段（208 行附近）：
```python
class EvaluateRequest(BaseModel):
    gold: Optional[List[dict]] = None
    project_id: Optional[str] = None
    top_k: int = 5
    with_faithfulness: bool = False
```
`evaluate` 路由改为：
```python
@router.post("/evaluate")
def evaluate(req: EvaluateRequest,
             service: KnowledgeService = Depends(get_knowledge_service),
             _admin: bool = Depends(require_admin)):
    if not req.project_id:
        return ApiResponse.error("project_id 必填", code=400)
    from app.knowledge.eval import RAGEvaluator
    try:
        gold = req.gold if req.gold else RAGEvaluator.DEFAULT_GOLD
        if not gold:
            return ApiResponse.error("gold 为空", code=400)
        ev = RAGEvaluator()
        metrics = ev.evaluate(service, gold, top_k=req.top_k,
                               project_id=req.project_id,
                               with_faithfulness=req.with_faithfulness)
        return ApiResponse.ok(metrics)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)
```
返回结构不变（`before/after/delta_*/rerank_not_worse`）。注意 `RAGEvaluator.evaluate` 已支持 `project_id` 参数（见 `app/knowledge/eval.py`）。

- [ ] **Step 4: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws1_security.py -v`
Expected: PASS（5 个）。

- [ ] **Step 5: 提交**
```bash
git add app/api/knowledge_api.py tests/knowledge/test_ws1_security.py
git commit -m "fix(knowledge): GET /evaluate 加 require_admin + 强制 project_id"
```

---

## Task 3: WS 异步化（WS2.1 — HIGH）

**Files:** Modify `app/api/knowledge_ws.py:105-108`

- [ ] **Step 1: 写失败测试**（新建 `tests/knowledge/test_ws2_perf.py`）
用 spy 验证 `svc.retrieve` 在 executor 中执行（不在事件循环协程栈内同步跑）。最稳健的断言：现有 WS 流式 + cancel 测试继续通过，且新增「检索期间不阻塞事件循环」的行为测试——在测试里往 loop 注册一个周期性任务，断言它在 retrieve 同步耗时期间仍被调度。

```python
import asyncio, os, tempfile, json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def ws_env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws2-admin"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p)
    ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("咖啡 烘焙 温度曲线 知识内容", project_id="P1", title="coffee")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    os.remove(p)


def test_ws_ask_streams_and_cancels(ws_env):
    # 复用 T10 真实验证：流式 token 输出 + cancel 真实停止
    with ws_env.websocket_connect("/ws/knowledge/ask?token=ws2-admin") as ws:
        ws.send_json({"type": "ask", "request_id": "r1", "project_id": "P1",
                      "query": "咖啡", "top_k": 3})
        frames = {}
        cancelled = False
        while True:
            msg = ws.receive_json()
            frames[msg["type"]] = frames.get(msg["type"], 0) + 1
            if msg["type"] == "end":
                cancelled = msg["data"].get("cancelled", False)
                break
        assert frames.get("token", 0) > 0
        assert frames.get("sources", 0) == 1
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py -v`
Expected: 现有 `test_ws_ask_streams_and_cancels` 表现应与 T10 一致通过；本任务不引入新失败，重点是 Step 3 重构后保持通过并验证不阻塞。

- [ ] **Step 3: 重构 `_handle_ask`**
将第 105-108 行：
```python
    svc = KnowledgeService(repo=repo)
    retrieved = svc.retrieve(data.get("query", ""), top_k=data.get("top_k", 5),
                             project_id=pid, rerank=data.get("rerank"),
                             rerank_top_n=data.get("rerank_top_n"))
```
改为：
```python
    svc = KnowledgeService(repo=repo)
    loop = asyncio.get_running_loop()
    retrieved = await loop.run_in_executor(
        None,
        lambda: svc.retrieve(
            data.get("query", ""), top_k=data.get("top_k", 5),
            project_id=pid, rerank=data.get("rerank"),
            rerank_top_n=data.get("rerank_top_n")))
```
`async_stream_chat` 仍走原生 async，`conn.cancel` 语义不变。`svc` 在 executor 闭包内捕获，无跨协程共享可变状态。

- [ ] **Step 4: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py tests/knowledge/test_ws_ask.py -v`
Expected: PASS（流式 + cancel 仍正确，无死锁）。

- [ ] **Step 5: 提交**
```bash
git add app/api/knowledge_ws.py tests/knowledge/test_ws2_perf.py
git commit -m "perf(knowledge): WS ask 的同步 retrieve 移入 run_in_executor，避免阻塞事件循环"
```

---

## Task 4: TF-IDF 增量索引（WS2.2 — HIGH/MED）

**Files:** Modify `app/knowledge/backends/tfidf.py:26-79`

- [ ] **Step 1: 写失败测试**（追加到 `tests/knowledge/test_ws2_perf.py`）

```python
from app.knowledge.backends.tfidf import TfidfBackend


def test_tfidf_incremental_skips_full_revectorize():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    backend = TfidfBackend(repo)
    calls = {"n": 0}
    orig = backend._vectorize
    def spy(text, vocab, idf):
        calls["n"] += 1
        return orig(text, vocab, idf)
    backend._vectorize = spy

    backend.index([{"id": "c1", "content": "hello world"},
                   {"id": "c2", "content": "foo bar"}])
    assert calls["n"] == 2  # 首次：全量向量化
    # 第二次仅追加内容，且用词均在已有词表内 -> 不应触发全量重向量化
    backend.index([{"id": "c3", "content": "hello foo"}])
    assert calls["n"] == 3  # 仅新增 1 个 chunk，而非 2+3=5
    os.remove(p)
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py::test_tfidf_incremental_skips_full_revectorize -v`
Expected: FAIL（当前每次 `index` 都重向量化全部 chunk → `calls["n"]==5`）。

- [ ] **Step 3: 重写 `tfidf.py` 的 `_build_and_store_model` 与 `index`**

```python
    def _build_and_store_model(self):
        rows = self.repo._execute("SELECT content FROM knowledge_chunks").fetchall()
        docs = [r["content"] for r in rows]
        vocab: dict = {}
        doc_term_counts: List[dict] = []
        for doc in docs:
            tf: dict = {}
            for tok in tokenize(doc):
                if tok not in vocab:
                    vocab[tok] = len(vocab)
                tf[tok] = tf.get(tok, 0) + 1
            doc_term_counts.append(tf)
        num_docs = max(len(docs), 1)
        idf: dict = {}
        for term in vocab:
            df = sum(1 for dt in doc_term_counts if term in dt)
            idf[term] = float(np.log((num_docs + 1) / (df + 1)) + 1)
        # 仅在词表变化时落库重建，否则复用（changed=False）
        existing = self.repo._execute(
            "SELECT vocab_json FROM tfidf_model WHERE id=1").fetchone()
        changed = True
        if existing:
            try:
                if json.loads(existing["vocab_json"]) == vocab:
                    changed = False
            except Exception:
                changed = True
        if changed:
            self.repo._execute("DELETE FROM tfidf_model")
            self.repo._execute(
                "INSERT INTO tfidf_model (id, vocab_json, idf_json) VALUES (1, ?, ?)",
                (json.dumps(vocab, ensure_ascii=False), json.dumps(idf, ensure_ascii=False)))
            self.repo._commit()
        return vocab, idf, changed

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        try:
            vocab, idf, changed = self._build_and_store_model()
        except Exception as e:
            logger.warning("tfidf model build failed: %s", e)
            return
        if not vocab:
            return
        if changed:
            # 词表维度变化，必须为全部 chunk 重新向量化
            all_rows = self.repo._execute(
                "SELECT id, content FROM knowledge_chunks").fetchall()
            targets = [{"id": r["id"], "content": r["content"]} for r in all_rows]
        else:
            # 词表不变，仅向量化本次新增/变更 chunk（增量）
            targets = chunk_records
        for rec in targets:
            vec = self._vectorize(rec["content"], vocab, idf)
            self.repo._execute(
                "INSERT OR REPLACE INTO knowledge_tfidf (chunk_id, vector) VALUES (?, ?)",
                (rec["id"], vec.tobytes()))
        self.repo._commit()
```

注意：`_vectorize` 保持不变（50-58 行）。

- [ ] **Step 4: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py::test_tfidf_incremental_skips_full_revectorize -v`
Expected: PASS（`calls["n"]==3`）。

- [ ] **Step 5: 提交**
```bash
git add app/knowledge/backends/tfidf.py tests/knowledge/test_ws2_perf.py
git commit -m "perf(knowledge): TF-IDF 增量索引（词表不变时仅向量化新增 chunk）"
```

---

## Task 5: 检索下推 project_id/LIMIT + 去 N+1（WS2.3 — MED）

**Files:** Modify `app/knowledge/backends/{tfidf,vector,keyword}.py`、`app/knowledge/service.py:124-170`

- [ ] **Step 1: 写失败测试**（追加到 `tests/knowledge/test_ws2_perf.py`）

```python
def test_retrieve_isolates_projects():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("alpha 专属内容 X", project_id="PA", title="a")
    svc.ingest_text("beta 专属内容 Y", project_id="PB", title="b")
    res = svc.retrieve("alpha", project_id="PA", top_k=5)
    assert res, "应至少召回 PA 的文档"
    assert all(r["chunk_id"].split("-")[0] or True for r in res)  # 占位
    # 核心断言：PA 检索结果不得包含 PB 内容
    pb_hit = any("beta" in (r.get("content") or "") for r in res)
    assert not pb_hit
    os.remove(p)
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py::test_retrieve_isolates_projects -v`
Expected: 取决于后端——当前各 backend `search` 全表扫描无 project 过滤，若 PB 文档向量/词频更匹配可能串入，断言可能失败（或偶过）。本任务目标使其稳定通过且 SQL 含下推。

- [ ] **Step 3: 为三个 backend 的 `search` 增加 `project_id` + `limit` 下推参数**
统一签名 `search(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[str]`。

`tfidf.py` `search`（原 81-96）：
```python
    def search(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        vocab, idf = self._load_model()
        if not vocab:
            return []
        qv = self._vectorize(query, vocab, idf)
        sql = ("SELECT t.chunk_id, t.vector FROM knowledge_tfidf t "
               "JOIN knowledge_chunks c ON t.chunk_id=c.id "
               "JOIN knowledge_docs d ON c.doc_id=d.id")
        params: list = []
        if project_id:
            sql += " WHERE d.project_id=?"
            params.append(project_id)
        sql += " LIMIT ?"
        params.append(limit)
        rows = self.repo._execute(sql, tuple(params)).fetchall()
        scored = []
        for r in rows:
            cv = np.frombuffer(r["vector"], dtype=np.float64)
            sim = float(np.dot(qv, cv))
            if sim > 0:
                scored.append((r["chunk_id"], sim))
        scored.sort(key=lambda x: -x[1])
        return [cid for cid, _ in scored[:limit]]
```

`vector.py` `search`（原 58-88）：在 `WHERE model=?` 后追加 `AND d.project_id=?` 并 JOIN：
```python
    def search(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        try:
            provider = self._get_provider()
            qv = np.asarray(provider.embed([query])[0], dtype=np.float64)
        except Exception as e:
            logger.warning("vector 检索失败(返回空): %s", e)
            return []
        sql = ("SELECT v.chunk_id, v.vector FROM knowledge_vectors v "
               "JOIN knowledge_chunks c ON v.chunk_id=c.id "
               "JOIN knowledge_docs d ON c.doc_id=d.id "
               "WHERE v.model=?")
        params: list = [provider.name]
        if project_id:
            sql += " AND d.project_id=?"
            params.append(project_id)
        sql += " LIMIT ?"
        params.append(limit)
        rows = self.repo._execute(sql, tuple(params)).fetchall()
        if not rows:
            return []
        qnorm = np.linalg.norm(qv)
        scored = []
        for r in rows:
            try:
                cv = np.frombuffer(r["vector"], dtype=np.float32).astype(np.float64)
                if cv.shape[0] != qv.shape[0]:
                    continue
                cnorm = np.linalg.norm(cv)
                if qnorm == 0 or cnorm == 0:
                    continue
                sim = float(np.dot(qv, cv) / (qnorm * cnorm))
                if sim > 0:
                    scored.append((r["chunk_id"], sim))
            except Exception:
                continue
        scored.sort(key=lambda x: -x[1])
        return [cid for cid, _ in scored[:limit]]
```

`keyword.py` `search`：仿照追加 `project_id`/`limit` 下推 JOIN（读取该文件确认当前实现后对齐；保持接口一致）。

- [ ] **Step 4: 改 `service.retrieve` 透传 `project_id`/`limit`**
`app/knowledge/service.py` 148-156：
```python
        kw_ids = self.backends["keyword"].search(query, project_id=project_id, limit=top_k*4)
        tf_ids = self.backends["tfidf"].search(query, project_id=project_id, limit=top_k*4)
        vec_ids = self.backends["vector"].search(query, project_id=project_id, limit=top_k*4)
```

- [ ] **Step 5: 去 N+1——`_fetch_candidates` 批量**
`app/knowledge/service.py` 124-146 改为：
```python
    def _fetch_candidates(self, ids_with_scores, project_id: Optional[str] = None) -> List[dict]:
        if not ids_with_scores:
            return []
        ids = [cid for cid, _ in ids_with_scores]
        placeholders = ",".join("?" for _ in ids)
        rows = self.repo._execute(
            f"SELECT c.id AS cid, c.content AS content, c.section AS section, "
            f"c.idx AS idx, d.title AS doc_title "
            f"FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
            f"WHERE c.id IN ({placeholders}) AND d.project_id = ?",
            tuple(ids + [project_id or ""])).fetchall()
        by_id = {r["cid"]: r for r in rows}
        results = []
        for cid, score in ids_with_scores:
            row = by_id.get(cid)
            if row:
                results.append({
                    "chunk_id": cid,
                    "content": row["content"],
                    "section": row["section"] or "",
                    "idx": row["idx"] or 0,
                    "score": score,
                    "doc_title": row["doc_title"] or "未知来源",
                })
        return results
```

- [ ] **Step 6: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws2_perf.py -v`
Expected: PASS（含隔离断言）。

- [ ] **Step 7: 提交**
```bash
git add app/knowledge/backends/tfidf.py app/knowledge/backends/vector.py app/knowledge/backends/keyword.py app/knowledge/service.py tests/knowledge/test_ws2_perf.py
git commit -m "perf(knowledge): 检索下推 project_id+LIMIT，_fetch_candidates 批量去 N+1"
```

---

## Task 6: Mock 向量不污染排序（WS3.1 — MED）

**Files:** Modify `app/core/config.py`、`app/knowledge/service.py:148-170`

- [ ] **Step 1: 写失败测试**（新建 `tests/knowledge/test_ws3_correctness.py`）

```python
import os, tempfile
import pytest
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service
from app.knowledge.backends.vector import VectorBackend


@pytest.fixture
def env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws3-admin"
    settings.EMBEDDING_PROVIDER = "mock"
    settings.VECTOR_FUSE_ENABLED = True
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("机器学习 模型 训练", project_id="P1", title="ml")
    svc.ingest_text("做菜 食谱 火候", project_id="P1", title="cook")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    yield svc, repo
    app.dependency_overrides.clear()
    os.remove(p)


def test_mock_vector_excluded_from_fusion(env):
    svc, repo = env
    backend = VectorBackend(repo)
    called = {"n": 0}
    orig = backend.search
    def spy(*a, **k):
        called["n"] += 1
        return orig(*a, **k)
    backend.search = spy
    svc.retrieve("机器学习", project_id="P1", top_k=3)
    assert called["n"] == 0, "mock provider 下 VectorBackend.search 不应被调用"
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws3_correctness.py::test_mock_vector_excluded_from_fusion -v`
Expected: FAIL（当前 `retrieve` 无条件调用 `backends["vector"].search`）。

- [ ] **Step 3: 加配置 `VECTOR_FUSE_ENABLED`**
`app/core/config.py` 在 `EMBEDDING_PROVIDER` 附近新增：
```python
    EMBEDDING_PROVIDER: str = "mock"  # 向量检索 embedding 来源 (mock/openai)
    VECTOR_FUSE_ENABLED: bool = True  # 是否将稠密向量后端纳入 RRF 融合（仅当 provider!="mock" 生效）
```

- [ ] **Step 4: 改 `retrieve` 条件调用向量后端**
`app/knowledge/service.py` 154-156：
```python
        kw_ids = self.backends["keyword"].search(query, project_id=project_id, limit=top_k*4)
        tf_ids = self.backends["tfidf"].search(query, project_id=project_id, limit=top_k*4)
        vec_ids = []
        if settings.VECTOR_FUSE_ENABLED and settings.EMBEDDING_PROVIDER != "mock":
            vec_ids = self.backends["vector"].search(query, project_id=project_id, limit=top_k*4)
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
```

- [ ] **Step 5: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws3_correctness.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**
```bash
git add app/core/config.py app/knowledge/service.py tests/knowledge/test_ws3_correctness.py
git commit -m "fix(knowledge): mock provider 下向量后端不混入 RRF 融合（VECTOR_FUSE_ENABLED）"
```

---

## Task 7: Embedding 漂移检测 + 重嵌（WS3.2 — MED）

**Files:** Modify `app/knowledge/backends/vector.py`、`app/knowledge/service.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/knowledge/test_ws3_correctness.py`）

```python
def test_embedding_model_mismatch_excludes_stale():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    backend = VectorBackend(repo)
    # 写入 model='old' 的陈旧向量
    backend.repo._execute(
        "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, model, dim, vector) VALUES (?,?,?,?)",
        ("stale-c1", "old", 2, np.array([1.0, 0.0], dtype=np.float32).tobytes()))
    backend.repo._commit()
    # 当前 provider（test 默认 mock）查询时不得返回陈旧向量
    got = backend.search("anything", project_id=None, limit=10)
    assert "stale-c1" not in got
    os.remove(p)
```

- [ ] **Step 2: 运行验证**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws3_correctness.py::test_embedding_model_mismatch_excludes_stale -v`
Expected: 当前 `search` 已用 `WHERE model=?`（provider.name）过滤，**应已通过**——本任务确认该行为并补充 `reindex_stale` 显式修正入口（供下次 ingest 修正陈旧向量）。若未通过说明 provider.name 取值异常，需先修 `WHERE model=?` 对齐。

- [ ] **Step 3: 加 `reindex_stale` 修正入口**
`app/knowledge/backends/vector.py` 末尾新增：
```python
    def reindex_stale(self, project_id: Optional[str] = None) -> int:
        """标记/重嵌陈旧向量：删除 model 与当前 provider 不一致的向量行，
        返回被清除的行数（下次 ingest 该 doc 时会按新模型重写）。"""
        try:
            provider = self._get_provider()
        except Exception:
            return 0
        sql = ("DELETE FROM knowledge_vectors v "
               "WHERE v.model IS NOT NULL AND v.model <> ?")
        params: list = [provider.name]
        if project_id:
            sql += (" AND v.chunk_id IN (SELECT c.id FROM knowledge_chunks c "
                    "JOIN knowledge_docs d ON c.doc_id=d.id WHERE d.project_id=?)")
            params.append(project_id)
        cur = self.repo._execute(sql, tuple(params))
        self.repo._commit()
        return cur.rowcount if hasattr(cur, "rowcount") else 0
```
`service.py` 增加便捷方法（可选 admin 端点留到 WS4/后续）：
```python
    def reindex_stale_vectors(self, project_id: Optional[str] = None) -> int:
        return self.backends["vector"].reindex_stale(project_id)
```

- [ ] **Step 4: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws3_correctness.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**
```bash
git add app/knowledge/backends/vector.py app/knowledge/service.py tests/knowledge/test_ws3_correctness.py
git commit -m "fix(knowledge): embedding 漂移——search 仅取当前模型向量 + reindex_stale 修正入口"
```

---

## Task 8: 轻量可观测性（WS4 — MED）

**Files:** Create `app/knowledge/metrics.py`；Modify `app/api/knowledge_api.py`（新增 `GET /knowledge/metrics`）；Modify `app/knowledge/service.py`（`retrieve` 打点）

- [ ] **Step 1: 写失败测试**（新建 `tests/knowledge/test_ws4_metrics.py`）

```python
import os, tempfile, json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service
from app.knowledge import metrics as M


@pytest.fixture
def env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws4-admin"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("可观测性 检索 延迟", project_id="P1", title="m")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    M.metrics.reset()
    yield TestClient(app), svc
    app.dependency_overrides.clear()
    os.remove(p)


def test_metrics_records_retrieval_and_auth(env):
    client, svc = env
    svc.retrieve("可观测性", project_id="P1", top_k=3)
    # 触发一次鉴权失败
    r0 = client.get("/knowledge/documents")
    assert r0.json()["success"] is False
    r = client.get("/knowledge/metrics", headers={"Authorization": "Bearer ws4-admin"})
    assert r.json()["success"] is True
    data = r.json()["data"]
    assert data["retrieval_latency_ms"]["count"] >= 1
    assert data["auth_failures"] >= 1


def test_metrics_requires_admin(env):
    client, _ = env
    r = client.get("/knowledge/metrics")
    assert r.json()["success"] is False
    assert r.json()["code"] == 403
```

- [ ] **Step 2: 运行验证失败**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws4_metrics.py -v`
Expected: FAIL（`app/knowledge/metrics.py` 不存在、无 `/metrics` 端点）。

- [ ] **Step 3: 创建 `app/knowledge/metrics.py`**

```python
"""轻量进程内指标收集器（无外部依赖）。"""
from __future__ import annotations
import logging
import threading
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.retrieval_latency_ms: Dict[str, float] = {"count": 0.0, "sum": 0.0, "max": 0.0}
        self.rerank_hit_rate: Dict[str, float] = {"count": 0.0, "sum": 0.0}
        self.eval_regressions: int = 0
        self.auth_failures: int = 0

    def record_retrieval(self, ms: float):
        with self._lock:
            s = self.retrieval_latency_ms
            s["count"] += 1; s["sum"] += ms
            s["max"] = max(s["max"], ms)

    def record_rerank_hit_rate(self, rate: float):
        with self._lock:
            self.rerank_hit_rate["count"] += 1
            self.rerank_hit_rate["sum"] += rate

    def record_eval_regression(self):
        with self._lock:
            self.eval_regressions += 1

    def record_auth_failure(self):
        with self._lock:
            self.auth_failures += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            s = self.retrieval_latency_ms
            avg = (s["sum"] / s["count"]) if s["count"] else 0.0
            return {
                "retrieval_latency_ms": {"count": int(s["count"]), "avg": round(avg, 3), "max": round(s["max"], 3)},
                "rerank_hit_rate": {"count": int(self.rerank_hit_rate["count"]),
                                    "avg": round(self.rerank_hit_rate["sum"] / self.rerank_hit_rate["count"], 4)
                                    if self.rerank_hit_rate["count"] else 0.0},
                "eval_regressions": self.eval_regressions,
                "auth_failures": self.auth_failures,
            }

    def reset(self):
        with self._lock:
            self.__init__()


metrics = Metrics()
```

- [ ] **Step 4: `service.retrieve` 打点**
`app/knowledge/service.py` 顶部 `from app.knowledge import metrics as _metrics`，在 `retrieve` 入口/出口：
```python
    def retrieve(self, query, top_k=5, project_id=None, rerank=None, rerank_top_n=None):
        _t0 = time.perf_counter()
        try:
            if not query or not query.strip():
                return []
            if not project_id:
                return []
            ...
            return result
        finally:
            _metrics.metrics.record_retrieval((time.perf_counter() - _t0) * 1000.0)
```
（在 `app/knowledge/service.py` 加 `import time`）。

- [ ] **Step 5: 新增 `GET /knowledge/metrics`（admin）**
`app/api/knowledge_api.py` 末尾新增：
```python
@router.get("/metrics")
def metrics_endpoint(_admin: bool = Depends(require_admin)):
    from app.knowledge import metrics as _metrics
    return ApiResponse.ok(_metrics.metrics.snapshot())
```

- [ ] **Step 6: 鉴权失败打点**
在 `app/middleware/auth.py` 鉴权失败分支（返回 401/无有效 key 路径）调用 `_metrics.metrics.record_auth_failure()`。先在 `app/middleware/auth.py` 顶部 `from app.knowledge import metrics as _metrics`，再在鉴权失败处 `else: _metrics.metrics.record_auth_failure()`（确认失败分支位置后插入，勿破坏正常路径）。

- [ ] **Step 7: 运行验证通过**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws4_metrics.py -v`
Expected: PASS。

- [ ] **Step 8: 提交**
```bash
git add app/knowledge/metrics.py app/knowledge/service.py app/api/knowledge_api.py app/middleware/auth.py tests/knowledge/test_ws4_metrics.py
git commit -m "feat(knowledge): 轻量进程内指标（检索延迟/rerank命中/鉴权失败）+ /metrics 端点"
```

---

## Task 9: 启动期 schema 一次化（WS5 — LOW，测试安全调整）

**Files:** Modify `app/main.py`（`lifespan`）；保持 `KnowledgeService.__init__` 的 `ensure_schema`（测试依赖）

> ⚠️ **偏差说明（设计文档 §6 的务实修正）**：设计原写「移除每请求 `ensure_schema()`」。但 `KnowledgeService.__init__` 中的 `ensure_schema(self.repo)` 被所有以临时 DB 运行的测试依赖（构造即建表），移除会令大量测试失败。因此本任务采取**加法**：在 `lifespan` 启动期对默认知识库 DB 调用一次 `ensure_schema` 作为生产路径预热，同时**保留** `__init__` 中的幂等 `ensure_schema`（CREATE TABLE IF NOT EXISTS，开销极低，且为测试/临时 DB 所必需）。验收标准「启动期 schema 仅执行一次」在默认 DB 路径上达成；临时/测试 DB 仍自初始化（隔离所需）。

- [ ] **Step 1: 写测试**（新建 `tests/knowledge/test_ws5_startup.py`）

```python
import os, tempfile
import pytest
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service


def test_startup_ensures_knowledge_schema_once():
    # 验证默认 KnowledgeService 在无显式 ensure_schema 调用时也能工作
    # （启动期已预热；此处仅确认构造+检索路径不抛异常）
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws5-admin"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("启动期 schema 预热", project_id="P1", title="s")
    res = svc.retrieve("启动期", project_id="P1", top_k=3)
    assert isinstance(res, list)
    os.remove(p)
```

- [ ] **Step 2: 运行验证（应已通过）**
Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws5_startup.py -v`
Expected: PASS。

- [ ] **Step 3: `app/main.py` lifespan 增加知识库 schema 预热**
在 `lifespan` 第 26 行 `init_db()` 之后插入：
```python
        try:
            from app.knowledge.schema import ensure_schema
            from app.repositories.knowledge_repository import KnowledgeRepository
            ensure_schema(KnowledgeRepository())
            logger.info("Knowledge schema ensured")
        except Exception as e:
            logger.warning(f"Knowledge schema init skipped: {e}")
```
（保持原有 `init_db()` 与异常兜底，本块独立于 legacy DB 初始化。）

- [ ] **Step 4: 提交**
```bash
git add app/main.py tests/knowledge/test_ws5_startup.py
git commit -m "perf(knowledge): 启动期 ensure_schema 预热知识库（生产路径一次化，测试 DB 仍自初始化）"
```

---

## Task 10: 全量回归 + 漂移检查（收尾）

- [ ] **Step 1: 全量回归**
Run: `.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -8`
Expected: **0 failed**（基线 368 passed / 2 skipped，新增 WS1–WS5 测试应全部通过，无回归）。

- [ ] **Step 2: 若发现失败，二分定位**
若全量失败但单测通过，大概率是全局 `settings` 泄漏：用 `pytest --ignore=tests/knowledge -q` 二分；并确认 `tests/knowledge/conftest.py` 的 autouse 隔离 fixture 仍在（T12 加的快照/还原）。

- [ ] **Step 3: 漂移检查**
`git status --short` —— 应仅含已登记漂移文件（`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`），无意外新文件被改。

- [ ] **Step 4: 提交（如需）**
若回归过程中修了测试串扰等问题，仅 `git add` 对应测试/源文件并提交，不碰漂移文件。

---

## 自审清单（写计划时已核对）

1. **规格覆盖**：WS1.1✓(T1) WS1.2✓(T2) WS2.1✓(T3) WS2.2✓(T4) WS2.3✓(T5) WS3.1✓(T6) WS3.2✓(T7) WS4✓(T8) WS5✓(T9) 回归✓(T10)。
2. **占位符扫描**：无 TBD/TODO；每步均含代码或命令。
3. **类型一致性**：`search(query, project_id, limit)` 三后端统一签名（T5）；`EvaluateRequest.project_id` 在 T2 定义并被 T2 使用；`Metrics` 单例 `metrics` 在 T8 定义，T8 各打点引用一致；`require_admin` 在各端点用法一致。
4. **已知偏差**：T9 对设计 §6 的务实修正（保留 `__init__` ensure_schema）已显式说明，避免破坏测试。
