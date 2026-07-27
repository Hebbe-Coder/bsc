import sqlite3

from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_repository import WikiRepository
from app.repositories.knowledge_repository import KnowledgeRepository


def test_operations_tenant_migration_backfills_legacy_projects_and_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy-projects.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE knowledge_projects ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, "
        "metadata TEXT DEFAULT '{}', rerank_config TEXT DEFAULT '{}')"
    )
    connection.execute(
        "INSERT INTO knowledge_projects (id,name,created_at) VALUES (?,?,?)",
        ("legacy-project", "Legacy", "2026-07-01T00:00:00"),
    )
    connection.commit()
    connection.close()

    repo = WikiRepository(db_path=str(db_path))
    try:
        ensure_schema(repo)
        row = repo._execute(
            "SELECT tenant_id FROM knowledge_projects WHERE id=?", ("legacy-project",)
        ).fetchone()
        assert row["tenant_id"] == "default"
    finally:
        repo.close()


def test_tenant_scoped_project_queries_do_not_leak_other_projects(tmp_path):
    repo = KnowledgeRepository(db_path=str(tmp_path / "projects.db"))
    try:
        repo.create_project("project-a", "Project A", tenant_id="tenant-a")
        repo.create_project("project-b", "Project B", tenant_id="tenant-b")

        assert [item["id"] for item in repo.list_projects_for_tenant("tenant-a")] == ["project-a"]
        assert repo.get_project_for_tenant("project-a", "tenant-a")["tenant_id"] == "tenant-a"
        assert repo.get_project_for_tenant("project-b", "tenant-a") is None
    finally:
        repo.close()
