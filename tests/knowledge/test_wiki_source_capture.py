from datetime import datetime, timezone

from app.knowledge.wiki_contracts import SourceStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import (
    CapturedSourceInput,
    HorizonSignal,
    InvalidSourceTransition,
    SourceCaptureService,
    SourceTrustPolicy,
    sha256_content,
)


def test_source_capture_hashes_and_deduplicates_project_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-capture.db"))
    service = SourceCaptureService(repo)
    try:
        payload = CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="notes/brief.md",
            raw_content="# Brief\nSame evidence",
            vault_path="inbox/brief.md",
            trust_level="trusted",
        )

        first = service.capture(payload)
        duplicate = service.capture(payload)

        assert first.created is True
        assert duplicate.created is False
        assert duplicate.source["id"] == first.source["id"]
        assert first.source["content_hash"] == sha256_content("# Brief\nSame evidence")
        assert first.source["raw_content"] == "# Brief\nSame evidence"
        assert repo.list_sources("project-a") == [first.source]
    finally:
        repo.close()


def test_trust_policy_promotes_only_allowed_sources(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-policy.db"))
    policy = SourceTrustPolicy(
        trusted_source_types={"horizon_signal"},
        trusted_origin_prefixes=("https://news.example.com/",),
    )
    service = SourceCaptureService(repo, trust_policy=policy)
    try:
        trusted = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://news.example.com/ai/1",
                raw_content="Trusted article",
            )
        )
        assert trusted.source["status"] == SourceStatus.ELIGIBLE.value
        assert trusted.source["trust_level"] == "trusted"

        untrusted = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://unknown.example.net/ai/1",
                raw_content="Unknown article",
            )
        )
        assert untrusted.source["status"] == SourceStatus.VALIDATED.value
        assert untrusted.source["trust_level"] == "untrusted"
    finally:
        repo.close()


def test_horizon_signal_maps_to_immutable_source_input():
    signal = HorizonSignal(
        project_id="project-a",
        url="https://news.example.com/radar/42",
        title="Agent systems mature",
        summary="A concise radar item.",
        source_name="Horizon",
        published_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        tags=["agents", "knowledge"],
        raw_payload={"id": 42},
    )

    source = signal.to_source_input()

    assert source.source_type == "horizon_signal"
    assert source.origin == "https://news.example.com/radar/42"
    assert "Agent systems mature" in source.raw_content
    assert source.metadata["source_name"] == "Horizon"
    assert source.metadata["tags"] == ["agents", "knowledge"]


def test_source_capture_service_rejects_invalid_lifecycle_regression(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-lifecycle.db"))
    service = SourceCaptureService(repo)
    try:
        captured = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="notes/processed.md",
                raw_content="Ready evidence",
                trust_level="trusted",
            )
        )

        processed = service.transition_source(
            "project-a",
            captured.source["id"],
            SourceStatus.PROCESSED,
        )
        assert processed["status"] == SourceStatus.PROCESSED.value

        try:
            service.transition_source("project-a", captured.source["id"], SourceStatus.ELIGIBLE)
        except InvalidSourceTransition as exc:
            assert "processed -> eligible" in str(exc)
        else:
            raise AssertionError("expected invalid transition to be rejected")
    finally:
        repo.close()


def test_source_capture_versions_changed_content_at_the_same_origin(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-version.db"))
    service = SourceCaptureService(repo)
    try:
        first = service.capture(
            CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="first", trust_level="trusted")
        )
        second = service.capture(
            CapturedSourceInput(project_id="project-a", source_type="manual_upload", origin="brief.md", raw_content="second", trust_level="trusted")
        )

        assert first.created and second.created
        assert second.source["supersedes_id"] == first.source["id"]
        assert repo.get_source("project-a", first.source["id"])["status"] == "superseded"
        assert repo.get_source("project-a", second.source["id"])["status"] == "eligible"
        assert [(edge["from_id"], edge["to_id"], edge["edge_type"]) for edge in repo.list_graph_edges("project-a")] == [
            (second.source["id"], first.source["id"], "source_supersedes_source")
        ]
    finally:
        repo.close()
