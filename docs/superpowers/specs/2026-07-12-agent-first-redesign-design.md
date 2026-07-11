# BSC 端到端重构设计：Agent-first 对话式业务系统共创（含可编辑画布）

- 日期：2026-07-12
- 状态：Proposed（待用户复核后进入实现规划）
- 作者：架构通（Software Architect）+ 用户共创
- 关联分支：`feature/agent-first-redesign`（自 `feature/mcp-real-llm` 切出）
- 关联工作：MCP 真实 deepseek 接入（commit `527a896`）、Round 3 安全加固

---

## ADR-001：以 Agent-first 对话式架构重构 BSC 交互范式，MVP 即含可编辑画布

### Status
Proposed

### Context
用户反馈 BSC 当前体验在四个阶段全面失效：
- **A 输入与理解**：一句话丢进去，系统没"懂"，后面全跑偏。
- **B 生成质量**：business_system / SOP 是放之四海皆准的套话，不贴领域。
- **C 交付与落地**：产物躺在 JSON/HTML 里，看不懂、改不动、接不进真实业务。
- **D 全程没有"合伙人感"**：每一步像填表/调 API，而非跟懂行搭档聊着把事办成。

用户明确选择：**(1) 端到端重构（D）**；**(2) 目标成品 = 多轮对话智能体（C）**；**(3) 打法 = Agent-first 重架构（B）**；**(4) 重画布要做，且进 MVP（A）**。

既有资产已就绪：FastAPI 后端、`compile_to_business_system_async` 编译引擎、`SOPReportEngine`（已开启 `enable_ai_analysis=True`）、`LLMService`（真实 deepseek，已验证可用）、`KnowledgeService`/`RAGAnswerGenerator`、以及已接入真实 deepseek 的 4 个 MCP 工具（`bsc_compile` / `bsc_generate_sop` / `analyze_domain` / `knowledge_ask`）。

### Decision
采用 **Agent-first** 架构：以 LLM（真实 deepseek）为总指挥的对话循环（Agent Loop）持有会话状态，按需调用一组细粒度工具（澄清 / 编译 / 生成 SOP / 改节点 / 总结），工具**进程内直接调用既有引擎**（不走 MCP 子进程，快、可共享状态）。MVP 同时交付**对话 + 可编辑画布**（左聊右画，双向同步），画布直接进首版而非阶段二。

两条交互面并存：
- **Web 聊天页 + 画布**（新增，Vite/React/Tailwind，集成进现有前端工程）：`POST /api/agent/chat` 驱动。
- **MCP `chat` 工具**（扩展现有 `app/mcp/server.py`）：让 Claude Desktop 等 MCP 客户端也能对话式使用。

### Consequences
- **变容易**：用户从"填表/调 API"变为"边聊边改"，C/D 两段体验直接解决；草稿全程可编辑，C 段"改不动"解决；澄清工具 + 领域判别缓解 A 段"没懂"。
- **变困难 / 代价**：MVP 前端工作量显著上升（画布状态同步）；Agent-first 比"外层编排"更易失控、确定性更差；真实 deepseek 依赖带来 402/限流风险（已用熔断兜底）；B 段"套模板"根因（引擎本身）未在本 MVP 根治，需阶段二跟进。
- **可逆性**：Agent 层为纯新增，内核引擎不动；画布为新增前端，可独立于后端演进。任一组件可单独回退。

---

## 1. 目标与非目标

### 目标（MVP 必须）
1. 用户用自然语言描述点子，Agent 通过多轮对话逐步澄清、编译、生成 SOP。
2. 全程产出一份**结构化可编辑草稿（Project Draft）**，用户可随时改任意节点。
3. 提供**可编辑画布**：实时渲染 business_system 的节点/流程/SOP，与对话双向同步。
4. 真实 deepseek 驱动；遇 402/限流/引擎异常时**优雅降级、绝不卡死**。
5. 同时可通过 Web UI 与 MCP 客户端使用。

### 非目标（阶段二及以后）
- 根治引擎层"套模板"（B 段根因）——阶段二专项。
- `critique` / 深化 `knowledge` 工具。
- 知识库召回升级（需 embedding key）。
- 流式响应（SSE）、多项目/协作、画布拖拽布局、导出增强。
- 微服务/事件驱动拆分（保持模块化单体）。

---

## 2. 总体架构（分层）

```
[交付层]
  ├─ Web 聊天页 + 画布 (Vite/React/Tailwind, 集成现有前端)  ──►  POST /api/agent/chat
  └─ MCP 客户端 (Claude Desktop 等)                        ──►  MCP server `chat` 工具
                         │
[编排层]  Agent Loop（新增 app/agent/agent_loop.py）
          ├─ 加载会话状态（messages + Project Draft）
          ├─ 调 deepseek 推理 → 决策：澄清 / 调工具 / 收尾
          └─ 合成自然语言回复 + 草稿变更
                         │
[工具层]  app/agent/tools.py（新增，细粒度）
          clarify / compile / generate_sop / edit_node / summarize
                         │  （进程内直接调用，不走 MCP 子进程）
[执行核]  既有：FastAPI + compile 引擎 + SOPReportEngine + LLMService(真实 deepseek)
                     + KnowledgeService / RAGAnswerGenerator
                         │
[状态层]  Project Draft（新增，SQLite 新表 project_drafts，复用 app/db.py）
```

