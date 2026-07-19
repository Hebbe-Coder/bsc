"""
Multi-Agent Board Demo: 5个角色并行分析 + Board Review 综合决策

CEO / CFO / CTO / COO / Compliance 同时分析同一个商业方案,
然后 Board Review Agent 综合投票, 输出最终裁决。
"""
import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.artifacts import ArtifactGraphStore, BusinessModelArtifact
from app.artifacts import AssumptionArtifact, RiskArtifact, Severity, RiskDimension
from app.capabilities import MultiAgentBoard

# ── Setup: 复用食链项目的 Artifact Graph ──
data_dir = tempfile.mkdtemp(prefix="board_demo_")
store = ArtifactGraphStore(data_dir=data_dir)

bm = BusinessModelArtifact(
    label="食链 - 餐饮供应链数字化平台",
    project_id="shilian_board",
    domain="餐饮数字化",
    value_proposition="集采降本15-30% + AI预测减少浪费20% + 48h冷链配送",
    objectives=["3城市6个月1000家门店", "成本降低>15%", "留存率>70%"],
)
store.add(bm)

assumptions_data = [
    ("中小餐饮企业愿意接受数字化改造", "market", Severity.HIGH),
    ("冷链物流合作伙伴供给稳定", "operational", Severity.CRITICAL),
    ("食材价格不会剧烈波动", "financial", Severity.MEDIUM),
]
for stmt, cat, crit in assumptions_data:
    store.add(AssumptionArtifact(
        label=stmt[:40], statement=stmt, category=cat,
        criticality=crit, parent_ids=[bm.artifact_id],
    ))

risks_data = [
    ("冷链物流断裂", RiskDimension.OPERATIONAL, Severity.CRITICAL, "多供应商策略"),
    ("客户流失>30%", RiskDimension.MARKET, Severity.HIGH, "客户成功团队+预警"),
    ("食品安全事故", RiskDimension.COMPLIANCE, Severity.CRITICAL, "全链路溯源+保险"),
    ("美团/饿了么降维打击", RiskDimension.MARKET, Severity.HIGH, "差异化非外卖场景"),
]
for risk, dim, sev, mit in risks_data:
    store.add(RiskArtifact(
        label=risk, risk_statement=risk, dimension=dim,
        severity=sev, mitigation=mit, parent_ids=[bm.artifact_id],
    ))

print(f"Artifacts: {store.count()} (1 BM + {len(assumptions_data)} Assumptions + {len(risks_data)} Risks)")
print()

# ── Board Convene ──
async def main():
    board = MultiAgentBoard(store)
    decision = await board.convene(project_id="shilian_board")

    print("=" * 60)
    print("  Multi-Agent Board — 董事会裁决")
    print("=" * 60)
    print(f"  项目: 食链 - 餐饮供应链数字化平台")
    print(f"  参与角色: {len(decision.votes)} 个")
    print()

    # Individual votes
    print("  ── 各角色投票 ──")
    for role_id, verdict in decision.votes.items():
        icon = {"go": "[GO]    ", "conditional_go": "[COND]  ", "no_go": "[NO-GO] "}.get(verdict, "[?]     ")
        print(f"    {icon} {role_id.upper():12s} ({verdict})")

    print()
    print("  ── 综合决策 ──")
    print(f"    加权得分:    {decision.weighted_score:.2f}")
    print(f"    共识程度:    {decision.consensus}")
    print(f"    最终裁决:    {decision.final_verdict.upper()}")
    print(f"    执行摘要:    {decision.executive_summary}")

    if decision.minority_report:
        print(f"    少数派报告:  {decision.minority_report}")

    if decision.aligned_on:
        print()
        print("  ── 一致同意 ──")
        for a in decision.aligned_on:
            print(f"    [OK] {a}")

    if decision.conflicts:
        print()
        print("  ── 冲突/红线 ──")
        for c in decision.conflicts:
            print(f"    [!] [{c['role']}] {c['issue']}: {c.get('detail', '')}")

    if decision.key_conditions:
        print()
        print("  ── 放行条件 ──")
        for cond in decision.key_conditions:
            print(f"    -> {cond}")

    # Board decision stored as artifact
    board_art = store.get_by_type(__import__('app.artifacts.types', fromlist=['ArtifactType']).ArtifactType.DECISION)
    if board_art:
        d = board_art[0]
        if isinstance(d, __import__('app.artifacts.types', fromlist=['DecisionArtifact']).DecisionArtifact):
            print(f"\n  Board Decision Artifact: {d.artifact_id}")
            print(f"  Decision: {d.decision_statement[:80]}")

    print()
    print("=" * 60)
    print("  Multi-Agent Board Demo 完成")
    print("=" * 60)

asyncio.run(main())
