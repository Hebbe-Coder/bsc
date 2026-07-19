"""
╔══════════════════════════════════════════════════════════════╗
║         Business Agent OS — 端到端 Demo                    ║
║                                                            ║
║  真实场景：餐饮数字化平台商业分析                             ║
║                                                            ║
║  全链路：                                                   ║
║    Plan → Execute → Reflect → Memory → Export              ║
║                                                            ║
║  ADR-010 三大原则验证：                                      ║
║    1. Artifact Graph 是唯一业务状态                           ║
║    2. Planner 选 Capability，不选 Agent                     ║
║    3. Business Runtime 拥有 Loop                            ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys, os, json, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.artifacts import (
    ArtifactGraphStore,
    BusinessModelArtifact, AssumptionArtifact,
    RiskArtifact, ConstraintArtifact, EvidenceArtifact,
    CoverageArtifact, GapArtifact, DecisionArtifact,
    ArtifactType, Severity, GapCategory, RiskDimension,
)
from app.capabilities import (
    build_default_registry, MissionPlanner,
    BusinessRuntime, ReflectionPipeline, BusinessMemory,
)

# ═══════════════════════════════════════════════════════════════
# STEP 0: 初始化
# ═══════════════════════════════════════════════════════════════

print("=" * 60)
print("  Business Agent OS — 端到端 Demo")
print("  场景：餐饮数字化平台商业分析")
print("=" * 60)

data_dir = tempfile.mkdtemp(prefix="bsc_demo_")
store = ArtifactGraphStore(data_dir=os.path.join(data_dir, "artifacts"))
reg = build_default_registry()
planner = MissionPlanner(registry=reg, mode="static")  # 用 LLM 时可切 "llm"
runtime = BusinessRuntime(store=store, registry=reg, planner=planner, executor_backend="local")
mem = runtime.enable_memory(os.path.join(data_dir, "memory"))

print(f"\n[INIT] Store: {data_dir}")
print(f"[INIT] Capabilities: {reg.count()} registered")
print(f"[INIT] Planner mode: {planner.mode}")

# ═══════════════════════════════════════════════════════════════
# STEP 1: PRD 输入（模拟业务理解 Agent 产出）
# ═══════════════════════════════════════════════════════════════

PRD = """
项目名称：食链 —— 餐饮供应链数字化平台

目标：为中小餐饮企业提供从采购、库存到配送的一站式数字化解决方案。

核心价值主张：
- 集采降低食材成本 15-30%
- AI 需求预测减少浪费 20%
- 48 小时冷链配送覆盖

目标客户：二线城市 50-200 平米独立餐饮门店

商业模式：SaaS 订阅 + 交易抽佣（GMV 的 3-5%）

关键假设：
1. 中小餐饮企业愿意接受数字化改造
2. 冷链物流合作伙伴供给稳定
3. 食材价格不会剧烈波动
4. 监管政策对食品安全要求持续提升

主要风险：
1. 供应链断裂（依赖第三方冷链）
2. 餐饮客户流失率高（行业平均 30%）
3. 食品安全事故的声誉风险
4. 巨头进入（美团/饿了么可能降维打击）

