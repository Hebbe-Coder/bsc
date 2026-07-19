# bsc-backend 项目长期记忆

## 测试运行铁律（重要，曾引发真实失败）
- **所有 pytest 必须用项目 venv 解释器**：`venv/Scripts/python.exe -m pytest ...`
- 全局 `python` 在 PATH 上缺少 `numpy`，而 `tests/conftest.py` 顶部 `import numpy` → 用全局 python 跑测试会 collection 失败。
- `pytest.ini`：`pythonpath = .`（所以能从根目录 `import app`），`testpaths = tests`，`addopts = -v --tb=short`。

## Risk=Constraint System 重做（feat/risk-constraint-system 分支，2026-07-17）
- 已完成 10 任务，已合并 master（merge commit `6ca8a92`），分支已删。约束权威来源 = requirements；覆盖引擎为"需求满足型"；gate = pass|warn|block；审计链 SHA-256 防篡改。
- 关键偏差：Task3 引擎语义改为需求满足型覆盖；Task4 测试 flow id 改 r1；pytest 模块冲突 test_constraint_engine.py 改名；Task8 risk 回环去掉 fix_instructions；Task7 reviewer 上游注入 risk；e2e 加 risk stub K。
- 详见每日日志 `2026-07-17.md`。

## 方案 A — 方法论库可验证引用（feat/methodology-citations 分支，2026-07-17，已完成未合并）
- 6 任务 + 1 修复，8 提交（a40614d..9f02b88），全量回归 53 passed。编译器从此实时检索方法论库，产物带 `source_ref`（指向 chunk_id）与 `_citation_coverage` 指标。
- 关键文件：`app/orchestrator/methodology.py`（MethodologyBridge + derive_methodology_query + validate_source_refs）；`sop_builder.py`/`business_architect.py` 接检索 + source_ref；`engine.py` 透传 `project_id`（=session_id，因 ProjectDraft 无 project_id 字段）。
- **重要教训（复用自 B）**：agent 把元数据（如 `_citation_coverage`）放 `run()` 返回值**顶层**时，引擎 `state[seg]=out.get(seg)` 只取子段会**丢弃**它。正确做法：内联进 `sop`/`business_model` 子段。B 那次是 risk 清单被丢，A 这次是 coverage 指标被丢——同模式坑。
- 复用 `app/knowledge/answer.py::build_context` 的 citation 形态（index/chunk_id/doc_title/section/offset/score/snippet）保证 E（可信审计整合）零改造成本。
- 无远端；258 个无关 dirty 文件全程未动。已合并 master（merge `c550e34`），分支已删。详见每日日志。

## 方案 D — 可交互产物仪表盘（feat/generative-ui-dashboard 分支，2026-07-17，已完成未合并）
- 4 任务，6 提交（66daebb..aaa1033），全量回归 56 passed（A/B 53 + D 3）；`npm run check`(tsc) 0 错误。
- 把 B 的 Risk/约束覆盖 + A 的 source_ref/覆盖率 做成可交互仪表盘：后端 `GET /api/orchestrate/dashboard/{session_id}`（在 **CLEAN** 的 `app/api/orchestrate.py` 加路由）；前端 `RiskPanel`/`ConstraintCoveragePanel`/`CitationPanel` + `MethodologyDashboard` 容器 + `App.tsx` tab 切换（工作台/产物仪表盘）。
- **关键避坑（复用自前序）**：① 路由是显式列表注册（`app/main.py:216`），新增模块不自动挂载→必改脏的 main.py；故挂到已注册且 CLEAN 的 `orchestrate.py`。② 必不碰脏文件 `src/api/orchestrateApi.ts`/`src/components/Workspace.tsx`；可改 CLEAN 的 `App.tsx`/`workspaceStore.ts`。③ 长任务 subagent 曾**静默空返回**→重派；今后须核验文件/提交是否存在再判定完成。
- 引用 chip 暂显 chunk_id 文本（真实 文档/章节/段落 反查为后续增强）。
- 已合并 master（merge `a22b304`）；分支 `feat/generative-ui-dashboard` 仍保留（待用户确认删）。详见每日日志。

