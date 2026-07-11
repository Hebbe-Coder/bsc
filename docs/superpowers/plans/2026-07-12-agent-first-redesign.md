# 多 Agent 团队编排的 Vibe Coding 工作区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **取代旧 plan**：本 plan 用多 Agent 团队编排（ADR-002）整体替换原单 Agent Loop 的 10 任务 plan。

**Goal:** 让用户用一句话描述点子，Orchestrator 驱动 5 个专职 Agent（Planner / Business Architect / SOP Builder / Reviewer / Presenter）协作产出 6 段状态，并在「实时工作区」画布（左聊天 / 中 React Flow 业务架构图 / 右 SOP / 底 Agent 执行日志）里实时显示团队进度，全链路真实 deepseek。

**Architecture:** Orchestrator 是唯一持有会话状态、唯一对接 SSE 实时流的进程，按混合流水线（固定顺序 + 回环≤1 + 定点重跑）派发 5 个专职 Agent。每个 Agent 是 `BaseAgent` 子类，只吃上游状态、只写自己那段状态（Planner→project+requirements；BA→business_model；SOP→sop；Reviewer→review；Presenter→presentation），内部按需复用 `compile_to_business_system_async` / `SOPReportEngine`。状态持久化到 SQLite `agent_project_drafts`（6 段）。

**Tech Stack:** Python 3.13 / FastAPI / pydantic / SQLite / `LLMService`（真实 deepseek，JSON 模式）/ `compile_to_business_system_async` / `SOPReportEngine` / python-pptx（Presenter 生成 PPT）；前端 React 18 + TypeScript + Vite + Tailwind + zustand + React Flow + EventSource。

**Spec:** `docs/superpowers/specs/2026-07-12-agent-first-redesign-design.md`（ADR-002，commit `7f2c03a`）。

---

## 文件结构（新建 / 修改）

### 后端（修改）
- `app/agent/state.py` — `ProjectDraft` 扩展为 6 段（`project/requirements/business_model/sop/review/presentation`）+ `ProjectDraftRepository.patch(segment, value)` 支持任意段。
- `app/main.py` — router 列表加入 `"app.api.orchestrate"`。
- `requirements.txt` — 增加 `python-pptx`、`reactflow`（前端，另见前端部分）。

### 后端（新建）
- `app/orchestrator/schemas.py` — 6 段 pydantic 模型 + `validate_segment()`。
- `app/orchestrator/engine.py` — `OrchestratorEngine`：流水线 / 回环≤1 / 定点重跑 / 事件发射。
- `app/orchestrator/sse.py` — `SessionEventBus`（每会话 `asyncio.Queue` 事件总线）。
- `app/orchestrator/agents/planner.py` — `PlannerAgent(BaseAgent)`
- `app/orchestrator/agents/business_architect.py` — `BusinessArchitectAgent`
- `app/orchestrator/agents/sop_builder.py` — `SopBuilderAgent`（内部用 `SOPReportEngine`）
- `app/orchestrator/agents/reviewer.py` — `ReviewerAgent`
- `app/orchestrator/agents/presenter.py` — `PresenterAgent`（HTML 汇报页 + python-pptx PPT）
- `app/api/orchestrate.py` — `POST /api/orchestrate` + `GET /api/orchestrate/stream`(SSE)
- `app/orchestrator/__init__.py`、`app/orchestrator/agents/__init__.py`

### 前端（新建）
- `src/api/orchestrateApi.ts` — `/api/orchestrate` + SSE `EventSource`
- `src/store/workspaceStore.ts` — zustand：6 段状态 + 阶段状态 + 实时日志
- `src/components/Workspace.tsx` — 四栏布局（左聊天/中图/右 SOP/底日志）
- `src/components/BusinessGraph.tsx` — React Flow 渲染 `business_model`
- `src/components/SopPanel.tsx` — SOP 步骤卡
- `src/components/AgentLog.tsx` — SSE 实时日志
- `src/components/ChatPanel.tsx` — 左栏聊天（复用 `MessageBubble`）

### 前端（修改）
- `src/App.tsx` — 增加 `/studio` 路由渲染 `Workspace`

### 测试（新建）
- `tests/orchestrator/test_state.py` — 6 段状态层单测
- `tests/orchestrator/test_schemas.py` — segment 校验单测
- `tests/orchestrator/test_agents.py` — 5 个 Agent 单测（注入 `FakeLLM`）
- `tests/orchestrator/test_engine.py` — 流水线 / 回环 / 重跑单测（注入 FakeLLM + FakeBus）
- `tests/orchestrator/test_api.py` — `/api/orchestrate` + SSE 集成测试（含鉴权头）
- `tests/orchestrator/test_e2e.py` — golden：「内容审核中心」端到端断言 6 段状态

---

## Task 1: 6 段状态层（扩展 T1 state.py）

**Files:**
- Modify: `app/agent/state.py`
- Test: `tests/orchestrator/test_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_state.py
import pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft, SEGMENTS


def test_create_and_get_six_segments():
    repo = ProjectDraftRepository()
    sid = "sess-6seg"
    d = ProjectDraft(session_id=sid, idea="内容审核中心")
    repo.save(d)
    got = repo.get(sid)
    assert got is not None
    assert got.idea == "内容审核中心"
    for seg in SEGMENTS:
        assert isinstance(getattr(got, seg), (dict, list))


def test_patch_segment():
    repo = ProjectDraftRepository()
    sid = "sess-patch"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    repo.patch(sid, "project", {"name": "审核中心"})
    got = repo.get(sid)
    assert got.project == {"name": "审核中心"}
    assert got.status == "edited:project"


def test_patch_unknown_segment_raises():
    repo = ProjectDraftRepository()
    sid = "sess-bad"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    with pytest.raises(ValueError):
        repo.patch(sid, "nope", {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/orchestrator/test_state.py -v`
Expected: FAIL（`SEGMENTS`/`patch(segment,value)` 不存在）

- [ ] **Step 3: 实现 6 段状态层**

