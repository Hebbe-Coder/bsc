"""Auditable weekly-distillation recovery and idempotency integration coverage."""

from __future__ import annotations

from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.tasks.knowledge_tasks import execute_knowledge_run


def test_weekly_distillation_retries_after_evidence_arrives_and_reuses_cutoff(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("project rules", encoding="utf-8")
    repository = WikiRepository(db_path=str(tmp_path / "knowledge-weekly.db"))
    repository.configure_vault("project-a", "projects/project-a")
    unavailable = KnowledgeRun(project_id="project-a", run_type="weekly_distillation", trigger="manual")
    repository.create_run(unavailable)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.knowledge.wiki_commands.is_celery_real", lambda: False)
    try:
        first = execute_knowledge_run("project-a", unavailable.id, week="2026-W30", repository=repository)
        assert first["status"] == "unavailable"

        source = SourceCaptureService(repository).capture(
            CapturedSourceInput(
                project_id="project-a",
                source_type="manual_upload",
                origin="brief.md",
                raw_content="# Review evidence\nA human approval is required.",
                trust_level="trusted",
            )
        ).source
        retry = WikiCommandService(repository).retry_run(project_id="project-a", run_id=unavailable.id)
        retried_run = repository.get_run("project-a", retry["run_id"])
        assert retry["status"] == "completed"
        assert retried_run["retry_of"] == unavailable.id
        assert retried_run["output_refs"]["source_cutoff"] == retry["source_cutoff"]

        repeated = KnowledgeRun(project_id="project-a", run_type="weekly_distillation", trigger="manual")
        repository.create_run(repeated)
        repeated_result = execute_knowledge_run("project-a", repeated.id, week="2026-W30", repository=repository)
        records = repository.list_distillations("project-a")
        assert repeated_result["source_cutoff"] == retry["source_cutoff"]
        assert len(records) == 1
        assert records[0]["source_cutoff"] == retry["source_cutoff"]

        action = (project_root / "distillations" / "2026-W30" / "knowledge-action.md").read_text(encoding="utf-8")
        context = (project_root / "distillations" / "2026-W30" / "context-pack.md").read_text(encoding="utf-8")
        assert source["id"] in action
        assert retry["source_cutoff"] in action
        assert retry["source_cutoff"] in context
        events = repository.list_run_events(project_id="project-a", run_id=retry["run_id"])
        assert any(event["event_type"] == "knowledge.distillation.completed" for event in events)
    finally:
        repository.close()


def test_source_sync_extracts_new_vault_assets_once_and_records_auditable_summary(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    source = project_root / "01_Sources" / "metrics.csv"
    source.parent.mkdir(parents=True)
    source.write_text("month,revenue_usd\n2026-06,120\n2026-07,180\n", encoding="utf-8")
    repository = WikiRepository(db_path=str(tmp_path / "knowledge-source-sync.db"))
    repository.configure_vault("project-a", "projects/project-a")
    first_run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
    repository.create_run(first_run)
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr("app.tasks.knowledge_tasks.settings.KNOWLEDGE_OBSIDIAN_SYNC_ENABLED", True)
    try:
        first = execute_knowledge_run("project-a", first_run.id, repository=repository)

        assert first["status"] == "completed"
        assert first["sync"]["multimodal_extraction"] == {
            "attempted": 1,
            "complete": 1,
            "partial": 0,
            "needs_review": 0,
            "unavailable": 0,
            "restricted": 0,
            "skipped_existing": 0,
        }
        captured = repository.list_sources("project-a")
        assert len(captured) == 1
        asset = repository.list_media_assets("project-a", source_id=captured[0]["id"])[0]
        extraction = repository.list_extraction_artifacts("project-a", source_id=captured[0]["id"])[0]
        assert extraction["asset_id"] == asset["id"]
        assert extraction["status"] == "complete"
        assert repository.list_table_artifacts("project-a", extraction_id=extraction["id"])[0]["row_count"] == 2

        repeat_run = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual")
        repository.create_run(repeat_run)
        repeated = execute_knowledge_run("project-a", repeat_run.id, repository=repository)
        assert repeated["status"] == "completed"
        assert repeated["sync"]["multimodal_extraction"]["attempted"] == 0
        assert repeated["sync"]["multimodal_extraction"]["skipped_existing"] == 1
        assert len(repository.list_extraction_artifacts("project-a", source_id=captured[0]["id"])) == 1
        events = repository.list_run_events(project_id="project-a", run_id=first_run.id)
        assert any(event["event_type"] == "knowledge.source.sync.completed" for event in events)
    finally:
        repository.close()
