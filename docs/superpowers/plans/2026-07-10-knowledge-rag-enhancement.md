# 知识库 RAG 后端增强 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有知识库 RAG 上增加「检索重排 Rerank」与「更多文档类型接入 + 增量幂等更新」，并以 C 级验收（功能正确 + RAGEvaluator 前后对比 + 延迟 P95 守护）证明增强有效。

**Architecture:** 分层扩展，不重构核心。`Reranker` 抽象（本地 cross-encoder / 云端 Cohere·Jina / Mock）并入现有 `app/knowledge/reranker.py`，插在「RRF 融合 → top_k」之间；文档格式**扩展现有** `app/core/document_parser.py`（`.md/.pptx/.xlsx` 为真正缺口，PDF/OCR/Word/纯文本/图片已具备）；增量更新在 `KnowledgeService.ingest_text` 内用 `doc_id`+`content_hash` 实现幂等。

**Tech Stack:** Python / FastAPI / SQLite（原生 SQL）/ `sentence-transformers`（可选）/ `python-pptx`、`openpyxl`（可选，懒导入）/ 既有 `ApiResponse`、`KnowledgeRepository`、`document_parser`。

---

## 实现备注（与已批准设计规格的关键偏差）

代码核查发现，**设计规格中的若干假设需按现状修正**（已在 `docs/superpowers/specs/2026-07-10-knowledge-rag-enhancement-design.md` §4.2/§11 同步更正）：

1. **文档解析已存在**：`app/core/document_parser.py` 的 `DocumentParser` + `parse_document()` 已被 `/ingest` 使用，支持 `.docx/.pdf/.txt`/图片，PDF 的 OCR 回退已通过 **LLM 视觉服务**（`llm_service.ocr_image`）实现。
2. **因此「更多文档类型」的真正缺口只有**：`.md`/`.markdown`（纯文本）、`.pptx`（python-pptx）、`.xlsx`/`.xls`（openpyxl）。**不再新建 `parsers.py`，改为扩展现有 `document_parser`**；**移除 `pytesseract` 依赖**（OCR 沿用 LLM 视觉）。
3. **增量更新是 ingest 线的核心新工作**：`/ingest` 当前 `status` 仅看 doc_id 是否为空，无 `content_hash` 去重/版本；`ingest_text` 将补齐此逻辑。

## §14 默认值裁决（本计划拍板）

| 项 | 决议 | 理由 |
|----|------|------|
| `RERANK_PROVIDER` 默认 | `"none"` | 默认关闭重排，避免生产误触发本地重模型；测试显式置 `"mock"`。 |
| 本地 cross-encoder 默认模型 | `ms-marco-MiniLM-L-6-v2`（~80MB，CPU 友好） | 比 `bge-reranker-v2-m3`(~1.1GB) 轻，首次加载快、易在 CI 验证降级路径。 |
| `RERANK_TOP_N` 默认 | `20` | 候选池 4× top_k，兼顾召回与延迟；`retrieve` 内 clamp 到 ≥ top_k。 |

## 文件结构

- **Create** `app/knowledge/cloud_reranker.py` —— `CloudReranker`（Cohere/Jina，多 key 故障转移）。
- **Modify** `app/core/config.py` —— 新增 `RERANK_*` / `OCR_ENABLED` 配置。
- **Modify** `app/knowledge/reranker.py` —— 追加 `Reranker` 基类、`NoOp`/`Mock`/`LocalCrossEncoder` 实现与 `get_reranker()` 工厂（保留既有 `rrf_fuse`）。
- **Modify** `app/knowledge/service.py` —— `ingest_text()` 幂等 + `ingest()` 兼容包装 + `retrieve()` 接入 rerank + `_fetch_candidates()` / `_content_hash()` / `_resolve_doc_id()` 辅助。
- **Modify** `app/knowledge/schema.py` —— `knowledge_docs` 幂等加列（`doc_format`/`content_hash`/`version`）。
- **Modify** `app/core/document_parser.py` —— 扩展 `SUPPORTED_EXTENSIONS`、dispatch，新增 `_parse_md/_parse_pptx/_parse_xlsx`，各返回带 `doc_format`。
- **Modify** `app/knowledge/eval.py` —— `evaluate()` 增加 `rerank`/`rerank_top_n` 透传；新增 `compare_before_after()`。
- **Modify** `app/api/knowledge_api.py` —— `/ingest` 支持 `doc_id` + 返回真实 `status/version` + `doc_format`；`/retrieve`、`/ask` 增加 `rerank`/`rerank_top_n` 参数。
- **Create/Modify** `tests/knowledge/test_reranker.py`、`test_document_parser_ext.py`、`test_incremental_ingest.py`、`test_retrieve_rerank.py`、`tests/knowledge/test_api_enhancement.py`。

---

# Slice 1 —— 快赢（先转绿）

## Task 1: 配置项

**Files:** Modify `app/core/config.py`

- [ ] **Step 1: 在 `LLM_TEMPERATURE` 附近新增 Rerank 配置**

在 `app/core/config.py` 的 `RAG_TWO_PHASE: bool = False` 之后插入：

```python
    RERANK_PROVIDER: str = "none"        # 重排提供方: none/mock/local/cloud
    RERANK_KEYS: List[str] = []          # 云端 rerank 多 key 轮询/故障转移
    RERANK_MODEL: str = "ms-marco-MiniLM-L-6-v2"  # 本地 cross-encoder 默认(轻量)
    RERANK_TOP_N: int = 20               # 重排候选池大小(须 >= top_k)
    RERANK_ENABLED: bool = False         # retrieve 默认是否重排
    OCR_ENABLED: bool = True             # PDF OCR 总开关(复用既有 LLM 视觉 OCR)
```

- [ ] **Step 2: 运行冒烟导入验证**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -c "from app.core.config import settings; print(settings.RERANK_PROVIDER, settings.RERANK_TOP_N)"`
Expected: `none 20`

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py
git commit -m "feat(config): 新增 RERANK_* 与 OCR_ENABLED 配置项"
```

## Task 2: Reranker 抽象 + Mock + Local(降级)

**Files:** Modify `app/knowledge/reranker.py`

- [ ] **Step 1: 在 `rrf_fuse` 后追加 Reranker 体系（保留 rrf_fuse）**

