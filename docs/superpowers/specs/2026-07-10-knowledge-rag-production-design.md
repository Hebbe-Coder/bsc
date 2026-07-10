# 知识库 RAG 生产级加固 — 设计文档（子项目 A）

> 状态：设计草稿（待评审）
> 上游：已完成「知识库 RAG 增强」（T1–T11，333 passed，2026-07-09 验收）
> 范围：仅动 **知识库专属 DB**（KnowledgeRepository）与 knowledge API；不碰主库 `app/core/database.py` 的 `projects`/`project_members` 注册表。
> 落库路径：`C:\Users\34216\Documents\New project 3\bsc-backend`

---

## 0. 已锁定的决策（9 项）

| # | 维度 | 决策 |
|---|------|------|
| 1 | 子项目范围 | A=RAG 生产级加固（B 引用溯源硬化 / C 导出可靠性 后续轮次）|
| 2 | 隔离层级 | **3** = 技术隔离 + project 级鉴权（双重强隔离）|
| 3 | rerank 默认 | **3** = 全局默认 local + 开启；per-project 可覆盖 provider/key/model |
| 4 | 流式输出 | **严格 WebSocket**（路径 B）|
| 5 | 评测基准 | **3** = 常驻 `/knowledge/evaluate/benchmark` API 端点，外部调度拉取 |
| 6 | 成员模型 | 复用现有 knowledge DB `project_members` + 新增 `project_keys` 表 |
| 7 | L0/L1 契约 | ① 全局 admin 保留超级权限但须显式带 project_id；② 角色两级（project_admin 读写 / project_reader 只读）；③ `/ingest` 宽松自动建 project |
| 8 | L2 密钥 | per-project 云端 rerank key 用 **Fernet 加密入库**（非 env 变量名）；project 级 rerank 默认继承全局 local+开启 |
| 9 | L3 帧 | 流式首帧带 `sources` |

---

## 1. 代码现状（已核准，避免重复造轮子）

- **零 WebSocket 基建**：全项目 `grep [Ww]eb[Ss]ocket` 无命中 → L3 将引入**首个 WS 端点**；需 `uvicorn`（已用）支持 ASGI WS。
- **流式帧协议已统一**：`app/api/stream_api.py` 的 `stream_chat` 产 `{type:"token"|"end"|"error", data}`；`llm_service.stream_chat` / `async_llm_service.stream_chat` 为生成器。L3 复用此协议映射到 WS。
- **L4 已有 80% 基础**：`app/knowledge/eval.py` 的 `RAGEvaluator.evaluate(service, gold, top_k, project_id, rerank, rerank_top_n, with_faithfulness)` 已支持按 project 检索与 rerank；`compare_before_after` 已算 `delta_precision/delta_recall/rerank_not_worse`；`knowledge_api.py` 已有 `POST /evaluate`（内联 gold）。L4 仅把 gold **常驻化（落库）** 并升级为外部可调度的 `/evaluate/benchmark`。
- **隔离裂缝**：`service._fetch_candidates` 用 `AND (? = '' OR d.project_id = ?)` —— project_id 为空即跨项目可见（L1 修复点）。
- **密钥表已存在线索**：knowledge DB 已有 `project_members(id, project_id, user_id, role, joined_at)`（未被鉴权使用），本轮复用并补索引。

---

## 2. L0 — 数据模型（knowledge DB）

### 2.1 新增 / 变更表（幂等 `CREATE TABLE IF NOT EXISTS`）

```sql
-- 复用已有 project_members; 仅补复合索引
CREATE INDEX IF NOT EXISTS idx_pm_project_user
  ON project_members(project_id, user_id);

-- 项目注册（knowledge 侧, 轻量）
CREATE TABLE IF NOT EXISTS knowledge_projects (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  metadata    TEXT DEFAULT '{}',
  rerank_config TEXT DEFAULT '{}'   -- JSON: {provider,model,top_n,enabled,keys_encrypted}
);

-- 项目级密钥: 只存哈希, 不存明文
CREATE TABLE IF NOT EXISTS project_keys (
  key_hash   TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  role       TEXT NOT NULL,        -- project_admin | project_reader
  label      TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES knowledge_projects(id)
);

-- 常驻评测 gold 集
CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id         TEXT,         -- NULL = 全局/跨项目
  query              TEXT NOT NULL,
  expected_chunk_ids TEXT DEFAULT '[]',
  notes              TEXT,
  created_at         TEXT NOT NULL
);

-- 隔离加固索引
CREATE INDEX IF NOT EXISTS idx_kdocs_project
  ON knowledge_docs(project_id);
```

### 2.2 约束
- `knowledge_docs.project_id` 已存在 → 仅补索引；新写入强制非空（L1）。
- `project_keys.key_hash = sha256(plaintext_key)`，鉴权比对哈希。

---

## 3. L1 — 强隔离 + 项目级鉴权

