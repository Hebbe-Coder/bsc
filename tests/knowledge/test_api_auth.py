"""知识库端点鉴权与限流回归测试。

目的：从代码层面锁死以下保证，防止日后有人把 /knowledge/ 误加进鉴权/限流白名单而静默放开：
1. 未携带有效 API Key 的请求访问 /knowledge/* 必须被拦截（401）；
2. 携带错误 Key 同样被拦截（401）；
3. 携带正确 Bearer Key 才放行（200 + 统一信封 code=0）；
4. 知识库专属限速档已在 RateLimitMiddleware 中注册。

注：全局 AuthMiddleware 在 TestClient 下会把 401 以 HTTPException 形式抛出，故用 pytest.raises 校验。
"""
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.middleware.rate_limiter import RateLimitMiddleware


@pytest.fixture
def secured_client(client, monkeypatch):
    """复用知识库 client（临时库 + DI 覆盖），并强制开启鉴权、关闭限流以隔离验证。"""
    monkeypatch.setattr(settings, "API_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    return client


def test_knowledge_requires_api_key_401(secured_client):
    # 无任何 Authorization 头 → 全局 AuthMiddleware 必须拦截
    with pytest.raises(HTTPException) as exc:
        secured_client.get("/knowledge/documents")
    assert exc.value.status_code == 401


def test_knowledge_wrong_key_401(secured_client):
    with pytest.raises(HTTPException) as exc:
        secured_client.get(
            "/knowledge/documents",
            headers={"Authorization": "Bearer wrong-key"},
        )
    assert exc.value.status_code == 401


def test_knowledge_valid_key_passes(secured_client):
    r = secured_client.get(
        "/knowledge/documents",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200  # 统一信封：成功码为 200
    assert "documents" in body["data"]


def test_knowledge_ingest_requires_key_401(secured_client):
    # 可灌入端点同样必须鉴权（防止未授权灌语料）
    with pytest.raises(HTTPException) as exc:
        secured_client.post("/knowledge/ingest", data={"text": "x"})
    assert exc.value.status_code == 401


def test_knowledge_rate_limit_profiles_registered():
    # 知识库专属限速档已注册，且 ingest 严于全局默认
    pl = RateLimitMiddleware._PATH_RATE_LIMITS
    assert pl.get("/knowledge/ingest") == {"rate": 5, "burst": 10}
    assert pl.get("/knowledge/retrieve") == {"rate": 20, "burst": 40}
    assert pl.get("/knowledge/documents") == {"rate": 15, "burst": 30}
