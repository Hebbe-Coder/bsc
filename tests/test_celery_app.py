from app.core.celery_app import SyncCelery, celery, get_celery_app, is_celery_broker_available


def test_celery_cli_entrypoint_reuses_the_configured_application():
    assert celery is get_celery_app()


def test_broker_availability_is_false_for_sync_or_failed_real_connection(monkeypatch):
    monkeypatch.setattr("app.core.celery_app.get_celery_app", lambda: SyncCelery())
    assert is_celery_broker_available() is False

    class FailedCelery:
        def connection_for_read(self, **_kwargs):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr("app.core.celery_app.get_celery_app", lambda: FailedCelery())
    assert is_celery_broker_available() is False


def test_broker_availability_releases_a_successful_connection(monkeypatch):
    class Connection:
        connected = False
        released = False

        def ensure_connection(self, **_kwargs):
            self.connected = True

        def release(self):
            self.released = True

    connection = Connection()
    celery_app = type("Celery", (), {"connection_for_read": lambda self, **kwargs: connection})()
    monkeypatch.setattr("app.core.celery_app.get_celery_app", lambda: celery_app)

    assert is_celery_broker_available() is True
    assert connection.released is True
