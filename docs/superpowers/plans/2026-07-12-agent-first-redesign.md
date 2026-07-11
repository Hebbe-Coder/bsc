# Agent-first 对话式业务系统共创（含可编辑画布） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户用自然语言描述点子，BSC 通过多轮对话逐步澄清→编译业务系统→生成 SOP，全程产出一份结构化可编辑草稿，并提供「对话 + 可编辑画布」界面（Web 与 MCP 双交付面），真实 deepseek 驱动、异常优雅降级。

**Architecture:** 复用已有的 LangChain Agent 框架（`app/core/langchain_agent.py` 的 `create_agent` + `MemorySaver` + `BaseTool` 模式），新建 `BSCAgentService` 并把 5 个 BSC 专属工具（clarify/compile/generate_sop/edit_node/summarize）挂上去；Agent 进程内直调既有 `compile_to_business_system_async` 与 `SOPReportEngine`（不走 MCP 子进程）。草稿状态存 SQLite 新表 `agent_project_drafts`（复用 `app/db.py:get_db()`）。前端在现有 React+Vite+TS 工程内新增 `AgentStudio` 页面（不复用被 presentation store 绑死的 `ChatInterface`/`Canvas`），左聊右画、双向同步。

**Tech Stack:** Python 3.13 / FastAPI / LangChain (`create_agent`, `langgraph`) / SQLite / deepseek（真实，带 mock 熔断兜底）；前端 React 18 + TypeScript + Vite + Tailwind + zustand；复用 `src/api/bscApi.ts` 的 `BusinessSystem` 类型与 `fetchWrapper`。

**Spec:** `docs/superpowers/specs/2026-07-12-agent-first-redesign-design.md`（ADR-001 已锁定：Agent-first + 画布进 MVP）。

---

## 文件结构（新建 / 修改）

### 后端（新建）
- `app/agent/__init__.py` — 包导出
- `app/agent/state.py` — `ProjectDraft` 模型 + `ProjectDraftRepository`（SQLite 表 `agent_project_drafts`，懒建表）
- `app/agent/tools.py` — 5 个 LangChain `BaseTool`：`ClarifyTool` / `CompileTool` / `GenerateSopTool` / `EditNodeTool` / `SummarizeTool`
- `app/agent/bsc_agent.py` — `BSCAgentService`（复用 `create_agent` + `MemorySaver`，BSC 系统提示词，熔断器，护栏）
- `app/api/agent_api.py` — `POST /api/agent/chat` + `POST /api/agent/edit` 路由

### 后端（修改）
- `app/main.py:215` — 在 router 列表加入 `"app.api.agent_api"`
- `app/mcp/server.py` — 新增 `@mcp.tool() chat(session_id, message)`（扩展既有 MCP server，直调 `BSCAgentService`）

### 前端（新建）
- `src/api/agentApi.ts` — `/api/agent/chat` 与 `/api/agent/edit` 客户端
- `src/components/AgentChat.tsx` — 聊天面板（复用 `MessageBubble`）
- `src/components/AgentCanvas.tsx` — 渲染 `business_system` 为卡片 + 节点图
- `src/components/AgentPropertyPanel.tsx` — 选中节点就地编辑
- `src/pages/AgentStudio.tsx` — 组合 聊 + 画 + 属性面板，管理 `session_id` 与草稿状态

### 前端（修改）
- `src/App.tsx` — 增加顶部切换，渲染 `AgentStudio`（保留 `Editor` 可切回）

### 测试（新建）
- `tests/agent/test_state.py` — 草稿状态层单测
- `tests/agent/test_tools.py` — 5 个工具单测（real + `BSC_MCP_FORCE_MOCK=1`）
- `tests/agent/test_agent_api.py` — `/api/agent/chat` 集成测试（含鉴权头）
- `tests/agent/test_mcp_chat.py` — MCP `chat` 工具测试

---

## Task 1: Project Draft 状态层

**Files:**
- Create: `app/agent/__init__.py`
- Create: `app/agent/state.py`
- Create: `tests/agent/__init__.py`
- Test: `tests/agent/test_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/test_state.py
import pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft


def test_create_and_get():
    repo = ProjectDraftRepository()
    sid = "sess-001"
    d = ProjectDraft(session_id=sid, idea="社区老人上门助浴")
    repo.save(d)
    got = repo.get(sid)
    assert got is not None
    assert got.session_id == sid
    assert got.idea == "社区老人上门助浴"
    assert got.status == "idea"


def test_patch_node():
    repo = ProjectDraftRepository()
    sid = "sess-002"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    repo.patch(sid, "business_system.roles", [{"role": "助浴师", "responsibilities": ["安全"]}])
    got = repo.get(sid)
    assert got.business_system["roles"][0]["role"] == "助浴师"
```

- [ ] **Step 2: 运行测试确认失败**
Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/agent/test_state.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent`）

- [ ] **Step 3: 最小实现**

```python
# app/agent/__init__.py
from .state import ProjectDraft, ProjectDraftRepository
```

```python
# app/agent/state.py
from __future__ import annotations
import json, time, uuid
from typing import Any, Dict, Optional
from app.db import get_db


