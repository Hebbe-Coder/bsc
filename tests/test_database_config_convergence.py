def test_legacy_and_backend_sqlite_paths_share_settings(tmp_path, monkeypatch):
    import app.db as legacy_db
    from app.core.config import settings
    from app.core.database import SQLiteBackend, resolve_sqlite_path

    target = tmp_path / "configured.db"
    monkeypatch.setattr(settings, "DB_PATH", str(target))

    if legacy_db._connection is not None:
        legacy_db._connection.close()
        legacy_db._connection = None

    try:
        backend = SQLiteBackend()
        assert resolve_sqlite_path() == str(target)
        assert backend._db_path == str(target)

        backend.execute("CREATE TABLE backend_probe (id INTEGER PRIMARY KEY)")
        backend.commit()
        backend.close()

        legacy = legacy_db.get_db()
        count = legacy.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='backend_probe'"
        ).fetchone()[0]
    finally:
        if legacy_db._connection is not None:
            legacy_db._connection.close()
            legacy_db._connection = None

    assert count == 1


def test_clean_configured_database_bootstraps_repository_tables(tmp_path, monkeypatch):
    import app.db as legacy_db
    from app.core.config import settings
    from app.core.preference_db import PreferenceDB
    from app.db import init_db
    from app.knowledge.schema import ensure_schema
    from app.repositories import GraphRepository, KnowledgeRepository, ProjectRepository

    target = tmp_path / "clean.db"
    monkeypatch.setattr(settings, "DB_PATH", str(target))
    if legacy_db._connection is not None:
        legacy_db._connection.close()
        legacy_db._connection = None

    try:
        init_db()
        repo = ProjectRepository()
        project = repo.create_project("Clean install")
        asset = repo.save_asset(project["id"], "report", {"ok": True})
        document = repo.save_document(project["id"], "prd", "clean.md", "content")
        knowledge = KnowledgeRepository()
        ensure_schema(knowledge)
        entity = knowledge.save_knowledge_entity(
            "entity-clean",
            project["id"],
            "fact",
            "Clean entity",
        )
        preferences = PreferenceDB()
        assert preferences.create_user("clean-user", name="Clean User")
        graph = GraphRepository().save_graph_snapshot(
            "graph-clean", "Clean graph", {}, project_id=project["id"]
        )
    finally:
        if legacy_db._connection is not None:
            legacy_db._connection.close()
            legacy_db._connection = None

    assert asset["project_id"] == project["id"]
    assert document["project_id"] == project["id"]
    assert entity["title"] == "Clean entity"
    assert preferences.get_user("clean-user")["name"] == "Clean User"
    assert graph["project_id"] == project["id"]


def test_postgresql_sql_adaptation_escapes_literal_percent_patterns():
    from app.core.database import PostgreSQLBackend

    converted = PostgreSQLBackend._postgresql_sql(
        "SELECT payload BLOB FROM jobs WHERE status LIKE 'edited:%' AND session_id = ?"
    )

    assert "payload BYTEA" in converted
    assert "LIKE 'edited:%%'" in converted
    assert "session_id = %s" in converted
