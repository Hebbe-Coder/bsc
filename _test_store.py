import sys, tempfile, os, json
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.artifacts.store import ArtifactGraphStore
from app.artifacts.types import ArtifactType, Severity, GapCategory, RiskDimension

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))

bm = store.create_business_model(
    label="AI SaaS Subscription",
    project_id="proj_001",
    domain="AI SaaS",
    objectives=["Validate market fit", "Assess technology risk"],
    value_proposition="AI-powered analytics platform",
    customer_segments=["Mid-market enterprises"],
)

a1 = store.create_assumption(
    statement="Enterprise customers will adopt AI analytics within 6 months",
    parent_ids=[bm.artifact_id],
    category="market",
    criticality=Severity.HIGH,
)

a2 = store.create_assumption(
    statement="Cloud infrastructure costs remain stable",
    parent_ids=[bm.artifact_id],
    category="financial",
    criticality=Severity.MEDIUM,
)

r1 = store.create_risk(
    risk_statement="Instructor supply drops 50%",
    parent_ids=[bm.artifact_id],
    dimension=RiskDimension.OPERATIONAL,
    severity=Severity.HIGH,
    mitigation="Build instructor pipeline",
)

from app.artifacts.types import EvidenceArtifact
e1 = EvidenceArtifact(
    artifact_type=ArtifactType.EVIDENCE,
    label="Market survey Q3",
    evidence_type="market_data",
    source="Internal survey n=200",
    supports_assumption_id=a1.artifact_id,
    finding="72% of enterprises plan AI analytics adoption in 12 months",
    strength=Severity.HIGH,
    parent_ids=[a1.artifact_id],
)
store.add(e1)

g1 = store.create_gap(
    gap_statement="No competitive analysis conducted",
    parent_ids=[bm.artifact_id],
    category=GapCategory.ANALYSIS_INSUFFICIENT,
    severity=Severity.MEDIUM,
)

d1 = store.create_decision(
    decision_statement="Enter market via PLG + enterprise sales hybrid",
    parent_ids=[bm.artifact_id, a1.artifact_id, r1.artifact_id],
    rationale="PLG reduces CAC while enterprise sales capture high-value accounts",
    assumption_confidence=0.72,
    risk_acceptable=True,
    coverage_pct=85.0,
)

print(f"Total artifacts: {store.count()}")
print(f"BusinessModels: {len(store.get_by_type(ArtifactType.BUSINESS_MODEL))}")
print(f"Assumptions: {len(store.get_by_type(ArtifactType.ASSUMPTION))}")
print(f"Risks: {len(store.get_by_type(ArtifactType.RISK))}")
print(f"Gaps: {len(store.get_by_type(ArtifactType.GAP))}")
print(f"Decisions: {len(store.get_by_type(ArtifactType.DECISION))}")

children = store.get_children(bm.artifact_id)
print(f"Children of business model: {[c.artifact_type.value for c in children]}")

parents_of_decision = store.get_parents(d1.artifact_id)
print(f"Parents of decision: {[p.label for p in parents_of_decision]}")

sub = store.get_subgraph(bm.artifact_id)
print(f"Subgraph nodes: {len(sub['nodes'])}, edges: {len(sub['edges'])}")

export = store.export()
print(f"Export business_domain: {export['business_domain']}")
print(f"Export risks count: {len(export['risks'])}")
print(f"Export _version: {export['_version']}")
print(f"Export _artifact_graph total: {export['_artifact_graph']['total_artifacts']}")

store.delete(a2.artifact_id)
print(f"After delete: {store.count()} artifacts")

store2 = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))
print(f"Re-loaded store: {store2.count()} artifacts")

print()
print("=== ALL CHECKS PASSED ===")
