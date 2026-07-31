from app.core.metrics import MetricsStore


class RecordingBackend:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.statements.append((sql, params))

    def commit(self):
        self.commits += 1


class UnavailableBackend:
    def __init__(self):
        self.calls = 0

    def execute(self, sql, params=()):
        self.calls += 1
        raise RuntimeError("no such table: api_usage_log")

    def commit(self):
        raise AssertionError("commit must not run after a failed execute")


def test_daily_metrics_use_cross_database_upsert():
    backend = RecordingBackend()
    store = MetricsStore()
    store._db_backend = backend
    store.request_counts["/health"] = 2
    store.response_times["/health"] = [10.0, 20.0]

    store._update_daily_stats()

    assert len(backend.statements) == 1
    sql, params = backend.statements[0]
    assert "INSERT OR REPLACE" not in sql
    assert "ON CONFLICT(date) DO UPDATE SET" in sql
    assert "total_requests=excluded.total_requests" in sql
    assert params[2] == 2
    assert backend.commits == 1


def test_metrics_persistence_failure_is_rate_limited(monkeypatch, caplog):
    backend = UnavailableBackend()
    store = MetricsStore()
    store._db_backend = backend
    now = [100.0]
    monkeypatch.setattr("app.core.metrics.time.monotonic", lambda: now[0])

    store.record_request("GET /assets", 25.0, 200, "GET")
    store.record_request("GET /assets", 25.0, 200, "GET")

    assert backend.calls == 1
    assert store.request_counts["GET /assets"] == 2
    assert caplog.text.count("Metrics persistence API usage logging failed") == 1

    now[0] += 61.0
    store.record_request("GET /assets", 25.0, 200, "GET")

    assert backend.calls == 2
