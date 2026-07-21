from datetime import datetime, timezone

import pytest

from app.knowledge.scheduler import KnowledgeScheduler, ScheduleValidationError
from app.knowledge.wiki_repository import WikiRepository


def test_scheduler_persists_safe_schedule_and_calculates_next_run(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "scheduler.db"))
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
    try:
        with pytest.raises(ScheduleValidationError, match="cron"):
            KnowledgeScheduler(repo, scheduler_available=True).configure(
                project_id="project-a", job_type="weekly_distillation", cron="0 0 1 * *"
            )

        result = KnowledgeScheduler(repo, scheduler_available=False).run_now(
            project_id="project-a", job_type="weekly_distillation", trigger="manual"
        )
        assert result["status"] == "unavailable"
        assert repo.get_run("project-a", result["run_id"])["status"] == "unavailable"
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
