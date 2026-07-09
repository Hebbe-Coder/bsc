# 知识库稠密向量检索后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有 `KnowledgeService` 可插拔后端注册表里新增第三类后端 `VectorBackend`（稠密 embedding 向量），补足 TF-IDF 对同义/改写召回的短板。

**Architecture:** 抽象 `EmbeddingProvider`（默认 `MockEmbeddingProvider` 离线确定性 + `RemoteEmbeddingProvider` 走远程 OpenAI 兼容 `/v1/embeddings`）；`VectorBackend` 复用 `index(chunk_records)` / `search(query)->List[chunk_id]` 接口，按余弦排序；`KnowledgeService.retrieve` 把 `vec_ids` 作为第三路并入 `rrf_fuse([kw_ids, tf_ids, vec_ids])`。向量增量写入新表 `knowledge_vectors`（BLOB 存 `np.float32`），远程失败即抛、由后端捕获降级为空，检索退化为 keyword+tfidf 两路。

**Tech Stack:** Python 3.13, FastAPI, numpy 2.5（已装）, httpx（已装，注入式测试）。零新重依赖。

**项目路径:** `C:\Users\34216\Documents\New project 3\bsc-backend`（git repo root，路径均相对它）。
**测试命令（Windows + Git Bash，必须用项目自带 venv）:** `/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest <args>`

**git 纪律（贯穿全程，不可违反）:** 工作树存在刻意保留的未提交漂移，**严禁触碰或提交**：
- `app/bsc_cloud.db`、`app/bsc_cloud.db-shm`
- `app/services/llm_service.py`（已修改，不碰）
- `static/dashboard.html`（已修改，不碰）
- `archive/orphan_fork/...`（已删除）
提交时**只** `git add` 本计划明确列出的文件，绝不 `git add -A` 或 `git add .`。

---

### Task 1: config.py 新增 `EMBEDDING_*` 配置

**Files:**
- Modify: `app/core/config.py` (紧接 `SOP_LLM_PROVIDER` 行之后插入)

- [ ] **Step 1: 在 `SOP_LLM_PROVIDER` 行后插入 4 行配置**

定位（精确锚点）:
```python
    SOP_LLM_PROVIDER: str = "mock"  # SOP AI 段使用的 LLM provider (deepseek/doubao/qwen/kimi/mock)
```
在其后新增（保留其后原有空行）:
```python
    EMBEDDING_PROVIDER: str = "mock"  # 向量检索 embedding 来源 (mock/openai)
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
```

- [ ] **Step 2: 写失败测试并先跑（应 FAIL，尚未读取该属性）**

新建 `tests/test_config_embedding.py`:
```python
from app.core.config import settings


def test_embedding_provider_default_is_mock():
    assert hasattr(settings, "EMBEDDING_PROVIDER")
    assert settings.EMBEDDING_PROVIDER == "mock"


def test_embedding_config_defaults():
    assert settings.EMBEDDING_BASE_URL == "https://api.openai.com/v1"
    assert settings.EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.EMBEDDING_API_KEY == ""
```
运行:
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/test_config_embedding.py -v`
Expected: PASS（属性本就存在？确认：当前 config 无 `EMBEDDING_*`，但 `settings` 是 pydantic，`hasattr` 对未声明字段返回 False → 此处其实会 FAIL 在 `test_embedding_provider_default_is_mock` 的 `hasattr` 为 False）。Step 1 已写入则 PASS。若 Step 1 未执行则 FAIL —— 这正是红绿验证。

- [ ] **Step 3: 运行确认 PASS**

运行同 Step 2，Expected: PASS（2 passed）。

- [ ] **Step 4: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/core/config.py tests/test_config_embedding.py
git commit -m "feat(config): add EMBEDDING_* for dense vector retrieval (mock default)"
```

---

### Task 2: Embedding 抽象层（Provider + 工厂）

