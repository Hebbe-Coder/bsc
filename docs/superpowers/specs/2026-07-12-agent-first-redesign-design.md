# BSC 端到端重构设计：多 Agent 团队编排的 Vibe Coding 工作区

- 日期：2026-07-12
- 状态：Approved（设计已于 2026-07-12 经用户拍板；经自审 + 用户复核后进入实现规划）
- 作者：架构通（Software Architect）+ 用户共创
- 关联分支：`feature/agent-first-redesign`（自 `feature/mcp-real-llm` 切出）
- 关联工作：MCP 真实 deepseek 接入（commit `527a896`）、Round 3 安全加固、T1 状态层（commit `f52e3c1`）
- **取代**：原 ADR-001（单 Agent Loop → Tools）已被本设计推翻——用户明确：真正的 Vibe Coding 不是「用户→Agent→结果」，而是「用户→AI 团队→结果」。

---

## ADR-002：以「Orchestrator + 5 Agent 团队」重构 BSC 为实时共创工作区

### Status
Approved

### Context
用户对原 Agent-first（单 Agent Loop）方向不满意，核心诉求升级为：
- **不是单个 Agent 在循环调工具**，而是**一支专职 Agent 团队**在 Orchestrator 指挥下协作：Planner → Business Architect → SOP Builder → Reviewer → Presenter。
- **画布定位必须升级**：原设计把画布当「Business System 展示」（太弱）；Vibe Coding 的画布应是**实时工作区**——左聊天 / 中业务架构图 / 右 SOP / 底 Agent 执行日志，实时显示每个 Agent 在干什么（✓ 正在识别行业 / ✓ 正在构建流程…），让用户感觉「在指挥一个团队」。
- **状态结构必须扩展**：从 `{business_system, sop}` 两字段，扩展为 6 段 `{project, requirements, business_model, sop, review, presentation}`，每段由对应 Agent 专职产出。

既有资产已就绪：`compile_to_business_system_async`（编译引擎）、`SOPReportEngine`、真实 deepseek 的 `LLMService`、`ProjectDraftRepository`（T1 已提交，仅 `business_system`/`sop` 两字段，本设计扩展为 6 段）、前端 `ChatInterface`/`presentationStore`/`MessageBubble`/`bscApi.ts`。

### Decision
采用 **多 Agent 团队编排**架构：

1. **Orchestrator（总指挥）**是唯一持有会话状态、唯一对接前端实时流（SSE）的进程。它**不亲自干业务活**，只做派发阶段 → 收集结构化产出 → 写 6 段状态 → 推进度 → 处理回环/重跑 → 推送实时日志。
2. **5 个专职 Agent** 各自只吃自己那段输入、只写自己那段状态，互不直接调用，全靠 Orchestrator 传状态：
   - **Planner**：理解目标/边界/组织结构/规模 → 写 `project` + `requirements`
   - **Business Architect**：业务建模 → 写 `business_model`（复用 `compile_to_business_system_async` 作内部引擎）
   - **SOP Builder**：生成 SOP → 写 `sop`（复用 `SOPReportEngine` 作内部引擎）
   - **Reviewer**：找漏洞（缺复审/升级机制/SLA）→ 写 `review`，可触发受控回环
   - **Presenter**：汇报材料 → 写 `presentation`（真实生成 HTML 汇报页 + PPT）
3. **混合编排（C）**：主干固定流水线（Planner→BA→SOP→Reviewer→Presenter），允许两种受控偏离——① Reviewer 发现 high 级漏洞时**回环一次**给 BA/SOP 重做；② 用户显式指令（「只改第 3 步 SOP」）时**定点重跑单节点**。
4. **实时工作区画布**：左聊天 / 中 React Flow 真实交互图（从 `business_model` 渲染）/ 右 SOP 面板 / 底 Agent 执行日志（SSE 流式）。
5. **全链路真实（A）**：5 Agent 全接真实 deepseek（已充值，走 `LLMService`），中栏真实交互图，Presenter 真出 HTML + PPT；无 mock 默认。

### Consequences
- **变容易**：用户从「跟一个 Agent 填表」变为「指挥一支团队」；6 段状态让每段产出职责清晰、可单测、可独立重跑；实时日志 + 真实交互图直接兑现「团队在干活」的体感。
- **变困难 / 代价**：编排层工程复杂度高于单 Agent Loop；5 次真实 LLM 调用链路最长、最易出意外；回环/重跑需严谨护栏防失控；React Flow 中栏比静态卡片工作量大。
- **可逆性**：Orchestrator 与 5 Agent 为纯新增模块；旧 `app/core/langchain_agent.py`（单 Agent Loop）标记废弃但保留，不删除；内部引擎（`compile_to_business_system_async`/`SOPReportEngine`）不动。

