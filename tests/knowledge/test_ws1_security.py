import os, tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.knowledge_api import get_knowledge_service


@pytest.fixture
def env():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings.API_KEY = "ws1-admin"
    settings.API_KEY_READER = "ws1-reader"
    from app.knowledge.schema import ensure_schema
    from app.repositories.knowledge_repository import KnowledgeRepository
    repo = KnowledgeRepository(db_path=p)
    ensure_schema(repo)
    svc = __import__("app.knowledge.service", fromlist=["KnowledgeService"]).KnowledgeService(db_path=p)
    svc.ingest_text("项目A 的内容 alpha", project_id="PA", title="docA")
    svc.ingest_text("项目B 的内容 beta", project_id="PB", title="docB")
    app.dependency_overrides[get_knowledge_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    try:
        svc.repo.close()
        repo.close()
    except Exception:
        pass
    os.remove(p)
    for suf in ("", "-wal", "-shm"):
        try: os.remove(p + suf)
        except OSError: pass


def test_reader_with_project_id_only_sees_that_project(env):
    r = env.get("/knowledge/documents?project_id=PA",
                headers={"Authorization": "Bearer ws1-reader"})
    assert r.json()["success"] is True
    docs = r.json()["data"]["documents"]
    assert docs, "reader 应能看到 PA 文档"
    assert all(d["project_id"] == "PA" for d in docs)


def test_reader_without_project_id_is_rejected(env):
    # 关键安全断言：reader 绝不能因 allow_admin_all 而全表返回
    r = env.get("/knowledge/documents",
                headers={"Authorization": "Bearer ws1-reader"})
    # 本仓库的 HTTPException 处理器返回 {"code": 400, "message": ..., "data": None}
    # （HTTP 状态 400），无 success 字段；安全意图是「拒绝 + 400」。
    assert r.status_code == 400
    assert r.json()["code"] == 400


def test_admin_without_project_id_sees_all(env):
    r = env.get("/knowledge/documents",
                headers={"Authorization": "Bearer ws1-admin"})
    assert r.json()["success"] is True
    assert {d["project_id"] for d in r.json()["data"]["documents"]} == {"PA", "PB"}