**关键决策**：Agent Service 与 MCP server 是两条独立的"交互面"，但共用同一套引擎与（可选的）Agent Loop 逻辑。MCP server 保持 stdio 传输 + 子进程隔离的现状作为外部集成面；Agent Service 走进程内直调以保证对话的低延迟与状态共享。

---

## 3. 组件职责

### 3.1 Agent Loop（`app/agent/agent_loop.py`）
- 输入：会话 ID + 用户消息。
- 加载该会话的 `messages` 与 `Project Draft`。
- 将（系统提示 + 历史 + 当前草稿 + 用户消息）喂给 `LLMService`（真实 deepseek），以 **function-calling / tool-use** 形式让模型决定下一步动作。
- 执行被决策的工具，把结果合并进草稿。
- 合成面向用户的自然语言回复（含草稿变更摘要）。
- 写回 `messages` 与草稿，返回给交付层。
- 内置护栏（见 §6）。

### 3.2 工具集（`app/agent/tools.py`，MVP 5 个）
| 工具 | 输入 | 调用引擎 | 写入草稿 |
|------|------|----------|----------|
| `clarify` | 当前 idea/draft | 仅 deepseek 生成追问（不调编译） | — |
| `compile` | 描述/精炼需求 | `compile_to_business_system_async(desc)` | `business_system`, `status=compiled` |
| `generate_sop` | `draft.business_system` | `SOPReportEngine().generate_full_sop_report(bs, enable_ai_analysis=True)` | `sop` |
| `edit_node` | `{path, value}` | 仅校验 + 打补丁 | 对应节点 |
| `summarize` | draft | deepseek 生成一段状态总结 | — |

> 注：`analyze_domain` 的判别能力在 MVP 中可融入 `compile` 前的澄清/分类步骤；独立的 `knowledge` 工具留阶段二。

### 3.3 状态：Project Draft（`app/agent/state.py` + 新表 `project_drafts`）
结构化 JSON，按会话持久化：
```
ProjectDraft {
  id, session_id,
  idea: str,
  requirements: str,            # clarify 后沉淀
  domain: { type, confidence }, # 领域判别（可选，compile 阶段产出）
  business_system: dict,        # compile 输出（画布渲染源）
  sop: dict,                    # generate_sop 输出
  status: enum(idea|clarifying|modeling|compiled|sop|review),
  messages: [ {role, content, ts} ],
  updated_at
}
```
- `edit_node` 按 JSON-path 校验后打补丁，保证画布与草稿同源。
- 复用 `app/db.py` 的 SQLite 连接与现有 repository 模式（新建 `ProjectDraftRepository`）。

### 3.4 API 端点（`app/api/chat.py`，新增路由）
- `POST /api/agent/chat`：`{session_id?, message}` → `{session_id, reply, draft, status}`。
- 纳入既有 `AuthMiddleware` + `RateLimitMiddleware`（基于 API key），与现有端点一致。
- MVP 先用请求/响应 JSON；SSE 流式留阶段二。

### 3.5 画布前端（集成现有 Vite/React/Tailwind 工程）
- 左：聊天面板（消息流 + 输入框）。
- 右：可编辑画布，渲染 `draft.business_system` 的节点（角色/流程/数据实体/触点）与边（流转关系），以及 SOP 摘要。
- **双向同步**：对话触发草稿变更 → 画布重渲染；画布内编辑节点 → 调 `edit_node`（经 `/api/agent/chat` 或独立 `/api/agent/edit` 端点）→ 回写草稿。
- 节点 schema 由 compile 输出派生，MVP 采用"卡片 + 连线"的轻量图表示，不做自由拖拽布局。

### 3.6 MCP `chat` 工具（扩展 `app/mcp/server.py`）
- 新增 `@mcp.tool() chat(session_id, message)`，进程内调用 Agent Loop（与 Web 同逻辑），返回回复 + 草稿摘要。
- 复用现有 `_run_engine_subprocess` 基础设施不必要——Agent Loop 直调引擎，MCP `chat` 直接 import 调用即可。

---

## 4. 一轮对话流

1. 用户消息经 Web `/api/agent/chat` 或 MCP `chat` 进入 Agent Loop。
2. 加载会话 `messages` + `Project Draft`。
3. deepseek（tool-use 模式）推理 → 决策：
   - 信息不足 → `clarify` 生成追问，返回用户。
   - 需求充分 → `compile`（或接续已有草稿）→ 合并 `business_system`。
   - 已有 business_system → `generate_sop` → 合并 `sop`。
   - 用户明确要求改 → `edit_node` → 打补丁。
   - 用户要进度 → `summarize`。
4. 结果合并进草稿（状态层写回 SQLite）。
5. 合成自然语言回复 + 草稿变更，返回交付层。
6. Web 端：聊天气泡追加 + 画布重渲染；MCP 端：文本回复 + 草稿 JSON。

