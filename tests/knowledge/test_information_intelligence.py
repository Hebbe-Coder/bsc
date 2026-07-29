from __future__ import annotations

import pytest

from app.core.config import settings
from app.knowledge.information_intelligence import InformationIntelligenceService
from app.knowledge.information_intelligence_contracts import (
    SignalBatch,
    SignalItem,
    SourceRegistryEntry,
)
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
