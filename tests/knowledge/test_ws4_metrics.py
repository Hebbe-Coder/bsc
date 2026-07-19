import os
import tempfile
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service
from app.knowledge import metrics as M


@pytest.fixture
def metrics_env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws4-admin"
    settings.API_KEY_READER = "ws4-reader"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("可观测性 检索 延迟 指标", project_id="P1", title="m")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    M.metrics.reset()
    yield TestClient(app), svc
    app.dependency_overrides.clear()
    svc.repo.close(); repo.close()
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def test_metrics_records_retrieval_and_auth(metrics_env):
    client, svc = metrics_env
    svc.retrieve("可观测性", project_id="P1", top_k=3)
    # 触发一次知识库鉴权失败（无 key）——按本仓库 T1-T7 约定，
    # 全局 AuthMiddleware 在 TestClient 下以 HTTPException(401) 抛出，
    # 但计数已在抛出前累加。
    with pytest.raises(HTTPException) as exc:
        client.get("/knowledge/documents")
    assert exc.value.status_code in (401, 403)
    r = client.get("/knowledge/metrics", headers={"Authorization": "Bearer ws4-admin"})
    assert r.json()["success"] is True
    data = r.json()["data"]
    assert data["retrieval_latency_ms"]["count"] >= 1
    assert data["auth_failures"] >= 1


def test_metrics_requires_admin(metrics_env):
    client, _ = metrics_env
    # 携带有效 reader key 通过中间件，再由 require_admin 依赖拦截为 403 响应
    # （无 key 会被中间件在路由前以 401 抛出，故此处用 reader key 验证 admin 门禁）。
    r = client.get("/knowledge/metrics", headers={"Authorization": "Bearer ws4-reader"})
    assert r.status_code == 403
    assert r.json()["code"] == 403