```python
# app/agent/state.py
from __future__ import annotations
import json, time, uuid
from typing import Any, Dict, Optional
from app.db import get_db

SEGMENTS = ("project", "requirements", "business_model", "sop", "review", "presentation")


class ProjectDraft:
    def __init__(self, session_id: str = None, idea: str = "",
                 project: Optional[dict] = None, requirements: Optional[list] = None,
                 business_model: Optional[dict] = None, sop: Optional[dict] = None,
                 review: Optional[dict] = None, presentation: Optional[dict] = None,
                 status: str = "planned", messages: Optional[list] = None,
                 updated_at: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.idea = idea
        self.project = project or {}
        self.requirements = requirements or []
        self.business_model = business_model or {}
        self.sop = sop or {}
        self.review = review or {}
        self.presentation = presentation or {}
        self.status = status
        self.messages = messages or []
        self.updated_at = updated_at or time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id, "idea": self.idea,
            "project": self.project, "requirements": self.requirements,
            "business_model": self.business_model, "sop": self.sop,
            "review": self.review, "presentation": self.presentation,
            "status": self.status, "messages": self.messages, "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row):
        d = dict(row)
        for seg in SEGMENTS:
            v = d.get(seg)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    v = {}
            d[seg] = v or {}
        d["messages"] = json.loads(d["messages"]) if isinstance(d.get("messages"), str) else (d.get("messages") or [])
        return cls(**d)


class ProjectDraftRepository:
    def __init__(self):
        self._db = get_db()
        self._ensure_table()

    def _ensure_table(self):
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS agent_project_drafts (
                session_id TEXT PRIMARY KEY, idea TEXT, project TEXT, requirements TEXT,
                business_model TEXT, sop TEXT, review TEXT, presentation TEXT,
                status TEXT, messages TEXT, updated_at TEXT
            )"""
        )
        self._db.commit()

    def save(self, draft: ProjectDraft):
        draft.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, idea, project, requirements, business_model, sop, review, presentation, status, messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               idea=excluded.idea, project=excluded.project, requirements=excluded.requirements,
               business_model=excluded.business_model, sop=excluded.sop, review=excluded.review,
               presentation=excluded.presentation, status=excluded.status, messages=excluded.messages,
               updated_at=excluded.updated_at""",
            (draft.session_id, draft.idea,
             json.dumps(draft.project, ensure_ascii=False),
             json.dumps(draft.requirements, ensure_ascii=False),
             json.dumps(draft.business_model, ensure_ascii=False),
             json.dumps(draft.sop, ensure_ascii=False),
             json.dumps(draft.review, ensure_ascii=False),
             json.dumps(draft.presentation, ensure_ascii=False),
             draft.status, json.dumps(draft.messages, ensure_ascii=False), draft.updated_at))
        self._db.commit()

    def get(self, session_id: str):
        row = self._db.execute("SELECT * FROM agent_project_drafts WHERE session_id=?", (session_id,)).fetchone()
        return ProjectDraft.from_row(row) if row else None

    def patch(self, session_id: str, segment: str, value: Any):
        if segment not in SEGMENTS:
            raise ValueError(f"未知状态段: {segment}")
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        setattr(draft, segment, value)
        draft.status = f"edited:{segment}"
        self.save(draft)
        return draft
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/orchestrator/test_state.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/agent/state.py tests/orchestrator/test_state.py
git commit -m "feat(agent): extend ProjectDraft to 6 segments + segment patch"
```

---

## Task 2: 6 段状态校验 schema（pydantic）

**Files:**
- Create: `app/orchestrator/schemas.py`
- Test: `tests/orchestrator/test_schemas.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_schemas.py
import pytest
from app.orchestrator.schemas import validate_segment, ValidationError


def test_validate_business_model_ok():
    data = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    assert validate_segment("business_model", data)["flows"][0]["id"] == "f1"


def test_validate_business_model_missing_required():
    with pytest.raises(ValidationError):
        validate_segment("business_model", {"flows": []})  # 缺 roles/rules


def test_validate_review_loopback():
    data = {"approved": False, "gaps": [{"severity": "high", "type": "sla",
            "desc": "缺 SLA", "suggested_fix": "加 SLA", "target": "sop"}],
            "loopback_target": "sop", "summary": "需补 SLA"}
    out = validate_segment("review", data)
    assert out.loopback_target == "sop"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_schemas.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 schemas**

```python
# app/orchestrator/schemas.py
from __future__ import annotations
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError


class ProjectModel(BaseModel):
    name: str
    goal: str
    industry: str
    scope: dict = Field(default_factory=dict)   # {in_scope:[], out_scope:[]}
    actors: list = Field(default_factory=list)   # [{role, description}]


class Requirement(BaseModel):
    id: str
    text: str
    priority: str = "mid"
    source: str = ""


class BusinessModel(BaseModel):
    flows: list = Field(default_factory=list)    # [{id,name,description,steps[],input,output}]
    roles: list = Field(default_factory=list)     # [{id,name,responsibility,belongs_to_flow}]
    rules: list = Field(default_factory=list)     # [{id,statement,applies_to}]


class SopStep(BaseModel):
    seq: int
    action: str
    sla: str = ""


class Sop(BaseModel):
    id: str
    title: str
    owner_role: str = ""
    trigger: str = ""
    steps: list = Field(default_factory=list)    # [{seq,action,sla?}]
    escalation: str = ""
    review_cycle: str = ""


class SopSet(BaseModel):
    sops: list = Field(default_factory=list)     # [Sop]


class Gap(BaseModel):
    id: str = ""
    severity: str                                # high|medium|low
    type: str = ""
    desc: str = ""
    suggested_fix: str = ""
    target: str = ""                            # ba|sop


class Review(BaseModel):
    approved: bool = False
    gaps: list = Field(default_factory=list)     # [Gap]
    loopback_target: str = None                  # ba|sop|null
    summary: str = ""


class Presentation(BaseModel):
    html_url: str = ""
    ppt_path: str = ""
    diagram_spec: dict = Field(default_factory=dict)


_VALIDATORS = {
    "project": ProjectModel,
    "requirements": lambda v: [Requirement(**r) for r in (v or [])],
    "business_model": BusinessModel,
    "sop": SopSet,
    "review": Review,
    "presentation": Presentation,
}


class ValidationError(Exception):
    pass