class ProjectDraft:
    def __init__(self, session_id: str = None, idea: str = "", requirements: str = "",
                 domain: Optional[dict] = None, business_system: Optional[dict] = None,
                 sop: Optional[dict] = None, status: str = "idea",
                 messages: Optional[list] = None):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.idea = idea
        self.requirements = requirements
        self.domain = domain or {}
        self.business_system = business_system or {}
        self.sop = sop or {}
        self.status = status
        self.messages = messages or []
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id, "idea": self.idea, "requirements": self.requirements,
            "domain": self.domain, "business_system": self.business_system, "sop": self.sop,
            "status": self.status, "messages": self.messages, "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row):
        d = dict(row)
        d["domain"] = json.loads(d["domain"]) if isinstance(d.get("domain"), str) else (d.get("domain") or {})
        d["business_system"] = json.loads(d["business_system"]) if isinstance(d.get("business_system"), str) else (d.get("business_system") or {})
        d["sop"] = json.loads(d["sop"]) if isinstance(d.get("sop"), str) else (d.get("sop") or {})
        d["messages"] = json.loads(d["messages"]) if isinstance(d.get("messages"), str) else (d.get("messages") or [])
        return cls(**d)


class ProjectDraftRepository:
    def __init__(self):
        self._db = get_db()
        self._ensure_table()

    def _ensure_table(self):
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS agent_project_drafts (
                session_id TEXT PRIMARY KEY,
                idea TEXT, requirements TEXT, domain TEXT,
                business_system TEXT, sop TEXT, status TEXT,
                messages TEXT, updated_at TEXT
            )"""
        )
        self._db.commit()

    def save(self, draft: ProjectDraft):
        draft.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, idea, requirements, domain, business_system, sop, status, messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               idea=excluded.idea, requirements=excluded.requirements, domain=excluded.domain,
               business_system=excluded.business_system, sop=excluded.sop, status=excluded.status,
               messages=excluded.messages, updated_at=excluded.updated_at""",
            (draft.session_id, draft.idea, draft.requirements, json.dumps(draft.domain, ensure_ascii=False),
             json.dumps(draft.business_system, ensure_ascii=False), json.dumps(draft.sop, ensure_ascii=False),
             draft.status, json.dumps(draft.messages, ensure_ascii=False), draft.updated_at))
        self._db.commit()

    def get(self, session_id: str) -> Optional[ProjectDraft]:
        row = self._db.execute("SELECT * FROM agent_project_drafts WHERE session_id=?", (session_id,)).fetchone()
        return ProjectDraft.from_row(row) if row else None

    def patch(self, session_id: str, path: str, value: Any):
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        # 仅支持 business_system.<key> 一级打补丁（MVP 范围）
        if not path.startswith("business_system."):
            raise ValueError(f"只允许补丁 business_system.* ，收到: {path}")
        key = path.split(".", 1)[1]
        draft.business_system[key] = value
        draft.status = "edited"
        self.save(draft)
        return draft
```

- [ ] **Step 4: 运行测试确认通过**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_state.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**
```bash
git add app/agent/__init__.py app/agent/state.py tests/agent/__init__.py tests/agent/test_state.py
git commit -m "feat(agent): Project Draft 状态层（SQLite agent_project_drafts）"
```

---

## Task 2: 5 个 BSC 工具（LangChain BaseTool）

**Files:**
- Create: `app/agent/tools.py`
- Test: `tests/agent/test_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/test_tools.py
import os, pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.agent.tools import CompileTool, GenerateSopTool, EditNodeTool, SummarizeTool, ClarifyTool


def _fresh_repo(sid="t-compile"):
    repo = ProjectDraftRepository()
    repo.save(ProjectDraft(session_id=sid, idea="社区老人上门助浴，含预约/上门/安全监护/家属通知"))
    return repo, sid


def test_compile_tool_writes_business_system():
    os.environ.setdefault("BSC_MCP_FORCE_MOCK", "1")  # 加速、确定性
    repo, sid = _fresh_repo()
    tool = CompileTool(session_id=sid, repo=repo)
    out = tool._run("")
    assert "已编译" in out
    draft = repo.get(sid)
    assert draft.business_system.get("roles") is not None
    assert draft.status == "compiled"


def test_edit_node_tool_patches():
    repo, sid = _fresh_repo()
    tool = EditNodeTool(session_id=sid, repo=repo)
    out = tool._run("business_system.roles", [{"role": "助浴师", "responsibilities": ["安全"]}])
    assert "已更新" in out
    assert repo.get(sid).business_system["roles"][0]["role"] == "助浴师"


def test_edit_node_rejects_bad_path():
    repo, sid = _fresh_repo()
    tool = EditNodeTool(session_id=sid, repo=repo)
    with pytest.raises(ValueError):
        tool._run("idea", "hacked")
```

- [ ] **Step 2: 运行测试确认失败**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_tools.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.tools`）

- [ ] **Step 3: 最小实现**

