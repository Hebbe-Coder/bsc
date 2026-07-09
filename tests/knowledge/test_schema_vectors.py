import tempfile

from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema


def test_knowledge_vectors_table_exists():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    row = repo._execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_vectors'"
    ).fetchone()
    assert row is not None
    # 可写可读
    repo._execute(
        "INSERT INTO knowledge_vectors (chunk_id, model, dim, vector) VALUES (?,?,?,?)",
        ("c1", "mock", 3, b"\x00\x00\x00\x00"))
    repo._commit()
    cnt = repo._execute("SELECT COUNT(*) AS c FROM knowledge_vectors").fetchone()["c"]
    assert cnt == 1
