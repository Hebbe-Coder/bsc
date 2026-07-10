# 知识库加固 Round 2 设计文档

> 日期：2026-07-10
> 范围：在已合入 master 的 RAG 生产级加固（L0–L4）之上，做一轮「综合加固」——收口安全盲点、提升性能/可扩展性、修正排序正确性、补齐可观测性、清理启动期开销。
> 执行方式：单 feature 分支 `feature/knowledge-hardening-round2` + subagent-driven（每任务 TDD + 双评审），最终合回 master。

## 0. 真实代码事实（设计依据，已核验）
- `_enforce_project_access(request, project_id, allow_admin_all=True)` 中 `reader` 分支（knowledge_api.py:53-58）在 `allow_admin_all=True` 且 `project_id` 缺失时直接 `return requested_project_id`(=None)；`GET /knowledge/documents` 用了该标志 → `service.list_documents(project_id=None)` 丢弃 WHERE → **reader 可看全项目文档**（跨项目泄漏，HIGH）。
- `GET /evaluate`（knowledge_api.py:229-239）无 `require_admin`、未传 `project_id`，`evaluate(...)` 因 `retrieve("")` 守卫返回 `[]` → 静默空结果（MED）。
- `knowledge_ws.py:106` `_handle_ask` 在异步 task 内同步调用 `svc.retrieve(...)`（内含 `httpx.Client` 网络调用 + 同步 `requests.post` 云端 rerank），真实 provider 下阻塞事件循环（HIGH）。
- `tfidf.py:26 _build_and_store_model` 每次 `index()` 重读全表 `knowledge_chunks` 并重算所有 chunk 向量；`index(chunk_records)` 当前无 content_hash 增量逻辑（HIGH/MED）。
- `tfidf.search`/`vector.search` 全表加载无 `project_id`/`LIMIT` 下推；`service._fetch_candidates` 逐候选一条 SELECT（N+1）（MED）。
- `EMBEDDING_PROVIDER="mock"`（config.py:64），`VectorBackend` 默认参与 RRF 融合 → 无意义向量噪声污染排序（MED）。
- `get_knowledge_service` 每请求 `ensure_schema()` 跑 DDL（knowledge_api.py:16-17），应改为启动期一次（LOW）。
- **遗留 RBAC（`VALID_ROLES`/`add_member`/`index_knowledge` 等）经核实仍被 `app/db.py` 与 `tests/test_repositories.py` 引用，是另一套在用的实体子系统，非死代码 → 不在本轮清理范围。**

## 1. 架构与共享基础设施
本轮 5 条工作流（WS1–WS5）共享三处基础设施改动：
1. **读路径鉴权语义收紧**：`_enforce_project_access` 的 `allow_admin_all` 仅对 `admin` 生效（WS1）。
2. **同步检索的异步化包装**：WS 端点用 `loop.run_in_executor` 包裹同步 `retrieve`（WS2）。
3. **轻量 Metrics 收集器**：进程内单例（WS4）。

所有改动隔离在独立 feature 分支，每任务派发实现子代理、先写失败测试，再由两阶段评审（规格 + 代码质量/安全）把关。

## 2. WS1 — 安全收口（HIGH/MED）
### 2.1 修 `reader` 跨项目泄漏（HIGH）
- 修改 `_enforce_project_access`：`allow_admin_all=True` 仅当 `role=="admin"` 时允许 `project_id` 为空（=全部）；
- `reader`/`project_admin`/`project_reader` 分支：若 `requested_project_id` 为空，**回退到令牌绑定的 `token_pid`**（取自 `request.state.knowledge_project_id`）；若仍为空则 `raise HTTPException(400, "project_id 必填")`。
- 效果：`GET /knowledge/documents` 不带 project_id 的 reader key 只会看到自身令牌绑定的项目，绝不返回全表；admin 仍可按 `project_id` 或空=全部。
- 注意：仅收紧 `allow_admin_all` 语义，不改动 admin 既有行为。

### 2.2 `GET /evaluate` 加固（MED）
- 加 `_admin: bool = Depends(require_admin)`。
- 强制 `project_id` 必填（缺失返回 400，明确信息），不再静默空结果。
- 返回结构不变（`before/after/delta_*/rerank_not_worse`）。

### 2.3 测试
- `test_reader_cannot_list_all_projects`：构造 reader key（绑定某 project）+ 不带 project_id 调 `/knowledge/documents` → 仅返回绑定项目文档，断言不包含其它项目。
- `test_evaluate_requires_project_id` / `test_evaluate_requires_admin`。

## 3. WS2 — 性能 / 扩展性（HIGH/MED）
### 3.1 WS 异步化（HIGH）
- `knowledge_ws.py` `_handle_ask` 中：`retrieved = await loop.run_in_executor(None, lambda: svc.retrieve(...))`，其中 `loop = asyncio.get_event_loop()`。
- `async_stream_chat` 仍走原生 async，cancel 语义保持（T10 已验证）；检索阻塞被移出事件循环。
- WS 测试继续用 mock LLM，并新增断言：检索在 executor 路径执行、流式 + cancel 仍正确。

