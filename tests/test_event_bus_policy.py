import sys
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.event_bus import RedisEventBus


class _UnavailableRedis:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        raise OSError("redis unavailable")


def test_production_redis_event_bus_refuses_process_local_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_UnavailableRedis))

    with pytest.raises(RuntimeError, match="Redis event backend is unavailable"):
        RedisEventBus("redis://unavailable")


def test_development_redis_event_bus_marks_a_local_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_UnavailableRedis))

    bus = RedisEventBus("redis://unavailable")

    assert bus._use_fallback() is True
