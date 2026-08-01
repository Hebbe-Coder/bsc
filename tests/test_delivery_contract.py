import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, lifespan


def test_liveness_is_public_and_legacy_routes_advertise_sunset(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "delivery-key")
    client = TestClient(app)

    live = client.get("/live")
    legacy = client.post(
        "/bsc/compile",
        json={},
        headers={"Authorization": "Bearer delivery-key"},
    )

    assert live.status_code == 200
    assert legacy.headers["deprecation"] == "true"
    assert legacy.headers["sunset"] == "Thu, 31 Dec 2026 23:59:59 GMT"
    assert "/api/orchestrate" in legacy.headers["link"]


def test_spa_shell_remains_public_in_production_auth_mode(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "delivery-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code in {200, 307}


def test_production_startup_fails_when_database_initialization_fails(monkeypatch):
    import app.db as database_module

    def fail_init():
        raise OSError("database unavailable")

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(database_module, "init_db", fail_init)

    async def run_lifespan():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="configured database is unavailable"):
        asyncio.run(run_lifespan())


def test_production_startup_survives_recovered_growth_runs(monkeypatch):
    from app import main
    from app.knowledge import candidate_extraction, method_distillation

    async def no_orchestrator_recovery():
        return []

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(main, "recover_orchestrator_jobs_on_startup", no_orchestrator_recovery)
    monkeypatch.setattr(
        method_distillation,
        "recover_abandoned_source_method_distillations",
        lambda repository: ["method-run"],
    )
    monkeypatch.setattr(
        candidate_extraction,
        "recover_abandoned_source_candidate_extractions",
        lambda repository: ["candidate-run"],
    )

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
