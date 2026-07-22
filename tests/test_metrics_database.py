from app.core.metrics import MetricsStore


class RecordingBackend:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.statements.append((sql, params))

    def commit(self):
        self.commits += 1


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
