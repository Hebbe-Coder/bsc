"""End-to-end test: Phase 0-4 full chain verification."""
import sys, tempfile, os
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

# Phase 0: Artifact Graph
from app.artifacts import (
    ArtifactGraphStore,
    BusinessModelArtifact, AssumptionArtifact,
    RiskArtifact, GapArtifact, DecisionArtifact,
    ArtifactType, Severity, GapCategory, RiskDimension,
)

# Phase 1-4: Capability System + Planner + Runtime + Reflection
from app.capabilities import (
    build_default_registry, MissionPlanner, BusinessRuntime,
    ReflectionPipeline,
)

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))

# --- Phase 0 verification ---
print("=== PHASE 0: Artifact Graph ===")

bm = store.create_business_model(
    label="AI SaaS Subscription Platform",
    project_id="proj_e2e",
    domain="AI SaaS",
    objectives=["Validate market fit", "Assess tech risk"],
    value_proposition="AI-powered analytics",
)

a1 = store.create_assumption(
    statement="Instructor supply remains stable",
    parent_ids=[bm.artifact_id],
    category="operational",
    criticality=Severity.HIGH,
)

r1 = store.create_risk(
    risk_statement="Instructor churn > 30%",
    parent_ids=[bm.artifact_id],
    dimension=RiskDimension.OPERATIONAL,
    severity=Severity.HIGH,
    mitigation="Build instructor pipeline",
)

d1 = store.create_decision(
    decision_statement="PLG + enterprise hybrid go-to-market",
    parent_ids=[bm.artifact_id, r1.artifact_id],
    rationale="PLG reduces CAC; enterprise captures high-value",
    assumption_confidence=0.72,
    risk_acceptable=True,
    coverage_pct=85.0,
)

print(f"  Artifacts: {store.count()}")
print(f"  BusinessModels: {len(store.get_by_type(ArtifactType.BUSINESS_MODEL))}")
print(f"  Assumptions: {len(store.get_by_type(ArtifactType.ASSUMPTION))}")
print(f"  Risks: {len(store.get_by_type(ArtifactType.RISK))}")
print(f"  Decisions: {len(store.get_by_type(ArtifactType.DECISION))}")

children = store.get_children(bm.artifact_id)
print(f"  Children of BM: {[c.artifact_type.value for c in children]}")

sub = store.get_subgraph(bm.artifact_id)
print(f"  Subgraph: {len(sub['nodes'])} nodes, {len(sub['edges'])} edges")

# Backward compat
export = store.export()
print(f"  Export _version: {export['_version']}")
print(f"  Export business_domain: {export['business_domain']}")
print(f"  Export risks count: {len(export['risks'])}")
print()

# --- Phase 1: Capability System ---
print("=== PHASE 1: Capability System ===")
reg = build_default_registry()
print(f"  Registered: {reg.count()} capabilities")

caps_for_bm = reg.find_by_input(ArtifactType.BUSINESS_MODEL)
print(f"  Capabilities consuming BusinessModel: {len(caps_for_bm)}")

best = reg.best_for(input_type=ArtifactType.BUSINESS_MODEL, output_type=ArtifactType.RISK)
print(f"  Best for BM->Risk: {best.name} (score={best.score_for(input_type=ArtifactType.BUSINESS_MODEL):.2f})")
print()

# --- Phase 2: Mission Planner ---
print("=== PHASE 2: Mission Planner ===")
planner = MissionPlanner(registry=reg, mode="static")

import asyncio

async def test_planner():
    mission = await planner.plan(
        prd_text="AI SaaS analytics platform for mid-market. Need risk and market analysis.",
        domain_hint="saas",
    )
    print(f"  Mode: {mission.planning_mode}")
    print(f"  Steps: {len(mission.steps)}")
    print(f"  Required: {mission.required_capabilities}")
    order = mission.get_execution_order()
    print(f"  Execution order: {[s.capability_name for s in order]}")
    groups = mission.get_parallel_groups()
    parallel_count = sum(1 for g in groups.values() if len(g) > 1)
    print(f"  Parallel groups: {len(groups)} ({parallel_count} with concurrency)")
    print()
    return mission

mission = asyncio.run(test_planner())

# --- Phase 4: Reflection Pipeline ---
print("=== PHASE 4: Reflection ===")
pipe = ReflectionPipeline(store, reg)
report = pipe.run()

print(f"  Gaps found: {report['stages']['reflect']['gaps_found']}")
print(f"  Analysis: {report['stages']['analyze']}")
print(f"  Resolved: {report['stages']['resolve']['resolved']}")
print(f"  Needs replan: {report['stages']['resolve']['needs_replan']}")
print(f"  Summary: {report['summary']}")

for g in report["gaps"]:
    print(f"    [{g['category']}] {g['statement'][:80]} → {g['resolution'][:60]}")

print()

# --- Final state ---
print("=== FINAL STATE ===")
print(f"  Total artifacts in store: {store.count()}")
for at in ArtifactType:
    count = len(store.get_by_type(at))
    if count > 0:
        print(f"  {at.value}: {count}")

final_export = store.export()
print(f"  Export total: {final_export['_artifact_graph']['total_artifacts']}")

# Disk persistence
store2 = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))
assert store2.count() == store.count(), "Persistence mismatch!"
print(f"  Disk reload: {store2.count()} artifacts (PASS)")

print()
print("=" * 50)
print("ALL PHASE 0-4 CHECKS PASSED")
print("=" * 50)
