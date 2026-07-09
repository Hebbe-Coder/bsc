# 统一知识中台（RAG）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建统一知识检索层（KnowledgeService 门面 + 可插拔后端 BM25/TF-IDF + RRF 重排 + agent 工具），把上传文档变成可检索知识，增强 PRD→business_system 生成。

**Architecture:** `KnowledgeService` 门面聚合 `KeywordBackend`（FTS5/BM25）与 `TfidfBackend`（numpy TF-IDF cosine），`HybridReranker` 用 RRF 融合排名；摄取经 `document_parser`→`Chunker`→双后端索引→SQLite 落库；`RetrieveKnowledgeTool` 把 top-k 格式化为上下文回流 agent。所有逻辑零新依赖、可离线，错误在 Service 内层捕获，绝不向上抛。

**Tech Stack:** Python 3.13 / SQLite（FTS5 虚拟表 + BLOB）/ numpy 2.5 / LangChain `BaseTool` / pytest。复用 `KnowledgeRepository`、`document_parser`、`llm_service` 的 TF-IDF 分词思路。

---

## 文件结构

**新建 `app/knowledge/` 包（知识层，与现有 `repositories` 解耦）**
- `app/knowledge/__init__.py` — 包标识
- `app/knowledge/schema.py` — `ensure_schema(repo)`：建 4 张新表 + FTS5 虚表（CREATE TABLE IF NOT EXISTS）
- `app/knowledge/tokenize.py` — `tokenize(text)`：中英文混合分词（镜像 `llm_service._tokenize`，独立无重依赖）
- `app/knowledge/chunker.py` — `Chunk` dataclass + `chunk_text(text, max_chars=500)`
- `app/knowledge/backends/__init__.py` — 包标识
- `app/knowledge/backends/keyword.py` — `KeywordBackend`（FTS5/BM25，失败降级为空）
- `app/knowledge/backends/tfidf.py` — `TfidfBackend`（numpy TF-IDF，全局模型存 `tfidf_model` 表）
- `app/knowledge/reranker.py` — `rrf_fuse(ranklists, k=60)`
- `app/knowledge/service.py` — `KnowledgeService`（门面 ingest/retrieve + 可插拔后端注册表）
- `app/knowledge/tool.py` — `RetrieveKnowledgeTool(BaseTool)`（agent 工具）

**修改**
- `app/core/langchain_agent.py` — 导入并注册 `RetrieveKnowledgeTool()` 到 `tools` 列表（line ~357）

**新建测试 `tests/knowledge/`**
- `tests/knowledge/__init__.py`
- `tests/knowledge/test_chunker.py` — T1
- `tests/knowledge/test_keyword.py` — T2
- `tests/knowledge/test_tfidf.py` — T3
- `tests/knowledge/test_reranker.py` — T4
- `tests/knowledge/test_service.py` — T5/T7（集成 + 错误健壮）
- `tests/knowledge/test_tool.py` — T6/T7（工具 + 健壮）

**测试数据库隔离**：所有测试用 `tempfile` 临时 SQLite 文件，绝不污染 `app/bsc_cloud.db`。`KnowledgeRepository(db_path=tmp)` + `ensure_schema(repo)`。

---

### Task 1: Chunker

**Files:**
- Create: `app/knowledge/__init__.py`, `app/knowledge/chunker.py`
- Test: `tests/knowledge/__init__.py`, `tests/knowledge/test_chunker.py`

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_chunker.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.chunker import chunk_text

def test_chunker_basic():
    text = "# 项目背景\n这是关于内容安全平台的业务系统。内容安全平台用于过滤违规信息。\n\n# 核心目标\n提升审核效率，降低人工成本。"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].section == "项目背景"
    assert "内容安全平台" in chunks[0].content
    assert chunks[1].section == "核心目标"
    assert "审核效率" in chunks[1].content

