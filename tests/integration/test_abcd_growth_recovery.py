"""Idempotency, revision preservation and durable restart proof for growth jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import pytest

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_distillation import GrowthDistillationService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceRecord, SourceStatus


_CUTOFF_SAFE_TIME = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _register_output(repo: GrowthRepository, output_id: str, status: str = "accepted") -> dict:
    return repo.register_output(
        OutputAsset(
            id=output_id,
            project_id="project-a",
            kind="report",
            title=output_id,
            content_hash=hashlib.sha256(output_id.encode()).hexdigest(),
            vault_path=f"outputs/2026/{output_id}/report.md",
            idempotency_key=output_id,
            status=status,
            quality={"quality": 91 if status == "accepted" else 42},
            metadata={"task_family": "weekly-review"},
            created_at=_CUTOFF_SAFE_TIME,
            updated_at=_CUTOFF_SAFE_TIME,
        )
    )


def test_daily_and_weekly_are_idempotent_archive_revisions_and_exclude_distillations(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-recovery.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "admin")
        _register_output(repo, "accepted-output")
        repo.create_source(
            SourceRecord(
                id="recursive-source",
                project_id="project-a",
                source_type="obsidian_import",
                content_hash="d" * 64,
                raw_content="A generated weekly file must not feed itself.",
                vault_path="distillations/weekly/2026-W30/00-summary.md",
                trust_level="trusted",
                status=SourceStatus.ELIGIBLE,
            )
        )
        service = GrowthDistillationService(repo, vault_root)

        daily_first = service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        daily_second = service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        assert daily_first["status"] == "generated"
        assert daily_second["status"] == "noop"
        assert daily_first["id"] == daily_second["id"]
        assert all(item["id"] != "recursive-source" for item in daily_first["manifest"]["inputs"])

        weekly_first = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")
        weekly_second = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")
        assert weekly_second["status"] == "noop"
        assert weekly_first["input_hash"] == weekly_second["input_hash"]
        assert weekly_first["manifest"]["input_count"] == 1
        assert all(item["id"] != "recursive-source" for item in weekly_first["manifest"]["inputs"])

        weekly_root = vault_root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        assert (weekly_root / "每日增量" / "2026-07-24.md").exists()
        user_file = weekly_root / "user-observation.md"
        user_file.write_text("This is owned by the user.", encoding="utf-8")
        changed = service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T10:00:00Z")
        assert changed["input_hash"] != weekly_first["input_hash"]
        assert user_file.read_text(encoding="utf-8") == "This is owned by the user."
        archived_manifest = weekly_root / "revisions" / weekly_first["input_hash"] / "manifest.json"
        assert archived_manifest.exists()
        manifest = json.loads((weekly_root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["input_hash"] == changed["input_hash"]
        assert len(manifest["paths"]) == 5
    finally:
        repo.close()


def test_weekly_allows_managed_daily_directory_but_refuses_unmarked_managed_file(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-managed-conflict.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "admin")
        service = GrowthDistillationService(repo, vault_root)
        service.run_daily("project-a", "2026-07-24", source_cutoff="2026-07-24T09:00:00Z")
        weekly_root = vault_root / "projects" / "project-a" / "distillations" / "每周蒸馏" / "2026-W30"
        conflict = weekly_root / "00-本周总结.md"
        conflict.write_text("user-owned summary", encoding="utf-8")

        with pytest.raises(ValueError, match="unmarked user-authored file"):
            service.run_weekly("project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z")

        assert conflict.read_text(encoding="utf-8") == "user-owned summary"
        assert (weekly_root / "每日增量" / "2026-07-24.md").exists()
        assert not (weekly_root / "manifest.json").exists()
    finally:
        repo.close()


def test_restart_preserves_growth_assets_runs_events_schedules_and_distillation(tmp_path):
    database = str(tmp_path / "restart-growth.db")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    first = GrowthRepository(db_path=database)
    first.configure_vault("project-a", "projects/project-a", "admin")
    output = _register_output(first, "restart-output")
    distillation = GrowthDistillationService(first, vault_root).run_weekly(
        "project-a", "2026-W30", source_cutoff="2026-07-24T09:00:00Z"
    )
    run = KnowledgeRun(project_id="project-a", run_type="growth_weekly_distillation", trigger="manual")
    first.create_run(run)
    first.update_run_status(
        "project-a",
        run.id,
        RunStatus.COMPLETED,
        output_refs={"distillation_id": distillation["id"], "output_id": output["id"]},
    )
    schedule = KnowledgeScheduler(first, scheduler_available=True).configure(
        project_id="project-a",
        job_type="growth_weekly_distillation",
        cron="30 17 * * 5",
        timezone_name="Asia/Shanghai",
        now=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    first.close()

    restarted = GrowthRepository(db_path=database)
    try:
        assert restarted.get_output("project-a", output["id"])["content_hash"] == output["content_hash"]
        assert restarted.get_growth_distillation(
            "project-a", "weekly", "2026-W30", distillation["input_hash"]
        )["id"] == distillation["id"]
        assert restarted.get_run("project-a", run.id)["status"] == "completed"
        assert [event["sequence"] for event in restarted.list_run_events(project_id="project-a", run_id=run.id)] == [1, 2]
        assert restarted.get_schedule("project-a", schedule["id"])["timezone"] == "Asia/Shanghai"
    finally:
        restarted.close()


def test_abandoned_run_is_failed_before_retry_and_scheduler_unavailability_is_truthful(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "abandoned.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "admin")
        run = KnowledgeRun(
            project_id="project-a",
            run_type="growth_daily",
            trigger="schedule",
            status=RunStatus.RUNNING,
        )
        repo.create_run(run)
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        repo._execute(
            "UPDATE knowledge_runs SET status='running',started_at=?,updated_at=? WHERE project_id=? AND id=?",
            (stale, stale, "project-a", run.id),
        )
        repo._commit()

        scheduler = KnowledgeScheduler(repo, scheduler_available=True)
        assert scheduler.recover_abandoned_runs(timeout_seconds=3600) == [run.id]
        recovered = repo.get_run("project-a", run.id)
        assert recovered["status"] == "failed"
        assert recovered["output_refs"]["failure"]["code"] == "abandoned_run"
        assert recovered["output_refs"]["failure"]["retryable"] is True

        unavailable = KnowledgeScheduler(repo, scheduler_available=False).run_now(
            project_id="project-a",
            job_type="growth_daily",
            trigger="manual",
        )
        assert unavailable["status"] == "unavailable"
        assert repo.get_run("project-a", unavailable["run_id"])["status"] == "unavailable"
    finally:
        repo.close()
