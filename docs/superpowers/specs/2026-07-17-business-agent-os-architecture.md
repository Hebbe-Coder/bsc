# ADR-010: Business Agent OS — Architecture Freeze

**Status**: FROZEN (2026-07-17)
**Supersedes**: ADR-009 (BSC Pipeline v5)
**Scope**: 从 Business Compiler 到 Business Agent Runtime 的架构升级

---

## 1. 决策：BSC 的三个阶段定位

```
BSC v1-v5:   Business Compiler
             "输入 PRD → 输出 SOP/风险/KPI 报告"
             固定 6 阶段 Pipeline

BSC v6:      Business Reasoning Engine (当前)
             "PRD → 业务推理 → 结构化知识图谱"
             Artifact Graph + Capability System

BSC v7+:     Business Agent OS (本 ADR 目标)
             "企业业务推理操作系统, 基于 Nanobot Agent Kernel"
             Mission Loop + Execution Loop + Reflection Loop
```

---

## 2. 冻结架构

### 2.1 整体分层

```
┌──────────────────────────────────────────────────────────┐
│                     Nanobot                              │
│                 Agent Kernel Layer                        │
│                                                          │
│   Agent Loop  │  Tool Call  │  Memory  │  MCP  │  Session│
└────────────────────────────┬─────────────────────────────┘
                             │
                             │ "Linux Kernel → Android Framework"
                             │
┌────────────────────────────▼─────────────────────────────┐
│              Business Agent Framework                     │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Business Runtime                       │  │
│  │                                                    │  │
│  │  ┌──────────────┐ ┌───────────────┐ ┌───────────┐  │  │
│  │  │ Mission Loop │ │ Execution Loop│ │Reflection │  │  │
│  │  │              │ │               │ │   Loop    │  │  │
│  │  │ plan()       │ │ execute()     │ │ evaluate()│  │  │
│  │  │ replan()     │ │ observe()     │ │ resolve() │  │  │
│  │  └──────┬───────┘ └───────┬───────┘ └─────┬─────┘  │  │
│  │         │                 │               │        │  │
│  │         └────────┬────────┴───────┬───────┘        │  │
│  │                  │                │                │  │
│  └──────────────────┼────────────────┼────────────────┘  │
│                     │                │                   │
│  ┌──────────────────▼────────────────▼────────────────┐  │
│  │            Capability System                        │  │
│  │                                                    │  │
│  │  assumption_reasoning  │  risk_analysis            │  │
│  │  constraint_generation │  market_validation        │  │
│  │  compliance_check      │  kpi_design               │  │
│  │  coverage_analysis     │  decision_support         │  │
│  └──────────────────────────┬─────────────────────────┘  │
│                             │                            │
│  ┌──────────────────────────▼─────────────────────────┐  │
│  │              Artifact Graph (World Model)           │  │
│  │                                                    │  │
│  │  BusinessModel ─┬─ Assumption ─── Evidence         │  │
│  │                 ├─ Risk         ─── Mitigation      │  │
│  │                 ├─ Constraint   ─── Boundary        │  │
│  │                 ├─ Coverage     ─── Matrix          │  │
│  │                 ├─ Gap          ─── Resolution      │  │
│  │                 └─ Decision     ─── Rationale       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2.2 两个 Graph 的明确区分

**Mission Graph**（计划空间 — 我要完成什么）:

```json
{
  "mission": "evaluate_business_model",
  "goals": ["validate_growth", "identify_risk", "assess_feasibility"],
  "required_capabilities": ["assumption_reasoning", "risk_analysis", "constraint_generation"],
  "execution_strategy": {
    "parallel": [["assumption_reasoning"]],
    "sequential": [["risk_analysis"], ["constraint_generation"]],
    "depends_on": { "risk_analysis": ["assumption_reasoning"] }
  }
}
```

**Artifact Graph**（知识空间 — 我知道了什么）:

```
BusinessModel(id=biz-001, domain="在线教育")
  │
  ├── Assumption(id=asm-001, statement="讲师供给持续增长", confidence=0.72)
  │   └── Evidence(id=evd-001, type="industry_report", source="2025教育行业白皮书")
  │
  ├── Risk(id=rsk-001, type="operational", severity="critical")
  │   └── Mitigation(id=mit-001, strategy="多平台讲师签约")
  │
  ├── Constraint(id=con-001, type="regulatory", scope="双减政策")
  │
  ├── Coverage(id=cov-001, matrix={"process": 0.9, "org": 0.7, "system": 0.3, "compliance": 0.5})
  │
  ├── Gap(id=gap-001, type="missing_evidence", severity="critical")
  │   └── Resolution(id=res-001, action="invoke market_validation")
  │
  └── Decision(id=dec-001, choice="A市场进入策略",
       rationale={"assumption_confidence": 0.83, "risk_acceptable": true, "coverage_pct": 92})
```

### 2.3 Capability System（不是 Agent 集合，是能力市场）

```python
Capability(
    name="assumption_reasoning",
    description="从商业模式中提取并评估隐藏假设",
    required_inputs=["BusinessModelArtifact"],
    produces_artifact="AssumptionArtifact",
    executor=AssumptionAgent,           # 实现细节, Planner 不感知
    quality_score=0.82,                 # 运行时评估
    avg_tokens=5000,
    applicable_domains=["education", "retail", "saas"],
)
```

**核心原则（ADR-010 锁定）**:
- Planner 只看到 Capability，不看到 Agent
- Agent 是 Capability 的实现细节
- 未来 Capability 可以有多个 executor（评分选最优）

### 2.4 Business Runtime（三 Loop，不是 Pipeline）

```
BusinessRuntime.run(prd_content):
    │
    ▼
