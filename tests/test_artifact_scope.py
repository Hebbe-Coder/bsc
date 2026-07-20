import pytest

from app.artifacts import ArtifactGraphStore


def _scoped_store(tmp_path, tenant_id: str, session_id: str) -> ArtifactGraphStore:
    return ArtifactGraphStore(
        str(tmp_path / "shared-directory"),
        tenant_id=tenant_id,
        project_id="project-a",
        session_id=session_id,
    )


def test_artifact_store_hides_cross_tenant_and_cross_session_records(tmp_path):
    owner = _scoped_store(tmp_path, "tenant-a", "session-a")
    artifact = owner.create_business_model(
        label="Tenant A model",
        project_id="project-a",
        domain="retail",
    )

    other_tenant = _scoped_store(tmp_path, "tenant-b", "session-a")
    other_session = _scoped_store(tmp_path, "tenant-a", "session-b")

    for store in (other_tenant, other_session):
        assert store.get(artifact.artifact_id) is None
        assert store.list_all() == []
        assert store.count() == 0
        assert store.get_by_project("project-a") == []
        assert store.export("project-a")["_artifact_graph"]["total_artifacts"] == 0


def test_artifact_store_rejects_cross_scope_writes_and_exports(tmp_path):
    store = _scoped_store(tmp_path, "tenant-a", "session-a")

    with pytest.raises(ValueError, match="outside this store scope"):
        store.create_business_model(
            label="Wrong project",
            project_id="project-b",
        )

    store.create_business_model(label="Scoped model", project_id="project-a")
    with pytest.raises(ValueError, match="outside this store scope"):
        store.export("project-b")


def test_snapshots_are_scoped_and_restore_keeps_scope_metadata(tmp_path):
    owner = _scoped_store(tmp_path, "tenant-a", "session-a")
    artifact = owner.create_business_model(
        label="Scoped snapshot model",
        project_id="project-a",
    )
    snapshot_id = owner.snapshot(name="baseline")["snapshot_id"]

    other_tenant = _scoped_store(tmp_path, "tenant-b", "session-a")
    other_session = _scoped_store(tmp_path, "tenant-a", "session-b")
    for store in (other_tenant, other_session):
        assert store.list_snapshots() == []
        assert store.load_snapshot(snapshot_id) is None
        with pytest.raises(ValueError, match="Snapshot not found"):
            store.restore_snapshot(snapshot_id)

    assert owner.delete(artifact.artifact_id)
    assert owner.restore_snapshot(snapshot_id) == 1
    assert owner.get(artifact.artifact_id) is not None


def test_snapshot_id_cannot_escape_store_directory(tmp_path):
    store = _scoped_store(tmp_path, "tenant-a", "session-a")

    assert store.load_snapshot("../outside") is None
    snapshot = store.snapshot(name="../../outside")
    assert "/" not in snapshot["snapshot_id"]
    assert "\\" not in snapshot["snapshot_id"]
