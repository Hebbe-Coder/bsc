import sys, asyncio, tempfile, os
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.artifacts import ArtifactGraphStore
from app.capabilities import build_default_registry, LLMReflectionPipeline

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))
reg = build_default_registry()

# Seed test data (same as before)
store.create_business_model(
    label="AI SaaS Subscription Platform",
    project_id="p1", domain="AI SaaS",
    objectives=["Validate market fit"],
    value_proposition="AI analytics for mid-market",
)

store.create_assumption(
    statement="Instructor supply remains stable",
    parent_ids=[store.list_all()[0]],
    criticality="high",
)

store.create_risk(
    risk_statement="Instructor churn > 30%",
    parent_ids=[store.list_all()[0]],
    dimension="operational",
    severity="high",
    mitigation="Build pipeline",
)

store.create_decision(
    decision_statement="PLG + enterprise hybrid",
    parent_ids=[store.list_all()[0]],
    rationale="PLG reduces CAC",
    assumption_confidence=0.72,
)

async def test():
    # Test 1: Rule-based (prefer_llm=False)
    pipe = LLMReflectionPipeline(store, reg)
    report = await pipe.run(prefer_llm=False)
    print(f"[Rule] Engine: {report['engine']}, Gaps: {report['stages']['reflect']['gaps_found']}")
    print(f"[Rule] Summary: {report['summary']}")

    # Clear gaps from store for clean second test
    for aid in list(store.list_all()):
        art = store.get(aid)
        if art and art.artifact_type.value == "gap":
            store.delete(aid)

    # Test 2: LLM preferred (will fall back since no LLM configured)
    report2 = await pipe.run(prefer_llm=True)
    print(f"[LLM-fallback] Engine: {report2['engine']}, Gaps: {report2['stages']['reflect']['gaps_found']}")
    print(f"[LLM-fallback] Summary: {report2['summary']}")

    print()
    print("=== LLM REFLECTION TEST PASSED ===")

asyncio.run(test())
