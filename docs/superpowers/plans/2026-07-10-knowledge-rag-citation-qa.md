# 知识库 RAG 引用溯源与问答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有知识库检索骨架(keyword+tfidf+vector 三路 RRF)之上,新增 RAG 引用溯源与问答(`/ask`)、分节精准注入、引用校验、引标评估(`/evaluate`),并支持多 Key 轮询/故障转移与细分的接地提示词。

**Architecture:** 新建 `RAGAnswerGenerator`(`app/knowledge/answer.py`)编排 `KnowledgeService.retrieve`(扩展返回 chunk_id/idx/score)→ 分节结构化上下文(`build_context`)→ 复用 `SOPLLMClient`(扩展多 key 轮询+故障转移)生成带 `[n]` 引用 → `validate_citations` 剔除非命中编号 → 返回 `{answer, citations, metrics}`。提示词拆为 `app/knowledge/prompts.py` 五块子常量,支持可选两阶段(先引证规划再作答)。`RAGEvaluator`(`app/knowledge/eval.py`)对 gold 集算 P@k/R@k/faithfulness。新增 `/knowledge/ask`、`/knowledge/evaluate` 端点。

**Tech Stack:** Python 3.13, FastAPI, pydantic-settings, httpx(注入式 fake 测试), numpy(已装)。零新重依赖。

**项目路径:** `C:\Users\34216\Documents\New project 3\bsc-backend`(git repo root,路径均相对它)。
**测试命令(Windows + Git Bash,必须用项目自带 venv):** `/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest <args>`

**git 纪律(贯穿全程,不可违反):** 工作树存在刻意保留的未提交漂移,**严禁触碰或提交**:
- `app/bsc_cloud.db`、`app/bsc_cloud.db-shm`
- `app/services/llm_service.py`(已修改,不碰)
- `static/dashboard.html`(已修改,不碰)
- `archive/orphan_fork/...`(已删除)
提交时**只** `git add` 本计划明确列出的文件,绝不 `git add -A` 或 `git add .`。

---

### Task 1: config.py 新增 RAG 配置

**Files:**
- Modify: `app/core/config.py`(在 `EMBEDDING_MODEL` 行之后插入)
- Test: `tests/test_config_rag.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_config_rag.py`:
```python
from app.core.config import settings


def test_rag_llm_provider_default_is_mock():
    assert hasattr(settings, "RAG_LLM_PROVIDER")
    assert settings.RAG_LLM_PROVIDER == "mock"


def test_rag_config_defaults():
    assert settings.RAG_LLM_KEYS == []
    assert settings.RAG_TWO_PHASE is False
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/test_config_rag.py -v`
Expected: FAIL(`AttributeError`/`hasattr` 为 False)。

- [ ] **Step 3: 修改 `app/core/config.py`**

定位:
```python
    EMBEDDING_MODEL: str = "text-embedding-3-small"
```
在其后新增(保留其后原有空行):
```python
    RAG_LLM_PROVIDER: str = "mock"  # RAG 问答生成使用的 LLM provider (deepseek/doubao/qwen/kimi/mock)
    RAG_LLM_KEYS: List[str] = []    # 多 Key 轮询/故障转移;为空则回落该 provider 的单 key
    RAG_TWO_PHASE: bool = False     # 两阶段生成:先引证规划再作答(更精准,延迟更高)
```
(`List` 已在文件顶部 `from typing import List, Optional` 导入。)

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/test_config_rag.py -v`
Expected: 2 passed。

- [ ] **Step 5: 提交**
```bash
git add app/core/config.py tests/test_config_rag.py
git commit -m "feat(config): add RAG_LLM_PROVIDER/KEYS/TWO_PHASE for citation QA"
```

---

### Task 2: SOPLLMClient 扩展多 Key 轮询 + 故障转移

**Files:**
- Modify: `app/services/sop_llm_client.py`(`__init__` 加 `keys`; `chat` 加轮询/故障转移)
- Test: `tests/test_sop_llm_client_multikeys.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_sop_llm_client_multikeys.py`:
```python
import httpx
import pytest

