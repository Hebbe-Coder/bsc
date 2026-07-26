from __future__ import annotations

from pathlib import Path

import pytest

from app.artifacts import ArtifactGraphStore, DeliverableArtifact
from app.core.config import settings
from app.dbos.intake import IntakeError
from app.dbos.service import DBOSService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


def _complete(service: DBOSService, session_id: str) -> None:
    while question := service.next_intake_question(session_id):
        service.answer_intake(session_id, question["question_id"], skipped=True)


def _source(source_id: str, *, project_id: str = "project-a", status: SourceStatus = SourceStatus.ELIGIBLE, origin: str = "https://research.example.test/report"):
    return SourceRecord(
        id=source_id,
        project_id=project_id,
        source_type="horizon_signal",
        origin=origin,
        content_hash=(source_id[0] * 64),
        raw_content="A verified research signal with a concrete applicability boundary.",
        trust_level="reviewed",
        status=status,
        metadata={"summary": "Evidence supports a staged customer-research decision."},
    )


def test_recommendations_only_use_admitted_url_backed_project_sources(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "knowledge.db"))
    try:
        repo.create_source(_source("a-source"))
        repo.create_source(_source("b-source", status=SourceStatus.VALIDATED))
        repo.create_source(_source("c-source", origin="note.md"))
        service = DBOSService(store=ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a"), knowledge_repository=repo)
        session = service.create_intake("project-a", "Build a research workflow")
        _complete(service, session.artifact_id)
        service.select_intake_tier(session.artifact_id, "standard")

        recommended = service.recommend_intake(session.artifact_id)

        assert recommended.recommendation_state == "available"
        assert [item["source_id"] for item in recommended.recommendations] == ["a-source"]
        assert recommended.recommendations[0]["source_url"].startswith("https://")
        assert recommended.recommendations[0]["captured_at"]
    finally:
        repo.close()


def test_unavailable_evidence_and_unapproved_export_do_not_write_to_vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "knowledge.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault_root))
        service = DBOSService(store=ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a"), knowledge_repository=repo)
        session = service.create_intake("project-a", "Build a research workflow")
        _complete(service, session.artifact_id)
        service.select_intake_tier(session.artifact_id, "lite")
        assert service.recommend_intake(session.artifact_id).recommendation_state == "unavailable"
        service.convert_intake(session.artifact_id)

        with pytest.raises(IntakeError, match="explicit approval"):
            service.export_intake_handoff(session.artifact_id, actor_id="owner", approved=False)
        assert not (vault_root / "projects" / "project-a" / "outputs" / "handoffs").exists()
    finally:
        repo.close()


def test_approved_handoff_is_hashed_idempotent_and_not_a_source(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "knowledge.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(_source("a-source"))
        monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault_root))
        service = DBOSService(store=ArtifactGraphStore(str(tmp_path / "artifacts"), project_id="project-a"), knowledge_repository=repo)
        session = service.create_intake("project-a", "Build a research workflow")
        _complete(service, session.artifact_id)
        service.select_intake_tier(session.artifact_id, "lite")
        service.recommend_intake(session.artifact_id)
        service.convert_intake(session.artifact_id)

        first = service.export_intake_handoff(session.artifact_id, actor_id="owner", approved=True)
        second = service.export_intake_handoff(session.artifact_id, actor_id="owner", approved=True)
        target = vault_root / "projects" / "project-a" / "outputs" / "handoffs" / f"{session.artifact_id}.md"

        assert isinstance(first, DeliverableArtifact)
        assert first.artifact_id == second.artifact_id
        assert first.metadata["content_sha256"] == service.get_intake(session.artifact_id).handoff_sha256
        assert target.exists()
        assert "must not be re-ingested" in target.read_text(encoding="utf-8")
        assert repo.list_sources("project-a")[0]["id"] == "a-source"
    finally:
        repo.close()
