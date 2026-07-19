import sys, tempfile, os
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.artifacts import ArtifactGraphStore, Severity
from app.capabilities import (
    build_default_registry, MissionPlanner, BusinessRuntime,
    BusinessMemory, CapabilityExecutor,
)

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))
reg = build_default_registry()
planner = MissionPlanner(registry=reg, mode="static")
runtime = BusinessRuntime(store=store, registry=reg, planner=planner, executor_backend="local")
mem = runtime.enable_memory(os.path.join(tmpdir, "memory"))

store.create_business_model(label="AI SaaS", project_id="p1", domain="AI SaaS")
store.create_assumption(statement="Supply stable", parent_ids=[store.list_all()[0]], criticality=Severity.HIGH)
store.create_risk(risk_statement="Churn risk", parent_ids=[store.list_all()[0]], severity=Severity.HIGH, mitigation="Pipeline")

# Capability memory
mem.record_capability("risk_analysis", True, 1200.0, 2, "local")
mem.record_capability("risk_analysis", False, 2000.0, 0, "local")
mem.record_capability("risk_analysis", True, 800.0, 3, "local")

# Industry memory
mem.record_project("fintech", ["risk_analysis", "compliance"], gaps_found=3)
mem.record_project("fintech", ["risk_analysis", "constraint"], gaps_found=1)

# Run memory
mem.record_run("run_001", domain="fintech", total_artifacts=12, gaps_found=3, duration_ms=5000)

print("=== Capability Memory ===")
stats = mem.capability.get("risk_analysis")
print(f"risk_analysis: {stats['total_runs']} runs, sr={stats['success_rate']:.2f}")

best = mem.capability.best_capabilities(min_runs=1)
print(f"Best: {best}")

print()
print("=== Industry Memory ===")
fintech = mem.industry.get_industry("fintech")
print(f"fintech: {fintech['total_projects']} projects, avg_gaps={fintech['avg_gaps']:.1f}")
print(f"Recommended: {mem.industry.recommended_capabilities('fintech', 3)}")

print()
print("=== Summary ===")
print(mem.summary())

# Executor
executor = CapabilityExecutor(store, backend="local")
print(f"\nExecutor: {type(executor._backend).__name__}")

# LLM Reflection
from app.capabilities.reflection import LLMReflectionEngine, LLMReflectionPipeline
print("LLMReflection: OK")

print()
print("=== ALL P1 CHECKS PASSED ===")
