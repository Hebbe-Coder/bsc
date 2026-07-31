"""Durable PBOS periodic evidence reports using the configured Celery runtime."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.api.dbos_api import dbos_service_for
from app.core.celery_app import get_celery_app
from app.core.config import settings
from app.pbos import PBOSReportService, PBOSService

celery_app = get_celery_app()
_PBOS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _shanghai_date(now: datetime | None = None) -> date:
    """Keep direct PBOS report tasks aligned with the configured user cadence."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_PBOS_TIMEZONE).date()


def run_pbos_periodic_report(
    project_id: str, run_type: str, period: str = ""
) -> dict[str, str]:
    service = PBOSService(dbos_service_for(project_id).store, project_id)
    return PBOSReportService(
        service,
        Path(settings.OBSIDIAN_VAULT_ROOT) / "projects" / project_id,
    ).periodic(run_type, period)


def run_pbos_weekly_report(project_id: str, week: str = "") -> dict[str, str]:
    """Compatibility entry point for callers that explicitly request a weekly report."""
    return run_pbos_periodic_report(project_id, "pbos_weekly", week)


@celery_app.task(name="pbos.weekly_report")
def pbos_weekly_report_task(project_id: str, week: str = "") -> dict[str, str]:
    return run_pbos_weekly_report(project_id, week)


@celery_app.task(name="pbos.daily_review")
def pbos_daily_review_task(project_id: str) -> dict[str, str]:
    period = _shanghai_date().isoformat()
    return run_pbos_periodic_report(project_id, "pbos_daily", period)


@celery_app.task(name="pbos.monthly_review")
def pbos_monthly_review_task(project_id: str) -> dict[str, str]:
    period = _shanghai_date().strftime("%Y-%m")
    return run_pbos_periodic_report(project_id, "pbos_monthly", period)
