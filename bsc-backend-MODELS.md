# BSC Backend 数据模型与架构债分析报告（最终版）

**分析日期**: 2026-07-08
**分析轮次**: 4轮深度代码追踪 + 引用验证 + 字段级对比 + 双入口底层分歧确认
**结论**: 生产路径无 Pydantic 校验，三套数据模型并存，两套 Agent 实现底层机制完全不同（LLM vs 正则启发式）

---

## 一、核心发现：三套数据模型并存

### 1.1 模型全景

| 模型 | 定义位置 | Pydantic校验 | 生产路径 | 消费方 |
|------|---------|-------------|----------|--------|
| **模型A** BusinessSystemSchema | `app/schemas/business_schema.py` | ✅ 严格（workflow闭环+风险引用） | ❌ 未接入 | 仅 compiler.py / mock_compiler.py |
| **模型B** Pipeline dict | `app/core/bsc_pipeline.py` / `async_pipeline.py` | ❌ 无 | ✅ `POST /bsc/compile` | bsc_api / exporters / visual_binding / 前端 |
| **模型C** Skill Chain | `app/chains/*.py` (8个Chain) | ❌ 无 | ✅ `POST /api/skill/execute` | skill_routes / 前端技能系统 |

### 1.2 模型B 字段清单（生产真实产出）

来源：`compile_to_business_system()` / `compile_to_business_system_async()`

| 字段 | 来源 Agent | 类型 | 说明 |
|------|-----------|------|------|
| `business_domain` | Business Understanding | `str` | 业务领域 |
| `objectives` | Business Understanding | `list[{objective, target, priority?, kpi?}]` | 业务目标 |
| `roles` | SOP | `list[{role, responsibilities[]}]` | 角色职责 |
| `workflow` | SOP | `list[{step, name, action, owner?, sla?}]` | 流程步骤（线性） |
| `responsibilities` | SOP | `list` | 职责清单 |
| `sla` | SOP | `list` | SLA配置 |
| `metrics` / `kpi` | SOP | `list[{name, formula, target, owner?, current?, target_value?}]` | KPI（冗余双字段） |
| `risks` | flatten_risks(Risk) | `list[{risk, severity, mitigation, category?}]` | 扁平化风险 |
| `risk` | Risk | `{process_risks[], organization_risks[], system_risks[], compliance_risks[]}` | 分类风险 |
| `strategy` | Strategy | `{growth_opportunities?[]}` | 战略分析 |
| `optimization` | Optimization | `{recommendations?[]}` | 优化建议 |
| `composed` | Composer | `{report?{title, executive_summary, sections[]}}` | 组装结果 |
| `report` | composed.report | `dict` | 冗余字段 |
| `template` | （可选） | `{id, name, industry, config}` | 行业模板 |

### 1.3 模型A vs 模型B 字段级不兼容

`BusinessSystemSchema(**bs)` 必抛多个 ValidationError：

| 字段 | 模型A要求 | 模型B实际 | 适配难度 |
|------|----------|----------|---------|
| `metadata` | 必填，含 system_id/objective/domain/version | **完全缺失** | 🟢 易合成 |
| `modules` | `list[BusinessModule]`（id/name/description/priority/dependencies） | **缺失** | 🟡 需从workflow反推 |
| `workflow` | 图结构：`WorkflowNode`（id/type=start\|end\|action\|decision/next_node_id/conditions）+ 闭环校验 | 线性步骤：`{step, name, action}` | 🔴 需重构为图 |
| `kpi` | `KpiTree`（branches+weights） | `list[{name, formula, target}]` | 🔴 结构完全不同 |
| `metrics` | `list[KpiMetric]`（id+branch枚举+direction枚举+formula非占位符校验） | `list[{name, formula, target, owner?}]` | 🟡 需生成id+映射枚举 |
| `risk` | `list[RiskItem]`（id+description+probability+impact+score=概率×影响+Mitigation模型+category枚举7类） | `list[{risk, severity, mitigation(str)}]` | 🔴 需拆分severity+构造Mitigation |
| `risk.category` | 枚举：operational/technical/quality/capacity/compliance/financial/strategic | 自由字符串（可能含枚举外的"resource"） | 🟡 需映射 |