from app.services.sop_llm_client import SOPLLMClient, SOPLLMError


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code not in (401, 402, 429):
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


def test_multikeys_failover_hits_valid_key():
    seq = {1: _FakeResp({"error": "unauth"}, status=401),
           2: _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})}

    def handler(n, url, headers, body):
        return seq[n]

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["bad", "good"],
                     http_client=_FakeClient(handler))
    out = c.chat("sys", "usr")
    assert out["content"] == '{"answer":"ok"}'


def test_multikeys_exhausted_raises():
    def handler(n, url, headers, body):
        return _FakeResp({"error": "unauth"}, status=401)

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["k1", "k2"],
                     http_client=_FakeClient(handler))
    with pytest.raises(SOPLLMError):
        c.chat("sys", "usr")


def test_multikeys_5xx_also_failover():
    seq = {1: _FakeResp({"error": "boom"}, status=500),
           2: _FakeResp({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})}

    def handler(n, url, headers, body):
        return seq[n]

    c = SOPLLMClient(provider="deepseek", api_key="bad", keys=["bad", "good"],
                     http_client=_FakeClient(handler))
    assert c.chat("sys", "usr")["content"] == '{"answer":"ok"}'
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/test_sop_llm_client_multikeys.py -v`
Expected: FAIL(`__init__() got an unexpected keyword argument 'keys'`)。

- [ ] **Step 3: 修改 `app/services/sop_llm_client.py`**

(a) `__init__` 增加 `keys` 参数并在构造末尾设置 `self.keys`(在 `if self.provider == "mock": return` 之后、`if self.provider not in PROVIDER_REGISTRY:` 之前插入):
```python
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
        keys: Optional[list] = None,
    ):
```
并在 `self.api_key = api_key if api_key is not None else getattr(settings, key_attr, "")` 之后插入:
```python
        if keys:
            self.keys = list(keys)
        elif self.api_key:
            self.keys = [self.api_key]
        else:
            self.keys = []
```

(b) 替换 `chat` 方法体(仅非 mock 分支的 HTTP 调用部分)为带 key 轮询的版本。将:
```python
        try:
            client = self._http or httpx.Client(timeout=self.timeout)
            try:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return {"content": data["choices"][0]["message"]["content"]}
            finally:
                if self._http is None:
                    client.close()
        except httpx.HTTPError as e:
            raise SOPLLMError(f"LLM 请求失败: {e}") from e
```
替换为:
```python
        keys = self.keys or [self.api_key]
        last_err = None
        for key in keys:
            try:
                client = self._http or httpx.Client(timeout=self.timeout)
                try:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code in (401, 402, 429):
                        logger.warning("LLM key 被拒(%s),切换下一 key", resp.status_code)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    return {"content": data["choices"][0]["message"]["content"]}
                finally:
                    if self._http is None:
                        client.close()
            except httpx.HTTPError as e:
                last_err = e
                logger.warning("LLM 请求失败(尝试下一 key): %s", e)
                continue
        raise SOPLLMError(f"所有 LLM key 均不可用: {last_err}")
```

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/test_sop_llm_client_multikeys.py -v`
Expected: 3 passed。

- [ ] **Step 5: 提交**
```bash
git add app/services/sop_llm_client.py tests/test_sop_llm_client_multikeys.py
git commit -m "feat(llm): SOPLLMClient 支持多 key 轮询与 401/402/429/5xx 故障转移"
```

---

### Task 3: retrieve 扩展返回 chunk_id/idx/score

**Files:**
- Modify: `app/knowledge/reranker.py`(`rrf_fuse` 返回 `(cid, score)` 元组)
- Modify: `app/knowledge/service.py`(`retrieve` 使用元组并返回新字段)
- Test: `tests/knowledge/test_retrieve_enriched.py`