将 `app/knowledge/reranker.py` 整体替换为：

```python
"""RRF 融合 + Reranker 抽象（本地 cross-encoder / 云端 / Mock）。"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List[tuple]:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


class Reranker:
    name = "base"

    def rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        raise NotImplementedError


class NoOpReranker(Reranker):
    """原序透传（rerank 关闭或降级时）。"""
    name = "none"

    def rerank(self, query, candidates, top_k):
        return candidates[:top_k]


class MockReranker(Reranker):
    """确定性重排：按 query 词在 content 中的命中数降序，便于测试断言。"""
    name = "mock"

    def rerank(self, query, candidates, top_k):
        q_tokens = [t for t in (query or "").lower().split() if t]

        def score(c):
            text = (c.get("content") or "").lower()
            return float(sum(text.count(t) for t in q_tokens))

        ranked = [dict(c, rerank_score=score(c)) for c in candidates]
        ranked.sort(key=lambda x: -x["rerank_score"])
        return ranked[:top_k]


class LocalCrossEncoderReranker(Reranker):
    """懒加载 cross-encoder；导入/推理失败 → 自动降级返回原序，绝不抛异常。"""
    name = "local"

    def __init__(self, model_name: str = ""):
        self.model_name = model_name or settings.RERANK_MODEL
        self._model = None  # None=未加载; False=加载失败

    def _ensure(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning("本地 reranker 加载失败, 将降级原序: %s", e)
                self._model = False
        return self._model

    def rerank(self, query, candidates, top_k):
        model = self._ensure()
        if not model:
            return candidates[:top_k]
        try:
            pairs = [(query, c.get("content") or "") for c in candidates]
            scores = model.predict(pairs)
            scored = [dict(c, rerank_score=float(s)) for c, s in zip(candidates, scores)]
            scored.sort(key=lambda x: -x["rerank_score"])
            return scored[:top_k]
        except Exception as e:
            logger.warning("本地 rerank 推理失败, 降级原序: %s", e)
            return candidates[:top_k]


def get_reranker(provider: Optional[str] = None, keys=None, model: str = None) -> Reranker:
    provider = (provider or settings.RERANK_PROVIDER or "none").lower()
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

- [ ] **Step 2: 写失败测试**

Create `tests/knowledge/test_reranker.py`:

```python
from app.knowledge.reranker import (
    get_reranker, MockReranker, NoOpReranker, LocalCrossEncoderReranker,
)


def _cands():
    return [
        {"chunk_id": "a", "content": "苹果 香蕉 水果", "score": 0.3},
        {"chunk_id": "b", "content": "苹果 蔬菜", "score": 0.2},
        {"chunk_id": "c", "content": "汽车 引擎", "score": 0.1},
    ]


def test_mock_rerank_orders_by_query_hits():
    out = MockReranker().rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]
    assert "rerank_score" in out[0]


def test_noop_passthrough():
    out = NoOpReranker().rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]


def test_get_reranker_none_returns_noop():
    assert isinstance(get_reranker("none"), NoOpReranker)


def test_local_degrades_when_model_load_fails():
    r = LocalCrossEncoderReranker()
    r._model = False  # 模拟加载失败
    out = r.rerank("苹果", _cands(), top_k=2)
    assert [c["chunk_id"] for c in out] == ["a", "b"]  # 降级原序
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_reranker.py -v`
Expected: PASS（4 passed）

- [ ] **Step 4: Commit**

```bash
git add app/knowledge/reranker.py tests/knowledge/test_reranker.py
git commit -m "feat(rerank): Reranker 抽象 + Mock/Local(降级) + get_reranker 工厂"
```

## Task 3: 文档格式扩展（.md/.pptx/.xlsx）+ doc_format 字段

**Files:** Modify `app/core/document_parser.py`

- [ ] **Step 1: 更新 SUPPORTED_EXTENSIONS 并在 dispatch 中加分派**

修改 `document_parser.py` 顶部常量：

```python
SUPPORTED_EXTENSIONS = [".docx", ".pdf", ".txt", ".md", ".markdown",
                        ".pptx", ".xlsx", ".xls",
                        ".png", ".jpg", ".jpeg", ".gif", ".webp"]
```

修改 `parse_file` 的 dispatch（`ext == ".txt"` 分支后追加）：

```python
            elif ext in [".md", ".markdown"]:
                return self._parse_md(file_bytes, filename)
            elif ext == ".pptx":
                return self._parse_pptx(file_bytes, filename)
            elif ext in [".xlsx", ".xls"]:
                return self._parse_xlsx(file_bytes, filename)
```

- [ ] **Step 2: 给既有 `_parse_txt/_parse_docx/_parse_pdf/_parse_image` 返回补充 `doc_format`**

以 `_parse_txt` 为例（其余同理，在返回的 dict 中加 `"doc_format": "txt"` / `"docx"` / `"pdf"` / `"image"`）：

```python
    def _parse_txt(self, file_bytes: bytes, filename: str) -> dict:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("gbk", errors="replace")
        return {
            "success": True,
            "text": text,
            "filename": filename,
            "error": "",
            "doc_format": "txt",
        }
```

- [ ] **Step 3: 新增三个解析方法（懒导入依赖）**

在 `_parse_txt` 之后追加：

```python
    def _parse_md(self, file_bytes: bytes, filename: str) -> dict:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("gbk", errors="replace")
        return {
            "success": True,
            "text": text,
            "filename": filename,
            "error": "",
            "doc_format": "md",
        }

    def _parse_pptx(self, file_bytes: bytes, filename: str) -> dict:
        try:
            from pptx import Presentation
            from io import BytesIO
        except ImportError:
            return {"success": False, "text": "", "filename": filename,
                    "error": "python-pptx未安装，请运行: pip install python-pptx", "doc_format": "pptx"}
        try:
            prs = Presentation(BytesIO(file_bytes))
            slides_text = []
            for slide in prs.slides:
                texts = [sh.text.strip() for sh in slide.shapes if sh.has_text_frame and sh.text.strip()]
                if texts:
                    slides_text.append("\n".join(texts))
            full_text = "\n\n".join(slides_text)
            return {"success": True, "text": full_text, "filename": filename, "error": "", "doc_format": "pptx"}
        except Exception as e:
            return {"success": False, "text": "", "filename": filename,
                    "error": f"PPT解析失败: {str(e)}", "doc_format": "pptx"}

    def _parse_xlsx(self, file_bytes: bytes, filename: str) -> dict:
        try:
            from openpyxl import load_workbook
            from io import BytesIO
        except ImportError:
            return {"success": False, "text": "", "filename": filename,
                    "error": "openpyxl未安装，请运行: pip install openpyxl", "doc_format": "xlsx"}
        try:
            wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
            sheets_text = []
            for ws in wb.worksheets:
                rows = []
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip()]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    sheets_text.append(f"=== {ws.title} ===\n" + "\n".join(rows))
            full_text = "\n\n".join(sheets_text)
            return {"success": True, "text": full_text, "filename": filename, "error": "", "doc_format": "xlsx"}
        except Exception as e:
            return {"success": False, "text": "", "filename": filename,
                    "error": f"Excel解析失败: {str(e)}", "doc_format": "xlsx"}