**关键约束**：模型A的 `validate_closed_loop`（workflow必须start→end可达）和 `validate_risk_module_refs`（风险必须引用真实module id）在适配器合成的数据上会**永远空过**——合成出的modules是空壳，严格校验的业务价值被稀释。

---

## 二、架构债：双入口底层完全分歧（第四轮确认）

### 2.1 双实现全景

| 维度 | 主链路 Agent | Studio Agent |
|------|-------------|--------------|
| **基类** | `app/agents/base_agent.py` BaseAgent | `app/agents/protocol.py` 类型化Protocol |
| **文件** | `business_understanding_agent.py` + `base_agent.py` 内的 SOPAgent/RiskAgent/StrategyAgent/OptimizationAgent | `sop_agent.py` / `risk_agent.py` / `strategy_agent.py` / `optimization_agent.py` |
| **注册** | `AgentFactory.AGENT_REGISTRY` | `studio_orchestrator.py:118-130` |
| **入口** | `POST /bsc/compile` | `POST /studio/ask` |

### 2.2 字段错位（原假设修正）

~~原假设：Studio Agent 读 `processes` 但 BU 产出 `process_flow`，会读到空走兜底。~~

**第四轮查证结论：错位假设不成立。** 两条路径各自内部完全自洽：

```
主链路: business_understanding_agent.py → 产出 process_flow  ← composer.py 读 process_flow  ✅ 自洽
Studio: engines/business_understanding.parse_documents → 产出 processes  ← 4个protocol Agent 读 processes  ✅ 自洽
```

Studio 的 protocol Agent 能拿到真实 `processes`，**不会**退化到默认 SOP。

### 2.3 双入口底层分歧（比字段错位更严重）

**同一份 PRD，两个入口给出定性不同的结果：**

| 维度 | 主链路 `/bsc/compile` | Studio `/studio/ask` |
|------|----------------------|---------------------|
| **业务理解生产者** | `business_understanding_agent.py`（**LLM**，输出 process_flow/core_objectives） | `engines/business_understanding.parse_documents`（**纯正则**，输出 processes/objectives） |
| **下游分析引擎** | `base_agent` LLM Agents（每次重读 PRD 调 LLM） | `protocol` 版 Agent（`on_generate`/`on_analyze`，**纯本地启发式、无 LLM**） |
| **SOP生成** | LLM 生成 | `SLA_BASELINE` 硬编码表 + 动词匹配（`sop_agent.py:7-14`） |
| **性质** | 全程 LLM 驱动 | 除资产生成外是确定性规则管线 |

**风险**：
1. 两条管线会**悄悄分叉**——用户不知道 `/studio/ask` 的结果质量受正则规则局限（`_extract_processes` 只按动词出现抽句子，没有语义）
2. 双实现的第四处实例：业务理解生产者有两套（LLM vs 正则），分析引擎也有两套（LLM vs 本地启发式）

### 2.4 主管线本质

主链路是**提示词链**，不是强类型数据流：
- `base_agent.run` 每个 Agent 只拿 PRD chunks + 上游结果 JSON 重新调 LLM
- 不消费 BU 产出的强类型字段
- 模型B是多个独立 LLM JSON 的拼装物，没有单一 schema 驱动

---

## 三、消费方字段依赖

### 3.1 后端消费方

| 消费方 | 访问字段 | 兼容度 |
|--------|---------|--------|
| `engines/visual_binding.py` | `metrics/kpi`, `workflow`, `risk`, `modules` | ⚠️ 依赖 `modules`（模型B不产出） |
| `exporters/ppt_exporter_v2.py` | `metadata`, `business_domain`, `modules`, `workflow`, `kpi/metrics`, `risk/risks`, `strategy`, `optimization` + 大量fallback | ⚠️ 兼容两套 |
| `exporters/html_exporter.py` | 同上 | ⚠️ 同上 |
| `exporters/word_exporter.py` | `business_domain`, `objectives`, `roles`, `workflow`, `risks`, `strategy`, `report` | ✅ 仅模型B |
| `exporters/markdown_exporter.py` | 同上 | ✅ 仅模型B |
| `exporters/xlsx_exporter.py` | `modules`, `workflow`, `risk`, `metrics/kpi` | ⚠️ 依赖 `modules`（模型A独有） |
| `exporters/pdf_exporter.py` | `business_domain`, `report`, `objectives`, `roles`, `workflow`, `risks` | ✅ 仅模型B |

