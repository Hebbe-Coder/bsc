from app.knowledge.knowledge_health import KnowledgeHealthService
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


def test_health_snapshot_reports_real_empty_state_without_synthetic_scores(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health.db"))
    try:
        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")

        assert health["status"] == "available"
        assert health["citation_coverage"] is None
        assert health["pages"] == 0
        assert health["evaluation"]["status"] == "unavailable"
        trend = KnowledgeHealthService(repo).trend(project_id="project-a")
        assert trend["source_throughput"] == []
        assert trend["evaluations"] == []
    finally:
        repo.close()


def test_health_counts_explicit_cross_source_contradictions(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health-contradictions.db"))
    first = SourceCaptureService(repo).capture(
        CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="first.md", raw_content="First", trust_level="trusted")
    ).source
    SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a", source_type="manual_upload", origin="second.md", raw_content="Second", trust_level="trusted",
            metadata={"contradicts_source_ids": [first["id"]]},
        )
    )
    try:
        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")

        assert health["contradiction_count"] == 1
        second_id = next(source["id"] for source in repo.list_sources("project-a") if source["id"] != first["id"])
        assert health["contradiction_pairs"] == [sorted([first["id"], second_id])]
    finally:
        repo.close()


def test_health_marks_citations_stale_when_their_source_is_superseded(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health-stale-citations.db"))
    capture = SourceCaptureService(repo)
    try:
        first = capture.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="brief.md",
                raw_content="First version",
                trust_level="trusted",
            )
        ).source
        repo.record_publication(
            project_id="project-a",
            contents={"wiki/index.md": f"# Index\nClaim [source:{first['id']}]\n"},
            source_ids=[],
        )

        capture.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="brief.md",
                raw_content="Second version",
                trust_level="trusted",
            )
        )

        assert repo.list_citations("project-a") == []
        citations = repo.list_citations("project-a", include_stale=True)
        assert len(citations) == 1
        assert citations[0]["source_id"] == first["id"]
        assert citations[0]["status"] == "stale"
        assert KnowledgeHealthService(repo).snapshot(project_id="project-a")["stale_citation_count"] == 1
    finally:
        repo.close()