### 3.1 技术隔离（无空值全可见分支）
- `service._fetch_candidates`：
  ```python
  # 旧: AND (? = '' OR d.project_id = ?)
  # 新:
  WHERE c.id=? AND d.project_id = ?
  ```
- `retrieve / ingest / list_documents / delete_document` 的 `project_id` 语义升级为**必填**：空值 → 返回 `ApiResponse.error("project_id 必填", code=400)`。
- 全局 admin 仍走强隔离：**必须显式带 project_id**，无「不带即全库」通配。

### 3.2 鉴权扩展
- 抽取 `app/middleware/auth.py` 的 `_resolve_knowledge_role(api_key)` 为可复用解析函数；新增 `_resolve_project_key(api_key) -> (role, project_id | None)`：
  - 查 `project_keys` 命中 → `request.state.knowledge_role = role`，`request.state.knowledge_project_id = project_id`。
  - 全局 `API_KEY` → admin（超级，须带 project_id）；`API_KEY_READER` → reader（仅全局文档，无 project 范围）。
- 新增 FastAPI 依赖：
  - `require_admin`（既有，全局超级）
  - `require_project_read(project_id)`：role ∈ {admin, project_admin, project_reader} 且（admin 或 `state.project_id == project_id`）
  - `require_project_write(project_id)`：role ∈ {admin, project_admin} 且（admin 或 `state.project_id == project_id`）

### 3.3 密钥签发（admin 专属）
- `POST /knowledge/projects`：建 `knowledge_projects` 行；生成 32 字节随机 `project_admin` key，明文**一次性**返回，存 `sha256(key)` 入 `project_keys`。
- `POST /knowledge/projects/{id}/keys`：签发 `project_admin` / `project_reader` key（同上，明文一次性返回）。
- `/ingest` 宽松自动建（契约③）：若 `project_id` 不在 `knowledge_projects` 且调用方为全局 admin → 自动补建 `knowledge_projects` 行（metadata 标 `auto_created=true`）。

---

## 4. L2 — Per-project Rerank（Fernet 加密 + 全局默认）

### 4.1 解析优先级
`get_reranker(project_id=None, provider=None, keys=None, model=None)`：
1. 显式 `provider/keys/model` → 直接使用（最高优先）。
2. 给定 `project_id` → 读 `knowledge_projects.rerank_config`：`{provider, model, top_n, enabled, keys_encrypted}`。
   - 若 `keys_encrypted` 非空 → `Fernet(settings.RERANK_KEY_MASTER).decrypt(...)` 还原真实 key。
3. 否则 → 全局 `settings.RERANK_*`（**默认 provider=local, enabled=True**）。

### 4.2 Fernet 加密入库
- 依赖 `cryptography.fernet.Fernet`；主密钥 `settings.RERANK_KEY_MASTER`（env 注入，**不入库、不硬编码**）。
- 写入 `rerank_config.keys_encrypted`：`Fernet(master).encrypt(cloud_api_key.encode())`。
- 读取时解密；主密钥缺失 → 该 project 降级为全局 local（不阻塞 ingest/retrieve）。
- 新 project `rerank_config` 默认 `{}` → 自动继承全局 local+开启（契约⑧）。

### 4.3 接线
- `service.retrieve` 已支持 `rerank/rerank_top_n`；补充：当 `rerank=None` 时按 `project_id` 解析 per-project 配置（L1+L2 联动）。

---

## 5. L3 — 流式 `/ask`（严格 WebSocket + sources 帧）

### 5.1 新增 `app/api/knowledge_ws.py`
- `ConnectionManager`：
  - `active: dict[WebSocket, dict]` 记录连接态；
  - `cancel_events: dict[request_id, asyncio.Event]` 支持中断。
- 路由 `@router.websocket("/ws/knowledge/ask")`（**项目首个 WS 端点**）。

### 5.2 鉴权（WS 无 middleware，手动解析）
- 从 `websocket.headers["authorization"]`（去 `Bearer `）或 query `?token=` 取 key；调用 L1 解析函数 → 设 `role` / `project_id`；失败 `await websocket.close(code=1008)`。

### 5.3 消息协议
**客户端 → 服务端**
```json
{"type":"ask","request_id":"r1","query":"...","project_id":"p1","top_k":5,"rerank":null,"rerank_top_n":null}
{"type":"cancel","request_id":"r1"}
{"type":"ping"}
```
**服务端 → 客户端**（复用 stream_api 帧语义）
```json
{"type":"sources","request_id":"r1","data":[ /* retrieve 返回的片段列表 */ ]}
{"type":"token","request_id":"r1","data":"..."}
{"type":"end","request_id":"r1","data":{"answer":"全文","metrics":{"citation_rate":0.9}}}
{"type":"error","request_id":"r1","data":"消息"}
{"type":"pong"}
```

