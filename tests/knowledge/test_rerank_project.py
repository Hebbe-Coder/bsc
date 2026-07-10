import os, tempfile
from app.knowledge.reranker import get_reranker, _encrypt_key, _decrypt_key
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.core.config import settings


def _repo():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    r = KnowledgeRepository(db_path=p); ensure_schema(r)
    return r, p


def _rm(r, p):
    try: r.close()
    except Exception: pass
    for s in ("", "-wal", "-shm"):
        try: os.remove(p + s)
        except OSError: pass


def test_fernet_roundtrip():
    master = "any-master-secret-123"
    enc = _encrypt_key("cloud-secret-xyz", master)
    assert enc != "cloud-secret-xyz"
    assert _decrypt_key(enc, master) == "cloud-secret-xyz"


def test_fernet_wrong_master_fails():
    enc = _encrypt_key("s", "master-A")
    import pytest
    with pytest.raises(Exception):
        _decrypt_key(enc, "master-B")


def test_project_rerank_resolution():
    r, p = _repo()
    try:
        r.create_project("pX", "X", {}, {"provider": "mock", "enabled": True})
        rr = get_reranker(project_id="pX", repo=r)
        assert rr.name == "mock"
        # 无 project → 走全局默认(settings.RERANK_PROVIDER 默认 none)
        rr2 = get_reranker(repo=r)
        assert rr2.name in ("none", "mock", "local")
    finally:
        _rm(r, p)


def test_project_disabled_falls_back_global():
    r, p = _repo()
    try:
        r.create_project("pY", "Y", {}, {"provider": "mock", "enabled": False})
        rr = get_reranker(project_id="pY", repo=r)
        # enabled=False → 不用项目配置，回退全局(默认 none)
        assert rr.name == "none"
    finally:
        _rm(r, p)


def test_explicit_provider_wins():
    r, p = _repo()
    try:
        r.create_project("pZ", "Z", {}, {"provider": "mock", "enabled": True})
        # 显式 provider 优先于项目配置
        assert get_reranker("none", project_id="pZ", repo=r).name == "none"
    finally:
        _rm(r, p)


def test_backward_compat_positional_provider():
    # test_reranker.py 既有用法必须不破
    assert get_reranker("none").name == "none"
    assert get_reranker("mock").name == "mock"