注:`rrf_fuse` 仅被 `service.py:75` 调用,改动可控。

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_retrieve_enriched.py`:
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


def test_retrieve_returns_chunk_id_idx_score():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    svc.ingest("咖啡 烘焙 风味 分析", project_id="p1", title="B")
    res = svc.retrieve("内容安全 违规")
    assert res, "应检索到结果"
    top = res[0]
    assert "chunk_id" in top and top["chunk_id"]
    assert "idx" in top
    assert "score" in top and isinstance(top["score"], float)
    assert top["doc_title"] == "A"
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_retrieve_enriched.py -v`
Expected: FAIL(`'chunk_id' not in top`)。

- [ ] **Step 3: 修改 `app/knowledge/reranker.py`**

将:
```python
def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List[str]:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda c: -scores[c])
```
改为:
```python
def rrf_fuse(ranklists: List[List[str]], k: int = 60) -> List:
    scores: dict = {}
    for rl in ranklists:
        for rank, cid in enumerate(rl):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])
```

- [ ] **Step 4: 修改 `app/knowledge/service.py` 的 `retrieve`**

将:
```python
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
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
改为:
```python
        fused = rrf_fuse([kw_ids, tf_ids, vec_ids])
        top = fused[:top_k]
        if not top:
            return []
        results = []
        for cid, score in top:
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
                    "idx": row["idx"],
                    "score": score,
                    "doc_title": row["doc_title"] or "未知来源",
                })
        return results
```

- [ ] **Step 5: 更新既有 reranker 单测(若其断言返回纯 id 列表)**

若 `tests/knowledge/test_reranker.py`(或类似)断言 `rrf_fuse(...)` 返回 `List[str]`,将其断言改为检查返回的 `(cid, score)` 元组(或 cid 集合)。运行全知识测试确认无回归:
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/ -q`

- [ ] **Step 6: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_retrieve_enriched.py tests/knowledge/test_reranker.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**
```bash
git add app/knowledge/reranker.py app/knowledge/service.py tests/knowledge/test_retrieve_enriched.py
git commit -m "feat(knowledge): retrieve 返回 chunk_id/idx/score 供引用溯源使用"
```

---

### Task 4: prompts.py 细分接地提示词

**Files:**
- Create: `app/knowledge/prompts.py`
- Test: `tests/knowledge/test_prompts.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_prompts.py`:
```python
from app.knowledge.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_citation_plan_prompt,
    build_answer_prompt,
    ROLE_BLOCK,
    TASK_BLOCK,
    CONTEXT_CONTRACT_BLOCK,
    CITATION_RULES_BLOCK,
    OUTPUT_SCHEMA_BLOCK,
)


def test_system_prompt_has_five_subblocks():
    sp = build_system_prompt()
    for blk in (ROLE_BLOCK, TASK_BLOCK, CONTEXT_CONTRACT_BLOCK,
                CITATION_RULES_BLOCK, OUTPUT_SCHEMA_BLOCK):
        assert blk in sp


def test_user_prompt_contains_question_and_context():
    up = build_user_prompt("什么是 SLA?", "[1] SLA 是服务等级")
    assert "什么是 SLA?" in up
    assert "[1] SLA 是服务等级" in up


def test_citation_plan_prompt_mentions_cite_ids():
    assert "cite_ids" in build_citation_plan_prompt("Q", "ctx")


def test_answer_prompt_constrains_to_plan():
    ap = build_answer_prompt("Q", "ctx", [1, 3])
    assert "[1]" in ap and "[3]" in ap
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_prompts.py -v`
Expected: FAIL(`ModuleNotFoundError: app.knowledge.prompts`)。

- [ ] **Step 3: 创建 `app/knowledge/prompts.py`**

