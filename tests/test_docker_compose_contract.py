from pathlib import Path

import yaml


def test_celery_services_disable_the_http_healthcheck():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["celery-worker"]["healthcheck"] == {"disable": True}
    assert compose["services"]["celery-beat"]["healthcheck"] == {"disable": True}
