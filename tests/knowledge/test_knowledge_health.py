from app.knowledge.knowledge_health import KnowledgeHealthService
from app.knowledge.wiki_repository import WikiRepository


def test_health_snapshot_reports_real_empty_state_without_synthetic_scores(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health.db"))
    try:
        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")

        assert health["status"] == "available"
        assert health["citation_coverage"] is None
        assert health["pages"] == 0
        assert health["evaluation"]["status"] == "unavailable"
    finally:
        repo.close()
