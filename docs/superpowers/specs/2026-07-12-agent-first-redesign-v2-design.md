# ADR-003: 多 Agent 团队编排 v2 — 对话驱动 + 分叉汇聚 DAG

## Status

**Proposed** — 取代 **ADR-002**（2026-07-12 批准的线性 5-Agent 流水线）。

ADR-002 已落地（T1–T12 合入 `master`，orchestrator 套件 22 passed）。本 ADR 在其之上做拓扑升级，不推翻其状态层 / 校验 / Agent 基类 / SSE 等已验证基建。

---

## Context

ADR-002 交付的是一条**线性管道**：

```
User → Planner → Business Architect → SOP Builder → Reviewer → Presenter → Workspace
```

6 段状态：`project / requirements / business_model / sop / review / presentation`。

它在生产中暴露了四个局限，促使本 ADR：

1. **无多轮对话**：`ChatPanel` 只把一次性 `idea` 丢给 Planner，用户无法在生成前澄清、生成后定点追问。需求澄清逻辑被硬塞进 Planner 的 system prompt。
2. **缺 KPI 与 Risk 能力**：产物只有业务模型 / SOP / 汇报，没有可度量的 **KPI** 和 **风险** 视图——而这恰是「业务系统」交付的核心价值。
3. **可并行的活被串行化**：SOP 与 KPI 在逻辑上互不依赖（都只吃 Business Model），却被强制排成前后序，白白多等一轮 LLM 延迟。
4. **Presenter 概念偏窄**：最终产物只叫 `presentation`，未区分「汇报/报告（report）」这一更通用的交付物。

因此本 ADR 把拓扑从「线性管道」升级为「**对话层 + 分叉-汇聚 DAG**」，并把状态从 6 段扩到 **9 段**。

---

## Decision

### 1. 目标拓扑（修正 DAG）

```
User
  │
  ▼
Conversation Agent          ← 新增：多轮对话 / 需求澄清 / 生成触发
  │  (收敛出 brief 后触发)
  ▼
Planner Agent
  │
  ▼
Business Architect          ← 先出业务模型（SOP/KPI 的共同上游）
  │
  ├──────────────┐
  ▼              ▼
SOP Architect   KPI Architect   ← 并行（fork），都吃 business_model
  └──────┬───────┘
         ▼
     Risk Architect            ← 汇聚（join）：吃 business_model + sop + kpi
         │
         ▼
    Reviewer Agent             ← 可 ↺ 打回 business / sop / kpi / risk（回环 ≤ 1）
         │
         ▼
   Report Architect            ← 取代 Presenter，产出 report
         │
         ▼
      Workspace
```

**相对用户原图的修正（关键决策）**：用户原图让三路 Architect 都直接从 Planner 分叉。但 **SOP 与 KPI 在语义上依赖 Business Model**——没有业务模型，SOP/KPI 只能基于需求空跑，产物会偏 shallow。故改为 `Planner → Business → (SOP ∥ KPI)` 的真实 DAG 依赖序，既解开依赖矛盾，又保留并行降延迟的好处。

### 2. 编排模式

| 机制 | 说明 | 与 ADR-002 的差异 |
|------|------|------------------|
| **fork-join 并行** | Business 之后 `asyncio.gather(SOP, KPI)` 并发执行 | ADR-002 全串行 |
| **受控回环 ≤ 1** | Reviewer 的 `loopback_target` 可为 `business/sop/kpi/risk` 任一；打回后重跑该节点 + 其下游闭包，再复审一次即止 | ADR-002 仅能打回 `business/sop` |
| **下游闭包重跑** | 定点重跑某节点时，自动级联重跑其下游（如重跑 KPI → 必重跑 Risk → Reviewer → Report） | ADR-002 `rerun_node` 只重跑单节点 |
| **对话驱动入口** | Conversation Agent 持有会话轮次；用户说「生成」或意图判定为 ready 才触发 DAG；生成后可追问做定点重跑 | ADR-002 入口是一次性 `run_pipeline(idea)` |

**回环预算**：保留 `≤ 1` 以防无限循环；若后续需要更激进修复，可升到 `≤ 2`，但需在 Reviewer 契约里约束「第二次必须 approved」。

### 3. 九段状态模型

> 段数更正：上一轮沟通估算为「8 段」系笔误；准确为 **9 段**（6 基础段中 `presentation`→`report` 为改名不增不减，再加 `conversation`/`kpi`/`risk`）。