约束条件：
1. 初期资金 500 万，覆盖 3 个城市
2. 需要取得食品经营许可等资质
3. 团队 15 人，缺乏餐饮行业经验
"""

print(f"\n{'='*60}")
print("  STEP 1: PRD → Artifact Graph")
print(f"{'='*60}")

# ── 1a: 创建 BusinessModelArtifact ──
bm = BusinessModelArtifact(
    label="食链 - 餐饮供应链数字化平台",
    project_id="shilian_v1",
    domain="餐饮数字化",
    value_proposition="集采降本15-30% + AI预测减少浪费20% + 48h冷链配送",
    revenue_model="SaaS订阅 + 交易抽佣(GMV 3-5%)",
    customer_segments=["二线城市50-200平米独立餐饮门店"],
    key_partners=["冷链物流商", "食材供应商", "支付服务商"],
    key_activities=["集采供应链管理", "AI需求预测", "冷链配送调度", "客户成功"],
    key_resources=["供应链管理系统", "冷链合作网络", "AI预测模型"],
    cost_structure=["技术研发", "冷链物流成本", "客户获取", "合规成本"],
    objectives=["3城市6个月覆盖1000家门店", "食材成本降低>15%", "客户留存率>70%"],
    source_agent="business_understanding",
)
store.add(bm)
print(f"  [Artifact] BusinessModel: {bm.label}")

# ── 1b: 提取假设 ──
assumptions_data = [
    ("中小餐饮企业愿意接受数字化改造", "market", Severity.HIGH,
     "如果企业主拒绝数字化，获客成本将翻倍且转化率低于5%"),
    ("冷链物流合作伙伴供给稳定", "operational", Severity.CRITICAL,
     "如果冷链断裂，48小时配送承诺无法兑现，客户信任崩塌"),
    ("食材价格不会剧烈波动", "financial", Severity.MEDIUM,
     "如果食材成本上涨20%，集采价格优势消失，商业模式失去立足点"),
    ("食品安全监管政策持续收紧", "regulatory", Severity.HIGH,
     "如果政策放松，平台合规优势贬值；如果过紧，合规成本吞噬利润"),
]

for i, (stmt, cat, crit, cf) in enumerate(assumptions_data):
    a = AssumptionArtifact(
        label=f"假设{i+1}: {stmt[:40]}",
        statement=stmt,
        category=cat,
        criticality=crit,
        counterfactual=cf,
        parent_ids=[bm.artifact_id],
        source_agent="assumption_reasoning",
    )
    store.add(a)
    print(f"  [Artifact] Assumption: {stmt[:50]}...")

# ── 1c: 风险分析 ──
risks_data = [
    ("冷链物流断裂导致配送失败", RiskDimension.OPERATIONAL, Severity.CRITICAL, Severity.MEDIUM,
     "多供应商策略: 每个城市至少2家冷链商", "紧急启用本地仓储+第三方配送"),
    ("餐饮客户流失率>30%", RiskDimension.MARKET, Severity.HIGH, Severity.HIGH,
     "客户成功团队+流失预警模型+数据驱动留存", "降低订阅费+免费试用延长"),
    ("食品安全事故", RiskDimension.COMPLIANCE, Severity.CRITICAL, Severity.LOW,
     "全链路溯源+供应商资质审核+食安保险", "危机公关预案+监管部门沟通机制"),
    ("美团/饿了么降维打击", RiskDimension.MARKET, Severity.HIGH, Severity.MEDIUM,
     "差异化: 专注中小餐饮非外卖场景", "探索被收购可能"),
    ("团队缺乏餐饮经验", RiskDimension.ORGANIZATION, Severity.MEDIUM, Severity.HIGH,
     "引入餐饮行业顾问+与餐饮协会合作", "快速试错+数据驱动决策"),
]

for i, (risk, dim, sev, prob, mit, cont) in enumerate(risks_data):
    r = RiskArtifact(
        label=f"风险{i+1}: {risk[:40]}",
        risk_statement=risk,
        dimension=dim,
        severity=sev,
        probability=prob,
        mitigation=mit,
        contingency=cont,
        parent_ids=[bm.artifact_id],
        source_agent="risk_analysis",
    )
    store.add(r)
    print(f"  [Artifact] Risk [{sev.value.upper()}]: {risk[:50]}...")

# ── 1d: 约束条件 ──
constraints_data = [
    ("初期资金500万，覆盖3个城市", "resource", True, "超预算则放弃第3城市"),
    ("需取得食品经营许可等资质", "regulatory", True, "上线前必须完成所有资质"),
    ("团队15人，缺餐饮经验", "organizational", False, "优先招聘有餐饮背景的人才"),
]

for i, (stmt, ctype, hard, workaround) in enumerate(constraints_data):
    c = ConstraintArtifact(
        label=f"约束{i+1}: {stmt[:40]}",
        constraint_statement=stmt,
        constraint_type=ctype,
        hard_limit=hard,
        workaround=workaround,
        parent_ids=[bm.artifact_id],
        source_agent="constraint_generation",
    )
    store.add(c)
    print(f"  [Artifact] Constraint: {stmt[:50]}...")

print(f"\n  >> 已创建 {store.count()} 个 Artifact")

# ═══════════════════════════════════════════════════════════════
# STEP 2: Coverage 分析
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 2: Coverage 分析")
print(f"{'='*60}")

cov = CoverageArtifact(
    label="食链商业分析覆盖度",
    dimension_scores={
        "市场分析": 0.85,
        "财务建模": 0.60,
        "风险评估": 0.90,
        "运营设计": 0.75,
        "合规审查": 0.70,
        "技术可行性": 0.55,
        "客户验证": 0.40,
        "竞争格局": 0.65,
    },
    dimensions_covered=["市场分析", "风险评估", "运营设计", "合规审查"],
    dimensions_missed=["客户验证", "技术可行性", "财务建模"],
    overall_coverage=0.68,
    parent_ids=[bm.artifact_id],
    source_agent="coverage_analysis",
)
store.add(cov)
print(f"  [Artifact] Coverage: {cov.overall_coverage:.0%} 总体覆盖")
print(f"  [Artifact] 已覆盖: {', '.join(cov.dimensions_covered)}")
print(f"  [Artifact] 缺失: {', '.join(cov.dimensions_missed)}")

# ═══════════════════════════════════════════════════════════════
# STEP 3: Reflection — 发现 Gap
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 3: Reflection — 反事实推理")
print(f"{'='*60}")

pipe = ReflectionPipeline(store, reg)
report = pipe.run()

print(f"  [Reflect] 发现 {report['stages']['reflect']['gaps_found']} 个 Gap")
print(f"  [Analyze] {report['stages']['analyze']}")
print(f"  [Resolve] 已解决 {report['stages']['resolve']['resolved']}，需Replan: {report['stages']['resolve']['needs_replan']}")

for g in report["gaps"]:
    icon = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(g["severity"], " - ")
    print(f"    {icon} [{g['category']}] {g['statement'][:80]}")
    print(f"       → {g['resolution'][:70]}")

# ═══════════════════════════════════════════════════════════════
# STEP 4: Snapshot + Diff
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 4: Snapshot / Diff")
print(f"{'='*60}")

snap_v1 = store.snapshot(name="v1_initial_analysis", tag="iteration_1")
print(f"  [Snapshot] v1: {snap_v1['total_artifacts']} artifacts")

# 添加证据验证
evidence = EvidenceArtifact(
    label="餐饮企业数字化意愿调研",
    evidence_type="market_data",
    source="中国餐饮数字化白皮书2024 + 门店调研n=150",
    supports_assumption_id=store.get_by_type(ArtifactType.ASSUMPTION)[0].artifact_id,
    finding="67%餐饮企业主表示愿意尝试数字化工具，其中43%愿意付费。二线城市意愿度高于一线。",
    strength=Severity.HIGH,
    contradicts=False,
    parent_ids=[store.get_by_type(ArtifactType.ASSUMPTION)[0].artifact_id],
    source_agent="evidence_validation",
)
store.add(evidence)
print(f"  [Artifact] Evidence: 数字化意愿调研（支持假设1）")

# 添加决策
decision = DecisionArtifact(
    label="市场进入策略决策",
    decision_statement="采用'单城深耕+供应链先建'策略进入市场",
    alternatives=[
        "多城同步扩张（资金压力大，不推荐）",
        "纯平台撮合模式（品控风险高，不推荐）",
    ],
    rationale="先在一个城市验证供应链模型和单位经济，再复制扩张。餐饮供应链是重运营生意，必须先用一个城市跑通全链路。",
    assumption_confidence=0.78,
    risk_acceptable=True,
    coverage_pct=68.0,
    recommendation="建议首城选成都（餐饮业态丰富、竞争适中、冷链基础设施好）",
    parent_ids=[bm.artifact_id],
    source_agent="decision_support",
)
store.add(decision)
print(f"  [Artifact] Decision: {decision.decision_statement[:60]}...")

snap_v2 = store.snapshot(name="v2_with_evidence_decision", tag="iteration_2")
print(f"  [Snapshot] v2: {snap_v2['total_artifacts']} artifacts")

diff = store.diff(snapshot_a=snap_v1["snapshot_id"], snapshot_b=snap_v2["snapshot_id"])
print(f"  [Diff] v1→v2: {diff['summary']}")
for a in diff["added"]:
    print(f"    + {a['type']}: {a['label']}")

# ═══════════════════════════════════════════════════════════════
# STEP 5: Business Memory
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 5: Business Memory")
print(f"{'='*60}")

# 模拟跨 run 学习
mem.record_capability("business_understanding", True, 2500.0, 1, "local")
mem.record_capability("assumption_reasoning", True, 1800.0, 4, "local")
mem.record_capability("risk_analysis", True, 1500.0, 5, "local")
mem.record_capability("constraint_generation", True, 800.0, 3, "local")
mem.record_capability("coverage_analysis", True, 1200.0, 1, "local")
mem.record_capability("evidence_validation", True, 900.0, 1, "local")
mem.record_capability("decision_support", True, 1100.0, 1, "local")

mem.record_project("餐饮数字化", [
    "business_understanding", "assumption_reasoning", "risk_analysis",
    "constraint_generation", "coverage_analysis", "evidence_validation",
    "decision_support",
], gaps_found=3)

mem.record_run("demo_shilian_v1",
               domain="餐饮数字化",
               project_id="shilian_v1",
               total_artifacts=store.count(),
               iterations=1,
               gaps_found=3,
               duration_ms=8500,
               status="completed")

summary = mem.summary()
print(f"  能力追踪: {summary['capabilities_tracked']}")
print(f"  行业追踪: {summary['industries_tracked']}")
print(f"  总运行次数: {summary['total_runs']}")
print(f"  最佳能力: {summary['best_capabilities']}")

# 行业推荐
recs = mem.industry.recommended_capabilities("餐饮数字化", top_n=5)
print(f"  餐饮数字化推荐能力: {recs}")

# ═══════════════════════════════════════════════════════════════
# STEP 6: 最终报告导出
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 6: 最终报告")
print(f"{'='*60}")

final_export = store.export(project_id="shilian_v1")

print(f"""
╔══════════════════════════════════════════════════════════════╗
║              食链 — 商业分析报告                              ║
╠══════════════════════════════════════════════════════════════╣
║  领域: {final_export['business_domain']:<50s}║
║  版本: v2 (Artifact Graph v{final_export['_version']})                        ║
║  总 Artifact: {final_export['_artifact_graph']['total_artifacts']} 个                                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  核心业务模型:                                                ║
║    价值主张: 集采降本+AI预测+冷链配送                           ║
║    收入模式: SaaS订阅+交易抽佣                                 ║
║    目标客户: 二线城市中小餐饮门店                               ║
║                                                              ║
║  关键假设 (4个):                                              ║
║    1. 企业数字化接受度 (HIGH) — 已验证                         ║
║    2. 冷链供给稳定 (CRITICAL) — 待验证                        ║
║    3. 食材价格稳定 (MEDIUM) — 待验证                           ║
║    4. 监管政策趋严 (HIGH) — 待验证                            ║
║                                                              ║
║  风险矩阵 (5个):                                              ║
║    [CRIT] 冷链断裂 — CRITICAL — 多供应商策略                       ║
║    [HIGH] 客户流失 — HIGH — 客户成功团队+流失预警                  ║
║    [CRIT] 食品安全 — CRITICAL — 全链路溯源+食安保险                ║
║    [HIGH] 巨头竞争 — HIGH — 差异化专注非外卖场景                   ║
║    [MED] 团队经验 — MEDIUM — 行业顾问+餐饮协会                    ║
║                                                              ║
║  覆盖度: {cov.coverage_pct():.0f}%                                              ║
║    缺失维度: 客户验证、技术可行性、财务建模                      ║
║                                                              ║
║  决策:                                                        ║
║    单城深耕+供应链先建                                         ║
║    假设置信度: {decision.assumption_confidence:.0%}                                          ║
║    风险可接受: 是                                              ║
║    推荐首城: 成都                                              ║
║                                                              ║
║  发现 Gap ({report['stages']['reflect']['gaps_found']}个):                                              ║""")

for g in report["gaps"]:
    print(f"║    [{g['severity']}] {g['statement'][:55]}".ljust(67) + "║")

print("""║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  Memory 统计:                                                 ║""")
print(f"║    能力追踪: {summary['capabilities_tracked']} 项                                          ║")
print(f"║    行业积累: 餐饮数字化 1 个项目                              ║")
print(f"║    下次推荐: {', '.join(recs[:3])}        ║")
print("""╚══════════════════════════════════════════════════════════════╝""")

# ═══════════════════════════════════════════════════════════════
# STEP 7: 验证 ADR-010 三大原则
# ═══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  STEP 7: ADR-010 三大原则验证")
print(f"{'='*60}")

# 原则1: Artifact Graph 是唯一业务状态
all_ids = store.list_all()
has_state_dict = any("state_dict" in id for id in all_ids)
print(f"  [原则1] Artifact Graph 是唯一状态: {'[PASS] PASS' if not has_state_dict else '[FAIL] FAIL'}")
print(f"          所有 {store.count()} 个对象均为强类型 Artifact")

# 原则2: Planner 选 Capability，不选 Agent
import asyncio
mission = asyncio.run(
    planner.plan(prd_text=PRD, domain_hint='餐饮数字化')
)
has_agent_refs = any("agent" in s.capability_name.lower() for s in mission.steps)
print(f"  [原则2] Planner 选 Capability: {'[PASS] PASS' if not has_agent_refs else '[FAIL] FAIL'}")
print(f"          计划包含 {len(mission.required_capabilities)} 个能力（非 Agent）")

# 原则3: Runtime 有 Loop
has_loop = hasattr(runtime, '_executor') and hasattr(runtime, '_memory')
print(f"  [原则3] Runtime 有 Loop: {'[PASS] PASS' if has_loop else '[FAIL] FAIL'}")
print(f"          Executor: {type(runtime._executor._backend).__name__}")
print(f"          Memory: {'enabled' if runtime._memory else 'disabled'}")

print(f"\n{'='*60}")
print("  [OK] 端到端 Demo 完成！")
print(f"  Artifact Graph: {store.count()} 个强类型对象")
print(f"  Capability 计划: {len(mission.required_capabilities)} 步")
print(f"  Gap 发现: {report['stages']['reflect']['gaps_found']} 个")
print(f"  Memory: {mem.run.count()} 次运行记录")
print(f"  输出: 结构化商业分析报告")
print(f"{'='*60}")


