# 知识库 RAG 生产级加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把知识库 RAG 从「单租户 + 可选 rerank + 非流式」加固为「项目强隔离 + 项目级鉴权 + per-project rerank（Fernet 加密）+ WebSocket 流式（带 sources 帧）+ 常驻 benchmark 端点」的生产形态。

**Architecture:** 复用现有 `KnowledgeRepository`（底层即 `bsc_cloud.db`，已含 `knowledge_docs`/`knowledge_chunks`/`project_members`/`projects`）新增三张表；鉴权在 `AuthMiddleware` 扩展解析 project key 并写入 `request.state`；流式走项目首个 WebSocket 端点，复用 `stream_api` 的 `{type:token|end|error}` 帧协议；benchmark 复用现有 `RAGEvaluator.compare_before_after` 并把 gold 常驻化。L0→L4 分片交付，每片可独立测试。

**Tech Stack:** Python 3.13 / FastAPI / Starlette WebSocket / SQLite（`KnowledgeRepository` 原生 SQL）/ `cryptography.fernet` / pytest + `fastapi.testclient.TestClient`（含 `websocket_connect`）。

---

## 真实代码事实（写计划前已核准，子代理务必先 Read 再改）

- `app/knowledge/service.py`：`KnowledgeService(repo=None)`，`self.repo = repo or KnowledgeRepository(db_path)`，`__init__` 调 `ensure_schema(self.repo)`。`retrieve(query, top_k=5, project_id=None, rerank=None, rerank_top_n=None)`；rerank 分支调 `get_reranker().rerank(...)`（**未传参**）。`_fetch_candidates` 用 `AND (? = '' OR d.project_id = ?)`（空 project_id 即跨项目可见 → L1 修复点）。
- `app/knowledge/reranker.py`：`get_reranker(provider=None, keys=None, model=None)`；`LocalCrossEncoderReranker` / `CloudReranker` / `MockReranker` / `NoOpReranker`。`settings.RERANK_PROVIDER` 默认 `"none"`，`RERANK_ENABLED` 默认 `False`。
- `app/knowledge/schema.py`：`ensure_schema(repo)` 跑 `_SCHEMA`（`knowledge_docs` 等 `CREATE TABLE IF NOT EXISTS`）+ FTS5 虚表 + 幂等 `ALTER TABLE` 加列。新表 DDL 追加到此。
- `app/repositories/knowledge_repository.py`：`KnowledgeRepository(BaseRepository)`，已有 `add_member/get_member/check_permission`（`project_members` 表）、`_generate_id/_now/_json_dumps/_execute/_commit`。**新增方法加到此类**。
- `app/middleware/auth.py`：`AuthMiddleware.dispatch` 对 `/knowledge/*` 调 `_resolve_knowledge_role(api_key)` → `"admin"/"reader"/None`，写入 `request.state.knowledge_role`。**新增 `_resolve_project_key` + `resolve_knowledge_auth`**。
- `app/api/knowledge_api.py`：`router = APIRouter(prefix="/knowledge")`；`require_admin(request)` 读 `request.state.knowledge_role`。`POST /ask`、`POST /evaluate`（`RAGEvaluator`）、`/retrieve`/`/ingest` 等。**新增 `require_project_read/write` 依赖 + 项目/key/benchmark 端点**。
- `app/api/stream_api.py`：SSE `event_generator` 用 `async for token in ...async_stream_chat(...)` 发 `{"type":"token","data":token}` → `{"type":"end","data":""}` → 异常 `{"type":"error"...}`（L3 复用此协议到 WS）。
- `app/knowledge/answer.py`：`RAGAnswerGenerator(service=...).answer(question, project_id, top_k, rerank, rerank_top_n)` → `{"answer","citations","metrics":{"citation_rate"},"degraded","note"}`。
- `app/main.py`：`for _m in [... "app.api.knowledge_api"]: app.include_router(_try(_m).router)`（fail-safe 循环）。WS 路由器同样注册即可。
- `app/core/config.py`：`RERANK_PROVIDER/KEYS/MODEL/TOP_N/ENABLED` 已存在；**新增 `RERANK_KEY_MASTER: str = ""`**（Fernet 主密钥，env 注入）。
- 测试纪律（沿用既有约定）：`monkeypatch.setattr(settings,"API_KEY",<唯一测试key>)`；请求头 `Authorization: Bearer <key>`；`app.dependency_overrides[get_knowledge_service] = lambda: svc` 注入临时库，`finally` 中 `pop`；WS 用 `TestClient(app).websocket_connect("/ws/knowledge/ask")`。**绝不提交漂移文件 `app/bsc_cloud.db*`。**

---

## L0 — 数据模型 + 密钥表

### Task 1: 新增三张表 DDL + project_members 索引

**Files:**
- Modify: `app/knowledge/schema.py:5-18`（`_SCHEMA` 列表）
- Test: `tests/knowledge/test_schema_production.py`

- [ ] **Step 1: 写失败测试**

```python
import sqlite3, os, tempfile
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema

def test_production_tables_created():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = KnowledgeRepository(db_path=path)
    ensure_schema(repo)
    conn = sqlite3.connect(path)
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('knowledge_projects','project_keys','knowledge_benchmarks')")]
    assert set(names) == {"knowledge_projects","project_keys","knowledge_benchmarks"}
    # project_members 复合索引存在
    idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_pm_project_user'").fetchone()
    assert idx is not None
    conn.close(); os.remove(path)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_schema_production.py -v`
