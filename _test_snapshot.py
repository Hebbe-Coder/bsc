import sys, tempfile, os
sys.path.insert(0, r"C:\Users\34216\Documents\New project 3\bsc-backend")

from app.artifacts import ArtifactGraphStore, Severity, RiskDimension

tmpdir = tempfile.mkdtemp()
store = ArtifactGraphStore(data_dir=os.path.join(tmpdir, "artifacts"))

# Build initial state
bm = store.create_business_model(label="AI SaaS", project_id="p1", domain="AI SaaS")
a1 = store.create_assumption(statement="Supply stable", parent_ids=[bm.artifact_id])
r1 = store.create_risk(risk_statement="Churn risk", parent_ids=[bm.artifact_id],
                        dimension=RiskDimension.OPERATIONAL, severity=Severity.HIGH,
                        mitigation="Pipeline")

print(f"Initial: {store.count()} artifacts")

# Snapshot 1: after initial build
snap1 = store.snapshot(name="after_initial", tag="v1")
print(f"Snapshot 1: {snap1['snapshot_id']} ({snap1['total_artifacts']} artifacts)")

# Add more artifacts
d1 = store.create_decision(decision_statement="PLG strategy",
                            parent_ids=[bm.artifact_id, r1.artifact_id],
                            rationale="Low CAC", assumption_confidence=0.72)
g1 = store.create_gap(gap_statement="Missing evidence", parent_ids=[a1.artifact_id])

print(f"After additions: {store.count()} artifacts")

# Snapshot 2: after additions
snap2 = store.snapshot(name="after_additions", tag="v2")
print(f"Snapshot 2: {snap2['snapshot_id']} ({snap2['total_artifacts']} artifacts)")

# List snapshots
snaps = store.list_snapshots()
print(f"Snapshots available: {len(snaps)}")
for s in snaps:
    print(f"  {s['name']} ({s['tag']}): {s['total_artifacts']} artifacts")

# Diff snap1 vs snap2
diff = store.diff(snapshot_a=snap1['snapshot_id'], snapshot_b=snap2['snapshot_id'])
print(f"Diff: {diff['summary']}")
print(f"  Added: {[a['label'] for a in diff['added']]}")
print(f"  Removed: {[r['label'] for r in diff['removed']]}")
print(f"  Modified: {len(diff['modified'])}")

# Modify an artifact
r1.mitigation = "Enhanced pipeline + retention bonus"
store.update(r1)

snap3 = store.snapshot(name="after_modification", tag="v3")

diff2 = store.diff(snapshot_a=snap2['snapshot_id'], snapshot_b=snap3['snapshot_id'])
print(f"Diff v2→v3: {diff2['summary']}")
for m in diff2['modified']:
    print(f"  Modified: {m['label']} — {m['changed_fields']}")

# Restore to snapshot 1
count = store.restore_snapshot(snap1['snapshot_id'])
print(f"Restored to snap1: {count} artifacts (expected 3)")

# Verify
print(f"After restore: {store.count()} artifacts")
types = set()
for aid in store.list_all():
    art = store.get(aid)
    if art:
        types.add(art.artifact_type.value)
print(f"Types present: {types}")

# No decisions or gaps after restore
assert store.count() == 3
assert len(store.get_by_type(__import__("app.artifacts.types", fromlist=["ArtifactType"]).ArtifactType.DECISION)) == 0
assert len(store.get_by_type(__import__("app.artifacts.types", fromlist=["ArtifactType"]).ArtifactType.GAP)) == 0

print()
print("=== SNAPSHOT/DIFF/RESTORE ALL PASSED ===")
