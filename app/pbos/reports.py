"""Evidence-only PBOS periodic report projections."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .service import PBOSService


class PBOSReportService:
    def __init__(self, service: PBOSService, project_root: Path | str) -> None:
        self.service = service
        self.project_root = Path(project_root).resolve()

    def weekly(self, week: str = "") -> dict[str, str]:
        return self.periodic("pbos_weekly", week)

    def periodic(self, run_type: str, period: str = "") -> dict[str, str]:
        if not self.project_root.is_dir():
            return {"state": "vault_unavailable"}
        if run_type == "pbos_daily":
            report_period = period or date.today().isoformat()
            relative_path = Path("pbos") / "reviews" / "daily" / report_period / "daily-action.md"
            title = "Personal Growth Daily Action"
        elif run_type == "pbos_monthly":
            report_period = period or date.today().strftime("%Y-%m")
            relative_path = Path("pbos") / "reviews" / "monthly" / report_period / "capability-report.md"
            title = "Personal Growth Monthly Capability Report"
        elif run_type == "pbos_weekly":
            today = date.today().isocalendar()
            report_period = period or f"{today.year}-W{today.week:02d}"
            relative_path = Path("distillations") / "每周蒸馏" / report_period / "pbos" / "personal-growth.md"
            title = "Personal Growth Weekly Review"
        else:
            raise ValueError("unsupported PBOS report type")
        if not report_period or any(part in {"", ".", ".."} for part in Path(report_period).parts):
            raise ValueError("invalid PBOS report period")
        cockpit = self.service.cockpit()
        path = (self.project_root / relative_path).resolve()
        if self.project_root not in path.parents:
            raise ValueError("PBOS report path escaped project Vault")
        body = self._render(report_period, cockpit, title=title)
        if path.exists() and path.read_text(encoding="utf-8") != body:
            return {"state": "conflict", "path": path.relative_to(self.project_root).as_posix()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return {"state": "written", "path": path.relative_to(self.project_root).as_posix()}

    @staticmethod
    def _render(period: str, cockpit: dict, *, title: str) -> str:
        capabilities = cockpit.get("capabilities") or []
        outcomes = cockpit.get("outcomes") or []
        today = cockpit.get("today") or {}
        lines = ["---", "asset_kind: pbos_periodic_review", "managed_by_bsc: true", f'period: "{period}"', "---", "", f"# {title}", "", "## Next Action", "", str(today.get("title") or "No grounded action is available yet."), "", "## Capability Evidence", ""]
        lines += [f"- {item.get('name', 'Capability')}: level {item.get('level', 0)}, evidence {item.get('evidence_count', 0)}" for item in capabilities] or ["- No verified capability update this week."]
        lines += ["", "## Outcomes", ""]
        lines += [f"- {item.get('acceptance_status', 'unverified')}: quality {item.get('quality_score', 'unverified')}" for item in outcomes] or ["- No verified outcome recorded this week."]
        lines += ["", "## Connector Status", ""]
        lines += [f"- {name}: {state}" for name, state in (cockpit.get("connectors") or {}).items()]
        return "\n".join(lines) + "\n"