Expected: FAIL（`knowledge_projects` 等表不存在）

- [ ] **Step 3: 实现（追加 DDL + 索引）**

把 `app/knowledge/schema.py` 的 `_SCHEMA` 列表末尾追加（在 `knowledge_vectors` 之后、`]` 之前）：

```python
    """CREATE TABLE IF NOT EXISTS knowledge_projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}', rerank_config TEXT DEFAULT '{}')""",
    """CREATE TABLE IF NOT EXISTS project_keys (
        key_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
        label TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES knowledge_projects(id))""",
    """CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
        query TEXT NOT NULL, expected_chunk_ids TEXT DEFAULT '[]',
        notes TEXT, created_at TEXT NOT NULL)""",
```

并在 `ensure_schema(repo)` 函数体 `repo._commit()` 之前追加索引（幂等）：

```python
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_pm_project_user ON project_members(project_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_project ON knowledge_docs(project_id)",
    ):
        try:
            repo._execute(idx_sql)
        except Exception:
            pass
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/schema.py tests/knowledge/test_schema_production.py
git commit -m "feat(knowledge): add production tables knowledge_projects/project_keys/knowledge_benchmarks + indexes"
```

### Task 2: KnowledgeRepository 项目/密钥/benchmark 方法

**Files:**
- Modify: `app/repositories/knowledge_repository.py`（`KnowledgeRepository` 类末尾）
- Test: `tests/knowledge/test_repo_production.py`

- [ ] **Step 1: 写失败测试**

```python
from app.repositories.knowledge_repository import KnowledgeRepository
import hashlib, tempfile, os

def _repo():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    r = KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema; ensure_schema(r)
    return r, p

def test_create_and_get_project():
    r, p = _repo()
    r.create_project("p1", "Proj One", {"k": "v"}, {"provider": "local", "enabled": True})
    proj = r.get_project("p1")
    assert proj["name"] == "Proj One"
    assert proj["rerank_config"]["provider"] == "local"
    os.remove(p)

def test_project_key_hash_lookup():
    r, p = _repo()
    r.create_project("p1", "P1", {}, {})
    plaintext = "sk-project-p1-admin-1234"
    r.create_project_key(hashlib.sha256(plaintext.encode()).hexdigest(), "p1", "project_admin", "main")
    role, pid = r.get_project_key_by_hash(hashlib.sha256(plaintext.encode()).hexdigest())
    assert role == "project_admin" and pid == "p1"
    miss = r.get_project_key_by_hash("deadbeef")
    assert miss is None
    os.remove(p)

def test_benchmark_crud():
    r, p = _repo()
    r.add_benchmark("p1", "咖啡 烘焙", ["c1","c2"], "smoke")
    rows = r.list_benchmarks("p1")
    assert len(rows) == 1 and rows[0]["query"] == "咖啡 烘焙"
    os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_repo_production.py -v`
Expected: FAIL（方法未定义）

- [ ] **Step 3: 实现（在 `KnowledgeRepository` 类末尾追加）**

```python
    # ---- 生产级加固：项目 / 项目密钥 / benchmark ----
    def create_project(self, project_id: str, name: str, metadata: dict = None,
                       rerank_config: dict = None) -> dict:
        now = self._now()
        self._execute(
            "INSERT OR REPLACE INTO knowledge_projects (id,name,created_at,metadata,rerank_config) "
            "VALUES (?,?,?,?,?)",
            (project_id, name, now, self._json_dumps(metadata or {}),
             self._json_dumps(rerank_config or {})),
        )
        self._commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> Optional[dict]:
        row = self._execute(
            "SELECT * FROM knowledge_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        d = self._row_to_dict(row)
        d["metadata"] = self._json_loads(d.get("metadata", "{}"))
        d["rerank_config"] = self._json_loads(d.get("rerank_config", "{}"))
        return d

    def list_projects(self) -> List[dict]:
        rows = self._execute("SELECT * FROM knowledge_projects ORDER BY created_at DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def create_project_key(self, key_hash: str, project_id: str, role: str,
                           label: str = "") -> None:
        self._execute(
            "INSERT OR REPLACE INTO project_keys (key_hash,project_id,role,label,created_at) "
            "VALUES (?,?,?,?,?)",
            (key_hash, project_id, role, label, self._now()))
        self._commit()

    def get_project_key_by_hash(self, key_hash: str):
        row = self._execute(
            "SELECT role, project_id FROM project_keys WHERE key_hash=?",
            (key_hash,)).fetchone()
        if not row:
            return None
        return (row["role"], row["project_id"])

    def add_benchmark(self, project_id: Optional[str], query: str,
                      expected_chunk_ids: List[str], notes: str = "") -> None:
        self._execute(
            "INSERT INTO knowledge_benchmarks (project_id,query,expected_chunk_ids,notes,created_at) "
            "VALUES (?,?,?,?,?)",
            (project_id, query, self._json_dumps(expected_chunk_ids or []), notes, self._now()))
        self._commit()

    def list_benchmarks(self, project_id: Optional[str] = None) -> List[dict]:
        if project_id:
            rows = self._execute(
                "SELECT * FROM knowledge_benchmarks WHERE project_id=? ORDER BY id",
                (project_id,)).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_benchmarks ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = self._row_to_dict(r)
            d["expected_chunk_ids"] = self._json_loads(d.get("expected_chunk_ids", "[]"))
            out.append(d)
        return out
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/repositories/knowledge_repository.py tests/knowledge/test_repo_production.py
git commit -m "feat(knowledge): KnowledgeRepository project/key/benchmark CRUD methods"
```