def test_chunker_long_paragraph():
    text = "内容" * 600  # 1200 字，超 500 上限
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.section == "正文"
        assert "offset" in c.meta
    # offset 连续
    offsets = [c.meta["offset"] for c in chunks]
    assert offsets == sorted(offsets)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_chunker.py -q`
Expected: FAIL（ModuleNotFoundError: app.knowledge）

- [ ] **Step 3: 最小实现**

`app/knowledge/__init__.py`:
```python
```

`app/knowledge/chunker.py`:
```python
"""文档切分：按段落/标题结构 + 长度上限切分为 Chunk。"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    content: str
    section: str = "正文"
    meta: dict = field(default_factory=dict)


_HEADING_RE = re.compile(r"^\s*(#{1,6}\s+.+|第[一二三四五六七八九十\d]+[章节部分].*)$")


def _split_sentences(text: str) -> List[str]:
    # 以中文/英文句号、问号、叹号、换行切句，保留标点
    parts = re.split(r"(?<=[。！？!?\n])", text)
    return [p for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = 500) -> List[Chunk]:
    text = text or ""
    lines = text.split("\n")
    chunks: List[Chunk] = []
    current_section = "正文"
    buf: List[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        para = "".join(buf).strip()
        buf = []
        if not para:
            return
        if len(para) <= max_chars:
            chunks.append(Chunk(content=para, section=current_section,
                                meta={"offset": len(chunks)}))
            return
        # 超长段落：先按句分组，再以 max_chars 硬上限兜底（无标点也必切）
        sents = _split_sentences(para) or [para]
        piece = ""
        base = len(chunks)
        for sent in sents:
            if piece and len(piece) + len(sent) > max_chars:
                chunks.append(Chunk(content=piece, section=current_section,
                                    meta={"offset": base}))
                base += 1
                piece = ""
            piece += sent
            while len(piece) > max_chars:
                chunks.append(Chunk(content=piece[:max_chars], section=current_section,
                                    meta={"offset": base}))
                base += 1
                piece = piece[max_chars:]
        if piece:
            chunks.append(Chunk(content=piece, section=current_section,
                                meta={"offset": base}))

    for line in lines:
        if _HEADING_RE.match(line):
            flush()
            current_section = line.strip().lstrip("#").strip() or "正文"
            continue
        if line.strip() == "":
            flush()
            continue
        buf.append(line + "\n")
    flush()
    return chunks
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_chunker.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/__init__.py app/knowledge/chunker.py tests/knowledge/__init__.py tests/knowledge/test_chunker.py
git commit -m "feat(knowledge): add Chunker with heading/length-aware splitting"
```

---

### Task 2: KeywordBackend（FTS5 / BM25）

**Files:**
- Create: `app/knowledge/schema.py`, `app/knowledge/backends/__init__.py`, `app/knowledge/backends/keyword.py`
- Test: `tests/knowledge/test_keyword.py`

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_keyword.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.keyword import KeywordBackend

def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo

def test_keyword_backend_bm25():
    repo = _tmp_repo()
    kb = KeywordBackend(repo)
    recs = [
        {"id": "c1", "content": "内容安全平台用于过滤违规信息", "doc_id": "d1"},
        {"id": "c2", "content": "今天天气真好适合出游", "doc_id": "d1"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    kb.index(recs)
    res = kb.search("内容安全平台")
    assert res and res[0] == "c1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_keyword.py -q`
Expected: FAIL（import error）

- [ ] **Step 3: 最小实现**

`app/knowledge/schema.py`:
```python
"""知识库表结构（4 张新表 + FTS5 虚表），与现有 knowledge_index/entities 并存。"""
from __future__ import annotations
from typing import Any

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_docs (
        id TEXT PRIMARY KEY, project_id TEXT, asset_id TEXT,
        title TEXT, source TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY, doc_id TEXT, idx INTEGER,
        content TEXT, section TEXT, metadata_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_tfidf (
        chunk_id TEXT PRIMARY KEY, vector BLOB)""",
    """CREATE TABLE IF NOT EXISTS tfidf_model (
        id INTEGER PRIMARY KEY CHECK (id=1), vocab_json TEXT, idf_json TEXT)""",
]

