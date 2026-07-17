# 方案 D — 可交互产物仪表盘（Generative UI Dashboard）

> 日期：2026-07-17 · 分支：`feat/generative-ui-dashboard`（基于 master，含已合并的 B+A）
> 风格：沿用 `docs/superpowers/plans` 的 TDD 纪律；每个任务 red→green，独立 subagent，合并等用户授权。

## 0. 你作为用户得到什么（体感优先）

之前编译器跑完，产物是「SOP 文本 + 静态 PPT/HTML 导出」。你**看不到**两件事：
- B 刚做的 Risk=Constraint 结果——覆盖率多少？gate 是 pass/warn/block？哪些约束没被满足？风险按严重度怎么排？
- A 刚做的 methodology 引用——每条 SOP 依据哪份文档哪一段？整体「有据可查」比例多高？

做完 D 后：编译器产物变成一个**活的可交互仪表盘**——Risk 卡片按严重度排序、点开可下钻到约束；约束覆盖用进度条+未覆盖清单呈现健康度；SOP 每条带可点击的来源引用 chip（`文档/章节/段落`），并附引用覆盖率条。干系人能「戳」产物，而不是读幻灯片。

## 1. 调研结论（先验证再计划，避免 B 那次「假设错」）

- `app/api/dashboard.py` 是**运维监控看板**（uptime/请求数/LLM 统计），**不是**编译器产物仪表盘 → D 要新建产物仪表盘接口。
- 分析文档称「已有 KpiPanel/RiskPanel」是**假的**（同「9 段 DAG 已落地」类过度宣称）：`src/` 里**只有 `SopPanel.tsx`**，无 Risk/KPI/Constraint/Citation 面板。
- `Workspace.tsx` 仅渲染 `BusinessGraph + SopPanel + AgentLog`；store 有 `businessModel/sop/review/presentation` 但**无 `risk` 字段** → B 的约束/风险数据对前端完全不可见。
- `SopPanel` 只读 `sops[].title/owner_role/steps/escalation/review_cycle`，**不渲染 `source_ref`/`_citation_coverage`** → A 的引用数据即使到了前端也没显示。
- **路由是显式列表注册**（`app/main.py:216` 的 17 模块循环）。新增模块不会自动挂载，必须改 main.py——但 **main.py 在用户 256 个脏文件里**。
- **干净且已注册的 api 模块**：`stream_api` / `knowledge_ws` / `orchestrate`。其中 **`app/api/orchestrate.py` 干净、有 `router` + `ProjectDraftRepository` + `ProjectDraft`** → 完美宿主，加路由不碰脏 main.py。
- **脏前端文件**（必不碰）：`src/api/orchestrateApi.ts`、`src/components/Workspace.tsx`。干净可改：`src/App.tsx`、`src/store/workspaceStore.ts`。

## 2. 范围（克制，一次只攻 D）

- ✅ 后端：在干净模块 `app/api/orchestrate.py` 加 `GET /api/orchestrate/dashboard/{session_id}`，把 ProjectDraft 重排成仪表盘就绪 payload。
- ✅ 前端：新增 4 个面板组件 + 1 个容器 + 1 个 api client（全是新文件），在干净的 `App.tsx` 加「工作台 / 产物仪表盘」切换。
- ❌ 不碰 `Workspace.tsx` / `orchestrateApi.ts`（脏，保留）。不重构现有 SopPanel。
- ❌ **不做** LLM「生成式 UI agent」（参考模板 ai-dashboard-canvas-agent 的 LLM 拼装部分）——那超出本次范围且引入不确定性。D 交付的是「数据驱动自动拼装的结构化面板」，即「生成式 UI」的实质用户价值。明确偏差。
- ❌ 不新增 React 测试框架（项目无现成配置）。前端靠 `tsc`/`vite build` 通过 + dev 冒烟验证；后端 pytest 全覆盖。

## 3. 数据骨架（后端重排后的 payload）

