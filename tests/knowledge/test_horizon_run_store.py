import json

import pytest

from app.knowledge.horizon_client import HorizonClientError
from app.knowledge.horizon_run_store import (
    HorizonRunStoreClient,
    HorizonRunStoreEmptyError,
    resolve_horizon_run_store_location,
)


def test_horizon_run_store_uses_host_path_when_container_mount_is_not_visible(tmp_path):
    location = resolve_horizon_run_store_location(
        runs_root="/horizon-runs",
        host_path=tmp_path,
    )

    assert location.available is True
    assert location.path == tmp_path.resolve()
    assert location.mode == "host_fallback"


def test_horizon_run_store_reads_native_filtered_artifact(tmp_path):
    run_dir = tmp_path / "run-20260722"
    run_dir.mkdir()
    (run_dir / "filtered_items.json").write_text(
        json.dumps([{"id": "item-1", "title": "Signal"}]),
        encoding="utf-8",
    )

    response = HorizonRunStoreClient(runs_root=tmp_path).fetch_stage(run_id="run-20260722", stage="filtered")

    assert response.run_id == "run-20260722"
    assert response.stage == "filtered"
    assert response.items == [{"id": "item-1", "title": "Signal"}]


def test_horizon_run_store_rejects_traversal_and_unpublished_stage(tmp_path):
    client = HorizonRunStoreClient(runs_root=tmp_path)

    with pytest.raises(HorizonClientError, match="invalid"):
        client.fetch_stage(run_id="../outside", stage="filtered")
    with pytest.raises(HorizonClientError, match="filtered or enriched"):
        client.fetch_stage(run_id="run-1", stage="raw")


def test_horizon_run_store_discovers_latest_unimported_run_and_prefers_enriched(tmp_path):
    older = tmp_path / "run-older"
    older.mkdir()
    (older / "enriched_items.json").write_text(json.dumps([{"id": "old"}]), encoding="utf-8")
    newest = tmp_path / "run-newest"
    newest.mkdir()
    (newest / "filtered_items.json").write_text(json.dumps([{"id": "filtered"}]), encoding="utf-8")
    (newest / "enriched_items.json").write_text(json.dumps([{"id": "enriched"}]), encoding="utf-8")

    response = HorizonRunStoreClient(runs_root=tmp_path).fetch_latest_stage(exclude_run_ids={"run-older"})

    assert response.run_id == "run-newest"
    assert response.stage == "enriched"
    assert response.items == [{"id": "enriched"}]


def test_horizon_run_store_reports_no_new_artifact_after_exclusions(tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "filtered_items.json").write_text("[]", encoding="utf-8")

    with pytest.raises(HorizonRunStoreEmptyError, match="No new"):
        HorizonRunStoreClient(runs_root=tmp_path).fetch_latest_stage(exclude_run_ids={"run-1"})
