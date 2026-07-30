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


def test_semantic_distillation_is_explicit_and_enabled_in_the_docker_runtime():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = "KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED=${KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED:-true}"

    for service_name in ("bsc-backend", "celery-worker", "celery-beat"):
        assert expected in set(compose["services"][service_name]["environment"])


def test_growth_distillation_timeout_reaches_only_the_api_and_worker():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = "KNOWLEDGE_GROWTH_LLM_TIMEOUT_SECONDS=${KNOWLEDGE_GROWTH_LLM_TIMEOUT_SECONDS:-150}"

    for service_name in ("bsc-backend", "celery-worker"):
        assert expected in set(compose["services"][service_name]["environment"])

    assert expected not in set(compose["services"]["celery-beat"]["environment"])


def test_pbos_compilation_timeout_reaches_only_the_api_and_worker():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = {
        "PBOS_LLM_TIMEOUT_SECONDS=${PBOS_LLM_TIMEOUT_SECONDS:-120}",
        "PBOS_LLM_MODEL=${PBOS_LLM_MODEL:-}",
        "PBOS_LLM_MAX_OUTPUT_TOKENS=${PBOS_LLM_MAX_OUTPUT_TOKENS:-2600}",
        "PBOS_LLM_MAX_STRUCTURED_ATTEMPTS=${PBOS_LLM_MAX_STRUCTURED_ATTEMPTS:-2}",
        "PBOS_LLM_MAX_CONTEXT_DOCUMENTS=${PBOS_LLM_MAX_CONTEXT_DOCUMENTS:-4}",
        "PBOS_LLM_CONTEXT_DOCUMENT_MAX_TOKENS=${PBOS_LLM_CONTEXT_DOCUMENT_MAX_TOKENS:-180}",
    }

    for service_name in ("bsc-backend", "celery-worker"):
        assert expected <= set(compose["services"][service_name]["environment"])

    assert not (expected & set(compose["services"]["celery-beat"]["environment"]))


def test_growth_task_lifecycle_limits_reach_only_the_api_and_worker():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = {
        "KNOWLEDGE_GROWTH_TASK_SOFT_TIMEOUT_SECONDS=${KNOWLEDGE_GROWTH_TASK_SOFT_TIMEOUT_SECONDS:-390}",
        "KNOWLEDGE_GROWTH_TASK_TIMEOUT_SECONDS=${KNOWLEDGE_GROWTH_TASK_TIMEOUT_SECONDS:-420}",
    }

    for service_name in ("bsc-backend", "celery-worker"):
        assert expected <= set(compose["services"][service_name]["environment"])

    beat_environment = set(compose["services"]["celery-beat"]["environment"])
    assert not any(item.startswith("KNOWLEDGE_GROWTH_TASK_") for item in beat_environment)


def test_source_sync_recovery_timeout_reaches_only_the_api_and_worker():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = "KNOWLEDGE_SOURCE_SYNC_RECOVERY_TIMEOUT_SECONDS=${KNOWLEDGE_SOURCE_SYNC_RECOVERY_TIMEOUT_SECONDS:-900}"

    for service_name in ("bsc-backend", "celery-worker"):
        assert expected in set(compose["services"][service_name]["environment"])

    assert expected not in set(compose["services"]["celery-beat"]["environment"])


def test_horizon_run_store_configuration_reaches_api_and_worker_only():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    required = {
        "HORIZON_ENABLED=${HORIZON_ENABLED:-false}",
        "HORIZON_API_BASE_URL=${HORIZON_API_BASE_URL:-}",
        "HORIZON_RUNS_ROOT=${HORIZON_RUNS_ROOT:-/horizon-runs}",
        "HORIZON_MAX_ARTIFACT_AGE_HOURS=${HORIZON_MAX_ARTIFACT_AGE_HOURS:-48}",
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


def test_api_and_worker_share_the_redis_broker_contract():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    api_required = {
        "REDIS_URL=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/0",
        "CELERY_ENABLED=${CELERY_ENABLED:-true}",
        "CELERY_BROKER_URL=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/2",
        "CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/3",
    }
    worker_required = {
        "CELERY_BROKER_URL=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/2",
        "CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/3",
    }

    assert api_required <= set(compose["services"]["bsc-backend"]["environment"])
    for service_name in ("celery-worker", "celery-beat"):
        assert worker_required <= set(compose["services"][service_name]["environment"])


def test_durable_services_share_postgresql_and_redis_runtime_dependencies():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    for service_name in ("bsc-backend", "celery-worker", "celery-beat"):
        environment = set(compose["services"][service_name]["environment"])
        assert "DB_TYPE=postgresql" in environment
        assert "EVENT_BACKEND=redis" in environment
        assert "REDIS_URL=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD must be set}@redis:6379/0" in environment
        assert "DB_URL=postgresql://${POSTGRES_USER:-bsc}:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}@postgres:5432/${POSTGRES_DB:-bsc}" in environment
        assert compose["services"][service_name]["depends_on"] == {
            "redis": {"condition": "service_healthy"},
            "postgres": {"condition": "service_healthy"},
        }

    assert "CACHE_TYPE=redis" in set(compose["services"]["bsc-backend"]["environment"])
    assert compose["services"]["redis"]["healthcheck"]["test"] == ["CMD-SHELL", 'redis-cli --no-auth-warning -a "$$REDIS_PASSWORD" ping']
    assert "profiles" not in compose["services"]["redis"]
    assert "profiles" not in compose["services"]["postgres"]
    assert "postgres-data-v2:/var/lib/postgresql/data" in compose["services"]["postgres"]["volumes"]
    assert "ports" not in compose["services"]["redis"]
    assert "ports" not in compose["services"]["postgres"]
    assert "--requirepass" in compose["services"]["redis"]["command"]
    assert "RATE_LIMIT_ENABLED=${RATE_LIMIT_ENABLED:-true}" in set(compose["services"]["bsc-backend"]["environment"])
    assert "RATE_LIMIT_BACKEND=redis" in set(compose["services"]["bsc-backend"]["environment"])


def test_dbos_artifact_ledger_is_mounted_on_the_durable_api_volume():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    api = compose["services"]["bsc-backend"]
    assert "DBOS_DATA_ROOT=/data/dbos" in set(api["environment"])
    assert "bsc-data:/data" in api["volumes"]
