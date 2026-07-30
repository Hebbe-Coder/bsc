"""Durable schedule intent and idempotent knowledge-run claims."""

from __future__ import annotations

from collections.abc import Mapping
import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus
from app.knowledge.wiki_repository import WikiRepository

_INTERVAL_CRON = re.compile(r"^\*/([1-9][0-9]?) \* \* \* \*$")
_CALENDAR_CRON = re.compile(r"^([0-5]?[0-9]) ([01]?[0-9]|2[0-3]) \* \* ([*0-6])$")
_MONTHLY_CRON = re.compile(r"^([0-5]?[0-9]) ([01]?[0-9]|2[0-3]) ([1-9]|[12][0-9]|3[01]) \* \*$")
_JOB_TYPES = {
    "source_sync",
    "horizon_capture",
    "wiki_maintenance",
    "knowledge_lint_eval",
    "weekly_distillation",
    "growth_daily",
    "growth_weekly_distillation",
    "pbos_daily",
    "pbos_weekly",
    "pbos_monthly",
}


class ScheduleValidationError(ValueError):
    """Raised for a schedule that cannot be operated safely."""


class KnowledgeScheduler:
    """Persist desired schedules while treating unavailable background execution honestly."""

    def __init__(self, repository: WikiRepository, *, scheduler_available: bool) -> None:
        self.repository = repository
        self.scheduler_available = scheduler_available

    def configure(
        self,
        *,
        project_id: str,
        job_type: str,
        cron: str,
        timezone_name: str = "UTC",
        now: datetime | None = None,
    ) -> dict:
        self._validate(job_type, cron)
        self._validate_timezone(timezone_name)
        if not self.repository.get_vault(project_id):
            raise ScheduleValidationError("project Vault mapping is required before scheduling knowledge jobs")
        current = now or datetime.now(timezone.utc)
        enabled = self.scheduler_available
        return self.repository.upsert_schedule(
            project_id=project_id,
            job_type=job_type,
            cron=cron,
            timezone_name=timezone_name,
            enabled=enabled,
            next_run_at=self.next_run(cron, current, timezone_name=timezone_name).isoformat() if enabled else "",
        )

    def list_schedules(self, project_id: str) -> list[dict]:
        return self.repository.list_schedules(project_id)

    def run_now(self, *, project_id: str, job_type: str, trigger: str) -> dict:
        self._validate_job_type(job_type)
        if not self.scheduler_available:
            run = KnowledgeRun(project_id=project_id, run_type=job_type, trigger=trigger, status=RunStatus.UNAVAILABLE)
            self.repository.create_run(run)
            self.repository.update_run_status(project_id, run.id, RunStatus.UNAVAILABLE, error="durable scheduler unavailable")
            return {"status": "unavailable", "run_id": run.id}
        claim = self.claim_run(
            project_id=project_id,
            job_type=job_type,
            idempotency_key=f"manual:{datetime.now(timezone.utc).isoformat()}",
            trigger=trigger,
        )
        return {"status": "queued" if claim["claimed"] else "duplicate", "run_id": claim["run_id"]}

    def claim_run(
        self,
        *,
        project_id: str,
        job_type: str,
        idempotency_key: str,
        trigger: str = "schedule",
    ) -> dict:
        self._validate_job_type(job_type)
        run = KnowledgeRun(
            project_id=project_id,
            run_type=job_type,
            trigger=trigger,
            status=RunStatus.QUEUED,
            input_refs={"idempotency_key": idempotency_key},
        )
        return self.repository.claim_schedule_run(run, idempotency_key)

    @staticmethod
    def next_run(cron: str, now: datetime, *, timezone_name: str = "UTC") -> datetime:
        KnowledgeScheduler._validate_timezone(timezone_name)
        zone = ZoneInfo(timezone_name)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        local_now = now.astimezone(zone)
        match = _INTERVAL_CRON.fullmatch(cron)
        if match:
            minutes = int(match.group(1))
            candidate = local_now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            while candidate.minute % minutes:
                candidate += timedelta(minutes=1)
            return candidate.astimezone(timezone.utc)
        match = _CALENDAR_CRON.fullmatch(cron)
        monthly = _MONTHLY_CRON.fullmatch(cron)
        if not match and not monthly:
            raise ScheduleValidationError("cron is not in the supported safe subset")
        minute = int((match or monthly).group(1))
        hour = int((match or monthly).group(2))
        if monthly:
            month_day = int(monthly.group(3))
            year, month = local_now.year, local_now.month
            # A monthly schedule must not rely on a minute-by-minute search:
            # day 31 can be more than forty days away and shorter months must
            # be skipped deterministically.
            for _ in range(24):
                if month_day <= monthrange(year, month)[1]:
                    candidate = datetime(year, month, month_day, hour, minute, tzinfo=zone)
                    if candidate > local_now:
                        return candidate.astimezone(timezone.utc)
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            raise ScheduleValidationError("monthly cron has no next run within two years")
        weekday = match.group(3) if match else "*"
        candidate = local_now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(40 * 24 * 60):
            cron_weekday = (candidate.weekday() + 1) % 7
            if candidate.minute == minute and candidate.hour == hour and (weekday == "*" or cron_weekday == int(weekday)):
                return candidate.astimezone(timezone.utc)
            candidate += timedelta(minutes=1)
        raise ScheduleValidationError("cron has no next run within eight days")

    def _validate(self, job_type: str, cron: str) -> None:
        self._validate_job_type(job_type)
        interval = _INTERVAL_CRON.fullmatch(cron)
        if interval and int(interval.group(1)) >= 5:
            return
        if _CALENDAR_CRON.fullmatch(cron) or _MONTHLY_CRON.fullmatch(cron):
            return
        raise ScheduleValidationError("cron must be every 5-59 minutes or a daily, weekly, or monthly fixed time")

    @staticmethod
    def _validate_job_type(job_type: str) -> None:
        if job_type not in _JOB_TYPES:
            raise ScheduleValidationError("job_type is not allowed")

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ScheduleValidationError("timezone must be a valid IANA timezone") from exc

    def recover_abandoned_runs(
        self,
        *,
        now: datetime | None = None,
        timeout_seconds: int = 3600,
        timeout_seconds_by_run_type: Mapping[str, int] | None = None,
    ) -> list[str]:
        if timeout_seconds < 60:
            raise ScheduleValidationError("abandoned run timeout must be at least 60 seconds")
        try:
            per_type_timeouts = {
                str(run_type).strip(): int(run_timeout)
                for run_type, run_timeout in (timeout_seconds_by_run_type or {}).items()
            }
        except (TypeError, ValueError) as exc:
            raise ScheduleValidationError("abandoned run timeout must be an integer") from exc
        if any(not run_type or run_timeout < 60 for run_type, run_timeout in per_type_timeouts.items()):
            raise ScheduleValidationError("abandoned run timeout must be at least 60 seconds")
        current = now or datetime.now(timezone.utc)
        recovered: list[str] = []
        for run in self.repository.list_running_runs():
            run_timeout = per_type_timeouts.get(str(run.get("run_type") or ""), timeout_seconds)
            value = str(run.get("updated_at") or run.get("started_at") or run.get("created_at") or "")
            try:
                updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if updated > current - timedelta(seconds=run_timeout):
                continue
            self.repository.update_run_status(
                run["project_id"],
                run["id"],
                RunStatus.FAILED,
                error="abandoned running job recovered",
                output_refs={
                    "failure": {
                        "category": "transient_dependency",
                        "code": "abandoned_run",
                        "retryable": True,
                    }
                },
            )
            recovered.append(run["id"])
        return recovered