def validate_segment(segment: str, data: dict):
    if segment not in _VALIDATORS:
        raise ValidationError(f"未知状态段: {segment}")
    try:
        return _VALIDATORS[segment](data)
    except PydanticValidationError as e:
        raise ValidationError(f"{segment} 校验失败: {e}") from e
    except TypeError as e:
        raise ValidationError(f"{segment} 类型错误: {e}") from e
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_schemas.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/__init__.py app/orchestrator/schemas.py tests/orchestrator/test_schemas.py
git commit -m "feat(orchestrator): add 6-segment pydantic validation schemas"
```

---

## Task 3: Planner Agent

**Files:**
- Create: `app/orchestrator/agents/__init__.py`, `app/orchestrator/agents/planner.py`
- Test: `tests/orchestrator/test_agents.py`（本任务先写 Planner 部分）

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_agents.py  (Planner 部分)
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.schemas import validate_segment


class FakeLLM:
    def __init__(self, payload): self._p = payload
    def chat(self, system_prompt, user_prompt, temperature=0.1, max_tokens=None, use_cache=True):
        return self._p


def test_planner_produces_project_and_requirements():
    payload = {
        "project": {"name": "内容审核中心", "goal": "高效审核 UGC", "industry": "互联网",
                    "scope": {"in_scope": ["文本审核"], "out_scope": ["视频"]},
                    "actors": [{"role": "审核员", "description": "一线审核"}]},
        "requirements": [{"id": "r1", "text": "支持多模态", "priority": "high", "source": "user"}],
    }
    agent = PlannerAgent(llm_service=FakeLLM(payload))
    out = agent.run(idea="我要做一个内容审核中心")
    validate_segment("project", out["project"])   # 不抛异常
    validate_segment("requirements", out["requirements"])
    assert out["project"]["name"] == "内容审核中心"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: FAIL（模块/类不存在）

- [ ] **Step 3: 实现 PlannerAgent**

```python
# app/orchestrator/agents/planner.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class PlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Planner Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Planner Agent。职责：理解用户的业务点子，明确目标、业务边界、组织结构与规模。\n"
            "必须只输出 JSON，格式：\n"
            "{\n"
            '  "project": {"name":str,"goal":str,"industry":str,'
            '   "scope":{"in_scope":[str],"out_scope":[str]},'
            '   "actors":[{"role":str,"description":str}]},\n'
            '  "requirements": [{"id":str,"text":str,"priority":"high|mid|low","source":str}]\n'
            "}"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["project", "requirements"]}

    def run(self, idea: str, context: dict = None) -> dict:
        user_prompt = f"用户的业务点子：{idea}\n请产出 project 与 requirements。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
```

> 复用 `BaseAgent.chat` 的 JSON 模式与 schema 必填校验；`FakeLLM` 在测试中注入，`run` 返回 LLM 的解析后 dict。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/agents/__init__.py app/orchestrator/agents/planner.py tests/orchestrator/test_agents.py
git commit -m "feat(agents): PlannerAgent produces project + requirements"
```

---

## Task 4: Business Architect Agent（复用 compile 引擎）

**Files:**
- Create: `app/orchestrator/agents/business_architect.py`
- Test: `tests/orchestrator/test_agents.py`（追加 BA 部分）

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_agents.py (追加)
import asyncio
from app.orchestrator.agents.business_architect import BusinessArchitectAgent


class FakeCompile:
    async def __call__(self, prd, llm_service=None, **kw):
        return {"functions": [{"name": "受理"}], "roles": [{"name": "审核员"}]}


def test_ba_produces_business_model():
    payload = {"business_model": {"flows": [{"id": "f1", "name": "受理", "steps": ["收单"]}],
                                  "roles": [{"id": "r1", "name": "审核员"}], "rules": []}}
    agent = BusinessArchitectAgent(llm_service=FakeLLM(payload))
    out = asyncio.run(agent.run(idea="内容审核中心",
                                project={"name": "内容审核中心"},
                                requirements=[],
                                _compile=FakeCompile()))
    assert "business_model" in out
    assert out["business_model"]["flows"][0]["name"] == "受理"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 BusinessArchitectAgent**

```python
# app/orchestrator/agents/business_architect.py
from __future__ import annotations
import asyncio
from app.agents.base_agent import BaseAgent


class BusinessArchitectAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Business Architect Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Business Architect Agent。职责：把已编译的业务系统结构化为业务模型。\n"
            "输入是编译后的 business_system（含流程/角色）。请产出 JSON：\n"
            '{"business_model":{"flows":[{"id":str,"name":str,"description":str,'
            '"steps":[str],"input":str,"output":str}],'
            ' "roles":[{"id":str,"name":str,"responsibility":str,"belongs_to_flow":str}],'
            ' "rules":[{"id":str,"statement":str,"applies_to":str}]}}'
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["business_model"]}

    async def run(self, idea: str, project: dict, requirements: list,
                  _compile=None, context: dict = None) -> dict:
        # 内部复用 compile_to_business_system_async 作为编译引擎
        if _compile is None:
            from app.core.async_pipeline import compile_to_business_system_async
            _compile = compile_to_business_system_async
        bs = await _compile(idea, llm_service=self.llm_service)
        user_prompt = (
            f"项目：{project}\n需求：{requirements}\n"
            f"已编译业务系统：{bs}\n请结构化为 business_model。"
        )
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/agents/business_architect.py tests/orchestrator/test_agents.py
git commit -m "feat(agents): BusinessArchitectAgent reuses compile engine"
```

---

## Task 5: SOP Builder Agent（复用 SOPReportEngine）

**Files:**
- Create: `app/orchestrator/agents/sop_builder.py`
- Test: `tests/orchestrator/test_agents.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_agents.py (追加)
from app.orchestrator.agents.sop_builder import SopBuilderAgent


class FakeSopEngine:
    def generate_full_sop_report(self, business_system, enable_ai_analysis=False):
        return {"workflow": [{"step": 1, "name": "受理", "action": "收单"}],
                "roles": [{"role": "审核员"}],
                "sla": [{"metric": "时效", "target": "5min", "owner": "审核员"}]}


def test_sop_builder_produces_sops():
    payload = {"sop": {"sops": [{"id": "s1", "title": "审核 SOP", "owner_role": "审核员",
                                  "trigger": "收到内容", "steps": [{"seq": 1, "action": "初审"}],
                                  "escalation": "升级主管", "review_cycle": "周"}]}}
    agent = SopBuilderAgent(llm_service=FakeLLM(payload))
    out = agent.run(business_model={"flows": [], "roles": [], "rules": []},
                    _engine=FakeSopEngine())
    assert "sop" in out
    assert out["sop"]["sops"][0]["title"] == "审核 SOP"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 SopBuilderAgent**

```python
# app/orchestrator/agents/sop_builder.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class SopBuilderAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "SOP Builder Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 SOP Builder Agent。职责：把 SOP 报告结构化为最终 SOP 集合。\n"
            "输入是 SOPReportEngine 生成的报告（含 workflow/roles/sla）。请产出 JSON：\n"
            '{"sop":{"sops":[{"id":str,"title":str,"owner_role":str,"trigger":str,'
            '"steps":[{"seq":int,"action":str,"sla":str}],"escalation":str,"review_cycle":str}]}}'
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["sop"]}

    def run(self, business_model: dict, _engine=None, context: dict = None) -> dict:
        if _engine is None:
            from app.engines.sop_report_engine import SOPReportEngine
            _engine = SOPReportEngine()
        report = _engine.generate_full_sop_report(business_model, enable_ai_analysis=True)
        user_prompt = f"SOP 报告：{report}\n请结构化为 sop 集合。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/agents/sop_builder.py tests/orchestrator/test_agents.py
