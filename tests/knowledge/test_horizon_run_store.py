import json

import pytest

from app.knowledge.horizon_client import HorizonClientError
from app.knowledge.horizon_run_store import HorizonRunStoreClient


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