---

## 5. 数据模型（Project Draft 持久化）

- 新表 `project_drafts`（SQLite，复用 `app/db.py`）：
  - `id` TEXT PK, `session_id` TEXT, `data` JSON, `status` TEXT, `updated_at` TIMESTAMP。
- `ProjectDraftRepository`（新建于 `app/agent/repositories.py` 或并入现有 repositories）：`get(session_id)` / `save(draft)` / `patch(session_id, path, value)`。
- `draft.business_system` 的节点 schema 由 compile 输出结构派生；MVP 以"节点列表 + 关系列表"最小表示支撑画布渲染，细节在实现阶段敲定（不阻塞本设计）。

---

## 6. 错误处理与护栏

- **引擎失败/超时**：工具层 try/except 捕获，调引擎自带的 mock 兜底，向用户用大白话说明并给重试建议，不向上抛异常中断对话。
- **deepseek 402 / 限流 / 网络错**：`LLMService` 已有回退 mock 逻辑；Agent Loop 加**熔断器**——连续失败 N 次则降级 mock + 明确告警，绝不空转卡死（已知坑：此前 deepseek 欠费曾导致全程回退 mock，现已充值，熔断仅作保险）。
- **`edit_node` 非法**：按草稿 JSON schema 校验 path/value，拒绝并说明原因，不改状态。
- **Agent 失控护栏**：单轮最多 K 次工具调用（默认 4）、单会话最多 M 轮（默认 30）、单轮超时；防止模型自循环。
- **鉴权**：`/api/agent/chat` 受 `AuthMiddleware` + `RateLimitMiddleware` 保护，与既有端点一致；MCP `chat` 沿用 MCP server 的进程级鉴权约定。

---

## 7. 测试策略

- **单测**（复用既有 pytest 套件 + `TestClient` + `monkeypatch` 隔离全局 settings 套路，见项目测试约定）：
  - 每个工具：`真实 deepseek` 路径 + `BSC_MCP_FORCE_MOCK=1` 强制 mock 路径，双覆盖。
  - `edit_node`：合法补丁 / 非法 path / 类型不符，三类用例。
  - Agent Loop：用脚本化消息序列断言草稿演进（idea→requirements→compiled→sop→edit）。
- **集成**（golden test）：给定多轮对话，断言最终 `Project Draft` 正确演进、画布数据源正确。
- **前端**：MVP 以画布渲染 draft 的冒烟校验为主，可手动；不引入新测试框架。
- 不新增测试框架，沿用 `pytest.ini` / `tests/` 现有结构。

---

## 8. MVP 范围（已锁定）

1. Agent Loop（`app/agent/agent_loop.py`）+ 5 工具（`clarify/compile/generate_sop/edit_node/summarize`）。
2. Project Draft 状态层（SQLite 新表 + Repository）。
3. `POST /api/agent/chat` 端点（含鉴权）。
4. MCP `chat` 工具（扩展 `app/mcp/server.py`）。
5. Web 聊天页 + 可编辑画布（Vite/React/Tailwind，集成现有前端工程，双向同步）。
6. 真实 deepseek 接通 + 熔断降级护栏。

### 阶段二（本设计外，单列待办）
- 根治引擎层"套模板"（B 段根因）：让 compile/SOP 真正吃透领域。
- `critique` 工具（Agent 自评草稿缺口/风险）+ `knowledge` 工具深化。
- 知识库召回升级（配 embedding key）。
- SSE 流式响应、画布拖拽布局、多项目/协作、导出增强。

---

## 9. 显式权衡（Trade-off）

| 决策 | 得到 | 放弃 |
|------|------|------|
| Agent-first（非外层编排） | 最像真搭档、最灵活 | 更易失控、确定性差、出首版慢 |
| 画布进 MVP（非阶段二） | 一步到位体验完整 | 前端工作量↑、MVP 周期拉长 |
| 进程内直调引擎（非 MCP 子进程） | 低延迟、共享状态、可流式 | 与 MCP server 的隔离模型不一致（两条面分治，可接受） |
| 复用既有引擎不重写 | 零重复造轮子、快 | B 段"套模板"根因 MVP 未治 |
| 真实 deepseek | 真智能、非模板 | 402/限流风险（熔断兜底） |

---

## 10. 风险与开放项

- **R1 Agent 跑偏**：靠 §6 护栏 + golden 测试约束；阶段二加 `critique` 自检。
- **R2 画布与草稿不同源**：`edit_node` 为唯一写入口，画布编辑必须经它回写，保证单一事实源。
- **R3 前端工程未知**：现有 `src/`、`public/`、`vite.config.ts` 的具体结构需在实现阶段先摸清再集成，避免另起炉灶。
- **R4 引擎"套模板"**：MVP 不解决，需在阶段二专项；当前靠对话澄清 + 真实 deepseek 缓解，但不根除。
- **开放项**：SSE 流式、画布节点 schema 最终字段、MCP `chat` 与 Web 是否共享同一 session 存储——实现规划阶段定。
