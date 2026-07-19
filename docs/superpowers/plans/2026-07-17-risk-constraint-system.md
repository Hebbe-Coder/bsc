# Risk=Constraint System 重做 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前"关键词启发式"的风险报告，重做为基于约束的系统（Constraint System）——业务模型每个 process/role/rule 必须被至少一个约束覆盖才能放行，且每次检查写入防篡改哈希审计链；Risk 作为与 SOP 并行的节点接入 DAG。

**Architecture:** 新增 `app/constraint/` 包（纯函数式引擎 + 哈希审计链，无 LLM 依赖、可单测）；新增 `RiskArchitectAgent` 调用该引擎产出 `risk` 段；`risk` 段加入 `ProjectDraft` 状态模型与 `schemas` 校验器；引擎 `run_pipeline` 改为 DAG：Business Model 之后 `asyncio.to_thread` 并发跑 `sop` 与 `risk`（真并行），Reviewer 与 Presenter 消费 `risk`。复用既有 `BaseAgent`、`ProjectDraftRepository`、`FakeLLM` 测试桩。

**Tech Stack:** Python 3.12、Pydantic v2、asyncio（to_thread 并发）、hashlib（SHA-256 审计链）、pytest（复用 `tests/orchestrator/test_agents.py::FakeLLM`）。

**约定：** 约束的权威来源是 `requirements`（既有字段，ADR-002 已用其做覆盖率检查）。本计划把"覆盖引擎"扩展为双向：① 每个 requirement 是否被 BM/SOP 覆盖（既有 reviewer 逻辑，保留）；② **每个 BM 元素（flow/role/rule）是否被至少一个约束治理**（本计划新增，放行门槛）。

---

## File Structure

| 文件 | 责任 |
|------|------|
| `app/constraint/__init__.py` | 包导出 |
| `app/constraint/models.py` | Pydantic 模型：Constraint / ElementCoverage / CoverageReport / AuditEntry / GateDecision / RiskItem / ConstraintResult |
| `app/constraint/audit.py` | `AuditChain`：SHA-256 哈希链追加 + `verify()` 完整性校验 |
| `app/constraint/engine.py` | `evaluate(business_model, sop, requirements, risk_payload) -> ConstraintResult`：覆盖计算 + 门禁决策 + 写审计 |
| `app/orchestrator/agents/risk_architect.py` | `RiskArchitectAgent(BaseAgent)`：LLM 风险评估 + 调用 `evaluate` 产出 `risk` 段 |
| `app/orchestrator/schemas.py` | 新增 `RiskModel` 等并注册到 `_VALIDATORS["risk"]` |
| `app/agent/state.py` | `SEGMENTS` 增加 `risk`；`ProjectDraft` 增加 `risk` 字段；repo 表增加 `risk` 列 |
| `app/orchestrator/engine.py` | `run_pipeline` 改为 DAG（sop∥risk 并发）；`_save`/`_upstream_for`/`rerun_node` 增加 `risk` 与下游闭包 |
| `app/orchestrator/agents/reviewer.py` | `run` 增加 `risk` 入参（可选），prompt 纳入 risk 摘要 |
| `app/api/orchestrate.py` | `build_agents` 注册 `RiskArchitectAgent` |
| `tests/constraint/test_engine.py` | 覆盖计算 / 门禁 / 审计链单测 |
| `tests/constraint/test_audit.py` | 哈希链完整性 + 篡改检测单测 |
| `tests/orchestrator/test_risk_architect.py` | `RiskArchitectAgent` + FakeLLM 单测 |
| `tests/orchestrator/test_engine.py` | 更新 `make_engine` 加入 risk 桩；新增 DAG 并发 / 门禁 / 下游闭包测试 |

---

### Task 1: Constraint 数据模型

**Files:**
- Create: `app/constraint/__init__.py`
- Create: `app/constraint/models.py`
- Test: `tests/constraint/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/constraint/test_models.py
from app.constraint.models import (Constraint, ElementCoverage, CoverageReport,
                                    AuditEntry, GateDecision, RiskItem, ConstraintResult)


def test_constraint_result_defaults():
    r = ConstraintResult()
    assert r.overall_score == "medium"
    assert r.coverage.coverage_pct == 0
    assert r.gate.decision == "pass"
    assert r.audit == []


def test_element_coverage_flag():
    ec = ElementCoverage(element_type="flow", element_id="f1", element_name="受理",
                         governed_by=["r1"], covered=True)
    assert ec.covered is True


def test_audit_entry_fields():
    a = AuditEntry(seq=0, agent="x", action="y", input_hash="i", output_hash="o",
                   hash="h", prev_hash="p")
    assert a.seq == 0 and a.hash == "h"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/34216/Documents/New project 3/bsc-backend" && python -m pytest tests/constraint/test_models.py -v`
Expected: ERROR "ModuleNotFoundError: No module named 'app.constraint'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/constraint/__init__.py
from app.constraint.models import (
    Constraint, ElementCoverage, CoverageReport, AuditEntry,
    GateDecision, RiskItem, ConstraintResult,
)
```

```python
# app/constraint/models.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class Constraint(BaseModel):
    id: str = ""
    text: str = ""
    priority: str = "mid"          # high|mid|low
    source: str = ""
    scope: str = "business_model"  # business_model|sop|any
    owner_role: str = ""


class ElementCoverage(BaseModel):
    element_type: str = ""         # flow|role|rule
    element_id: str = ""
    element_name: str = ""
    governed_by: List[str] = Field(default_factory=list)
    covered: bool = False