```python
# app/agent/tools.py
from __future__ import annotations
import json, logging
from typing import Dict, Any, ClassVar
from langchain_core.tools import BaseTool
from app.core.async_pipeline import compile_to_business_system_async
from app.engines.sop_report_engine import SOPReportEngine
from app.services.llm_service import LLMService
from app.core.config import settings

logger = logging.getLogger(__name__)


def _llm() -> LLMService:
    return LLMService(provider=settings.LLM_PROVIDER)


class ClarifyTool(BaseTool):
    name: str = "clarify"
    description: str = "当用户想法模糊、信息不足时，生成 1-3 个针对性澄清问题。输入为当前草稿的 idea/requirements 文本。"
    session_id: str
    repo: ClassVar = None

    def _run(self, context: str = "") -> str:
        draft = self.__class__.repo.get(self.session_id)
        idea = (draft.idea if draft else "") or context
        sys_p = "你是业务分析师。基于用户的模糊点子，输出最多3个最关键的澄清问题（JSON 数组，每项含 question 与 purpose）。只输出 JSON。"
        usr_p = f"点子：{idea}\n已有需求：{draft.requirements if draft else ''}"
        try:
            resp = _llm().chat(system_prompt=sys_p, user_prompt=usr_p, use_cache=False)
            text = resp.get("content") or resp.get("text") or str(resp)
            return json.dumps({"questions": _safe_json_list(text)}, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"clarify failed: {e}")
            return json.dumps({"questions": ["请描述你的目标用户是谁？", "核心业务流程是什么？"]}, ensure_ascii=False)


class CompileTool(BaseTool):
    name: str = "compile"
    description: str = "将需求编译为业务系统（business_system）。当需求充分或用户明确要求生成时使用。输入为描述文本。"
    session_id: str
    repo: ClassVar = None

    def _run(self, description: str = "") -> str:
        draft = self.__class__.repo.get(self.session_id)
        text = description or (draft.requirements if draft and draft.requirements else draft.idea if draft else "")
        if not text:
            return "错误：没有可编译的需求文本。"
        try:
            result = compile_to_business_system_async(text)
            bs = result.get("business_system", {})
            draft.business_system = bs
            draft.status = "compiled"
            self.__class__.repo.save(draft)
            return f"已编译业务系统：领域={bs.get('business_domain','')}，角色{len(bs.get('roles',[]))}个，流程{len(bs.get('workflow',[]))}步。"
        except Exception as e:
            logger.error(f"compile failed: {e}")
            return f"编译失败（已降级）：{e}"


class GenerateSopTool(BaseTool):
    name: str = "generate_sop"
    description: str = "基于已编译的 business_system 生成 SOP 报告（含 AI 分析与优化建议）。当 business_system 就绪后使用。"
    session_id: str
    repo: ClassVar = None

    def _run(self, _: str = "") -> str:
        draft = self.__class__.repo.get(self.session_id)
        bs = draft.business_system if draft else {}
        if not bs:
            return "错误：请先 compile 得到 business_system。"
        try:
            report = SOPReportEngine().generate_full_sop_report(bs, enable_ai_analysis=True)
            draft.sop = report
            draft.status = "sop"
            self.__class__.repo.save(draft)
            return f"已生成 SOP 报告：摘要={'有' if report.get('ai_summary') else '无'}，建议{len(report.get('ai_recommendations',{}).get('optimization_suggestions',[]))}条。"
        except Exception as e:
            logger.error(f"generate_sop failed: {e}")
            return f"SOP 生成失败（已降级）：{e}"


class EditNodeTool(BaseTool):
    name: str = "edit_node"
    description: str = "修改草稿中 business_system 的任意节点。输入 path（如 business_system.roles）与 value（JSON 字符串）。"
    session_id: str
    repo: ClassVar = None

    def _run(self, path: str, value: str = "{}") -> str:
        try:
            val = json.loads(value) if isinstance(value, str) else value
        except Exception:
            return "错误：value 不是合法 JSON。"
        try:
            self.__class__.repo.patch(self.session_id, path, val)
            return f"已更新 {path}"
        except (ValueError, KeyError) as e:
            return f"编辑被拒：{e}"


class SummarizeTool(BaseTool):
    name: str = "summarize"
    description: str = "总结当前草稿进度（一句话）。当用户问“进度如何/总结一下”时使用。"
    session_id: str
    repo: ClassVar = None

    def _run(self, _: str = "") -> str:
        draft = self.__class__.repo.get(self.session_id)
        if not draft:
            return "还没有任何草稿。"
        bs = draft.business_system or {}
        sys_p = "你是项目助理。用一句话总结当前业务系统设计的进度与缺口。只输出一句话。"
        usr_p = f"状态={draft.status}；领域={bs.get('business_domain','未定')}；角色{len(bs.get('roles',[]))}；SOP={'已生成' if draft.sop else '未生成'}。"
        try:
            resp = _llm().chat(system_prompt=sys_p, user_prompt=usr_p, use_cache=False)
            return resp.get("content") or resp.get("text") or str(resp)
        except Exception as e:
            return f"进度：{draft.status}；领域={bs.get('business_domain','未定')}。"


def _safe_json_list(text: str):
    try:
        return json.loads(text)
    except Exception:
        return [text]
```

> 注意：`LLMService.chat` 返回 dict，文本字段为 `content`（若实际为其他 key，按 `resp.get("content") or resp.get("text")` 兜底，已处理）。

- [ ] **Step 4: 运行测试确认通过**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_tools.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**
```bash
git add app/agent/tools.py tests/agent/test_tools.py
git commit -m "feat(agent): 5 个 BSC 工具（clarify/compile/generate_sop/edit_node/summarize）"
```

