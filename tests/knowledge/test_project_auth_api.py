import hashlib, os, tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.service import KnowledgeService
import app.api.knowledge_api as kapi
import app.middleware.auth as auth_mw

_ORIG_RESOLVE = None


def _client(global_admin):
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings.API_KEY = global_admin
    repo = KnowledgeRepository(db_path=p)
    ensure_schema(repo)
    svc = KnowledgeService(repo=repo)
    app.dependency_overrides[kapi.get_knowledge_service] = lambda: svc
    # 让中间件用同一个临时 repo 解析 project key，避免污染真实 db 且保持测试密闭
    global _ORIG_RESOLVE
    _ORIG_RESOLVE = auth_mw.resolve_knowledge_auth
    orig = _ORIG_RESOLVE
    auth_mw.resolve_knowledge_auth = lambda api_key: orig(api_key, repo=repo)
    return TestClient(app), p, repo, svc


def _cleanup(p):
    global _ORIG_RESOLVE
    if _ORIG_RESOLVE is not None:
        auth_mw.resolve_knowledge_auth = _ORIG_RESOLVE
        _ORIG_RESOLVE = None
    app.dependency_overrides.clear()
    for s in ("", "-wal", "-shm"):
        try:
            os.remove(p + s)
        except OSError:
            pass


def test_ingest_auto_creates_project():
    ga = "ga-1234"
    c, p, repo, svc = _client(ga)
    try:
        r = c.post(
            "/knowledge/ingest",
            data={"text": "hello world", "project_id": "NEWPA", "title": "t"},
            headers={"Authorization": f"Bearer {ga}"},
        )
        assert r.status_code == 200, r.text
        assert repo.get_project("NEWPA") is not None

        # 用 project key 读取隔离（中间件现解析临时 repo 中的 key）
        repo.create_project_key(
            hashlib.sha256(b"pk1").hexdigest(), "NEWPA", "project_reader", "r"
        )
        ra = c.post(
            "/knowledge/retrieve",
            json={"query": "hello", "project_id": "NEWPA"},
            headers={"Authorization": "Bearer pk1"},
        )
        assert ra.status_code == 200, ra.text
    finally:
        _cleanup(p)