### 3.2 前端消费方

| 文件 | 说明 |
|------|------|
| `src/api/bscApi.ts` | `BusinessSystem` interface — 完全匹配模型B |
| `src/utils/bscConverter.ts` | 基于模型B |
| `src/store/presentationStore.ts` | 技能API调用，不走compile路径 |
| `src/components/PipelineSummary.tsx` | 基于模型B |

**结论**：前端完全基于模型B设计，与 BusinessSystemSchema 无交集。

---

## 四、死代码追踪

### 4.1 死代码清单

| 文件 | 被引用次数 | 引用来源 | 判定 |
|------|----------|---------|------|
| `app/core/pipeline.py` | 0 | — | ✅ 可安全删除 |
| `app/core/compiler.py` | 2 | `app/core/__init__.py`（导出）、`visual_binding.py`（仅`__main__`测试） | ⚠️ 生产零引用，可删 |
| `app/services/mock_compiler.py` | 2 | `app/services/__init__.py`（导出）、`compiler.py`（调用） | ⚠️ 随compiler一并可删 |
| `app/schemas/business_schema.py` | 3 | `compiler.py`、`mock_compiler.py`、`pipeline.py` | ⚠️ 生产零引用，但本身是高质量Schema |

### 4.2 引用链验证

- `app/core/__init__.py` 导出 `compile_business_system`，但全工程无 `from app.core import ...`
- `app/services/__init__.py` 导出 `MockCompiler`，同样零引用
- `visual_binding.py:457` 的 `compile_business_system` 调用仅在 `if __name__ == "__main__"` 块

---

## 五、REVIEW_REPORT.md 错误结论纠正

旧报告（2026-07-03）以下结论**在生产路径上不成立**：

| 旧结论 | 实际情况 |
|--------|---------|
| "Pydantic v2严格验证：BusinessSystemSchema包含workflow闭环验证、风险模块引用验证" | ❌ 严格校验的Schema在生产路径零引用。`POST /bsc/compile` 产出的是未校验的dict |
| "输入验证：Pydantic min_length/max_length/pattern" | ⚠️ 仅API请求层（CompileRequest）有校验，产出数据无校验 |
| "数据模型：Pydantic v2模型完整，验证严格" | ❌ 模型存在但未接入生产路径 |
| "Mock编译器：5行业模板，关键词+语义检索" | ⚠️ mock_compiler.py引用的retrieval_engine缺失，有try/except降级 |

---

## 六、修复方案评估

### 方案A：生产路径升级到 BusinessSystemSchema

| 维度 | 评估 |
|------|------|
| 工作量 | 🔴 大 |
| 改造范围 | pipeline层 + 所有消费方（10+文件） |
| 风险 | workflow结构差异巨大（节点图 vs 步骤列表），风险结构差异（统一RiskItem vs 四类） |
| 前端影响 | 🔴 Breaking Change — 前端 BusinessSystem interface 需完全重写 |
| 收益 | ✅ 严格校验 + 类型安全 |
| 结论 | 成本过高，且合成的modules/graph会让严格校验空过 |

### 方案B：为生产路径定义新 Pydantic 模型（推荐）

| 维度 | 评估 |
|------|------|
| 工作量 | 🟡 中 |
| 改造范围 | 新增 `ProductionBusinessSystem` 模型 + pipeline返回前校验 |
| 风险 | 低 — 不破坏现有消费方 |
| 前端影响 | 🟢 零 |
| 收益 | ✅ 生产路径有Schema校验 + 统一模型 + 不破坏现有 |
| 结论 | 性价比最高 |

### 方案C：适配器（仅用于导出）

| 维度 | 评估 |
|------|------|
| 工作量 | 🟡 中 |
| 改造范围 | 新增 模型B→模型A 适配器，仅用于导出场景 |
| 风险 | 低 — 不阻塞实时链路 |
| 收益 | ✅ 导出时有严格校验，实时链路不受影响 |
| 结论 | 适合作为方案B的补充 |

---

## 七、推荐执行路线

### 阶段一：清理（零风险，立即见效）— ✅ 全部完成