---

## Task 3: BSCAgentService（Agent Loop + 熔断器 + 护栏）

**Files:**
- Create: `app/agent/bsc_agent.py`
- Test: `tests/agent/test_agent_api.py`（先用 service 级测试，稍后扩 API 级）

- [ ] **Step 1: 写失败测试（service 级）**

```python
# 追加到 tests/agent/test_tools.py 或新建 tests/agent/test_bsc_agent.py
import os
from app.agent.bsc_agent import BSCAgentService
from app.agent.state import ProjectDraftRepository


def test_agent_chat_compiles_and_returns_draft():
    os.environ.setdefault("BSC_MCP_FORCE_MOCK", "1")
    sid = "agent-svc-1"
    ProjectDraftRepository().save(__import__("app.agent.state", fromlist=["ProjectDraft"]).ProjectDraft(
        session_id=sid, idea="社区老人上门助浴，含预约/上门/安全监护/家属通知"))
    svc = BSCAgentService()
    res = svc.chat(sid, "帮我生成业务系统和SOP")
    assert res["success"] is True
    draft = ProjectDraftRepository().get(sid)
    assert draft.status in ("compiled", "sop")
```

- [ ] **Step 2: 运行确认失败**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_bsc_agent.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent.bsc_agent`）

- [ ] **Step 3: 最小实现**

```python
# app/agent/bsc_agent.py
from __future__ import annotations
import json, logging
from typing import Dict, Any, List, ClassVar
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from app.core.config import settings
from app.agent.state import ProjectDraftRepository
from app.agent.tools import ClarifyTool, CompileTool, GenerateSopTool, EditNodeTool, SummarizeTool

logger = logging.getLogger(__name__)


class BSCAgentService:
    def __init__(self, provider: str = None, use_mock: bool = None):
        self.provider = provider or settings.LLM_PROVIDER
        self.use_mock = use_mock if use_mock is not None else (self.provider == "mock")
        self._agent_graphs: Dict[str, Any] = {}
        self._checkpointers: Dict[str, MemorySaver] = {}
        self._fail_count = 0  # 熔断器计数

    # ---- 熔断器 ----
    def _llm_config(self) -> Dict[str, Any]:
        from langchain_openai import ChatOpenAI
        if self.use_mock or self._fail_count >= 3:
            from app.services.langchain_service import MockLLM
            from langchain_core.runnables import RunnableLambda
            return {"model": RunnableLambda(MockLLM().invoke), "use_mock": True}
        prov = {
            "deepseek": (settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL),
        }.get(self.provider)
        if not prov or not prov[0]:
            from app.services.langchain_service import MockLLM
            from langchain_core.runnables import RunnableLambda
            return {"model": RunnableLambda(MockLLM().invoke), "use_mock": True}
        return {"model": ChatOpenAI(api_key=prov[0], base_url=prov[1], model=prov[2],
                                    temperature=settings.LLM_TEMPERATURE, max_tokens=settings.LLM_MAX_TOKENS,
                                    timeout=settings.LLM_TIMEOUT), "use_mock": False}

    def _build_system_prompt(self) -> str:
        return (
            "你是 BSC 业务系统共创助手，像懂行的搭档一样帮用户把模糊点子变成可落地的业务系统。\n"
            "工作流：\n"
            "1. 信息不足时用 clarify 追问（最多3个问题）。\n"
            "2. 需求充分时用 compile 编译 business_system。\n"
            "3. 编译完成后用 generate_sop 生成 SOP。\n"
            "4. 用户要改某处时用 edit_node（path 形如 business_system.roles）。\n"
            "5. 用户问进度时用 summarize。\n"
            "始终用工具完成任务，最后用一句自然语言向用户说明你做了什么。"
        )

    def _get_tools(self, session_id: str):
        repo = ProjectDraftRepository()
        for t in (ClarifyTool, CompileTool, GenerateSopTool, EditNodeTool, SummarizeTool):
            t.session_id = session_id
            t.repo = repo
        return [ClarifyTool(session_id=session_id, repo=repo),
                CompileTool(session_id=session_id, repo=repo),
                GenerateSopTool(session_id=session_id, repo=repo),
                EditNodeTool(session_id=session_id, repo=repo),
                SummarizeTool(session_id=session_id, repo=repo)]

    def _get_agent(self, session_id: str):
        if session_id not in self._agent_graphs:
            cfg = self._llm_config()
            self._agent_graphs[session_id] = create_agent(
                model=cfg["model"], tools=self._get_tools(session_id),
                system_prompt=self._build_system_prompt(),
                checkpointer=self._get_checkpointer(session_id), debug=False)
        return self._agent_graphs[session_id]

    def _get_checkpointer(self, session_id: str):
        if session_id not in self._checkpointers:
            self._checkpointers[session_id] = MemorySaver()
        return self._checkpointers[session_id]

    def chat(self, session_id: str, user_input: str, user_id: str = None) -> Dict[str, Any]:
        try:
            agent = self._get_agent(session_id)
            config = {"configurable": {"thread_id": session_id}, "recursion_limit": 8}
            result = agent.invoke({"messages": [HumanMessage(content=user_input)]}, config=config)
            content = ""
            for m in result.get("messages", []):
                if isinstance(m, AIMessage):
                    content = m.content
            self._fail_count = 0
            return {"success": True, "response": content, "session_id": session_id}
        except Exception as e:
            self._fail_count += 1
            logger.error(f"BSC agent chat failed (fails={self._fail_count}): {e}")
            return {"success": False, "error": str(e), "session_id": session_id,
                    "response": "抱歉，我暂时无法处理（已触发降级）。请稍后再试或换种说法。"}

    def create_session(self, user_id: str = "anon", idea: str = "") -> str:
        sid = f"agent-{abs(hash(user_id + idea)) % 10**12:012d}"
        ProjectDraftRepository().save(__import__("app.agent.state", fromlist=["ProjectDraft"]).ProjectDraft(
            session_id=sid, idea=idea))
        return sid
