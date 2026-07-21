import sqlite3

from app.knowledge.schema import ensure_schema
from app.knowledge.wiki_repository import WikiRepository


def test_wiki_schema_is_additive_and_idempotent(tmp_path):
    db_path = tmp_path / "wiki-schema.db"
    repo = WikiRepository(db_path=str(db_path))
    try:
        ensure_schema(repo)
        ensure_schema(repo)

        connection = sqlite3.connect(db_path)
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'knowledge_%'"
            )
        }
        expected = {
            "knowledge_vaults",
            "knowledge_sources",
            "knowledge_wiki_pages",
            "knowledge_proposals",
            "knowledge_proposal_operations",
            "knowledge_citations",
            "knowledge_runs",
            "knowledge_schedules",
            "knowledge_distillations",
            "knowledge_graph_edges",
            "knowledge_eval_runs",
        }
        assert expected <= names

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_kw_%'"
            )
        }
        assert {"idx_kw_sources_project_status", "idx_kw_runs_project_created"} <= indexes
    finally:
        repo.close()
        connection.close()
