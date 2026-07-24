import hashlib
import json
import os
from datetime import datetime, timezone

import pytest

from app.knowledge.growth_distillation import GrowthDistillationService, ManagedContentConflictError
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.growth_contracts import (
    FeedbackType,
    KnowledgeLineageEdge,
    OutputAsset,
    OutputEvaluation,
    OutputFeedback,
    ProjectKnowledgeProfile,
)
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus
from app.knowledge.wiki_rules import build_default_agents_rules


_CUTOFF_SAFE_TIME = datetime(2026, 7, 23, tzinfo=timezone.utc)


class _NarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {"daily": "## Grounded daily synthesis\n\n[source:source-a@revision-a] changes the project decision context."}
        names = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        return {
            "weekly": {
                names[0]: "# This week\n\n[source:source-a] is the decisive evidence.",
                names[1]: "# Knowledge actions\n\nReview [source:source-a].",
                names[2]: "# Content creation\n\nUse [source:source-a] for a review-gate explainer.",
                names[3]: "# Next context\n\n[source:source-a] remains available.",
                names[4]: "# Method iteration\n\n[source:source-a] requires evaluation before promotion.",
            }
        }


class _UncitedNarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {"daily": "## Generic daily update\n\nNothing to review."}
        return {
            "weekly": {
                name: "## Generic weekly update\n\nNothing to review."
                for name in GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
            }
        }


class _PartialNarrativeProvider:
    def render(self, *, kind, project_id, period, context):
        if kind == "daily":
            return {"daily": "## Grounded daily synthesis\n\n[source:source-a] changed the project decision context."}
        slots = GrowthDistillationService.WEEKLY_NARRATIVE_SLOTS
        return {
            "weekly": {
                slots[0]: "## Bespoke summary\n\n[source:source-a] changes the project decision context.",
                slots[1]: "## Uncited action\n\nFollow up next week.",
                slots[2]: "## Uncited content\n\nDraft a useful article.",
                slots[3]: "## Uncited context\n\nContinue the review.",
                slots[4]: "## Uncited method\n\nRevise the process.",
            }
        }


def test_validated_markdown_normalizes_structured_list_items_before_citation_validation():
    content = GrowthDistillationService._validated_markdown(
        [
            "Review the current project decision against [source:source-a].",
            "Draft one evidence-backed content angle from [source:source-a].",
        ],
        {"citation_source_ids": ["source-a"]},
    )

    assert content == (
        "- Review the current project decision against [source:source-a].\n\n"
        "- Draft one evidence-backed content angle from [source:source-a]."
    )
    assert "['Review" not in content