class CoverageReport(BaseModel):
    elements: List[ElementCoverage] = Field(default_factory=list)
    total: int = 0
    covered: int = 0
    coverage_pct: int = 0
    uncovered_ids: List[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    seq: int
    agent: str
    action: str
    input_hash: str
    output_hash: str
    hash: str
    prev_hash: str
    timestamp: str = ""


class GateDecision(BaseModel):
    decision: str = "pass"         # pass|warn|block
    reasons: List[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    id: str = ""
    category: str = ""
    description: str = ""
    likelihood: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    owner_role: str = ""


class ConstraintResult(BaseModel):
    overall_score: str = "medium"  # low|medium|high
    risks: List[RiskItem] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    gate: GateDecision = Field(default_factory=GateDecision)
    audit: List[AuditEntry] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/constraint/test_models.py -v`
Expected: PASSED (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/constraint/__init__.py app/constraint/models.py tests/constraint/test_models.py
git commit -m "feat(constraint): add pydantic models for constraint system"
```

---

### Task 2: 哈希审计链 AuditChain

**Files:**
- Create: `app/constraint/audit.py`
- Test: `tests/constraint/test_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/constraint/test_audit.py
from app.constraint.audit import AuditChain


def test_chain_hashes_and_verifies():
    c = AuditChain()
    c.append("risk", "coverage", {"input": {"x": 1}, "output": {"pct": 100}})
    c.append("risk", "gate", {"input": {"pct": 100}, "output": {"decision": "pass"}})
    assert len(c.entries) == 2
    assert c.verify() is True


def test_tamper_detection():
    c = AuditChain()
    c.append("risk", "coverage", {"input": {"x": 1}, "output": {"pct": 100}})
    # 篡改某条记录的 output，不改 hash
    c.entries[0].output_hash = "deadbeef"
    assert c.verify() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/constraint/test_audit.py -v`
Expected: ERROR "No module named 'app.constraint.audit'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/constraint/audit.py
from __future__ import annotations
import hashlib
import json
import time
from app.constraint.models import AuditEntry

GENESIS = "0" * 64


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _stable(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


class AuditChain:
    def __init__(self):
        self.entries: list[AuditEntry] = []
        self._prev = GENESIS

    def append(self, agent: str, action: str, payload: dict) -> AuditEntry:
        seq = len(self.entries)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        inp = _sha256(_stable(payload.get("input", {})))
        out = _sha256(_stable(payload.get("output", {})))
        raw = f"{seq}|{ts}|{agent}|{action}|{inp}|{out}|{self._prev}"
        h = _sha256(raw)
        entry = AuditEntry(seq=seq, agent=agent, action=action,
                           input_hash=inp, output_hash=out,
                           hash=h, prev_hash=self._prev, timestamp=ts)
        self.entries.append(entry)
        self._prev = h
        return entry

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries:
            raw = f"{e.seq}|{e.timestamp}|{e.agent}|{e.action}|{e.input_hash}|{e.output_hash}|{prev}"
            if _sha256(raw) != e.hash:
                return False
            prev = e.hash
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/constraint/test_audit.py -v`
Expected: PASSED (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/constraint/audit.py tests/constraint/test_audit.py
git commit -m "feat(constraint): add SHA-256 hash-chained audit trail"
```

---

### Task 3: ConstraintEngine.evaluate（覆盖引擎 + 门禁）

**Files:**
- Create: `app/constraint/engine.py`
- Test: `tests/constraint/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/constraint/test_engine.py
from app.constraint.engine import evaluate


def test_full_coverage_passes():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [{"id": "r1", "name": "审核员"}],
          "rules": [{"id": "ru1", "statement": "审核员必须复核"}]}
    reqs = [{"id": "r1", "text": "审核员负责受理", "priority": "high"},
            {"id": "ru1", "text": "复核规则", "priority": "mid"}]
    res = evaluate(bm, sop={"sops": []}, requirements=reqs)
    assert res.coverage.coverage_pct == 100
    assert res.gate.decision == "pass"
    assert res.audit  # 审计链已写入


def test_uncovered_high_priority_blocks():
    bm = {"flows": [{"id": "f1", "name": "支付"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "支付风控", "priority": "high"}]  # 无元素匹配 r1
    res = evaluate(bm, sop={"sops": []}, requirements=reqs)
    assert res.coverage.coverage_pct < 100
    assert res.gate.decision == "block"
    assert any("高危" in r for r in res.gate.reasons)


def test_sop_covers_constraint():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "受理 SOP", "priority": "mid"}]
    sop = {"sops": [{"id": "s1", "title": "受理", "covers_constraints": ["r1"]}]}
    res = evaluate(bm, sop=sop, requirements=reqs)
    assert res.coverage.coverage_pct == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/constraint/test_engine.py -v`
Expected: ERROR "No module named 'app.constraint.engine'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/constraint/engine.py
from __future__ import annotations
from typing import Optional
from app.constraint.models import (Constraint, ConstraintResult, CoverageReport,
                                    ElementCoverage, GateDecision, AuditEntry)
from app.constraint.audit import AuditChain

HIGH = {"high"}


def build_constraints(requirements: list) -> list[Constraint]:
    out = []
    for r in (requirements or []):
        if isinstance(r, dict):
            out.append(Constraint(id=r.get("id", ""), text=r.get("text", ""),
                                  priority=r.get("priority", "mid"),
                                  source=r.get("source", "")))
    return out


def _elements(bm: dict) -> list[tuple]:
    els = []
    for f in bm.get("flows", []) or []:
        els.append(("flow", str(f.get("id", "")), f.get("name", "")))
    for r in bm.get("roles", []) or []:
        if isinstance(r, dict):
            els.append(("role", str(r.get("id", "")), r.get("name", "")))
    for ru in bm.get("rules", []) or []:
        if isinstance(ru, dict):
            els.append(("rule", str(ru.get("id", "")), ru.get("statement", "")))
    return els


def evaluate(business_model: dict, sop: Optional[dict] = None,
             requirements: Optional[list] = None,
             risk_payload: Optional[dict] = None) -> ConstraintResult:
    bm = business_model or {}
    constraints = build_constraints(requirements)
    sop = sop or {}
    covers = set()
    for s in sop.get("sops", []) or []:
        for cid in (s.get("covers_constraints", []) or []):
            covers.add(cid)

    elements = _elements(bm)
    ecov: list[ElementCoverage] = []
    uncovered: list[str] = []
    for (etype, eid, ename) in elements:
        low_id, low_name = eid.lower(), ename.lower()
        governed = [c.id for c in constraints
                    if c.id and (c.id in low_id or c.id in low_name)]
        covered = bool(governed) or (eid in covers)
        ecov.append(ElementCoverage(element_type=etype, element_id=eid,
                                     element_name=ename, governed_by=governed,
                                     covered=covered))
        if not covered:
            uncovered.append(f"{etype}:{eid or ename}")

    total = len(ecov)
    covered_n = sum(1 for e in ecov if e.covered)
    cov_pct = round(covered_n / total * 100) if total else 100

    high_ids = {c.id for c in constraints if c.priority in HIGH}
    reasons: list[str] = []
    decision = "pass"
    if uncovered:
        reasons.append(f"{len(uncovered)} 个业务元素未被任何约束覆盖")
        if any(e.element_id in high_ids for e in ecov if not e.covered):
            decision = "block"
            reasons.append("存在高危优先级元素未被覆盖")
        else:
            decision = "warn"
    risk_score = (risk_payload or {}).get("overall_score", "low")
    if risk_score == "high":
        decision = "block"
        reasons.append("风险评估为 high")
    elif risk_score == "medium" and decision == "pass":
        decision = "warn"

    chain = AuditChain()
    chain.append("constraint_engine", "coverage_check",
                 {"input": {"elements": total, "constraints": len(constraints)},
                  "output": {"coverage_pct": cov_pct, "uncovered": uncovered}})
    chain.append("constraint_engine", "gate_decision",
                 {"input": {"coverage_pct": cov_pct, "risk_score": risk_score},
                  "output": {"decision": decision}})

    return ConstraintResult(
        overall_score=risk_score,
        coverage=CoverageReport(elements=ecov, total=total, covered=covered_n,
                                coverage_pct=cov_pct, uncovered_ids=uncovered),
        gate=GateDecision(decision=decision, reasons=reasons),
        audit=chain.entries,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/constraint/test_engine.py -v`
Expected: PASSED (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/constraint/engine.py tests/constraint/test_engine.py
git commit -m "feat(constraint): add coverage engine + gate decision"
```

---

### Task 4: RiskArchitectAgent

**Files:**
- Create: `app/orchestrator/agents/risk_architect.py`
- Test: `tests/orchestrator/test_risk_architect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/orchestrator/test_risk_architect.py
import asyncio
from app.orchestrator.agents.risk_architect import RiskArchitectAgent


class FakeLLM:
    def chat(self, system_prompt, user_prompt, temperature=0.1, max_tokens=None, use_cache=True):
        return {"risk": {"overall_score": "medium",
                          "risks": [{"id": "rk1", "category": "compliance",
                                     "description": "缺合规", "likelihood": "low",
                                     "impact": "medium", "mitigation": "补审计",
                                     "owner_role": "法务"}]}}


def test_risk_agent_produces_risk_segment():
    bm = {"flows": [{"id": "f1", "name": "受理"}], "roles": [], "rules": []}
    reqs = [{"id": "r1", "text": "受理约束", "priority": "mid"}]
    agent = RiskArchitectAgent(llm_service=FakeLLM())
    out = agent.run(business_model=bm, requirements=reqs)
    assert "risk" in out
    assert out["risk"]["overall_score"] == "medium"
    assert out["risk"]["coverage"]["coverage_pct"] == 100  # r1 覆盖 f1
    assert out["risk"]["gate"]["decision"] in ("pass", "warn", "block")
    assert out["risk"]["audit"]  # 审计链已随段落库
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/orchestrator/test_risk_architect.py -v`
Expected: ERROR "No module named 'app.orchestrator.agents.risk_architect'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/orchestrator/agents/risk_architect.py
from __future__ import annotations
import json
from app.agents.base_agent import BaseAgent
from app.constraint.engine import evaluate as evaluate_constraints


SYSTEM_PROMPT = (
    "你是 Risk Architect Agent（约束系统）。职责：基于业务模型与可选 SOP，评估业务风险并生成风险清单。\n"
    "输入：business_model（flows/roles/rules），可选 sop、kpi。\n"
    "请产出 JSON：\n"
    '{"risk":{"overall_score":"low|medium|high",'
    '"risks":[{"id":str,"category":str,"description":str,"likelihood":"low|medium|high",'
    '"impact":"low|medium|high","mitigation":str,"owner_role":str}]}}'
)


class RiskArchitectAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Risk Architect Agent"

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def output_schema(self) -> dict:
        return {"required": ["risk"]}

    def run(self, business_model: dict, sop: dict = None, kpi: dict = None,
            requirements: list = None, context: dict = None) -> dict:
        user_prompt = (
            f"业务模型：{json.dumps(business_model, ensure_ascii=False)}\n"
            f"SOP：{json.dumps(sop or {}, ensure_ascii=False)}\n"
            f"KPI：{json.dumps(kpi or {}, ensure_ascii=False)}\n"
            f"请评估风险并产出 risk。"
        )
        risk_payload = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)
        if not isinstance(risk_payload, dict):
            risk_payload = {}
        risk_payload = risk_payload.get("risk", {})
        result = evaluate_constraints(
            business_model=business_model, sop=sop,
            requirements=requirements or [],
            risk_payload=risk_payload,
        )
        return {"risk": result.model_dump()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/orchestrator/test_risk_architect.py -v`
Expected: PASSED (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/agents/risk_architect.py tests/orchestrator/test_risk_architect.py
git commit -m "feat(agent): add RiskArchitectAgent producing constraint-system risk segment"
```

---

### Task 5: schemas 注册 RiskModel

**Files:**
- Modify: `app/orchestrator/schemas.py` (在 `Presentation` 后追加模型；在 `_VALIDATORS` 增加 `"risk"`)
- Test: `tests/orchestrator/test_risk_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/orchestrator/test_risk_schema.py
from app.orchestrator.schemas import validate_segment, RiskModel


def test_validate_risk_segment():
    data = {
        "overall_score": "low",
        "risks": [{"id": "rk1", "category": "compliance", "description": "x",
                   "likelihood": "low", "impact": "low", "mitigation": "y",
                   "owner_role": "法务"}],
        "coverage": {"total": 1, "covered": 1, "coverage_pct": 100, "uncovered_ids": []},
        "gate": {"decision": "pass", "reasons": []},
        "audit": [{"seq": 0, "agent": "risk", "action": "coverage",
                   "input_hash": "i", "output_hash": "o", "hash": "h",
                   "prev_hash": "0" * 64}],
    }
    m = validate_segment("risk", data)
    assert isinstance(m, RiskModel)
    assert m.gate.decision == "pass"
    assert m.coverage.coverage_pct == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/orchestrator/test_risk_schema.py -v`
Expected: ERROR "Unknown segment: risk" (validate_segment 抛 ValidationError)

- [ ] **Step 3: Write minimal implementation**

在 `app/orchestrator/schemas.py` 的 `Presentation` 类**之后**、`_VALIDATORS` **之前**插入：

```python
class RiskItem(BaseModel):
    id: str = ""
    category: str = ""
    description: str = ""
    likelihood: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    owner_role: str = ""


class CoverageModel(BaseModel):
    total: int = 0
    covered: int = 0
    coverage_pct: int = 0
    uncovered_ids: list = Field(default_factory=list)


class GateModel(BaseModel):
    decision: str = "pass"
    reasons: list = Field(default_factory=list)


class AuditEntryModel(BaseModel):
    seq: int
    agent: str
    action: str
    input_hash: str
    output_hash: str
    hash: str
    prev_hash: str
    timestamp: str = ""


class RiskModel(BaseModel):
    overall_score: str = "medium"
    risks: list[RiskItem] = Field(default_factory=list)
    coverage: CoverageModel = Field(default_factory=CoverageModel)
    gate: GateModel = Field(default_factory=GateModel)
    audit: list[AuditEntryModel] = Field(default_factory=list)
```

在 `_VALIDATORS` 字典中增加一行（放在 `"presentation"` 那行之后）：

```python
    "risk": RiskModel.model_validate,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/orchestrator/test_risk_schema.py -v`
Expected: PASSED (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/schemas.py tests/orchestrator/test_risk_schema.py
git commit -m "feat(schema): register RiskModel validator for risk segment"
```

---

### Task 6: state.py 增加 risk 段

**Files:**
- Modify: `app/agent/state.py`（`SEGMENTS`、`ProjectDraft`、`ProjectDraftRepository`）
- Test: `tests/orchestrator/test_state.py` 已动态遍历 `SEGMENTS`，无需改；新增 `tests/agent/test_risk_segment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_risk_segment.py
from app.agent.state import ProjectDraftRepository, ProjectDraft, SEGMENTS


def test_risk_in_segments():
    assert "risk" in SEGMENTS


def test_risk_roundtrip():
    repo = ProjectDraftRepository()
    sid = "sess-risk"
    repo.save(ProjectDraft(session_id=sid, idea="x",
                            risk={"overall_score": "low", "gate": {"decision": "pass"}}))
    got = repo.get(sid)
    assert got.risk["overall_score"] == "low"
    assert got.risk["gate"]["decision"] == "pass"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_risk_segment.py -v`
Expected: FAILED `test_risk_in_segments` ("risk" not in SEGMENTS)

- [ ] **Step 3: Write minimal implementation**

`app/agent/state.py` 改动三处：

1. 第 9 行 `SEGMENTS` 元组增加 `"risk"`：

```python
SEGMENTS = ("project", "requirements", "business_model", "sop", "risk", "review", "presentation")
```

2. `ProjectDraft.__init__` 参数与 `to_dict` / `from_row` 增加 `risk`：

```python
    def __init__(self, session_id: str = None, idea: str = "",
                 project: Optional[dict] = None, requirements: Optional[list] = None,
                 business_model: Optional[dict] = None, sop: Optional[dict] = None,
                 risk: Optional[dict] = None, review: Optional[dict] = None,
                 presentation: Optional[dict] = None,
                 status: str = "planned", messages: Optional[list] = None,
                 updated_at: Optional[str] = None):
        ...
        self.risk = risk or {}
        ...

    def to_dict(self) -> Dict[str, Any]:
        return {
            ...,
            "risk": self.risk,
            ...,
        }
```

`from_row` 中 `for seg in SEGMENTS:` 已自动反序列化 `risk`（因其为 JSON 列），无需改；确保 `d["risk"]` 兜底：在循环后补一行（与 requirements 同级兜底）：

```python
        d["risk"] = d.get("risk") or {}
```

3. `ProjectDraftRepository`：`expected_cols` 增加 `"risk"`；`CREATE TABLE` 增加 `risk TEXT`；`save` 的 INSERT/UPDATE 增加 `risk` 列与 `json.dumps(draft.risk, ensure_ascii=False)`：

`expected_cols` 改为：

```python
        expected_cols = {"session_id", "idea", "project", "requirements", "business_model",
                         "sop", "risk", "review", "presentation", "status", "messages", "updated_at"}
```

`CREATE TABLE` 改为（在 `sop TEXT,` 后加 `risk TEXT,`）：

```python
                """CREATE TABLE agent_project_drafts (
                    session_id TEXT PRIMARY KEY, idea TEXT, project TEXT, requirements TEXT,
                    business_model TEXT, sop TEXT, risk TEXT, review TEXT, presentation TEXT,
                    status TEXT, messages TEXT, updated_at TEXT
                )"""
```

`save` 的 INSERT 改为（列清单与 VALUES 各加 `risk`；参数加 `json.dumps(draft.risk, ensure_ascii=False)`）：

```python
        self._db.execute(
            """INSERT INTO agent_project_drafts
               (session_id, idea, project, requirements, business_model, sop, risk, review, presentation, status, messages, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
               idea=excluded.idea, project=excluded.project, requirements=excluded.requirements,
               business_model=excluded.business_model, sop=excluded.sop, risk=excluded.risk,
               review=excluded.review, presentation=excluded.presentation, status=excluded.status,
               messages=excluded.messages, updated_at=excluded.updated_at""",
            (draft.session_id, draft.idea,
             json.dumps(draft.project, ensure_ascii=False),
             json.dumps(draft.requirements, ensure_ascii=False),
             json.dumps(draft.business_model, ensure_ascii=False),
             json.dumps(draft.sop, ensure_ascii=False),
             json.dumps(draft.risk, ensure_ascii=False),
             json.dumps(draft.review, ensure_ascii=False),
             json.dumps(draft.presentation, ensure_ascii=False),
             draft.status, json.dumps(draft.messages, ensure_ascii=False), draft.updated_at))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_risk_segment.py tests/orchestrator/test_state.py -v`
Expected: PASSED（全部通过；`test_state.py` 因动态遍历 SEGMENTS 自动覆盖 risk）

- [ ] **Step 5: Commit**

```bash
git add app/agent/state.py tests/agent/test_risk_segment.py
git commit -m "feat(state): add risk segment to ProjectDraft and repository"
```

---

### Task 7: 引擎 DAG 化（sop ∥ risk 真并行）

**Files:**
- Modify: `app/orchestrator/engine.py`（`run_pipeline` 并发跑 sop/risk；`_save` 含 risk；reviewer 入参含 risk）
- Modify: `app/orchestrator/agents/reviewer.py`（`run` 增加 `risk` 入参）
- Test: `tests/orchestrator/test_engine.py`（更新 `make_engine` + 新增并发测试）

- [ ] **Step 1: Write the failing test**

在 `tests/orchestrator/test_engine.py` 顶部 `make_engine` 的 `agents` 字典中增加：

```python
        "risk": StubAgent({"risk": {"overall_score": "low", "coverage": {"total": 0, "covered": 0, "coverage_pct": 100, "uncovered_ids": []}, "gate": {"decision": "pass", "reasons": []}, "audit": []}}),
```

并在文件末尾新增：

```python
def test_sop_and_risk_run_in_parallel():
    import time
    eng = make_engine()

    class SlowStub:
        def __init__(self, payload, delay): self.payload = payload; self.delay = delay
        def run(self, *a, **k):
            time.sleep(self.delay)
            return self.payload
    eng.agents["sop"] = SlowStub({"sop": {"sops": []}}, 0.2)
    eng.agents["risk"] = SlowStub({"risk": {"overall_score": "low", "coverage": {"coverage_pct": 100}, "gate": {"decision": "pass"}, "audit": []}}, 0.2)
    t0 = time.perf_counter()
    asyncio.run(eng.run_pipeline("s-par", "内容审核中心"))
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.35, f"并行应 <0.35s，实际 {elapsed:.2f}s"


def test_reviewer_receives_risk():
    eng = make_engine()
    captured = {}
    class ReviewerSpy:
        def run(self, *a, **k):
            captured.update(k)
            return {"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}
    eng.agents["reviewer"] = ReviewerSpy()
    asyncio.run(eng.run_pipeline("s-risk", "内容审核中心"))
    assert "risk" in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/orchestrator/test_engine.py -v`
Expected: FAILED `test_sop_and_risk_run_in_parallel`（当前串行，耗时应 ≈0.4s 且 risk 段未生成）

- [ ] **Step 3: Write minimal implementation**

`app/orchestrator/engine.py` 的 `run_pipeline` 修改：在 architect 段之后、reviewer 之前，把原来的串行 sop 替换为并发 sop∥risk：

```python
        # FORK: sop || risk（二者仅依赖 business_model，真并行）
        await self._emit(session_id, "sop", "running", "正在生成 SOP")
        await self._emit(session_id, "risk", "running", "正在评估约束与风险（并行）")
        sop_fut = asyncio.to_thread(self._call_sync, "sop", business_model=state["business_model"])
        risk_fut = asyncio.to_thread(self._call_sync, "risk",
                                     business_model=state["business_model"],
                                     requirements=state.get("requirements", []))
        sop_out, risk_out = await asyncio.gather(sop_fut, risk_fut)
        state["sop"] = sop_out.get("sop", {})
        state["risk"] = risk_out.get("risk", {})
        self._save(session_id, state)
        await self._emit(session_id, "sop", "done", "SOP 已生成")
        await self._emit(session_id, "risk", "done", "约束与风险评估完成")
```

Reviewer 调用增加 `risk=state["risk"]`：

```python
        out = await self._call("reviewer",
                               project=state["project"], business_model=state["business_model"],
                               sop=state["sop"], risk=state["risk"],
                               requirements=state.get("requirements", []))
```

新增辅助方法（放在 `_call` 之前）：

```python
    def _call_sync(self, name, **kwargs):
        agent = self.agents[name]
        return agent.run(**kwargs)
```

`_save` 增加 `risk`：

```python
        draft = ProjectDraft(
            session_id=session_id, idea=state.get("idea", ""),
            project=state.get("project", {}), requirements=state.get("requirements", []),
            business_model=state.get("business_model", {}), sop=state.get("sop", {}),
            risk=state.get("risk", {}), review=state.get("review", {}),
            presentation=state.get("presentation", {}),
            status="running", messages=state.get("messages", []),
        )
```

`app/orchestrator/agents/reviewer.py` 的 `run` 签名增加 `risk: dict = None`，并在 `user_prompt` 中附带（最小改动：在 `f"SOP：..."` 之后加一行）：

```python
    def run(self, project: dict, business_model: dict, sop: dict,
            requirements: list = None, risk: dict = None, context: dict = None) -> dict:
        ...
        f"SOP：{json.dumps(sop, ensure_ascii=False)}\n"
        f"风险/约束系统：{json.dumps(risk or {}, ensure_ascii=False)}\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/orchestrator/test_engine.py -v`
Expected: PASSED（含新增 2 个测试；既有 3 个测试因 `make_engine` 已含 risk 桩仍通过）

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/engine.py app/orchestrator/agents/reviewer.py tests/orchestrator/test_engine.py
git commit -m "feat(engine): run sop and risk in parallel DAG fork"
```

---

### Task 8: rerun_node 下游闭包 + 支持打回 risk

**Files:**
- Modify: `app/orchestrator/engine.py`（`rerun_node` 增加 `risk` 与下游闭包；loopback 支持 `risk` 目标）
- Test: `tests/orchestrator/test_rerun.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/orchestrator/test_rerun.py
import asyncio
from app.orchestrator.engine import OrchestratorEngine


class FakeBus:
    def __init__(self): self.events = []
    async def publish(self, session_id, event): self.events.append(event)


class Stub:
    def __init__(self, payload): self.payload = payload
    def run(self, *a, **k): return self.payload


def make():
    agents = {
        "planner": Stub({"project": {"name": "x"}, "requirements": []}),
        "architect": Stub({"business_model": {"flows": [], "roles": [], "rules": []}}),
        "sop": Stub({"sop": {"sops": []}}),
        "risk": Stub({"risk": {"overall_score": "low", "coverage": {"coverage_pct": 100}, "gate": {"decision": "pass"}, "audit": []}}),
        "reviewer": Stub({"review": {"approved": True, "gaps": [], "loopback_target": None, "summary": "ok"}}),
        "presenter": Stub({"presentation": {"html_url": "u", "ppt_path": "p", "diagram_spec": {}}}),
    }
    return OrchestratorEngine(agents=agents, repo=None, bus=FakeBus())


def test_rerun_risk_propagates_to_reviewer_and_presenter():
    eng = make()
    asyncio.run(eng.run_pipeline("r1", "x"))
    # 重跑 risk 应级联 reviewer -> presenter
    out = asyncio.run(eng.rerun_node("r1", "risk"))
    assert "risk" in out
    assert "review" in out
    assert "presentation" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/orchestrator/test_rerun.py -v`
Expected: FAILED（`rerun_node` 当前拒绝 "risk"：`ValueError: 不允许重跑 risk`）

- [ ] **Step 3: Write minimal implementation**

替换 `app/orchestrator/engine.py` 的 `rerun_node` 为：

```python
    async def rerun_node(self, session_id: str, node: str) -> dict:
        """定点重跑节点，并级联其下游闭包（reviewer -> presenter）。"""
        if node not in self.agents:
            raise ValueError(f"不允许重跑 {node}")
        draft = self.repo.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        state = draft.to_dict()
        # 下游闭包（含自身）
        closure = {
            "architect": ["sop", "risk", "reviewer", "presenter"],
            "sop": ["risk", "reviewer", "presenter"],
            "risk": ["reviewer", "presenter"],
            "reviewer": ["presenter"],
            "presenter": [],
        }
        order = ["architect", "sop", "risk", "reviewer", "presenter"]
        targets = [node] + closure.get(node, [])
        seen, seq = set(), []
        for t in order:
            if t in targets and t not in seen:
                seen.add(t); seq.append(t)
        for t in seq:
            if t not in self.agents:
                continue
            await self._emit(session_id, t, "running", f"定点重跑 {t}")
            kwargs = self._upstream_for(t, state)
            out = await self._call(t, **kwargs)
            seg = {"architect": "business_model", "sop": "sop", "risk": "risk",
                   "reviewer": "review", "presenter": "presentation"}[t]
            state[seg] = out.get(seg, out)
            self._save(session_id, state)
            await self._emit(session_id, t, "done", f"{t} 已重跑")
        return state
```

`_upstream_for` 增加 `risk` 分支（在 `if node == "sop":` 之后）：

```python
        if node == "risk":
            return {"business_model": state["business_model"], "sop": state.get("sop", {}),
                    "requirements": state.get("requirements", [])}
```

loopback 支持 `risk` 目标：在 `run_pipeline` 的 `else:` 之前加一个分支：

```python
            elif target == "risk":
                await self._emit(session_id, "risk", "loopback",
                                 f"↺ 打回 Risk 重做（第{loop_count+1}次回环），需补齐 {len(high_gaps)} 项缺口")
                out = await self._call("risk", business_model=state["business_model"],
                                       sop=state["sop"], requirements=state.get("requirements", []),
                                       fix_instructions=fixes)
                state["risk"] = out.get("risk", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/orchestrator/test_rerun.py -v`
Expected: PASSED (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/engine.py tests/orchestrator/test_rerun.py
git commit -m "feat(engine): rerun risk with downstream closure + loopback target"
```

---

### Task 9: API 注册 RiskArchitectAgent

**Files:**
- Modify: `app/api/orchestrate.py`（`build_agents` 增加 `risk`）

- [ ] **Step 1: Write the failing test**

```python
# tests/orchestrator/test_build_agents.py
from app.api.orchestrate import build_agents
from app.services.llm_service import LLMService


def test_build_agents_includes_risk():
    agents = build_agents(LLMService())
    assert "risk" in agents
    assert agents["risk"].__class__.__name__ == "RiskArchitectAgent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/orchestrator/test_build_agents.py -v`
Expected: FAILED（"risk" not in agents）

- [ ] **Step 3: Write minimal implementation**

在 `app/api/orchestrate.py` 的 `build_agents` 中，import 并注册：

```python
    from app.orchestrator.agents.risk_architect import RiskArchitectAgent
    return {
        "planner": PlannerAgent(llm_service=llm),
        "architect": BusinessArchitectAgent(llm_service=llm),
        "sop": SopBuilderAgent(llm_service=llm),
        "risk": RiskArchitectAgent(llm_service=llm),
        "reviewer": ReviewerAgent(llm_service=llm),
        "presenter": PresenterAgent(llm_service=llm),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/orchestrator/test_build_agents.py -v`
Expected: PASSED (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/api/orchestrate.py tests/orchestrator/test_build_agents.py
git commit -m "feat(api): register RiskArchitectAgent in build_agents"
```

---

### Task 10: 全量回归 + 收尾

**Files:**
- Run: 全量测试

- [ ] **Step 1: Run the full orchestrator + constraint suite**

Run: `python -m pytest tests/orchestrator tests/constraint tests/agent -q`
Expected: PASSED（无回归；既有 `test_state.py` / `test_engine.py` 因扩展自动兼容）

- [ ] **Step 2: Run the entire test suite to confirm no collateral breakage**

Run: `python -m pytest -q`
Expected: 除已知的环境相关用例（需真实 API Key 的集成测试）外，全部通过。若 `test_e2e.py` / `test_real_e2e.py` 因缺 Key 失败，属预期，不在本计划范围。

- [ ] **Step 3: 冒烟验证 DAG 门禁**

可临时跑一段脚本确认 `gate.decision` 在覆盖不足时为 `block`：

```python
from app.constraint.engine import evaluate
bm = {"flows": [{"id": "f1", "name": "支付"}], "roles": [], "rules": []}
reqs = [{"id": "r1", "text": "支付风控", "priority": "high"}]
print(evaluate(bm, sop={"sops": []}, requirements=reqs).gate.decision)  # -> block
```

- [ ] **Step 4: Commit 收尾（若前面已逐任务提交，此步仅做状态同步）**

```bash
git status
```

---

## Self-Review（写完后自查）

**1. Spec coverage：**
- 覆盖引擎（每个 BM 元素被约束治理）→ Task 3 `evaluate` 已实现并单测。✅
- 门禁（coverage<100 或 risk=high 时 block/warn）→ Task 3 GateDecision。✅
- 哈希审计链（防篡改、可 verify）→ Task 2 AuditChain + Task 3 写入 audit。✅
- Risk 作为并行节点接入 DAG → Task 7 `asyncio.to_thread` 并发 sop∥risk。✅
- 下游闭包重跑 / 打回 risk → Task 8。✅
- 状态模型与校验器扩展 → Task 5/6。✅

**2. Placeholder scan：** 所有步骤均含完整代码；无 TBD / "自行补充" / "类似 Task N"。

**3. Type consistency：** `evaluate` 返回 `ConstraintResult`；`RiskArchitectAgent.run` 返回 `{"risk": result.model_dump()}`；`RiskModel` 字段与 `ConstraintResult.model_dump()` 完全一致（`overall_score/risks/coverage/gate/audit`）；`engine._save` 与 `state.SEGMENTS` 均含 `risk`。`AuditEntry`/`AuditEntryModel` 字段一致。`GateModel.decision` 取值 `pass|warn|block` 全链路统一。

**已知范围边界（YAGNI）：** KPI 段（ADR-003 的 `kpi`）本计划未实现；`RiskArchitectAgent.run` 已预留 `kpi` 入参，待 KPI Agent 落地后一行接入即可。`reviewer` 的 `loopback_target` 已支持 `risk`，但 reviewer prompt 仅把 risk 纳入上下文、未强制其产出 `risk` 目标（保持最小改动；如需强约束可在后续迭代扩展 prompt）。

---

## Execution Log（落地记录，2026-07-17）

**执行方式：** Superpowers `subagent-driven-development`（每任务独立 subagent 提交 + 两阶段复核）。

**分支：** `feat/risk-constraint-system`（从 `master` 带脏树切出，**未触碰 main/master**，保护用户其它未提交改动）。

**提交（12 个，20 文件，+639/−42；+ 评审修复 +20/−1）：**
```
847fdcd fix(constraint): propagate LLM risk list through evaluate() into ConstraintResult   [评审修复]
82be969 test(e2e): add risk stub to golden pipeline test for parallel DAG fork
ac3e4cc test(constraint): rename test_engine.py -> test_constraint_engine.py (pytest 模块名冲突)
0ba6dfe feat(api): register RiskArchitectAgent in build_agents
45ae310 feat(engine): rerun risk with downstream closure + loopback target
6c5c8e1 feat(engine): run sop and risk in parallel DAG fork
51e5851 feat(state): add risk segment to ProjectDraft and repository
cfbd325 feat(schema): register RiskModel validator for risk segment
3ebb53f feat(agent): add RiskArchitectAgent producing constraint-system risk segment
729c39a feat(constraint): add coverage engine + gate decision
aa72c48 feat(constraint): add SHA-256 hash-chained audit trail
7553de6 feat(constraint): add pydantic models for constraint system
```

**最终回归：** `venv/Scripts/python.exe -m pytest tests/orchestrator tests/constraint tests/agent -q`
→ **39 passed**（Task 10 达成 + 评审修复后复测；无回归）。
全树 collect-only：432 collected / 1 error（`tests/test_export_boundary.py` 缺 `docx` 依赖——**预存 env 问题，与本次改动无关**）。

**环境铁律：** 全局 `python` 缺 `numpy` 且 `tests/conftest.py` 顶部要求 → 所有 pytest 必须走 `venv/Scripts/python.exe`（项目 venv 解释器）。

### 执行中发现的偏差 / 纠偏（均已落地并单测覆盖）

1. **Task 3 引擎语义（实质更正）**：计划原 `evaluate()` 按 BM *元素* 计算覆盖、并对"未覆盖的元素 id"做门禁，与计划自带 3 个测试矛盾（SOP 显式覆盖的约束不计、未满足的高危需求不会 block）。修正为 **"需求满足型覆盖"**：约束满足 ⇔ BM 元素引用其 id/name **或** SOP 在 `covers_constraints` 列出；`coverage_pct = 满足数/需求总数`；任一**高危**需求未满足 → `block`，并附 `存在高危优先级约束未被满足`。
2. **Task 4 测试夹具**：计划里 flow id 写 `"f1"` + 需求 `"r1"`，在修正后引擎下覆盖到不了 100%。改为 flow id `"r1"`（让需求 r1 治理该 flow），覆盖 100%。
3. **pytest 模块名冲突**：`tests/constraint/test_engine.py` 与 `tests/orchestrator/test_engine.py` 同名 → collection 报 `import file mismatch` 中止。处理：`git mv` 前者为 `tests/constraint/test_constraint_engine.py` 并提交（ac3e4cc），所有引用同步。
4. **Task 8 risk 回环**：计划 loopback 代码对 `risk` 传 `fix_instructions=fixes`，但 `RiskArchitectAgent.run` 不接受该参数 → 会崩溃。处理：去掉 `fix_instructions`（偏差，已文档化；如需支持须先给 `RiskArchitectAgent.run` 加该参数）。
5. **Task 7 reviewer 重跑上游**：计划 `_upstream_for` 的 `reviewer` 分支未把 `risk` 传给 reviewer，导致重跑 reviewer 时丢失 risk 上下文。处理：reviewer 的 `_upstream_for` 与 `run_pipeline` 调用均注入 `risk=state["risk"]`（偏差，闭包正确性所需）。
6. **e2e 回归修复**：`tests/orchestrator/test_e2e.py` 的硬编码 agents 字典无 `risk`，Task 7 的 fork 使其 `KeyError: 'risk'`。处理：加 `class K` stub 返回 pass 级 payload，注册 `"risk": K()`，并 `assert "risk" in state`（82be969）。

### Review：finishing-a-development-branch（2026-07-17，用户选 B）

逐文件通读已提交代码（`engine.py` / `constraint/engine.py` / `risk_architect.py` / `schemas.py` / `reviewer.py` / `constraint/models.py`），整体一致、可单测、门禁逻辑正确。发现并修复 1 处真实缺陷：

- **缺陷（已修，847fdcd）**：`evaluate()` 只从 `risk_payload` 读 `overall_score`，**从不设置 `risks`** → `ConstraintResult.risks` 恒为 `[]`。`RiskArchitectAgent` 把 LLM 产出的风险清单塞进 `risk_payload` 传入，却被整体丢弃；尽管 `RiskModel.risks` 字段存在、prompt 也要求产出 risks，最终 `risk` 段里风险清单永远为空。
  - 修复：`evaluate` 增加 `rp = risk_payload or {}`、`risks = rp.get("risks", [])`，`ConstraintResult(risks=risks, ...)`；Pydantic 自动 coerce dict→`RiskItem`。
  - 新增测试：`test_risk_architect` 断言风险清单端到端存活（首条 `id == "rk1"`）；`test_constraint_engine::test_risk_list_propagates_from_payload` 锁定 `evaluate` 行为（high 风险→block 且 risks 透传）。

**复核后仍存在的设计级观察（已在 d74586f 打磨完成，非阻塞）：**
1. `CoverageReport.total/covered/coverage_pct` 度量**约束满足度**（需求满足型），而 `elements[].covered` 度量**单元素是否被治理**——两维度共用一对象易误读 → **已加 docstring 澄清双维度语义**（constraint/models.py + schemas.py）。
2. `CoverageModel`（schemas）无 `elements` 字段，经 `RiskModel` 校验时会丢 per-element 覆盖明细 → **已补 `elements: List[ElementCoverageModel]`**，新增 `test_risk_segment_preserves_element_coverage` 锁定。
3. `run_pipeline` 的 fork 直接 `self.agents["risk"]`，缺 risk 会 KeyError → **已加 guard**：fork 与 loopback 均检查 `"risk" in self.agents`，缺失时 skip risk 段（留空 `{}`）且不阻塞主链路；新增 `test_pipeline_runs_without_risk_agent` 锁定。

**状态：** 10/10 任务完成 + 评审修复 + 评审观察打磨（13 提交），**未合并 master**（需用户明确同意）。下一步：用户点头发合并。
