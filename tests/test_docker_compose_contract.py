from pathlib import Path

import yaml


def test_celery_services_disable_the_http_healthcheck():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["celery-worker"]["healthcheck"] == {"disable": True}
    assert compose["services"]["celery-beat"]["healthcheck"] == {"disable": True}


def test_deepseek_configuration_reaches_api_and_worker_only():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    required = {
        "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}",
        "DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}",
        "DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-chat}",
        "ANALYSIS_PROVIDER=${ANALYSIS_PROVIDER:-deepseek}",
        "GENERATION_PROVIDER=${GENERATION_PROVIDER:-deepseek}",
        "SOP_LLM_PROVIDER=${SOP_LLM_PROVIDER:-deepseek}",
        "RAG_LLM_PROVIDER=${RAG_LLM_PROVIDER:-deepseek}",
    }

    for service_name in ("bsc-backend", "celery-worker"):
        environment = set(compose["services"][service_name]["environment"])
        assert required <= environment

    beat_environment = set(compose["services"]["celery-beat"]["environment"])
    assert not any(item.startswith("DEEPSEEK_API_KEY=") for item in beat_environment)
    assert "ollama" not in compose["services"]["celery-worker"]["depends_on"]


def test_horizon_run_store_configuration_reaches_api_and_worker_only():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    required = {
        "HORIZON_ENABLED=${HORIZON_ENABLED:-false}",
        "HORIZON_API_BASE_URL=${HORIZON_API_BASE_URL:-}",
        "HORIZON_RUNS_ROOT=${HORIZON_RUNS_ROOT:-/horizon-runs}",
    }

    for service_name in ("bsc-backend", "celery-worker"):
        environment = set(compose["services"][service_name]["environment"])
        assert required <= environment

    beat_environment = set(compose["services"]["celery-beat"]["environment"])
    assert not any(item.startswith("HORIZON_API_KEY=") for item in beat_environment)
    assert not any(item.startswith("HORIZON_RUNS_ROOT=") for item in beat_environment)

    expected_mount = "${HORIZON_RUNS_HOST_PATH:-./data/horizon-runs}:/horizon-runs:ro"
    assert expected_mount in compose["services"]["bsc-backend"]["volumes"]
    assert expected_mount in compose["services"]["celery-worker"]["volumes"]
    assert expected_mount not in compose["services"]["celery-beat"]["volumes"]