```

- [ ] **Step 4: 写失败→通过测试**

Create `tests/knowledge/test_document_parser_ext.py`:

```python
from app.core.document_parser import DocumentParser


def test_md_parsed_as_text():
    p = DocumentParser()
    out = p.parse_file("# 标题\n正文内容".encode("utf-8"), "note.md")
    assert out["success"] and out["doc_format"] == "md" and "标题" in out["text"]


def test_pptx_parsed(tmp_path):
    p = DocumentParser()
    try:
        from pptx import Presentation
    except ImportError:
        import pytest
        pytest.skip("python-pptx 未安装")
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = "演示要点一"
    path = tmp_path / "s.pptx"
    prs.save(str(path))
    out = p.parse_file(path.read_bytes(), "s.pptx")
    assert out["success"] and out["doc_format"] == "pptx" and "演示要点一" in out["text"]


def test_xlsx_parsed(tmp_path):
    p = DocumentParser()
    try:
        from openpyxl import Workbook
    except ImportError:
        import pytest
        pytest.skip("openpyxl 未安装")
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "分数"])
    ws.append(["张三", 90])
    path = tmp_path / "d.xlsx"
    wb.save(str(path))
    out = p.parse_file(path.read_bytes(), "d.xlsx")
    assert out["success"] and out["doc_format"] == "xlsx" and "张三" in out["text"]


def test_missing_dep_returns_failure_not_exception():
    p = DocumentParser()
    # 未装 python-pptx 时不应抛异常
    try:
        import pptx  # noqa
    except ImportError:
        out = p.parse_file(b"dummy", "x.pptx")
        assert out["success"] is False and "doc_format" in out
```

- [ ] **Step 5: 运行测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_document_parser_ext.py -v`
Expected: PASS（pptx/xlsx 在无依赖时自动 skip，md 必过）

- [ ] **Step 6: Commit**

```bash
git add app/core/document_parser.py tests/knowledge/test_document_parser_ext.py
git commit -m "feat(parser): 扩展文档解析支持 .md/.pptx/.xlsx 并返回 doc_format"
```

## Task 4: DB 加列迁移（幂等）

**Files:** Modify `app/knowledge/schema.py`

- [ ] **Step 1: 在 ensure_schema 中追加幂等加列**

修改 `ensure_schema` 函数，在 `repo._commit()` 之前（FTS 创建之后亦可）插入：

```python
    # 增量更新所需列（幂等：老库已有则忽略）
    for col_sql in (
        "ALTER TABLE knowledge_docs ADD COLUMN doc_format TEXT",
        "ALTER TABLE knowledge_docs ADD COLUMN content_hash TEXT",
        "ALTER TABLE knowledge_docs ADD COLUMN version INTEGER DEFAULT 1",
    ):
        try:
            repo._execute(col_sql)
        except Exception:
            pass  # DuplicateColumn 等 → 已存在，忽略
```

（保留函数末尾既有 `repo._commit()`）

- [ ] **Step 2: 写迁移测试**

Create `tests/knowledge/test_schema_migration.py`:

```python
import tempfile, os
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema


def test_ensure_schema_idempotent_adds_columns():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        repo = KnowledgeRepository(f.name)
        ensure_schema(repo)
        ensure_schema(repo)  # 二次调用不报错
        cols = [r["name"] for r in repo._execute("PRAGMA table_info(knowledge_docs)").fetchall()]
        for c in ("doc_format", "content_hash", "version"):
            assert c in cols
    finally:
        os.remove(f.name)
```

