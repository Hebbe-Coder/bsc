import hashlib
import hmac
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.request_signature import RequestSignatureMiddleware


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    app.add_middleware(RequestSignatureMiddleware)
    return TestClient(app)


def _signature_header(api_key: str, path: str) -> str:
    timestamp = str(int(time.time()))
    body_md5 = hashlib.md5(b"", usedforsecurity=False).hexdigest()
    message = f"{timestamp}GET{path}{body_md5}"
    signature = hmac.new(
        api_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"Signature key={api_key},timestamp={timestamp},signature={signature}"


def test_signature_disabled_allows_protected_request(monkeypatch):
    monkeypatch.setattr(settings, "SIGNATURE_ENABLED", False)
    response = _client().get("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_signature_enabled_rejects_unsigned_protected_request(monkeypatch):
    monkeypatch.setattr(settings, "SIGNATURE_ENABLED", True)
    monkeypatch.setattr(settings, "API_KEY", "signature-test-key")
    response = _client().get("/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_signature_enabled_accepts_valid_signature(monkeypatch):
    api_key = "signature-test-key"
    monkeypatch.setattr(settings, "SIGNATURE_ENABLED", True)
    monkeypatch.setattr(settings, "API_KEY", api_key)
    response = _client().get(
        "/protected",
        headers={"Authorization": _signature_header(api_key, "/protected")},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_valid_signature_authenticates_through_the_full_application(monkeypatch):
    from app.main import app

    api_key = "signature-test-key"
    monkeypatch.setattr(settings, "API_KEY", api_key)
    monkeypatch.setattr(settings, "SIGNATURE_ENABLED", True)

    response = TestClient(app).get(
        "/api/mcp/compatibility",
        headers={"Authorization": _signature_header(api_key, "/api/mcp/compatibility")},
    )

    assert response.status_code == 200
