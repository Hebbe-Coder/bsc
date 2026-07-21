from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.auth import AuthMiddleware


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    @app.options("/protected")
    async def protected_preflight():
        return {"ok": True}

    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def test_unauthenticated_middleware_request_returns_401(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "middleware-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = _client().get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}


def test_reader_key_is_rejected_with_403_outside_knowledge(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "middleware-key")
    monkeypatch.setattr(settings, "API_KEY_READER", "reader-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = _client().get(
        "/protected", headers={"Authorization": "Bearer reader-key"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "read-only key cannot access this endpoint"}


def test_unauthenticated_cors_preflight_bypasses_authentication(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "middleware-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = _client().options("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
