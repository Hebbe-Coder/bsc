"""Detached execution for persisted Cangjie five-way candidate extraction."""

from __future__ import annotations

import logging
from threading import Thread
from typing import Callable

from app.core.celery_app import get_celery_app, is_celery_broker_available, is_celery_real
from app.knowledge.candidate_extraction import (
    SourceCandidateExtractionService,
    claim_source_candidate_extraction_run,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import RunStatus


logger = logging.getLogger(__name__)
TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
    RunStatus.UNAVAILABLE.value,
}


class CandidateExtractionDispatchError(RuntimeError):
    """A persisted extraction request could not reach an independent executor."""


def execute_source_candidate_extraction(
    project_id: str,
    run_id: str,
    *,
    repository: GrowthRepository | None = None,
    service_factory: Callable[[GrowthRepository], SourceCandidateExtractionService] = SourceCandidateExtractionService,
) -> dict:
    """Claim and execute one persisted source candidate run exactly once."""
    repo = repository or GrowthRepository()
    owns_repository = repository is None
    try:
        run = repo.get_run(project_id, run_id)
        if not run:
            raise ValueError("candidate extraction run not found")
        if run.get("status") in TERMINAL_RUN_STATUSES:
            return _duplicate_delivery(repo, run)
        if not claim_source_candidate_extraction_run(repo, project_id=project_id, run_id=run_id):
            return _duplicate_delivery(repo, repo.get_run(project_id, run_id) or run)
        return service_factory(repo).execute_claimed(project_id=project_id, run_id=run_id)
    except Exception as exc:
        current = repo.get_run(project_id, run_id)
        if current and current.get("status") == RunStatus.RUNNING.value:
            repo.update_run_status(
                project_id,
                run_id,
                RunStatus.FAILED,
                error=str(exc)[:2_000],
                output_refs={
                    "failure": {
                        "category": "transient_dependency",
                        "code": "candidate_extraction_executor_failed",
                        "retryable": True,
                    },
                    "publication_status": "review_only",
                },
            )
        return {"status": "failed", "run_id": run_id, "error": str(exc)[:2_000]}
    finally:
        if owns_repository:
            repo.close()


def dispatch_source_candidate_extraction(
    project_id: str,
    run_id: str,
    *,
    repository: GrowthRepository | None = None,
) -> dict[str, str]:
    """Queue extraction only when its run ledger is worker-visible.

    Redis availability does not prove that a Celery worker can read the
    submitted run. In particular, an API using a local SQLite repository and
    a worker using PostgreSQL share a broker but not the run ledger. Keep that
    request in-process so the terminal state remains truthful and retryable.
    """
    if _repository_supports_shared_celery_execution(repository) and is_celery_real():
        if not is_celery_broker_available():
            raise CandidateExtractionDispatchError(
                "candidate extraction executor unavailable because the Celery broker is unreachable"
            )
        task = source_candidate_extraction_execute.apply_async(args=[project_id, run_id])
        if hasattr(task, "failed") and task.failed():
            raise CandidateExtractionDispatchError(str(getattr(task, "info", "queue submission failed")))
        assignment = {
            "execution": "celery",
            "task_name": "knowledge.candidate_extraction.execute",
            "task_id": str(task.id),
        }
        _record_execution_assignment(repository, project_id=project_id, run_id=run_id, assignment=assignment)
        return assignment

    def run_local() -> None:
        result = execute_source_candidate_extraction(project_id, run_id, repository=repository)
        if result.get("status") == "failed":
            logger.warning("Local candidate extraction failed for run %s", run_id)

    worker = Thread(
        target=run_local,
        name=f"knowledge-candidate-extraction-{run_id[:12]}",
        daemon=True,
    )
    worker.start()
    assignment = {
        "execution": "in_process",
        "task_name": "knowledge.candidate_extraction.execute",
        "task_id": f"in-process:{run_id}",
    }
    _record_execution_assignment(repository, project_id=project_id, run_id=run_id, assignment=assignment)
    return assignment


def _repository_supports_shared_celery_execution(repository: GrowthRepository | None) -> bool:
    """Return whether the submitted run uses the shared PostgreSQL ledger."""
    probe = repository or GrowthRepository()
    owns_probe = repository is None
    try:
        return getattr(probe._get_connection(), "dialect", "sqlite") == "postgresql"
    finally:
        if owns_probe:
            probe.close()


def _duplicate_delivery(repository: GrowthRepository, run: dict) -> dict:
    repository.append_run_event(
        project_id=str(run["project_id"]),
        run_id=str(run["id"]),
        event_type="knowledge.candidate_extraction.duplicate_delivery",
        payload={"status": str(run.get("status") or "")},
    )
    return {"status": str(run.get("status") or "recorded"), "run_id": str(run["id"]), "duplicate": True}


def _record_execution_assignment(
    repository: GrowthRepository | None,
    *,
    project_id: str,
    run_id: str,
    assignment: dict[str, str],
) -> None:
    if repository is None:
        return
    repository.append_run_event(
        project_id=project_id,
        run_id=run_id,
        event_type="knowledge.candidate_extraction.execution_assigned",
        payload=assignment,
    )


celery_app = get_celery_app()


@celery_app.task(name="knowledge.candidate_extraction.execute")
def source_candidate_extraction_execute(project_id: str, run_id: str) -> dict:
    return execute_source_candidate_extraction(project_id, run_id)