---

## 1. 目标与非目标

### 目标（MVP 必须）
1. 用户用一句话描述点子（如「我要做一个内容审核中心」），Orchestrator 驱动 5 Agent 团队逐步产出 6 段状态。
2. 每段状态由专职 Agent 以**结构化 JSON** 产出，可持久化、可独立重跑。
3. 提供**实时工作区画布**：左聊天 / 中 React Flow 业务架构图 / 右 SOP / 底 Agent 执行日志，实时显示团队进度。
4. 全链路真实 deepseek；回环/重跑受控；遇 402/限流/超时**优雅降级、绝不卡死**。
5. Reviewer 发现 high 级漏洞可**回环一次**打回 BA/SOP；用户可**定点重跑**任意单节点。

### 非目标（阶段二及以后）
- MCP `chat` 工具作为第二交付面（Orchestrator 可再挂 MCP，但 MVP 聚焦 Web 实时工作区）。
- 根治引擎层「套模板」根因（阶段二专项）。
- 多项目/协作、画布自由拖拽布局持久化、知识库召回升级（需 embedding key）。
- SOP/PPT 的二次 AI 精修（MVP 先用结构化模板生成，后续加深）。

---

## 2. 总体架构

```
[实时工作区画布]  Vite/React/Tailwind（集成现有前端）
  左聊天 │ 中 React Flow 业务架构图 │ 右 SOP │ 底 Agent 执行日志(SSE)
                         │  POST /api/orchestrate  +  GET /api/orchestrate/stream (SSE)
                         ▼
[Orchestrator]  app/orchestrator/orchestrator.py（新增，总指挥）
   ├─ 持有会话状态（6 段 ProjectDraft）
   ├─ 按混合流水线派发：Planner → BA → SOP → Reviewer → Presenter
   ├─ 处理回环(≤1) / 定点重跑
   └─ 通过 SSE 推送阶段事件（start/done/progress）
       │  （每个 Agent 只吃自己那段输入、只写自己那段状态）
       ▼
[5 个专职 Agent]  app/agents/*.py（新增，签名 run(ctx, llm) -> dict）
   Planner | BusinessArchitect | SopBuilder | Reviewer | Presenter
       │  （内部按需调用既有引擎，进程内直调，不走 MCP 子进程）
[执行核]  既有：FastAPI + compile_to_business_system_async + SOPReportEngine
                     + LLMService(真实 deepseek) + KnowledgeService/RAG
       │
[状态层]  ProjectDraft（T1 已建，本设计扩为 6 段，SQLite 表 agent_project_drafts）
```

**关键决策**：旧 `app/core/langchain_agent.py`（单 Agent Loop + 6 个 PRD BaseTool）标记废弃、保留不删；其 `create_agent`/`BaseTool` 模式不再用于本设计。每个 Agent 是独立纯函数式模块，由 Orchestrator 组合，符合「用户 → AI 团队 → 结果」而非「用户 → Agent → 结果」。

---

## 3. 6 段状态模型 ↔ Agent 产出契约

统一状态对象 `ProjectDraft`（`app/agent/state.py`，在 T1 基础上扩展）含 6 段，每段由专属 Agent 写入：

| Agent | 写入段 | 产出 schema（结构化 JSON，经 `LLMService` JSON 模式产出） |
|------|--------|--------------------------------------------------------|
| **Planner** | `project` + `requirements` | 见下 |
| **Business Architect** | `business_model` | `{flows:[…], roles:[…], rules:[…]}` |
| **SOP Builder** | `sop` | `{sops:[{title, owner_role, trigger, steps[], escalation?, review_cycle?}]}` |
| **Reviewer** | `review` | `{approved:bool, gaps:[{severity,type,desc,fix,target}], loopback_target, summary}` |
| **Presenter** | `presentation` | `{html_url, ppt_path, diagram_spec}` |

各段字段定义：

```jsonc
project: {
  name: str, goal: str, industry: str,
  scope: { in_scope: [str], out_scope: [str] },
  actors: [ { role: str, description: str } ]
}
requirements: [ { id: str, text: str, priority: high|mid|low, source: str } ]
   // Planner 播种；Reviewer 发现的新需求缺口可回写 requirements 与 review
business_model: {
  flows: [ { id, name, description, steps: [str], input, output } ],
  roles: [ { id, name, responsibility, belongs_to_flow } ],
  rules: [ { id, statement, applies_to } ]
}
sop: {
  sops: [ { id, title, owner_role, trigger,
            steps: [ { seq, action, sla? } ],
            escalation?: str, review_cycle?: str } ]
}
review: {
  approved: bool,
  gaps: [ { id, severity: high|medium|low, type, desc, suggested_fix, target: ba|sop } ],
  loopback_target: "ba" | "sop" | null,
  summary: str
}
presentation: { html_url: str, ppt_path: str, diagram_spec: { flows, roles, rules } }
```