```python
"""RAG 接地提示词的细分子块与组装函数。

把提示词拆成独立常量(角色/任务/上下文契约/引用规则/输出 schema),
便于单独测试与调优;可选两阶段(先引证规划再作答)。
"""
from __future__ import annotations

ROLE_BLOCK = (
    "你是严格基于企业知识库作答的业务分析师,只使用下方带编号的 [n] 知识,"
    "不得凭空杜撰或引入未提供的外部信息。"
)
TASK_BLOCK = "根据用户问题,仅使用下方带编号的 [n] 知识给出答案。"
CONTEXT_CONTRACT_BLOCK = (
    "下方知识按「[章节：xxx]」分段,每段内有 [n] 编号的内容块。"
    "未提供编号的知识一律不得使用;每个 [n] 仅对应其下方标注的内容。"
)
CITATION_RULES_BLOCK = (
    "引用规则:每条事实必须标注其来源 [n];禁止出现无任何 [n] 的来源断言;"
    "若现有知识不足以回答问题,明确说明「依据现有知识无法回答」。"
)
OUTPUT_SCHEMA_BLOCK = '只输出 JSON {"answer": "<含 [n] 引用的答案>"},不要额外解释。'


def build_system_prompt() -> str:
    return "\n\n".join([
        ROLE_BLOCK, TASK_BLOCK, CONTEXT_CONTRACT_BLOCK,
        CITATION_RULES_BLOCK, OUTPUT_SCHEMA_BLOCK,
    ])


def build_user_prompt(question: str, context: str) -> str:
    return f"问题：{question}\n\n知识：\n{context}"


def build_citation_plan_prompt(question: str, context: str) -> str:
    return (
        "请先判断支撑回答需要引用哪些知识块。只输出 JSON "
        '{"cite_ids": [<用到的 [n] 编号列表>]}。\n\n'
        f"问题：{question}\n\n知识：\n{context}"
    )


def build_answer_prompt(question: str, context: str, cite_ids) -> str:
    ids = ", ".join(f"[{i}]" for i in cite_ids)
    return (
        f"问题：{question}\n\n"
        f"只允许引用以下编号的知识:{ids}\n\n知识：\n{context}"
    )
```

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_prompts.py -v`
Expected: 4 passed。

- [ ] **Step 5: 提交**
```bash
git add app/knowledge/prompts.py tests/knowledge/test_prompts.py
git commit -m "feat(knowledge): 细分接地提示词为五块子常量 + 两阶段组装函数"
```

---

### Task 5: RAGAnswerGenerator(answer.py)

**Files:**
- Create: `app/knowledge/answer.py`
- Test: `tests/knowledge/test_answer_generator.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_answer_generator.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService
from app.knowledge.answer import RAGAnswerGenerator
from app.knowledge.prompts import build_system_prompt


class _FakeLLM:
    """模拟 SOPLLMClient.chat_structured:单阶段返回带 [1] 的 answer。"""
    provider = "fake"

    def chat_structured(self, system_prompt, user_prompt, **kw):
        return {"answer": "依据[1]可知需要加强审核。"}


class _FakeLLMTwoPhase:
    provider = "fake"
    calls = 0

    def chat_structured(self, system_prompt, user_prompt, **kw):
        self.calls += 1
        if "cite_ids" in system_prompt:
            return {"cite_ids": [1]}
        return {"answer": "依据[1]作答。"}


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_build_context_groups_by_section():
    gen = RAGAnswerGenerator()
    ctx, cites = gen.build_context([
        {"chunk_id": "a", "content": "内容安全 审核", "section": "合规", "idx": 0, "score": 0.5, "doc_title": "D"},
        {"chunk_id": "b", "content": "咖啡 烘焙", "section": "合规", "idx": 1, "score": 0.3, "doc_title": "D"},
    ])
    assert "[章节：合规]" in ctx
    assert cites[0]["index"] == 1 and cites[1]["index"] == 2
    assert cites[0]["section"] == "合规"


def test_answer_mock_returns_citations_degraded():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息", project_id="p1", title="A")
    gen = RAGAnswerGenerator(service=svc, provider="mock")
    out = gen.answer("内容安全 违规", project_id="p1")
    assert out["answer"] == ""
    assert out["citations"]
    assert out["degraded"] is True


def test_answer_with_fake_llm_returns_cited():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    gen = RAGAnswerGenerator(service=svc, llm_client=_FakeLLM())
    out = gen.answer("内容安全 违规", project_id="p1")
    assert "审核" in out["answer"]
    assert out["citations"]
    assert "citation_rate" in out["metrics"]


