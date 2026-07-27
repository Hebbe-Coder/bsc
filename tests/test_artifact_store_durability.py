import json

from app.artifacts import ArtifactGraphStore


def test_independently_opened_stores_merge_index_writes_without_losing_artifacts(tmp_path):
    """API and worker stores may open the same ledger before either writes."""
    root = tmp_path / "shared-ledger"
    api_store = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")
    worker_store = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")

    api_artifact = api_store.create_business_model("API write", project_id="project-a", domain="retail")
    worker_artifact = worker_store.create_business_model("Worker write", project_id="project-a", domain="retail")

    reopened = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")
    assert {api_artifact.artifact_id, worker_artifact.artifact_id} <= set(reopened.list_all())
    assert json.loads((root / "_index.json").read_text(encoding="utf-8"))["total"] == 2
    assert not list(root.glob("._index.json.*.tmp"))


def test_snapshot_restore_rebuilds_an_atomic_index_before_later_writes(tmp_path):
    root = tmp_path / "shared-ledger"
    restore_store = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")
    saved = restore_store.create_business_model("Saved state", project_id="project-a", domain="retail")
    snapshot = restore_store.snapshot("before-change")
    restore_store.create_business_model("Discarded state", project_id="project-a", domain="retail")

    # This store intentionally retains the old in-memory index, as a worker
    # does while the API restores a governed Mission revision.
    worker_store = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")
    assert restore_store.restore_snapshot(snapshot["snapshot_id"]) == 1
    worker_artifact = worker_store.create_business_model("Worker write", project_id="project-a", domain="retail")

    reopened = ArtifactGraphStore(str(root), project_id="project-a", session_id="dbos")
    assert set(reopened.list_all()) == {saved.artifact_id, worker_artifact.artifact_id}
    assert json.loads((root / "_index.json").read_text(encoding="utf-8"))["total"] == 2
