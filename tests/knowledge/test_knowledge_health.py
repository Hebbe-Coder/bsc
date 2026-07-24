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
            contents={"wiki/concepts/policy.md": f"# Policy\nClaim [source:{first['id']}]\n"},
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


def test_health_excludes_rules_navigation_and_log_from_substantive_citation_coverage(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health-substantive-pages.db"))
    source = SourceCaptureService(repo).capture(
        CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="brief.md",
            raw_content="Evidence-backed policy.",
            trust_level="trusted",
        )
    ).source
    try:
        repo.record_publication(
            project_id="project-a",
            contents={
                "AGENTS.md": "# Rules\n",
                "wiki/index.md": "# Index\n- [[wiki/overview.md]]\n",
                "wiki/log.md": "# Log\n- Published\n",
                "wiki/overview.md": (
                    "---\ntitle: Overview\nkind: brief\n---\n"
                    f"[[wiki/concepts/policy.md]] [source:{source['id']}]\n"
                ),
                "wiki/concepts/policy.md": (
                    "---\ntitle: Policy\nkind: concept\n---\n"
                    f"Evidence-backed policy. [source:{source['id']}]\n"
                ),
            },
            source_ids=[source["id"]],
        )

        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")

        assert health["pages"] == 5
        assert health["citation_coverage"] == 1.0
        assert health["uncited_page_ids"] == []
        assert health["orphan_page_ids"] == []
    finally:
        repo.close()


def test_health_excludes_navigation_and_log_citation_history_from_dangling_and_stale_counts(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "health-nonsubstantive-citations.db"))
    try:
        repo.record_publication(
            project_id="project-a",
            contents={
                "wiki/index.md": "# Index\nLegacy [source:missing-source]\n",
                "wiki/log.md": "# Log\nLegacy [source:missing-source]\n",
            },
            source_ids=[],
        )

        health = KnowledgeHealthService(repo).snapshot(project_id="project-a")

        assert health["dangling_citation_count"] == 0
        assert health["stale_citation_count"] == 0
    finally:
        repo.close()
