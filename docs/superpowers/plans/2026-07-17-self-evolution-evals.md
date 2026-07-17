# 方案 C — 自进化 + Evals（编译器产物评测与自我进化闭环）

> 状态：**调研 + 计划草案，待用户确认后实施**（用户 2026-07-17 12:44 授权"开始"；按约定先做调研+TDD 计划，不急着写重实现）。
> 分支：`feat/self-evolution-evals`（从 master `6009e54` 切出，保护 257 脏文件）。
> 作者：Senior Developer（高级开发工程师）

---

## 1. Context（为什么做）

A/B/D/E 四个升级已合并 master，编译器现在能产出：SOP + 业务模型（A 带方法论引用 `source_ref`/`_citation_coverage`）、Risk=Constraint 覆盖与门禁（B）、可交互仪表盘（D）、SHA-256 可信审计链（E）。

**但有一个核心缺口**：编译器从没被"评测"过——没人给产出的 SOP/业务模型/风险打过分；编译器自身也没有"根据反馈变好"的闭环。这正是方案 C 要补的两半：
- **Evals**：对编译产物做带维度的质量评分（复用 A 的方法论采用度 + B 的约束覆盖率）。
- **Self-evolution**：把高分产物/反馈回流，让编译器下次产出更好（自进化闭环）。

用户原话："C 偏重，可以最后做" → 故本计划把 C **拆成两阶段**，Phase 1（Evals）风险低价值高先落地，Phase 2（自进化，偏重）单独确认后再做。

---

## 2. 调研发现（实测，防假设错）

### 2.1 已存在、可复用的能力
| 能力 | 位置 | 说明 | 与 C 的关系 |
|------|------|------|------------|
| `PRDQualityScorer` | `app/core/prd_quality_scorer.py` | 规则+LLM 两层评分，产出 `QualityReport`/`QualityDimension`，有 `get_quality_level()` | **Evals 评分原语**，但只评 **PRD 输入文本** |
| `PRDRefiner` | `app/core/prd_refiner.py` | 多轮"评分→LLM 改写→再评分"自优化闭环（`RefinementStep` 记录 before/after） | **自进化闭环原语**，但只作用于 **PRD 文本** |
| `ReviewerAgent` | `app/orchestrator/agents/reviewer.py` | 新 DAG 里的 LLM 评审：约束覆盖 + 漏洞 + 回环（approved/gaps） | 是 Eval 钩子雏形，但产出是"通过/不通过 + gap 列表"，**非带维度评分报告** |
| A 方法论引用 | `sop._citation_coverage` / `sop.sops[i].source_ref` / `business_model.{flows,roles,rules}[i].source_ref` | 编译器实时检索方法论库留下的可追溯引用 | Evals 的"方法论采用度"维度数据源 |
| B 约束覆盖 | `risk.coverage.{total,covered,coverage_pct}` / `risk.gate.decision` | 需求满足型覆盖引擎 + 门禁 | Evals 的"约束覆盖率/风险健康"维度数据源 |
| E 审计链 | `trusted_audit.verified` | SHA-256 链可独立 verify | Evals 的"审计完整性"维度数据源 |
| D 仪表盘 | `app/api/orchestrate.py` dashboard 端点 + `MethodologyDashboard` + 各面板 | 已注册的干净路由，可加段 | Evals 结果的前端落点 |
| `metrics.py` | `app/core/metrics.py` | **性能/基础设施指标**（Prometheus、请求计数、LLM 调用统计） | **与质量评分无关，排除** |

### 2.2 核心缺口
1. **编译器产物零评测**：没有对 `ProjectDraft`（SOP+业务模型+风险）的质量评分，只有 ReviewerAgent 的二元通过/不通过。
2. **编译器无自进化**：`PRDRefiner` 只优化 PRD *输入*；编译器的 *产物* 和 *agent prompt* 没有任何基于反馈的进化闭环。
3. **Evals 未与 A/B/E 打通**：A 的引用度、B 的覆盖率、E 的完整性本来就是现成的质量信号，却没被聚合成一份评分报告。

### 2.3 关键架构事实（复用边界）
- 仪表盘端点 `app/api/orchestrate.py` 是 **CLEAN 已注册路由**（D/E 已改过、已合 master、不在 257 脏文件中）→ 加 `evaluation` 段安全，**零碰脏 `main.py`**。
- `ProjectDraft.to_dict()` 是仪表盘数据源；A/B/E 段都是**端点内即时计算**（不持久化 schema）→ Evals 同样用"端点即时计算"模式，避免动 draft 存储 schema（YAGNI、低风险）。
- `QualityReport`/`QualityDimension` 模型在 `prd_quality_scorer.py`，可**直接 import 复用**，不重复造轮子。
- 测试纪律：所有 pytest 走 `./venv/Scripts/python.exe`；Evals 的确定性维度（规则类）不依赖 LLM，可用 mock/无 LLM 测；LLM 深评维度做成可关（默认规则即可测）。

