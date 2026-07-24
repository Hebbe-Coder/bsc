import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from scripts.run_horizon_pipeline import HorizonProducerTimeout, _producer_lock, _run, _safe_error, _write_state


class _RunStore:
    def __init__(self):
        self.metadata = []

    def update_meta(self, run_id, payload):
        self.metadata.append((run_id, payload))


class _ProducerService:
    def __init__(self, *, hang_stage=""):
        self.hang_stage = hang_stage
        self.run_store = _RunStore()

    async def fetch_items(self, **_kwargs):
        if self.hang_stage == "fetch":
            await asyncio.Event().wait()
        return {"run_id": "run-test", "fetched": 3}

    async def score_items(self, **_kwargs):
        if self.hang_stage == "score":
            await asyncio.Event().wait()
        return {"scored": 3}

    async def filter_items(self, **_kwargs):
        if self.hang_stage == "filter":
            await asyncio.Event().wait()
        return {"kept": 2}

    async def enrich_items(self, **_kwargs):
        if self.hang_stage == "enrich":
            await asyncio.Event().wait()
        return {"enriched": 2}


def _args(**overrides):
    values = {
        "hours": 24,
        "sources": [],
        "threshold": 7.0,
        "enrich": True,
        "stage_timeout_seconds": 1,
        "enrichment_timeout_seconds": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_horizon_producer_lock_rejects_overlap_and_cleans_up(tmp_path):
    lock_path = tmp_path / ".bsc-producer.lock"

    with _producer_lock(lock_path, stale_after_seconds=60):
        assert lock_path.is_file()
        with pytest.raises(RuntimeError, match="already running"):
            with _producer_lock(lock_path, stale_after_seconds=60):
                pass

    assert not lock_path.exists()


def test_horizon_producer_reclaims_stale_lock_and_writes_atomic_state(tmp_path):
    lock_path = tmp_path / ".bsc-producer.lock"
    lock_path.write_text("stale", encoding="utf-8")
    os.utime(lock_path, (1, 1))
    state_path = tmp_path / "producer-state.json"

    with _producer_lock(lock_path, stale_after_seconds=60):
        _write_state(state_path, {"status": "completed", "fetched": 2})

    assert json.loads(state_path.read_text(encoding="utf-8")) == {"status": "completed", "fetched": 2}
    assert not state_path.with_suffix(".tmp").exists()


def test_horizon_producer_redacts_provider_keys():
    secret = "".join(("sk", "-", "secret-value"))
    assert secret not in _safe_error(RuntimeError(f"provider rejected {secret}"))


def test_horizon_producer_falls_back_to_filtered_artifact_when_enrichment_times_out(tmp_path):
    service = _ProducerService(hang_stage="enrich")

    result = asyncio.run(
        _run(_args(enrichment_timeout_seconds=0.01), tmp_path, service_factory=lambda **_kwargs: service)
    )

    assert result["status"] == "completed_with_degradation"
    assert result["ready_stage"] == "filtered"
    assert result["enrichment"] == {"status": "timed_out", "timeout_seconds": 0.01}
    assert result["degradations"] == ["enrichment_timeout"]
    assert service.run_store.metadata == [
        (
            "run-test",
            {
                "bsc_ready_at": service.run_store.metadata[0][1]["bsc_ready_at"],
                "bsc_ready_stage": "filtered",
                "producer": "bsc-scheduled",
                "enrichment": {"status": "timed_out", "timeout_seconds": 0.01},
            },
        )
    ]


def test_horizon_producer_fails_fast_when_a_required_stage_times_out(tmp_path):
    service = _ProducerService(hang_stage="score")

    with pytest.raises(HorizonProducerTimeout, match="score stage exceeded"):
        asyncio.run(_run(_args(stage_timeout_seconds=0.01), tmp_path, service_factory=lambda **_kwargs: service))
