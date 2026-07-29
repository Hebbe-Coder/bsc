"""PBOS schedules on the existing durable knowledge scheduler."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository


class PBOSScheduleCoordinator:
    TIMEZONE = "Asia/Shanghai"
    DAILY_JOB = "pbos_daily"
    WEEKLY_JOB = "pbos_weekly"
    MONTHLY_JOB = "pbos_monthly"
    DEFAULTS = (
        (DAILY_JOB, "0 17 * * *"),
        (WEEKLY_JOB, "30 17 * * 5"),
        (MONTHLY_JOB, "0 17 1 * *"),
    )

    def __init__(self, repository: WikiRepository, *, scheduler_available: bool) -> None:
        self.repository = repository
        self.scheduler = KnowledgeScheduler(repository, scheduler_available=scheduler_available)
        self.scheduler_available = scheduler_available

    def ensure_defaults(self, project_id: str, *, now: datetime | None = None) -> list[dict]:
        current = now or datetime.now(timezone.utc)
        existing = {item["job_type"]: item for item in self.repository.list_schedules(project_id)}
        schedules: list[dict] = []
        for job_type, cron in self.DEFAULTS:
            schedule = existing.get(job_type)
            if schedule and schedule.get("cron") == cron and schedule.get("timezone") == self.TIMEZONE:
                if not self.scheduler_available and schedule.get("enabled"):
                    schedule = self.repository.set_schedule_enabled(
                        project_id=project_id,
                        schedule_id=schedule["id"],
                        enabled=False,
                        next_run_at="",
                    )
                schedules.append(schedule)
                continue
            schedules.append(
                self.scheduler.configure(
                    project_id=project_id,
                    job_type=job_type,
                    cron=cron,
                    timezone_name=self.TIMEZONE,
                    now=current,
                )
            )
        return schedules

    def claim_scheduled_run(self, schedule: dict, *, due_at: datetime) -> dict:
        job_type = str(schedule.get("job_type") or "")
        if job_type not in {self.DAILY_JOB, self.WEEKLY_JOB, self.MONTHLY_JOB}:
            raise ValueError("schedule is not a PBOS schedule")
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        local = due_at.astimezone(ZoneInfo(str(schedule.get("timezone") or self.TIMEZONE)))
        if job_type == self.DAILY_JOB:
            period_key, period = "date", local.date().isoformat()
        elif job_type == self.WEEKLY_JOB:
            period_key, period = "week", f"{local.isocalendar().year}-W{local.isocalendar().week:02d}"
        else:
            period_key, period = "month", local.strftime("%Y-%m")
        scheduled_at = due_at.astimezone(timezone.utc).isoformat()
        idempotency_key = f"pbos:{schedule['project_id']}:{job_type}:{period}:{scheduled_at}"
        run = KnowledgeRun(
            project_id=str(schedule["project_id"]),
            run_type=job_type,
            trigger="schedule",
            status=RunStatus.QUEUED,
            input_refs={
                "period": period,
                period_key: period,
                "scheduled_at": scheduled_at,
                "idempotency_key": idempotency_key,
            },
        )
        return self.repository.claim_schedule_run(run, idempotency_key)