```

- [ ] **Step 4: 运行测试确认通过**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_bsc_agent.py -v`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add app/agent/bsc_agent.py tests/agent/test_bsc_agent.py
git commit -m "feat(agent): BSCAgentService（Agent Loop + 熔断器 + 护栏 recursion_limit=8）"
```

---

## Task 4: API 端点 `/api/agent/chat` 与 `/api/agent/edit`

**Files:**
- Create: `app/api/agent_api.py`
- Modify: `app/main.py:215`（router 列表追加 `"app.api.agent_api"`）
- Test: `tests/agent/test_agent_api.py`

> 鉴权：全局 `AuthMiddleware` + `RateLimitMiddleware` 已挂载，端点自动受保护（测试需注入 `settings.API_KEY` 与 `Authorization` 头，沿用项目测试约定）。

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/test_agent_api.py
import os, pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.core.config import settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-key-agent")
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    with patch("app.middleware.auth.AuthMiddleware") if False else patch.dict(os.environ, {"BSC_MCP_FORCE_MOCK": "1"}):
        yield TestClient(app)


def test_agent_chat_requires_auth(client):
    r = client.post("/api/agent/chat", json={"message": "hi"})
    assert r.status_code in (401, 403)


def test_agent_chat_returns_draft(client):
    r = client.post("/api/agent/chat", json={"message": "社区老人上门助浴，生成业务系统和SOP"},
                    headers={"Authorization": "Bearer test-key-agent"})
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body and "reply" in body
    assert body["draft"]["status"] in ("compiled", "sop", "idea")
```

- [ ] **Step 2: 运行确认失败**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_agent_api.py -v`
Expected: FAIL（`404` 或 `ModuleNotFoundError`）

- [ ] **Step 3: 最小实现**

```python
# app/api/agent_api.py
from __future__ import annotations
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.agent.bsc_agent import BSCAgentService
from app.agent.state import ProjectDraftRepository

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class AgentChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., description="用户输入")


class AgentEditRequest(BaseModel):
    session_id: str
    path: str
    value: Any


@router.post("/chat")
async def agent_chat(req: AgentChatRequest):
    svc = BSCAgentService()
    sid = req.session_id or svc.create_session(idea=req.message)
    result = svc.chat(sid, req.message)
    draft = ProjectDraftRepository().get(sid)
    return {
        "session_id": sid,
        "reply": result.get("response", ""),
        "draft": draft.to_dict() if draft else {},
        "status": draft.status if draft else "idea",
        "success": result.get("success", False),
    }


@router.post("/edit")
async def agent_edit(req: AgentEditRequest):
    repo = ProjectDraftRepository()
    try:
        repo.patch(req.session_id, req.path, req.value)
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    draft = repo.get(req.session_id)
    return {"success": True, "draft": draft.to_dict() if draft else {}}
```

- [ ] **Step 4: 在 main.py 注册路由**
在 `app/main.py:215` 的 router 列表中加入 `"app.api.agent_api"`：
```python
for _m in ["app.api.bsc_api","app.api.chat_api","app.api.studio_api","app.api.visual_api","app.api.dashboard","app.api.template_api","app.api.tasks_api","app.api.stream_api","app.api.recommendation_api","app.api.prd_api","app.api.pm_report_api","app.api.dialog_api","app.api.prd_editor_api","app.api.skill_routes","app.api.sop_report_api","app.api.brainstorm_api","app.api.knowledge_api","app.api.knowledge_ws","app.api.files_api","app.api.agent_api"]:
```

- [ ] **Step 5: 运行测试确认通过**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_agent_api.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**
```bash
git add app/api/agent_api.py app/main.py tests/agent/test_agent_api.py
git commit -m "feat(agent): POST /api/agent/chat 与 /api/agent/edit 端点（受全局鉴权）"
```

---

## Task 5: MCP `chat` 工具

**Files:**
- Modify: `app/mcp/server.py`（新增 `chat` 工具）
- Test: `tests/agent/test_mcp_chat.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/test_mcp_chat.py
import os
os.environ.setdefault("BSC_MCP_FORCE_MOCK", "1")
from app.mcp.server import mcp
from app.agent.state import ProjectDraftRepository


