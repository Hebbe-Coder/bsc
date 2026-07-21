from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.wiki_repository import WikiRepository


def test_horizon_import_preserves_run_score_and_original_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "horizon.db"))
    try:
        report = HorizonImportService(repo, min_score=7.0).import_items(
            project_id="project-a",
            run_id="horizon-run-1",
            stage="filtered",
            items=[
                {
                    "id": "rss:ai:1", "source_type": "rss", "title": "Agent systems",
                    "url": "https://example.com/agents", "content": "Primary article content.",
                    "published_at": "2026-07-21T00:00:00Z", "ai_score": 8.4,
                    "ai_reason": "Useful architecture", "ai_summary": "A grounded summary.",
                    "ai_tags": ["agents"], "metadata": {"category": "ai-news"},
                },
                {
                    "id": "rss:ai:2", "source_type": "rss", "title": "Noise",
                    "url": "https://example.com/noise", "content": "Low value", "ai_score": 3,
                },
            ],
        )

        assert report == {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 1}
        source = repo.list_sources("project-a")[0]
        assert source["status"] == "validated"
        assert source["metadata"]["horizon_run_id"] == "horizon-run-1"
        assert source["metadata"]["ai_score"] == 8.4
        assert "Primary article content." in source["raw_content"]
    finally:
        repo.close()
