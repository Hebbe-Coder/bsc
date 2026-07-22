"""Project-scoped cadence, ordering and claims for knowledge-growth jobs."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from zoneinfo import ZoneInfo

from app.knowledge.scheduler import KnowledgeScheduler, ScheduleValidationError
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository


class GrowthScheduleCoordinator:
    TIMEZONE = "Asia/Shanghai"
    DAILY_JOB = "growth_daily"
    WEEKLY_JOB = "growth_weekly_distillation"
    DAILY_CRON = "0 17 * * *"
    WEEKLY_CRON = "30 17 * * 5"

    def __init__(self, repository: WikiRepository, *, scheduler_available: bool) -> None:
        self.repository = repository
        self.scheduler = KnowledgeScheduler(repository, scheduler_available=scheduler_available)
        self.scheduler_available = scheduler_available

    def ensure_defaults(self, project_id: str, *, now: datetime | None = None) -> list[dict]:
        current = now or datetime.now(timezone.utc)
        existing = {item["job_type"]: item for item in self.repository.list_schedules(project_id)}
        result: list[dict] = []
        for job_type, cron in ((self.DAILY_JOB, self.DAILY_CRON), (self.WEEKLY_JOB, self.WEEKLY_CRON)):
            schedule = existing.get(job_type)
            if schedule and schedule.get("cron") == cron and schedule.get("timezone") == self.TIMEZONE:
                if not self.scheduler_available and schedule.get("enabled"):
                    schedule = self.repository.set_schedule_enabled(
                        project_id=project_id,
                        schedule_id=schedule["id"],
                        enabled=False,
                        next_run_at="",
                    )
                result.append(schedule)
                continue
            result.append(self.scheduler.configure(
                project_id=project_id,
                job_type=job_type,
                cron=cron,
                timezone_name=self.TIMEZONE,
                now=current,
            ))
        return result

    def pause(self, project_id: str, schedule_id: str) -> dict:
        return self.repository.set_schedule_enabled(
            project_id=project_id,
            schedule_id=schedule_id,
            enabled=False,
            next_run_at="",
        )

    def resume(self, project_id: str, schedule_id: str, *, now: datetime | None = None) -> dict:
        if not self.scheduler_available:
            raise ScheduleValidationError("durable scheduler unavailable")
        schedule = self.repository.get_schedule(project_id, schedule_id)
        if not schedule:
            raise KeyError("growth schedule not found in project")
        if schedule["job_type"] not in {self.DAILY_JOB, self.WEEKLY_JOB}:
            raise ScheduleValidationError("schedule is not a growth schedule")
        next_run = self.scheduler.next_run(
            schedule["cron"],
            now or datetime.now(timezone.utc),
            timezone_name=str(schedule.get("timezone") or self.TIMEZONE),
        )
        return self.repository.set_schedule_enabled(
            project_id=project_id,
            schedule_id=schedule_id,
            enabled=True,
            next_run_at=next_run.isoformat(),
        )

    def claim_scheduled_run(self, schedule: dict, *, due_at: datetime) -> dict:
        job_type = str(schedule.get("job_type") or "")
        if job_type not in {self.DAILY_JOB, self.WEEKLY_JOB}:
            raise ScheduleValidationError("schedule is not a growth schedule")
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        project_id = str(schedule.get("project_id") or "")
        local = due_at.astimezone(ZoneInfo(str(schedule.get("timezone") or self.TIMEZONE)))
        period = local.date().isoformat() if job_type == self.DAILY_JOB else f"{local.isocalendar().year}-W{local.isocalendar().week:02d}"
        input_refs = {
            "source_cutoff": due_at.astimezone(timezone.utc).isoformat(),
            "date" if job_type == self.DAILY_JOB else "week": period,
        }
        if job_type == self.WEEKLY_JOB:
            daily = self._completed_daily(project_id, local.date().isoformat())
            if daily is None:
                return {"claimed": False, "status": "waiting_for_daily", "run_id": ""}
            input_refs["daily_run_id"] = daily["id"]
        idempotency_key = f"growth:{project_id}:{job_type}:{period}:{due_at.astimezone(timezone.utc).isoformat()}"
        input_refs["idempotency_key"] = idempotency_key
        run = KnowledgeRun(
            project_id=project_id,
            run_type=job_type,
            trigger="schedule",
            status=RunStatus.QUEUED,
            input_refs=input_refs,
        )
        return self.repository.claim_schedule_run(run, idempotency_key)

    def run_now(
        self,
        project_id: str,
        job_type: str,
        *,
        request_id: str,
        now: datetime | None = None,
    ) -> dict:
        if job_type not in {self.DAILY_JOB, self.WEEKLY_JOB}:
            raise ScheduleValidationError("job_type is not a growth job")
        if not request_id.strip():
            raise ScheduleValidationError("manual growth runs require a request_id")
        if not self.repository.get_vault(project_id):
            raise ScheduleValidationError("project Vault mapping is required before running growth jobs")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        local = current.astimezone(ZoneInfo(self.TIMEZONE))
        input_refs = {
            "source_cutoff": current.astimezone(timezone.utc).isoformat(),
            "date" if job_type == self.DAILY_JOB else "week": (
                local.date().isoformat()
                if job_type == self.DAILY_JOB
                else f"{local.isocalendar().year}-W{local.isocalendar().week:02d}"
            ),
        }
        if not self.scheduler_available:
            run = KnowledgeRun(
                project_id=project_id,
                run_type=job_type,
                trigger="manual",
                status=RunStatus.UNAVAILABLE,
                input_refs=input_refs,
                error="durable scheduler unavailable",
            )
            self.repository.create_run(run)
            self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.UNAVAILABLE,
                error="durable scheduler unavailable",
                output_refs={"failure": {"category": "configuration", "code": "scheduler_unavailable", "retryable": False}},
            )
            return {"status": "unavailable", "run_id": run.id}
        request_hash = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        idempotency_key = f"growth:{project_id}:{job_type}:manual:{request_hash}"
        input_refs["idempotency_key"] = idempotency_key
        run = KnowledgeRun(
            project_id=project_id,
            run_type=job_type,
            trigger="manual",
            input_refs=input_refs,
        )
        claim = self.repository.claim_schedule_run(run, idempotency_key)
        return {
            "status": "queued" if claim["claimed"] else "duplicate",
            "run_id": claim["run_id"],
        }

    def _completed_daily(self, project_id: str, local_date: str) -> dict | None:
        for run in self.repository.list_runs(project_id, limit=500):
            if run.get("run_type") != self.DAILY_JOB or run.get("status") != RunStatus.COMPLETED.value:
                continue
            inputs = run.get("input_refs") or {}
            growth = (run.get("output_refs") or {}).get("growth") or {}
            if str(inputs.get("date") or growth.get("period") or "") == local_date:
                return run
        return None