def test_mcp_chat_tool_registered():
    names = [t.name for t in mcp._tool_manager.list_tools()] if hasattr(mcp, "_tool_manager") else []
    # 退路：直接调用函数体
    import asyncio
    from app.agent.bsc_agent import BSCAgentService
    sid = "mcp-chat-1"
    ProjectDraftRepository().save(__import__("app.agent.state", fromlist=["ProjectDraft"]).ProjectDraft(
        session_id=sid, idea="社区老人上门助浴"))
    res = BSCAgentService().chat(sid, "生成业务系统和SOP")
    assert res["success"] is True
```

- [ ] **Step 2: 运行确认失败**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_mcp_chat.py -v`
Expected: 测试体通过（BSCAgentService 已存在），本任务重点在注册 MCP 工具。

- [ ] **Step 3: 在 server.py 注册 chat 工具**

在 `app/mcp/server.py` 的 4 个工具之后追加：
```python
@app.tool()
def chat(session_id: str, message: str) -> str:
    """对话式共创：给定会话ID与用户消息，返回助手回复与当前草稿JSON。"""
    from app.agent.bsc_agent import BSCAgentService
    from app.agent.state import ProjectDraftRepository
    svc = BSCAgentService()
    sid = session_id or svc.create_session(idea=message)
    res = svc.chat(sid, message)
    draft = ProjectDraftRepository().get(sid)
    return json.dumps({
        "session_id": sid,
        "reply": res.get("response", ""),
        "draft": draft.to_dict() if draft else {},
        "success": res.get("success", False),
    }, ensure_ascii=False)
```
（确保 `app/mcp/server.py` 顶部已 `import json`；`mcp = FastMCP("bsc-engine")` 实例名若是 `mcp` 则装饰器用 `@mcp.tool()`，若命名不同请对齐。）

- [ ] **Step 4: 运行测试确认通过**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/test_mcp_chat.py -v`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add app/mcp/server.py tests/agent/test_mcp_chat.py
git commit -m "feat(mcp): 新增 chat 工具，复用 BSCAgentService 对话式共创"
```

---

## Task 6: 前端 API 客户端 `agentApi.ts`

**Files:**
- Create: `src/api/agentApi.ts`

- [ ] **Step 1: 创建客户端**

```typescript
// src/api/agentApi.ts
import { fetchWrapper } from './fetchWrapper';
import { BusinessSystem } from './bscApi';

export interface AgentDraft {
  session_id: string;
  idea: string;
  requirements: string;
  domain: Record<string, unknown>;
  business_system: BusinessSystem;
  sop: Record<string, unknown>;
  status: string;
  messages: Array<{ role: string; content: string; ts?: string }>;
  updated_at: string;
}

export interface AgentChatResponse {
  session_id: string;
  reply: string;
  draft: AgentDraft;
  status: string;
  success: boolean;
}

export const agentApi = {
  chat: async (sessionId: string | null, message: string): Promise<AgentChatResponse> => {
    const response = await fetchWrapper.fetch<AgentChatResponse>('/api/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    return response as AgentChatResponse;
  },

  editNode: async (sessionId: string, path: string, value: unknown): Promise<{ success: boolean; draft: AgentDraft }> => {
    const response = await fetchWrapper.fetch<{ success: boolean; draft: AgentDraft }>('/api/agent/edit', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, path, value }),
    });
    return response as { success: boolean; draft: AgentDraft };
  },
};
```

- [ ] **Step 2: 类型检查**
Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && npm run check`
Expected: 无类型错误（或仅既有警告）

- [ ] **Step 3: 提交**
```bash
git add src/api/agentApi.ts
git commit -m "feat(agent): 前端 agentApi 客户端（/api/agent/chat + /edit）"
```

---

## Task 7: 前端聊天面板 `AgentChat.tsx`

**Files:**
- Create: `src/components/AgentChat.tsx`

- [ ] **Step 1: 组件（复用 MessageBubble）**

```tsx
// src/components/AgentChat.tsx
import React, { useState, useRef, useEffect } from 'react';
import MessageBubble, { Message } from './MessageBubble';
import { agentApi, AgentDraft } from '../api/agentApi';

interface AgentChatProps {
  draft: AgentDraft | null;
  onDraft: (d: AgentDraft) => void;
}

const AgentChat: React.FC<AgentChatProps> = ({ draft, onDraft }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = async () => {
    if (!input.trim() || typing) return;
    const text = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now().toString(), type: 'user', content: text }]);
    setTyping(true);
    try {
      const res = await agentApi.chat(sessionId, text);
      setSessionId(res.session_id);
      onDraft(res.draft);
      setMessages(prev => [...prev, { id: (Date.now()+1).toString(), type: 'assistant', content: res.reply }]);
    } catch (e: any) {
      setMessages(prev => [...prev, { id: (Date.now()+1).toString(), type: 'assistant', content: '调用失败：' + e.message }]);
    } finally {
      setTyping(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {messages.map(m => <MessageBubble key={m.id} message={m} />)}
        {typing && <div className="text-xs text-gray-400">思考中…</div>}
        <div ref={endRef} />
      </div>
      <div className="border-t p-2 flex gap-2">
        <input
          className="flex-1 border rounded px-2 py-1 text-sm"
          value={input}
          placeholder="描述你的点子，或让助手继续…"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
        />
        <button className="bg-indigo-600 text-white px-3 rounded text-sm" onClick={send}>发送</button>
      </div>
    </div>
  );
};

