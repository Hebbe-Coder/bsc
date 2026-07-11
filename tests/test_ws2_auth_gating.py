import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.api import dashboard as dashboard_module
from app.api.auth_deps import verify_admin_key
from app.core.config import settings


def _req(headers=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard/overview",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_dashboard_unauth_rejected(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    with pytest.raises(Exception) as exc:
        verify_admin_key(_req({}))
    assert exc.value.status_code == 401


def test_dashboard_admin_key_accepted(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    assert verify_admin_key(_req({"Authorization": "Bearer ws2-admin"})) is True


def test_dashboard_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    with pytest.raises(Exception) as exc:
        verify_admin_key(_req({"Authorization": "Bearer wrong"}))
    assert exc.value.status_code == 401


def test_dashboard_router_unauth_401(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    app = FastAPI()
    app.include_router(dashboard_module.router)
    client = TestClient(app)
    resp = client.get("/dashboard/overview")
    assert resp.status_code == 401
