from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware import rate_limiter
from app.middleware.rate_limiter import RateLimitMiddleware


class _UnavailableBucket:
    def consume(self, *_args, **_kwargs):
        raise OSError("redis unavailable")


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, rate=1, burst=1)
    return TestClient(app)


def test_production_redis_rate_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(rate_limiter, "RedisTokenBucket", lambda _url: _UnavailableBucket())
    client = _client()

    response = client.get("/protected")

    # The middleware's Redis client cannot connect to this test URL and must
    # return an honest protection failure rather than silently allowing traffic.
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