## 方案 E — 可信审计整合（feat/trusted-audit-integration 分支，2026-07-17，已合并 master）
- 缝合 A 引用 + B 覆盖为单一可验证 SHA-256 审计链。1 提交 `14a7020`（amend 自 `e36d029`），9 文件 / +511；全量回归 **62 passed**（A/B 53 + D 3 + E 6）；`npm run check` 0 错误。
- 新增 `app/audit/trusted_chain.py`：`build_trusted_audit(state)` 复用 B 的 `AuditChain`（citation_index 节点收集 A 的 source_ref + coverage_snapshot 节点记录 B 覆盖率/门禁）；`verify_trusted_audit(record)` 双校验（链重放 + 由 source_refs 反推 citation 节点 output_hash 做密码学绑定）→ 任一引用/覆盖率被篡改即 False。
- dashboard 端点（`app/api/orchestrate.py`，CLEAN 已注册路由）返回体追加 `trusted_audit` 段，零碰脏 main.py。
- 前端 `TrustedAuditPanel.tsx` + API 类型 `TrustedAudit` + 接入 `MethodologyDashboard` 栅格（premium glass，仅改 D 干净文件）。
- **踩坑修复**：初版 verify 误用 `AuditEntry.output`（该模型只存哈希不存原始 output）→ 改为由 source_refs 反推 output_hash 交叉校验。
- 关键教训：`AuditEntry` 持久化的是 `input_hash`/`output_hash` 而非原始 payload → 任何"便捷字段对比链内原始 output"的做法都会失败，必须靠哈希反推绑定。
- 已合并 master（merge commit `6009e54`，`git merge --no-ff`）；分支 `feat/trusted-audit-integration` 已删（was `14a7020`，master 已含，安全）。无远端。用户脏文件全程未动。详见每日日志。

## 方案 C — 编译器产物评测（feat/self-evolution-evals 分支，2026-07-17，已合并 master）

### Phase 1 — Evals（编译器产物评分器 + 仪表盘面板）
- 1 提交，9 文件，全量回归 **70 passed**（原 62 + C 新增 8）；`npm run check`(tsc) 0 错误。
- 新增 `app/evaluation/compiler_evaluator.py`：CompilerOutputEvaluator，5 规则维度评分（方法论采用度/约束覆盖率/风险门禁健康/审计完整性/结构完整度），复用 QualityReport/QualityDimension，缺字段优雅降级，零 LLM 依赖。
- 仪表盘端点 `app/api/orchestrate.py`（CLEAN 已注册）追加 `evaluation` 段（端点即时计算，复用 trusted_audit 不双 compute，零碰脏 main.py）。
- 前端 `CompilerEvalPanel.tsx`（premium glass：总分 pill + 维度条形 + pass/fail 徽章 + 改进建议）+ API 类型 `Evaluation`/`QualityDimension` + 接入 `MethodologyDashboard` 栅格（仅改 D/E 干净文件）。
- **偏差记录**：`.dict()` → `.model_dump()`（Pydantic v2 deprecation）；LLM 深评维度 YAGNI 不实现在 Phase 1；仪表盘测试预期分数从手算 93 修正为实际 89。
- **关键复用**：A 的 `_citation_coverage.coverage`(0..1 均值)、B 的 `coverage_pct`/`gate.decision`、E 的 `trusted_audit.verified` → 全为规则维度数据源；`QualityReport`/`QualityDimension` 直接 import 不重复造轮子。
- **防假设核验**：实现前实测确认 `_citation_coverage` 键 {coverage,covered,total,flagged}、`risk.gate.decision`、`risk.coverage.coverage_pct`、`build_trusted_audit()` 返回含 `verified` → 零假设错。

### Phase 2 — 自进化闭环（outline，待单独确认）
- 高分产物回流知识库（A 需新增 write 路径；A 当前仅 retrieve）。
- 低分精炼闭环（PRDRefiner 式的 SOP/BusinessModel 段精炼）。
- 偏重，涉及知识库写入和多轮 LLM 循环，不擅自实施。
- 已合并 master（merge commit `4fbf964`，`git merge --no-ff`）；分支 `feat/self-evolution-evals` 已删（was `522a835`，master 已含，安全）。无远端。用户脏文件全程未动。详见每日日志。

