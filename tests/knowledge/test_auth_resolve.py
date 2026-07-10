import hashlib, tempfile, os
from app.middleware.auth import resolve_knowledge_auth
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.core.config import settings


def _setup():
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = KnowledgeRepository(db_path=p)
    ensure_schema(r)
    r.create_project("p1", "P1", {}, {})
    proj_key = "proj-secret-1234"
    r.create_project_key(hashlib.sha256(proj_key.encode()).hexdigest(), "p1", "project_admin", "m")
    return r, p, proj_key


def _cleanup(r, p):
    try:
        r.close()
    except Exception:
        pass
    for s in ("", "-wal", "-shm"):
        try:
            os.remove(p + s)
        except OSError:
            pass


def test_global_admin():
    r, p, _ = _setup()
    settings.API_KEY = "admin-key"
    try:
        role, pid = resolve_knowledge_auth("admin-key", repo=r)
        assert role == "admin" and pid is None
    finally:
        _cleanup(r, p)


def test_project_key():
    r, p, pk = _setup()
    settings.API_KEY = "admin-key"
    try:
        role, pid = resolve_knowledge_auth(pk, repo=r)
        assert role == "project_admin" and pid == "p1"
    finally:
        _cleanup(r, p)


def test_unknown_rejected():
    r, p, _ = _setup()
    settings.API_KEY = "admin-key"
    try:
        assert resolve_knowledge_auth("wrong", repo=r) is None
    finally:
        _cleanup(r, p)
