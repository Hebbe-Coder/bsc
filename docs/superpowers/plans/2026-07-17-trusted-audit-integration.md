# 方案 E — 可信审计整合（Trusted Audit Integration）

> 来源：awesome-llm-apps 结合升级序列（A 方法论引用 / B Risk=Constraint 审计链 / C 自进化+Evals / D 生成式 UI 仪表盘 / E 可信审计整合）。
> 本方案缝合 **A（方法论库可验证引用）** 与 **B（Risk=Constraint System 的 SHA-256 审计链）**，产出单一、可独立验证的可信审计记录，并在方案 D 仪表盘上呈现。

## 1. 背景与目标

- A 给编译器产物（SOP / 业务模型元素）注入了 `source_ref`（指向方法论库 chunk_id），并算出 `_citation_coverage` 指标，但引用仅停留在产物数据里，**不可独立验证、不可防篡改**。
- B 给约束评估产出了 `AuditChain`（SHA-256 链，含 coverage + gate 节点），但**只覆盖了约束维度，没把 A 的引用纳入链**。
- 方案 E：把 A 的引用集合 + B 的覆盖率/门禁快照，统一灌入一条 SHA-256 审计链，任何对引用或覆盖率的篡改都会断链 → `verify()` 返回 False。产物因而具备"可审计、防篡改、可独立验证"的可信属性（对应 awesome-llm-apps 的 `trust_gated_agent_team` / `ai_agent_governance` / `knowledge_graph_rag_citations` 思想）。

## 2. 调研结论（实测，避免假设错）

- **B 审计链** `app/constraint/audit.py`：`AuditChain.append(agent, action, payload)` 会把 `payload.output` 做 SHA-256，并用 `prev_hash` 串接；`verify()` 重放每条 entry 的 `seq|timestamp|agent|action|input_hash|output_hash|prev_hash` 并与存储的 `hash` 比对。genesis = `"0"*64`。`AuditEntry` 是 pydantic 模型，`model_dump()` ↔ `AuditEntry(**d)` 可往返。
- **A 引用落点**（实测 grep 确认）：
  - `sop["sops"][i]["source_ref"]`：`[chunk_id, ...]`
  - `business_model["flows"|"roles"|"rules"][i]["source_ref"]`：`[chunk_id, ...]`
  - `sop["_citation_coverage"]` / `business_model["_citation_coverage"]`：`{coverage, total, covered, flagged}`
- **仪表盘负载** `app/api/orchestrate.py:dashboard`：`state = draft.to_dict()` 含 `sop`/`risk`/`business_model` 三键，可直接喂给新审计构建器，**无需改脏的 `app/main.py`**（复用已注册的 `orchestrate` 路由）。
- **前端可改文件**（均为方案 D 新建的干净文件，非脏）：`src/api/compilerDashboardApi.ts`、`src/store/workspaceStore.ts`、`src/components/MethodologyDashboard.tsx`，以及新增 `src/components/TrustedAuditPanel.tsx`。脏文件 `orchestrateApi.ts` / `Workspace.tsx` 一律不碰。

## 3. 范围（YAGNI）

- 仅新增一个**纯函数模块** `app/audit/trusted_chain.py` + 接入现有 dashboard 端点 + 前端面板。**不新增 DAG 段、不改编排引擎、不引入数据库**。
- 不碰 `app/main.py`、不碰任何脏文件。
- 不做方案 C（自进化/Evals）——留作下一升级。
- 审计链为"只读快照"：编译完成后定时点计算，不重写编译产物。

## 4. 任务拆解（TDD）

- **T1 调研**（已完成）：见 §2。
- **T2 计划文档**（本文件）。
- **T3 可信审计内核** `app/audit/trusted_chain.py`：
  - `_collect_source_refs(state)` → 去重有序的 chunk_id 列表（来自 sop + business_model 各元素）。
  - `_coverage_snapshot(state)` → 从 `risk.coverage` + `risk.gate` 取 `coverage_pct/covered/total/uncovered_ids/gate_decision`。
  - `build_trusted_audit(state)` → 用 `AuditChain` 追加 `methodology/citation_index`（output 含 source_refs）与 `constraint/coverage_snapshot`（output 含覆盖率快照），返回 `{source_refs, coverage, audit:[...], chain_hash, verified}`。
  - `verify_trusted_audit(record)` → 重建链重放 `verify()` **且** 交叉校验 `record["source_refs"]` 与链内记录的 citation output 一致 → 任一项不符即 False。
- **T4 接入端点**：`dashboard()` 返回体追加 `"trusted_audit": build_trusted_audit(state)`。
- **T5 后端测试** `tests/audit/test_trusted_chain.py`：happy path（verified=True、2 entry、chain_hash 非空）、篡改 entry output_hash → verify False、篡改 convenience 字段 `source_refs` → verify False、空 state 优雅降级、dashboard 响应含 `trusted_audit`。
- **T6 前端面板** `TrustedAuditPanel.tsx` + 扩展 `compilerDashboardApi` 类型 / `workspaceStore` 字段 / 接入 `MethodologyDashboard` 栅格。（premium glass 风格，与 D 一致）
- **T7 全量回归** + `npm run check` + 执行日志 + 记忆更新。

## 5. 质量门

- `venv/Scripts/python.exe -m pytest tests/audit tests/api/test_compiler_dashboard.py -q` 全绿（期望 56 → 59+ passed）。
- `npm run check`（tsc）0 错误。
- 合并前 256 脏文件零改动（全程 git status 核验）。
- 不碰 master（特性分支提交，合并留待用户确认）。

## 6. 执行日志（live）

| 时间 | 提交 | 内容 |
|------|------|------|
| 11:5x | — | 建分支 `feat/trusted-audit-integration`（master `a22b304` 起）；调研完成；本计划落定 |
| 11:5x | `e36d029` | T3 内核 `app/audit/trusted_chain.py` + T4 接入 dashboard 端点 + T5 后端测试(6) + T6 前端 TrustedAuditPanel + T7 全量回归。单次提交 9 文件 / +511 |

## 7. 执行结果

- 后端：`app/audit/trusted_chain.py`（`build_trusted_audit` / `verify_trusted_audit` / `collect_source_refs`），复用 B 的 `AuditChain`；dashboard 端点追加 `trusted_audit` 段。
- 前端：`TrustedAuditPanel.tsx` + API 类型 `TrustedAudit` + 接入 `MethodologyDashboard` 栅格（premium glass，仅改 D 干净文件）。
- 测试：5（内核，含两类防篡改）+ 1（端点含 trusted_audit）= 6 新增。
- **全量回归**：`tests/constraint tests/orchestrator tests/agent tests/audit tests/api/test_compiler_dashboard.py tests/api/test_dashboard_trusted_audit.py` → **62 passed**（A/B 53 + D 3 + E 6）。
- `npm run check`（tsc）**0 错误**。
- 用户 256 脏文件零改动（仅我的 9 文件进提交）；master 未碰（`MASTER..FEAT=1, FEAT..MASTER=0`）。
- **修复的真实缺陷**：初版 `verify_trusted_audit` 误用 `AuditEntry.output`（该模型只存哈希不存原始 output）→ 改为由 `source_refs` 反推 citation 节点 `output_hash` 做密码学交叉校验，防篡改用例才通过。

## 8. 待用户确认（不自主执行）

- ① 合并 `feat/trusted-audit-integration` 进 master（`--no-ff`）。
- ② 删已合并分支 `feat/generative-ui-dashboard`（D 已完成未清理）。
- ③ 加 remote 并 push（当前 `git remote -v` 为空）。
- ④ 下一步可选：方案 C（自进化 + Evals）。