`project` / `requirements` 由 Planner 拥有；`review` 的 `loopback_target` 驱动受控回环；`presentation.diagram_spec` 是 `business_model` 的镜像，供中栏 React Flow 直接消费。

---

## 4. 实时工作区画布（四栏 + 实时日志）

复用并扩展现有前端工程（`src/` 已有 `ChatInterface`/`presentationStore`/`MessageBubble`/`bscApi.ts`）：

- **左：聊天**——用户指令 + Agent 追问，复用 `MessageBubble`；指令经 `POST /api/orchestrate` 进入 Orchestrator。
- **中：React Flow 真实交互图**——从 `business_model.{flows, roles, rules}` 渲染可拖拽流程图（flow 为节点、role 为泳道/分组、rule 为边注释）；节点随 BA 推进逐个点亮 ✓。
- **右：SOP 面板**——从 `sop.sops` 渲染可折叠步骤卡，含 owner / trigger / SLA / 升级机制 / 复审周期。
- **底：Agent 执行日志**——Orchestrator 经 SSE 流式推送：`✓ Planner 正在识别行业 → ✓ BA 正在构建流程 → ✓ SOP Builder 正在生成 SOP → ⚠ Reviewer 发现缺口：缺 SLA → ↺ 打回 BA 重做 → ✓ 重新生成`。

复用现有 `presentationStore.pipelineStages` 作为进度骨架，扩展为 5 Agent 阶段（planner / architect / sop / reviewer / presenter），每个阶段携带 `status: pending|running|done|loopback` 与实时日志条目。

---

## 5. 编排引擎（混合模式 C）

- **主干固定流水线**：Planner → BA → SOP → Reviewer → Presenter。Orchestrator 顺序派发，每步：读上游状态 → 调 Agent → 校验产出 schema → 写对应段 → 推 SSE 事件。
- **受控回环（≤1 次）**：Reviewer 产出 `approved=false` 且存在 `severity=high` 的 gap、`loopback_target` 指向 `ba` 或 `sop` → Orchestrator 打回对应 Agent 重做**一次**，重跑后再次 Reviewer；若仍 `approved=false` → 标记 `human_review_needed=true`，停止回环，绝不无限循环。
- **定点重跑**：用户显式指令（如「只改第 3 步 SOP」）→ Orchestrator 在已有 `business_model` 上重跑 SOP Builder（或指定单 Agent），patch 对应段，重推 SSE 日志；不重跑上游。
- **实时流（SSE）**：新增 `GET /api/orchestrate/stream?session_id=`；Orchestrator 把阶段事件（start/done/progress/loopback）以 `text/event-stream` 推送，前端增量渲染日志与进度。
- **状态持久化**：每步写回 `ProjectDraft`（扩展自 T1），断点可恢复。

---

## 6. 技术栈与复用件迁移

- **后端**：FastAPI（已有）。每个 Agent = `app/agents/<name>.py`，签名 `async def run(ctx: AgentContext, llm) -> dict`，用 `LLMService.chat`（真实 deepseek + JSON 模式）产出结构化结果；纯函数式、无副作用（只通过 `ctx` 读写状态）。
- **Orchestrator**：`app/orchestrator/orchestrator.py` + `app/orchestrator/engine.py`（流水线/回环/重跑状态机）+ `app/orchestrator/sse.py`（事件流）。
- **状态层**：扩展已提交 T1 `app/agent/state.py` 的 `ProjectDraft` / `ProjectDraftRepository` 至 6 段（原 `business_system` 演进为 `business_model`，保留 `sop`，新增 `project`/`requirements`/`review`/`presentation`）；不重写，仅加字段 + 扩展 `patch` 支持 6 段。
- **复用内部引擎**：`compile_to_business_system_async` 作为 BA 的内部编译步骤；`SOPReportEngine` 作为 SOP Builder 的内部生成步骤——均进程内直调。
- **前端**：React 18 + TS + Vite + Tailwind + zustand（已有）；新增 React Flow 中栏、SOP 右栏、底部日志组件；SSE 用 `EventSource`。
- **真实 LLM**：接入已修好的真实 deepseek（`LLMService`），无 mock 默认；`LLMService` 既有回退仅作熔断保险。

---

## 7. MVP 范围与构建顺序

MVP = 全链路真实（用户选 A）：5 Agent 全接真实 LLM、中栏真实交互图、Presenter 真出 HTML + PPT。增量构建（每个切片都真，便于逐步验收）：

