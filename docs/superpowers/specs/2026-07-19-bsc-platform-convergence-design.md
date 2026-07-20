# BSC Platform Convergence Design

**Status:** Implemented
**Date:** 2026-07-19
**Scope:** 收敛当前 BSC Pipeline、Orchestrator、Business Agent OS、Artifact Graph 与 React Workspace 的运行边界
**Supersedes:** 不取代 ADR-010；本设计定义 ADR-010 从“已实现组件”走向“唯一生产运行时”的迁移路径

---

## 1. Executive Decision

BSC 以 `/api/orchestrate` 作为唯一产品编排入口，以 `BusinessRuntime` 作为目标执行内核，以 Artifact Graph 作为唯一业务事实源。现有 `/bsc/*` 固定 Pipeline 保留为兼容能力，通过适配器被 Runtime 调用；它不再拥有独立的产品状态、任务生命周期或前端主流程。

迁移不采用一次性重写。系统按四个可独立验收的子项目推进：

1. Orchestrator Lifecycle：先让当前编排入口具备可靠终态、事件协议和前端结果闭环。
2. Runtime Convergence：让 HTTP Agent OS 和 Orchestrator 真正执行 BusinessRuntime，旧 BSC 变为 Capability。
3. Persistence and Security：统一数据库后端、租户边界、Artifact 隔离和认证策略。
4. Delivery and Cleanup：修复 Docker/Kubernetes/CI，完成旧入口和不可达前端代码的退役。

每个子项目单独制定实施计划、测试和回滚点。本 Spec 冻结总体方向，首个实施计划只覆盖第 1 项。

---

## 2. Current-State Problem

当前仓库存在四套相互重叠的执行模型：

| 模型 | 当前入口 | 状态 | 主要问题 |
|---|---|---|---|
| Legacy BSC Pipeline | `/bsc/compile` | 活跃 | 所谓异步阶段仍执行同步 Agent；LLM 失败静默回退 mock |
| New Orchestrator | `/api/orchestrate` | 当前编译 UI 使用 | 裸后台任务、无可靠终态、SSE 不可重放、内部嵌套旧 Pipeline |
| Business Agent OS | `/agent/analyze`、CLI | 组件已实现 | HTTP 入口没有运行完整 BusinessRuntime；共享 Artifact 目录与固定项目 ID |
| Frontend Skill Pipeline | 未被当前 `App.tsx` 挂载 | 遗留可用代码 | 与后端编排重复，当前产品入口不可达 |

由此产生五类系统性风险：

- 同一个用户意图可能进入不同状态模型和输出 Schema。
- “成功”可能表示真实 LLM、mock 或部分空数据，调用方无法可靠区分。
- 任务完成、失败、取消和断线恢复没有统一语义。
- SQLite、PostgreSQL、文件 Artifact 和内存事件各自保存部分状态，没有唯一事实源。
- 前端显示的阶段进度与后端真实执行状态可能不一致。

---

## 3. Goals

### 3.1 Product Goals

- 用户提交一次分析后获得稳定的 `session_id`，可查询、订阅、恢复和取消。
- 前端只根据后端终态判断完成，不使用固定超时猜测。
- 编排完成后，业务模型、SOP、风险、审计与评测在同一 Workspace 中可见。
- API 明确标识 `real`、`mock`、`fallback`，生产环境不得把 fallback 冒充真实成功。

### 3.2 Architecture Goals

- Artifact Graph 是业务产物唯一事实源。
- ProjectDraft/Job 只保存任务投影：状态、阶段、错误、Artifact Graph 引用和时间戳。
- BusinessRuntime 拥有 Plan、Execute、Reflect 三个循环。
- Orchestrator 是控制面：创建任务、驱动 Runtime、发布事件、维护终态。
- Legacy BSC 通过 Capability Adapter 接入，不直接拥有产品工作流。

### 3.3 Operational Goals

- 任务状态具有确定状态机和幂等终态。
- SSE 支持序号、断线重连、终态关闭和多个订阅者。
- 数据库配置只有一个入口；生产后端配置失败时服务启动失败。
- 健康检查区分 liveness 与 readiness。

---

## 4. Non-Goals

- 本轮不重写所有 Agent Prompt。
- 本轮不改变知识库检索算法、RRF 或 reranker。
- 本轮不删除 `/bsc/*`、旧导出器或旧前端组件。
- 本轮不引入 Kafka、Temporal 或新的分布式任务平台。
- Phase 1 不完成 PostgreSQL 迁移；只保证当前 SQLite 路径上的任务生命周期正确。

---

## 5. Target Architecture

```text
React UnifiedWorkspace
        |
        | POST /api/orchestrate
        | GET  /api/orchestrate/{session_id}
        | GET  /api/orchestrate/{session_id}/events?after=<seq>
        v
Orchestrator Control Plane
  - Job lifecycle
  - Event sequencing/replay
  - Cancellation
  - Terminal error policy
        |
        v
BusinessRuntime
  Mission Loop -> Execution Loop -> Reflection Loop
        |
        +--> Native Capabilities
        +--> Knowledge/RAG Capability
        +--> LegacyBSCCompatibilityCapability
        |
        v
ArtifactGraphStore
  tenant_id / project_id / session_id isolated
        |
        v
Dashboard Projection + Exporters
```