**Files:**
- Create: `app/knowledge/embeddings.py`
- Create: `tests/knowledge/test_embeddings.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_embeddings.py`:
```python
import httpx
import numpy as np
import pytest

from app.knowledge.embeddings import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    RemoteEmbeddingProvider,
    get_embedding_provider,
)


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        return self._handler(self.calls, url, headers, json)

    def close(self):
        pass


def test_mock_provider_deterministic():
    p = MockEmbeddingProvider()
    a = p.embed(["内容安全平台过滤违规"])
    b = p.embed(["内容安全平台过滤违规"])
    c = p.embed(["咖啡烘焙风味分析"])
    assert a == b
    assert a != c
    assert len(a[0]) == p.dim


def test_mock_provider_normalized():
    p = MockEmbeddingProvider()
    v = np.array(p.embed(["用户反馈 投诉 处理"])[0])
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-6


def test_remote_provider_request():
    captured = {}

    def handler(n, url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return _FakeResp({"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    p = RemoteEmbeddingProvider(
        api_key="sk-test", base_url="https://emb.example.com/v1",
        model="emb-model", http_client=_FakeClient(handler))
    out = p.embed(["hello"])
    assert captured["url"] == "https://emb.example.com/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "emb-model"
    assert captured["body"]["input"] == ["hello"]
    assert out == [[0.1, 0.2, 0.3]]
    assert p.dim == 3


def test_remote_provider_parse_by_index():
    def handler(n, url, headers, body):
        # 逆序返回，验证按 index 对齐
        return _FakeResp({"data": [
            {"index": 1, "embedding": [9, 9]},
            {"index": 0, "embedding": [1, 1]},
        ]})

    p = RemoteEmbeddingProvider(
        api_key="k", base_url="https://x/v1", model="m",
        http_client=_FakeClient(handler))
    out = p.embed(["a", "b"])
    assert out == [[1, 1], [9, 9]]


def test_remote_provider_raises_on_error():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "boom"}, status=500)

    p = RemoteEmbeddingProvider(
        api_key="k", base_url="https://x/v1", model="m",
        http_client=_FakeClient(handler))
    with pytest.raises(Exception):
        p.embed(["x"])


def test_factory_mock_and_remote():
    assert isinstance(get_embedding_provider("mock"), MockEmbeddingProvider)
    rp = get_embedding_provider(
        "openai", api_key="k", base_url="https://x/v1", model="m")
    assert isinstance(rp, RemoteEmbeddingProvider)
    assert rp.name == "openai"


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_embedding_provider("nope")
```

- [ ] **Step 2: 运行确认 FAIL（模块尚不存在）**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_embeddings.py -v`
Expected: ERROR/FAIL `ModuleNotFoundError: app.knowledge.embeddings`.

- [ ] **Step 3: 实现 `app/knowledge/embeddings.py`**

```python
"""Embedding 抽象：将文本批量转为稠密向量。

默认 MockEmbeddingProvider（离线确定性，非真语义，仅供测试与零配置运行）；
RemoteEmbeddingProvider 走远程 OpenAI 兼容 /v1/embeddings（OpenAI / vLLM / 任意兼容服务）。
"""
from __future__ import annotations
import logging
from typing import List, Optional

import httpx
import numpy as np

from app.core.config import settings
from app.knowledge.tokenize import tokenize

logger = logging.getLogger(__name__)

MOCK_DIM = 256


class EmbeddingProvider:
    """抽象基类：embed(texts) -> List[List[float]]。"""

    name: str = "base"
    dim: int = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def batch_embed(self, texts: List[str]) -> List[List[float]]:
        return self.embed(texts)


class MockEmbeddingProvider(EmbeddingProvider):
    """确定性哈希向量：离线、无依赖、测试用。非真语义。"""

    name = "mock"
    dim = MOCK_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        out = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float64)
            for tok in tokenize(text or ""):
                vec[hash(tok) % self.dim] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            out.append(vec.tolist())
        return out