| 段 | 写入者 | 形态（schema 草图） | 说明 |
|----|--------|---------------------|------|
| `conversation` | Conversation | `{turns:[{role,content,ts}], intent:"eliciting"\|"ready"\|"editing", brief:str}` | 多轮对话记录 + 收敛后的需求简述（喂 Planner） |
| `project` | Planner | `{name, goal, industry, ...}` | 不变 |
| `requirements` | Planner / Conversation | `[{id, text, priority}]` | 不变 |
| `business_model` | Business Architect | `{flows:[...], roles:[...], rules:[...]}` | 不变 |
| `sop` | SOP Architect | `{sops:[{id,title,owner_role,steps,escalation,review_cycle}]}` | 不变 |
| `kpi` | **KPI Architect（新）** | `{kpis:[{id,name,dimension,definition,formula,target,owner_role,data_source}]}` | 新增：可度量指标 |
| `risk` | **Risk Architect（新）** | `{overall_score:"low"\|"medium"\|"high", risks:[{id,category,description,likelihood,impact,mitigation,owner_role}]}` | 新增：风险汇总 |
| `review` | Reviewer | `{approved, gaps:[{severity,target}], loopback_target, summary}` | `gaps[].target` 现可指 `business/sop/kpi/risk` |
| `report` | Report Architect | `{html_url, ppt_path, diagram_spec}` | ADR-002 的 `presentation` 改名而来 |

`ProjectDraft`（`app/agent/state.py`）需新增三列：`conversation` / `kpi` / `risk`，并把 `presentation` 列改名 `report`（迁移策略同 ADR-002 T1：比对列名后 `DROP+CREATE` 或 `ALTER`，优先无损 `ALTER TABLE ... ADD COLUMN`）。`validate_segment`（`app/orchestrator/schemas.py`）需补 `ConversationModel` / `KpiModel` / `RiskModel` / `ReportModel` 校验器。

### 4. Conversation 层设计

采用**「对话前置、DAG 后置」**的干净分离（而非让 Conversation 包裹整个 DAG）：

- **Eliciting 态**：用户与 Conversation Agent 多轮对话，每轮追加到 `conversation.turns`，Agent 用轻量意图判定是否信息充分。
- **触发**：用户显式说「生成 / go」**或** 意图判定 `ready` → 调用 `engine.run_dag(session_id, brief=conversation.brief)`，进入 DAG。
- **Editing 态**：DAG 跑完后，用户可说「把 KPI 改一下」「风险再严一点」→ `engine.rerun_node(session_id, "kpi")`，引擎自动级联重跑 `Risk → Reviewer → Report`，结果回灌 `conversation` 并推送 SSE。

**可重放性**：`conversation.turns` 是纯追加日志，DAG 输入输出都落库，任何时刻可重放整段会话，利于调试与审计。

### 5. Agent 职责契约（新增 / 变更）

| Agent | 入参（run） | 产出段 | 备注 |
|-------|------------|--------|------|
| ConversationAgent | `(session_id, message, state)` | `conversation` | LLM 驱动；可选挂 `commit_requirements` 工具 |
| PlannerAgent | `(idea / brief)` | `project` + `requirements` | 输入由 conversation.brief 提供 |
| BusinessArchitectAgent | `(idea, project, requirements, _compile)` | `business_model` | 不变（async） |
| SOPBuilderAgent | `(business_model, _engine)` | `sop` | 不变 |
| **KPIArchitectAgent（新）** | `(business_model, sop=None, _llm=None)` | `kpi` | 纯新增 |
| **RiskArchitectAgent（新）** | `(business_model, sop, kpi, _llm=None)` | `risk` | 纯新增，汇聚三路 |
| ReviewerAgent | `(project, business_model, sop, kpi, risk)` | `review` | 入参扩增，gap.target 泛化 |
| ReportArchitectAgent | `(session_id, state, out_dir)` | `report` | 即 ADR-002 Presenter，改名 + 纳入 kpi/risk 摘要 |

`BaseAgent` 抽象（T3–T7 已落地）直接复用；新 Agent 只需实现 `name` / `system_prompt` / `output_schema` 三属性与 `run`。

### 6. 引擎改造点（`app/orchestrator/engine.py`）

1. `STAGES` 由线性列表升级为 **DAG 依赖表**：`{"business":[], "sop":["business"], "kpi":["business"], "risk":["sop","kpi"], "reviewer":["risk"], "report":["reviewer"]}`。
2. 新增 `run_dag(session_id, brief)`：拓扑排序后执行；到 `sop`/`kpi` 节点用 `asyncio.gather` 并行。
3. 新增 `run_conversation_turn(session_id, message)`：追加 turn → 意图判定 → 触发 `run_dag` 或 `rerun_node`。
4. `rerun_node(session_id, node)` 改造：计算**下游闭包**（含自身到 `report` 的路径），逐节点重跑，末位重跑 `reviewer`（受回环预算约束）。
5. 回环逻辑泛化：`loopback_target` 支持 `business/sop/kpi/risk`；重跑目标 + 下游闭包 + 再复审。
6. SSE 事件：在 ADR-002 的 `stage/status/msg` 基础上，新增 `conversation` 类型事件（turn 落库、意图变化）。