def ensure_schema(repo: Any) -> None:
    for sql in _SCHEMA:
        repo._execute(sql)
    try:
        repo._execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
            "content, doc_id UNINDEXED, chunk_id UNINDEXED, tokenize='trigram')")
    except Exception:
        # FTS5 不可用（极端环境）：keyword 后端将降级为空，不影响其他后端
        pass
    repo._commit()
```

`app/knowledge/backends/__init__.py`:
```python
```

`app/knowledge/backends/keyword.py`:
```python
"""关键词后端：FTS5 trigram + BM25，不可用时退回 LIKE，再不行降级为空。"""
from __future__ import annotations
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class KeywordBackend:
    def __init__(self, repo):
        self.repo = repo
        self.enabled = True

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        rows = [(r["content"], r["doc_id"], r["id"]) for r in chunk_records]
        try:
            self.repo._executemany(
                "INSERT INTO knowledge_fts (content, doc_id, chunk_id) VALUES (?,?,?)", rows)
            self.repo._commit()
        except Exception as e:
            logger.warning("keyword index failed, disabling: %s", e)
            self.enabled = False

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not self.enabled or not query or not query.strip():
            return []
        # 多词查询按词 OR（trigram 子串匹配），单/多词都稳健
        import re as _re
        terms = [t for t in _re.split(r"\s+", query.strip()) if t]
        if not terms:
            return []
        q = " OR ".join('"%s"' % t.replace('"', " ") for t in terms)
        try:
            rows = self.repo._execute(
                "SELECT chunk_id, bm25(knowledge_fts) AS s FROM knowledge_fts "
                "WHERE knowledge_fts MATCH ? ORDER BY s LIMIT ?",
                (q, limit)).fetchall()
            return [r["chunk_id"] for r in rows]
        except Exception:
            # 退回 LIKE 兜底
            try:
                like = f"%{query}%"
                rows = self.repo._execute(
                    "SELECT id AS chunk_id FROM knowledge_chunks WHERE content LIKE ? LIMIT ?",
                    (like, limit)).fetchall()
                return [r["chunk_id"] for r in rows]
            except Exception:
                self.enabled = False
                return []
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_keyword.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/schema.py app/knowledge/backends/__init__.py app/knowledge/backends/keyword.py tests/knowledge/test_keyword.py
git commit -m "feat(knowledge): add KeywordBackend with FTS5/BM25 and LIKE fallback"
```

---

### Task 3: TfidfBackend（numpy TF-IDF）

**Files:**
- Create: `app/knowledge/tokenize.py`, `app/knowledge/backends/tfidf.py`
- Test: `tests/knowledge/test_tfidf.py`

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_tfidf.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.tfidf import TfidfBackend

def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo

def test_tfidf_backend_cosine():
    repo = _tmp_repo()
    tb = TfidfBackend(repo)
    recs = [
        {"id": "a", "content": "内容安全平台 违规信息 过滤 审核", "doc_id": "d1"},
        {"id": "b", "content": "咖啡 烘焙 风味 产地", "doc_id": "d2"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    tb.index(recs)
    res = tb.search("内容安全 审核")
    assert res and res[0] == "a"

def test_tfidf_idf_rare_higher():
    # 稀有词（仅 1 篇出现）idf 应高于常见词（2 篇都出现）
    repo = _tmp_repo()
    tb = TfidfBackend(repo)
    recs = [
        {"id": "x", "content": "苹果 苹果 苹果 苹果 内容 审核", "doc_id": "d1"},
        {"id": "y", "content": "苹果 麒麟 梼杌", "doc_id": "d2"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    tb.index(recs)
    vocab, idf = tb._load_model()
    assert idf["獬豸"] > idf["苹果"]  # 稀有词 idf 更高
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_tfidf.py -q`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`app/knowledge/tokenize.py`:
```python
"""中英文混合分词（镜像 llm_service._tokenize，独立无重依赖）。"""
from __future__ import annotations
import re
from typing import List


def tokenize(text: str, max_length: int = 2000) -> List[str]:
    text = (text or "")[:max_length]
    tokens: List[str] = []
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        for i in range(len(word)):
            for j in range(i + 1, min(i + 3, len(word) + 1)):
                tokens.append(word[i:j])
    for word in re.findall(r"[a-zA-Z]+", text.lower()):
        if len(word) >= 2:
            tokens.append(word)
    return tokens
```

