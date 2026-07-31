from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.knowledge.information_intelligence import InformationIntelligenceService
from app.knowledge.information_intelligence_contracts import (
    SignalBatch,
    SignalItem,
    SourceRegistryEntry,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.knowledge.wiki_repository import WikiRepository


def _entry(project_id: str = "project-a") -> SourceRegistryEntry:
    return SourceRegistryEntry(
        project_id=project_id,
        name="BSC engineering feed",
        connector_type="rss",
        feed_url="https://example.com/engineering.xml",
        authority_tier="trusted",
        topics=["agents"],
        languages=["en"],
    )


def _batch(registry_id: str, *, project_id: str = "project-a", batch_id: str = "batch-001") -> SignalBatch:
    return SignalBatch(
        project_id=project_id,
        batch_id=batch_id,
        execution_id=f"execution-{batch_id}",
        connector_type="rss",
        items=[
            SignalItem(
                registry_id=registry_id,
                external_id="entry-001",
                title="A reliable engineering update",
                url="https://example.com/articles/one?utm_source=rss",
                raw_content="# A reliable engineering update\n\nPrimary evidence body.",
                published_at="2026-07-27T00:00:00Z",
                discovery_metrics={"popularity": 98, "views": 5000},
                derivatives=[
                    {
                        "kind": "summary",
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "content": "A derived summary, not primary evidence.",
                    }
                ],
            )
        ],
    )


def test_source_registry_reports_credential_bound_connectors_as_unavailable(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence.db"))
    service = InformationIntelligenceService(repository)
    try:
        rss = service.register_source(_entry())
        unavailable = service.register_source(
            SourceRegistryEntry(
                project_id="project-a",
                name="Reddit discovery",
                connector_type="reddit",
                feed_url="https://www.reddit.com/r/MachineLearning/.rss",
            )
        )

        assert rss["availability"] == "available"
        assert unavailable["availability"] == "unavailable"
        assert unavailable["unavailable_reason"] == "credential_or_terms_required"
    finally:
        repository.close()


def test_n8n_manifest_contains_only_enabled_available_first_release_sources(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-manifest.db"))
    service = InformationIntelligenceService(repository)
    try:
        rss = service.register_source(_entry())
        youtube = service.register_source(
            SourceRegistryEntry(
                project_id="project-a",
                name="BSC video channel",
                connector_type="youtube_channel_rss",
                feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UC123",
                channel_id="UC123",
                authority_tier="primary",
            )
        )
        service.register_source(
            SourceRegistryEntry(
                project_id="project-a",
                name="Disabled feed",
                connector_type="rss",
                feed_url="https://example.com/disabled.xml",
                enabled=False,
            )
        )
        service.register_source(
            SourceRegistryEntry(
                project_id="project-a",
                name="Unavailable social connector",
                connector_type="reddit",
                feed_url="https://www.reddit.com/r/example/.rss",
            )
        )

        manifest = service.n8n_source_manifest("project-a")

        assert manifest["state"] == "ready"
        assert manifest["project_id"] == "project-a"
        assert {source["id"] for source in manifest["sources"]} == {rss["id"], youtube["id"]}
        assert all(set(source) <= {
            "id", "name", "connector_type", "feed_url", "channel_id", "topics", "languages",
            "freshness_hours", "retention_days", "authority_tier",
        } for source in manifest["sources"])
        assert [source["id"] for source in service.n8n_source_manifest("project-a", "rss")["sources"]] == [rss["id"]]
        with pytest.raises(ValueError, match="unavailable"):
            service.n8n_source_manifest("project-a", "reddit")
    finally:
        repository.close()


def test_signal_batch_keeps_raw_evidence_and_derivatives_separate_and_replays_idempotently(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence.db"))
    service = InformationIntelligenceService(repository)
    try:
        registry = service.register_source(_entry())
        first = service.ingest(_batch(registry["id"]))
        replay = service.ingest(_batch(registry["id"]))

        assert first["replayed"] is False
        assert first["status"] == "completed"
        assert replay["replayed"] is True
        assert replay["receipt_count"] == 1
        source = repository.get_source("project-a", first["receipts"][0]["source_id"])
        assert source is not None
        assert source["origin"] == "https://example.com/articles/one"
        assert source["raw_content"] == "# A reliable engineering update\n\nPrimary evidence body."
        assert source["metadata"]["intelligence"]["discovery_metrics"]["popularity"] == 98
        derivatives = service.list_derivatives("project-a", source["id"])
        assert derivatives[0]["kind"] == "summary"
        assert derivatives[0]["content"] == "A derived summary, not primary evidence."
        assert len(repository.list_sources("project-a")) == 1
    finally:
        repository.close()


def test_information_overview_separates_new_sources_from_repeat_discovery_receipts(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-overview-dedup.db"))
    service = InformationIntelligenceService(repository)
    try:
        registry = service.register_source(_entry())
        first = service.ingest(_batch(registry["id"], batch_id="batch-first"))
        repeated = service.ingest(_batch(registry["id"], batch_id="batch-repeat"))

        assert first["receipts"][0]["metadata"]["source_created"] is True
        assert repeated["receipts"][0]["reason"] == "duplicate_source"
        assert repeated["receipts"][0]["metadata"]["source_created"] is False
        assert service.overview("project-a")["counts"] == {
            "sources": 1,
            "available_sources": 1,
            "unavailable_sources": 0,
            "captured": 2,
            "new_sources": 1,
            "duplicate_sources": 1,
            "lead_only": 0,
            "rejected": 0,
        }
    finally:
        repository.close()


def test_lead_only_never_claims_to_have_captured_primary_evidence(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence.db"))
    service = InformationIntelligenceService(repository)
    try:
        registry = service.register_source(_entry())
        result = service.ingest(
            SignalBatch(
                project_id="project-a",
                batch_id="lead-batch",
                execution_id="lead-execution",
                connector_type="rss",
                items=[
                    SignalItem(
                        registry_id=registry["id"],
                        external_id="lead-1",
                        title="External lead",
                        url="https://example.com/lead",
                        lead_only=True,
                        discovery_metrics={"popularity": 99},
                    )
                ],
            )
        )

        receipt = result["receipts"][0]
        source = repository.get_source("project-a", receipt["source_id"])
        assert receipt["disposition"] == "lead_only"
        assert source["metadata"]["intelligence"]["evidence_state"] == "lead_only"
        assert source["metadata"]["intelligence"]["raw_evidence_captured"] is False
    finally:
        repository.close()


def test_signal_batch_rejects_a_registry_from_another_project(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence.db"))
    service = InformationIntelligenceService(repository)
    try:
        registry = service.register_source(_entry("project-b"))
        with pytest.raises(PermissionError, match="registry"):
            service.ingest(_batch(registry["id"]))
    finally:
        repository.close()


def test_signal_intake_projects_bsc_owned_evidence_to_a_configured_obsidian_vault(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-vault.db"))
    vault_root = tmp_path / "vault"
    (vault_root / "projects" / "project-a").mkdir(parents=True)
    repository.configure_vault("project-a", "projects/project-a")
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault_root))
    service = InformationIntelligenceService(repository)
    try:
        registry = service.register_source(_entry())
        result = service.ingest(_batch(registry["id"]))
        source = repository.get_source("project-a", result["receipts"][0]["source_id"])
        assert source is not None
        mirror = source["metadata"]["intelligence"]["obsidian_projection"]
        assert mirror["status"] == "completed"
        assert (vault_root / "projects" / "project-a" / "01_Sources" / "bsc-evidence" / f"{source['id']}.md").is_file()
    finally:
        repository.close()


def test_daily_brief_is_a_redacted_completed_batch_projection_with_confirmation_lineage(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-brief.db"))
    service = InformationIntelligenceService(repository)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    try:
        registry = service.register_source(_entry())
        captured = service.ingest(_batch(registry["id"], batch_id="brief-captured"))
        lead = service.ingest(
            SignalBatch(
                project_id="project-a",
                batch_id="brief-lead",
                execution_id="execution-brief-lead",
                connector_type="rss",
                items=[
                    SignalItem(
                        registry_id=registry["id"],
                        external_id="lead-brief-1",
                        title="Needs primary confirmation",
                        url="https://example.com/lead-brief",
                        lead_only=True,
                    )
                ],
            )
        )

        brief = service.daily_brief("project-a", day=day)

        assert brief["state"] == "available"
        assert brief["coverage"] == "complete"
        assert brief["denominator"] == 2
        assert brief["summary"]["captured"] == 1
        assert brief["summary"]["confirmation_required"] == 1
        assert brief["confirmation_queue"][0]["next_action"] == "capture_original_source"
        assert set(brief["lineage"]["batch_ids"]) == {captured["batch_id"], lead["batch_id"]}
        assert "raw_content" not in str(brief)
        assert "derivatives" not in str(brief)
        assert brief["delivery"]["state"] == "unavailable"
    finally:
        repository.close()


def test_daily_brief_reports_no_sample_for_a_window_without_completed_batches(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-brief-empty.db"))
    service = InformationIntelligenceService(repository)
    day = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=2)).isoformat()
    try:
        brief = service.daily_brief("project-a", day=day)
        assert brief["state"] == "no_sample"
        assert brief["coverage"] == "no_sample"
        assert brief["denominator"] == 0
        assert brief["lineage"]["receipt_ids"] == []
    finally:
        repository.close()


def test_daily_brief_interprets_legacy_naive_batch_timestamps_in_shanghai_time():
    start = "2026-07-30T16:00:00Z"
    end = "2026-07-31T16:00:00Z"
    assert InformationIntelligenceService._timestamp_in_window(
        "2026-07-31T00:15:00",
        start,
        end,
    ) is True
    assert InformationIntelligenceService._timestamp_in_window(
        "2026-07-30T16:00:00.000001Z",
        start,
        end,
    ) is True
    assert InformationIntelligenceService._timestamp_in_window(
        "2026-07-31T16:00:00Z",
        start,
        end,
    ) is False


def test_horizon_review_queue_is_metadata_only_and_excludes_already_cited_signals(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-horizon-queue.db"))
    service = InformationIntelligenceService(repository)
    try:
        repository.create_source(
            SourceRecord(
                id="horizon-cited",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://example.com/cited",
                content_hash="a" * 64,
                raw_content="PRIVATE CITED HORIZON BODY",
                trust_level="reviewed",
                status=SourceStatus.ELIGIBLE,
                metadata={"title": "Already cited", "ai_score": 9.7},
            )
        )
        repository.create_source(
            SourceRecord(
                id="horizon-pending",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://example.com/pending",
                content_hash="b" * 64,
                raw_content="PRIVATE PENDING HORIZON BODY",
                trust_level="reviewed",
                status=SourceStatus.ELIGIBLE,
                metadata={"title": "Pending primary review", "ai_score": 8.7, "task_families": ["research"]},
            )
        )
        repository.record_publication(
            project_id="project-a",
            contents={"wiki/cited.md": "# Cited\n[source:horizon-cited]\n"},
            source_ids=["horizon-cited"],
        )
        # Publication normally transitions sources to processed. Restore the
        # fixture to eligible so this test proves citation filtering instead
        # of passing only because of the source-status filter.
        repository._execute(
            "UPDATE knowledge_sources SET status=? WHERE project_id=? AND id=?",
            (SourceStatus.ELIGIBLE.value, "project-a", "horizon-cited"),
        )
        repository._commit()
        repository.create_source(
            SourceRecord(
                id="horizon-low-priority",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://example.com/low-priority",
                content_hash="c" * 64,
                raw_content="PRIVATE LOW PRIORITY HORIZON BODY",
                trust_level="reviewed",
                status=SourceStatus.ELIGIBLE,
                metadata={"title": "Lower priority review", "ai_score": 1.2},
            )
        )

        def reject_full_source_read(*_args, **_kwargs):
            raise AssertionError("Horizon review queue must use metadata-only source projections")

        monkeypatch.setattr(repository, "list_sources", reject_full_source_read)
        monkeypatch.setattr(repository, "get_source", reject_full_source_read)
        monkeypatch.setattr(repository, "list_citations", reject_full_source_read)
        queue = service.horizon_review_queue("project-a", limit=1)

        assert queue["state"] == "available"
        assert queue["count"] == 1
        assert queue["items"] == [{
            "source_id": "horizon-pending",
            "title": "Pending primary review",
            "origin": "https://example.com/pending",
            "status": "eligible",
            "trust_level": "reviewed",
            "ai_score": 8.7,
            "task_families": ["research"],
            "next_action": "capture_primary_source",
        }]
        assert "PRIVATE" not in str(queue)
        full_queue = service.horizon_review_queue("project-a")
        assert [item["source_id"] for item in full_queue["items"]] == ["horizon-pending", "horizon-low-priority"]
        metadata_by_id = {
            str(source["id"]): source
            for source in repository.list_evidence_source_metadata("project-a")
        }
        assert metadata_by_id["horizon-pending"]["status"] == SourceStatus.ELIGIBLE.value
        assert metadata_by_id["horizon-low-priority"]["status"] == SourceStatus.ELIGIBLE.value
    finally:
        repository.close()


def test_horizon_review_queue_advances_to_primary_review_after_a_linked_capture(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "intelligence-horizon-primary-review.db"))
    service = InformationIntelligenceService(repository)
    try:
        repository.create_source(
            SourceRecord(
                id="horizon-pending",
                project_id="project-a",
                source_type="horizon_signal",
                origin="https://example.com/release",
                content_hash="d" * 64,
                raw_content="PRIVATE HORIZON BODY",
                trust_level="reviewed",
                status=SourceStatus.ELIGIBLE,
                metadata={"title": "Release signal", "ai_score": 8.7},
            )
        )
        repository.create_source(
            SourceRecord(
                id="primary-capture",
                project_id="project-a",
                source_type="primary_web",
                origin="https://example.com/release",
                content_hash="e" * 64,
                raw_content="PRIVATE PRIMARY BODY",
                trust_level="reviewed",
                status=SourceStatus.ELIGIBLE,
                metadata={
                    "evidence_role": "primary_capture",
                    "supports_horizon_signal_ids": ["horizon-pending"],
                },
            )
        )

        def reject_full_source_read(*_args, **_kwargs):
            raise AssertionError("Horizon review queue must use metadata-only source projections")

        monkeypatch.setattr(repository, "list_sources", reject_full_source_read)
        monkeypatch.setattr(repository, "get_source", reject_full_source_read)
        queue = service.horizon_review_queue("project-a")

        assert queue["items"] == [{
            "source_id": "horizon-pending",
            "title": "Release signal",
            "origin": "https://example.com/release",
            "status": "eligible",
            "trust_level": "reviewed",
            "ai_score": 8.7,
            "task_families": [],
            "next_action": "review_primary_capture",
            "primary_capture": {
                "source_id": "primary-capture",
                "status": "eligible",
                "origin": "https://example.com/release",
                "trust_level": "reviewed",
            },
        }]
        assert "PRIVATE" not in str(queue)
    finally:
        repository.close()