### 5.4 处理流程（`ask`）
1. 校验 `require_project_read(project_id)` 权限（无权限 → `error` 帧）。
2. `retrieved = service.retrieve(query, project_id, top_k, rerank, rerank_top_n)`（L1 隔离 + L2 重排）。
3. **先发 `sources` 帧**（契约⑨，为子项目 B 引用溯源预留）。
4. 拼 prompt；`async for token in gen_tokens(system, user, cancel_event)` 转发 `token` 帧。
   - `gen_tokens` 包 `llm_service.stream_chat` / `async_llm_service.stream_chat` 为 async 生成器，每轮查 `cancel_event.is_set()`。
5. 完成或收到 `cancel` → 发 `end` 帧（含全文 answer + metrics）。
6. `WebSocketDisconnect` → 清理连接与 cancel 事件。

### 5.5 兼容
- 保留 `POST /ask`（非流式）供程序化客户端 / 向后兼容。

---

## 6. L4 — 常驻 Benchmark 端点

### 6.1 数据
- gold 常驻 `knowledge_benchmarks`（L0 表）；admin 通过 `POST /knowledge/evaluate/benchmark/gold` 注入（含 `expected_chunk_ids`）。

### 6.2 端点
`GET /knowledge/evaluate/benchmark?project_id=&top_k=5&rerank_top_n=&with_faithfulness=false`
- 读 `knowledge_benchmarks`（按 `project_id` 过滤；NULL=全部）。
- 复用 `RAGEvaluator.compare_before_after` → `before / after / delta_precision / delta_recall / rerank_not_worse`。
- 附加：
  - `isolation_check`：每条 gold query 校验检索结果 `chunk.project_id == project_id`（无泄漏）→ `isolation_ok: bool`（呼应 L1）。
  - `latency_ms`：`retrieve` 全程 p50/p95。
- 返回 `ApiResponse.ok(report)`。
- 鉴权：`require_admin` 或 `require_project_read(project_id)`。
- 保留既有 `POST /evaluate`（内联 gold，手动即席评测）不删。

### 6.3 外部调度
- cron / CI 周期调用 `GET /evaluate/benchmark`；当 `rerank_not_worse=False` 或 `recall@k < 阈值` 时告警。

---

## 7. 跨切面

### 7.1 迁移
- 新表幂等建表（启动时执行）；`knowledge_docs.project_id` 已存在仅补索引；无数据迁移脚本（gold 由 admin 注入）。

### 7.2 测试（沿用 TestClient 集成测试约定）
- 唯一测试 API key 注入 `monkeypatch.setattr(settings,"API_KEY",<key>)`；请求头 `Authorization: Bearer <key>`。
- `app.dependency_overrides[dep] = lambda: instance`，`finally` 中 `pop` 还原。
- WS 测试：Starlette `TestClient.websocket_connect("/ws/knowledge/ask")` 验证 `sources` → `token*` → `end` 帧序与取消。
- benchmark 测试：注入 gold → 调 `/evaluate/benchmark` 断言 `rerank_not_worse` 与 `isolation_ok`。

### 7.3 风险 / 待确认
- **破坏性**：`project_id` 由可选变必填，既有空 project_id 调用方需改造；`/ingest` 自动建 project 缓和断裂。
- **WS 首引入**：需确认部署 uvicorn 配置支持 WS；测试用 `TestClient.websocket_connect`。
- **Fernet 主密钥**：`RERANK_KEY_MASTER` 须由部署环境注入，缺失时该项目降级 local。

---

## 8. 验收标准（C 级）

1. **隔离**：用 project A 的 key 检索/列举/删除，结果绝不出现 project B 的 chunk/doc；空 project_id 调用被 400 拒绝。
2. **鉴权**：project_admin 可写、project_reader 只读、跨项目 reader 被拒；全局 admin 须带 project_id 方可操作。
3. **rerank**：未配置 project 时默认 local+开启；配置云端 key 经 Fernet 加解密往返一致；显式参数优先。
4. **流式**：`/ws/knowledge/ask` 收到 `ask` 先回 `sources` 再逐 `token` 后 `end`；`cancel` 可中断；`POST /ask` 仍可用。
5. **benchmark**：`/evaluate/benchmark` 返回 `before/after/delta/rerank_not_worse/isolation_ok/latency_ms`；gold 来自库而非请求体。
6. **回归**：全量 `pytest` 通过（基线 333 passed），无新增漂移文件。

---

## 9. 实施分片（供 writing-plans 消费）

- **L0**：建表 + 索引（knowledge DB 启动迁移）。
- **L1**：`_fetch_candidates` 去空值分支；解析函数抽取；`require_project_*` 依赖；密钥签发端点；`/ingest` 自动建。
- **L2**：`get_reranker` 加 project_id 解析 + Fernet 加解密；`retrieve` 接线。
- **L3**：`knowledge_ws.py`（ConnectionManager + WS 端点 + 帧协议 + 取消）；保留 `POST /ask`。
- **L4**：`knowledge_benchmarks` 表；gold 注入端点；`/evaluate/benchmark` 端点 + 报告。
- **测试**：各层集成测试 + WS 帧测试 + benchmark 测试。

> 下一步：本设计文档自审 → 用户评审 → 调用 writing-plans 按 L0–L4 生成实施计划。