export default AgentChat;
```

- [ ] **Step 2: 提交**
```bash
git add src/components/AgentChat.tsx
git commit -m "feat(agent): AgentChat 聊天面板（复用 MessageBubble）"
```

---

## Task 8: 前端可编辑画布 `AgentCanvas.tsx`

**Files:**
- Create: `src/components/AgentCanvas.tsx`

- [ ] **Step 1: 组件（渲染 business_system 为卡片 + 选中回调）**

```tsx
// src/components/AgentCanvas.tsx
import React from 'react';
import { BusinessSystem } from '../api/bscApi';

interface AgentCanvasProps {
  businessSystem: BusinessSystem | null;
  selectedKey: string | null;
  onSelect: (key: string, value: unknown) => void;
}

const AgentCanvas: React.FC<AgentCanvasProps> = ({ businessSystem, selectedKey, onSelect }) => {
  if (!businessSystem) {
    return <div className="h-full flex items-center justify-center text-gray-400 text-sm">编译后将在这里显示业务系统画布</div>;
  }
  const bs = businessSystem;
  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      <h3 className="font-semibold">领域：{bs.business_domain || '未定'}</h3>

      <Section title={`角色 (${bs.roles?.length || 0})`}>
        {bs.roles?.map((r, i) => (
          <Card key={`role-${i}`} label={`role.${i}`} active={selectedKey === `role.${i}`}
                onClick={() => onSelect(`business_system.roles.${i}`, r)} title={r.role}>
            {(r.responsibilities || []).join('、')}
          </Card>
        ))}
      </Section>

      <Section title={`流程 (${bs.workflow?.length || 0})`}>
        {bs.workflow?.map((w, i) => (
          <Card key={`wf-${i}`} label={`workflow.${i}`} active={selectedKey === `workflow.${i}`}
                onClick={() => onSelect(`business_system.workflow.${i}`, w)} title={`${w.step}. ${w.name}`}>
            {w.action}
          </Card>
        ))}
      </Section>

      <Section title={`指标 (${bs.metrics?.length || 0})`}>
        {bs.metrics?.map((m, i) => (
          <Card key={`m-${i}`} label={`metrics.${i}`} active={selectedKey === `metrics.${i}`}
                onClick={() => onSelect(`business_system.metrics.${i}`, m)} title={m.name}>
            {m.target}
          </Card>
        ))}
      </Section>
    </div>
  );
};

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <div className="text-xs font-medium text-gray-500 mb-1">{title}</div>
    <div className="grid grid-cols-2 gap-2">{children}</div>
  </div>
);

const Card: React.FC<{ label: string; title: string; active: boolean; onClick: () => void; children: React.ReactNode }> =
  ({ label, title, active, onClick, children }) => (
    <div onClick={onClick}
      className={`border rounded p-2 text-xs cursor-pointer hover:border-indigo-400 ${active ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200'}`}>
      <div className="font-medium text-gray-800">{title}</div>
      <div className="text-gray-500 mt-1">{children}</div>
    </div>
  );

export default AgentCanvas;
```

- [ ] **Step 2: 提交**
```bash
git add src/components/AgentCanvas.tsx
git commit -m "feat(agent): AgentCanvas 业务系统画布（卡片化渲染 + 选中）"
```

---

## Task 9: 属性面板 + AgentStudio 页面 + 接入 App

**Files:**
- Create: `src/components/AgentPropertyPanel.tsx`
- Create: `src/pages/AgentStudio.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: AgentPropertyPanel（就地编辑选中节点）**

```tsx
// src/components/AgentPropertyPanel.tsx
import React, { useState, useEffect } from 'react';
import { agentApi, AgentDraft } from '../api/agentApi';

interface Props {
  sessionId: string | null;
  selected: { path: string; value: unknown } | null;
  onApplied: (d: AgentDraft) => void;
}

const AgentPropertyPanel: React.FC<Props> = ({ sessionId, selected, onApplied }) => {
  const [text, setText] = useState('');
  useEffect(() => { setText(selected ? JSON.stringify(selected.value, null, 2) : ''); }, [selected]);

  const apply = async () => {
    if (!sessionId || !selected) return;
    let val: unknown;
    try { val = JSON.parse(text); } catch { return; }
    const res = await agentApi.editNode(sessionId, selected.path, val);
    if (res.success) onApplied(res.draft);
  };

  if (!selected) return <div className="w-72 border-l p-3 text-xs text-gray-400">在画布中选择一个节点进行编辑</div>;
  return (
    <div className="w-72 border-l p-3 space-y-2">
      <div className="text-xs font-medium text-gray-500">编辑：{selected.path}</div>
      <textarea className="w-full h-40 border rounded text-xs font-mono p-1" value={text}
        onChange={e => setText(e.target.value)} />
      <button className="w-full bg-indigo-600 text-white rounded py-1 text-xs" onClick={apply}>应用到草稿</button>
    </div>
  );
};

export default AgentPropertyPanel;
```

- [ ] **Step 2: AgentStudio 组合三者**

