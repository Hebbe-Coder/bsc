from datetime import datetime, timezone

from app.knowledge.wiki_contracts import SourceStatus
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.project_profile import ProjectProfileService
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import (
    CapturedSourceInput,
    HorizonSignal,
    InvalidSourceTransition,
    SourceCaptureService,
    SourceTrustPolicy,
    sha256_content,
)


class RecordingSourceIndex:
    def __init__(self, result=None):
        self.sources = []
        self.result = result or {"status": "ingested", "doc_id": "source-doc"}

    def project_source(self, source):
        self.sources.append(dict(source))
        return dict(self.result)


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


def test_source_capture_canonicalizes_web_origins_before_supersession(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "canonical-origin.db"))
    service = SourceCaptureService(repo)
    try:
        first = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="HTTPS://News.Example.com:443/brief/?b=2&utm_source=radar&a=1#overview",
                raw_content="First captured version.",
            )
        )
        updated = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://news.example.com/brief?a=1&utm_medium=email&b=2",
                raw_content="Updated captured version.",
            )
        )

        canonical_origin = "https://news.example.com/brief?a=1&b=2"
        assert first.source["origin"] == canonical_origin
        assert updated.source["origin"] == canonical_origin
        assert updated.source["supersedes_id"] == first.source["id"]
        assert repo.get_source("project-a", first.source["id"])["status"] == SourceStatus.SUPERSEDED.value
        attempts = repo.list_source_capture_attempts("project-a")
        assert {attempt["origin"] for attempt in attempts} == {canonical_origin}
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


def test_source_registry_precedes_projection_and_retains_projection_failure(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-projection.db"))
    index = RecordingSourceIndex({"status": "error", "reason": "backend unavailable"})
    service = SourceCaptureService(repo, search_index=index)
    try:
        result = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="evidence.md",
                raw_content="Registered before projection.",
                trust_level="trusted",
            )
        )

        assert index.sources[0]["id"] == result.source["id"]
        persisted = repo.get_source("project-a", result.source["id"])
        assert persisted["raw_content"] == "Registered before projection."
        assert persisted["metadata"]["projection"]["status"] == "failed"
        assert persisted["metadata"]["projection"]["code"] == "index_backend_error"
    finally:
        repo.close()


def test_trust_assessment_records_freshness_relevance_curation_and_extraction(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "source-assessment.db"))
    service = SourceCaptureService(repo, search_index=RecordingSourceIndex())
    try:
        result = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://trusted.example/items/1",
                raw_content="A complete extracted signal with enough material for synthesis and review.",
                trust_level="reviewed",
                metadata={
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "ai_score": 9.2,
                    "curated": True,
                    "extraction_status": "complete",
                },
            )
        )

        assessment = result.source["metadata"]["policy_assessment"]
        assert assessment["freshness"] == "fresh"
        assert assessment["relevance"] == "high"
        assert assessment["curation"] == "user_curated"
        assert assessment["extraction_quality"] == "complete"
        assert assessment["reasons"]
    finally:
        repo.close()


def test_capture_attempt_ledger_keeps_policy_projection_and_deduplication_evidence(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "capture-attempts.db"))
    service = SourceCaptureService(
        repo,
        search_index=RecordingSourceIndex({"status": "error", "reason": "backend unavailable"}),
    )
    try:
        payload = CapturedSourceInput(
            project_id="project-a",
            source_type="manual_upload",
            origin="evidence/brief.md",
            raw_content="Evidence must remain in the immutable source record only.",
            trust_level="trusted",
        )
        captured = service.capture(payload)
        duplicate = service.capture(payload)
        rejected = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="web_clip",
                origin="https://example.test/failed-extraction",
                raw_content="The rejected source is still retained for audit.",
                metadata={"extraction_status": "failed"},
            )
        )

        attempts = repo.list_source_capture_attempts("project-a", limit=20)
        by_outcome = {attempt["outcome"]: attempt for attempt in attempts}

        projection_failed = by_outcome["projection_failed"]
        assert projection_failed["source_id"] == captured.source["id"]
        assert projection_failed["content_hash"] == captured.source["content_hash"]
        assert projection_failed["projection"]["status"] == "failed"
        assert projection_failed["policy"]["extraction_quality"] == "complete"
        assert "raw_content" not in projection_failed

        duplicate_attempt = by_outcome["duplicate"]
        assert duplicate_attempt["source_id"] == duplicate.source["id"]
        assert duplicate_attempt["content_hash"] == captured.source["content_hash"]

        rejected_attempt = by_outcome["rejected_by_policy"]
        assert rejected_attempt["source_id"] == rejected.source["id"]
        assert rejected_attempt["policy"]["extraction_quality"] == "failed"
        assert repo.list_source_capture_attempts("project-b", limit=20) == []
    finally:
        repo.close()


