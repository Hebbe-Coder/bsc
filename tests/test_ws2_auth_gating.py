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


import os
import tempfile
from app.api import files_api


def _client_with_file(monkeypatch, key):
    d = tempfile.mkdtemp()
    monkeypatch.setattr(files_api, "_OUTPUT_DIR", d)
    monkeypatch.setattr(settings, "API_KEY", key)
    p = os.path.join(d, "report_1.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write("<html>ok</html>")
    app = FastAPI()
    app.include_router(files_api.router)
    return TestClient(app), "report_1.html"


def test_download_no_token_rejected(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    assert client.get(f"/api/files/{name}").status_code == 401


def test_download_with_token_ok(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    from app.api.auth_deps import download_url
    resp = client.get(download_url(name))
    assert resp.status_code == 200
    assert resp.text == "<html>ok</html>"


def test_download_path_traversal_blocked(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    resp = client.get("/api/files/..%2f..%2fsecret?token=ws2-admin")
    assert resp.status_code in (400, 404)


def test_asset_agent_returns_protected_url(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    from app.api.auth_deps import download_url
    url = download_url("report_x.html")
    assert url.startswith("/api/files/report_x.html?token=")
    assert "ws2-admin" not in url