### 5.1 Component Ownership

| Component | Owns | Must not own |
|---|---|---|
| `app/api/orchestrate.py` | HTTP validation、task creation、status/events endpoints | Agent business logic |
| `app/orchestrator/engine.py` | task state machine、stage orchestration、terminal transition | HTTP responses、global singleton data |
| `app/orchestrator/sse.py` | ordered event log、subscriber fan-out、replay | task status persistence |
| `app/capabilities/runtime.py` | mission/execution/reflection loops | FastAPI lifecycle |
| `app/artifacts/store.py` | typed business artifacts and graph edges | global cross-tenant exports |
| `app/agent/state.py` | task projection and status | destructive schema recreation |
| `src/components/UnifiedWorkspace.tsx` | user interaction and state presentation | inferred backend completion timers |

---

## 6. Job State Model

Canonical states:

```text
queued -> running -> completed
                  -> failed
                  -> cancelled
```

Rules:

- `queued`、`running` are non-terminal.
- `completed`、`failed`、`cancelled` are terminal and immutable.
- A completed task must have a dashboard projection.
- A failed task must have a stable error code and user-safe message.
- Cancellation is cooperative; already terminal tasks return their existing state.
- Restart recovery marks orphaned `running` tasks as `failed` with code `worker_restarted` until a durable queue is introduced.

Task projection fields:

```json
{
  "session_id": "abc123",
  "status": "running",
  "current_stage": "sop",
  "error_code": null,
  "error_message": null,
  "event_seq": 12,
  "created_at": "2026-07-19T10:00:00+08:00",
  "updated_at": "2026-07-19T10:00:08+08:00",
  "completed_at": null
}
```

Phase 1 reuses the existing `status` column and avoids schema expansion. The remaining projection fields are introduced with the persistence subproject after non-destructive migrations exist.

---

## 7. Event Protocol

Every event uses one envelope:

```json
{
  "session_id": "abc123",
  "seq": 12,
  "type": "stage.completed",
  "stage": "sop",
  "status": "done",
  "message": "SOP generated",
  "terminal": false,
  "timestamp": "2026-07-19T10:00:08+08:00",
  "data": {}
}
```

Required event types:

- `pipeline.started`
- `stage.started`
- `stage.completed`
- `stage.loopback`
- `pipeline.completed`
- `pipeline.failed`
- `pipeline.cancelled`

Protocol guarantees:

- `seq` is strictly increasing per session.
- A subscriber may reconnect with `after=<last_seq>` and receive retained events.
- Every subscriber receives every event; subscribers never compete for one Queue.
- Exactly one terminal event is emitted.
- The SSE response ends after the terminal event.
- Phase 1 retains the latest 256 events per session in memory. Durable replay belongs to the persistence subproject.

---

## 8. API Contract

### Create

`POST /api/orchestrate`

```json
{
  "idea": "business description",
  "project_id": "optional-project-id"
}
```

Response: HTTP 202

```json
{
  "session_id": "abc123",
  "status": "queued",
  "status_url": "/api/orchestrate/abc123",
  "events_url": "/api/orchestrate/abc123/events"
}
```

### Status

`GET /api/orchestrate/{session_id}` returns the persisted task projection. Unknown sessions return HTTP 404.

### Cancel

`DELETE /api/orchestrate/{session_id}` cooperatively cancels an active in-process task and returns HTTP 202. The task remains non-terminal until the engine persists `cancelled` and emits `pipeline.cancelled`. Cancelling an already terminal task is idempotent and returns its existing state.

### Events

`GET /api/orchestrate/{session_id}/events?after=0` returns SSE and closes after a terminal event.

The existing `/api/orchestrate/stream?session_id=...` remains as a compatibility alias for one release and emits the same envelope.

### Dashboard

`GET /api/orchestrate/dashboard/{session_id}` remains the output projection endpoint. It returns HTTP 409 while the task is non-terminal and HTTP 422 for failed tasks. Phase 1 may preserve the current permissive response until all frontend callers use the status endpoint.

---

## 9. Error and Fallback Policy

Three execution modes are observable:

| Mode | Meaning | Production behavior |
|---|---|---|
| `real` | configured provider returned valid structured output | success |
| `mock` | explicitly configured development mock | allowed only outside production |
| `fallback` | real provider failed and mock substituted | task fails by default in production |

Every stage records its mode. A task may complete with fallback only when an explicit request/configuration allows degraded output. The dashboard must display degraded status; it must not silently label it as real analysis.

---

## 10. Data and Tenant Boundaries

Target identifiers are distinct:

- `tenant_id`: security boundary.
- `project_id`: knowledge and business workspace boundary.
- `session_id`: one execution boundary.
- `artifact_id`: one typed fact or decision.

Artifact queries and exports require all applicable boundaries. The literal project ID `api` is removed. File-backed stores use `data/artifacts/<tenant>/<project>/<session>/`; database-backed stores include indexed boundary columns.

No repository may construct its own default database path. All repositories receive one configured backend/session factory.

Schema changes use versioned, non-destructive migrations. A column mismatch must stop startup or run a migration; it must never drop a production table.

---

## 11. Security Model

- SPA shell and versioned static assets are publicly readable.
- Business APIs require Bearer authentication in production.
- `/agent/*` is removed from the blanket auth and rate-limit whitelist.
- Browser SSE uses same-origin secure session authentication; API keys are not placed in query strings.
- Project-scoped keys may only access their bound `project_id`.
- Request signing reads `SIGNATURE_ENABLED` directly and is tested both enabled and disabled.
- Frontend has one API client and one authentication source; raw `fetch` calls do not bypass it.

---

## 12. Deployment Contract

- Docker uses a multi-stage build: Node builds `dist`, Python image copies it.
- Docker health checks use Python or install the required HTTP client explicitly.
- Required production extras (`redis`, `celery`, PostgreSQL driver) are declared in installable dependency groups.
- Complex environment values use JSON, for example `ALLOWED_ORIGINS=["https://bsc.example.com"]`.
- `/live` checks process health; `/ready` checks required dependencies and returns non-2xx when unavailable.
- Prometheus scrapes `/metrics/prometheus`.
- CI runs on the repository's actual default branch and gates Python collection/tests, TypeScript check, ESLint and Docker build.

---

## 13. Migration Roadmap

### Subproject A: Orchestrator Lifecycle

Deliverables:

- Canonical job states and terminal transitions.
- Replayable fan-out SSE protocol.
- Managed background task references and error capture.
- Frontend completion driven by terminal events.
- Dashboard fetched and rendered after completion.

Exit criteria:

- No fixed completion timer.
- Reconnect with `after` does not lose retained events.
- Multiple subscribers receive identical sequences.
- Failed agents produce persisted `failed` status and `pipeline.failed`.

### Subproject B: Runtime Convergence

Deliverables:

- `/agent/analyze` and `/api/orchestrate` share BusinessRuntime.
- Legacy BSC is a registered compatibility Capability.
- Agent OS response and frontend type contracts are generated from one schema.
- Default mock covers every registered Capability or fails validation.

Exit criteria:

- HTTP analysis executes capabilities, not only planning/reflection.
- One request cannot observe another request's artifacts.
- Old and new output adapters pass golden contract tests.

### Subproject C: Persistence and Security

Deliverables:

- One configured database backend and migration system.
- Durable job/event/artifact storage.
- Tenant/project/session isolation.
- Production-compatible SPA, API and SSE authentication.

Exit criteria:

- SQLite and PostgreSQL run the same repository contract suite.
- Restart recovery is deterministic.
- Cross-project and cross-session access tests fail closed.

### Subproject D: Delivery and Cleanup

Deliverables:

- Reproducible frontend/backend container.
- Correct liveness/readiness/metrics.
- Passing CI quality gates.
- Encoding repair and unreachable-code inventory.
- Deprecation headers and published removal dates for legacy endpoints.

Exit criteria:

- Clean checkout builds and starts without prebuilt local artifacts.
- Full tests collect and pass under the supported Python version.
- TypeScript check and ESLint pass.
- Production smoke test completes one real or explicitly mocked job end to end.

---

## 14. Compatibility and Rollback

- `/bsc/*` remains available throughout Subprojects A-C.
- Existing dashboard payload fields remain stable during Subproject A.
- The old SSE URL remains an alias for one release.
- Each subproject ships behind independently reversible commits.
- Runtime convergence uses an environment switch during one release: `BSC_RUNTIME_MODE=legacy|business_runtime`.
- Rollback returns traffic to `legacy` without deleting newly written Artifact data.

---

## 15. Acceptance Criteria

The platform convergence program is complete when all statements are true:

1. A single documented runtime owns all product executions.
2. Every execution has a queryable terminal state.
3. SSE reconnect and multi-subscriber behavior are deterministic.
4. Frontend output is populated from backend artifacts after real completion.
5. Production cannot silently replace failed LLM output with mock output.
6. All business data obey tenant/project/session boundaries.
7. Database configuration applies to every repository.
8. A clean checkout passes CI and produces a runnable container with the React SPA.

---

## 16. Design Self-Review

- Scope is explicitly decomposed into four independently testable subprojects.
- Artifact Graph ownership is consistent with ADR-010.
- ProjectDraft is a lifecycle projection, not a competing business state model.
- API, event and state terminal semantics use the same vocabulary.
- Phase 1 avoids schema expansion and distributed infrastructure, preserving a small rollback surface.
- No requirement depends on an unspecified component or unresolved design choice.