```
GET /api/orchestrate/dashboard/{session_id}
→ 200 {
  "session_id": str,
  "sop": {
     "sops": [ {id,title,owner_role,steps,escalation,review_cycle,
                source_ref:[chunk_id...],            # A 的引用
                "_citation_coverage":{coverage,covered,total,flagged} } ],
     "_citation_coverage": {coverage,covered,total,flagged}   # 整体引用覆盖
  },
  "risk": {
     "overall_score": "low|medium|high",
     "gate": {decision:"pass|warn|block", reason:str},
     "coverage": {total,covered,coverage_pct,uncovered_ids:[...]},  # B 的覆盖引擎结果
     "risks": [ {id,title,severity,linked_constraints:[...],detail} ]
  },
  "business_model": { ... }      # 仅透传，供面板取流程/角色名
}
→ 404 {detail:"session not found"}   若草稿不存在
→ 200 空壳 {session_id, sop:{}, risk:{}, business_model:{}}  若流水线尚未产出
```

注：字段名直接复用 B（`ConstraintResult.risk/coverage/gate`）与 A（`sop.source_ref`/`sop._citation_coverage`）的真实输出，保证端到端一致。

## 4. 任务（TDD，独立 subagent 逐任务实现 + 两阶段复核）

### Task 1 — 后端仪表盘接口（重排 ProjectDraft）
- 改 `app/api/orchestrate.py`（CLEAN），加：
  ```python
  @router.get("/dashboard/{session_id}")
  async def dashboard(session_id: str):
      repo = ProjectDraftRepository()
      draft = repo.get(session_id)
      if draft is None:
          raise HTTPException(404, "session not found")
      state = draft.to_dict()
      sop = state.get("sop") or {}
      risk = state.get("risk") or {}
      return {
          "session_id": session_id,
          "sop": {"sops": sop.get("sops", []), "_citation_coverage": sop.get("_citation_coverage", {})},
          "risk": {
              "overall_score": risk.get("overall_score"),
              "gate": risk.get("gate", {}),
              "coverage": risk.get("coverage", {}),
              "risks": risk.get("risks", []),
          },
          "business_model": state.get("business_model", {}),
      }
  ```
- 测试 `tests/api/test_compiler_dashboard.py`：用 `TestClient(app)` + `ProjectDraftRepository().save(ProjectDraft(session_id="d1", idea="x", status="done", **seeded_state))`。
  - `test_dashboard_returns_reshaped`：seed 含 `sop.sops[0].source_ref=["c1"]` + `sop._citation_coverage` + `risk.coverage` + `risk.gate`；断言 200 且响应含 `risk.gate.decision`、`risk.coverage.coverage_pct`、`sop.sops[0].source_ref`。
  - `test_dashboard_404_unknown`：GET 未知 session → 404。
  - `test_dashboard_empty_shell`：seed 空 state → 200 且 `sop=={}`。
- pytest：`venv/Scripts/python.exe -m pytest tests/api/test_compiler_dashboard.py -q` → GREEN。
- 提交：`app/api/orchestrate.py` + `tests/api/test_compiler_dashboard.py`。

### Task 2 — 前端 api client + store 字段
- 新文件 `src/api/compilerDashboardApi.ts`：
  ```ts
  export async function fetchCompilerDashboard(sessionId: string) {
    const r = await fetch(`/api/orchestrate/dashboard/${sessionId}`);
    if (!r.ok) throw new Error(`dashboard ${r.status}`);
    return r.json();
  }
  ```
- `src/store/workspaceStore.ts`（CLEAN）加 `risk: any` 字段（保持与 sop/businessModel 一致；仪表盘也可直接 fetch，但补字段无害且对齐现状）。
- 测试/验证：`tsc --noEmit` 通过（项目若有 tsconfig）。无单测框架，靠类型检查。
- 提交：`src/api/compilerDashboardApi.ts` + `src/store/workspaceStore.ts`。

### Task 3 — 三个面板组件（premium CSS，新文件）
- `src/components/RiskPanel.tsx`：gate 徽章（pass=绿/warn=黄/block=红）+ overall_score；约束覆盖进度条（`coverage.coverage_pct`）+ 未覆盖清单（`uncovered_ids`）；风险列表按 severity 排序，每项可展开看 `linked_constraints` 与 detail。glass card 风格。
- `src/components/CitationPanel.tsx`：遍历 `sop.sops`，每条渲染 `source_ref` 为可点击 chip（`文档/章节/段落` 来自 chunk_id 反查——本任务先用 chunk_id 文本展示，后续接 knowledge 解析）；顶部 `_citation_coverage` 条（有据可查比例）。
- `src/components/ConstraintCoveragePanel.tsx`：复用 risk.coverage 的视觉化（total/covered/pct + uncovered），与 RiskPanel 互补呈现「约束健康度」。
- 验证：`tsc --noEmit` 通过。
- 提交：三个新组件文件。