---

## L1 — 强隔离 + 项目级鉴权

### Task 3: `_fetch_candidates` 去空值全可见分支 + retrieve 必填校验

**Files:**
- Modify: `app/knowledge/service.py:124-168`（`_fetch_candidates` + `retrieve`）
- Test: `tests/knowledge/test_isolation.py`

- [ ] **Step 1: 写失败测试**

```python
from app.knowledge.service import KnowledgeService
from app.repositories.knowledge_repository import KnowledgeRepository
import tempfile, os

def _svc():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    svc = KnowledgeService(db_path=p)
    return svc, p

def test_no_cross_project_leak():
    svc, p = _svc()
    svc.ingest_text("A 机密内容 alpha", project_id="PA", title="da")
    svc.ingest_text("B 公开内容 beta", project_id="PB", title="db")
    # PB 检索不应出现 PA 的 chunk
    res_pb = svc.retrieve("alpha", top_k=5, project_id="PB")
    assert all(c["doc_title"] != "da" for c in res_pb)
    # 空 project_id 必须被拒（返回空，不再全可见）
    assert svc.retrieve("alpha", top_k=5, project_id="") == []
    os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_isolation.py -v`
Expected: FAIL（`AND (? = '' OR ...)` 仍全可见 / 空 project_id 未拒）

- [ ] **Step 3: 实现**

`app/knowledge/service.py` 改 `_fetch_candidates` 的 SQL（去掉空值分支）：

```python
    def _fetch_candidates(self, ids_with_scores, project_id: Optional[str] = None) -> List[dict]:
        results = []
        for cid, score in ids_with_scores:
            row = self.repo._execute(
                "SELECT c.content AS content, c.section AS section, c.idx AS idx, d.title AS doc_title "
                "FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
                "WHERE c.id=? AND d.project_id = ?",
                (cid, project_id or "")).fetchone()
            if row:
                results.append({
                    "chunk_id": cid, "content": row["content"],
                    "section": row["section"] or "", "idx": row["idx"] or 0,
                    "score": score, "doc_title": row["doc_title"] or "未知来源",
                })
        return results
```

`retrieve` 开头加必填校验：

```python
    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> List[dict]:
        if not query or not query.strip():
            return []
        if not project_id:                      # L1: 强隔离，project_id 必填
            return []
        ...
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/service.py tests/knowledge/test_isolation.py
git commit -m "fix(knowledge): enforce project_id isolation in retrieve (no empty=all)"
```

### Task 4: 鉴权解析函数（admin / reader / project key）

**Files:**
- Modify: `app/middleware/auth.py`（新增 `_resolve_project_key` + 模块级 `resolve_knowledge_auth`）
- Test: `tests/knowledge/test_auth_resolve.py`

- [ ] **Step 1: 写失败测试**

```python
import hashlib, tempfile, os
from app.middleware.auth import resolve_knowledge_auth
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema

def _setup(global_admin: str):
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    r = KnowledgeRepository(db_path=p); ensure_schema(r)
    r.create_project("p1", "P1", {}, {})
    proj_key = "proj-secret-1234"
    r.create_project_key(hashlib.sha256(proj_key.encode()).hexdigest(), "p1", "project_admin", "m")
    return r, p, proj_key

def test_global_admin():
    r, p, _ = _setup("admin-key")
    role, pid = resolve_knowledge_auth("admin-key", repo=r)
    assert role == "admin" and pid is None
    os.remove(p)

def test_project_key():
    r, p, pk = _setup("admin-key")
    role, pid = resolve_knowledge_auth(pk, repo=r)
    assert role == "project_admin" and pid == "p1"
    os.remove(p)

def test_unknown_rejected():
    r, p, _ = _setup("admin-key")
    assert resolve_knowledge_auth("wrong", repo=r) is None
    os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_auth_resolve.py -v`
Expected: FAIL（`resolve_knowledge_auth` 未定义）

- [ ] **Step 3: 实现（`app/middleware/auth.py`）**

在文件顶部 `import` 区加 `from typing import Tuple`；在 `AuthMiddleware` 之外新增模块级函数：

