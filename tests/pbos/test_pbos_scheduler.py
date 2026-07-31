from datetime import date, datetime, timezone

from app.api import dbos_api
from app.core.config import settings
from app.knowledge.wiki_contracts import KnowledgeRun
from app.knowledge.wiki_repository import WikiRepository
from app.pbos.scheduler import PBOSScheduleCoordinator
from app.tasks import pbos_tasks
from app.tasks import knowledge_tasks
from app.tasks.knowledge_tasks import execute_knowledge_run


def test_pbos_default_schedules_use_shanghai_cadence_and_month_boundary(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "pbos-schedules.db"))
    repository.configure_vault("project-a", "projects/project-a")
    coordinator = PBOSScheduleCoordinator(repository, scheduler_available=True)
    now = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)
    try:
        schedules = coordinator.ensure_defaults("project-a", now=now)

        assert [(item["job_type"], item["cron"], item["timezone"]) for item in schedules] == [
            ("pbos_daily", "0 17 * * *", "Asia/Shanghai"),
            ("pbos_weekly", "0 17 * * 5", "Asia/Shanghai"),
            ("pbos_monthly", "0 17 1 * *", "Asia/Shanghai"),
        ]
        assert schedules[0]["next_run_at"] == "2026-07-23T09:00:00+00:00"
        assert schedules[1]["next_run_at"] == "2026-07-24T09:00:00+00:00"
        assert schedules[2]["next_run_at"] == "2026-08-01T09:00:00+00:00"
    finally:
        repository.close()


def test_pbos_default_schedules_migrate_the_legacy_weekly_half_hour_cron(tmp_path):
    repository = WikiRepository(db_path=str(tmp_path / "pbos-legacy-schedules.db"))
    repository.configure_vault("project-a", "projects/project-a")
    repository.upsert_schedule(
        project_id="project-a",
        job_type="pbos_weekly",
        cron="30 17 * * 5",
        timezone_name="Asia/Shanghai",
        enabled=True,
        next_run_at="2026-07-24T09:30:00+00:00",
    )
    coordinator = PBOSScheduleCoordinator(repository, scheduler_available=True)
    try:
        schedules = coordinator.ensure_defaults(
            "project-a", now=datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)
        )
        weekly = next(item for item in schedules if item["job_type"] == "pbos_weekly")

        assert weekly["cron"] == "0 17 * * 5"
        assert weekly["next_run_at"] == "2026-07-24T09:00:00+00:00"
    finally:
        repository.close()


def test_pbos_scheduled_weekly_run_writes_auditable_vault_report_once(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    repository = WikiRepository(db_path=str(tmp_path / "pbos-run.db"))
    repository.configure_vault("project-a", "projects/project-a")
    run = KnowledgeRun(
        project_id="project-a",
        run_type="pbos_weekly",
        trigger="schedule",
        input_refs={"week": "2026-W31", "period": "2026-W31"},
    )
    repository.create_run(run)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr(settings, "DYNAMIC_BUSINESS_OS_ENABLED", True)
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repository)

        assert result["status"] == "completed"
        assert result["pbos"]["report"]["state"] == "written"
        report = project_root / "distillations" / "每周蒸馏" / "2026-W31" / "pbos" / "personal-growth.md"
        assert report.exists()
        persisted = repository.get_run("project-a", run.id)
        assert persisted["status"] == "completed"
        assert persisted["output_refs"]["pbos"]["report"]["path"] == report.relative_to(project_root).as_posix()

        repeated = execute_knowledge_run("project-a", run.id, repository=repository)
        assert repeated["duplicate"] is True
    finally:
        repository.close()


def test_due_pbos_schedule_claims_and_dispatches_through_the_knowledge_queue(tmp_path, monkeypatch):
    repository = WikiRepository(db_path=str(tmp_path / "pbos-dispatch.db"))
    repository.configure_vault("project-a", "projects/project-a")
    coordinator = PBOSScheduleCoordinator(repository, scheduler_available=True)
    before_due = datetime(2026, 7, 23, 8, 30, tzinfo=timezone.utc)
    coordinator.ensure_defaults("project-a", now=before_due)
    dispatched: list[list[str]] = []
    monkeypatch.setattr(settings, "KNOWLEDGE_SCHEDULES_ENABLED", True)
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)
    monkeypatch.setattr(knowledge_tasks, "WikiRepository", lambda: repository)
    monkeypatch.setattr(knowledge_tasks, "is_celery_real", lambda: True)
    monkeypatch.setattr(knowledge_tasks, "_submit_task", lambda _task, args: dispatched.append(args))
    monkeypatch.setattr(repository, "close", lambda: None)
    due = datetime(2026, 7, 24, 9, 1, tzinfo=timezone.utc)
    try:
        result = knowledge_tasks.reconcile_knowledge_schedules(now=due)

        assert result["queued"] == 2
        assert len(dispatched) == 2
        runs = [item for item in repository.list_runs("project-a") if item["run_type"].startswith("pbos_")]
        assert {item["run_type"] for item in runs} == {"pbos_daily", "pbos_weekly"}
        weekly = next(item for item in runs if item["run_type"] == "pbos_weekly")
        assert weekly["input_refs"]["week"] == "2026-W30"
        assert weekly["input_refs"]["scheduled_at"] == "2026-07-24T09:00:00+00:00"
        assert any(
            event["event_type"] == "knowledge.run.execution_dispatched"
            for event in repository.list_run_events(project_id="project-a", run_id=weekly["id"])
        )
    finally:
        repository.close()


def test_direct_pbos_tasks_keep_daily_and_monthly_reports_out_of_weekly_distillation(tmp_path, monkeypatch):
    class FrozenDate:
        @classmethod
        def today(cls):
            return date(2026, 7, 30)

    root = tmp_path / "vault"
    project_root = root / "projects" / "project-a"
    project_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr(dbos_api, "DBOS_DATA_ROOT", tmp_path / "dbos")
    monkeypatch.setattr(pbos_tasks, "date", FrozenDate)

    daily = pbos_tasks.pbos_daily_review_task.run("project-a")
    monthly = pbos_tasks.pbos_monthly_review_task.run("project-a")

    assert daily == {
        "state": "written",
        "path": "pbos/reviews/daily/2026-07-30/daily-action.md",
    }
    assert monthly == {
        "state": "written",
        "path": "pbos/reviews/monthly/2026-07/capability-report.md",
    }
    assert not (project_root / "distillations" / "每周蒸馏" / "daily-2026-07-30").exists()