def test_project_profile_source_policy_controls_authority_retention_and_capture_snapshot(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "profile-capture-policy.db"))
    service = SourceCaptureService(repo, search_index=RecordingSourceIndex())
    try:
        ProjectProfileService(repo).update_profile(
            "project-a",
            {
                "source_policy": {
                    "primary_origin_prefixes": ["https://primary.example/"],
                    "trusted_origin_prefixes": ["https://trusted.example/"],
                    "community_origin_prefixes": ["https://community.example/"],
                    "blocked_origin_prefixes": ["https://blocked.example/"],
                    "trusted_source_types": ["manual_upload"],
                    "require_triage_source_types": ["horizon_signal"],
                    "primary_retention_days": 720,
                    "trusted_retention_days": 360,
                    "community_retention_days": 45,
                    "untrusted_retention_days": 15,
                }
            },
            expected_revision=0,
            actor_id="owner-a",
        )

        primary = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://primary.example/brief",
                raw_content="Primary evidence remains subject to Horizon triage.",
                trust_level="reviewed",
            )
        )
        community = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="web_clip",
                origin="https://community.example/thread",
                raw_content="Community evidence requires review.",
            )
        )
        blocked = service.capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="https://blocked.example/unsafe",
                raw_content="Blocked evidence is retained only for the audit ledger.",
                trust_level="trusted",
            )
        )

        primary_policy = primary.source["metadata"]["policy_assessment"]
        assert primary.source["status"] == SourceStatus.VALIDATED.value
        assert primary_policy["authority"] == "primary"
        assert primary_policy["retention_days"] == 720
        assert primary_policy["policy_source"] == "project_profile"
        assert primary_policy["profile_revision"] == 1
        assert primary_policy["policy_snapshot"]["community_retention_days"] == 45
        assert primary_policy["retention_expires_at"]

        community_policy = community.source["metadata"]["policy_assessment"]
        assert community.source["status"] == SourceStatus.VALIDATED.value
        assert community.source["trust_level"] == "reviewed"
        assert community_policy["authority"] == "community"
        assert community_policy["retention_days"] == 45

        assert blocked.source["status"] == SourceStatus.REJECTED.value
        assert blocked.source["metadata"]["policy_assessment"]["authority"] == "blocked"
        assert blocked.source["metadata"]["projection"]["status"] == "skipped"

        attempts = repo.list_source_capture_attempts("project-a", limit=10)
        primary_attempt = next(item for item in attempts if item["source_id"] == primary.source["id"])
        assert primary_attempt["policy"]["profile_revision"] == 1
        assert primary_attempt["policy"]["policy_snapshot"]["primary_origin_prefixes"] == ["https://primary.example/"]
    finally:
        repo.close()


def test_unconfigured_project_uses_a_truthful_default_source_policy(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "default-capture-policy.db"))
    try:
        captured = SourceCaptureService(repo, search_index=RecordingSourceIndex()).capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="notes/brief.md",
                raw_content="Local evidence remains usable with the documented default policy.",
                trust_level="trusted",
            )
        )

        policy = captured.source["metadata"]["policy_assessment"]
        assert captured.source["status"] == SourceStatus.ELIGIBLE.value
        assert policy["policy_source"] == "default"
        assert policy["profile_revision"] == 0
        assert policy["profile_configured"] is False
        assert repo.get_profile("project-a") is None
    finally:
        repo.close()
