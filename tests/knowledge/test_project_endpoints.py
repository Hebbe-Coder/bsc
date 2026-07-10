import os, tempfile, pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService
from app.api.knowledge_api import get_knowledge_service
import app.middleware.auth as auth_mw

# 真实实现的解析函数（模块加载时即为原始版本），cleanup 时还原，避免污染其它测试文件
REAL_RESOLVE = auth_mw.resolve_knowledge_auth


def _c():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    ga = "ga-t6-unique"
    settings.API_KEY = ga
    repo = KnowledgeRepository(db_path=p); ensure_schema(repo)
    svc = KnowledgeService(db_path=p)
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    # 让中间件用同一个临时 repo 解析 project key，保持测试密闭（符合 test_project_auth_api.py 约定）
    auth_mw.resolve_knowledge_auth = lambda api_key: REAL_RESOLVE(api_key, repo=repo)
    return TestClient(app), p, ga, repo, svc


def _cleanup(p, repo, svc):
    auth_mw.resolve_knowledge_auth = REAL_RESOLVE
    app.dependency_overrides.clear()
    # Windows 下需先关闭 sqlite 连接才能删除文件
    try:
        svc.repo.close()
    except Exception:
        pass
    try:
        repo.close()
    except Exception:
        pass
    for s in ("", "-wal", "-shm"):
        try:
            os.remove(p + s)
        except OSError:
            pass


def test_create_project_returns_admin_key():
    c, p, ga, repo, svc = _c()
    try:
        r = c.post("/knowledge/projects", json={"name": "P One"},
                   headers={"Authorization": f"Bearer {ga}"})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["project_id"].startswith("proj_")
        assert body["key"].startswith("sk-")
        assert body["role"] == "project_admin"
        # 用该 key 检索（project_admin 能力）应放行（结果为空但 200）
        c2 = c.post("/knowledge/retrieve",
                    json={"query": "x", "project_id": body["project_id"]},
                    headers={"Authorization": f"Bearer {body['key']}"})
        assert c2.status_code == 200
    finally:
        _cleanup(p, repo, svc)


def test_issue_key_for_existing_project():
    c, p, ga, repo, svc = _c()
    try:
        r = c.post("/knowledge/projects", json={"name": "P Two"},
                   headers={"Authorization": f"Bearer {ga}"})
        pid = r.json()["data"]["project_id"]
        rk = c.post(f"/knowledge/projects/{pid}/keys",
                    json={"role": "project_reader", "label": "ro"},
                    headers={"Authorization": f"Bearer {ga}"})
        assert rk.status_code == 200
        assert rk.json()["data"]["role"] == "project_reader"
        assert rk.json()["data"]["key"].startswith("sk-")
    finally:
        _cleanup(p, repo, svc)


def test_issue_key_unknown_project_404():
    c, p, ga, repo, svc = _c()
    try:
        rk = c.post("/knowledge/projects/nope/keys",
                    json={"role": "project_reader"},
                    headers={"Authorization": f"Bearer {ga}"})
        # ApiResponse.not_found 走统一信封，HTTP 200 但 code 表示未找到
        assert rk.status_code == 200
        body = rk.json()
        assert body.get("code") in (404, 40400) or body.get("success") is False
    finally:
        _cleanup(p, repo, svc)


def test_issue_key_invalid_role():
    c, p, ga, repo, svc = _c()
    try:
        r = c.post("/knowledge/projects", json={"name": "P3"},
                   headers={"Authorization": f"Bearer {ga}"})
        pid = r.json()["data"]["project_id"]
        rk = c.post(f"/knowledge/projects/{pid}/keys",
                    json={"role": "hacker"},
                    headers={"Authorization": f"Bearer {ga}"})
        assert rk.status_code == 200
        assert rk.json().get("success") is False
    finally:
        _cleanup(p, repo, svc)


def test_create_project_requires_admin():
    c, p, ga, repo, svc = _c()
    try:
        # 无 Authorization → 中间件应 401（知识库端点强制鉴权）。
        # 真实实现：TestClient 下 AuthMiddleware 以 HTTPException 形式抛出（见 test_api_auth.py 约定）。
        with pytest.raises(HTTPException) as exc:
            c.post("/knowledge/projects", json={"name": "X"})
        assert exc.value.status_code in (401, 403)
    finally:
        _cleanup(p, repo, svc)