def test_two_phase_only_cites_plan():
    svc = _tmp_service()
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    fake = _FakeLLMTwoPhase()
    gen = RAGAnswerGenerator(service=svc, llm_client=fake, two_phase=True)
    out = gen.answer("内容安全 违规", project_id="p1")
    assert "[1]" in out["answer"]
    assert fake.calls == 2


def test_validate_citations_strips_invalid():
    gen = RAGAnswerGenerator()
    cleaned, rate = gen.validate_citations(
        "依据[1]和[9]处理", [{"index": 1}, {"index": 2}])
    assert "[9]" not in cleaned
    assert "[1]" in cleaned
    assert rate == 0.5
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_answer_generator.py -v`
Expected: FAIL(`ModuleNotFoundError: app.knowledge.answer`)。

- [ ] **Step 3: 创建 `app/knowledge/answer.py`**

```python
"""RAG 答案生成器:检索 → 分节上下文 → 多厂商 LLM 生成带 [n] 引用 → 引用校验。"""
from __future__ import annotations
import logging
import re
from typing import List, Optional

from app.core.config import settings
from app.knowledge.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_citation_plan_prompt,
    build_answer_prompt,
)

logger = logging.getLogger(__name__)


class RAGAnswerGenerator:
    def __init__(
        self,
        provider: Optional[str] = None,
        service=None,
        llm_client=None,
        keys: Optional[List[str]] = None,
        two_phase: bool = False,
    ):
        self.provider = (provider or settings.RAG_LLM_PROVIDER or "mock").lower()
        self.service = service
        self._llm_client = llm_client
        self.keys = keys or list(getattr(settings, "RAG_LLM_KEYS", []) or [])
        self.two_phase = two_phase or bool(getattr(settings, "RAG_TWO_PHASE", False))

    def _get_llm(self):
        if self._llm_client is None:
            from app.services.sop_llm_client import SOPLLMClient
            self._llm_client = SOPLLMClient(self.provider, keys=self.keys)
        return self._llm_client

    def _get_service(self):
        if self.service is None:
            from app.knowledge.service import KnowledgeService
            self.service = KnowledgeService()
        return self.service

    def build_context(self, chunks: List[dict]):
        grouped = {}
        order = []
        for ch in chunks:
            sec = ch.get("section") or "未分节"
            if sec not in grouped:
                grouped[sec] = []
                order.append(sec)
            grouped[sec].append(ch)
        parts = []
        citations = []
        idx = 0
        for sec in order:
            parts.append(f"[章节：{sec}]")
            for ch in grouped[sec]:
                idx += 1
                snippet = (ch.get("content") or "")[:200]
                parts.append(f"[{idx}] {snippet}")
                citations.append({
                    "index": idx,
                    "chunk_id": ch.get("chunk_id"),
                    "doc_title": ch.get("doc_title"),
                    "section": sec,
                    "offset": ch.get("idx", 0),
                    "score": ch.get("score", 0.0),
                    "snippet": snippet,
                })
        return "\n\n".join(parts), citations

    def validate_citations(self, answer_text: str, citations: List[dict]):
        valid_ids = {c["index"] for c in citations}
        found = re.findall(r"\[(\d+)\]", answer_text or "")
        total = len(found)
        valid = 0
        cleaned = answer_text
        for n_str in found:
            n = int(n_str)
            if n in valid_ids:
                valid += 1
            else:
                cleaned = cleaned.replace(f"[{n}]", "")
        rate = (valid / total) if total else 0.0
        return cleaned, rate

    def answer(self, question: str, project_id: Optional[str] = None, top_k: int = 5) -> dict:
        chunks = self._get_service().retrieve(question, top_k=top_k, project_id=project_id)
        if not chunks:
            return {"answer": "", "citations": [], "degraded": True, "note": "未检索到相关知识"}
        context, citations = self.build_context(chunks)
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("RAG LLM 不可用,降级: %s", e)
            return {"answer": "", "citations": citations, "degraded": True, "note": "无可用模型"}
        if getattr(llm, "provider", "mock") == "mock":
            return {"answer": "", "citations": citations, "degraded": True, "note": "未生成答案(无可用模型)"}
        try:
            if self.two_phase:
                plan = llm.chat_structured(build_citation_plan_prompt(question, context), question) or {}
                cite_ids = plan.get("cite_ids", []) if isinstance(plan, dict) else []
                raw = llm.chat_structured(build_answer_prompt(question, context, cite_ids), question)
            else:
                raw = llm.chat_structured(build_system_prompt(), build_user_prompt(question, context))
            data = raw or {}
            answer_text = data.get("answer", "")
            if not answer_text:
                return {"answer": "", "citations": citations, "degraded": True, "note": "模型未返回答案"}
            cleaned, rate = self.validate_citations(answer_text, citations)
            return {"answer": cleaned, "citations": citations, "metrics": {"citation_rate": rate}}
        except Exception as e:
            logger.warning("RAG 答案生成失败,降级: %s", e)
            return {"answer": "", "citations": citations, "degraded": True, "note": "生成失败,仅返回检索上下文"}
