import json

import pytest

from app.artifacts import ArtifactGraphStore
import app.artifacts.store as artifact_store_module


def test_atomic_write_retries_transient_replace_lock(tmp_path, monkeypatch):
    """A brief Windows file lock must not abort a governed ledger update."""
    target = tmp_path / "artifact.json"
    original_replace = artifact_store_module.os.replace
    attempts = 0

    def transiently_locked(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(13, "access denied", str(destination))
        return original_replace(source, destination)

    monkeypatch.setattr(artifact_store_module.os, "replace", transiently_locked)

    ArtifactGraphStore._atomic_write_text(target, '{"status":"durable"}')

    assert attempts == 3
    assert target.read_text(encoding="utf-8") == '{"status":"durable"}'
    assert not list(tmp_path.glob(".artifact.json.*.tmp"))


def test_atomic_write_preserves_persistent_replace_failure(tmp_path, monkeypatch):
    """Retry must not turn a persistent lock into a false durability claim."""
    target = tmp_path / "artifact.json"
    attempts = 0

    def permanently_locked(source, destination):
        nonlocal attempts
        attempts += 1
        raise PermissionError(13, "access denied", str(destination))

    monkeypatch.setattr(artifact_store_module.os, "replace", permanently_locked)

    with pytest.raises(PermissionError):
        ArtifactGraphStore._atomic_write_text(target, '{"status":"blocked"}')

    assert attempts == ArtifactGraphStore.ATOMIC_WRITE_REPLACE_ATTEMPTS
    assert not target.exists()
    assert not list(tmp_path.glob(".artifact.json.*.tmp"))


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
