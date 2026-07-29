from datetime import datetime, timezone

import pytest

from app.knowledge.scheduler import KnowledgeScheduler, ScheduleValidationError
from app.knowledge.wiki_repository import WikiRepository


def test_scheduler_persists_safe_schedule_and_calculates_next_run(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler.db"))
    repo.configure_vault("project-a", "projects/project-a")
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    now = datetime(2026, 7, 21, 9, 7, tzinfo=timezone.utc)
    try:
        schedule = scheduler.configure(
            project_id="project-a", job_type="weekly_distillation", cron="*/15 * * * *",
            now=now,
        )

        assert schedule["enabled"] == 1
        assert schedule["next_run_at"] == "2026-07-21T09:15:00+00:00"
        assert scheduler.list_schedules("project-b") == []
    finally:
        repo.close()


def test_scheduler_rejects_unsafe_cron_and_truthfully_records_unavailable_run(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler-unavailable.db"))
    repo.configure_vault("project-a", "projects/project-a")
    try:
        with pytest.raises(ScheduleValidationError, match="cron"):
            KnowledgeScheduler(repo, scheduler_available=True).configure(
                project_id="project-a", job_type="weekly_distillation", cron="0 0 1,15 * *"
            )

        result = KnowledgeScheduler(repo, scheduler_available=False).run_now(
            project_id="project-a", job_type="weekly_distillation", trigger="manual"
        )
        assert result["status"] == "unavailable"
        assert repo.get_run("project-a", result["run_id"])["status"] == "unavailable"
    finally:
        repo.close()


def test_scheduler_supports_monthly_runs_and_skips_short_months(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler-monthly.db"))
    repo.configure_vault("project-a", "projects/project-a")
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    try:
        schedule = scheduler.configure(
            project_id="project-a",
            job_type="pbos_monthly",
            cron="0 17 1 * *",
            timezone_name="Asia/Shanghai",
            now=datetime(2026, 7, 21, 9, 7, tzinfo=timezone.utc),
        )
        assert schedule["next_run_at"] == "2026-08-01T09:00:00+00:00"
        assert KnowledgeScheduler.next_run(
            "0 17 31 * *",
            datetime(2026, 2, 15, 0, 0, tzinfo=timezone.utc),
            timezone_name="Asia/Shanghai",
        ) == datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)
    finally:
        repo.close()


def test_scheduler_claims_one_idempotent_run(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler-claim.db"))
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    try:
        first = scheduler.claim_run(project_id="project-a", job_type="wiki_maintenance", idempotency_key="same-input")
        duplicate = scheduler.claim_run(project_id="project-a", job_type="wiki_maintenance", idempotency_key="same-input")

        assert first["claimed"] is True
        assert duplicate == {"claimed": False, "run_id": first["run_id"]}
    finally:
        repo.close()


def test_scheduler_validates_timezone_and_requires_project_vault(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler-policy.db"))
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    try:
        with pytest.raises(ScheduleValidationError, match="Vault"):
            scheduler.configure(project_id="project-a", job_type="source_sync", cron="*/15 * * * *")
        repo.configure_vault("project-a", "projects/project-a")
        with pytest.raises(ScheduleValidationError, match="timezone"):
            scheduler.configure(
                project_id="project-a", job_type="source_sync", cron="*/15 * * * *", timezone_name="Mars/Olympus"
            )

        schedule = scheduler.configure(
            project_id="project-a",
            job_type="weekly_distillation",
            cron="0 8 * * 1",
            timezone_name="Asia/Shanghai",
            now=datetime(2026, 7, 20, 0, 30, tzinfo=timezone.utc),
        )
        assert schedule["next_run_at"] == "2026-07-27T00:00:00+00:00"
    finally:
        repo.close()


def test_scheduler_marks_only_abandoned_running_jobs_failed(tmp_path):
    from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus

    repo = WikiRepository(db_path=str(tmp_path / "scheduler-recovery.db"))
    stale = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="schedule", status=RunStatus.RUNNING)
    recent = KnowledgeRun(project_id="project-a", run_type="source_sync", trigger="manual", status=RunStatus.RUNNING)
    repo.create_run(stale)
    repo.create_run(recent)
    repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", ("2026-07-20T00:00:00+00:00", stale.id))
    repo._execute("UPDATE knowledge_runs SET updated_at=? WHERE id=?", ("2026-07-22T09:59:30+00:00", recent.id))
    repo._commit()
    try:
        recovered = KnowledgeScheduler(repo, scheduler_available=True).recover_abandoned_runs(
            now=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc), timeout_seconds=3600
        )

        assert recovered == [stale.id]
        assert repo.get_run("project-a", stale.id)["status"] == "failed"
        assert repo.get_run("project-a", stale.id)["output_refs"]["failure"]["code"] == "abandoned_run"
        assert repo.get_run("project-a", recent.id)["status"] == "running"
    finally:
        repo.close()