### 3.2 TF-IDF 增量索引（HIGH/MED）
- `tfidf.index(chunk_records)`：以 `content_hash` 为主键去重——已存在且 hash 相同的 chunk 跳过向量化；仅对新/变更 chunk 计算向量并写 `knowledge_tfidf`。
- `_build_and_store_model`：仅当 vocab（去重词表）发生变化时才重建 `tfidf_model` 全模型；否则复用缓存。
- 失败/回退：hash 缺失的 chunk 按「需重算」处理，保证不漏。

### 3.3 检索下推 + 去 N+1（MED）
- `tfidf.search`/`vector.search` 的 SQL 注入 `project_id` 与 `LIMIT`（拼接参数化条件，不拼字符串字面量）。
- `service._fetch_candidates`：将「每候选一条 SELECT」改为 `WHERE id IN (...) AND d.project_id=?` 批量取，一次性 map 回结果。

### 3.4 测试
- `test_ws_retrieve_runs_in_executor`（结构/行为断言不阻塞）。
- `test_tfidf_incremental_skips_unchanged`（重 ingest 同内容 → 向量重算次数不随语料增长）。
- `test_retrieve_sql_pushdown_project_id`（断言 backend SQL 含 project_id 条件，可用 fake repo/计数验证）。

## 4. WS3 — 正确性（MED）
### 4.1 Mock 向量不混入 RRF
- `service.retrieve` 构建候选融合时：仅当 `settings.EMBEDDING_PROVIDER != "mock"` 才把 `VectorBackend` 结果纳入 `rrf_fuse`；mock 下走 keyword+tfidf。
- 配置项 `VECTOR_FUSE_ENABLED`（默认 True，仅 provider!="mock" 生效）便于显式关闭。

### 4.2 Embedding 漂移
- `knowledge_vectors` 行已带 `model` 字段；`VectorBackend.search`/写入时若检测到存储的 `model` 与当前 `settings.EMBEDDING_PROVIDER` 模型标识不一致，标记该 doc 向量为陈旧并触发重嵌（保守：仅对受影响 doc 重算，不重建全表）。
- 提供一次性重建命令/端点（admin）可选，本期至少保证「检测+标记」并在下次 ingest 时修正。

### 4.3 测试
- `test_mock_vector_excluded_from_fusion`：mock provider 下融合结果不含向量分数贡献（对比开启真实 provider 的排序差异，或断言 vector 后端未参与）。
- `test_embedding_model_mismatch_triggers_reembed`。

## 5. WS4 — 可观测性（MED，轻量）
- 新增进程内 `Metrics` 单例（`app/knowledge/metrics.py` 或 `app/core/metrics.py`）：
  - `retrieval_latency_ms` 直方图分桶（在 `service.retrieve` 入口/出口打点）。
  - `rerank_hit_rate`：rerank 前后 top-k 重合度（与 `RAGEvaluator` 思路一致，简化计数）。
  - `eval_regressions`：benchmark 中 `rerank_not_worse=False` 的累计次数。
  - `auth_failures`：鉴权失败（含跨项目拦截）计数。
- `GET /knowledge/metrics`（`require_admin` 门禁）返回聚合 JSON。
- 关键路径加结构化日志：`logger.info(json.dumps({...}))` 记录延迟/命中/失败。
- **不引入 Prometheus / 外部 metrics 后端**，保持零新增依赖。

## 6. WS5 — 清理（LOW）
- `get_knowledge_service`（knowledge_api.py:16-17）移除每请求 `ensure_schema()`；schema 初始化统一在应用启动期（`lifespan`/`init_db`）执行一次（确认 `app/main.py` 启动流程已覆盖 `ensure_schema`，若未覆盖则在此补充调用）。
- 不删除遗留 RBAC（见 §0，仍被 `app/db.py` 使用）。

## 7. 测试与回归策略
- 每 WS 派发实现子代理，先写失败测试。
- 复用 T12 的 `tests/knowledge/conftest.py` autouse 隔离 fixture（快照/还原全局 settings + dependency_overrides），避免 settings 串扰复发。
- 全量回归目标：保持 368+ passed、不引入新失败；漂移文件规则不变（`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*` 不提交）。

## 8. 验收标准
- 🔴 `reader` 跨项目泄漏闭环（测试证明 reader 不带 project_id 仅见绑定项目）。
- WS 真实 provider 下不再阻塞事件循环（`run_in_executor` 路径覆盖）。
- TF-IDF 增量：大规模语料 ingest 不再 O(全语料) 重算。
- 检索 SQL 含 `project_id` 下推 + 批量候选取，无 N+1。
- Mock 向量不污染排序；provider 切换可检测并修正陈旧向量。
- `/knowledge/metrics` 可查聚合；结构化日志落地。
- 启动期 schema 仅执行一次；全量测试全绿。

## 9. 风险与权衡
- WS2.1 异步化：`run_in_executor` 是最低成本修复；更彻底的「backend 全异步（httpx.AsyncClient）」留作后续，本期不追求。
- WS3.2 漂移：采用「检测+标记+下次 ingest 修正」而非立即全量重嵌，避免大写入风暴。
- WS5 清理范围收敛：遗留 RBAC 经核实仍在使用，故仅做启动期 schema 优化，不做符号删除。
