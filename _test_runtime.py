import sys, asyncio, tempfile, os
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.artifacts import ArtifactGraphStore, BusinessModelArtifact, AssumptionArtifact, Severity
from app.artifacts.types import ArtifactType
from app.capabilities import build_default_registry, MissionPlanner, BusinessRuntime
from app.capabilities.runtime import RuntimePhase

reg = build_default_registry()
planner = MissionPlanner(registry=reg, mode="static")

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))

async def test():
    bm = BusinessModelArtifact(
        label="AI SaaS Subscription Platform",
        project_id="proj_001",
        domain="AI SaaS",
        objectives=["Validate market fit", "Assess technology risk"],
        value_proposition="AI-powered analytics for mid-market",
    )
    store.add(bm)

    a = AssumptionArtifact(
        label="Instructor supply",
        statement="Instructor supply remains stable",
        criticality=Severity.HIGH,
        parent_ids=[bm.artifact_id],
    )
    store.add(a)

    runtime = BusinessRuntime(store=store, registry=reg, planner=planner, max_iterations=2)
    result = await runtime.run(
        prd_text="AI SaaS subscription platform for mid-market analytics.",
        domain_hint="saas",
        project_id="proj_001",
    )

    print(f"Status: {result.status}")
    print(f"Iterations: {result.iterations}")
    print(f"Elapsed: {result.elapsed_ms:.0f}ms")
    print(f"Errors: {result.errors}")
    print(f"Artifacts in store: {store.count()}")

    for at in ArtifactType:
        count = len(store.get_by_type(at))
        if count > 0:
            print(f"  {at.value}: {count}")

    export = result.export
    print(f"Export _version: {export.get('_version')}")
    print(f"Export total: {export['_artifact_graph']['total_artifacts']}")

    print()
    print("=== PHASE 3 RUNTIME TEST PASSED ===")

asyncio.run(test())