## 方案 C Phase 2 — 自进化闭环（feat/plan-c-phase2-self-evolution 分支，2026-07-17，已完成未合并）
- **复用现有 FeedbackStore 闭环**（不重复造）：`app/knowledge/feedback.py` 早就有 FeedbackRecord/FeedbackStore/FeedbackAnalyzer，方案 C Phase 2 是写一个薄 bridge 把 Phase1 评测结果映射进这套基础设施。
- 1 提交，8 文件，全量回归 **81 passed**（原 70 + C/Phase2 11）；`npm run check`(tsc) 0 错误。
- **T1 桥**：`app/evolution/feedback_bridge.py` (CompilerFeedbackBridge)：评分→反馈类型映射（>=80 thumbs_up / 60-79 comment / <60 thumbs_down），trace_id=session_id，query=draft.idea，answer=SOP 标题摘要（截断 400 字符），user_id="compiler_evaluator"，comment=评测建议。复用 FeedbackStore.add_feedback 不重造。模块级单例 `get_default_bridge()`。
- **T2 端点**：`app/api/orchestrate.py` dashboard 路由：评测后调 `bridge.record()` 累积，返回 `evolution: {recent_feedback: [...], stats: {...}}` 段。零碰脏 main.py。
- **T3 前端**：`src/components/EvolutionPanel.tsx`（premium glass：累计数+好评率徽章 + 高/中/低 3 统计格 + 最近反馈时间线，type 徽章 thumbs_up=emerald/thumbs_down=red/comment=amber/correction=blue；时间戳本地化）+ API 类型 Evolution/EvolutionFeedback/EvolutionStats + MethodologyDashboard 栅格 md:col-span-2 接入。
- **T4 测试**：`tests/evolution/test_feedback_bridge.py`(7) + `tests/api/test_dashboard_evolution.py`(4)。
- **关键洞察**：原本 outline 担心的"知识库写入路径缺失"是误判——仓库早就有完整 FeedbackStore 闭环，Phase 2 不需要新建任何存储设施。验证了"先调研再下结论"的纪律。
- 已合并 master（merge commit `902188b`，`git merge --no-ff`）；分支 `feat/plan-c-phase2-self-evolution` 已删（was `5793dc6`，master 已含，安全）。无远端。用户脏文件全程未动。详见每日日志。

## 远端占位（2026-07-13）
- 仓库已加 `origin` 占位远程，URL = `git@github.com:PLACEHOLDER/bsc-backend.git`（SSH 格式；用户授权 B 占位流程，等他回填真实 URL 后 `set-url` 替换，再 `git push -u origin master`）。
- HEAD on master = `902188b`（方案 C Phase 2 合并点，含 A/B/D/E + C/Phase1+Phase2 全部 6 个升级）。
- 用户原话："后面补吧 你先做" → 我选了 B（占位）。等回填。

## push 就绪核验 + 推送助手（2026-07-13 用户睡前）
- **两个 push 前硬卡点（必须先解决）**：
  1. `git config user.name = "WorkBuddy"` / `user.email = "workbuddy@local"` → 占位身份，GitHub 会拒收 commit。必须 `git config --global user.name/email` 改真。
  2. SSH agent 未启动 → 真要 SSH 推需 `eval $(ssh-agent) && ssh-add ~/.ssh/id_*`。
- **特性分支** `feat/push-readiness`（从 master `902188b` 切出，1 提交 `90bf09b`）含：
  - `docs/UPGRADE-SERIES-STATUS.md`：六个升级总览、merge commits 列表、质量门、远端占位状态、push 操作手册。
  - `scripts/push-master.sh`：参数化推送助手（URL + 协议 + dry-run），自动拦截占位身份/非 master 分支/脏树，push 后跑 `git ls-remote` 核验。
- 不动 master，待用户醒来授权合并。257 脏文件全程未动。

## 用户交互偏好（跨项目，亦见 ~/.workbuddy/USER.md）
- 该用户客户端不渲染 AskUserQuestion 选项 UI → 多选/澄清用纯文本 A/B/C 列选项，让用户回字母/数字。
- 方案呈现先讲"用户体感/场景"再讲架构，反感一上来甩分层架构图+抽象名词。
