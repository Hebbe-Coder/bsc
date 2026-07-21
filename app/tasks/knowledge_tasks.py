"""Celery entry points for persisted, auditable knowledge jobs."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.celery_app import get_celery_app
from app.core.config import settings
from app.knowledge.distillation import DistillationError, WeeklyDistillationService
from app.knowledge.horizon_client import HorizonClient, HorizonClientError
from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.wiki_sync import ObsidianSyncService
from app.knowledge.wiki_compiler import WikiCompilationError, WikiCompiler
from app.knowledge.wiki_llm_provider import SOPWikiCompilerProvider
from app.knowledge.wiki_contracts import RunStatus
from app.knowledge.wiki_repository import WikiRepository


def execute_knowledge_run(
    project_id: str, run_id: str, schedule_id: str = "", week: str = "", repository: WikiRepository | None = None
) -> dict:
    """Execute one persisted job; unsupported or ungrounded work remains explicitly unavailable."""
    repo = repository or WikiRepository()
    owns_repository = repository is None
    try:
        run = repo.get_run(project_id, run_id)
        if not run:
            raise ValueError("knowledge run not found")
        repo.update_run_status(project_id, run_id, RunStatus.RUNNING)
        if run["run_type"] == "source_sync":
            if not settings.OBSIDIAN_VAULT_ROOT:
                repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="Obsidian Vault is not configured")
                return {"status": "unavailable", "run_id": run_id}
            report = ObsidianSyncService(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).sync(project_id=project_id)
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.source.sync.completed", payload=report
            )
            repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs={"sync": report})
            return {"status": "completed", "run_id": run_id, "sync": report}
        if run["run_type"] == "horizon_capture":
            if not settings.HORIZON_ENABLED or not settings.HORIZON_API_BASE_URL:
                repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="Horizon sidecar is not configured")
                return {"status": "unavailable", "run_id": run_id}
            horizon_run_id = str(run["input_refs"].get("horizon_run_id") or "").strip()
            stage = str(run["input_refs"].get("stage") or "filtered")
            if not horizon_run_id:
                repo.update_run_status(project_id, run_id, RunStatus.FAILED, error="Horizon run ID is required")
                return {"status": "failed", "run_id": run_id, "error": "Horizon run ID is required"}
            try:
                response = HorizonClient(
                    base_url=settings.HORIZON_API_BASE_URL,
                    api_key=settings.HORIZON_API_KEY,
                    stage_url_template=settings.HORIZON_STAGE_URL_TEMPLATE,
                    timeout_seconds=settings.HORIZON_TIMEOUT_SECONDS,
                    max_response_bytes=settings.HORIZON_MAX_RESPONSE_BYTES,
                    allow_private_network=settings.HORIZON_ALLOW_PRIVATE_NETWORK,
                ).fetch_stage(run_id=horizon_run_id, stage=stage)
                report = HorizonImportService(repo).import_items(
                    project_id=project_id, run_id=response.run_id, stage=response.stage, items=response.items
                )
            except HorizonClientError as exc:
                repo.update_run_status(project_id, run_id, RunStatus.FAILED, error=str(exc))
                return {"status": "failed", "run_id": run_id, "error": str(exc)}
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.horizon.capture.completed",
                payload={"horizon_run_id": horizon_run_id, "stage": stage, **report},
            )
            repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs={"horizon": report, "horizon_run_id": horizon_run_id, "stage": stage})
            return {"status": "completed", "run_id": run_id, "horizon": report}
        if run["run_type"] == "wiki_maintenance":
            if not settings.OBSIDIAN_VAULT_ROOT:
                repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="Obsidian Vault is not configured")
                return {"status": "unavailable", "run_id": run_id}
            vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id)
            rules_path = vault.project_root / "AGENTS.md"
            if not rules_path.is_file():
                repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="project AGENTS.md is required")
                return {"status": "unavailable", "run_id": run_id}
            page_snapshots = []
            for page in repo.list_pages(project_id):
                content = repo.get_page_content(project_id, page["id"])
                if content:
                    page_snapshots.append({**page, "content": content["content"]})
            try:
                result = WikiCompiler(repo, SOPWikiCompilerProvider()).compile_maintenance(
                    project_id=project_id,
                    source_ids=run["input_refs"].get("source_ids") or None,
                    trigger=run["trigger"],
                    rules_text=rules_path.read_text(encoding="utf-8"),
                    actor_id="knowledge-task",
                    page_snapshots=page_snapshots,
                )
            except WikiCompilationError as exc:
                reason = str(exc)
                status = RunStatus.UNAVAILABLE if "real KNOWLEDGE_WIKI_LLM_PROVIDER" in reason else RunStatus.FAILED
                repo.update_run_status(project_id, run_id, status, error=reason)
                return {"status": status.value, "run_id": run_id, "error": reason}
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.proposal.created",
                payload={"proposal_id": result.proposal["id"], "compiler_run_id": result.run["id"]},
            )
            repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs={"proposal_id": result.proposal["id"], "compiler_run_id": result.run["id"]})
            return {"status": "completed", "run_id": run_id, "proposal_id": result.proposal["id"]}
        if run["run_type"] != "weekly_distillation":
            repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="knowledge executor not configured")
            return {"status": "unavailable", "run_id": run_id}
        sources = repo.list_sources(project_id, status="eligible")
        if not sources:
            repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="no eligible source evidence")
            return {"status": "unavailable", "run_id": run_id}
        if not settings.OBSIDIAN_VAULT_ROOT:
            repo.update_run_status(project_id, run_id, RunStatus.UNAVAILABLE, error="Obsidian Vault is not configured")
            return {"status": "unavailable", "run_id": run_id}
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id)
        rules_path = vault.project_root / "AGENTS.md"
        rule_revision = hashlib.sha256(
            rules_path.read_bytes() if rules_path.exists() else b""
        ).hexdigest()
        selected_week = week or _iso_week()
        pages = repo.list_pages(project_id)
        bundle = WeeklyDistillationService(vault).distill(
            project_id=project_id,
            week=selected_week,
            sources=sources,
            pages=pages,
            rule_revision=rule_revision,
        )
        source_cutoff = hashlib.sha256(
            "|".join(f"{source['id']}:{source['content_hash']}" for source in sorted(sources, key=lambda item: item["id"])).encode("utf-8")
        ).hexdigest()
        repo.record_distillation(
            project_id=project_id,
            week=selected_week,
            paths=list(bundle.paths),
            source_cutoff=source_cutoff,
        )
        repo.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.distillation.completed",
            payload={"week": selected_week, "paths": list(bundle.paths), "source_cutoff": source_cutoff},
        )
        repo.update_run_status(
            project_id,
            run_id,
            RunStatus.COMPLETED,
            output_refs={"week": selected_week, "paths": list(bundle.paths), "schedule_id": schedule_id},
        )
        return {"status": "completed", "run_id": run_id, "paths": list(bundle.paths)}
    except DistillationError as exc:
        repo.update_run_status(project_id, run_id, RunStatus.FAILED, error=str(exc))
        return {"status": "failed", "run_id": run_id, "error": str(exc)}
    finally:
        if owns_repository:
            repo.close()


def _iso_week() -> str:
    value = date.today().isocalendar()
    return f"{value.year}-W{value.week:02d}"


def reconcile_knowledge_schedules(now: datetime | None = None) -> dict:
    """Claim due persistent schedules and enqueue runs exactly once per due instant."""
    repo = WikiRepository()
    current = now or datetime.now(timezone.utc)
    queued = 0
    duplicates = 0
    failures = 0
    try:
        scheduler = KnowledgeScheduler(repo, scheduler_available=True)
        for schedule in repo.list_due_schedules(current.isoformat()):
            due_at = str(schedule["next_run_at"])
            idempotency_key = f"{schedule['id']}:{due_at}"
            claim = scheduler.claim_run(
                project_id=schedule["project_id"],
                job_type=schedule["job_type"],
                idempotency_key=idempotency_key,
                trigger="schedule",
            )
            if not claim["claimed"]:
                duplicates += 1
                continue
            try:
                knowledge_execute.apply_async(args=[schedule["project_id"], claim["run_id"], schedule["id"]])
                next_run = scheduler.next_run(schedule["cron"], current).isoformat()
                advanced = repo.advance_schedule(
                    schedule_id=schedule["id"],
                    expected_next_run_at=due_at,
                    next_run_at=next_run,
                    last_run_at=current.isoformat(),
                )
                if advanced:
                    queued += 1
                else:
                    duplicates += 1
            except Exception as exc:
                failures += 1
                repo.update_run_status(schedule["project_id"], claim["run_id"], RunStatus.FAILED, error=f"queue submission failed: {exc}")
                repo.release_schedule_claim(
                    project_id=schedule["project_id"], job_type=schedule["job_type"], idempotency_key=idempotency_key
                )
        return {"queued": queued, "duplicates": duplicates, "failures": failures}
    finally:
        repo.close()


celery_app = get_celery_app()


@celery_app.task(name="knowledge.execute")
def knowledge_execute(project_id: str, run_id: str, schedule_id: str = "", week: str = "") -> dict:
    return execute_knowledge_run(project_id, run_id, schedule_id=schedule_id, week=week)


@celery_app.task(name="knowledge.reconcile_schedules")
def knowledge_reconcile_schedules() -> dict:
    return reconcile_knowledge_schedules()
