"""知识库端点鉴权与限流回归测试。

目的：从代码层面锁死以下保证，防止日后有人把 /knowledge/ 误加进鉴权白名单而静默放开，
或误把知识库端点放进开发模式放行逻辑：
1. 已配置 API_KEY 时：/knowledge/* 无 Key → 401；错 Key → 401；正确 Bearer → 200。
2. 未配置 API_KEY（开发模式）时：/knowledge/* 仍必须被拒（401），非知识库路径正常放行。
3. 知识库专属限速档已在 RateLimitMiddleware 中注册。

注：全局 AuthMiddleware 在 TestClient 下会把 401 以 HTTPException 形式抛出，故用 pytest.raises 校验。
"""
from app.middleware.rate_limiter import RateLimitMiddleware


def test_knowledge_requires_api_key_401(anon_client):
    response = anon_client.get("/knowledge/documents")
    assert response.status_code == 401


def test_knowledge_wrong_key_401(anon_client):
    response = anon_client.get(
        "/knowledge/documents",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


def test_knowledge_valid_key_passes(client):
    r = client.get(
        "/knowledge/documents",
        headers={"Authorization": "Bearer test-api-key-for-knowledge-suite"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200  # 统一信封：成功码为 200
    assert "documents" in body["data"]


def test_knowledge_ingest_requires_key_401(anon_client):
    # 可灌入端点同样必须鉴权（防止未授权灌语料）
    response = anon_client.post("/knowledge/ingest", data={"text": "x"})
    assert response.status_code == 401


def test_knowledge_rejected_when_api_key_unset(dev_unset_client):
    # 即使处于「未配置 API_KEY」的开发模式，知识库端点也必须被拒
    response = dev_unset_client.get("/knowledge/documents")
    assert response.status_code == 401
    # 非知识库路径（如 /docs）在开发模式仍正常放行，证明收紧是范围限定的
    r = dev_unset_client.get("/docs")
    assert r.status_code == 200


def test_knowledge_rate_limit_profiles_registered():
    # 知识库专属限速档已注册，且 ingest 严于全局默认
    pl = RateLimitMiddleware._PATH_RATE_LIMITS
    assert pl.get("/knowledge/ingest") == {"rate": 5, "burst": 10}
    assert pl.get("/knowledge/retrieve") == {"rate": 20, "burst": 40}
    assert pl.get("/knowledge/documents") == {"rate": 15, "burst": 30}
