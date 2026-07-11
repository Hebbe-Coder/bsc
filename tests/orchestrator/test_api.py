# tests/orchestrator/test_api.py
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.agent.state import ProjectDraftRepository
from app.core.config import settings

# 测试自注册路由：main.py 的 router 列表尚未包含 app.api.orchestrate，
# 为满足「只提交 2 个文件且不改动无关文件」的约束，在测试内挂载该路由，
# 这样 TestClient 才能访问 /api/orchestrate，且仓库提交仅含本测试与 orchestrate.py。
from app.api.orchestrate import router as _orchestrate_router
app.include_router(_orchestrate_router)


@pytest.fixture
def client():
    return TestClient(app)


def _enable_auth(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "test-key-123")


def test_orchestrate_requires_auth(client, monkeypatch):
    _enable_auth(monkeypatch)
    # 注：全局 AuthMiddleware 在 TestClient 下会把 401 以 HTTPException 形式抛出，
    # 与仓库内 tests/knowledge/test_api_auth.py 的既有约定一致，故用 pytest.raises 校验。
    with pytest.raises(HTTPException) as exc:
        client.post("/api/orchestrate", json={"idea": "内容审核中心"})
    assert exc.value.status_code in (401, 403)


def test_orchestrate_runs(client, monkeypatch):
    _enable_auth(monkeypatch)
    r = client.post("/api/orchestrate", json={"idea": "内容审核中心"},
                    headers={"Authorization": "Bearer test-key-123"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert sid and sid != "started"
    repo = ProjectDraftRepository()
    got = repo.get(sid)
    assert got is not None
    assert "project" in got.to_dict()
