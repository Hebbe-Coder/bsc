from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.project_profile import ProjectProfileService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository


def test_horizon_import_preserves_run_score_and_original_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "horizon.db"))
    try:
        capture_run = KnowledgeRun(
            id="knowledge-capture-run-1",
            project_id="project-a",
            run_type="horizon_capture",
            trigger="test",
            status=RunStatus.RUNNING,
        )
        repo.create_run(capture_run)
        report = HorizonImportService(repo, min_score=7.0).import_items(
            project_id="project-a",
            run_id="horizon-run-1",
            stage="filtered",
            capture_run_id="knowledge-capture-run-1",
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
        assert source["metadata"]["admission_gate"] == "project_triage"
        assert source["metadata"]["evidence_role"] == "discovery_signal"
        assert source["metadata"]["primary_capture_required"] is True
        assert source["metadata"]["ai_score"] == 8.4
        assert source["metadata"]["title"] == "Agent systems"
        assert source["metadata"]["task_families"] == ["context_mapping"]
        assert "Primary article content." in source["raw_content"]
        assert "Horizon rationale:" not in source["raw_content"]
        assert "Horizon summary:" not in source["raw_content"]
        attempts = repo.list_source_capture_attempts("project-a", run_id="knowledge-capture-run-1")
        assert len(attempts) == 1
        assert attempts[0]["source_id"] == source["id"]
    finally:
        repo.close()


def test_horizon_import_uses_the_revisioned_project_source_policy(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "horizon-profile-policy.db"))
    try:
        ProjectProfileService(repo).update_profile(
            "project-a",
            {
                "source_policy": {
                    "primary_origin_prefixes": ["https://research.example/"],
                    "community_retention_days": 21,
                    "primary_retention_days": 730,
                }
            },
            expected_revision=0,
            actor_id="owner-a",
        )
        repo.create_run(KnowledgeRun(
            id="knowledge-capture-run-profile-policy",
            project_id="project-a",
            run_type="horizon_capture",
            trigger="test",
            status=RunStatus.RUNNING,
        ))

        report = HorizonImportService(repo).import_items(
            project_id="project-a",
            run_id="horizon-run-policy",
            stage="enriched",
            capture_run_id="knowledge-capture-run-profile-policy",
            items=[
                {
                    "id": "rss:policy:1",
                    "source_type": "rss",
                    "title": "Primary research signal",
                    "url": "https://research.example/brief",
                    "content": "Evidence captured from a configured primary origin.",
                    "ai_score": 9.2,
                }
            ],
        )

        assert report == {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 0}
        source = repo.list_sources("project-a")[0]
        policy = source["metadata"]["policy_assessment"]
        assert source["status"] == "validated"
        assert policy["authority"] == "primary"
        assert policy["retention_days"] == 730
        assert policy["profile_revision"] == 1
        assert policy["policy_source"] == "project_profile"
    finally:
        repo.close()
