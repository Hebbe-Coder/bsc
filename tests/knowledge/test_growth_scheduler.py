from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.growth_scheduler import GrowthScheduleCoordinator
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.tasks.knowledge_tasks import execute_knowledge_run


def test_growth_schedules_are_timezone_correct_and_project_scoped(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-schedule.db"))
    repo.configure_vault("project-a", "projects/project-a")
    scheduler = KnowledgeScheduler(repo, scheduler_available=True)
    try:
        now = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)
        daily = scheduler.configure(
            project_id="project-a",
            job_type="growth_daily",
            cron="0 17 * * *",
            timezone_name="Asia/Shanghai",
            now=now,
        )
        weekly = scheduler.configure(
            project_id="project-a",
            job_type="growth_weekly_distillation",
            cron="30 17 * * 5",
            timezone_name="Asia/Shanghai",
            now=now,
        )

        assert daily["next_run_at"] == "2026-07-23T09:00:00+00:00"
        assert weekly["next_run_at"] == "2026-07-24T09:30:00+00:00"
        assert scheduler.list_schedules("project-b") == []
    finally:
        repo.close()


def test_growth_coordinator_installs_defaults_and_supports_pause_resume(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-defaults.db"))
    repo.configure_vault("project-a", "projects/project-a")
    coordinator = GrowthScheduleCoordinator(repo, scheduler_available=True)
    now = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)
    try:
        schedules = coordinator.ensure_defaults("project-a", now=now)
        assert [(item["job_type"], item["cron"], item["timezone"]) for item in schedules] == [
            ("growth_daily", "0 17 * * *", "Asia/Shanghai"),
            ("growth_weekly_distillation", "30 17 * * 5", "Asia/Shanghai"),
        ]
        paused = coordinator.pause("project-a", schedules[0]["id"])
        assert paused["enabled"] == 0
        resumed = coordinator.resume("project-a", schedules[0]["id"], now=now)
        assert resumed["enabled"] == 1
        assert resumed["next_run_at"] == "2026-07-23T09:00:00+00:00"
    finally:
        repo.close()


def test_default_reconciliation_disables_preexisting_intent_without_durable_scheduler(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-default-unavailable.db"))
    repo.configure_vault("project-a", "projects/project-a")
    available = GrowthScheduleCoordinator(repo, scheduler_available=True)
    try:
        available.ensure_defaults("project-a", now=datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc))
        disabled = GrowthScheduleCoordinator(repo, scheduler_available=False).ensure_defaults(
            "project-a", now=datetime(2026, 7, 23, 8, 1, tzinfo=timezone.utc)
        )
        assert all(item["enabled"] == 0 and item["next_run_at"] == "" for item in disabled)
    finally:
        repo.close()


def test_weekly_claim_waits_for_same_day_daily_and_uses_separate_idempotency(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-ordering.db"))
    repo.configure_vault("project-a", "projects/project-a")
    coordinator = GrowthScheduleCoordinator(repo, scheduler_available=True)
    due = datetime(2026, 7, 24, 9, 30, tzinfo=timezone.utc)
    try:
        weekly = coordinator.ensure_defaults("project-a", now=due - timedelta(days=1))[1]
        waiting = coordinator.claim_scheduled_run(weekly, due_at=due)
        assert waiting == {"claimed": False, "status": "waiting_for_daily", "run_id": ""}

        daily = KnowledgeRun(
            id="daily-ready",
            project_id="project-a",
            run_type="growth_daily",
            trigger="schedule",
            input_refs={"date": "2026-07-24", "source_cutoff": "2026-07-24T09:00:00+00:00"},
        )
        repo.create_run(daily)
        repo.update_run_status(
            "project-a", daily.id, RunStatus.COMPLETED,
            output_refs={"growth": {"period": "2026-07-24", "input_hash": "a" * 64}},
        )
        claim = coordinator.claim_scheduled_run(weekly, due_at=due)
        assert claim["claimed"] is True
        persisted = repo.get_run("project-a", claim["run_id"])
        assert persisted["input_refs"]["week"] == "2026-W30"
        assert "growth_weekly_distillation" in persisted["input_refs"]["idempotency_key"]
        assert "daily-ready" in persisted["input_refs"]["daily_run_id"]
    finally:
        repo.close()


def test_manual_growth_request_is_idempotent_and_scheduler_unavailability_is_truthful(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-manual.db"))
    repo.configure_vault("project-a", "projects/project-a")
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    try:
        coordinator = GrowthScheduleCoordinator(repo, scheduler_available=True)
        first = coordinator.run_now("project-a", "growth_daily", request_id="request-1", now=now)
        duplicate = coordinator.run_now("project-a", "growth_daily", request_id="request-1", now=now)
        assert first["status"] == "queued"
        assert duplicate == {"status": "duplicate", "run_id": first["run_id"]}
        assert repo.get_run("project-a", first["run_id"])["input_refs"]["date"] == "2026-07-24"

        unavailable = GrowthScheduleCoordinator(repo, scheduler_available=False).run_now(
            "project-a", "growth_weekly_distillation", request_id="request-2", now=now
        )
        assert unavailable["status"] == "unavailable"
        assert repo.get_run("project-a", unavailable["run_id"])["status"] == "unavailable"
    finally:
        repo.close()


def test_growth_distillation_task_writes_daily_artifact_and_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "growth-task.db"))
    repo.configure_vault("project-a", "projects/project-a")
    run = KnowledgeRun(
        project_id="project-a",
        run_type="growth_daily",
        trigger="manual",
        input_refs={"date": "2026-07-23", "source_cutoff": "2026-07-23T09:00:00Z"},
    )
    repo.create_run(run)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(root))
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", False)
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)
        assert result["status"] == "completed"
        artifact = root / "projects" / "project-a" / result["growth"]["paths"][0]
        assert artifact.exists()
        assert repo.get_run("project-a", run.id)["status"] == "completed"

        repeated = execute_knowledge_run("project-a", run.id, repository=repo)
        assert repeated["duplicate"] is True
    finally:
        repo.close()


def test_growth_task_reports_unavailable_without_vault(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-unavailable.db"))
    run = KnowledgeRun(project_id="project-a", run_type="growth_weekly_distillation", trigger="manual")
    repo.create_run(run)
    monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", "")
    try:
        result = execute_knowledge_run("project-a", run.id, repository=repo)
        assert result["status"] == "unavailable"
        assert result["failure"]["code"] == "vault_not_configured"
    finally:
        repo.close()