def test_weekly_distillation_is_idempotent_and_writes_dual_track_bundle(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.register_output(
            OutputAsset(
                id="output-a", project_id="project-a", kind="report", title="Accepted report", content_hash="a" * 64,
                vault_path="outputs/2026/output-a/report.md", idempotency_key="output-a", status="accepted",
                metadata={"task_family": "weekly-report"},
            )
        )
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T17:00:00Z")
        second = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T17:00:00Z")
        assert first["input_hash"] == second["input_hash"]
        assert second["status"] == "noop"
        project_root = root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        for name in ["00-本周总结.md", "01-知识行动.md", "02-内容创作.md", "03-下周上下文包.md", "04-方法迭代.md", "manifest.json"]:
            assert (project_root / name).exists()
        manifest = json.loads((project_root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["input_hash"] == first["input_hash"]
        assert manifest["owner"] == "bsc.knowledge.growth"
        assert manifest["ownership_marker"] == "bsc-growth-distillation/v1"
        assert len(manifest["paths"]) == 5
        for relative, expected_hash in manifest["file_hashes"].items():
            assert hashlib.sha256((root / "projects" / "project-a" / relative).read_bytes()).hexdigest() == expected_hash
    finally:
        repo.close()


def test_distillation_uses_validated_narrative_provider_and_records_its_mode(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-narrative.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="The project must keep review gates before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        service = GrowthDistillationService(repo, root, narrative_provider=_NarrativeProvider())

        daily = service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        weekly = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")

        daily_path = root / "projects" / "project-a" / daily["paths"][0]
        weekly_path = root / "projects" / "project-a" / weekly["paths"][0]
        assert "Grounded daily synthesis" in daily_path.read_text(encoding="utf-8")
        assert "[source:source-a]" in daily_path.read_text(encoding="utf-8")
        assert "[source:source-a@revision-a]" not in daily_path.read_text(encoding="utf-8")
        assert "decisive evidence" in weekly_path.read_text(encoding="utf-8")
        assert daily["manifest"]["generation"]["mode"] == "llm"
        assert weekly["manifest"]["generation"]["mode"] == "llm"
        assert weekly["manifest"]["distillation_contract_revision"] == GrowthDistillationService.DISTILLATION_CONTRACT_REVISION
    finally:
        repo.close()


def test_daily_distillation_prefers_current_admitted_horizon_evidence_when_budget_is_tight(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-triage-priority.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.save_profile(ProjectKnowledgeProfile(project_id="project-a"), actor_id="owner")
        repo.create_source(
            SourceRecord(
                id="legacy-source",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Legacy evidence that should not crowd out current triage. " * 40,
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        repo.create_source(
            SourceRecord(
                id="horizon-current",
                project_id="project-a",
                source_type="horizon_signal",
                content_hash="b" * 64,
                raw_content="Current Horizon evidence selected for this project. " * 300,
                trust_level="reviewed",
                status=SourceStatus.VALIDATED,
                metadata={
                    "admission_gate": "project_triage",
                    "relevance": 100,
                    "value": 100,
                    "freshness": 100,
                    "outputability": 100,
                    "connectedness": 100,
                },
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )
        SourceTriageService(repo).triage_source("project-a", "horizon-current")

        result = GrowthDistillationService(
            repo,
            root,
            narrative_provider=_UncitedNarrativeProvider(),
        ).run_daily(
            "project-a",
            "2026-07-24",
            source_cutoff="2026-08-01T00:00:00Z",
        )

        assert repo.get_source("project-a", "horizon-current")["status"] == SourceStatus.ELIGIBLE.value
        assert "horizon-current" in result["manifest"]["context"]["source_ids"]
        assert "horizon-current" in result["manifest"]["context"]["citation_source_ids"]
    finally:
        repo.close()


def test_distillation_rejects_uncited_narrative_and_uses_governed_fallback(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-uncited.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(repo, root, narrative_provider=_UncitedNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        assert result["manifest"]["generation"] == {
            "mode": "deterministic",
            "provider": "",
            "model": "",
            "reason": "provider_response_rejected",
        }
        rendered = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Generic weekly update" not in rendered
        assert "source-a" in rendered
        assert all(
            "[source:source-a]" in (root / "projects" / "project-a" / path).read_text(encoding="utf-8")
            for path in result["paths"]
        )
    finally:
        repo.close()


def test_distillation_preserves_only_cited_llm_documents_and_records_hybrid_provenance(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-hybrid.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(
            SourceRecord(
                id="source-a",
                project_id="project-a",
                source_type="article",
                content_hash="a" * 64,
                raw_content="Review gates are required before publication.",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=_CUTOFF_SAFE_TIME,
                updated_at=_CUTOFF_SAFE_TIME,
            )
        )

        result = GrowthDistillationService(repo, root, narrative_provider=_PartialNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        generation = result["manifest"]["generation"]
        assert generation["mode"] == "hybrid"
        assert generation["reason"] == "invalid_llm_documents_replaced"
        assert generation["llm_documents"] == [GrowthDistillationService.WEEKLY_DOCUMENTS[0]]
        assert set(generation["fallback_documents"]) == set(GrowthDistillationService.WEEKLY_DOCUMENTS[1:])
        summary = (root / "projects" / "project-a" / result["paths"][0]).read_text(encoding="utf-8")
        assert "Bespoke summary" in summary
        assert "Uncited action" not in (root / "projects" / "project-a" / result["paths"][1]).read_text(encoding="utf-8")
    finally:
        repo.close()


def test_hybrid_fallback_uses_only_records_retained_in_its_bounded_context(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-hybrid-citations.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article", content_hash="a" * 64,
            raw_content="Eligible evidence.", trust_level="trusted", status=SourceStatus.ELIGIBLE,
            captured_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        repo.create_source(SourceRecord(
            id="source-b", project_id="project-a", source_type="article", content_hash="b" * 64,
            raw_content="Superseded evidence.", trust_level="trusted", status=SourceStatus.SUPERSEDED,
        ))

        result = GrowthDistillationService(repo, root, narrative_provider=_PartialNarrativeProvider()).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
        )

        fallback_context = (root / "projects" / "project-a" / result["paths"][3]).read_text(encoding="utf-8")
        assert "[source:source-a]" in fallback_context
        assert "[source:source-b]" not in fallback_context
        assert '"rendered"' not in fallback_context
    finally:
        repo.close()


def test_distillation_contract_revision_participates_in_idempotency_hash(monkeypatch):
    baseline = GrowthDistillationService._input_hash([], "2026-07-24T09:00:00+00:00", "context")
    monkeypatch.setattr(
        GrowthDistillationService,
        "DISTILLATION_CONTRACT_REVISION",
        GrowthDistillationService.DISTILLATION_CONTRACT_REVISION + 1,
    )

    revised = GrowthDistillationService._input_hash([], "2026-07-24T09:00:00+00:00", "context")

    assert revised != baseline


def test_weekly_distillation_interprets_legacy_naive_repository_timestamps_as_shanghai_time(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-naive-timezone.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="article",
            content_hash="a" * 64,
            raw_content="A captured source must remain available to the weekly review.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        ))
        # Older repository writes use local wall-clock timestamps with no
        # offset. At 00:24Z it was already 08:24 in the schedule timezone.
        repo._execute(
            "UPDATE knowledge_sources SET captured_at=?, updated_at=? WHERE project_id=? AND id=?",
            ("2026-07-24T07:13:19", "2026-07-24T07:13:19", "project-a", "source-a"),
        )
        repo._commit()

        result = GrowthDistillationService(repo, root).run_weekly(
            "project-a", "2026-W30", source_cutoff="2026-07-24T00:24:18.951698Z"
        )

        assert result["manifest"]["context"]["citation_source_ids"] == ["source-a"]
        assert {item["id"] for item in result["manifest"]["inputs"]} >= {"source-a"}
    finally:
        repo.close()


def test_tampered_managed_file_is_never_archived_or_overwritten(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-tamper.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        managed = weekly_root / service.WEEKLY_DOCUMENTS[0]
        managed.write_text("user edited the managed report", encoding="utf-8")

        with pytest.raises(ManagedContentConflictError, match="hash conflict"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")

        assert managed.read_text(encoding="utf-8") == "user edited the managed report"
        assert not (weekly_root / "revisions" / first["input_hash"]).exists()
    finally:
        repo.close()


def test_tampered_manifest_is_rejected_even_when_documents_are_unchanged(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-manifest-tamper.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        manifest_path = weekly_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["inputs"] = [{"type": "source", "id": "forged"}]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ManagedContentConflictError, match="persisted manifest"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
    finally:
        repo.close()


def test_weekly_publish_restores_original_directory_when_final_swap_fails(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-atomic.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        user_file = weekly_root / "user-note.md"
        user_file.write_text("preserve through rollback", encoding="utf-8")
        original_manifest = (weekly_root / "manifest.json").read_bytes()
        real_replace = os.replace

        def fail_final_swap(source, destination):
            if str(source).endswith(".tmp") and os.fspath(destination) == os.fspath(weekly_root):
                raise OSError("simulated final directory swap failure")
            return real_replace(source, destination)

        monkeypatch.setattr("app.knowledge.growth_distillation.os.replace", fail_final_swap)
        with pytest.raises(OSError, match="simulated final"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")

        assert (weekly_root / "manifest.json").read_bytes() == original_manifest
        assert user_file.read_text(encoding="utf-8") == "preserve through rollback"
        assert repo.get_growth_distillation("project-a", "weekly", "2026-W30", first["input_hash"])
    finally:
        repo.close()


def test_daily_revisions_are_owned_redacted_and_user_file_is_protected(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-owned.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        secret = "sk-" + "d" * 32
        repo.register_output(OutputAsset(
            id="secret-output", project_id="project-a", kind="report", content_hash="d" * 64,
            vault_path="outputs/secret/report.md", idempotency_key="secret-output", status="accepted",
            quality={"token": secret, "quality": 90},
        ))
        service = GrowthDistillationService(repo, root)
        first = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        second = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T10:00:00Z")
        daily = root / "projects" / "project-a" / second["paths"][0]
        archive = daily.parent / "revisions" / "2026-07-22" / f"{first['input_hash']}.md"
        assert archive.exists()
        assert "bsc-growth-distillation/v1" in daily.read_text(encoding="utf-8")
        assert secret not in daily.read_text(encoding="utf-8")
        assert secret not in json.dumps(second["manifest"], ensure_ascii=False)

        other_date = daily.with_name("2026-07-23.md")
        other_date.write_text("user-authored daily note", encoding="utf-8")
        with pytest.raises(ManagedContentConflictError, match="unmarked user-authored"):
            service.run_daily("project-a", "2026-07-23", source_cutoff="2026-07-23T09:00:00Z")
        assert other_date.read_text(encoding="utf-8") == "user-authored daily note"
    finally:
        repo.close()


def test_daily_body_hash_protects_user_edits_after_filesystem_publish_before_db_commit(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-crash-window.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        daily = root / "projects" / "project-a" / first["paths"][0]
        edited = daily.read_text(encoding="utf-8") + "\nUser correction after publish.\n"
        daily.write_text(edited, encoding="utf-8")
        repo._execute("DELETE FROM knowledge_growth_distillations WHERE id=?", (first["id"],))
        repo._commit()

        with pytest.raises(ManagedContentConflictError, match="body hash conflict"):
            service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T10:00:00Z")
        assert daily.read_text(encoding="utf-8") == edited
    finally:
        repo.close()


def test_next_day_daily_digest_compares_with_previous_day_instead_of_readding_history(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "daily-incremental.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.register_output(OutputAsset(
            id="stable-output", project_id="project-a", kind="report", content_hash="e" * 64,
            vault_path="outputs/stable.md", idempotency_key="stable-output", status="accepted",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ))
        service = GrowthDistillationService(repo, root)
        service.run_daily("project-a", "2026-07-22", source_cutoff="2026-07-22T09:00:00Z")
        second = service.run_daily("project-a", "2026-07-23", source_cutoff="2026-07-23T09:00:00Z")
        daily = root / "projects" / "project-a" / second["paths"][0]
        content = daily.read_text(encoding="utf-8")
        assert "Added: `0`; changed: `0`; removed: `0`" in content
    finally:
        repo.close()


def test_weekly_manifest_covers_feedback_evaluations_contradictions_and_cutoff(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "weekly-complete-input.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        for source_id in ("source-a", "source-b"):
            repo.create_source(SourceRecord(
                id=source_id,
                project_id="project-a",
                source_type="manual_upload",
                content_hash=hashlib.sha256(source_id.encode()).hexdigest(),
                raw_content=f"Evidence from {source_id}",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
                captured_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
                updated_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
            ))
        repo.create_source(SourceRecord(
            id="future-source",
            project_id="project-a",
            source_type="manual_upload",
            content_hash="f" * 64,
            raw_content="This arrived after the immutable cutoff.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
            captured_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
        ))
        repo.register_output(OutputAsset(
            id="output-a", project_id="project-a", kind="report", content_hash="a" * 64,
            vault_path="outputs/output-a.md", idempotency_key="output-a", status="accepted",
            source_refs=["source-a"],
            created_at=_CUTOFF_SAFE_TIME, updated_at=_CUTOFF_SAFE_TIME,
        ))
        repo.save_output_evaluation(OutputEvaluation(
            id="eval-a", project_id="project-a", output_id="output-a",
            groundedness=0.9, task_fit=0.9, usefulness=0.9, coherence=0.9, format_quality=0.9,
            findings=["retain exact source references"],
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))
        repo.add_output_feedback(OutputFeedback(
            id="feedback-a", project_id="project-a", output_id="output-a",
            feedback_type=FeedbackType.CORRECTED, correction="Clarify the approval owner.",
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))
        # Saving an evaluation updates the output lifecycle timestamp. Model
        # this complete historical record as having existed before the cutoff.
        repo._execute(
            "UPDATE knowledge_outputs SET updated_at=? WHERE project_id=? AND id=?",
            (_CUTOFF_SAFE_TIME.isoformat(), "project-a", "output-a"),
        )
        repo._commit()
        repo.add_lineage_edge(KnowledgeLineageEdge(
            id="contradiction-a", project_id="project-a",
            from_type="source", from_id="source-a", to_type="source", to_id="source-b",
            relation="source_contradicts_source",
            created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        ))

        service = GrowthDistillationService(repo, root)
        result = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")
        manifest = result["manifest"]
        input_types = {item["type"] for item in manifest["inputs"]}
        input_ids = {item["id"] for item in manifest["inputs"]}
        assert {"source", "output", "evaluation", "feedback", "lineage"} <= input_types
        assert "future-source" not in input_ids
        assert manifest["source_cutoff"] == "2026-07-24T09:00:00+00:00"

        weekly_root = root / "projects" / "project-a" / "distillations" / service.WEEKLY_DIRECTORY / "2026-W30"
        summary = (weekly_root / "00-本周总结.md").read_text(encoding="utf-8")
        methods = (weekly_root / "04-方法迭代.md").read_text(encoding="utf-8")
        assert "Contradictions requiring review: `1`" in summary
        assert "feedback-a" in methods
        assert "eval-a" in methods
    finally:
        repo.close()


def test_changed_weekly_input_preserves_previous_managed_revision_and_user_file(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-revision.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        service = GrowthDistillationService(repo, root)
        first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T09:00:00Z")
        weekly_root = root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        (weekly_root / "user-note.md").write_text("keep me", encoding="utf-8")
        second = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-22T10:00:00Z")
        assert second["input_hash"] != first["input_hash"]
        assert (weekly_root / "revisions" / first["input_hash"] / "manifest.json").exists()
        assert (weekly_root / "user-note.md").read_text(encoding="utf-8") == "keep me"
    finally:
        repo.close()


def test_weekly_context_uses_published_b_page_without_duplicating_rules_or_audit_log(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "distillation-context-pages.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        project_root = root / "projects" / "project-a"
        project_root.mkdir(parents=True)
        (project_root / "AGENTS.md").write_text(build_default_agents_rules("project-a"), encoding="utf-8")
        source = SourceRecord(
            id="source-a",
            project_id="project-a",
            source_type="manual_upload",
            content_hash="a" * 64,
            raw_content="The ABCD loop requires immutable evidence.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        )
        repo.create_source(source)
        repo.record_publication(
            project_id="project-a",
            contents={
                "AGENTS.md": build_default_agents_rules("project-a"),
                "wiki/index.md": "# Index\n- [[wiki/concepts/loop.md]]\n",
                "wiki/log.md": "# Log\n- Publication event\n",
                "wiki/concepts/loop.md": (
                    "---\ntitle: ABCD loop\nkind: concept\n---\n"
                    "ABCD governs knowledge growth. [source:source-a]\n"
                ),
            },
            source_ids=["source-a"],
        )

        result = GrowthDistillationService(repo, root).run_weekly(
            "project-a", "2026-W30", source_cutoff="2100-01-01T00:00:00Z"
        )
        context = result["manifest"]["context"]
        page_by_path = {page["path"]: page["id"] for page in repo.list_pages("project-a")}

        assert page_by_path["wiki/concepts/loop.md"] in context["page_ids"]
        assert page_by_path["AGENTS.md"] not in context["page_ids"]
        assert page_by_path["wiki/log.md"] not in context["page_ids"]
    finally:
        repo.close()