┌───────────────────────────────────────────────┐
│  while mission_active:                        │
│                                               │
│    ┌─── Mission Loop ──────────────────────┐  │
│    │  plan_capabilities()                   │  │
│    │  update_mission_graph()                │  │
│    └──────────────┬────────────────────────┘  │
│                   │                           │
│    ┌──────────────▼────────────────────────┐  │
│    │  Execution Loop                       │  │
│    │  for group in strategy.groups:        │  │
│    │      AgentPool.execute_parallel(group) │  │
│    │  ArtifactGraph.ingest(results)        │  │
│    └──────────────┬────────────────────────┘  │
│                   │                           │
│    ┌──────────────▼────────────────────────┐  │
│    │  Reflection Loop                       │  │
│    │  gaps = GapAnalyzer.evaluate(graph)   │  │
│    │  if gaps.needs_action():              │  │
│    │      GapResolver.resolve(gaps)        │  │
│    │      mission.evolve()                 │  │
│    │  else:                                │  │
│    │      mission_active = False           │  │
│    └───────────────────────────────────────┘  │
│                                               │
│  最多 3 轮 (含初始), 超限 → 标记 unresolved     │
└───────────────────────────────────────────────┘
```

### 2.5 Reflection 三阶段拆分

```
Reflection Loop:
    │
    ▼
┌──────────────────┐
│ Reflection Engine │  "发现了什么缺口?"
│                  │
│ 反事实推理:       │
│ "如果讲师供给     │
│  下降50%,         │
│  结论还成立吗?"   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Gap Analyzer     │  "缺口分类"
│                  │
│ Type A: 缺证据    │  → RequestEvidence
│ Type B: 分析不足  │  → AddCapability
│ Type C: 方案失败  │  → GenerateAlternative
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Gap Resolver     │  "如何解决?"
│                  │
│ A → invoke market_validation │
│ B → add compliance_check     │
│ C → propose alternative model│
└──────────────────┘
```

---

## 3. 三大锁定原则

| # | 原则 | 含义 |
|---|------|------|
| **1** | **Artifact Graph 是唯一业务状态** | 不回归 state dict / business_system dict，所有 Agent 输出写入 Artifact Graph |
| **2** | **Planner 选 Capability，不选 Agent** | Agent 是实现细节，Planner 只声明需要什么能力 |
| **3** | **Business Runtime 必须拥有 Loop** | 三次以内闭环，否则永远只是智能 Pipeline |

---

## 4. 与 Nanobot 的关系

```
Nanobot                 BSC (Business Agent Framework)
───────                 ────────────────────────────────
Agent Kernel            Business Reasoning Layer

Agent Loop       →      Mission Loop
Tool Call/MCP    →      Capability System
Memory           →      Artifact Graph
Conversation     →      Reflection Dialogue
Session Mgmt     →      Mission Lifecycle

类比: Linux Kernel → Android Framework
```

Nanobot 不变，BSC 作为垂直领域 Framework 运行在其上。

---

## 5. 开发阶段（冻结版）

| Phase | 名称 | 内容 | 依赖 |
|-------|------|------|------|
| **0** | Artifact Graph v2 | 新增 6 个 Artifact 类型 + ArtifactGraphStore | 无 |
| **1** | Capability System | AgentPool → Capability 抽象层 | Phase 0 |
| **2** | Mission Planner | LLM 输出 MissionGraph（不是 agent DAG） | Phase 1 |
| **3** | Business Runtime | 三 Loop 执行引擎, LegacyPipeline 保留双轨 | Phase 2 |
| **4** | Reflection + Gap | 三阶段审查 + 三类决策 | Phase 0 (Artifact Graph 是前置) |

### Phase 0 详细：Artifact Graph v2

```
新增 Artifact 类型:

  现有                    新增 (Phase 0)
  ─────                   ──────────────
  BusinessSystem          BusinessModelArtifact
  Objective               AssumptionArtifact
  Risk                    ConstraintArtifact
  Strategy                EvidenceArtifact
  Optimization            CoverageArtifact
                          GapArtifact
                          DecisionArtifact

ArtifactGraphStore:

  add(artifact)           → 写入 + 建立依赖边
  get(id)                 → 单个 Artifact
  get_by_type(type)       → 同类型列表
  get_dependents(id)      → 上游依赖
  get_dependencies(id)    → 下游引用
  export()                → 序列化为 JSON (兼容现有 business_system)
```

---

## 6. 现有代码兼容

| 模块 | 处理方式 |
|------|---------|
| `bsc_pipeline.py` | 保留, 标记 `LEGACY_EXECUTION_MODE` |
| `async_pipeline.py` | 保留, 同上 |
| `compile_to_business_system()` | 不变, 底层逐步切到 Artifact Graph |
| `agent_pool.py` | 保留, Business Runtime 直接复用 |
| `interactive_pipeline.py` | 迁移到 Business Runtime |
| `bsc_api.py` | 新增 `POST /bsc/compile/agent` 端点 |

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| LLM Planner 输出不稳定 | 三级 Fallback (L0 LLM → L1 模板 → L2 完整 DAG) |
| Artifact Graph 过度设计 | 从 6 个核心类型开始, 按需扩展 |
| Reflection 无限循环 | 硬限制 3 轮, 超限标记 unresolved 但继续输出 |
| 与现有 API 兼容 | 双轨: 旧端点不变, 新端点 `/compile/agent` |