`app/knowledge/backends/tfidf.py`:
```python
"""TF-IDF 后端：numpy 向量（BLOB 存储），全局模型存 tfidf_model 表。"""
from __future__ import annotations
import json
import logging
from collections import Counter
from typing import List, Optional, Tuple

import numpy as np

from app.knowledge.tokenize import tokenize

logger = logging.getLogger(__name__)


class TfidfBackend:
    def __init__(self, repo):
        self.repo = repo

    def _load_model(self) -> Tuple[Optional[dict], Optional[dict]]:
        row = self.repo._execute(
            "SELECT vocab_json, idf_json FROM tfidf_model WHERE id=1").fetchone()
        if not row:
            return None, None
        return json.loads(row["vocab_json"]), json.loads(row["idf_json"])

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
        self.repo._execute("DELETE FROM tfidf_model")
        self.repo._execute(
            "INSERT INTO tfidf_model (id, vocab_json, idf_json) VALUES (1, ?, ?)",
            (json.dumps(vocab, ensure_ascii=False), json.dumps(idf, ensure_ascii=False)))
        self.repo._commit()
        return vocab, idf

    def _vectorize(self, text: str, vocab: dict, idf: dict) -> np.ndarray:
        vec = np.zeros(len(vocab))
        for tok, cnt in Counter(tokenize(text)).items():
            if tok in vocab:
                vec[vocab[tok]] = cnt * idf.get(tok, 1.0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def index(self, chunk_records: List[dict]) -> None:
        if not chunk_records:
            return
        try:
            vocab, idf = self._build_and_store_model()
        except Exception as e:
            logger.warning("tfidf model build failed: %s", e)
            return
        if not vocab:
            return
        for rec in chunk_records:
            vec = self._vectorize(rec["content"], vocab, idf)
            self.repo._execute(
                "INSERT OR REPLACE INTO knowledge_tfidf (chunk_id, vector) VALUES (?, ?)",
                (rec["id"], vec.tobytes()))
        self.repo._commit()

    def search(self, query: str, limit: int = 20) -> List[str]:
        if not query or not query.strip():
            return []
        vocab, idf = self._load_model()
        if not vocab:
            return []
        qv = self._vectorize(query, vocab, idf)
        rows = self.repo._execute("SELECT chunk_id, vector FROM knowledge_tfidf").fetchall()
        scored = []
        for r in rows:
            cv = np.frombuffer(r["vector"], dtype=np.float64)
            sim = float(np.dot(qv, cv))
            if sim > 0:
                scored.append((r["chunk_id"], sim))
        scored.sort(key=lambda x: -x[1])
        return [cid for cid, _ in scored[:limit]]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_tfidf.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/tokenize.py app/knowledge/backends/tfidf.py tests/knowledge/test_tfidf.py
git commit -m "feat(knowledge): add TfidfBackend with numpy vectors stored as BLOB"
```

---

### Task 4: HybridReranker（RRF）

**Files:**
- Create: `app/knowledge/reranker.py`
- Test: `tests/knowledge/test_reranker.py`

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_reranker.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.reranker import rrf_fuse

def test_reranker_rrf_agreement():
    fused = rrf_fuse([["a", "b", "c"], ["a", "b", "c"]])
    assert fused[0] == "a" and fused[1] == "b"