### Task 4 — 容器 + App 切换（CLEAN 接线）
- 新文件 `src/components/MethodologyDashboard.tsx`：fetch `fetchCompilerDashboard(sessionId)`（从 store 取 sessionId），loading/error 态，响应式网格排布 RiskPanel + ConstraintCoveragePanel + CitationPanel；空态提示「先运行一次编排」。
- 改 `src/App.tsx`（CLEAN）：加 tab 状态，`工作台`→`<Workspace/>`，`产物仪表盘`→`<MethodologyDashboard/>`；顶部两个 tab 按钮（premium 样式）。
- **不碰** `Workspace.tsx` / `orchestrateApi.ts`。
- 验证：`npm run build`（或 `tsc --noEmit`）通过；dev 冒烟（若有 dev server 可起）。
- 提交：`src/components/MethodologyDashboard.tsx` + `src/App.tsx`。

## 5. 质量门（合并前）

- 后端：`venv/Scripts/python.exe -m pytest tests/api/test_compiler_dashboard.py tests/constraint tests/orchestrator tests/agent -q` → 全绿（守住 A/B 的 53 门槛 + 新增）。
- 前端：`tsc --noEmit` / `npm run build` 通过，无类型错误。
- 脏文件保护：仅改 `app/api/orchestrate.py`（CLEAN）+ 新文件；`git status --short` 中用户的 256 个脏文件改动原封不动。
- 合并：同 A/B 纪律，`git merge --no-ff`，不碰 master 无授权。

## 6. 已知偏差 / 预警

- **不做 LLM 生成式 UI agent**：交付数据驱动的结构化面板，非 LLM 实时拼装。若你后续想要 LLM 拼装，单独立项。
- **引用 chip 暂显 chunk_id 文本**：真实 `文档/章节/段落` 反查需查 knowledge 库，本任务不接（保持 D 纯前端+单接口）；可作为后续小增强。
- 若 `ProjectDraftRepository` 在测试中要求真实 DB 且慢，subagent 复用 `tests/conftest.py` 现有 fixture 模式（如内存 repo 或测试 sqlite），不新建重型设施。

## 7. Execution Log（2026-07-17）

- 分支 `feat/generative-ui-dashboard`（基于 master `c550e34`），5 提交：
  - `66daebb` plan（TDD 计划文档）
  - `60cd6f0` Task 1：后端 `GET /api/orchestrate/dashboard/{session_id}`（在 CLEAN 的 `app/api/orchestrate.py` 加路由，未碰脏的 main.py）+ 3 测试
  - `4b8e3fd` Task 2：`src/api/compilerDashboardApi.ts`（新）+ `workspaceStore.ts` 加 `risk` 字段
  - `7934efc` Task 3：`RiskPanel` / `ConstraintCoveragePanel` / `CitationPanel` 三新组件（premium glass 风格）
  - `2a56c4d` Task 4：`MethodologyDashboard` 容器（新）+ `App.tsx` 加「工作台/产物仪表盘」tab 切换
- 全量回归 `tests/constraint tests/orchestrator tests/agent tests/api/test_compiler_dashboard.py` → **56 passed**（A/B 53 + D 3），全绿。
- 前端 `npm run check`（`tsc -b --noEmit`）→ 0 错误。
- 脏文件保护：仅改 CLEAN 的 `app/api/orchestrate.py` + `workspaceStore.ts` + `App.tsx` + 新文件；`orchestrateApi.ts` / `Workspace.tsx`（脏）原封未动；256 个无关脏文件全程保留。
- 偏差：① Task 3 首个 subagent 静默失败（空返回），重派后成功（commit `7934efc`）；② 测试空壳断言适配真实重塑结构（`resp["sop"]["sops"]==[]` 而非 `resp["sop"]=={}`）；③ 引用 chip 暂显 chunk_id 文本（真实反查留待后续）。
- 待用户点头发合并 master（同 A/B 纪律：不碰 master 无授权）。