```

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_answer_generator.py -v`
Expected: 5 passed。

- [ ] **Step 5: 提交**
```bash
git add app/knowledge/answer.py tests/knowledge/test_answer_generator.py
git commit -m "feat(knowledge): RAGAnswerGenerator 分节注入+引用校验+两阶段"
```

---

### Task 6: RAGEvaluator(eval.py)

**Files:**
- Create: `app/knowledge/eval.py`
- Test: `tests/knowledge/test_eval.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_eval.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.service import KnowledgeService
from app.knowledge.eval import RAGEvaluator


def _tmp_service():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_eval_builtin_gold_metrics():
    svc = _tmp_service()
    doc_id = svc.ingest("内容安全平台 过滤 违规 信息 审核 流程", project_id="p1", title="安全制度")
    # 取该 doc 的某个 chunk_id 作为 expected
    rows = svc.repo._execute(
        "SELECT id FROM knowledge_chunks WHERE doc_id=?", (doc_id,)).fetchall()
    expected = [r["id"] for r in rows]
    gold = [{"query": "内容安全 违规", "expected_chunk_ids": expected}]
    ev = RAGEvaluator()
    m = ev.evaluate(svc, gold, top_k=5)
    assert m["n"] == 1
    assert m["precision@k"] >= 0.0
    assert m["recall@k"] == 1.0  # 期望块都在 top-k 内


def test_eval_empty_gold_raises():
    import pytest
    ev = RAGEvaluator()
    with pytest.raises(ValueError):
        ev.evaluate(_tmp_service(), [], top_k=5)


def test_load_gold_rejects_bad_structure():
    import pytest
    ev = RAGEvaluator()
    with pytest.raises(ValueError):
        ev.load_gold([{"expected_chunk_ids": ["x"]}])  # 缺 query
```

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_eval.py -v`
Expected: FAIL(`ModuleNotFoundError: app.knowledge.eval`)。

- [ ] **Step 3: 创建 `app/knowledge/eval.py`**

```python
"""RAG 质量评估:对 gold Q&A 算 precision@k / recall@k;可选 faithfulness。"""
from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class RAGEvaluator:
    DEFAULT_GOLD: List[dict] = [
        {"query": "内容安全 违规", "expected_chunk_ids": []},
        {"query": "咖啡 烘焙", "expected_chunk_ids": []},
        {"query": "用户反馈 投诉", "expected_chunk_ids": []},
    ]

    def load_gold(self, payload) -> List[dict]:
        if not isinstance(payload, list):
            raise ValueError("gold 必须是列表")
        for item in payload:
            if not isinstance(item, dict) or not item.get("query"):
                raise ValueError("gold 每项需含非空 query")
        return payload

    def evaluate(self, service, gold=None, top_k: int = 5,
                 project_id: Optional[str] = None, with_faithfulness: bool = False) -> dict:
        gold = self.load_gold(gold if gold is not None else self.DEFAULT_GOLD)
        if not gold:
            raise ValueError("gold 为空")
        per_item = []
        p_sum = r_sum = 0.0
        for item in gold:
            retrieved = service.retrieve(item["query"], top_k=top_k, project_id=project_id)
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
                    out = gen.answer(item["query"], project_id=project_id, top_k=top_k)
                    entry["faithfulness"] = out.get("metrics", {}).get("citation_rate", None)
                except Exception as e:
                    logger.warning("faithfulness 计算失败: %s", e)
                    entry["faithfulness"] = None
            per_item.append(entry)
            p_sum += precision
            r_sum += recall
        n = len(per_item)
        result = {
            "precision@k": round(p_sum / n, 4) if n else 0.0,
            "recall@k": round(r_sum / n, 4) if n else 0.0,
            "n": n,
            "per_item": per_item,
        }
        return result
