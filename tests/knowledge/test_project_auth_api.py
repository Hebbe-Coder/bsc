import hashlib
import os
import tempfile
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


def test_project_reader_isolation_blocks_cross_project():
    """回归测试：project_reader 令牌的 project_id 必须与令牌绑定项目一致，
    否则跨项目检索/写入一律 403。"""
    ga = "ga-iso-1234"
    c, p, repo, svc = _client(ga)
    try:
        # 用 admin 灌入两个项目的数据
        c.post("/knowledge/ingest",
               data={"text": "secret-x alpha", "project_id": "PROJX", "title": "X"},
               headers={"Authorization": f"Bearer {ga}"})
        c.post("/knowledge/ingest",
               data={"text": "secret-y beta", "project_id": "PROJY", "title": "Y"},
               headers={"Authorization": f"Bearer {ga}"})

        # 创建绑定 PROJX 的 project_reader 密钥
        repo.create_project_key(
            hashlib.sha256(b"PK_X").hexdigest(), "PROJX", "project_reader", "r")

        # 自己的项目：允许
        ok = c.post(
            "/knowledge/retrieve",
            json={"query": "secret-x", "project_id": "PROJX"},
            headers={"Authorization": "Bearer PK_X"},
        )
        assert ok.status_code == 200, ok.text

        # 跨项目：拒绝（关键回归点）
        cross = c.post(
            "/knowledge/retrieve",
            json={"query": "secret-y", "project_id": "PROJY"},
            headers={"Authorization": "Bearer PK_X"},
        )
        assert cross.status_code == 403, cross.text

        # project_reader 写入：拒绝
        w = c.post(
            "/knowledge/ingest",
            data={"text": "should-fail", "project_id": "PROJX"},
            headers={"Authorization": "Bearer PK_X"},
        )
        assert w.status_code == 403, w.text
    finally:
        _cleanup(p)