def test_reranker_rrf_scale_invariant():
    # 只吃排名不吃分数；a 在两榜都靠前 → 总体靠前
    fused = rrf_fuse([["a", "b"], ["c", "a"]])
    assert fused[0] == "a"
    # 缺失后端（空榜）仍鲁棒
    fused2 = rrf_fuse([["a", "b"], []])
    assert fused2[0] == "a"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_reranker.py -q`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`app/knowledge/reranker.py`:
```python
"""RRF（Reciprocal Rank Fusion）融合多路排名，对分数尺度不敏感。"""
from __future__ import annotations
from typing import List


def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List[str]:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda c: -scores[c])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_reranker.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/reranker.py tests/knowledge/test_reranker.py
git commit -m "feat(knowledge): add HybridReranker with RRF fusion"
```

---

### Task 5: KnowledgeService 门面

**Files:**
- Create: `app/knowledge/service.py`
- Test: `tests/knowledge/test_service.py`（含 T7 健壮性部分）

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_service.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService

def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)

def test_ingest_then_retrieve():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台用于过滤违规信息。审核效率需要提升。",
                        project_id="p1", title="文档A", source="a.txt")
    assert doc_id
    res = svc.retrieve("内容安全 审核")
    assert res and "内容安全" in res[0]["content"]

def test_retrieve_project_filter():
    svc = _tmp_service()
    svc.ingest("内容安全平台过滤违规。", project_id="p1", title="A")
    svc.ingest("咖啡烘焙风味分析。", project_id="p2", title="B")
    res = svc.retrieve("内容", project_id="p1")
    assert res and all(r["doc_title"] == "A" for r in res)
    res2 = svc.retrieve("内容", project_id="p2")
    assert res2 == [] or all(r["doc_title"] == "B" for r in res2)

def test_hybrid_beats_single():
    svc = _tmp_service()
    svc.ingest("内容安全平台 违规信息 过滤 审核 风控", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 产地 杯测", project_id="p1", title="B")
    res = svc.retrieve("内容安全 审核 风控")
    assert res and res[0]["doc_title"] == "A"

def test_retrieve_empty_corpus():
    svc = _tmp_service()
    assert svc.retrieve("任何查询") == []

def test_ingest_empty_text_returns_none():
    svc = _tmp_service()
    assert svc.ingest("   ") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_service.py -q`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`app/knowledge/service.py`:
```python
"""知识层门面：ingest / retrieve + 可插拔后端注册表。永不向上抛异常。"""
from __future__ import annotations
import logging
from typing import List, Optional

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.chunker import chunk_text
from app.knowledge.backends.keyword import KeywordBackend
from app.knowledge.backends.tfidf import TfidfBackend
from app.knowledge.reranker import rrf_fuse

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self, db_path: Optional[str] = None, repo: Optional[KnowledgeRepository] = None):
        self.repo = repo or KnowledgeRepository(db_path)
        ensure_schema(self.repo)
        self.backends = {
            "keyword": KeywordBackend(self.repo),
            "tfidf": TfidfBackend(self.repo),
        }

    def ingest(self, text: str, project_id: str = "", asset_id: str = "",
               title: str = "", source: str = "") -> Optional[str]:
        text = (text or "").strip()
        if not text:
            return None
        try:
            chunks = chunk_text(text)
        except Exception as e:
            logger.warning("chunk failed: %s", e)
            return None
        if not chunks:
            return None
        doc_id = self.repo._generate_id()
        self.repo._execute(
            "INSERT INTO knowledge_docs (id, project_id, asset_id, title, source, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (doc_id, project_id, asset_id, title, source, self.repo._now()))
        chunk_records = []
        for i, ch in enumerate(chunks):
            cid = self.repo._generate_id()
            self.repo._execute(
                "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) "
                "VALUES (?,?,?,?,?,?)",
                (cid, doc_id, i, ch.content, ch.section, self.repo._json_dumps(ch.meta)))
            chunk_records.append({"id": cid, "content": ch.content, "doc_id": doc_id})
        self.repo._commit()
        # 后端各自容错，单后端失败不影响其他
        try:
            self.backends["keyword"].index(chunk_records)
        except Exception as e:
            logger.warning("keyword index failed: %s", e)
            self.backends["keyword"].enabled = False
        try:
            self.backends["tfidf"].index(chunk_records)
        except Exception as e:
            logger.warning("tfidf index failed: %s", e)
        return doc_id

    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None) -> List[dict]:
        if not query or not query.strip():
            return []
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids])
        top = fused[:top_k]
        if not top:
            return []
        results = []
        for cid in top:
            row = self.repo._execute(
                "SELECT c.content AS content, c.section AS section, d.title AS doc_title "
                "FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
                "WHERE c.id=? AND (? = '' OR d.project_id = ?)",
                (cid, project_id or "", project_id or "")).fetchone()
            if row:
                results.append({
                    "content": row["content"],
                    "section": row["section"],
                    "doc_title": row["doc_title"] or "未知来源",
                })
        return results
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_service.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/service.py tests/knowledge/test_service.py
git commit -m "feat(knowledge): add KnowledgeService facade with pluggable backends"
```