```

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_eval.py -v`
Expected: 3 passed。

- [ ] **Step 5: 提交**
```bash
git add app/knowledge/eval.py tests/knowledge/test_eval.py
git commit -m "feat(knowledge): RAGEvaluator 引标评估 precision@k/recall@k"
```

---

### Task 7: knowledge_api 新增 /ask 与 /evaluate

**Files:**
- Modify: `app/api/knowledge_api.py`(新增两个端点 + 请求模型)
- Test: `tests/knowledge/test_api_ask_eval.py`(集成,用 TestClient 或_requests_)

- [ ] **Step 1: 写失败测试**

新建 `tests/knowledge/test_api_ask_eval.py`:
```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from app.main import app  # 若 main 暴露 app;否则用 app.api.knowledge_api.router 组装
from app.knowledge.service import KnowledgeService


def _client_with_tmp_db():
    # 用临时库初始化一个 KnowledgeService 并写入样例,再对 /knowledge/ask 发请求
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    svc = KnowledgeService(db_path=f.name)
    svc.ingest("内容安全平台 过滤 违规 信息 审核", project_id="p1", title="A")
    return svc


def test_ask_endpoint_returns_citations():
    svc = _client_with_tmp_db()
    # 直接调用 generator(走真实端点的集成需 app 装配,此处验证行为等价)
    from app.knowledge.answer import RAGAnswerGenerator
    out = RAGAnswerGenerator(service=svc, provider="mock").answer("内容安全 违规", project_id="p1")
    assert out["degraded"] is True
    assert out["citations"]


def test_evaluate_endpoint_structure():
    from app.knowledge.eval import RAGEvaluator
    svc = _client_with_tmp_db()
    m = RAGEvaluator().evaluate(svc, [{"query": "内容安全 违规", "expected_chunk_ids": []}], top_k=5)
    assert "precision@k" in m and "recall@k" in m and m["n"] == 1
```

注:若项目用 TestClient 直接打 `/knowledge/ask` 需要 app 装配且 DB 路径一致,集成测试以 generator/evaluator 直调方式验证行为(等价),避免全局 DB 耦合。

- [ ] **Step 2: 运行确认 FAIL**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_ask_eval.py -v`
Expected: 测试存在但行为待接入端点后稳定(本步先确认可导入/结构)。

- [ ] **Step 3: 修改 `app/api/knowledge_api.py`**

在 `RetrieveRequest` 之后新增:
```python
class AskRequest(BaseModel):
    question: str
    project_id: str = ""
    top_k: int = 5


class EvaluateRequest(BaseModel):
    gold: Optional[List[dict]] = None
    top_k: int = 5
    with_faithfulness: bool = False
