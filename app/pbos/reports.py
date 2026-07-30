"""Evidence-only PBOS periodic report projections."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from .service import PBOSService


class PBOSReportService:
    _MARKER = re.compile(r"^<!-- pbos-managed-sha256:([0-9a-f]{64}) -->\s*$", re.MULTILINE)

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
        if path.exists() and not self._can_refresh_managed_report(path, body):
            return {"state": "conflict", "path": path.relative_to(self.project_root).as_posix()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return {"state": "written", "path": path.relative_to(self.project_root).as_posix()}

    @classmethod
    def _can_refresh_managed_report(cls, path: Path, body: str) -> bool:
        existing = path.read_text(encoding="utf-8")
        if existing == body:
            return True
        marker = cls._MARKER.search(existing)
        if marker:
            # A marker must be the terminal managed footer. Anything after it is user content.
            if existing[marker.end():].strip():
                return False
            return hashlib.sha256(existing[:marker.start()].encode("utf-8")).hexdigest() == marker.group(1)
        # Reports created before integrity footers are known BSC-owned projections.
        # Upgrade them once; all subsequent human edits are detected by the footer.
        return "asset_kind: pbos_periodic_review" in existing and "managed_by_bsc: true" in existing

    @staticmethod
    def _render(period: str, cockpit: dict, *, title: str) -> str:
        capabilities = cockpit.get("capabilities") or []
        outcomes = cockpit.get("outcomes") or []
        observations = {
            str(item.get("artifact_id") or ""): item
            for item in cockpit.get("outcome_observations") or []
            if isinstance(item, dict)
        }
        action = cockpit.get("today_action") or {}
        refs = [str(item).strip() for item in action.get("knowledge_context_refs") or [] if str(item).strip()]
        lines = ["---", "asset_kind: pbos_periodic_review", "managed_by_bsc: true", f'period: "{period}"', "---", "", f"# {title}", "", "## Next Action", "", str(action.get("title") or "Capture a bounded Mission and one governed project context."), "", "## Why This Action", ""]
        lines += [f"- {item}" for item in action.get("rationale") or []] or ["- PBOS has not yet compiled a reviewable personal plan."]
        lines += ["", "## Success Check", "", f"- {str(action.get('success_check') or 'Record an observable receipt and a concise reflection.')}", "", "## Planning Grounding", ""]
        lines += [f"- `{item}`" for item in refs] or ["- No governed context is available yet; this is a capture recommendation."]
        lines += ["", "Planning inputs guide the next action. They do not establish a verified personal capability.", "", "## Capability Evidence", ""]
        lines += [f"- {item.get('name', 'Capability')}: level {item.get('level', 0)}, evidence {item.get('evidence_count', 0)}" for item in capabilities] or ["- No verified capability update this week."]
        lines += ["", "## Outcomes", ""]
        outcome_lines = []
        for item in outcomes:
            observation = observations.get(str(item.get("artifact_id") or ""), {})
            if observation.get("eligible_for_evolution"):
                outcome_lines.append(f"- {item.get('acceptance_status', 'unverified')}: quality {item.get('quality_score', 'unverified')}; eligible for personal learning")
                continue
            missing = ", ".join(str(value) for value in observation.get("missing_requirements") or [])
            outcome_lines.append(f"- {item.get('acceptance_status', 'unverified')}: quality {item.get('quality_score', 'unverified')}; not eligible for personal learning ({missing or 'incomplete evidence'})")
        lines += outcome_lines or ["- No verified outcome recorded this week."]
        lines += ["", "## Connector Status", ""]
        lines += [f"- {name}: {state}" for name, state in (cockpit.get("connectors") or {}).items()]
        body = "\n".join(lines) + "\n"
        return body + f"<!-- pbos-managed-sha256:{hashlib.sha256(body.encode('utf-8')).hexdigest()} -->\n"