1. ~~删除 `app/core/pipeline.py`（零引用）~~ ✅
2. ~~删除 `app/core/compiler.py` + `app/services/mock_compiler.py`（生产零引用）~~ ✅
3. ~~清理 `app/core/__init__.py` 和 `app/services/__init__.py` 死导出~~ ✅
4. ~~修正 `REVIEW_REPORT.md` 错误结论~~ ✅
5. ~~删除 `app/core/orchestrator.py`（坏代码）~~ ✅
6. ~~归档 `python-backend/`（孤儿分叉）~~ ✅

### 阶段二：加固（中风险，高收益）— ✅ 全部完成

1. ~~为模型B定义 Pydantic 模型 `ProductionBusinessSystem`~~ ✅ → `app/schemas/production_schema.py`
2. ~~在 `compile_to_business_system()` / `compile_to_business_system_async()` 返回前做 Schema 校验~~ ✅
3. ~~校验失败降级 + 日志告警（不直接报错，保持可用性）~~ ✅
4. ~~清理 `app/schemas/__init__.py` 中对 business_schema 的死导出~~ ✅
5. ~~标记 `business_schema.py` 为 DEPRECATED~~ ✅

### 阶段三：统一（长期，可选）— 部分完成

1. ~~增强 `ProductionBusinessSystem` 业务逻辑校验（workflow序号连续、risk描述完整性、kpi字段完整性）~~ ✅
2. ~~标记 `business_schema.py` 废弃~~ ✅（保留文件但加 DEPRECATED 标记，因 repair_engine.py 仍引用）
3. ~~统一双入口：Studio 路径接入主链路 LLM Agent~~ ✅ → `studio_orchestrator.py` v4
4. ~~`validators/repair_engine.py` 已重写为 v2，适配生产模型~~ ✅
5. **架构债**：`app/services/` 目录已删除。所有 Service 类（LLMService、AsyncLLMService、LangChainService、CacheService、UserPreferenceService）实际位于 `app/core/` 而非 `app/services/`，属架构分层债，建议后续单独迁移（40+ 处 `from app.core.*service` 导入需更新）

---

## 附录：文件引用索引

| 文件 | 关键行 | 说明 |
|------|--------|------|
| `app/schemas/business_schema.py` | 全文 | 模型A定义（严格Pydantic） |
| `app/core/bsc_pipeline.py:556-628` | `compile_to_business_system()` | 同步生产路径，产出模型B |
| `app/core/async_pipeline.py:532-603` | `compile_to_business_system_async()` | 异步生产路径，产出模型B |
| `app/api/bsc_api.py:124-149` | `compile_prd()` | `POST /bsc/compile` 入口 |
| `app/agents/business_understanding_agent.py:43` | `process_flow` 产出 | 主链路BU字段（LLM驱动） |
| `app/engines/business_understanding.py:63-93` | `parse_documents()` | Studio路径BU（纯正则抽取） |
| `app/engines/business_understanding.py:132-139` | `_extract_processes()` | 正则按动词抽句子，无语义 |
| `app/agents/protocol.py:28-36` | `on_generate`/`on_analyze` | Studio Agent基类（纯本地启发式） |
| `app/agents/sop_agent.py:7-14` | `SLA_BASELINE` | 硬编码SLA表（无LLM） |
| `app/agents/sop_agent.py:48` | `bs.get("processes")` | Studio SOP读取字段 |
| `app/agents/composer.py:44` | `bu.get("process_flow")` | 主链路Composer读取字段 |
| `app/core/pipeline.py` | 全文 | 死代码（零引用） |
| `app/core/compiler.py` | 全文 | 死代码（仅__init__导出 + __main__测试） |
| `app/services/mock_compiler.py` | 全文 | 死代码（仅被compiler引用） |

---

## 附录：四轮分析历程

| 轮次 | 主题 | 产出 |
|------|------|------|
| **SURVEY** | 架构/规模/端点 | 项目全貌 |
| **DEEPDIVE** | 死代码判定 + CORS/报告造假 | 已执行清理（删orchestrator、归档python-backend、冒烟测试通过） |
| **MODELS** | 模型A vs 模型B字段级不兼容 | "补校验"= 适配器工程，非一行代码 |
| **MODELS §4修正** | Studio路径查证 | 错位假设不成立，但暴露双入口底层分歧（LLM vs 正则） |

---

**分析完成** — 四轮深度追踪，所有结论均经引用验证。