---

## 3. 范围决策（YAGNI）

- **做 Phase 1（Evals）**：编译器产物评分 + 仪表盘呈现 + 测试。风险低、价值高、复用 A/B/E。
- **Phase 2（自进化）单独确认**：写库回流 + 低分精炼闭环偏重，且涉及 knowledge 库**写入**（A 目前只检索）→ 先列清楚范围，用户点头再实施。
- **不做**：不碰 `main.py`、不动 `ProjectDraft` 存储 schema、不引入新的 LLM 评测供应商、不重构旧 `app/agents/` 体系。

---

## 4. Phase 1 — Evals（本次实施，TDD）

### T1 · 编译器产物评分器（内核）
- 新建 `app/evaluation/compiler_evaluator.py` + `__init__.py`。
- `CompilerOutputEvaluator.evaluate(state: dict) -> QualityReport`（复用 `QualityReport`/`QualityDimension`）。
- **规则维度（确定性，必做，可单测无 LLM）**：
  1. `方法论采用度`：取 `sop._citation_coverage.coverage`（0..1）→ 分 = coverage×100；details 记 covered/total。
  2. `约束覆盖率`：取 `risk.coverage.coverage_pct`（B）→ 分 = coverage_pct。
  3. `风险门禁健康`：取 `risk.gate.decision`（pass=100 / warn=70 / block=40）→ 分。
  4. `审计完整性`：取 `trusted_audit.verified`（E）→ pass=100 / fail=0 → 分。
  5. `结构完整度`：SOP 有 `sops[]`、business_model 有 `flows/roles/rules` → 覆盖率% → 分。
- 权重合成 `overall_score`；`is_passed = overall_score >= 阈值(默认70)`；`improvement_points` = 分<60 的维度数。
- **可选 LLM 深评维度（默认关，可开）**：复用 `PRDQualityScorer._calculate_llm_based_score` 思路，对 SOP 文本做连贯性/可执行性评分；测试用 mock provider，不依赖真 LLM。
- 入参缺字段（无 A/B/E）→ 该维度给 0 分并记 `details="未提供"`，**优雅降级**不崩。

### T2 · 接入仪表盘端点
- `app/api/orchestrate.py` dashboard 端点负载追加 `evaluation` 段：调用 `CompilerOutputEvaluator.evaluate(state)`（端点即时计算，不持久化）。
- 复用已注册干净路由，零碰脏 `main.py`。

### T3 · 前端 Evals 面板 + 接入
- 新建 `src/components/CompilerEvalPanel.tsx`（premium glass，复用 D/E 风格）：总分 pill + 各维度条形（按分着色 emerald/amber/red）+ pass/fail 徽章 + improvement_points。
- `src/api/compilerDashboardApi.ts` 加 `Evaluation`/`QualityDimension` 类型；`MethodologyDashboard.tsx` 栅格加 `CompilerEvalPanel`。
- 仅改 D/E 创建的干净文件，`npm run check`(tsc) 须 0 错误。

### T4 · 后端测试（含边界/防崩）
- `tests/evaluation/test_compiler_evaluator.py`：
  - 全维度满分的 draft → overall 高、is_passed True。
  - 缺 A/B/E 字段的 draft → 优雅降级（对应维度 0 分、不抛）。
  - 空 draft（`{}`）→ 安全返回低分报告。
  - 篡改 `trusted_audit.verified` → 审计维度 0 分。
- `tests/api/test_dashboard_evaluation.py`：仪表盘负载含 `evaluation` 段且结构正确。
- 全走 `./venv/Scripts/python.exe`。

### T5 · 全量回归 + 文档执行日志
- 全量 pytest（期望 62 → 68+ passed）、`npm run check` 0 错误、确认 257 脏文件未动、特性分支未合 master。
- 追加本计划 Execution Log + 每日记忆。

---

## 5. Phase 2 — 自进化闭环（仅 outline，需单独确认）

> 偏重，涉及 knowledge 库**写入**（A 目前只检索）与多轮精炼。列范围供确认，不擅自实施。

