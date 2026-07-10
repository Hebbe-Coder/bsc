import sqlite3, os, tempfile
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema

def test_production_tables_created():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = KnowledgeRepository(db_path=path)
    ensure_schema(repo)
    conn = sqlite3.connect(path)
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('knowledge_projects','project_keys','knowledge_benchmarks')")]
    assert set(names) == {"knowledge_projects","project_keys","knowledge_benchmarks"}
    # project_members 复合索引存在
    idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_pm_project_user'").fetchone()
    assert idx is not None
    conn.close(); repo.close(); os.remove(path)
