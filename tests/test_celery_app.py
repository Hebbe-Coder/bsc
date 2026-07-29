from importlib.util import find_spec

from app.core.celery_app import (
    CELERY_TASK_MODULES,
    SyncCelery,
    celery,
    get_celery_app,
    is_celery_broker_available,
)
from app.core.config import settings


def test_celery_cli_entrypoint_reuses_the_configured_application():
    assert celery is get_celery_app()


def test_worker_import_contract_lists_concrete_existing_task_modules():
    assert CELERY_TASK_MODULES == (
        "app.tasks.bsc_tasks",
        "app.tasks.document_tasks",
        "app.tasks.export_tasks",
        "app.tasks.knowledge_tasks",
        "app.tasks.growth_tasks",
        "app.tasks.method_distillation_tasks",
        "app.tasks.candidate_extraction_tasks",
        "app.tasks.pbos_tasks",
    )
    assert all(find_spec(module_name) is not None for module_name in CELERY_TASK_MODULES)


def test_real_celery_defaults_and_knowledge_route_share_the_runtime_queue():
    app = get_celery_app()
    if isinstance(app, SyncCelery):
        return

    expected_queue = settings.CELERY_KNOWLEDGE_QUEUE
    assert app.conf.task_default_queue == expected_queue
    assert app.conf.task_default_exchange == expected_queue
    assert app.conf.task_default_routing_key == expected_queue

    routed = app.amqp.router.route({}, "knowledge.execute", args=["default", "run"], kwargs={})
    assert routed["queue"].name == expected_queue


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
