import json
import os

import pytest

from scripts.run_horizon_pipeline import _producer_lock, _safe_error, _write_state


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