1. **状态层扩 6 段 + Orchestrator 骨架 + SSE 事件流**：跑通「派发→写状态→推日志」空壳（Agent 先用透传占位，验证编排与实时流）。
2. **Planner Agent（真实 LLM）** → 写 `project` + `requirements`。
3. **Business Architect Agent（真实 LLM，内部用 `compile_to_business_system_async`）** → 写 `business_model` + React Flow 中栏渲染。
4. **SOP Builder Agent（真实 LLM，内部用 `SOPReportEngine`）** → 写 `sop` + 右栏。
5. **Reviewer Agent（真实 LLM）** → 写 `review` + 回环逻辑联调。
6. **Presenter Agent（真实 LLM）** → 写 `presentation` + 真出 HTML 汇报页（python-pptx 生成 PPT）。
7. **四栏画布整合** + 底部实时日志联动。
8. **定点重跑 + 回环联调 + E2E 测试**。

> Presenter 的 PPT 用 `python-pptx` 由 6 段状态直接生成（阶段二再加深 AI 精修）；HTML 汇报页为主交付。

---

## 8. 错误处理与护栏

- **引擎/LLM 失败·超时**：Agent 层 try/except；`LLMService` 既有回退仅作熔断保险（已知坑：此前 deepseek 欠费曾全程回退 mock，现已充值）；单 Agent 超时则 Orchestrator 标记该段 `failed` 并推告警日志，不向上抛异常中断整条流水线。
- **回环失控护栏**：回环严格 ≤1 次；超过即 `human_review_needed=true` 停止。
- **定点重跑护栏**：仅允许重跑已存在上游状态的单节点；禁止凭空重跑 Planner（需用户提供新指令）。
- **schema 校验**：每个 Agent 产出先经 JSON schema 校验，非法则重试一次（带修正提示），仍非法则标记该段 `failed`。
- **鉴权**：`/api/orchestrate` 与 `/api/orchestrate/stream` 受 `AuthMiddleware` + `RateLimitMiddleware` 保护，与既有端点一致。
- **Agent 失控护栏**：单 Agent 单次 LLM 调用上限、整体流水线超时；防止模型自循环。

---

## 9. 测试策略

- **单测**（复用既有 pytest + `TestClient` + `monkeypatch` 隔离全局 settings 套路）：
  - 每个 Agent：`run()` 在注入 mock `llm` 下断言产出 schema 正确（不依赖真实 LLM）。
  - Orchestrator：脚本化阶段序列，断言 6 段状态正确演进 + SSE 事件序列。
  - 回环：构造 `review.approved=false & high` 断言打回一次后停止。
  - 定点重跑：断言仅目标段被 patch、上游不变。
- **集成（golden）**：给定「内容审核中心」多轮输入，断言最终 6 段状态 + 画布数据源正确；真实 LLM 路径用独立标记用例（避免套件耦合欠费风险）。
- **前端**：画布渲染 draft 的冒烟校验为主，手动 + 关键组件单测（React Flow 节点生成、SOP 卡渲染）。
- 不新增测试框架，沿用 `pytest.ini` / `tests/` 现有结构。

---

## 10. 显式权衡（Trade-off）

| 决策 | 得到 | 放弃 |
|------|------|------|
| 多 Agent 团队（非单 Agent Loop） | 最像「指挥团队」、职责清晰可单测 | 编排层更复杂、确定性更需护栏 |
| 混合编排 C（非纯动态） | 默认确定、可测，保留有限团队动态感 | 不如纯 LLM 动态灵活 |
| 全链路真实 A（非骨架+mock） | 真智能、不糊弄 | 首版周期最长、链路最易出意外 |
| 中栏真实交互图（非卡片） | 团队感最强 | React Flow 工作量最大 |
| 废弃旧 langchain_agent（保留不删） | 架构干净、方向一致 | 留一份废弃代码（可接受，便于回退） |

---

## 11. 风险与开放项

- **R1 编排失控**：靠 §8 护栏（回环≤1、超时、schema 校验）+ golden 测试约束。
- **R2 画布与状态不同源**：所有写入口经 Agent→Orchestrator 写 6 段状态，画布只读状态渲染，保证单一事实源。
- **R3 React Flow 数据映射**：`business_model` → 图的节点/边映射在实现阶段敲定（用 `diagram_spec` 镜像解耦）。
- **R4 引擎「套模板」**：MVP 不根治，靠真实 deepseek + Reviewer 缓解，阶段二专项。
- **开放项**：MCP `chat` 是否接入 Orchestrator、PPT 精修程度、SSE 鉴权粒度——实现规划阶段定。