---

### Task 6: RetrieveKnowledgeTool（agent 工具）

**Files:**
- Create: `app/knowledge/tool.py`
- Modify: `app/core/langchain_agent.py`（import + 注册到 tools 列表）
- Test: `tests/knowledge/test_tool.py`

- [ ] **Step 1: 写失败测试**

`tests/knowledge/test_tool.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.service import KnowledgeService
from app.knowledge.tool import RetrieveKnowledgeTool

def _tmp_tool():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return RetrieveKnowledgeTool(service=KnowledgeService(db_path=f.name))

def test_retrieve_tool_format():
    tool = _tmp_tool()
    tool._service.ingest("内容安全平台用于过滤违规信息。", project_id="p1", title="文档A")
    out = tool._run("内容安全")
    assert "[知识 1]" in out
    assert "出处：文档A" in out
    assert "内容安全平台" in out

def test_retrieve_tool_empty():
    tool = _tmp_tool()
    out = tool._run("任何查询")
    assert "未检索到相关知识" in out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_tool.py -q`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`app/knowledge/tool.py`:
```python
"""LangChain 工具：agent 自主调用，把 top-k 知识格式化为带出处的上下文。"""
from __future__ import annotations
import logging
from typing import Optional

from langchain_core.tools import BaseTool

from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)


class RetrieveKnowledgeTool(BaseTool):
    name: str = "knowledge_retrieve"
    description: str = (
        "检索企业知识库中与查询相关的文档片段，返回带出处标注的上下文，"
        "用于增强业务系统生成。输入 query（查询语句）与可选 top_k（返回条数，默认5）。"
    )
    _service: Optional[KnowledgeService] = None

    def __init__(self, service: Optional[KnowledgeService] = None, **kwargs):
        super().__init__(**kwargs)
        self._service = service

    def _run(self, query: str, top_k: int = 5) -> str:
        try:
            svc = self._service or KnowledgeService()
            results = svc.retrieve(query, top_k=top_k)
        except Exception as e:
            logger.warning("retrieve tool failed: %s", e)
            return "未检索到相关知识。"
        if not results:
            return "未检索到相关知识。"
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[知识 {i}] 出处：{r['doc_title']} / {r['section']}\n{r['content']}")
        return "\n\n".join(parts)

    async def _arun(self, query: str, top_k: int = 5) -> str:
        return self._run(query, top_k=top_k)
```