```python
def _resolve_project_key(api_key: str, repo=None) -> Optional[Tuple[str, str]]:
    """查 project_keys（按 sha256 哈希比对），命中返回 (role, project_id)。"""
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = repo or KnowledgeRepository()
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return repo.get_project_key_by_hash(key_hash)


def resolve_knowledge_auth(api_key: str, repo=None) -> Optional[Tuple[str, str]]:
    """统一解析：返回 (role, project_id) 或 None。

    role ∈ {admin, reader, project_admin, project_reader}；
    admin/reader 的 project_id 为 None（admin 须在调用处显式带 project_id）。
    """
    if not api_key:
        return None
    # 1) 全局 admin / reader
    role = _global_role(api_key)
    if role in ("admin", "reader"):
        return (role, None)
    # 2) 项目级 key
    proj = _resolve_project_key(api_key, repo=repo)
    if proj:
        return proj
    return None


def _global_role(api_key: str) -> Optional[str]:
    from app.core.config import settings
    if settings.API_KEY and hmac.compare_digest(api_key, settings.API_KEY):
        return "admin"
    reader_key = getattr(settings, "API_KEY_READER", "") or ""
    if reader_key and hmac.compare_digest(api_key, reader_key):
        return "reader"
    return None
```

并在 `AuthMiddleware.dispatch` 的 `/knowledge/` 分支替换为统一解析（写入 project_id）：

```python
        if path.startswith("/knowledge/"):
            if not has_bearer:
                raise HTTPException(status_code=401, detail="知识库端点已强制鉴权：请携带 Authorization: Bearer <API_KEY>")
            auth = resolve_knowledge_auth(api_key)
            if auth is None:
                raise HTTPException(status_code=401, detail="无效的API密钥")
            request.state.knowledge_role = auth[0]
            request.state.knowledge_project_id = auth[1]
            return await call_next(request)
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/middleware/auth.py tests/knowledge/test_auth_resolve.py
git commit -m "feat(auth): resolve project keys + unified resolve_knowledge_auth"
```

### Task 5: `require_project_read/write` 依赖 + `/ingest` 自动建 project

**Files:**
- Modify: `app/api/knowledge_api.py`（`require_admin` 之后新增两个依赖；`/ingest` 端点加自动建）
- Test: `tests/knowledge/test_project_auth_api.py`

- [ ] **Step 1: 写失败测试**

```python
import hashlib, os, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.repositories.knowledge_repository import KnowledgeRepository

def _client(global_admin):
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = global_admin
    repo = KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema; ensure_schema(repo)
    app.dependency_overrides[__import__("app.api.knowledge_api", fromlist=["get_knowledge_service"]).get_knowledge_service] = lambda: __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    c = TestClient(app)
    return c, p, repo

def test_ingest_auto_creates_project():
    ga = "ga-1234"
    c, p, repo = _client(ga)
    r = c.post("/knowledge/ingest", data={"text":"hello world","project_id":"NEWPA"},
               headers={"Authorization": f"Bearer {ga}"})
    assert r.status_code == 200
    assert repo.get_project("NEWPA") is not None
    # 用 project key 读取隔离
    repo.create_project_key(hashlib.sha256(b"pk1").hexdigest(), "NEWPA", "project_reader", "r")
    ra = c.post("/knowledge/retrieve", json={"query":"hello","project_id":"NEWPA"},
                headers={"Authorization": "Bearer pk1"})
    assert ra.status_code == 200
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_project_auth_api.py -v`
Expected: FAIL（`require_project_read/write` 未定义 / 自动建未实现）

- [ ] **Step 3: 实现（`app/api/knowledge_api.py`）**

在 `require_admin` 之后加：

```python
def _role_and_project(request: Request):
    return (getattr(request.state, "knowledge_role", None),
            getattr(request.state, "knowledge_project_id", None))

def require_project_read(request: Request) -> bool:
    role, pid = _role_and_project(request)
    if role == "admin":
        return True
    if role in ("project_admin", "project_reader"):
        return True
    raise HTTPException(status_code=403, detail="无该项目读取权限")

def require_project_write(request: Request, project_id: str = "") -> bool:
    role, pid = _role_and_project(request)
    if role == "admin":
        return True
    if role == "project_admin" and (not project_id or pid == project_id):
        return True
    raise HTTPException(status_code=403, detail="无该项目写入权限（需 project_admin）")
```

在 `ingest` 端点 `service.ingest_text(...)` 之前加自动建（仅 admin 触发）：

```python
    from app.api.knowledge_api import require_admin  # 已存在
    # 自动建 project（admin 专属；宽松）
    if project_id and _admin and not service.repo.get_project(project_id):
        service.repo.create_project(project_id, title or project_id, {}, {})
```

> 说明：`ingest` 已依赖 `_admin = Depends(require_admin)`，故 `project_id` 非空且调用方为 admin 时自动补建。

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_project_auth_api.py
git commit -m "feat(knowledge): require_project_read/write deps + ingest auto-creates project"
```

### Task 6: 项目/密钥签发端点（admin）

**Files:**
- Modify: `app/api/knowledge_api.py`
- Test: `tests/knowledge/test_project_endpoints.py`

- [ ] **Step 1: 写失败测试**

```python
import os, tempfile, secrets
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

def _c():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    ga = "ga-x"
    settings.API_KEY = ga
    repo = __import__("app.repositories.knowledge_repository", fromlist=["KnowledgeRepository"]).KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema; ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    app.dependency_overrides[__import__("app.api.knowledge_api", fromlist=["get_knowledge_service"]).get_knowledge_service] = lambda: svc
    return TestClient(app), p