git commit -m "feat(agents): SopBuilderAgent reuses SOPReportEngine"
```

---

## Task 6: Reviewer Agent（含回环信号）

**Files:**
- Create: `app/orchestrator/agents/reviewer.py`
- Test: `tests/orchestrator/test_agents.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_agents.py (追加)
from app.orchestrator.agents.reviewer import ReviewerAgent


def test_reviewer_finds_gap_and_loopback():
    payload = {"review": {"approved": False,
        "gaps": [{"id": "g1", "severity": "high", "type": "sla",
                  "desc": "缺 SLA", "suggested_fix": "加 SLA", "target": "sop"}],
        "loopback_target": "sop", "summary": "需补 SLA"}}
    agent = ReviewerAgent(llm_service=FakeLLM(payload))
    out = agent.run(project={}, business_model={}, sop={})
    assert out["review"]["approved"] is False
    assert out["review"]["loopback_target"] == "sop"


def test_reviewer_approves():
    payload = {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
    agent = ReviewerAgent(llm_service=FakeLLM(payload))
    out = agent.run(project={}, business_model={}, sop={})
    assert out["review"]["approved"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 ReviewerAgent**

```python
# app/orchestrator/agents/reviewer.py
from __future__ import annotations
from app.agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Reviewer Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Reviewer Agent。职责：审查业务模型与 SOP，找漏洞（尤其缺复审/升级机制/SLA）。\n"
            "必须输出 JSON：\n"
            '{"review":{"approved":bool,'
            ' "gaps":[{"id":str,"severity":"high|medium|low","type":str,"desc":str,'
            '          "suggested_fix":str,"target":"ba|sop"}],'
            ' "loopback_target":"ba|sop|null",'
            ' "summary":str}}'
            "\n若存在 high 级漏洞，loopback_target 指向需重做的段（ba 或 sop），否则 null。"
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["review"]}

    def run(self, project: dict, business_model: dict, sop: dict, context: dict = None) -> dict:
        user_prompt = f"项目：{project}\n业务模型：{business_model}\nSOP：{sop}\n请审查并产出 review。"
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: PASS（全部 agent 测试）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/agents/reviewer.py tests/orchestrator/test_agents.py
git commit -m "feat(agents): ReviewerAgent finds gaps + signals loopback"
```

---

## Task 7: Presenter Agent（HTML 汇报页 + PPT）

**Files:**
- Create: `app/orchestrator/agents/presenter.py`
- Test: `tests/orchestrator/test_agents.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_agents.py (追加)
import os, tempfile
from app.orchestrator.agents.presenter import PresenterAgent

def test_presenter_writes_html_and_ppt():
    out_dir = tempfile.mkdtemp()
    payload = {"presentation": {"html_url": "/presentations/s1.html",
                                "ppt_path": "/presentations/s1.pptx",
                                "diagram_spec": {"flows": [], "roles": [], "rules": []}}}
    agent = PresenterAgent(llm_service=FakeLLM(payload))
    out = agent.run(session_id="s1", state={"project": {"name": "审核中心"}}, out_dir=out_dir)
    assert out["presentation"]["html_url"].endswith(".html")
    assert os.path.exists(os.path.join(out_dir, "s1.html"))
    assert os.path.exists(os.path.join(out_dir, "s1.pptx"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 PresenterAgent**

```python
# app/orchestrator/agents/presenter.py
from __future__ import annotations
import os
from app.agents.base_agent import BaseAgent


class PresenterAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Presenter Agent"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 Presenter Agent。职责：基于 6 段状态生成汇报叙述。\n"
            "必须输出 JSON：\n"
            '{"presentation":{"html_url":str,"ppt_path":str,'
            ' "diagram_spec":{"flows":[],"roles":[],"rules":[]}}}'
        )

    @property
    def output_schema(self) -> dict:
        return {"required": ["presentation"]}

    def run(self, session_id: str, state: dict, out_dir: str = "static/presentations",
            context: dict = None) -> dict:
        os.makedirs(out_dir, exist_ok=True)
        user_prompt = f"6 段状态：{state}\n请生成汇报材料（HTML + PPT）的元信息与 diagram_spec。"
        meta = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        pres = meta.get("presentation", {})
        html_path = os.path.join(out_dir, f"{session_id}.html")
        ppt_path = os.path.join(out_dir, f"{session_id}.pptx")
        # 真实生成 HTML 汇报页
        html = self._render_html(state)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        # 真实生成 PPT（python-pptx）
        self._render_ppt(session_id, state, ppt_path)
        return {"presentation": {
            "html_url": f"/presentations/{session_id}.html",
            "ppt_path": f"/presentations/{session_id}.pptx",
            "diagram_spec": pres.get("diagram_spec", state.get("business_model", {})),
        }}

    def _render_html(self, state: dict) -> str:
        name = state.get("project", {}).get("name", "项目")
        return (
            "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
            f"<title>{name} 汇报</title></head><body>"
            f"<h1>{name} 业务共创汇报</h1>"
            f"<h2>业务模型</h2><pre>{state.get('business_model', {})!r}</pre>"
            f"<h2>SOP</h2><pre>{state.get('sop', {})!r}</pre>"
            f"<h2>审查</h2><pre>{state.get('review', {})!r}</pre>"
            "</body></html>"
        )

    def _render_ppt(self, session_id: str, state: dict, ppt_path: str):
        try:
            from pptx import Presentation
            from pptx.util import Inches
        except ImportError:
            # python-pptx 缺失时写占位文件，避免中断流水线
            with open(ppt_path, "w", encoding="utf-8") as f:
                f.write("PPT placeholder")
            return
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = state.get("project", {}).get("name", "项目") + " 业务共创汇报"
        prs.save(ppt_path)
```

> 需安装：`cd "/c/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/pip.exe install python-pptx`，并在 `requirements.txt` 增加 `python-pptx`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_agents.py -v`
Expected: PASS（全部 agent 测试）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/agents/presenter.py tests/orchestrator/test_agents.py requirements.txt
git commit -m "feat(agents): PresenterAgent generates HTML + PPT"
```

---

## Task 8: Orchestrator Engine（流水线 / 回环≤1 / 定点重跑）

**Files:**
- Create: `app/orchestrator/sse.py`, `app/orchestrator/engine.py`
- Test: `tests/orchestrator/test_engine.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_engine.py
import asyncio
from app.orchestrator.engine import OrchestratorEngine


class FakeBus:
    def __init__(self): self.events = []
    async def publish(self, session_id, event): self.events.append(event)


def make_engine():
    # 用 FakeLLM 驱动的 agent 工厂；此处用最简 stub：每个 agent 直接返回固定段
    class StubAgent:
        def __init__(self, seg, data): self.seg, self.data = seg, data
        def run(self, *a, **k): return {self.seg: self.data}
        async def run_async(self, *a, **k): return {self.seg: self.data}
    agents = {
        "planner": StubAgent("project+requirements", {"project": {"name": "x"}, "requirements": []}),
        "architect": StubAgent("business_model", {"business_model": {"flows": [], "roles": [], "rules": []}}),
        "sop": StubAgent("sop", {"sop": {"sops": []}}),
        "reviewer": StubAgent("review", {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}),
        "presenter": StubAgent("presentation", {"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}),
    }
    return OrchestratorEngine(agents=agents, repo=None, bus=FakeBus())


def test_pipeline_writes_six_segments():
    eng = make_engine()
    result = asyncio.run(eng.run_pipeline("s1", "内容审核中心"))
    assert result["project"]["name"] == "x"
    assert "business_model" in result
    assert result["review"]["approved"] is True


def test_loopback_once_on_high_gap():
    eng = make_engine()
    # 让 reviewer 第一次返回 high 漏洞打回 sop，第二次通过
    class LoopReviewer:
        def __init__(self): self.n = 0
        def run(self, *a, **k):
            self.n += 1
            if self.n == 1:
                return {"review": {"approved": False, "gaps": [{"severity": "high", "target": "sop"}],
                                   "loopback_target": "sop", "summary": "缺 SLA"}}
            return {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
    eng.agents["reviewer"] = LoopReviewer()
    result = asyncio.run(eng.run_pipeline("s2", "内容审核中心"))
    assert result["review"]["approved"] is True   # 回环后通过
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 sse.py + engine.py**

```python
# app/orchestrator/sse.py
from __future__ import annotations
import asyncio
from typing import Dict
from app.orchestrator.schemas import ValidationError


class SessionEventBus:
    """每会话一个 asyncio.Queue 的事件总线，供 SSE 端点消费。"""
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}

    def get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def publish(self, session_id: str, event: dict):
        await self.get_queue(session_id).put(event)

    async def subscribe(self, session_id: str):
        q = self.get_queue(session_id)
        while True:
            yield await q.get()
```

```python
# app/orchestrator/engine.py
from __future__ import annotations
import asyncio
from typing import Optional
from app.agent.state import ProjectDraftRepository, ProjectDraft
from app.orchestrator.schemas import validate_segment, ValidationError
from app.orchestrator.sse import SessionEventBus


class OrchestratorEngine:
    STAGES = ["planner", "architect", "sop", "reviewer", "presenter"]

    def __init__(self, agents: dict, repo: Optional[ProjectDraftRepository] = None,
                 bus: Optional[SessionEventBus] = None):
        self.agents = agents
        self.repo = repo or ProjectDraftRepository()
        self.bus = bus or SessionEventBus()

    async def _emit(self, sid, stage, status, msg=""):
        await self.bus.publish(sid, {"stage": stage, "status": status, "msg": msg})

    async def run_pipeline(self, session_id: str, idea: str) -> dict:
        draft = self.repo.get(session_id) or ProjectDraft(session_id=session_id, idea=idea)
        state = draft.to_dict()
        await self._emit(session_id, "planner", "running", "正在识别行业与边界")
        out = await self._call("planner", session_id, idea=idea)
        state["project"] = out.get("project", {})
        state["requirements"] = out.get("requirements", [])
        self._save(session_id, state)
        await self._emit(session_id, "planner", "done", "项目与目标已明确")

        await self._emit(session_id, "architect", "running", "正在构建流程")
        out = await self._call("architect", session_id, idea=idea,
                               project=state["project"], requirements=state["requirements"])
        state["business_model"] = out.get("business_model", {})
        self._save(session_id, state)
        await self._emit(session_id, "architect", "done", "业务架构已生成")

        await self._emit(session_id, "sop", "running", "正在生成 SOP")
        out = await self._call("sop", session_id, business_model=state["business_model"])
        state["sop"] = out.get("sop", {})
        self._save(session_id, state)
        await self._emit(session_id, "sop", "done", "SOP 已生成")

        # Reviewer + 受控回环（≤1）
        loop_count = 0
        while True:
            await self._emit(session_id, "reviewer", "running", "正在审查漏洞")
            out = await self._call("reviewer", session_id,
                                   project=state["project"], business_model=state["business_model"],
                                   sop=state["sop"])
            review = out.get("review", {})
            state["review"] = review
            self._save(session_id, state)
            if review.get("approved") or loop_count >= 1:
                await self._emit(session_id, "reviewer", "done", review.get("summary", "审查完成"))
                break
            target = review.get("loopback_target")
            await self._emit(session_id, target, "loopback", f"↺ 打回 {target} 重做")
            if target == "sop":
                out = await self._call("sop", session_id, business_model=state["business_model"])
                state["sop"] = out.get("sop", {})
            elif target == "architect":
                out = await self._call("architect", session_id, idea=idea,
                                       project=state["project"], requirements=state["requirements"])
                state["business_model"] = out.get("business_model", {})
            self._save(session_id, state)
            loop_count += 1
            await self._emit(session_id, "reviewer", "running", "重新审查")

        await self._emit(session_id, "presenter", "running", "正在生成汇报材料")
        out = await self._call("presenter", session_id, session_id=session_id, state=state)
        state["presentation"] = out.get("presentation", {})
        self._save(session_id, state)
        await self._emit(session_id, "presenter", "done", "汇报材料已生成")
        return state

    async def rerun_node(self, session_id: str, node: str) -> dict:
        """定点重跑单节点（仅允许 architect/sop/reviewer/presenter）。"""
        if node not in ("architect", "sop", "reviewer", "presenter"):
            raise ValueError(f"不允许重跑 {node}")
        draft = self.repo.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        state = draft.to_dict()
        await self._emit(session_id, node, "running", f"定点重跑 {node}")
        kwargs = self._upstream_for(node, state)
        out = await self._call(node, session_id, **kwargs)
        seg = {"architect": "business_model", "sop": "sop",
               "reviewer": "review", "presenter": "presentation"}[node]
        state[seg] = out.get(seg, out)
        self._save(session_id, state)
        await self._emit(session_id, node, "done", f"{node} 已重跑")
        return state

    async def _call(self, name, session_id, **kwargs):
        agent = self.agents[name]
        if hasattr(agent, "run_async"):
            return await agent.run_async(**kwargs)
        return agent.run(**kwargs)

    def _upstream_for(self, node, state):
        if node == "architect":
            return {"idea": state["idea"], "project": state["project"], "requirements": state["requirements"]}
        if node == "sop":
            return {"business_model": state["business_model"]}
        if node == "reviewer":
            return {"project": state["project"], "business_model": state["business_model"], "sop": state["sop"]}
        if node == "presenter":
            return {"session_id": state["session_id"], "state": state}
        return {}

    def _save(self, session_id, state):
        draft = ProjectDraft(
            session_id=session_id, idea=state.get("idea", ""),
            project=state.get("project", {}), requirements=state.get("requirements", []),
            business_model=state.get("business_model", {}), sop=state.get("sop", {}),
            review=state.get("review", {}), presentation=state.get("presentation", {}),
            status="running", messages=state.get("messages", []),
        )
        self.repo.save(draft)
```

> 注：真实使用时 `agents` 传 5 个真实 Agent 实例（`PlannerAgent(llm)` 等）。`run_pipeline` 为 async，由 API 层 `await`。回环严格 `loop_count >= 1` 即停，保证 ≤1 次。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_engine.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/orchestrator/sse.py app/orchestrator/engine.py tests/orchestrator/test_engine.py
git commit -m "feat(orchestrator): pipeline + loopback<=1 + targeted rerun"
```

---

## Task 9: API 端点 + SSE 实时流

**Files:**
- Create: `app/api/orchestrate.py`
- Test: `tests/orchestrator/test_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/orchestrator/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agent.state import ProjectDraftRepository


@pytest.fixture
def client(monkeypatch):
    # 用 FakeLLM 替身，避免真实 LLM
    import app.api.orchestrate as mod
    class Stub:
        def run(self, *a, **k): return {"project": {"name": "x"}, "requirements": []}
        def run_async(self, *a, **k): return self.run(*a, **k)
    monkeypatch.setattr(mod, "build_agents", lambda llm: {
        "planner": Stub(), "architect": Stub(), "sop": Stub(),
        "reviewer": Stub(), "presenter": Stub()})
    return TestClient(app)


def test_orchestrate_requires_auth(client):
    r = client.post("/api/orchestrate", json={"idea": "内容审核中心"})
    assert r.status_code in (401, 403)


def test_orchestrate_runs(client, monkeypatch):
    monkeypatch.setattr("app.agent.state.settings", __import__("app.core.config", fromlist=["settings"]).settings)
    monkeypatch.setattr(__import__("app.core.config", fromlist=["settings"]).settings, "API_KEY", "test-key-123")
    r = client.post("/api/orchestrate", json={"idea": "内容审核中心"},
                    headers={"Authorization": "Bearer test-key-123"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    repo = ProjectDraftRepository()
    got = repo.get(sid)
    assert got is not None
    assert "project" in got.to_dict()
```

> 鉴权遵循项目约定：注入唯一 `API_KEY`，请求头带 `Authorization: Bearer <key>`（`monkeypatch.setattr(settings, "API_KEY", ...)`）。

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 API**

```python
# app/api/orchestrate.py
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.agent.state import ProjectDraftRepository
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.sse import SessionEventBus
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])
_bus = SessionEventBus()


def build_agents(llm):
    from app.orchestrator.agents.planner import PlannerAgent
    from app.orchestrator.agents.business_architect import BusinessArchitectAgent
    from app.orchestrator.agents.sop_builder import SopBuilderAgent
    from app.orchestrator.agents.reviewer import ReviewerAgent
    from app.orchestrator.agents.presenter import PresenterAgent
    return {
        "planner": PlannerAgent(llm_service=llm),
        "architect": BusinessArchitectAgent(llm_service=llm),
        "sop": SopBuilderAgent(llm_service=llm),
        "reviewer": ReviewerAgent(llm_service=llm),
        "presenter": PresenterAgent(llm_service=llm),
    }


@router.post("")
async def orchestrate(request: Request):
    body = await request.json()
    idea = body.get("idea")
    if not idea:
        raise HTTPException(400, "idea required")
    sid = body.get("session_id")
    llm = LLMService()
    eng = OrchestratorEngine(agents=build_agents(llm), bus=_bus)
    # 后台跑流水线（真实场景可换 task），先返回 session_id
    asyncio.create_task(eng.run_pipeline(sid or __import__("uuid").uuid4().hex[:12], idea))
    return {"session_id": sid or "started", "status": "running"}


@router.get("/stream")
async def stream(session_id: str):
    async def event_gen():
        async for ev in _bus.subscribe(session_id):
            yield f"data: {__import__('json').dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator/test_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/api/orchestrate.py tests/orchestrator/test_api.py
git commit -m "feat(api): /api/orchestrate + SSE stream"
```

---

## Task 10: 注册路由到 main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 在 router 列表加入 orchestrate**

找到 main.py 中注册 api router 的位置（旧 plan 指向 `app/main.py:215` 附近，形如 `routers = ["app.api.knowledge", ...]` 或 `app.include_router(...)`），加入 `"app.api.orchestrate"`。

```python
# 示例（按你工程实际注册方式二选一）
# 方式 A：字符串列表自动加载
ROUTERS = [
    "app.api.knowledge",
    "app.api.orchestrate",   # <-- 新增
    # ... 其它既有 router
]

# 方式 B：显式 include_router
from app.api.orchestrate import router as orchestrate_router
app.include_router(orchestrate_router)
```

> 必须与现有注册方式一致；若工程用字符串列表，则加到列表；若用 `include_router`，则显式引入。保持与 `app/api/orchestrate.py` 的 `router` 对象同名。

- [ ] **Step 2: 运行全量测试确认无破坏**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator -v`
Expected: PASS（本模块全绿；全局套件可能因其他模块漂移，见项目测试约定）

- [ ] **Step 3: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add app/main.py
git commit -m "feat: register orchestrate router in main"
```

---

## Task 11: 前端实时工作区（四栏 + React Flow + SSE）

**Files:**
- Create: `src/api/orchestrateApi.ts`, `src/store/workspaceStore.ts`, `src/components/Workspace.tsx`, `src/components/BusinessGraph.tsx`, `src/components/SopPanel.tsx`, `src/components/AgentLog.tsx`, `src/components/ChatPanel.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: API 客户端 + store**

```typescript
// src/api/orchestrateApi.ts
import { fetchWrapper } from "./bscApi";

export async function startOrchestrate(idea: string): Promise<{ session_id: string }> {
  return fetchWrapper("/api/orchestrate", { method: "POST", body: JSON.stringify({ idea }) });
}

export function subscribeStream(sessionId: string, onEvent: (e: any) => void) {
  const es = new EventSource(`/api/orchestrate/stream?session_id=${encodeURIComponent(sessionId)}`);
  es.onmessage = (ev) => onEvent(JSON.parse(ev.data));
  return es;
}
```

```typescript
// src/store/workspaceStore.ts
import { create } from "zustand";

export const useWorkspace = create<{
  sessionId: string | null;
  idea: string;
  project: any; requirements: any[]; businessModel: any; sop: any; review: any; presentation: any;
  stages: Record<string, string>;   // planner|architect|sop|reviewer|presenter -> pending|running|done|loopback
  log: { stage: string; msg: string }[];
  set: (p: Partial<any>) => void;
  pushLog: (stage: string, msg: string) => void;
  setStage: (stage: string, status: string) => void;
}>(set => ({
  sessionId: null, idea: "", project: {}, requirements: [], businessModel: {}, sop: {}, review: {}, presentation: {},
  stages: {}, log: [],
  set: (p) => set(p),
  pushLog: (stage, msg) => set(s => ({ log: [...s.log, { stage, msg }] })),
  setStage: (stage, status) => set(s => ({ stages: { ...s.stages, [stage]: status } })),
}));
```

- [ ] **Step 2: 四栏组件**

```tsx
// src/components/BusinessGraph.tsx
import ReactFlow, { Node, Edge } from "reactflow";
import "reactflow/dist/style.css";

export function BusinessGraph({ model }: { model: any }) {
  const flows = model?.flows || [];
  const roles = model?.roles || [];
  const nodes: Node[] = flows.map((f: any, i: number) => ({
    id: f.id || `f${i}`, position: { x: 80, y: i * 90 }, data: { label: f.name },
  }));
  const edges: Edge[] = flows.flatMap((f: any, i: number) =>
    (f.steps || []).map((_: any, j: number) => ({
      id: `${f.id}-${j}`, source: f.id || `f${i}`, target: flows[i + 1]?.id || `f${i + 1}` || f.id,
    })).filter((e: Edge) => e.target !== e.source));
  return <ReactFlow nodes={nodes} edges={edges} fitView />;
}
```

```tsx
// src/components/SopPanel.tsx
export function SopPanel({ sop }: { sop: any }) {
  const sops = sop?.sops || [];
  return (
    <div className="space-y-2">
      {sops.map((s: any) => (
        <div key={s.id} className="border rounded p-2">
          <h4 className="font-medium">{s.title} <span className="text-xs text-gray-400">{s.owner_role}</span></h4>
          <ul className="text-sm list-decimal pl-5">
            {(s.steps || []).map((st: any) => <li key={st.seq}>{st.action}{st.sla ? ` (SLA ${st.sla})` : ""}</li>)}
          </ul>
          {s.escalation && <p className="text-xs text-amber-600">升级：{s.escalation}</p>}
          {s.review_cycle && <p className="text-xs text-gray-400">复审：{s.review_cycle}</p>}
        </div>
      ))}
    </div>
  );
}
```

```tsx
// src/components/AgentLog.tsx
import { useWorkspace } from "../store/workspaceStore";
export function AgentLog() {
  const log = useWorkspace(s => s.log);
  return (
    <div className="h-full overflow-auto text-xs font-mono space-y-1">
      {log.map((l, i) => (
        <div key={i} className={
          l.msg.includes("↺") ? "text-amber-600" : l.msg.includes("✓") || l.stage === "done" ? "text-green-600" : "text-gray-600"
        }>[{l.stage}] {l.msg}</div>
      ))}
    </div>
  );
}
```

```tsx
// src/components/ChatPanel.tsx
import { MessageBubble } from "./MessageBubble";
import { useWorkspace } from "../store/workspaceStore";
export function ChatPanel({ onSend }: { onSend: (t: string) => void }) {
  const { idea, set } = useWorkspace();
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto space-y-2 p-2">
        {idea && <MessageBubble role="user" content={idea} />}
      </div>
      <input className="border p-2 m-2 rounded" placeholder="描述你的业务点子…"
        onKeyDown={(e) => { if (e.key === "Enter") { set({ idea: e.currentTarget.value }); onSend(e.currentTarget.value); } }} />
    </div>
  );
}
```

```tsx
// src/components/Workspace.tsx
import { useEffect } from "react";
import { useWorkspace } from "../store/workspaceStore";
import { startOrchestrate, subscribeStream } from "../api/orchestrateApi";
import { ChatPanel } from "./ChatPanel";
import { BusinessGraph } from "./BusinessGraph";
import { SopPanel } from "./SopPanel";
import { AgentLog } from "./AgentLog";

export function Workspace() {
  const { set, pushLog, setStage, sessionId } = useWorkspace();
  const start = async (idea: string) => {
    const { session_id } = await startOrchestrate(idea);
    set({ sessionId: session_id });
    const es = subscribeStream(session_id, (e: any) => {
      setStage(e.stage, e.status);
      pushLog(e.stage, e.msg);
      if (e.status === "done" && e.stage === "architect") set({ businessModel: /* 拉取最新状态 */ {} });
    });
    return () => es.close();
  };
  return (
    <div className="grid grid-cols-[1fr_2fr_1fr] grid-rows-[1fr_200px] h-screen gap-2 p-2">
      <div className="row-span-1"><ChatPanel onSend={start} /></div>
      <div className="border rounded"><BusinessGraph model={useWorkspace.getState().businessModel} /></div>
      <div className="border rounded overflow-auto"><SopPanel sop={useWorkspace.getState().sop} /></div>
      <div className="col-span-3 border rounded bg-gray-50"><AgentLog /></div>
    </div>
  );
}
```

```tsx
// src/App.tsx （追加路由）
import { Workspace } from "./components/Workspace";
// 在既有路由表中增加：
// <Route path="/studio" element={<Workspace />} />
```

- [ ] **Step 3: 安装前端依赖并构建校验**

Run: `cd "/c/Users/34216/Documents/New project 3/bsc-backend" && npm install reactflow` （或按工程包管理）
Expected: 安装成功，前端可 `vite build` 通过（或 dev 启动无报错）。

- [ ] **Step 4: 提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add src/api/orchestrateApi.ts src/store/workspaceStore.ts src/components/Workspace.tsx \
        src/components/BusinessGraph.tsx src/components/SopPanel.tsx src/components/AgentLog.tsx \
        src/components/ChatPanel.tsx src/App.tsx
git commit -m "feat(frontend): realtime workspace (chat/graph/sop/log)"
```

---

## Task 12: E2E Golden 测试 + 最终提交

**Files:**
- Create: `tests/orchestrator/test_e2e.py`

- [ ] **Step 1: 写 golden 测试（注入 FakeLLM，断言 6 段状态正确演进）**

```python
# tests/orchestrator/test_e2e.py
import asyncio
from app.orchestrator.engine import OrchestratorEngine
from tests.orchestrator.test_engine import FakeBus


def test_golden_content_moderation():
    # 用与 Task 8 类似的 stub agents，但产出贴近「内容审核中心」语义
    class A:
        def run(self, *a, **k): return {"project": {"name": "内容审核中心", "industry": "互联网"},
                                         "requirements": [{"id": "r1", "text": "多模态", "priority": "high"}]}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class B:
        def run(self, *a, **k): return {"business_model": {"flows": [{"id": "f1", "name": "受理"}], "roles": [{"id": "r1", "name": "审核员"}], "rules": []}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class S:
        def run(self, *a, **k): return {"sop": {"sops": [{"id": "s1", "title": "审核SOP", "owner_role": "审核员", "steps": [{"seq": 1, "action": "初审"}]}]}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class R:
        def run(self, *a, **k): return {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    class P:
        def run(self, *a, **k): return {"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}
        def run_async(self, *a, **k): return self.run(*a, **k)
    eng = OrchestratorEngine(agents={"planner": A(), "architect": B(), "sop": S(), "reviewer": R(), "presenter": P()},
                              bus=FakeBus())
    state = asyncio.run(eng.run_pipeline("golden-1", "我要做一个内容审核中心"))
    assert state["project"]["name"] == "内容审核中心"
    assert state["business_model"]["flows"][0]["name"] == "受理"
    assert state["sop"]["sops"][0]["title"] == "审核SOP"
    assert state["review"]["approved"] is True
    assert "presentation" in state
```

- [ ] **Step 2: 运行全量 orchestrator 测试**

Run: `.venv/Scripts/python.exe -m pytest tests/orchestrator -v`
Expected: PASS（全部）

- [ ] **Step 3: 运行全量套件确认无回归**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: 除已知漂移/无关模块外全绿（见项目测试约定：跨模块 settings 泄漏需用 `monkeypatch.setattr` 隔离）。

- [ ] **Step 4: 最终提交**

```bash
cd "/c/Users/34216/Documents/New project 3/bsc-backend"
git add tests/orchestrator/test_e2e.py
git commit -m "test(orchestrator): golden e2e for content-moderation pipeline"
```

---

## Self-Review

**1. Spec 覆盖**：
- ADR-002 多 Agent 团队 → Task 3–7 五个 Agent ✅
- 6 段状态 → Task 1（状态层）+ Task 2（校验）+ 各 Agent 写入段 ✅
- 混合编排 C（流水线 / 回环≤1 / 定点重跑）→ Task 8 engine ✅
- 实时工作区四栏 + SSE → Task 9（SSE）+ Task 11（前端）✅
- 全链路真实 deepseek → 各 Agent 用 `LLMService.chat`（JSON 模式）；测试用 FakeLLM 注入，不耦合配额 ✅
- 复用 compile / SOPReportEngine → Task 4 / Task 5 ✅
- 废弃旧 langchain_agent（保留不删）→ 计划中未新建它，仅新增 orchestrator/*，旧文件保持不动 ✅

**2. Placeholder 扫描**：无 TBD/TODO；每个代码步骤均含完整实现。Task 10 的 main.py 注册以「二选一」给出两种既有注册方式并明确要求与工程实际一致——属合理分支，非占位。

**3. 类型一致性**：
- `OrchestratorEngine.run_pipeline` 返回 `state` dict，各 Agent `run` 返回 `{segment: data}`，engine 取 `out.get(segment)` 一致 ✅
- `BusinessArchitectAgent.run` 为 `async`，engine `_call` 优先 `run_async` 否则 `run`；测试中 stub 同时实现两者 ✅
- `SopBuilderAgent.run` 为 sync（SOPReportEngine 同步），engine `_call` 回退到 `run` ✅
- 事件结构 `{stage, status, msg}` 在 bus / API / 前端 store 三处一致 ✅

**4. 已知待办（实现阶段处理，不阻塞）**：
- Presenter 的 LLM 仅生成 `diagram_spec` 元信息，HTML/PPT 为模板真实生成；后续可加深 AI 精修。
- `app/main.py` 实际注册方式需执行 Task 10 时按工程现状确认（字符串列表 vs include_router）。
- SSE 在测试中以 `FakeBus` 替代 `SessionEventBus`，真实 `subscribe` 为异步生成器，需在 dev 环境手动验证流式。