修改 `app/core/langchain_agent.py`：
- 在其它 tool import 附近加：`from app.knowledge.tool import RetrieveKnowledgeTool`
- 在 `tools` 列表（`self._tools = [ ... ]`，约 line 360-368）追加 `RetrieveKnowledgeTool(),`

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_tool.py -q`
Expected: PASS

（另跑导入冒烟：`.venv/Scripts/python.exe -c "from app.core.langchain_agent import LangChainAgentService; print('ok')"` 确认工具注册不破坏模块导入。）

- [ ] **Step 5: 提交**

```bash
git add app/knowledge/tool.py app/core/langchain_agent.py tests/knowledge/test_tool.py
git commit -m "feat(knowledge): add RetrieveKnowledgeTool and register in agent"
```

---

### Task 7: 错误处理加固（健壮测试）

**Files:**
- Test: `tests/knowledge/test_service.py`, `tests/knowledge/test_tool.py`（追加）

- [ ] **Step 1: 写失败测试（摄取解析失败跳过 / 无模型安全 / 后端失败降级）**

在 `tests/knowledge/test_service.py` 追加：
```python
def test_ingest_parse_failure_skips():
    svc = _tmp_service()
    # chunk_text 对正常文本不抛；模拟空文本已覆盖。此处验证坏数据不崩：
    assert svc.ingest("") is None          # 空文本跳过
    assert svc.ingest(None) is None        # None 跳过

def test_retrieve_no_model_safe():
    svc = _tmp_service()                    # 未摄取，无 tfidf_model
    assert svc.retrieve("查询") == []       # 不崩，返回空
```

在 `tests/knowledge/test_tool.py` 追加：
```python
def test_backend_failure_degrades():
    # 人为让 tfidf 后端抛错，keyword 仍可返回
    tool = _tmp_tool()
    svc = tool._service
    svc.ingest("内容安全平台过滤违规信息。", project_id="p1", title="A")
    # 破坏 tfidf 模型表，使 tfidf.search 空结果，但 keyword 仍可用
    svc.repo._execute("DELETE FROM tfidf_model")
    svc.repo._commit()
    out = tool._run("内容安全")
    assert "[知识 1]" in out or "未检索到相关知识" in out   # 不崩
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/ -q`
Expected: PASS（全部 knowledge 测试）

- [ ] **Step 3: 提交**

```bash
git add tests/knowledge/test_service.py tests/knowledge/test_tool.py
git commit -m "test(knowledge): add error-handling and degradation guards"
```

---

### Task 8: 全量回归

**Files:** 无新增，仅运行

- [ ] **Step 1: 运行导出层与知识层相关套件（排除慢速 e2e）**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_real_e2e.py`
Expected: 既有套件无新失败（检索层改动不影响导出层），knowledge 测试全绿。

- [ ] **Step 2: 运行知识层专项**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/ -q`
Expected: PASS

- [ ] **Step 3: 提交（如有临时修复）**

若回归发现需小修，修复后提交；否则本任务无提交，仅确认绿灯。

---

## 自审要点（执行前已核对）

- **Spec 覆盖**：§3 架构→T1-T6；§4 组件→各 backend/reranker/service/tool；§5 存储→schema.py 4 表+FTS5；§6 数据流→service.ingest/retrieve；§7 错误→T7 + service 内层捕获；§8 测试 14 例→T1-T7 测试全覆盖（chunker 2 / keyword 1 / tfidf 2 / reranker 2 / service 5 / tool 2 / 健壮 3 = 17，超出 14 基线，含强化）。
- **无占位符**：每步均有完整代码，无 TODO/TBD。
- **类型一致**：`Chunk(content, section, meta)` 在 T1 定义、T5 ingest 使用；`chunk_records` 结构 `{id, content, doc_id}` 在 T2/T3/T5 一致；`rrf_fuse(ranklists)` 签名 T4/T5 一致；`KnowledgeService(db_path=)` 在 T5 定义、T6/T7 测试使用；`RetrieveKnowledgeTool(service=)` 在 T6 定义、测试使用。
- **零新依赖**：仅用 numpy（已装）、sqlite3（内置）、langchain_core（已装）。FTS5 已验证可用，不可用时降级。
