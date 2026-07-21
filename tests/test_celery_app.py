from app.core.celery_app import celery, get_celery_app


def test_celery_cli_entrypoint_reuses_the_configured_application():
    assert celery is get_celery_app()