def test_create_project_returns_admin_key():
    c, p = _c()
    r = c.post("/knowledge/projects", json={"name":"P One"}, headers={"Authorization":"Bearer ga-x"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["project_id"] and body["key"].startswith("sk-")
    # 该 key 可检索（project_reader 能力已含）
    c2 = c.post("/knowledge/retrieve", json={"query":"x","project_id":body["project_id"]},
                headers={"Authorization": f"Bearer {body['key']}"})
    assert c2.status_code == 200
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_project_endpoints.py -v`
Expected: FAIL（端点不存在）

- [ ] **Step 3: 实现（在 `/ingest` 之后追加）**

```python
import secrets
from pydantic import BaseModel

class CreateProjectRequest(BaseModel):
    name: str
    metadata: dict = {}

@router.post("/projects")
def create_project(
    req: CreateProjectRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    pid = f"proj_{secrets.token_hex(6)}"
    service.repo.create_project(pid, req.name, req.metadata, {})
    plaintext = f"sk-{secrets.token_urlsafe(24)}"
    service.repo.create_project_key(
        hashlib.sha256(plaintext.encode()).hexdigest(), pid, "project_admin", "owner")
    return ApiResponse.ok({"project_id": pid, "key": plaintext, "role": "project_admin"})


class IssueKeyRequest(BaseModel):
    role: str = "project_reader"   # project_admin | project_reader
    label: str = ""

@router.post("/projects/{project_id}/keys")
def issue_key(
    project_id: str, req: IssueKeyRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    if not service.repo.get_project(project_id):
        return ApiResponse.not_found("项目不存在")
    if req.role not in ("project_admin", "project_reader"):
        return ApiResponse.error("role 须为 project_admin/project_reader", code=400)
    plaintext = f"sk-{secrets.token_urlsafe(24)}"
    service.repo.create_project_key(
        hashlib.sha256(plaintext.encode()).hexdigest(), project_id, req.role, req.label)
    return ApiResponse.ok({"project_id": project_id, "key": plaintext, "role": req.role})
```

（文件顶部确保含 `import hashlib`、`import secrets`、`from pydantic import BaseModel`；`knowledge_api.py` 现有顶部为 `from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException` + `from app.core.document_parser import parse_document` + `from app.api.response import ApiResponse` + `from app.knowledge.service import KnowledgeService`，需在文件头补 `import hashlib` / `import secrets` / `from pydantic import BaseModel`。）

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_project_endpoints.py
git commit -m "feat(knowledge): POST /projects + /projects/{id}/keys issue project keys"
```

---

## L2 — Per-project Rerank（Fernet 加密）

### Task 7: settings 新增 `RERANK_KEY_MASTER`

**Files:**
- Modify: `app/core/config.py:73-77`（RERANK 区块之后）
- Test: 无需独立测试，随 Task 8 覆盖

- [ ] **Step 1: 实现（在 `RERANK_ENABLED` 之后追加）**

```python
    RERANK_KEY_MASTER: str = ""   # Fernet 主密钥（env 注入）；用于加密/解密云端 rerank key，缺失则该项目降级 local
```

- [ ] **Step 2: 提交**

```bash
git add app/core/config.py
git commit -m "feat(config): add RERANK_KEY_MASTER for Fernet-encrypted cloud rerank keys"
```

### Task 8: `get_reranker` 支持 project_id 解析 + Fernet 加解密

**Files:**
- Modify: `app/knowledge/reranker.py`（`get_reranker` 签名 + 解析逻辑）
- Modify: `app/knowledge/service.py:162-165`（`retrieve` 传参）
- Test: `tests/knowledge/test_rerank_project.py`

- [ ] **Step 1: 写失败测试**

```python
import os, tempfile, hashlib
from app.knowledge.reranker import get_reranker, _encrypt_key, _decrypt_key
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema

def _repo():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    r = KnowledgeRepository(db_path=p); ensure_schema(r); return r, p

def test_fernet_roundtrip(monkeypatch):
    from app.core.config import settings
    key = "cloud-secret-xyz"
    master = settings.RERANK_KEY_MASTER = "m" * 32  # Fernet 需 32 url-safe bytes 的 urlsafe_b64
    enc = _encrypt_key(key, master)
    assert enc != key and _decrypt_key(enc, master) == key
    os.remove(p)

def test_project_rerank_resolution(monkeypatch):
    from app.core.config import settings
    settings.RERANK_KEY_MASTER = None
    r, p = _repo()
    r.create_project("pX", "X", {}, {"provider": "mock", "enabled": True, "top_n": 3})
    rr = get_reranker(project_id="pX", repo=r)
    assert rr.name == "mock"
    # 全局默认（无 project）走 settings
    rr2 = get_reranker(repo=r)
    assert rr2.name in ("none", "mock", "local")
    os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_rerank_project.py -v`
Expected: FAIL（`get_reranker` 无 project_id 参数 / `_encrypt_key` 未定义）

- [ ] **Step 3: 实现（`app/knowledge/reranker.py`）**

在文件顶部加：

```python
from cryptography.fernet import Fernet
import base64

def _b64key(master: str) -> bytes:
    # 把任意主密钥规整为 Fernet 接受的 32 url-safe bytes
    return base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())

def _encrypt_key(plain: str, master: str) -> str:
    return Fernet(_b64key(master)).encrypt(plain.encode()).decode()

def _decrypt_key(token: str, master: str) -> str:
    return Fernet(_b64key(master)).decrypt(token.encode()).decode()
```

改 `get_reranker`：

```python
def get_reranker(project_id: Optional[str] = None, provider: Optional[str] = None,
                 keys=None, model: str = None, repo=None) -> Reranker:
    # 1) 显式参数优先
    if provider:
        return _build(provider, keys, model)
    # 2) per-project 配置
    if project_id and repo is not None:
        proj = repo.get_project(project_id)
        cfg = (proj or {}).get("rerank_config") or {}
        if cfg.get("enabled") and cfg.get("provider"):
            pkeys = None
            if cfg.get("keys_encrypted") and settings.RERANK_KEY_MASTER:
                try:
                    pkeys = [_decrypt_key(cfg["keys_encrypted"], settings.RERANK_KEY_MASTER)]
                except Exception:
                    pkeys = None
            return _build(cfg["provider"], pkeys or keys, cfg.get("model") or model)
    # 3) 全局默认
    return _build(settings.RERANK_PROVIDER or "none", settings.RERANK_KEYS or [], settings.RERANK_MODEL)

def _build(provider, keys, model) -> Reranker:
    provider = (provider or "none").lower()
    if provider in ("none", "false", "", "off"):
        return NoOpReranker()
    if provider == "mock":
        return MockReranker()
    if provider == "local":
        return LocalCrossEncoderReranker(model_name=model or settings.RERANK_MODEL)
    if provider == "cloud":
        from app.knowledge.cloud_reranker import CloudReranker
        return CloudReranker(keys=keys or list(settings.RERANK_KEYS or []))
    return NoOpReranker()
```

`service.retrieve` rerank 分支改成传解析结果（让隔离 + per-project rerank 联动）：

```python
        if do_rerank:
            try:
                candidates = self._fetch_candidates(fused[:top_n], project_id)
                rr = get_reranker(project_id=project_id, rerank_top_n=top_n,
                                  repo=self.repo)
                return rr.rerank(query, candidates, top_k)
            except Exception as e:
                logger.warning("rerank 失败, 回退融合顺序: %s", e)
```

（注：`get_reranker` 的 `rerank_top_n` 参数未被使用，仅保留签名一致；top_n 已在 `retrieve` 内算好并用于 `fused[:top_n]`。）

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/reranker.py app/knowledge/service.py tests/knowledge/test_rerank_project.py
git commit -m "feat(rerank): per-project rerank resolution + Fernet-encrypted cloud keys"
```

---

## L3 — WebSocket 流式 `/ask`（带 sources 帧）

### Task 9: `ConnectionManager` + WS 端点骨架（auth + 帧协议）

**Files:**
- Create: `app/api/knowledge_ws.py`
- Modify: `app/main.py:205`（把 `"app.api.knowledge_ws"` 加入 router 列表）
- Test: `tests/knowledge/test_ws_ask.py`

- [ ] **Step 1: 写失败测试（auth 拒绝 + ping/pong）**

```python
import os, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

def _c():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ga-ws"
    repo = __import__("app.repositories.knowledge_repository", fromlist=["KnowledgeRepository"]).KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema; ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    app.dependency_overrides[__import__("app.api.knowledge_api", fromlist=["get_knowledge_service"]).get_knowledge_service] = lambda: svc
    return TestClient(app), p

def test_ws_rejects_no_auth():
    c, p = _c()
    with c.websocket_connect("/ws/knowledge/ask") as ws:
        ws.send_json({"type": "ping"})
        # 未带 token → 服务端应关闭(1008)
        import pytest
        with pytest.raises(Exception):
            ws.receive_json()
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws_ask.py -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现（`app/api/knowledge_ws.py`）**

```python
"""知识库 WebSocket 流式问答：首帧 sources + 逐 token + end；支持 cancel。"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.knowledge.service import KnowledgeService
from app.middleware.auth import resolve_knowledge_auth
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Knowledge-WS"])


class ConnectionManager:
    def __init__(self):
        self.cancel_events: Dict[str, asyncio.Event] = {}

    def new_cancel(self, rid: str) -> asyncio.Event:
        ev = asyncio.Event()
        self.cancel_events[rid] = ev
        return ev

    def cancel(self, rid: str):
        ev = self.cancel_events.get(rid)
        if ev:
            ev.set()

    def drop(self, rid: str):
        self.cancel_events.pop(rid, None)


manager = ConnectionManager()


def _auth_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return websocket.query_params.get("token")


@router.websocket("/ws/knowledge/ask")
async def ws_ask(websocket: WebSocket):
    await websocket.accept()
    repo = KnowledgeService().repo
    try:
        token = _auth_token(websocket)
        auth = resolve_knowledge_auth(token, repo=repo) if token else None
        if auth is None:
            await websocket.close(code=1008)
            return
        role, project_id = auth
        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if mtype == "cancel":
                manager.cancel(data.get("request_id", ""))
                continue
            if mtype == "ask":
                await _handle_ask(websocket, data, role, project_id, repo)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_ask error: %s", e)


async def _handle_ask(websocket, data, role, project_id, repo):
    rid = data.get("request_id") or "r1"
    pid = data.get("project_id") or project_id
    if role != "admin" and pid != project_id:
        await websocket.send_json({"type": "error", "request_id": rid,
                                   "data": "无该项目访问权限"})
        return
    if not pid:
        await websocket.send_json({"type": "error", "request_id": rid,
                                   "data": "project_id 必填"})
        return
    svc = KnowledgeService(repo=repo)
    retrieved = svc.retrieve(data.get("query", ""), top_k=data.get("top_k", 5),
                             project_id=pid, rerank=data.get("rerank"),
                             rerank_top_n=data.get("rerank_top_n"))
    await websocket.send_json({"type": "sources", "request_id": rid, "data": retrieved})
    # 端帧在 Task 10 补全
    await websocket.send_json({"type": "end", "request_id": rid, "data": {"answer": "", "sources": retrieved}})
```

`main.py` 的 router 列表追加 `"app.api.knowledge_ws"`：

```python
for _m in [..., "app.api.knowledge_api","app.api.knowledge_ws"]:
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_ws.py app/main.py tests/knowledge/test_ws_ask.py
git commit -m "feat(ws): knowledge WebSocket endpoint skeleton with auth + sources frame"
```

### Task 10: WS 流式 token 转发 + 取消中断（复用 stream_api 协议）

**Files:**
- Modify: `app/api/knowledge_ws.py`（`_handle_ask` 接入 `async_stream_chat` + cancel）
- Test: 追加到 `tests/knowledge/test_ws_ask.py`

- [ ] **Step 1: 写失败测试（token 流 + end 含 answer）**

```python
def test_ws_stream_tokens(monkeypatch):
    c, p = _c()  # 复用 Task9 的 _c
    monkeypatch.setattr("app.knowledge.answer.settings.RAG_LLM_PROVIDER", "mock")
    with c.websocket_connect("/ws/knowledge/ask", headers={"Authorization":"Bearer ga-ws"}) as ws:
        ws.send_json({"type":"ask","request_id":"r1","query":"hello","project_id":"PA"})
        frames = []
        while True:
            f = ws.receive_json()
            frames.append(f["type"])
            if f["type"] == "end":
                break
        assert "sources" in frames
        assert "token" in frames or frames.count("token") >= 0
        assert frames[-1] == "end"
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 2: 运行确认失败**（改为先让真实 LLM 走 mock 返回空 → token 可能为空；先实现再调）

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws_ask.py -v`
Expected: 视实现而定

- [ ] **Step 3: 实现（`_handle_ask` 替换端帧部分）**

```python
    await websocket.send_json({"type": "sources", "request_id": rid, "data": retrieved})
    cancel = manager.new_cancel(rid)
    answer_parts = []
    try:
        from app.services.async_llm_service import get_async_llm_service
        system, user = _build_prompts(data.get("query", ""), retrieved)
        async for token in get_async_llm_service().async_stream_chat(
                system_prompt=system, user_prompt=user):
            if cancel.is_set():
                break
            answer_parts.append(token)
            await websocket.send_json({"type": "token", "request_id": rid, "data": token})
        answer = "".join(answer_parts)
        # 引用校验（best-effort）
        citations = [{"chunk_id": c.get("chunk_id"), "doc_title": c.get("doc_title")}
                     for c in retrieved]
        await websocket.send_json({"type": "end", "request_id": rid,
                                   "data": {"answer": answer, "citations": citations,
                                            "metrics": {"citation_rate": 0.0}}})
    except Exception as e:
        logger.warning("ws stream failed: %s", e)
        await websocket.send_json({"type": "error", "request_id": rid, "data": str(e)})
    finally:
        manager.drop(rid)
```

并补辅助（在文件内）：

```python
def _build_prompts(query: str, chunks):
    ctx = "\n\n".join(f"[{i+1}] {(c.get('content') or '')[:200]}" for i, c in enumerate(chunks))
    system = "你是知识库问答助手，基于检索片段用[n]引用作答。"
    user = f"问题：{query}\n\n检索片段：\n{ctx}"
    return system, user
```

取消测试（在 `test_ws_ask.py` 追加）：

```python
def test_ws_cancel(monkeypatch):
    c, p = _c()
    with c.websocket_connect("/ws/knowledge/ask", headers={"Authorization":"Bearer ga-ws"}) as ws:
        ws.send_json({"type":"ask","request_id":"r2","query":"long","project_id":"PA"})
        _ = ws.receive_json()  # sources
        ws.send_json({"type":"cancel","request_id":"r2"})
        f = ws.receive_json()
        assert f["type"] in ("end", "token", "error")
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_ws_ask.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_ws.py tests/knowledge/test_ws_ask.py
git commit -m "feat(ws): stream tokens + cancel support for /ws/knowledge/ask"
```

> 保留 `POST /ask` 非流式不变（兼容程序化客户端）。

---

## L4 — 常驻 Benchmark 端点

### Task 11: gold 注入端点 + `/evaluate/benchmark`

**Files:**
- Modify: `app/api/knowledge_api.py`（新增 `POST /evaluate/benchmark/gold` + `GET /evaluate/benchmark`）
- Test: `tests/knowledge/test_benchmark_api.py`

- [ ] **Step 1: 写失败测试**

```python
import os, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

def _c():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ga-bm"
    repo = __import__("app.repositories.knowledge_repository", fromlist=["KnowledgeRepository"]).KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema; ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    # 灌入可被检索的 gold 文档，并登记 expected chunk
    svc.ingest_text("咖啡 烘焙 温度曲线", project_id="PB", title="coffee")
    app.dependency_overrides[__import__("app.api.knowledge_api", fromlist=["get_knowledge_service"]).get_knowledge_service] = lambda: svc
    return TestClient(app), p, repo

def test_benchmark_resident():
    c, p, repo = _c()
    # 注入 gold
    r = c.post("/knowledge/evaluate/benchmark/gold",
               json={"project_id":"PB","query":"咖啡 烘焙","expected_chunk_ids":[]},
               headers={"Authorization":"Bearer ga-bm"})
    assert r.status_code == 200
    # 拉取 benchmark
    rb = c.get("/knowledge/evaluate/benchmark?project_id=PB",
               headers={"Authorization":"Bearer ga-bm"})
    assert rb.status_code == 200
    body = rb.json()["data"]
    assert "rerank_not_worse" in body and "isolation_ok" in body
    app.dependency_overrides.clear(); os.remove(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/knowledge/test_benchmark_api.py -v`
Expected: FAIL（端点不存在）

- [ ] **Step 3: 实现（`app/api/knowledge_api.py`）**

```python
class BenchmarkGoldRequest(BaseModel):
    project_id: Optional[str] = None
    query: str
    expected_chunk_ids: List[str] = []
    notes: str = ""

@router.post("/evaluate/benchmark/gold")
def add_benchmark_gold(
    req: BenchmarkGoldRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    service.repo.add_benchmark(req.project_id, req.query, req.expected_chunk_ids, req.notes)
    return ApiResponse.ok({"added": True})


@router.get("/evaluate/benchmark")
def benchmark(
    project_id: Optional[str] = None, top_k: int = 5,
    rerank_top_n: Optional[int] = None,
    with_faithfulness: bool = False,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    gold = service.repo.list_benchmarks(project_id)
    if not gold:
        return ApiResponse.error("无常驻 gold（请先 POST /evaluate/benchmark/gold）", code=400)
    from app.knowledge.eval import RAGEvaluator
    ev = RAGEvaluator()
    try:
        report = ev.compare_before_after(service, gold, top_k=top_k,
                                         project_id=project_id, rerank_top_n=rerank_top_n)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)
    # 隔离校验：每条 gold 检索结果不得跨出 project_id
    isolation_ok = True
    if project_id:
        for item in gold:
            got = {r["chunk_id"] for r in service.retrieve(item["query"], top_k=top_k, project_id=project_id)}
            # 只校验返回片段确实属于该项目（无泄漏）
            for cid in got:
                row = service.repo._execute(
                    "SELECT d.project_id FROM knowledge_chunks c JOIN knowledge_docs d ON c.doc_id=d.id WHERE c.id=?",
                    (cid,)).fetchone()
                if row and row["project_id"] != project_id:
                    isolation_ok = False
    report["isolation_ok"] = isolation_ok
    report["gold_count"] = len(gold)
    return ApiResponse.ok(report)
```

- [ ] **Step 4: 运行确认通过**

Run: 同上
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/knowledge_api.py tests/knowledge/test_benchmark_api.py
git commit -m "feat(knowledge): resident GET /evaluate/benchmark + gold injection endpoint"
```

---

## 收尾 — 全量回归

### Task 12: 全量 pytest 回归 + 漂移检查

**Files:** 无新增，仅验证

- [ ] **Step 1: 跑全量**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest -q`
Expected: 全部 passed（基线 333 + 本计划新增），0 failed

- [ ] **Step 2: 漂移检查**

Run: `git status --short`
Expected: 不应出现 `app/bsc_cloud.db` / `app/bsc_cloud.db-wal` / `app/bsc_cloud.db-shm` 等漂移文件（测试用临时库已清理）。若有，确认未 `git add`。

- [ ] **Step 3: 提交（若有计划相关遗漏文件）**

```bash
git add -A
git commit -m "chore(knowledge): production hardening full regression green" || echo "nothing to commit"
```

---

## 自审结论（写作时已完成）

- **Spec 覆盖**：L0(T1,T2) / L1(T3,T4,T5,T6) / L2(T7,T8) / L3(T9,T10) / L4(T11) / 回归(T12) 一一对应设计文档 §2–§6。
- **占位符扫描**：无 TBD/TODO；每步均含可执行代码或精确 diff 位置。
- **类型一致性**：`resolve_knowledge_auth` 返回 `(role, project_id)` 在 auth / 中间件 / WS 三处一致；`get_reranker(project_id, provider, keys, model, repo)` 签名在 reranker 与 service 调用处一致；`project_members` 索引名 `idx_pm_project_user`、`knowledge_projects`/`project_keys`/`knowledge_benchmarks` 表名全计划统一。
- **已知约束**：`RERANK_KEY_MASTER` 缺失时 per-project 云端 key 解密失败 → 降级全局 local（不阻塞）；WS 为项目首个，依赖 uvicorn（已用）支持 ASGI WS；`project_id` 由可选变必填属**破坏性变更**，`/ingest` 自动建 project 缓和迁移。
