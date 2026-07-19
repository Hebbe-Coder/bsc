from app.repositories.knowledge_repository import KnowledgeRepository
import hashlib
import tempfile
import os


def _repo():
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = KnowledgeRepository(db_path=p)
    from app.knowledge.schema import ensure_schema
    ensure_schema(r)
    return r, p


def _cleanup(r, p):
    r.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(p + suffix)
        except OSError:
            pass


def test_create_and_get_project():
    r, p = _repo()
    r.create_project("p1", "Proj One", {"k": "v"}, {"provider": "local", "enabled": True})
    proj = r.get_project("p1")
    assert proj["name"] == "Proj One"
    assert proj["rerank_config"]["provider"] == "local"
    _cleanup(r, p)


def test_project_key_hash_lookup():
    r, p = _repo()
    r.create_project("p1", "P1", {}, {})
    plaintext = "sk-project-p1-admin-1234"
    r.create_project_key(hashlib.sha256(plaintext.encode()).hexdigest(), "p1", "project_admin", "main")
    role, pid = r.get_project_key_by_hash(hashlib.sha256(plaintext.encode()).hexdigest())
    assert role == "project_admin" and pid == "p1"
    miss = r.get_project_key_by_hash("deadbeef")
    assert miss is None
    _cleanup(r, p)


def test_benchmark_crud():
    r, p = _repo()
    r.add_benchmark("p1", "咖啡 烘焙", ["c1", "c2"], "smoke")
    rows = r.list_benchmarks("p1")
    assert len(rows) == 1 and rows[0]["query"] == "咖啡 烘焙"
    _cleanup(r, p)


def test_list_projects_decodes_json():
    r, p = _repo()
    r.create_project("p1", "Proj One", {"k": "v"}, {"provider": "local", "enabled": True})
    rows = r.list_projects()
    assert rows[0]["rerank_config"]["provider"] == "local"
    assert rows[0]["metadata"]["k"] == "v"
    _cleanup(r, p)
