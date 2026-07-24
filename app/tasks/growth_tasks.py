"""Celery entry points and durable execution semantics for growth distillation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Callable
from zoneinfo import ZoneInfo

from app.core.celery_app import get_celery_app
from app.core.config import settings
from app.knowledge.generation_provenance import redact_secrets
from app.knowledge.growth_distillation import GrowthDistillationService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_output_sync import ObsidianOutputSyncService
from app.knowledge.obsidian_plugin_manifest import ObsidianPluginManifest
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.wiki_sync import ObsidianSyncService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus
from app.knowledge.wiki_repository import WikiRepository


GROWTH_RUN_TYPES = {"growth_daily", "growth_weekly_distillation"}


@dataclass(frozen=True)
class GrowthTaskFailure:
    category: str
    code: str
    retryable: bool


def classify_growth_failure(exc: Exception) -> GrowthTaskFailure:
    message = str(exc).lower()
    if isinstance(exc, PermissionError):
        return GrowthTaskFailure("policy", "permission_denied", False)
    if "user-authored" in message or "ownership" in message or "managed file" in message or "conflict" in message:
        return GrowthTaskFailure("write_conflict", "managed_content_conflict", False)
    if "not configured" in message or "does not exist" in message or "required" in message:
        return GrowthTaskFailure("configuration", "configuration_missing", False)
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return GrowthTaskFailure("transient_dependency", "storage_or_dependency_unavailable", True)
    if isinstance(exc, (TypeError, ValueError, KeyError)):
        return GrowthTaskFailure("input", "invalid_growth_input", False)
    return GrowthTaskFailure("transient_dependency", "unexpected_growth_failure", True)


def execute_growth_run(
    project_id: str,
    run_id: str,
    *,
    schedule_id: str = "",
    week: str = "",
    repository: WikiRepository | None = None,
) -> dict:
    """Execute one persisted growth run after atomically claiming queued state."""
    started_perf = time.perf_counter()
    base_repo = repository or GrowthRepository()
    owns_repository = repository is None
    repo = base_repo if isinstance(base_repo, GrowthRepository) else GrowthRepository(backend=base_repo._get_connection())
    try:
        run = repo.get_run(project_id, run_id)
        if not run:
            raise ValueError("knowledge run not found")
        if run.get("run_type") not in GROWTH_RUN_TYPES:
            raise ValueError("run is not a growth task")
        if run.get("status") in {"completed", "failed", "cancelled", "unavailable"}:
            return _record_duplicate(repo, run)
        if run.get("status") != RunStatus.QUEUED.value:
            return _record_duplicate(repo, run)
        if not settings.KNOWLEDGE_GROWTH_ENABLED:
            return _terminal(
                repo, run, RunStatus.UNAVAILABLE,
                GrowthTaskFailure("configuration", "knowledge_growth_disabled", False),
                "Knowledge growth feature is disabled",
            )
        if not settings.OBSIDIAN_VAULT_ROOT or not repo.get_vault(project_id):
            return _terminal(
                repo, run, RunStatus.UNAVAILABLE,
                GrowthTaskFailure("configuration", "vault_not_configured", False),
                "Obsidian Vault is not configured",
            )
        if not _claim_execution(repo, run):
            current = repo.get_run(project_id, run_id) or run
            return _record_duplicate(repo, current)

        repo.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.started",
            payload={"run_type": run["run_type"], "schedule_id": schedule_id},
        )
        inputs = run.get("input_refs") or {}
        created_at = _parse_datetime(run.get("created_at")) or datetime.now(timezone.utc)
        sync = _sync_declared_obsidian_exports(repo, project_id=project_id, run_id=run_id)
        explicit_cutoff = str(inputs.get("source_cutoff") or "").strip()
        cutoff = explicit_cutoff or datetime.now(timezone.utc).isoformat()
        service = GrowthDistillationService(repo, Path(settings.OBSIDIAN_VAULT_ROOT))
        if run["run_type"] == "growth_daily":
            period = str(inputs.get("date") or created_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat())
            result = service.run_daily(project_id, period, source_cutoff=cutoff)
        else:
            local = created_at.astimezone(ZoneInfo("Asia/Shanghai")).isocalendar()
            period = str(inputs.get("week") or week or f"{local.year}-W{local.week:02d}")
            result = service.run_weekly(project_id, period, source_cutoff=cutoff)

        finished = datetime.now(timezone.utc)
        queue_delay_ms = max(0, int((finished - (_parse_datetime(run.get("created_at")) or finished)).total_seconds() * 1000))
        persisted_during_execution = repo.get_run(project_id, run_id) or {}
        prior_metrics = (persisted_during_execution.get("output_refs") or {}).get("metrics") or {}
        metrics = {
            "queue_delay_ms": queue_delay_ms,
            "runtime_ms": max(0, int((time.perf_counter() - started_perf) * 1000)),
            "retry_count": _retry_depth(repo, run),
            "duplicate_count": int(prior_metrics.get("duplicate_count", 0)),
            "no_op_count": 1 if result.get("status") == "noop" else 0,
            "input_count": int((result.get("manifest") or {}).get("input_count", 0)),
            "input_hash": str(result.get("input_hash") or ""),
            "output_paths": list(result.get("paths") or []),
            "source_cutoff": cutoff,
            "freshness_seconds": max(0, int((finished - (_parse_datetime(cutoff) or finished)).total_seconds())),
            "failure_category": "",
        }
        refs = {"growth": result, "sync": sync, "schedule_id": schedule_id, "metrics": metrics}
        repo.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.distillation.completed" if result.get("status") != "noop" else "knowledge.growth.distillation.noop",
            payload={"kind": run["run_type"], "period": period, "input_hash": result.get("input_hash", ""), "paths": result.get("paths", [])},
        )
        repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs=refs)
        return {
            "status": "completed",
            "run_id": run_id,
            "growth": result,
            "sync": sync,
            "metrics": metrics,
        }
    except Exception as exc:
        run = repo.get_run(project_id, run_id)
        if not run or run.get("run_type") not in GROWTH_RUN_TYPES:
            raise
        failure = classify_growth_failure(exc)
        safe_error = str(redact_secrets(str(exc)))
        status = RunStatus.UNAVAILABLE if failure.category == "configuration" else RunStatus.FAILED
        return _terminal(repo, run, status, failure, safe_error)
    finally:
        if owns_repository:
            repo.close()


def recover_abandoned_growth_runs(
    repository: WikiRepository,
    *,
    dispatch: Callable[[str, str], object],
    now: datetime | None = None,
    timeout_seconds: int = 3600,
) -> dict[str, int]:
    """Fail stale workers and enqueue one durable replay preserving the input manifest."""
    if timeout_seconds < 60:
        raise ValueError("abandoned run timeout must be at least 60 seconds")
    current = now or datetime.now(timezone.utc)
    recovered = 0
    failures = 0
    for run in repository.list_running_runs(limit=500):
        if run.get("run_type") not in GROWTH_RUN_TYPES:
            continue
        updated = _parse_datetime(run.get("updated_at") or run.get("started_at") or run.get("created_at"))
        if updated is None or updated > current - timedelta(seconds=timeout_seconds):
            continue
        failure = GrowthTaskFailure("transient_dependency", "abandoned_run", True)
        repository.update_run_status(
            run["project_id"], run["id"], RunStatus.FAILED,
            error="abandoned growth job recovered",
            output_refs={"failure": asdict(failure)},
        )
    for failed in _retryable_failed_runs(repository):
        if _has_retry_child(repository, failed["id"]) or _retry_depth(repository, failed) >= 3:
            continue
        key = f"growth-recovery:{failed['id']}"
        input_refs = {**(failed.get("input_refs") or {}), "idempotency_key": key}
        retry = KnowledgeRun(
            project_id=failed["project_id"],
            run_type=failed["run_type"],
            trigger="recovery",
            input_refs=input_refs,
            retry_of=failed["id"],
        )
        repository.claim_schedule_run(retry, key)

    for queued in _undispatched_growth_runs(repository):
        try:
            dispatch(queued["project_id"], queued["id"])
            repository.append_run_event(
                project_id=queued["project_id"],
                run_id=queued["id"],
                event_type="knowledge.growth.dispatched",
                payload={"trigger": queued.get("trigger", "")},
            )
            recovered += 1
        except Exception as exc:
            repository.append_run_event(
                project_id=queued["project_id"],
                run_id=queued["id"],
                event_type="knowledge.growth.dispatch_failed",
                payload={
                    "failure": asdict(GrowthTaskFailure("transient_dependency", "broker_unavailable", True)),
                    "error": str(redact_secrets(str(exc))),
                },
            )
            failures += 1
    return {"recovered": recovered, "failures": failures}


def _retryable_failed_runs(repository: WikiRepository) -> list[dict]:
    rows = repository._execute(
        "SELECT * FROM knowledge_runs WHERE status=? AND run_type IN (?,?) ORDER BY created_at,id",
        (RunStatus.FAILED.value, *sorted(GROWTH_RUN_TYPES)),
    ).fetchall()
    values = [repository._decode(row, ("input_refs_json", "output_refs_json")) or {} for row in rows]
    return [
        run for run in values
        if bool(((run.get("output_refs") or {}).get("failure") or {}).get("retryable"))
    ]


def _undispatched_growth_runs(repository: WikiRepository) -> list[dict]:
    rows = repository._execute(
        "SELECT run.* FROM knowledge_runs AS run "
        "WHERE run.status=? AND run.run_type IN (?,?) "
        "AND NOT EXISTS (SELECT 1 FROM knowledge_run_events AS event "
        "WHERE event.project_id=run.project_id AND event.run_id=run.id AND event.event_type=?) "
        "ORDER BY run.created_at,run.id",
        (RunStatus.QUEUED.value, *sorted(GROWTH_RUN_TYPES), "knowledge.growth.dispatched"),
    ).fetchall()
    return [repository._decode(row, ("input_refs_json", "output_refs_json")) or {} for row in rows]


def _has_retry_child(repository: WikiRepository, run_id: str) -> bool:
    return bool(repository._execute("SELECT 1 FROM knowledge_runs WHERE retry_of=? LIMIT 1", (run_id,)).fetchone())


def _retry_depth(repository: WikiRepository, run: dict) -> int:
    depth = 0
    current = run
    seen: set[str] = set()
    while current.get("retry_of") and current["retry_of"] not in seen:
        seen.add(current["retry_of"])
        row = repository._execute("SELECT * FROM knowledge_runs WHERE id=?", (current["retry_of"],)).fetchone()
        if not row:
            break
        current = repository._decode(row, ("input_refs_json", "output_refs_json")) or {}
        depth += 1
    return depth


def _claim_execution(repository: WikiRepository, run: dict) -> bool:
    now = repository._now()
    cursor = repository._execute(
        "UPDATE knowledge_runs SET status=?,started_at=?,updated_at=? "
        "WHERE project_id=? AND id=? AND status=?",
        (RunStatus.RUNNING.value, now, now, run["project_id"], run["id"], RunStatus.QUEUED.value),
    )
    repository._commit()
    return cursor.rowcount == 1


def _terminal(
    repository: WikiRepository,
    run: dict,
    status: RunStatus,
    failure: GrowthTaskFailure,
    message: str,
) -> dict:
    safe_message = str(redact_secrets(message))
    current = datetime.now(timezone.utc)
    created = _parse_datetime(run.get("created_at")) or current
    started = _parse_datetime(run.get("started_at"))
    prior_metrics = ((run.get("output_refs") or {}).get("metrics") or {})
    refs = {
        "failure": asdict(failure),
        "metrics": {
            "queue_delay_ms": max(0, int(((started or current) - created).total_seconds() * 1000)),
            "runtime_ms": max(0, int((current - started).total_seconds() * 1000)) if started else 0,
            "retry_count": _retry_depth(repository, run),
            "duplicate_count": int(prior_metrics.get("duplicate_count", 0)),
            "no_op_count": 0,
            "input_count": 0,
            "input_hash": "",
            "output_paths": [],
            "source_cutoff": str((run.get("input_refs") or {}).get("source_cutoff") or ""),
            "freshness_seconds": 0,
            "failure_category": failure.category,
        },
    }
    repository.append_run_event(
        project_id=run["project_id"],
        run_id=run["id"],
        event_type=f"knowledge.growth.{status.value}",
        payload={"failure": asdict(failure), "error": safe_message},
    )
    repository.update_run_status(run["project_id"], run["id"], status, error=safe_message, output_refs=refs)
    return {
        "status": status.value,
        "run_id": run["id"],
        "error": safe_message,
        "failure": asdict(failure),
    }


def _record_duplicate(repository: WikiRepository, run: dict) -> dict:
    refs = dict(run.get("output_refs") or {})
    metrics = dict(refs.get("metrics") or {})
    metrics["duplicate_count"] = int(metrics.get("duplicate_count", 0)) + 1
    refs["metrics"] = metrics
    repository._execute(
        "UPDATE knowledge_runs SET output_refs_json=? WHERE project_id=? AND id=?",
        (repository._json_dumps(refs), run["project_id"], run["id"]),
    )
    repository._commit()
    repository.append_run_event(
        project_id=run["project_id"],
        run_id=run["id"],
        event_type="knowledge.growth.duplicate_delivery",
        payload={"status": run.get("status", "")},
    )
    return {
        "status": run.get("status", "running"),
        "run_id": run["id"],
        "duplicate": True,
        "output_refs": refs,
    }


def _sync_declared_obsidian_exports(
    repository: GrowthRepository,
    *,
    project_id: str,
    run_id: str,
) -> dict:
    """Capture only manifest-declared Obsidian exports before a growth pass.

    The daily job intentionally does not snapshot or modify Wiki pages. It
    imports A-layer plugin exports, registers D-layer plugin outputs, and
    records a triage decision for newly pending evidence. Reliability still
    controls whether a source can enter factual context.
    """
    if not settings.KNOWLEDGE_OBSIDIAN_SYNC_ENABLED:
        report = {"status": "unavailable", "reason": "obsidian_sync_disabled"}
        repository.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.obsidian_sync.unavailable",
            payload=report,
        )
        return report
    mapping = repository.get_vault(project_id)
    vault_root = Path(settings.OBSIDIAN_VAULT_ROOT)
    if not mapping or not settings.OBSIDIAN_VAULT_ROOT or not vault_root.is_dir():
        report = {"status": "unavailable", "reason": "vault_not_configured"}
        repository.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.obsidian_sync.unavailable",
            payload=report,
        )
        return report
    try:
        sources = ObsidianSyncService(repository, vault_root).sync(project_id=project_id)
        decisions = SourceTriageService(repository).triage_project(project_id, limit=100)
        outputs = ObsidianOutputSyncService(repository, vault_root).sync(
            project_id=project_id,
            run_id=run_id,
        )
        project_root = (vault_root / str(mapping["vault_path"])).resolve()
        manifest = ObsidianPluginManifest.load(project_root)
        triaged_statuses = [
            str((repository.get_source(project_id, str(item.get("source_id") or "")) or {}).get("status") or "")
            for item in decisions
        ]
        report = {
            "status": "completed",
            "sources": sources,
            "triage": {
                "evaluated": len(decisions),
                # Reliability is necessary but not sufficient for admission.
                # Report the persisted lifecycle state so the audit summary
                # never claims a low-priority, reliable source entered A.
                "eligible": sum(status in {SourceStatus.ELIGIBLE.value, SourceStatus.PROCESSED.value} for status in triaged_statuses),
                "pending_review": sum(status == SourceStatus.VALIDATED.value for status in triaged_statuses),
            },
            "outputs": outputs,
            "plugins": manifest.public_status(
                repository.list_sources(project_id),
                repository.list_outputs(project_id),
                project_root=project_root,
            ),
        }
        repository.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.obsidian_sync.completed",
            payload=report,
        )
        return report
    except Exception as exc:
        report = {
            "status": "failed",
            "reason": "obsidian_export_sync_failed",
            "error": str(redact_secrets(str(exc)))[:500],
        }
        repository.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.obsidian_sync.failed",
            payload=report,
        )
        return report


def _parse_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


celery_app = get_celery_app()


@celery_app.task(name="knowledge.growth.execute")
def growth_execute(project_id: str, run_id: str, schedule_id: str = "", week: str = "") -> dict:
    return execute_growth_run(project_id, run_id, schedule_id=schedule_id, week=week)
