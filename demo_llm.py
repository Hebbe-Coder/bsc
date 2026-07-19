"""LLM-powered full pipeline demo — 真实 DeepSeek 驱动"""
import sys, os, asyncio, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.artifacts import ArtifactGraphStore, BusinessModelArtifact
from app.artifacts import AssumptionArtifact, RiskArtifact, ConstraintArtifact
from app.artifacts import Severity, RiskDimension
from app.capabilities import build_default_registry, BusinessRuntime, ReflectionPipeline
from app.services.llm_adapter import get_llm_adapter, reset_llm_adapter

reset_llm_adapter()
llm = get_llm_adapter()

data_dir = tempfile.mkdtemp(prefix="llm_demo_")
store = ArtifactGraphStore(data_dir=data_dir)
reg = build_default_registry()
runtime = BusinessRuntime(store=store, registry=reg, planner=None, executor_backend="local")
mem = runtime.enable_memory(data_dir)

PRD = """
项目：食链 — 餐饮供应链数字化平台
目标：为中小餐饮企业提供采购、库存、配送一站式数字化方案。
价值主张：集采降本15-30%、AI需求预测、48h冷链配送。
模式：SaaS订阅 + 交易抽佣(GMV 3-5%)。
目标客户：二线城市50-200平米独立餐饮门店。
"""

print("=" * 50)
print("  LLM-Powered Business Agent OS Demo")
print("  Provider: DeepSeek (deepseek-chat)")
print("=" * 50)

async def main():
    t0 = time.perf_counter()

    # ── Step 1: LLM Business Understanding ──
    print("\n[1/4] LLM: Business Understanding...")
    resp = await llm.generate(
        system_prompt="你是商业分析师。分析以下PRD，提取商业模式核心要素。输出JSON。",
        prompt=f"""分析以下商业PRD并输出JSON:
{PRD}

输出格式:
{{
  "domain": "行业",
  "value_proposition": "价值主张",
  "customer_segments": ["客户1"],
  "revenue_model": "收入模式",
  "key_risks": ["风险1"],
  "key_assumptions": ["假设1"]
}}""",
        max_tokens=400,
    )
    print(f"  LLM Response: {resp[:200]}...")

    # ── Step 2: Seed artifacts + Reflection ──
    print("\n[2/4] Reflection: LLM counterfactual analysis...")
    bm = BusinessModelArtifact(
        label="食链", project_id="llm_demo", domain="餐饮数字化",
        value_proposition="集采降本+AI预测+冷链", objectives=["覆盖1000家门店"],
    )
    store.add(bm)
    for stmt, crit in [("冷链供给稳定", Severity.CRITICAL), ("企业接受数字化", Severity.HIGH)]:
        store.add(AssumptionArtifact(
            label=stmt, statement=stmt, criticality=crit, parent_ids=[bm.artifact_id],
        ))
    for risk, dim, sev in [("冷链断裂", RiskDimension.OPERATIONAL, Severity.CRITICAL),
                            ("客户流失", RiskDimension.MARKET, Severity.HIGH)]:
        store.add(RiskArtifact(
            label=risk, risk_statement=risk, dimension=dim, severity=sev,
            parent_ids=[bm.artifact_id],
        ))

    pipe = ReflectionPipeline(store, reg)
    report = pipe.run()
    print(f"  Gaps found: {report['stages']['reflect']['gaps_found']}")
    for g in report["gaps"][:3]:
        print(f"    [{g['severity']}] {g['statement'][:70]}")

    # ── Step 3: LLM Board Analysis ──
    print("\n[3/4] LLM: Multi-Agent Board...")
    from app.capabilities.board import MultiAgentBoard
    board = MultiAgentBoard(store)
    decision = await board.convene(project_id="llm_demo")
    print(f"  Verdict: {decision.final_verdict.upper()}")
    print(f"  Consensus: {decision.consensus}")
    print(f"  Votes: {dict(decision.votes)}")
    if decision.key_conditions:
        print(f"  Top condition: {decision.key_conditions[0][:100]}...")

    # ── Step 4: LLM Decision Synthesis ──
    print("\n[4/4] LLM: Executive decision synthesis...")
    final = await llm.generate(
        system_prompt="你是董事会主席。基于以下分析，做出最终商业决策。输出JSON。",
        prompt=f"""综合以下分析做出决策:

董事会投票: {dict(decision.votes)}
共识: {decision.consensus}
放行条件: {'; '.join(decision.key_conditions[:2])}

输出JSON:
{{
  "final_decision": "go|conditional_go|no_go",
  "executive_summary": "一句话总结",
  "top_priority": "最重要的下一步",
  "risk_appetite": "conservative|moderate|aggressive"
}}""",
        max_tokens=300,
    )
    print(f"  LLM Final: {final[:200]}...")

    elapsed = (time.perf_counter() - t0)
    print(f"\n{'='*50}")
    print(f"  LLM Demo Complete in {elapsed:.1f}s")
    print(f"  Artifacts: {store.count()}")
    print(f"  Board Verdict: {decision.final_verdict}")
    print(f"{'='*50}")

asyncio.run(main())