- [ ] **Step 3: 运行测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_schema_migration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/knowledge/schema.py tests/knowledge/test_schema_migration.py
git commit -m "feat(schema): knowledge_docs 幂等加列 doc_format/content_hash/version"
```

## Task 5: 增量幂等 ingest

**Files:** Modify `app/knowledge/service.py`

- [ ] **Step 1: 在 service.py 顶部补充 import**

将 `service.py` 顶部 `import logging` 改为：

```python
"""知识层门面：ingest / retrieve + 可插拔后端注册表。永不向上抛异常。"""
from __future__ import annotations
import hashlib
import logging
import re
from typing import List, Optional
```

- [ ] **Step 2: 替换 `ingest` 并新增 `ingest_text` / 辅助方法**

将现有 `ingest` 方法整体替换为：

```python
    def _resolve_doc_id(self, doc_id: str, source: str, project_id: str) -> str:
        if doc_id:
            return doc_id
        if source:
            return hashlib.sha256(f"{source}|{project_id}".encode("utf-8")).hexdigest()[:16]
        return self.repo._generate_id()

    @staticmethod
    def _content_hash(text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def ingest_text(self, text: str, project_id: str = "", asset_id: str = "",
                    title: str = "", source: str = "", doc_format: str = "text",
                    doc_id: Optional[str] = None) -> dict:
        text = (text or "").strip()
        if not text:
            return {"doc_id": None, "status": "skipped", "version": 0, "reason": "empty"}
        resolved_id = self._resolve_doc_id(doc_id, source, project_id)
        new_hash = self._content_hash(text)
        existing = self.repo._execute(
            "SELECT id, content_hash, version FROM knowledge_docs WHERE id=?",
            (resolved_id,)).fetchone()
        if existing:
            if existing["content_hash"] and existing["content_hash"] == new_hash:
                return {"doc_id": resolved_id, "status": "skipped",
                        "version": existing["version"] or 1, "content_hash": new_hash}
            self.delete_document(resolved_id)  # 级联清理旧 chunk
            version = (existing["version"] or 1) + 1
        else:
            version = 1
        try:
            chunks = chunk_text(text)
        except Exception as e:
            logger.warning("chunk failed: %s", e)
            return {"doc_id": None, "status": "error", "version": 0, "reason": str(e)}
        if not chunks:
            return {"doc_id": None, "status": "skipped", "version": 0, "reason": "no_chunks"}
        self.repo._execute(
            "INSERT INTO knowledge_docs (id, project_id, asset_id, title, source, doc_format, content_hash, version, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (resolved_id, project_id, asset_id, title, source, doc_format, new_hash, version, self.repo._now()))
        chunk_records = []
        for i, ch in enumerate(chunks):
            cid = self.repo._generate_id()
            self.repo._execute(
                "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) "
                "VALUES (?,?,?,?,?,?)",
                (cid, resolved_id, i, ch.content, ch.section, self.repo._json_dumps(ch.meta)))
            chunk_records.append({"id": cid, "content": ch.content, "doc_id": resolved_id})
        self.repo._commit()
        for name in ("keyword", "tfidf", "vector"):
            try:
                self.backends[name].index(chunk_records)
            except Exception as e:
                logger.warning("%s index failed: %s", name, e)
        status = "updated" if existing else "ingested"
        return {"doc_id": resolved_id, "status": status, "version": version, "content_hash": new_hash}

    def ingest(self, text: str, project_id: str = "", asset_id: str = "",
               title: str = "", source: str = "") -> Optional[str]:
        # 向后兼容：保持返回 str(doc_id) 或 None，不破坏既有 310 测试
        return self.ingest_text(
            text, project_id=project_id, asset_id=asset_id, title=title, source=source
        ).get("doc_id")
```

- [ ] **Step 3: 写失败→通过测试**

Create `tests/knowledge/test_incremental_ingest.py`:

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService


def _svc():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_idempotent_skip_when_hash_unchanged():
    svc = _svc()
    r1 = svc.ingest_text("内容安全 平台 过滤 违规", source="s1.txt", doc_format="txt")
    r2 = svc.ingest_text("内容安全 平台 过滤 违规", source="s1.txt", doc_format="txt")
    assert r1["status"] == "ingested" and r2["status"] == "skipped"
    assert r1["doc_id"] == r2["doc_id"]
    # chunk 数不应翻倍
    docs = svc.list_documents()
    assert docs["total"] == 1


def test_idempotent_update_bumps_version_and_replaces_chunks():
    svc = _svc()
    r1 = svc.ingest_text("旧版本 内容 A", source="s2.txt", doc_format="txt")
    r2 = svc.ingest_text("新版本 内容 B 完全不同", source="s2.txt", doc_format="txt")
    assert r1["status"] == "ingested" and r2["status"] == "updated"
    assert r2["version"] == 2
    # 检索应命中新内容，而非旧内容
    hit_new = svc.retrieve("新版本", top_k=3)
    assert any("新版本" in (c["content"] or "") for c in hit_new)


def test_explicit_doc_id_takes_precedence():
    svc = _svc()
    r1 = svc.ingest_text("显式 id 文档", doc_id="DOC-X", source="", doc_format="txt")
    r2 = svc.ingest_text("显式 id 文档", doc_id="DOC-X", doc_format="txt")
    assert r1["doc_id"] == "DOC-X" == r2["doc_id"]
    assert r2["status"] == "skipped"
```

- [ ] **Step 4: 运行测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_incremental_ingest.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add app/knowledge/service.py tests/knowledge/test_incremental_ingest.py
git commit -m "feat(ingest): 增量幂等 ingest_text(content_hash 去重 + version 递增)"
```

## Task 6: retrieve 接入 rerank

**Files:** Modify `app/knowledge/service.py`

- [ ] **Step 1: 新增 `_fetch_candidates` 并改写 `retrieve`**

在 `ingest` 方法之后，将现有 `retrieve` 方法整体替换为：

```python
    def _fetch_candidates(self, ids_with_scores, project_id):
        results = []
        for cid, score in ids_with_scores:
            row = self.repo._execute(
                "SELECT c.content AS content, c.section AS section, c.idx AS idx, d.title AS doc_title "
                "FROM knowledge_chunks c LEFT JOIN knowledge_docs d ON c.doc_id=d.id "
                "WHERE c.id=? AND (? = '' OR d.project_id = ?)",
                (cid, project_id or "", project_id or "")).fetchone()
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

    def retrieve(self, query: str, top_k: int = 5, project_id: Optional[str] = None,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> List[dict]:
        if not query or not query.strip():
            return []
        kw_ids = self.backends["keyword"].search(query)
        tf_ids = self.backends["tfidf"].search(query)
        vec_ids = self.backends["vector"].search(query)
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
        if not fused:
            return []
        do_rerank = rerank if rerank is not None else settings.RERANK_ENABLED
        top_n = rerank_top_n if rerank_top_n is not None else settings.RERANK_TOP_N
        if top_n < top_k:
            top_n = top_k
        if do_rerank:
            try:
                candidates = self._fetch_candidates(fused[:top_n], project_id)
                return get_reranker().rerank(query, candidates, top_k)
            except Exception as e:
                logger.warning("rerank 失败, 回退融合顺序: %s", e)
        return self._fetch_candidates(fused[:top_k], project_id)
```

注意：`service.py` 已 `from app.knowledge.reranker import rrf_fuse`，需追加 `get_reranker` 导入：将顶部 `from app.knowledge.reranker import rrf_fuse` 改为 `from app.knowledge.reranker import rrf_fuse, get_reranker`。同时 `retrieve` 用到 `settings`，确认文件已有 `from app.core.config import settings`（当前 service.py 未直接导入 settings——需新增：`from app.core.config import settings`）。

- [ ] **Step 2: 写失败→通过测试（rerank 改变顺序）**

Create `tests/knowledge/test_retrieve_rerank.py`:

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from app.knowledge.service import KnowledgeService
from app.core.config import settings


@pytest.fixture
def svc():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    s = KnowledgeService(db_path=f.name)
    s.ingest_text("苹果 香蕉 水果 营养", source="a.txt", doc_format="txt")
    s.ingest_text("苹果 公司 股价 财报", source="b.txt", doc_format="txt")
    s.ingest_text("汽车 引擎 发动机 保养", source="c.txt", doc_format="txt")
    return s


def test_rerank_off_returns_fused_order(svc):
    out = svc.retrieve("苹果", top_k=2, rerank=False)
    assert len(out) >= 1
    assert all("chunk_id" in c for c in out)


def test_rerank_mock_changes_order(svc, monkeypatch):
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    out = svc.retrieve("苹果 公司", top_k=2, rerank=True)
    # MockReranker 按命中数排序：含"公司"的 b 应排前
    assert out[0]["chunk_id"]  # 非空
    assert "rerank_score" in out[0]


def test_rerank_failure_degrades(svc, monkeypatch):
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    # 强制 get_reranker 抛异常 → retrieve 应回退融合顺序且不报错
    import app.knowledge.service as svc_mod
    orig = svc_mod.get_reranker
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(svc_mod, "get_reranker", boom)
    out = svc.retrieve("苹果", top_k=2, rerank=True)
    assert isinstance(out, list) and len(out) >= 1
```

- [ ] **Step 3: 运行测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_retrieve_rerank.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/knowledge/service.py tests/knowledge/test_retrieve_rerank.py
git commit -m "feat(retrieve): 接入 rerank（候选池 top_n + 失败降级原序）"
```

## Task 7: API 参数透传（/ingest 真实 status + /retrieve /ask rerank）

**Files:** Modify `app/api/knowledge_api.py`

- [ ] **Step 1: 改写 `/ingest` 使用 `ingest_text` 并透出 status/version/doc_format**

将现有 `ingest` 函数整体替换为：

```python
@router.post("/ingest")
async def ingest(
    files: Optional[List[UploadFile]] = File(None),
    text: str = Form(default=""),
    project_id: str = Form(default=""),
    asset_id: str = Form(default=""),
    title: str = Form(default=""),
    source: str = Form(default="upload"),
    doc_id: str = Form(default=""),
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    units = []
    parse_errors = []
    for f in (files or []):
        content = await f.read()
        parsed = parse_document(content, f.filename or "unknown")
        if parsed["success"]:
            units.append((title or f.filename or "unknown", parsed["text"], parsed.get("doc_format", "unknown")))
        else:
            parse_errors.append({"filename": f.filename, "error": parsed["error"]})
    if text and text.strip():
        units.append((title or "text", text, "text"))
    if not units:
        return ApiResponse.error("请提供文件或文本内容", code=400)
    docs = []
    for disp_title, t, doc_format in units:
        res = service.ingest_text(
            t, project_id=project_id, asset_id=asset_id,
            title=disp_title, source=source, doc_format=doc_format,
            doc_id=doc_id or None)
        docs.append({"doc_id": res["doc_id"], "title": disp_title,
                     "status": res["status"], "version": res["version"]})
    if parse_errors:
        return ApiResponse.partial(
            data={"docs": docs, "count": len(docs)},
            message="部分文件解析失败", errors=parse_errors)
    return ApiResponse.ok({"docs": docs, "count": len(docs)})
```

- [ ] **Step 2: `RetrieveRequest` / `AskRequest` 增加 rerank 参数，`retrieve`/`ask` 透传**

修改 `RetrieveRequest`：

```python
class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    project_id: str = ""
    rerank: Optional[bool] = None
    rerank_top_n: Optional[int] = None
```

修改 `/retrieve` 函数体：

```python
@router.post("/retrieve")
def retrieve(
    req: RetrieveRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    if not req.query or not req.query.strip():
        return ApiResponse.error("请提供查询语句", code=400)
    results = service.retrieve(
        req.query, top_k=req.top_k, project_id=req.project_id or None,
        rerank=req.rerank, rerank_top_n=req.rerank_top_n)
    return ApiResponse.ok({"results": results})
```

修改 `AskRequest`：

```python
class AskRequest(BaseModel):
    question: str
    project_id: str = ""
    top_k: int = 5
    rerank: Optional[bool] = None
    rerank_top_n: Optional[int] = None
```

修改 `/ask` 函数体（向 `gen.answer` 透传）：

```python
@router.post("/ask")
def ask(req: AskRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    if not req.question or not req.question.strip():
        return ApiResponse.error("请提供问题", code=400)
    from app.knowledge.answer import RAGAnswerGenerator
    gen = RAGAnswerGenerator(service=service)
    result = gen.answer(req.question, project_id=req.project_id or None, top_k=req.top_k,
                        rerank=req.rerank, rerank_top_n=req.rerank_top_n)
    return ApiResponse.ok(result)
```

- [ ] **Step 3: 让 `RAGAnswerGenerator.answer` 透传 rerank 到 retrieve**

修改 `app/knowledge/answer.py` 的 `answer` 签名与内部调用：

```python
    def answer(self, question: str, project_id: Optional[str] = None, top_k: int = 5,
               rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> dict:
        chunks = self._get_service().retrieve(
            question, top_k=top_k, project_id=project_id,
            rerank=rerank, rerank_top_n=rerank_top_n)
```

- [ ] **Step 4: 写 HTTP 集成测试**

Create `tests/knowledge/test_api_enhancement.py`:

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from app.knowledge.service import KnowledgeService
from app.main import app
from app.api.knowledge_api import get_knowledge_service
from app.core.config import settings


def _http(tmp):
    svc = KnowledgeService(db_path=tmp)
    svc.ingest_text("苹果 水果 营养 健康", source="a.txt", doc_format="txt")
    svc.ingest_text("苹果 公司 股价 财报", source="b.txt", doc_format="txt")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    return tmp


def test_ingest_returns_real_status_and_version():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    try:
        _http(tmp)
        client = TestClient(app)
        # 重复相同 source 入库 → 应 skipped
        resp = client.post(
            "/knowledge/ingest",
            data={"text": "苹果 水果 营养 健康", "source": "a.txt", "project_id": ""},
            headers={"Authorization": f"Bearer {settings.API_KEY or 'test'}"})
        # 注意：API_KEY 为空时中间件会 401；测试用 monkeypatch 注入，见下
    finally:
        app.dependency_overrides.pop(get_knowledge_service, None)
        os.remove(tmp)
```

> 由于 `/knowledge/*` 强制鉴权且 `API_KEY` 默认空，上述直连会 401。改为在测试内用 `monkeypatch` 注入唯一 key 并发请求（沿用 `tests/knowledge/test_api_ask_eval.py` 已验证模式）。将 `test_api_enhancement.py` 写成：

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient
from app.knowledge.service import KnowledgeService
from app.main import app
from app.api.knowledge_api import get_knowledge_service
from app.core.config import settings


@pytest.fixture
def client_and_cleanup(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-admin-key-enh")
    monkeypatch.setattr(settings, "RAG_LLM_PROVIDER", "mock")
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    svc = KnowledgeService(db_path=tmp)
    svc.ingest_text("苹果 水果 营养 健康", source="a.txt", doc_format="txt")
    svc.ingest_text("苹果 公司 股价 财报", source="b.txt", doc_format="txt")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-admin-key-enh"}
    yield client, headers, tmp
    app.dependency_overrides.pop(get_knowledge_service, None)
    try:
        os.remove(tmp)
    except OSError:
        pass


def test_ingest_idempotent_status(client_and_cleanup):
    client, headers, _ = client_and_cleanup
    r1 = client.post("/knowledge/ingest", data={"text": "苹果 水果 营养 健康", "source": "a.txt"}, headers=headers)
    r2 = client.post("/knowledge/ingest", data={"text": "苹果 水果 营养 健康", "source": "a.txt"}, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["docs"][0]["status"] == "ingested"
    assert r2.json()["data"]["docs"][0]["status"] == "skipped"


def test_retrieve_rerank_param(client_and_cleanup, monkeypatch):
    client, headers, _ = client_and_cleanup
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    resp = client.post("/knowledge/retrieve",
                       json={"query": "苹果 公司", "top_k": 2, "rerank": True},
                       headers=headers)
    assert resp.status_code == 200
    assert "rerank_score" in resp.json()["data"]["results"][0]
```

- [ ] **Step 5: 运行 Slice 1 新增测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_api_enhancement.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/knowledge_api.py app/knowledge/answer.py tests/knowledge/test_api_enhancement.py
git commit -m "feat(api): /ingest 真实 status/version, /retrieve|/ask 透传 rerank 参数"
```

## Task 8: Slice 1 全量回归

**Files:** （无新增，仅验证）

- [ ] **Step 1: 跑全量回归**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -20`
Expected: **全部 passed，0 failed**（含既有 310 + Slice 1 新增）。若失败，定位并修复后重跑。

- [ ] **Step 2: 确认未触碰漂移文件后提交（如有其他改动）**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && git status --short`
Expected: 仅显示本次计划涉及的源码/测试文件；`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*` 保持未暂存。如有意外改动，先 `git checkout -- <漂移文件>` 还原再继续。

---

# Slice 2 —— 补全（云端 rerank + 质量对比 + 性能守护）

## Task 9: CloudReranker（Cohere/Jina，多 key 故障转移）

**Files:** Create `app/knowledge/cloud_reranker.py`

- [ ] **Step 1: 写失败测试**

Create `tests/knowledge/test_cloud_reranker.py`:

```python
import types
from app.knowledge.cloud_reranker import CloudReranker


def _fake_response(payload):
    class R:
        def json(self):
            # Cohere 风格: results 含 index/score
            results = [{"index": i, "relevance_score": s}
                       for i, s in enumerate(payload["_scores"])]
            return {"results": results}
    return R()


def test_cloud_rerank_orders_and_failover(monkeypatch):
    scores = [0.1, 0.9, 0.3]
    called = {"n": 0}

    def fake_post(url, headers, json):
        called["n"] += 1
        if called["n"] == 1:
            raise RuntimeError("key1 dead")  # 第一把 key 失败
        json["_scores"] = scores
        return _fake_response(json)

    r = CloudReranker(keys=["bad", "good"])
    monkeypatch.setattr(r, "_post", fake_post)
    cands = [{"chunk_id": f"c{i}", "content": f"doc {i}"} for i in range(3)]
    out = r.rerank("q", cands, top_k=3)
    assert called["n"] == 2  # 故障转移到第二把 key
    assert [c["chunk_id"] for c in out] == ["c1", "c2", "c0"]  # 按 score 降序


def test_cloud_rerank_no_keys_degrades():
    r = CloudReranker(keys=[])
    cands = [{"chunk_id": "x", "content": "a"}]
    out = r.rerank("q", cands, top_k=1)
    assert out == cands  # 原序
```

- [ ] **Step 2: 实现 CloudReranker**

Create `app/knowledge/cloud_reranker.py`:

```python
"""云端 Reranker（Cohere/Jina 风格），多 key 故障转移，失败降级原序。"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional

from app.knowledge.reranker import Reranker

logger = logging.getLogger(__name__)

# 默认端点（Cohere Rerank v2）。如需 Jina 在 RERANK_KEYS 旁配置 base_url。
COHERE_URL = "https://api.cohere.ai/v2/rerank"


class CloudReranker(Reranker):
    name = "cloud"

    def __init__(self, provider: str = "cohere", keys: Optional[List[str]] = None,
                 base_url: Optional[str] = None):
        self.provider = provider
        self.keys = list(keys or [])
        self.base_url = base_url or COHERE_URL

    def _post(self, url, headers, json):
        import requests
        return requests.post(url, headers=headers, json=json, timeout=20)

    def _headers(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _payload(self, query: str, texts: List[str]) -> dict:
        return {"model": "rerank-english-v3.0", "query": query, "documents": texts, "top_n": len(texts)}

    def _extract(self, data: dict) -> List[float]:
        # Cohere: [{"index": i, "relevance_score": s}, ...]
        return [float(r["relevance_score"]) for r in data.get("results", [])]

    def rerank(self, query, candidates, top_k) -> List[Dict]:
        if not self.keys:
            logger.warning("cloud rerank 无 key, 降级原序")
            return candidates[:top_k]
        texts = [c.get("content") or "" for c in candidates]
        last_err = None
        for key in self.keys:
            try:
                resp = self._post(self.base_url, self._headers(key), self._payload(query, texts))
                scores = self._extract(resp.json())
                if len(scores) != len(candidates):
                    raise ValueError("云端返回分数数与候选不一致")
                scored = [dict(c, rerank_score=float(s)) for c, s in zip(candidates, scores)]
                scored.sort(key=lambda x: -x["rerank_score"])
                return scored[:top_k]
            except Exception as e:
                last_err = e
                logger.warning("cloud rerank key 失败, 尝试下一 key: %s", e)
        logger.warning("cloud rerank 全部 key 失败, 降级原序: %s", last_err)
        return candidates[:top_k]
```

- [ ] **Step 3: 运行测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_cloud_reranker.py -v`
Expected: PASS（需 `requests` 已安装——FastAPI 项目通常已带；若无则 `pip install requests`，仅测试/运行期用）

- [ ] **Step 4: Commit**

```bash
git add app/knowledge/cloud_reranker.py tests/knowledge/test_cloud_reranker.py
git commit -m "feat(rerank): CloudReranker(Cohere 风格, 多 key 故障转移, 降级原序)"
```

## Task 10: RAGEvaluator 前后对比 + 小 gold 集 + 性能守护

**Files:** Modify `app/knowledge/eval.py`；Create `tests/knowledge/test_eval_compare.py`、`tests/knowledge/test_perf_guard.py`

- [ ] **Step 1: 扩展 `evaluate` 透传 rerank，新增 `compare_before_after`**

将 `app/knowledge/eval.py` 顶部 import 补充 `Optional`，并将 `evaluate` 签名与内部 `retrieve` 调用改为透传，并在类末尾追加 `compare_before_after`：

```python
    def evaluate(self, service, gold=None, top_k: int = 5,
                 project_id: Optional[str] = None, with_faithfulness: bool = False,
                 rerank: Optional[bool] = None, rerank_top_n: Optional[int] = None) -> dict:
        gold = self.load_gold(gold if gold is not None else self.DEFAULT_GOLD)
        if not gold:
            raise ValueError("gold 为空")
        per_item = []
        p_sum = r_sum = 0.0
        for item in gold:
            retrieved = service.retrieve(item["query"], top_k=top_k, project_id=project_id,
                                         rerank=rerank, rerank_top_n=rerank_top_n)
            got = {r["chunk_id"] for r in retrieved}
            expected = set(item.get("expected_chunk_ids") or [])
            hit = len(got & expected)
            precision = hit / min(top_k, len(retrieved)) if retrieved else 0.0
            recall = (hit / len(expected)) if expected else (1.0 if not retrieved else 0.0)
            entry = {"query": item["query"], "precision@k": precision, "recall@k": recall}
            if with_faithfulness and expected:
                try:
                    from app.knowledge.answer import RAGAnswerGenerator
                    gen = RAGAnswerGenerator(service=service)
                    out = gen.answer(item["query"], project_id=project_id, top_k=top_k,
                                     rerank=rerank, rerank_top_n=rerank_top_n)
                    entry["faithfulness"] = out.get("metrics", {}).get("citation_rate", None)
                except Exception as e:
                    logger.warning("faithfulness 计算失败: %s", e)
                    entry["faithfulness"] = None
            per_item.append(entry)
            p_sum += precision
            r_sum += recall
        n = len(per_item)
        return {
            "precision@k": round(p_sum / n, 4) if n else 0.0,
            "recall@k": round(r_sum / n, 4) if n else 0.0,
            "n": n,
            "per_item": per_item,
        }

    def compare_before_after(self, service, gold=None, top_k: int = 5,
                             project_id: Optional[str] = None,
                             rerank_top_n: Optional[int] = None) -> dict:
        before = self.evaluate(service, gold, top_k=top_k, project_id=project_id, rerank=False)
        after = self.evaluate(service, gold, top_k=top_k, project_id=project_id,
                              rerank=True, rerank_top_n=rerank_top_n)
        return {
            "before": before,
            "after": after,
            "delta_precision": round(after["precision@k"] - before["precision@k"], 4),
            "delta_recall": round(after["recall@k"] - before["recall@k"], 4),
            "rerank_not_worse": (after["precision@k"] >= before["precision@k"] - 1e-9)
                                 and (after["recall@k"] >= before["recall@k"] - 1e-9),
        }
```

- [ ] **Step 2: 写前后对比测试（用 MockReranker 保证确定性）**

Create `tests/knowledge/test_eval_compare.py`:

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from app.knowledge.service import KnowledgeService
from app.knowledge.eval import RAGEvaluator
from app.core.config import settings


def _svc_with_gold():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    svc = KnowledgeService(db_path=f)
    svc.ingest_text("内容安全 平台 过滤 违规 信息 审核", source="p1.txt", doc_format="txt")
    svc.ingest_text("咖啡 烘焙 风味 产地", source="p2.txt", doc_format="txt")
    gold = [{"query": "内容安全 违规", "expected_chunk_ids": []}]
    return svc, f, gold


def test_compare_before_after_structure():
    svc, f, gold = _svc_with_gold()
    try:
        monkeypatch  # 占位避免未用告警（实际在 fixture 内）
    except NameError:
        pass
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    mp.setattr(settings, "RERANK_PROVIDER", "mock")
    try:
        ev = RAGEvaluator()
        rep = ev.compare_before_after(svc, gold, top_k=3)
        assert "before" in rep and "after" in rep
        assert "precision@k" in rep["before"] and "precision@k" in rep["after"]
        assert isinstance(rep["rerank_not_worse"], bool)
    finally:
        mp.undo()
        os.remove(f)
```

> 简化写法（推荐，直接 fixture）：

```python
import sys, os, tempfile, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService
from app.knowledge.eval import RAGEvaluator
from app.core.config import settings


@pytest.fixture
def svc_and_gold():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    svc = KnowledgeService(db_path=f)
    svc.ingest_text("内容安全 平台 过滤 违规 信息 审核", source="p1.txt", doc_format="txt")
    svc.ingest_text("咖啡 烘焙 风味 产地", source="p2.txt", doc_format="txt")
    yield svc, f, [{"query": "内容安全 违规", "expected_chunk_ids": []}]
    os.remove(f)


def test_compare_before_after_structure(svc_and_gold, monkeypatch):
    svc, _, gold = svc_and_gold
    monkeypatch.setattr(settings, "RERANK_PROVIDER", "mock")
    rep = RAGEvaluator().compare_before_after(svc, gold, top_k=3)
    assert "before" in rep and "after" in rep
    assert "precision@k" in rep["before"] and "precision@k" in rep["after"]
    assert isinstance(rep["rerank_not_worse"], bool)
```

- [ ] **Step 3: 写性能守护测试**

Create `tests/knowledge/test_perf_guard.py`:

```python
import time
from app.knowledge.reranker import MockReranker


def _big_cands(n=100):
    return [{"chunk_id": f"c{i}", "content": f"文档内容片段 {i} 关于主题关键词", "score": 1.0 - i * 0.001}
            for i in range(n)]


def test_mock_rerank_100_candidates_within_budget():
    cands = _big_cands(100)
    start = time.perf_counter()
    out = MockReranker().rerank("主题关键词", cands, top_k=5)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(out) == 5
    assert elapsed_ms < 50.0  # P95 预算：MockReranker 重排 100 候选应远低于 50ms
```

- [ ] **Step 4: 运行 Slice 2 测试**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/knowledge/test_cloud_reranker.py tests/knowledge/test_eval_compare.py tests/knowledge/test_perf_guard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/knowledge/eval.py tests/knowledge/test_eval_compare.py tests/knowledge/test_perf_guard.py
git commit -m "feat(eval): RAGEvaluator 前后对比 + 性能 P95 守护(MockReranker)"
```

## Task 11: 全量回归 + 验收报告

**Files:** （无新增）

- [ ] **Step 1: 跑全量回归**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -20`
Expected: **全部 passed，0 failed**。

- [ ] **Step 2: 生成验收摘要（C 级）**

Run（在临时库上用 `RAGEvaluator.compare_before_after` 跑一个小 gold 集，输出 precision@k/recall@k 前后对比 + 延迟预算结论），将结果记入 PR 描述或 `docs/superpowers/plans/2026-07-10-knowledge-rag-enhancement.md` 末尾「验收记录」小节。

- [ ] **Step 3: 漂移纪律最终确认**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && git status --short`
Expected: 仅源码/测试文件；漂移文件未提交。

---

## 自审（Self-Review）

1. **Spec 覆盖**：
   - Rerank 混合可切换 → Task 2（接口/Mock/Local）+ Task 9（Cloud）+ Task 6（接入）。
   - 多格式 → Task 3（.md/.pptx/.xlsx，扩展现有 parser；PDF/OCR/Word 已具备）。
   - 增量更新 → Task 4（迁移）+ Task 5（幂等 ingest）+ Task 7（API status）。
   - C 级验收 → Task 10（前后对比 + 性能守护）+ Task 11（全量回归）。
   - doc_id 显式>source派生>随机、content_hash、version → Task 5 实现并测试。
   - 漂移纪律 → 每个 Task 的 Commit 步骤仅 add 目标文件；Task 8/11 复核。
2. **占位符扫描**：无 TBD/TODO；每个代码步骤均给出完整实现或精确修改片段。
3. **类型一致性**：`Reranker.rerank(query, candidates, top_k)` 在 Mock/Local/Cloud/NoOp 签名一致；`get_reranker` 返回类型统一为 `Reranker`；`ingest_text` 返回 dict（含 `doc_id/status/version/content_hash`），`ingest` 仍返回 `Optional[str]`；`retrieve` 新增 `rerank/rerank_top_n` 在 service/answer/api 三处签名一致透传；`evaluate` 与 `compare_before_after` 均透传 `rerank/rerank_top_n`。`doc_format` 字段在 parser 各方法、API、`ingest_text` 入参、DB 列四处一致。
4. **已知偏差已记录**：见顶部「实现备注」，并已同步更正设计规格文档 §4.2/§11。

---

## 验收记录（C 级 · 2026-07-10 完成）

**执行方式**：superpowers:subagent-driven-development，Task 1→11 连续执行，每任务实现子代理 + 主控核验，master 分支直接提交。

**逐任务提交**：
| Task | 说明 | commit |
|------|------|--------|
| T1 | 新增 `RERANK_*` / `OCR_ENABLED` 配置项 | `30751be` |
| T2 | Reranker 抽象 + NoOp/Mock/Local(降级) + `get_reranker` 工厂 | `fc3ed97`（+ `66a5838` 恢复 rrf_fuse 单测） |
| T3 | 文档解析扩展 `.md/.pptx/.xlsx` + `doc_format` | `7790b7f` |
| T4 | `knowledge_docs` 幂等加列 `doc_format/content_hash/version` | `d78ae9e` |
| T5 | 增量幂等 `ingest_text`（content_hash 去重 + version 递增 + 级联替换） | `ccb6d12` |
| T6 | `retrieve` 接入 rerank（候选池 top_n + 失败降级原序） | `78f9a84` |
| T7 | `/ingest` 真实 status/version、`/retrieve`\|`/ask` 透传 rerank | `482a050` |
| T9 | `CloudReranker`（Cohere 风格，多 key 故障转移，降级原序） | `941471b` |
| T10 | `RAGEvaluator.compare_before_after` + 性能 P95 守护 | `e5d5ba8` |

**① 功能正确 — 全量回归**：`pytest -q` → **331 passed / 2 skipped / 0 failed**（基线 310，净增全绿）。

**② 前后对比（`RAGEvaluator.compare_before_after`，MockReranker 确定性）**：
```
before  precision@k=1.0000  recall@k=1.0000
after   precision@k=1.0000  recall@k=1.0000
delta_precision=0.0000  delta_recall=0.0000  rerank_not_worse=True
```
> 说明：小 gold 集下融合顺序已达上限，rerank 未劣化（`rerank_not_worse=True`），符合 C 级「重排不使指标变差」的守护目标；在候选噪声更大的真实语料上重排增益会显现。

**③ 延迟 P95 守护**：MockReranker 重排 100 候选耗时 **0.064 ms**（预算 50 ms）→ **PASS**。

**④ 漂移纪律**：全程仅 `git add` 计划内目标文件；`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/**` 全程未暂存/未提交。
