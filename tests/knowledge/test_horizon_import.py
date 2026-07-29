from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.project_profile import ProjectProfileService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository


def _accepted_horizon_item(*, item_id: str = "rss:ai:concurrent") -> dict:
    return {
        "id": item_id,
        "source_type": "rss",
        "title": "Concurrent agent systems",
        "url": "https://example.com/concurrent-agent-systems",
        "content": "Primary article content for a single immutable discovery signal.",
        "published_at": "2026-07-29T00:00:00Z",
        "ai_score": 8.4,
        "ai_reason": "Useful architecture",
        "ai_summary": "A grounded summary.",
        "ai_tags": ["agents"],
        "metadata": {"category": "ai-news"},
    }


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


def test_horizon_item_claim_releases_after_capture_failure(tmp_path, monkeypatch):
    repo = WikiRepository(db_path=str(tmp_path / "horizon-claim-retry.db"))
    try:
        importer = HorizonImportService(repo)
        item = _accepted_horizon_item()
        for run_id in ("knowledge-capture-run-failed", "knowledge-capture-run-retry"):
            repo.create_run(KnowledgeRun(
                id=run_id,
                project_id="project-a",
                run_type="horizon_capture",
                trigger="test",
                status=RunStatus.RUNNING,
            ))
        original_capture = importer.capture_service.capture

        def fail_once(*_args, **_kwargs):
            raise RuntimeError("search projection is temporarily unavailable")

        monkeypatch.setattr(importer.capture_service, "capture", fail_once)
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            importer.import_items(
                project_id="project-a",
                run_id="horizon-run-retry",
                stage="filtered",
                capture_run_id="knowledge-capture-run-failed",
                items=[item],
            )

        claim = repo.get_horizon_import_claim(
            project_id="project-a",
            horizon_run_id="horizon-run-retry",
            horizon_stage="filtered",
            horizon_item_id=item["id"],
        )
        assert claim is None

        monkeypatch.setattr(importer.capture_service, "capture", original_capture)
        report = importer.import_items(
            project_id="project-a",
            run_id="horizon-run-retry",
            stage="filtered",
            capture_run_id="knowledge-capture-run-retry",
            items=[item],
        )

        assert report == {"accepted": 1, "created": 1, "duplicates": 0, "rejected": 0}
        claim = repo.get_horizon_import_claim(
            project_id="project-a",
            horizon_run_id="horizon-run-retry",
            horizon_stage="filtered",
            horizon_item_id=item["id"],
        )
        assert claim["status"] == "completed"
        assert claim["source_id"] == repo.list_sources("project-a")[0]["id"]
    finally:
        repo.close()


def test_horizon_item_claim_can_recover_an_expired_worker_lease(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "horizon-claim-lease.db"))
    try:
        first = repo.claim_horizon_import(
            project_id="project-a",
            horizon_run_id="horizon-run-lease",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:lease",
            content_hash="a" * 64,
            capture_run_id="knowledge-capture-run-first",
            lease_seconds=1,
        )
        assert first["claimed"] is True
        repo._execute(
            "UPDATE knowledge_horizon_import_claims SET lease_expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", first["claim"]["id"]),
        )
        repo._commit()

        recovered = repo.claim_horizon_import(
            project_id="project-a",
            horizon_run_id="horizon-run-lease",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:lease",
            content_hash="b" * 64,
            capture_run_id="knowledge-capture-run-recovery",
        )

        assert recovered["claimed"] is True
        assert recovered["recovered"] is True
        assert recovered["claim"]["capture_run_id"] == "knowledge-capture-run-recovery"
        assert repo.complete_horizon_import_claim(
            project_id="project-a",
            horizon_run_id="horizon-run-lease",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:lease",
            capture_run_id="knowledge-capture-run-first",
            source_id="source-first",
        ) is False
        assert repo.complete_horizon_import_claim(
            project_id="project-a",
            horizon_run_id="horizon-run-lease",
            horizon_stage="filtered",
            horizon_item_id="rss:ai:lease",
            capture_run_id="knowledge-capture-run-recovery",
            source_id="source-recovered",
        ) is True
    finally:
        repo.close()


def test_horizon_import_claim_prevents_concurrent_duplicate_source_creation(tmp_path):
    db_path = str(tmp_path / "horizon-claim-concurrent.db")
    repositories = [WikiRepository(db_path=db_path), WikiRepository(db_path=db_path)]
    importers = [HorizonImportService(repository) for repository in repositories]
    barrier = Barrier(2)
    item = _accepted_horizon_item()
    for index, repository in enumerate(repositories):
        repository.create_run(KnowledgeRun(
            id=f"knowledge-capture-run-{index}",
            project_id="project-a",
            run_type="horizon_capture",
            trigger="test",
            status=RunStatus.RUNNING,
        ))

    def execute(index: int) -> dict[str, int]:
        barrier.wait(timeout=5)
        return importers[index].import_items(
            project_id="project-a",
            run_id="horizon-run-concurrent",
            stage="filtered",
            capture_run_id=f"knowledge-capture-run-{index}",
            items=[item],
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            reports = list(executor.map(execute, range(2)))

        verifier = WikiRepository(db_path=db_path)
        try:
            sources = verifier.list_sources("project-a")
            claim = verifier.get_horizon_import_claim(
                project_id="project-a",
                horizon_run_id="horizon-run-concurrent",
                horizon_stage="filtered",
                horizon_item_id=item["id"],
            )
        finally:
            verifier.close()

        assert len(sources) == 1
        assert sorted(report["created"] for report in reports) == [0, 1]
        assert sorted(report["duplicates"] for report in reports) == [0, 1]
        assert claim["status"] == "completed"
        assert claim["source_id"] == sources[0]["id"]
    finally:
        for repository in repositories:
            repository.close()