- **T6 · 高分产物回流**：`CompilerOutputEvaluator` 评分 ≥ 阈值时，把 SOP/业务片段 + eval 作为 exemplar 写入方法论知识库（需新增 `KnowledgeService.store` / 复用 `MethodologyBridge` 写入路径，A 当前仅 `retrieve`）。
- **T7 · 低分精炼闭环**：eval < 阈值时，对低分维度对应段触发 `PRDRefiner` 式精炼（mirror `refine()` 但作用于 SOP/business 段，非 PRD 文本），再评测直至达标或达最大轮次。
- **T8 · 进化可观测**：回流/精炼事件写入 E 的审计链（SHA-256），保证自进化过程也可信追溯。

---

## 6. 复用点清单
- `QualityReport`/`QualityDimension`（`prd_quality_scorer.py`）→ 直接 import。
- A `source_ref`/`_citation_coverage`、B `coverage_pct`/`gate`、E `trusted_audit` → Evals 维度数据源。
- D `MethodologyDashboard` 栅格 + 面板 glass 风格 → `CompilerEvalPanel` 对齐。
- `bsc-safe-merge` 技能 → 合并前安全协议（脏树零重叠 + `--no-ff`）。

## 7. 质量门
- 全量 pytest 绿（venv 解释器）；`npm run check`(tsc) 0 错误。
- 257 用户脏文件零触碰；不碰 `main.py`、不改 `ProjectDraft` schema。
- 所有 Evals 维度确定性可测（规则类无 LLM 依赖）；LLM 深评默认关、可 mock。

## 8. 回滚
- 全程特性分支；合并前用户确认（`--no-ff`）。回滚 = `git checkout master` + 删分支，用户文件不受影响。

---

## 9. 执行日志（Execution Log）

| 时间 | 提交 | 内容 |
|------|------|------|
| 12:44 | — | 用户授权"开始"；建分支 `feat/self-evolution-evals`（master `6009e54` 起，保护 257 脏文件） |
| 12:50 | — | 调研完成：确认仓库已有 PRDQualityScorer(PRD)、PRDRefiner(PRD)、ReviewerAgent(LLM 二元)；metrics.py 是性能指标排除；_citation_coverage/coverage_pct/gate.decision/trusted_audit.verified 字段形状实测确认 |
| 12:54 | — | TDD 计划落定（Phase1 T1-T5 + Phase2 outline）；用户确认 A（按 Phase1 开干） |
| 12:56 | — | T1 内核 `app/evaluation/compiler_evaluator.py` 完成：5 规则维度（方法论采用度/约束覆盖率/风险门禁健康/审计完整性/结构完整度），复用 QualityReport/QualityDimension，缺字段优雅降级 |
| 12:58 | — | T4 单元测试 `tests/evaluation/test_compiler_evaluator.py` 6 用例（满分/缺字段降级/空 state/篡改审计/门禁映射/部分结构）→ 6 passed |
| 13:00 | — | T2 仪表盘端点 `app/api/orchestrate.py` 追加 `evaluation` 段（端点即时计算，零碰脏 main.py） |
| 13:02 | — | T3 前端 `CompilerEvalPanel.tsx`（总分 pill + 5 维度条形 + pass/fail 徽章 + 改进建议，premium glass）+ API 类型 Evaluation/QualityDimension + 接入 MethodologyDashboard 栅格 |
| 13:03 | — | T4 仪表盘测试 `tests/api/test_dashboard_evaluation.py`（正常/空 draft 2 用例）。全量回归 **70 passed**（62 既有 + 6 eval 单元 + 2 dashboard）。`npm run check`(tsc) **0 错误**。脏文件 257+1 计划文档 = 265（用户 257 原封未动）。 |

### 偏差记录
- `evaluator._methodology_dimension`：sop/bm 各自的 `_citation_coverage.coverage` 取均值再 ×100 → 介于 0..100。若两者均缺失则 0 分标注「未提供」。
- `.dict()` → `.model_dump()`：因项目用 Pydantic v2，`.dict()` deprecation 警告，改用 `.model_dump()` 序列化 QualityReport。
- 防假设核验：实现前实测确认 `_citation_coverage` 键 {coverage, covered, total, flagged}、`risk.gate.decision`、`risk.coverage.coverage_pct`、`build_trusted_audit()` 返回含 `verified` 字段。零假设错。
- LLM 深评维度按 YAGNI 原则不在 Phase 1 实现（premature），仅保留规则维度。文档注记可扩展性。
- 等待用户授权合并 master（`--no-ff`，走 bsc-safe-merge 技能安全协议）。