### 7. 前端工作区演进（`src/`）

- **ChatPanel** 升级为真正的多轮对话 UI（渲染 `conversation.turns`，显示 assistant 回复；「生成」按钮触发 DAG）。
- 新增 **KpiPanel** 与 **RiskPanel**（或并入 SopPanel 用 tab 切换）；`BusinessGraph` 可额外渲染 KPI / Risk 节点。
- `workspaceStore` 扩 `conversation / kpi / risk / report` 字段与对应 `setX` action。
- 其余（React Flow 业务图、AgentLog、vite proxy）沿用 ADR-002 T11 成果。

### 8. 测试策略

- **单测**：`KPIArchitectAgent` / `RiskArchitectAgent` / `ConversationAgent` 各配 FakeLLM stub（沿用 `tests/orchestrator/test_agents.py` 模式）。
- **引擎**：`test_dag_runs_nine_segments`（含 SOP∥KPI 并发）、`test_rerun_propagates_downstream_closure`（重跑 KPI 级联到 report）、`test_loopback_to_kpi`（打回 KPI 后通过）、`test_conversation_turn_triggers_dag`。
- **Golden E2E**：`test_e2e.py` 扩为断言全部 9 段（内容审核中心语义）。
- **回归门槛**：沿用漂移纪律——绝不提交 `app/bsc_cloud.db*` / `llm_service.py` / `sop_report_engine.py` / `protocol.py` / `archive/orphan_fork/*` / `nul`。

---

## Consequences

### 变容易的
- **产物更完整**：一次生成同时交付业务模型 + SOP + KPI + 风险 + 报告，贴合「业务系统」真实交付物。
- **延迟更低**：SOP/KPI 并行，理论省一轮 LLM 往返。
- **交互更自然**：多轮对话澄清 + 生成后定点追问，UX 显著优于一次性输入。
- **可审计**：对话日志 + 段状态全落库，可重放。

### 变难的
- **引擎复杂度上升**：从线性 `run_pipeline` 变 DAG 拓扑 + 下游闭包 + 对话状态机，代码与测试面变大。
- **状态模型膨胀**：9 段，表结构迁移 + 校验器 + 前端 store 都需同步扩展。
- **并行正确性**：SOP/KPI 必须严格只读 `business_model`、只写各自段，否则 `gather` 下有竞态；需在契约与测试里锁死。
- **成本上升**：每会话多 ~3 次 LLM 调用（KPI + Risk + Report/原 Presenter 已算在内，净增 KPI+Risk）。

### 风险
- **R1（高）**：Conversation 意图判定失误，过早/过晚触发 DAG。缓解：默认「显式『生成』才触发」，意图 ready 仅作辅助提示。
- **R2（中）**：下游闭包重跑若未正确级联，会出现「改了 KPI 但报告还是旧的」。缓解：闭包计算单测覆盖。
- **R3（中）**：并行 SOP/KPI 若误读共享可变状态，结果不确定。缓解：入参只读、产出分写，契约测试断言。

---

## 与 ADR-002 的差异对照

| 维度 | ADR-002 | ADR-003 |
|------|---------|---------|
| 拓扑 | 线性 5-Agent | 对话层 + 分叉汇聚 DAG |
| 段数 | 6 | 9（新增 conversation/kpi/risk，presentation→report） |
| 并行 | 无 | SOP ∥ KPI |
| 入口 | 一次性 `idea` | Conversation 多轮 + 触发 |
| 回环目标 | business/sop | business/sop/kpi/risk |
| 定点重跑 | 单节点 | 下游闭包级联 |
| 终态 Agent | Presenter | Report Architect |

---

## 未决问题 / 后续
- **回环预算**：保持 ≤1 还是放宽到 ≤2？本 ADR 暂定 ≤1。
- **Conversation 是否挂工具**：是否给 Conversation Agent 暴露 `commit_requirements` / `edit_segment` 工具，还是纯文本意图？建议先纯文本意图，工具化留待 v2.1。
- **实现计划**：本 ADR 通过后，应走 `writing-plans` 产出新 TDD 计划（沿用 subagent-driven，预计 12+ 任务），再进入实现。

## 参考
- ADR-002 设计 spec：`docs/superpowers/specs/2026-07-12-agent-first-redesign-design.md`（commit `7f2c03a`）
- ADR-002 实现计划：`docs/superpowers/plans/2026-07-12-agent-first-redesign.md`（commit `237360b`）
- 已落地基建：`app/agent/state.py` / `app/orchestrator/{schemas,engine,sse}.py` / `app/orchestrator/agents/*` / `app/api/orchestrate.py` / `src/` 四栏工作区