```

在 `delete_document` 端点之前新增:
```python
@router.post("/ask")
def ask(req: AskRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    if not req.question or not req.question.strip():
        return ApiResponse.error("请提供问题", code=400)
    from app.knowledge.answer import RAGAnswerGenerator
    gen = RAGAnswerGenerator(service=service)
    result = gen.answer(req.question, project_id=req.project_id or None, top_k=req.top_k)
    return ApiResponse.ok(result)


@router.post("/evaluate")
def evaluate(req: EvaluateRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    from app.knowledge.eval import RAGEvaluator
    try:
        gold = req.gold if req.gold else RAGEvaluator.DEFAULT_GOLD
        if not gold:
            return ApiResponse.error("gold 为空", code=400)
        ev = RAGEvaluator()
        metrics = ev.evaluate(service, gold, top_k=req.top_k, with_faithfulness=req.with_faithfulness)
        return ApiResponse.ok(metrics)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)
```
(顶部 `from typing import List, Optional` 已导入。)

- [ ] **Step 4: 运行确认 PASS**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest tests/knowledge/test_api_ask_eval.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**
```bash
git add app/api/knowledge_api.py tests/knowledge/test_api_ask_eval.py
git commit -m "feat(knowledge): 新增 /knowledge/ask 与 /knowledge/evaluate 端点"
```

---

### Task 8: 全量回归

**Files:** 无新文件,仅运行。

- [ ] **Step 1: 跑全量测试**
`/c/Users/34216/Documents/New project 3/bsc-backend/.venv/Scripts/python.exe -m pytest -q`
Expected: 0 failed(既有 ~285 passed 不受影响;新增约 20 例全过;真实 LLM/embedding e2e 仍为 skip)。

- [ ] **Step 2: 若失败则定位修复(改完重跑,不新增提交)**
常见风险:
- `rrf_fuse` 返回元组后,任何仍按 `List[str]` 使用的旧代码(如 test_reranker)需同步(Step 5 已处理)。
- `RAGAnswerGenerator` 的 `service=None` 时懒加载默认 `KnowledgeService()`(指向默认 DB);测试均显式传入 `service=svc` 避免跨库。
- `RAG_LLM_KEYS` 为 `List[str]`;经 pydantic-settings 从 `.env` 读取时建议用 JSON 数组形式 `RAG_LLM_KEYS='["k1","k2"]'`,测试直接赋值 `settings.RAG_LLM_KEYS`。

- [ ] **Step 3: 确认无漂移被提交**
```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git status --short | grep -vE "bsc_cloud.db|llm_service.py|dashboard.html|orphan_fork"
```
Expected: 输出为空(无未提交的非漂移改动)。

---

## 自审(Self-Review)核对

1. **Spec 覆盖**:
   - 多 Key 轮询/故障转移 → Task 2 ✅(T2 扩展 SOPLLMClient + 3 测试)
   - 接地提示词细分(五块 + 两阶段) → Task 4(prompts.py)+ Task 5(answer 接入)✅
   - 分节精准注入(build_context 按 section 归并) → Task 5 ✅
   - 引用校验(validate_citations 剔除非命中 [n] + citation_rate) → Task 5 ✅
   - RAG 问答端点 /ask → Task 7 ✅
   - 引标评估 P@k/R@k/faithfulness → Task 6(eval.py)✅ + /evaluate 端点 Task 7 ✅
   - config RAG_LLM_PROVIDER/KEYS/TWO_PHASE → Task 1 ✅
   - 全量回归 → Task 8 ✅
2. **Spec 假设修正**:原 spec 假设 `retrieve` 返回 `chunk_id/score/offset`,实际仅返回 content/section/doc_title;Task 3 显式扩展 `retrieve`(及 `rrf_fuse` 返回元组)补齐,属必要补丁,已单列任务并含测试。
3. **占位符扫描**:无 TBD/TODO;每步含完整代码与期望输出 ✅
4. **类型一致性**:
   - `RAGAnswerGenerator.__init__(provider, service, llm_client, keys, two_phase)` 在 Task 5 定义;Task 7 端点用 `RAGAnswerGenerator(service=service)`(service 注入)✅
   - `build_system_prompt()/build_user_prompt()/build_citation_plan_prompt()/build_answer_prompt()` 在 Task 4 定义,Task 5 调用签名一致 ✅
   - `RAGEvaluator.evaluate(service, gold, top_k, project_id, with_faithfulness)` 在 Task 6 定义,Task 7 调用一致 ✅
   - `rrf_fuse` 返回 `List[(cid, score)]` 在 Task 3 定义,`retrieve` 解包 `(cid, score)` 一致 ✅
5. **风险已处理**:多 Key 仅对 401/402/429 显式 continue,5xx/timeout 经 httpx.HTTPError 捕获 continue,全部耗尽抛 SOPLLMError;mock/无 key 降级 `degraded:True`;非法 [n] 剔除;eval gold 空/非法返回 400/ValueError ✅