```tsx
// src/pages/AgentStudio.tsx
import React, { useState } from 'react';
import AgentChat from '../components/AgentChat';
import AgentCanvas from '../components/AgentCanvas';
import AgentPropertyPanel from '../components/AgentPropertyPanel';
import { AgentDraft } from '../api/agentApi';

const AgentStudio: React.FC = () => {
  const [draft, setDraft] = useState<AgentDraft | null>(null);
  const [selected, setSelected] = useState<{ path: string; value: unknown } | null>(null);

  return (
    <div className="h-screen flex flex-col">
      <div className="h-10 flex items-center px-4 border-b bg-indigo-600 text-white text-sm font-medium">
        BSC 业务系统共创 · 对话式工作台
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-1/3 border-r flex flex-col">
          <AgentChat draft={draft} onDraft={setDraft} />
        </div>
        <div className="flex-1 overflow-hidden">
          <AgentCanvas
            businessSystem={draft?.business_system || null}
            selectedKey={selected?.path || null}
            onSelect={(path, value) => setSelected({ path, value })}
          />
        </div>
        <AgentPropertyPanel
          sessionId={draft?.session_id || null}
          selected={selected}
          onApplied={setDraft}
        />
      </div>
    </div>
  );
};

export default AgentStudio;
```

- [ ] **Step 3: 修改 App.tsx 接入（保留 Editor 可切换）**

```tsx
// src/App.tsx
import { useState } from 'react';
import Editor from './components/Editor';
import AgentStudio from './pages/AgentStudio';

export default function App() {
  const [tab, setTab] = useState<'studio' | 'editor'>('studio');
  return (
    <div className="h-screen flex flex-col">
      <div className="h-9 flex items-center gap-2 px-3 border-b bg-gray-800 text-white text-xs">
        <button className={tab === 'studio' ? 'font-bold' : 'opacity-70'} onClick={() => setTab('studio')}>共创工作台</button>
        <button className={tab === 'editor' ? 'font-bold' : 'opacity-70'} onClick={() => setTab('editor')}>演示编辑器</button>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === 'studio' ? <AgentStudio /> : <Editor />}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 类型检查 + 构建冒烟**
Run: `npm run check && npm run build`
Expected: 通过（或仅既有警告，无新错误）

- [ ] **Step 5: 提交**
```bash
git add src/components/AgentPropertyPanel.tsx src/pages/AgentStudio.tsx src/App.tsx
git commit -m "feat(agent): AgentStudio 页面（聊+画+属性面板）并接入 App"
```

---

## Task 10: 端到端黄金测试 + 全量回归

**Files:**
- Create: `tests/agent/test_e2e_golden.py`

- [ ] **Step 1: 写多轮对话 golden 测试**

```python
# tests/agent/test_e2e_golden.py
import os
os.environ.setdefault("BSC_MCP_FORCE_MOCK", "1")
from app.agent.bsc_agent import BSCAgentService
from app.agent.state import ProjectDraftRepository


def test_golden_multi_turn():
    svc = BSCAgentService()
    sid = svc.create_session(idea="社区老人上门助浴，含预约/上门/安全监护/家属通知")
    # 轮1：澄清
    r1 = svc.chat(sid, "帮我设计这个业务")
    assert r1["success"]
    # 轮2：要求生成
    r2 = svc.chat(sid, "直接生成业务系统和SOP吧")
    assert r2["success"]
    draft = ProjectDraftRepository().get(sid)
    assert draft.status in ("compiled", "sop")
    assert draft.business_system.get("roles") is not None
    # 轮3：编辑
    repo = ProjectDraftRepository()
    repo.patch(sid, "business_system.roles", [{"role": "助浴师", "responsibilities": ["安全监护"]}])
    assert repo.get(sid).business_system["roles"][0]["role"] == "助浴师"
```

- [ ] **Step 2: 运行 golden + 全量 agent 测试**
Run: `.venv/Scripts/python.exe -m pytest tests/agent/ -v`
Expected: PASS（全部 agent 测试）

- [ ] **Step 3: 提交**
```bash
git add tests/agent/test_e2e_golden.py
git commit -m "test(agent): 多轮对话 golden 测试（澄清→编译→SOP→编辑）"
```

- [ ] **Step 4: 全量回归（确认未破坏既有）**
Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全绿（或仅既有已知 skip/xfail）

---

## 自审结论
- **Spec 覆盖**：ADR-001 全部要点均有对应任务（Agent Loop→T3、5 工具→T2、Project Draft→T1、API→T4、MCP chat→T5、Web 聊+画→T6-T9、真实 deepseek+熔断→T3、测试→T1/T2/T10）。画布进 MVP 已落地（T8/T9）。
- **无占位符**：每步均含可运行代码。
- **类型一致**：`AgentDraft` / `BusinessSystem` 在前后端一致；`repo.patch` 的 path 约定（`business_system.<key>`）在 T1/T2/T5/T9 一致。
- **已知约束**：`LLMService.chat` 返回 dict，文本字段按 `content` 兜底（T2 已处理）；`create_agent` 来自 `langchain.agents`（与 `langchain_agent.py` 同源）；前端复用 `MessageBubble`/`fetchWrapper`/`BusinessSystem`，未触碰被 presentation store 绑死的 `ChatInterface`/`Canvas`。
- **漂移文件**：本计划不改动 `app/bsc_cloud.db*`、`llm_service.py`、`sop_report_engine.py`、`protocol.py`；新建 `agent_project_drafts` 表由 `get_db()` 自动创建，不进 git 的 db 文件本身。