class RemoteEmbeddingProvider(EmbeddingProvider):
    """远程 OpenAI 兼容 /v1/embeddings（真语义）。失败即抛，由 VectorBackend 捕获降级。"""

    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str,
                 timeout: float = 30.0, http_client: Optional[httpx.Client] = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._http = http_client
        self.dim = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        body = {"model": self.model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            client = self._http or httpx.Client(timeout=self.timeout)
            try:
                resp = client.post(f"{self.base_url}/embeddings", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
            finally:
                if self._http is None:
                    client.close()
        except httpx.HTTPError as e:
            logger.warning("embedding 请求失败: %s", e)
            raise
        try:
            items = sorted(data["data"], key=lambda d: d["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("embedding 响应解析失败: %s", e)
            raise
        if vectors and self.dim == 0:
            self.dim = len(vectors[0])
        return vectors


def get_embedding_provider(provider: Optional[str] = None, **kwargs) -> EmbeddingProvider:
    name = (provider or settings.EMBEDDING_PROVIDER or "mock").lower()
    if name == "mock":
        return MockEmbeddingProvider()
    if name == "openai":
        return RemoteEmbeddingProvider(
            api_key=kwargs.get("api_key", settings.EMBEDDING_API_KEY),
            base_url=kwargs.get("base_url", settings.EMBEDDING_BASE_URL),
            model=kwargs.get("model", settings.EMBEDDING_MODEL),
            timeout=kwargs.get("timeout", 30.0),
            http_client=kwargs.get("http_client"),
        )
    raise ValueError(f"未知 EMBEDDING provider: {name}")
```

- [ ] **Step 4: 运行确认 PASS**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_embeddings.py -v`
Expected: PASS（7 passed）。

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/knowledge/embeddings.py tests/knowledge/test_embeddings.py
git commit -m "feat(knowledge): add EmbeddingProvider abstraction (mock + remote /v1/embeddings)"
```

---

### Task 3: schema 新增 `knowledge_vectors` 表

**Files:**
- Modify: `app/knowledge/schema.py` (`_SCHEMA` 列表新增一张表)

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_schema_vectors.py`:
```python
import tempfile

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema


def test_knowledge_vectors_table_exists():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    row = repo._execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_vectors'"
    ).fetchone()
    assert row is not None
    # 可写可读
    repo._execute(
        "INSERT INTO knowledge_vectors (chunk_id, model, dim, vector) VALUES (?,?,?,?)",
        ("c1", "mock", 3, b"\x00\x00\x00\x00"))
    repo._commit()
    cnt = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert cnt == 1
```

- [ ] **Step 2: 运行确认 FAIL**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_schema_vectors.py -v`
Expected: FAIL（表不存在 → `OperationalError: no such table: knowledge_vectors`）。

- [ ] **Step 3: 修改 `app/knowledge/schema.py`**

定位:
```python
    """CREATE TABLE IF NOT EXISTS tfidf_model (
        id INTEGER PRIMARY KEY CHECK (id=1), vocab_json TEXT, idf_json TEXT)""",
]
```
改为（在 `tfidf_model` 之后、`]` 之前追加一项）:
```python
    """CREATE TABLE IF NOT EXISTS tfidf_model (
        id INTEGER PRIMARY KEY CHECK (id=1), vocab_json TEXT, idf_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_vectors (
        chunk_id TEXT PRIMARY KEY, model TEXT, dim INTEGER, vector BLOB)""",
]
```

- [ ] **Step 4: 运行确认 PASS**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_schema_vectors.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/knowledge/schema.py tests/knowledge/test_schema_vectors.py
git commit -m "feat(knowledge): add knowledge_vectors table for dense vectors"
```

---

### Task 4: VectorBackend 实现

**Files:**
- Create: `app/knowledge/backends/vector.py`
- Create: `tests/knowledge/test_vector_backend.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_vector_backend.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.embeddings import MockEmbeddingProvider, EmbeddingProvider


def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo


def _insert(repo, recs):
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()


def test_vector_index_and_search_cosine():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    recs = [
        {"id": "a", "content": "内容安全平台 违规信息 过滤 审核", "doc_id": "d1"},
        {"id": "b", "content": "咖啡 烘焙 风味 产地", "doc_id": "d2"},
    ]
    _insert(repo, recs)
    vb.index(recs)
    res = vb.search("内容安全 违规 审核")
    assert res and res[0] == "a"


def test_vector_empty_query_returns_empty():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    assert vb.search("") == []
    assert vb.search("   ") == []


def test_vector_incremental_keeps_old():
    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=MockEmbeddingProvider())
    recs1 = [{"id": "a", "content": "内容安全 审核", "doc_id": "d1"}]
    _insert(repo, recs1)
    vb.index(recs1)
    recs2 = [{"id": "b", "content": "咖啡 烘焙", "doc_id": "d2"}]
    _insert(repo, recs2)
    vb.index(recs2)  # 仅处理新 chunk，不重建旧
    res = vb.search("内容安全")
    assert "a" in res


def test_vector_beats_keyword_on_paraphrase():
    # 远程不可用场景下的等价离线验证：用自定义 provider 制造「语义近义但字面无交集」。
    class ParaphraseProvider(EmbeddingProvider):
        name = "paraphrase"
        dim = 3

        def embed(self, texts):
            out = []
            for t in texts:
                if "用户反馈" in t or "投诉" in t or "处理" in t:
                    out.append([1.0, 0.0, 0.0])
                else:
                    out.append([0.0, 0.0, 1.0])
            return out

    repo = _tmp_repo()
    vb = VectorBackend(repo, provider=ParaphraseProvider())
    recs = [{"id": "a", "content": "用户反馈应对流程 与 售后 客服 安抚", "doc_id": "d1"}]
    _insert(repo, recs)
    vb.index(recs)
    # 改写 query 与原文字面无交集，但语义近 → 向量命中
    res = vb.search("客户投诉处理")
    assert res and res[0] == "a"
```

- [ ] **Step 2: 运行确认 FAIL**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_vector_backend.py -v`
Expected: FAIL（ModuleNotFoundError: app.knowledge.backends.vector）。

- [ ] **Step 3: 实现 `app/knowledge/backends/vector.py`**

```python
"""稠密向量后端：增量索引 chunk 向量，检索时按余弦排序返回 chunk_id。

与 KeywordBackend / TfidfBackend 同接口：index(chunk_records) / search(query)->List[str]。
远程 embedding 失败 → 抛出 → 本后端捕获降级为空（不把 mock 向量误标入库）。
"""
from __future__ import annotations
import logging
from typing import List, Optional

import numpy as np

from app.knowledge.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


class VectorBackend:
    def __init__(self, repo, provider: Optional[EmbeddingProvider] = None):
        self.repo = repo
        self._provider = provider

    def _get_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        try:
            provider = self._get_provider()
        except Exception as e:
            logger.warning("vector provider 加载失败: %s", e)
            return
        try:
            texts = [r.get("content", "") for r in chunk_records]
            vectors = provider.embed(texts)
        except Exception as e:
            # 远程失败：抛出由此处捕获，本次不写向量（向量后端为空），不影响其他后端
            logger.warning("vector embed 失败(整批跳过): %s", e)
            return
        rows = []
        for r, vec in zip(chunk_records, vectors):
            try:
                arr = np.asarray(vec, dtype=np.float32)
                rows.append((r["id"], provider.name, int(arr.shape[0]), arr.tobytes()))
            except Exception as e:
                logger.warning("vector 单条写入跳过 %s: %s", r.get("id"), e)
        if rows:
            try:
                self.repo._executemany(
                    "INSERT OR REPLACE INTO knowledge_vectors (chunk_id, model, dim, vector) "
                    "VALUES (?,?,?,?)", rows)
                self.repo._commit()
            except Exception as e:
                logger.warning("vector 写入失败: %s", e)

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        try:
            provider = self._get_provider()
            qv = np.asarray(provider.embed([query])[0], dtype=np.float64)
        except Exception as e:
            logger.warning("vector 检索失败(返回空): %s", e)
            return []
        rows = self.repo._execute(
            "SELECT chunk_id, vector FROM knowledge_vectors WHERE model=?",
            (provider.name,)).fetchall()
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

- [ ] **Step 4: 运行确认 PASS**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_vector_backend.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/knowledge/backends/vector.py tests/knowledge/test_vector_backend.py
git commit -m "feat(knowledge): add VectorBackend with incremental index and cosine search"
```

---

### Task 5: KnowledgeService 接入（注册 / ingest / retrieve / delete）

**Files:**
- Modify: `app/knowledge/service.py`
- Create: `tests/knowledge/test_vector_service.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_vector_service.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.embeddings import EmbeddingProvider


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_service_registers_vector_backend():
    svc = _tmp_service()
    assert "vector" in svc.backends
    assert isinstance(svc.backends["vector"], VectorBackend)


def test_retrieve_fuses_three_ways():
    # 用自定义 provider：让「改写 query」仅向量路命中，验证 vector 已并入 rrf_fuse。
    class ParaphraseProvider(EmbeddingProvider):
        name = "paraphrase"
        dim = 3

        def embed(self, texts):
            out = []
            for t in texts:
                if "用户反馈" in t or "投诉" in t or "处理" in t:
                    out.append([1.0, 0.0, 0.0])
                else:
                    out.append([0.0, 0.0, 1.0])
            return out

    svc = _tmp_service()
    svc.backends["vector"] = VectorBackend(svc.repo, provider=ParaphraseProvider())
    svc.ingest("用户反馈应对流程 与 售后 客服 安抚", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 产地", project_id="p1", title="B")
    res = svc.retrieve("客户投诉处理")  # 字面无交集，仅向量命中 A
    assert res and res[0]["doc_title"] == "A"


def test_remote_unavailable_retrieve_still_works():
    class FailingProvider(EmbeddingProvider):
        name = "failing"

        def embed(self, texts):
            raise RuntimeError("embedding down")

    svc = _tmp_service()
    svc.backends["vector"] = VectorBackend(svc.repo, provider=FailingProvider())
    svc.ingest("内容安全平台 过滤 违规 信息", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 分析", project_id="p1", title="B")
    # 向量后端整批失败 → 不写向量 → 检索退化为 keyword+tfidf，仍可用
    res = svc.retrieve("内容安全 违规")
    assert res and res[0]["doc_title"] == "A"


def test_delete_clears_vectors():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台 过滤 违规 信息", title="A")
    repo = svc.repo
    before = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert before > 0
    assert svc.delete_document(doc_id) is True
    after = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert after == 0


def test_empty_query_returns_empty():
    svc = _tmp_service()
    assert svc.retrieve("") == []
    assert svc.retrieve("   ") == []
```

- [ ] **Step 2: 运行确认 FAIL**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_vector_service.py -v`
Expected: FAIL（`test_service_registers_vector_backend` 断言 `"vector" in svc.backends` 为 False）。

- [ ] **Step 3: 修改 `app/knowledge/service.py`**

(a) 修改 import 块（精确锚点）:
```python
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.reranker import rrf_fuse
```
改为:
```python
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.backends.vector import VectorBackend
from app.knowledge.reranker import rrf_fuse
```

(b) 修改 `__init__` 的 `self.backends`（精确锚点）:
```python
        self.backends = {
            "keyword": KeywordBackend(self.repo),
            "tfidf": TfidfBackend(self.repo),
        }
```
改为:
```python
        self.backends = {
            "keyword": KeywordBackend(self.repo),
            "tfidf": TfidfBackend(self.repo),
            "vector": VectorBackend(self.repo),
        }
```

(c) 在 `ingest` 的 tfidf 容错块之后新增 vector 容错块（精确锚点）:
```python
        try:
            self.backends["tfidf"].index(chunk_records)
        except Exception as e:
            logger.warning("tfidf index failed: %s", e)
        return doc_id
```
改为:
```python
        try:
            self.backends["tfidf"].index(chunk_records)
        except Exception as e:
            logger.warning("tfidf index failed: %s", e)
        try:
            self.backends["vector"].index(chunk_records)
        except Exception as e:
            logger.warning("vector index failed: %s", e)
        return doc_id
```

(d) 修改 `retrieve` 的融合（精确锚点）:
```python
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids])
```
改为:
```python
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        vec_ids = self.backends["vector"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
```

(e) 修改 `delete_document` 的循环（精确锚点）:
```python
        for cid in chunk_ids:
            self.repo._execute("DELETE FROM knowledge_fts WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_tfidf WHERE chunk_id=?", (cid,))
```
改为:
```python
        for cid in chunk_ids:
            self.repo._execute("DELETE FROM knowledge_fts WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_tfidf WHERE chunk_id=?", (cid,))
            self.repo._execute("DELETE FROM knowledge_vectors WHERE chunk_id=?", (cid,))
```

- [ ] **Step 4: 运行确认 PASS**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_vector_service.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/knowledge/service.py tests/knowledge/test_vector_service.py
git commit -m "feat(knowledge): wire VectorBackend into service (register/ingest/retrieve/delete)"
```

---

### Task 6: 全量回归

**Files:** 无新文件，仅运行。

- [ ] **Step 1: 跑全量测试**

`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest -q`
Expected: 0 failed（既有 266 passed 不受影响；新增约 18 例全过；真实 LLM/embedding e2e 仍为 skip）。

- [ ] **Step 2: 若失败则定位修复（不新增提交，改完重跑）**

常见风险：
- `np.frombuffer` 维度不一致 → 代码已 `if cv.shape[0] != qv.shape[0]: continue` 跳过。
- 注入式 provider 在 `retrieve` 后 `search` 仍用同一实例 → 已通过 `svc.backends["vector"] = VectorBackend(..., provider=...)` 保证 index/search 同源。
- 既有 `tests/knowledge/test_service.py` 断言可能因三路融合改变排名 → 该文件用例均基于 keyword+tfidf 已能命中的查询，向量路只会加分，不破坏原有断言；若个别断言因融合顺序变化失败，优先确认是否误改了 `retrieve` 的 `top_k` 行为（本计划未改 `top_k`）。

- [ ] **Step 3: 确认无漂移被提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git status --short | grep -vE "bsc_cloud.db|llm_service.py|dashboard.html|orphan_fork"
```
Expected: 输出为空（无未提交的非漂移改动；全量回归不写文件）。

---

## 自审（Self-Review）核对

1. **Spec 覆盖**：
   - `EmbeddingProvider` / `MockEmbeddingProvider` / `RemoteEmbeddingProvider` / 工厂 → Task 2 ✅
   - `VectorBackend` 增量 index + 余弦 search → Task 4 ✅
   - `knowledge_vectors` 表 → Task 3 ✅
   - `KnowledgeService` 四处改动（注册/ingest/retrieve/delete）→ Task 5 ✅
   - `config.py` EMBEDDING_* → Task 1 ✅
   - 全量回归 → Task 6 ✅
   - 测试矩阵 12 例（spec §8）：mock 确定性/归一化(1-2)、remote 请求/解析/抛错(3-5)、vector 余弦(6)、改写命中(7)、增量(8)、三路融合(9)、远程不可用仍可用(10)、删除清向量(11)、空 query(12) → 全部覆盖 ✅
2. **占位符扫描**：无 TBD/TODO/"类似 Task N"/"加适当处理"；每步均含完整代码与期望输出 ✅
3. **类型一致性**：
   - `EmbeddingProvider.embed(texts: List[str]) -> List[List[float]]` 在 Task 2 定义，Task 4 `VectorBackend` 调用 `provider.embed([query])[0]` 与 `provider.embed(texts)` 一致 ✅
   - `vector.py` `search` 返回 `List[str]`、`index` 收 `List[dict]`（含 `id`/`content`），与 `KeywordBackend`/`TfidfBackend` 同接口 ✅
   - `provider.name` 用作 `knowledge_vectors.model` 写入与 `WHERE model=?` 过滤，index/search 同源一致 ✅
   - 注入式测试用 `VectorBackend(repo, provider=...)`（显式 provider），与生产默认 `provider=None` 懒加载并存，无冲突 ✅
4. **风险点已处理**：远程失败抛异常 → `VectorBackend.index`/`search` 捕获降级；`model` 维度不一致时 `search` 跳过；空 query 直接返回空 ✅
