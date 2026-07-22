"""Transport-neutral MCP handlers for project-scoped knowledge growth."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
import re
from typing import Any, Callable

from app.core.celery_app import is_celery_broker_available, is_celery_real
from app.core.config import settings
from app.knowledge.capture_adapters import redact_secrets
from app.knowledge.feedback_router import FeedbackRouter
from app.knowledge.growth_contracts import OutputAsset, OutputFeedback, ProjectKnowledgeProfile
from app.knowledge.growth_distillation import GrowthDistillationService
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.method_detector import MethodDetector
from app.knowledge.method_evaluator import MethodEvaluator
from app.knowledge.method_gate import MethodGate
from app.knowledge.method_registry import MethodRegistry
from app.knowledge.output_evaluator import OutputEvaluator
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.project_profile import ProjectProfileService
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.source_triage import SourceTriageService
from app.knowledge.wiki_commands import WikiCommandService
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


MAX_PAGE_SIZE = 500
GROWTH_JOB_TYPES = {"growth_daily", "growth_weekly_distillation"}
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class GrowthUnavailableError(RuntimeError):
    def __init__(self, message: str, availability: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.availability = availability or {"growth": bool(settings.KNOWLEDGE_GROWTH_ENABLED)}


class GrowthStateConflictError(ValueError):
    """A governed mutation is invalid for the persisted lifecycle state."""


def _repo() -> GrowthRepository:
    return GrowthRepository()


def _require_enabled() -> None:
    if not settings.KNOWLEDGE_GROWTH_ENABLED:
        raise GrowthUnavailableError(
            "Knowledge growth is disabled by configuration",
            {"growth": False},
        )


def growth_profile(
    project_id: str,
    action: str = "get",
    profile: dict[str, Any] | None = None,
    expected_revision: int | None = None,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"get", "update"})
    repo = _repo()
    try:
        if action == "get":
            value = repo.get_profile(project_id) or ProjectKnowledgeProfile(project_id=project_id).model_dump(mode="json")
        else:
            if expected_revision is None:
                raise ValueError("expected_revision is required for profile update")
            value = ProjectProfileService(repo).update_profile(
                project_id,
                {key: item for key, item in (profile or {}).items() if item is not None},
                expected_revision=expected_revision,
                actor_id="mcp",
            ).model_dump(mode="json")
        return _result(repo, project_id, {"profile": _public(value), "action": action})
    finally:
        repo.close()


def growth_assets(
    project_id: str,
    stage: str = "",
    limit: int = 100,
    cursor: str = "",
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    if stage not in {"", "A", "B", "C", "D", "review"}:
        raise ValueError("stage must be A, B, C, D, review, or empty")
    repo = _repo()
    try:
        items: list[dict[str, Any]] = []
        if stage in {"", "A"}:
            items.extend({**_source(item), "stage": "A", "asset_type": "source"} for item in repo.list_sources(project_id))
        if stage in {"", "B"}:
            items.extend({**_public(item), "stage": "B", "asset_type": "page"} for item in repo.list_pages(project_id))
        if stage in {"", "C"}:
            items.extend({**_public(item), "stage": "C", "asset_type": "method"} for item in repo.list_methods(project_id, limit=MAX_PAGE_SIZE))
        if stage in {"", "D"}:
            items.extend({**_public(item), "stage": "D", "asset_type": "output"} for item in repo.list_outputs(project_id, limit=MAX_PAGE_SIZE))
        if stage in {"", "review"}:
            items.extend({**_public(item), "stage": "review", "asset_type": "feedback"} for item in repo.list_feedback(project_id, limit=MAX_PAGE_SIZE))
        page, pagination = _paginate(items, limit, cursor)
        return _result(repo, project_id, {"stage": stage or "all", "items": page, "pagination": pagination})
    finally:
        repo.close()


def growth_source_triage(project_id: str, action: str = "get", source_id: str = "") -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"get", "run"})
    if not source_id:
        raise ValueError("source_id is required")
    repo = _repo()
    try:
        if not repo.get_source(project_id, source_id):
            raise KeyError("source not found in project")
        if action == "run":
            triage = SourceTriageService(repo).triage_source(project_id, source_id)
            status = "completed"
        else:
            records = [item for item in repo.list_triage(project_id, limit=MAX_PAGE_SIZE) if item.get("source_id") == source_id]
            triage = records[0] if records else None
            status = "completed" if triage else "not_run"
        return _result(repo, project_id, {"source_id": source_id, "triage": _public(triage), "status": status})
    finally:
        repo.close()


def growth_method(
    project_id: str,
    action: str = "list",
    method_id: str = "",
    proposal_id: str = "",
    status: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict[str, Any] | None = None,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "get", "propose", "review", "publish", "resolve", "revisions", "deprecate"})
    payload = payload or {}
    repo = _repo()
    try:
        if action == "list":
            records = repo.list_methods(project_id, status=status, limit=MAX_PAGE_SIZE)
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"methods": page, "pagination": pagination}
        elif action == "get":
            data = {"method": _required(repo.get_method(project_id, method_id), "method")}
        elif action == "propose":
            output_ids = list(dict.fromkeys(str(item) for item in payload.get("source_output_ids") or [] if str(item)))
            if len(output_ids) < 3:
                raise ValueError("method proposal requires three distinct accepted outputs")
            for output_id in output_ids:
                output = repo.get_output(project_id, output_id)
                if not output:
                    raise KeyError("source output not found in project")
                if output.get("status") != "accepted":
                    raise ValueError("method proposal requires accepted outputs")
            proposal = MethodDetector(repo).create_proposal(
                project_id,
                str(payload.get("slug") or ""),
                str(payload.get("body") or ""),
                output_ids,
                dict(payload.get("manifest") or {}),
            )
            data = {"proposal": _public(proposal), "publication_status": "proposal_only"}
        elif action == "review":
            proposal = _required(repo.get_method_proposal(project_id, proposal_id), "method proposal")
            evaluation = MethodEvaluator(repo).evaluate(
                proposal,
                comparable_uses=int(payload.get("comparable_uses", 0)),
                average_quality=float(payload.get("average_quality", 0)),
                groundedness=float(payload.get("groundedness", 0)),
                security_failures=int(payload.get("security_failures", 0)),
                regression_failures=int(payload.get("regression_failures", 0)),
            )
            data = {"proposal_id": proposal_id, "evaluation": evaluation}
        elif action == "publish":
            profile = repo.get_profile(project_id) or ProjectKnowledgeProfile(project_id=project_id).model_dump(mode="json")
            expected = payload.get("expected_profile_revision")
            if expected is not None and int(expected) != int(profile.get("revision") or 0):
                raise ValueError("project profile revision conflict")
            method = MethodGate(repo).publish_prompt_method(
                project_id=project_id,
                proposal_id=proposal_id,
                actor_id="mcp",
                policy_allows=str(profile.get("method_promotion_policy") or "gated") not in {"disabled", "manual_only"},
            )
            data = {"method": _public(method), "publication_status": "published"}
        elif action == "resolve":
            method = _required(repo.get_method(project_id, method_id), "method")
            revision = None
            if method.get("status") == "published" and method.get("active_revision_id"):
                revision = repo.get_method_revision(project_id, method["active_revision_id"])
            data = {
                "method": _public(method),
                "revision": _public(revision),
                "resolution_status": "available" if revision else "unavailable",
            }
        elif action == "revisions":
            _required(repo.get_method(project_id, method_id), "method")
            records = repo.list_method_revisions(
                project_id,
                method_id,
                limit=MAX_PAGE_SIZE,
            )
            page, pagination = _paginate(
                [_public(item) for item in records],
                limit,
                cursor,
            )
            data = {
                "method_id": method_id,
                "revisions": page,
                "pagination": pagination,
            }
        else:
            reason = _reason(payload)
            method = _required(repo.get_method(project_id, method_id), "method")
            if method.get("status") == "deprecated":
                deprecated = method
                idempotent = True
            elif method.get("status") != "published":
                raise GrowthStateConflictError(
                    "method state conflict: only a published method can be deprecated"
                )
            else:
                deprecated = _state_transition(
                    lambda: MethodRegistry(repo, _vault_root()).deprecate(
                        project_id,
                        method_id,
                        actor_id="mcp",
                        reason=reason,
                    ),
                    "method deprecation state conflict",
                )
                idempotent = False
            data = {"method": _public(deprecated), "idempotent": idempotent}
        return _result(repo, project_id, data)
    finally:
        repo.close()


def growth_output(
    project_id: str,
    action: str = "list",
    output_id: str = "",
    status: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict[str, Any] | None = None,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "get", "register", "evaluate", "file"})
    payload = payload or {}
    repo = _repo()
    try:
        if action == "list":
            records = repo.list_outputs(project_id, status=status, limit=MAX_PAGE_SIZE)
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"outputs": page, "pagination": pagination}
        elif action == "get":
            output = _required(repo.get_output(project_id, output_id), "output")
            data = {
                "output": _public(output),
                "evaluations": [_public(item) for item in repo.list_output_evaluations(project_id, output_id=output_id, limit=MAX_PAGE_SIZE)],
                "feedback": [_public(item) for item in repo.list_feedback(project_id, output_id=output_id, limit=MAX_PAGE_SIZE)],
            }
        elif action == "register":
            try:
                content = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("content_base64 is invalid") from exc
            values = {key: value for key, value in payload.items() if key not in {"content_base64", "metadata"}}
            output = OutputAsset(project_id=project_id, **values, metadata=redact_secrets(payload.get("metadata") or {}))
            registered = OutputRegistry(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).register_content(output, content)
            data = {"output": _public(registered)}
        elif action == "evaluate":
            components = dict(payload.get("components") or {})
            evaluation = OutputEvaluator(repo).evaluate(
                project_id=project_id,
                output_id=output_id,
                components=components,
                findings=list(payload.get("findings") or []),
            )
            data = {"evaluation": _public(evaluation)}
        else:
            reason = _reason(payload)
            output = _required(repo.get_output(project_id, output_id), "output")
            idempotent = output.get("status") == "filed"
            if output.get("status") not in {"accepted", "filed"}:
                raise GrowthStateConflictError(
                    "output state conflict: only an accepted output can be filed"
                )
            else:
                filed = _state_transition(
                    lambda: OutputRegistry(repo, _vault_root()).file_output(
                        project_id,
                        output_id,
                        actor_id="mcp",
                        reason=reason,
                    ),
                    "output filing state conflict",
                )
            _assert_output_immutable(output, filed)
            data = {"output": _public(filed), "idempotent": idempotent}
        return _result(repo, project_id, data)
    finally:
        repo.close()


def growth_feedback(
    project_id: str,
    action: str = "list",
    feedback_id: str = "",
    output_id: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict[str, Any] | None = None,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "create", "process"})
    payload = payload or {}
    repo = _repo()
    try:
        if action == "list":
            records = repo.list_feedback(project_id, output_id=output_id, limit=MAX_PAGE_SIZE)
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"feedback": page, "pagination": pagination}
        elif action == "create":
            feedback = repo.add_output_feedback(
                OutputFeedback(
                    project_id=project_id,
                    output_id=output_id,
                    actor_id=str(payload.get("actor_id") or "mcp"),
                    feedback_type=payload.get("feedback_type"),
                    rating=payload.get("rating"),
                    correction=str(payload.get("correction") or ""),
                    comment=str(payload.get("comment") or ""),
                )
            )
            data = {"feedback": _public(feedback)}
        else:
            data = {"review": _public(FeedbackRouter(repo).process(project_id, feedback_id))}
        return _result(repo, project_id, data)
    finally:
        repo.close()


def growth_summary(project_id: str) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    repo = _repo()
    try:
        sources = repo.list_sources(project_id)
        outputs = repo.list_outputs(project_id, limit=MAX_PAGE_SIZE)
        methods = repo.list_methods(project_id, limit=MAX_PAGE_SIZE)
        return _result(
            repo,
            project_id,
            {
                "counts": {
                    "sources": len(sources),
                    "eligible_sources": sum(item.get("status") == "eligible" for item in sources),
                    "pages": len(repo.list_pages(project_id)),
                    "methods": len(methods),
                    "published_methods": sum(item.get("status") == "published" for item in methods),
                    "outputs": len(outputs),
                    "accepted_outputs": sum(item.get("status") == "accepted" for item in outputs),
                    "rejected_outputs": sum(item.get("status") == "rejected" for item in outputs),
                    "feedback": len(repo.list_feedback(project_id, limit=MAX_PAGE_SIZE)),
                }
            },
        )
    finally:
        repo.close()


def growth_lineage(
    project_id: str,
    relation: str = "",
    limit: int = 100,
    cursor: str = "",
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    repo = _repo()
    try:
        records = repo.list_lineage(project_id, relation=relation, limit=MAX_PAGE_SIZE)
        page, pagination = _paginate([_public(item) for item in records], limit, cursor)
        return _result(repo, project_id, {"edges": page, "pagination": pagination})
    finally:
        repo.close()


def growth_review(
    project_id: str,
    action: str,
    target_id: str = "",
    minimum_uses: int = 3,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"feedback", "method_detection"})
    repo = _repo()
    try:
        if action == "feedback":
            if not target_id:
                raise ValueError("target_id is required")
            review = FeedbackRouter(repo).process(project_id, target_id)
        else:
            review = {
                "target_type": "method_detection",
                "proposals": MethodDetector(repo).detect(project_id, minimum_uses=minimum_uses),
            }
        return _result(repo, project_id, {"review": _public(review)})
    finally:
        repo.close()


def growth_schedule(
    project_id: str,
    action: str = "list",
    job_type: str = "",
    cron: str = "",
    timezone: str = "Asia/Shanghai",
    limit: int = 100,
    cursor: str = "",
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "create"})
    repo = _repo()
    try:
        if action == "list":
            records = [item for item in repo.list_schedules(project_id) if item.get("job_type") in GROWTH_JOB_TYPES]
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"schedules": page, "pagination": pagination}
        else:
            if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
                raise GrowthUnavailableError("knowledge schedules feature is disabled", _availability(repo, project_id))
            if job_type not in GROWTH_JOB_TYPES:
                raise ValueError("unsupported growth job type")
            schedule = WikiCommandService(repo).configure_schedule(
                project_id=project_id,
                job_type=job_type,
                cron=cron,
                timezone_name=timezone,
            )
            data = {"schedule": _public(schedule)}
        return _result(repo, project_id, data)
    finally:
        repo.close()


def growth_run(
    project_id: str,
    action: str = "list",
    run_id: str = "",
    job_type: str = "",
    idempotency_key: str = "",
    after_sequence: int = 0,
    limit: int = 100,
    cursor: str = "",
    payload: dict[str, Any] | None = None,
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "start", "get", "events"})
    payload = payload or {}
    repo = _repo()
    try:
        if action == "list":
            records = [item for item in repo.list_runs(project_id, limit=MAX_PAGE_SIZE) if item.get("run_type") in GROWTH_JOB_TYPES]
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"runs": page, "pagination": pagination}
        elif action == "get":
            data = {"run": _required(repo.get_run(project_id, run_id), "growth run")}
        elif action == "events":
            run = _required(repo.get_run(project_id, run_id), "growth run")
            latest = repo.latest_run_event_sequence(project_id=project_id, run_id=run_id)
            if after_sequence < 0 or after_sequence > latest:
                raise ValueError("after_sequence is outside persisted run history")
            events = repo.list_run_events(
                project_id=project_id,
                run_id=run_id,
                after_sequence=after_sequence,
                limit=_limit(limit),
            )
            data = {
                "run": _public(run),
                "events": [_public(item) for item in events],
                "pagination": {
                    "limit": _limit(limit),
                    "after_sequence": after_sequence,
                    "next_sequence": events[-1]["sequence"] if events and events[-1]["sequence"] < latest else None,
                    "count": len(events),
                },
            }
        else:
            if job_type not in GROWTH_JOB_TYPES:
                raise ValueError("unsupported growth job type")
            input_refs = {
                key: value
                for key, value in {
                    "date": payload.get("date"),
                    "week": payload.get("week"),
                    "source_cutoff": payload.get("source_cutoff"),
                }.items()
                if value
            }
            data = {
                "run": _start_run(
                    repo,
                    project_id=project_id,
                    job_type=job_type,
                    idempotency_key=idempotency_key,
                    input_refs=input_refs,
                )
            }
        return _result(repo, project_id, data)
    finally:
        repo.close()


def growth_distillation(
    project_id: str,
    action: str = "list",
    distillation_id: str = "",
    kind: str = "",
    week: str = "",
    source_cutoff: str = "",
    idempotency_key: str = "",
    limit: int = 100,
    cursor: str = "",
) -> dict:
    _require_enabled()
    project_id = _project(project_id)
    action = _action(action, {"list", "get", "start"})
    repo = _repo()
    try:
        if action == "list":
            if kind not in {"", "daily", "weekly"}:
                raise ValueError("kind must be daily, weekly, or empty")
            records = repo.list_growth_distillations(project_id, kind=kind, limit=MAX_PAGE_SIZE)
            page, pagination = _paginate([_public(item) for item in records], limit, cursor)
            data = {"distillations": page, "pagination": pagination}
        elif action == "get":
            records = repo.list_growth_distillations(project_id, limit=MAX_PAGE_SIZE)
            record = next((item for item in records if item.get("id") == distillation_id), None)
            data = {"distillation": _required(record, "distillation")}
        else:
            if not week or not source_cutoff:
                raise ValueError("week and source_cutoff are required")
            data = {
                "run": _start_run(
                    repo,
                    project_id=project_id,
                    job_type="growth_weekly_distillation",
                    idempotency_key=idempotency_key or f"weekly:{week}:{source_cutoff}",
                    input_refs={"week": week, "source_cutoff": source_cutoff},
                )
            }
        return _result(repo, project_id, data)
    finally:
        repo.close()


# Backward-compatible aliases retained for existing clients.
def growth_triage(project_id: str, source_id: str) -> dict:
    return growth_source_triage(project_id, action="run", source_id=source_id)


def growth_weekly_distill(project_id: str, week: str, source_cutoff: str) -> dict:
    _require_enabled()
    if not settings.OBSIDIAN_VAULT_ROOT:
        raise GrowthUnavailableError("OBSIDIAN_VAULT_ROOT is not configured", {"growth": True, "vault": False})
    project_id = _project(project_id)
    repo = _repo()
    try:
        value = GrowthDistillationService(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).run_weekly(
            project_id,
            week,
            source_cutoff=source_cutoff,
        )
        return _result(repo, project_id, {"distillation": _public(value)})
    finally:
        repo.close()


def _start_run(
    repo: GrowthRepository,
    *,
    project_id: str,
    job_type: str,
    idempotency_key: str,
    input_refs: dict[str, Any],
) -> dict[str, Any]:
    if not idempotency_key:
        return WikiCommandService(repo).start_run(
            project_id=project_id,
            job_type=job_type,
            trigger="mcp",
            input_refs=input_refs,
        )
    run = KnowledgeRun(
        project_id=project_id,
        run_type=job_type,
        trigger="mcp",
        status=RunStatus.QUEUED,
        actor_id="mcp",
        input_refs={**input_refs, "idempotency_key": idempotency_key},
    )
    claim = repo.claim_schedule_run(run, idempotency_key)
    if not claim["claimed"]:
        return {"status": "duplicate", "run_id": claim["run_id"], "duplicate": True}
    run_id = claim["run_id"]
    if not is_celery_real():
        from app.tasks.knowledge_tasks import execute_knowledge_run

        result = execute_knowledge_run(project_id, run_id, repository=repo)
        return {**result, "execution": "synchronous"}
    if not is_celery_broker_available():
        repo.update_run_status(
            project_id,
            run_id,
            RunStatus.UNAVAILABLE,
            error="durable scheduler unavailable because the Celery broker is unreachable",
            output_refs={"failure": {"code": "scheduler_unavailable", "retryable": True}},
        )
        return {"status": "unavailable", "run_id": run_id}
    from app.tasks.knowledge_tasks import knowledge_execute

    task = knowledge_execute.apply_async(args=[project_id, run_id])
    return {"status": "queued", "run_id": run_id, "task_id": task.id}


def _result(repo: GrowthRepository, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"project_id": project_id, **data, "availability": _availability(repo, project_id)}


def _availability(repo: GrowthRepository, project_id: str) -> dict[str, Any]:
    root = Path(settings.OBSIDIAN_VAULT_ROOT).resolve() if settings.OBSIDIAN_VAULT_ROOT else None
    return {
        "growth": bool(settings.KNOWLEDGE_GROWTH_ENABLED),
        "scheduler": bool(settings.KNOWLEDGE_SCHEDULES_ENABLED and is_celery_real() and is_celery_broker_available()),
        "vault": bool(repo.get_vault(project_id) and root and root.is_dir()),
        "mcp_write": bool(settings.KNOWLEDGE_MCP_WRITE_ENABLED),
    }


def _paginate(items: list[dict[str, Any]], limit: int, cursor: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_limit = _limit(limit)
    if not cursor:
        offset = 0
        normalized = None
    elif cursor.isdigit() and int(cursor) <= MAX_PAGE_SIZE:
        offset = int(cursor)
        normalized = cursor
    else:
        raise ValueError("cursor must be an integer between 0 and 500")
    total = min(len(items), MAX_PAGE_SIZE)
    end = min(offset + selected_limit, total)
    page = items[offset:end] if offset < total else []
    return page, {
        "limit": selected_limit,
        "cursor": normalized,
        "next_cursor": str(end) if end < total else None,
        "count": len(page),
    }


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_PAGE_SIZE:
        raise ValueError("limit must be between 1 and 500")
    return value


def _project(value: str) -> str:
    project_id = str(value or "").strip()
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("project_id has an invalid format")
    return project_id


def _action(value: str, allowed: set[str]) -> str:
    action = str(value or "").strip()
    if action not in allowed:
        raise ValueError(f"unsupported growth action: {action}")
    return action


def _required(value: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    if value is None:
        raise KeyError(f"{kind} not found in project")
    return _public(value)


def _reason(payload: dict[str, Any]) -> str:
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise ValueError("reason is required")
    if len(reason) > 500:
        raise ValueError("reason must not exceed 500 characters")
    return reason


def _vault_root() -> Path:
    configured = str(settings.OBSIDIAN_VAULT_ROOT or "").strip()
    if not configured:
        raise GrowthUnavailableError(
            "Obsidian Vault is not configured",
            {"growth": True, "vault": False},
        )
    root = Path(configured).resolve()
    if not root.is_dir():
        raise GrowthUnavailableError(
            "Obsidian Vault is unavailable",
            {"growth": True, "vault": False},
        )
    return root


def _state_transition(callback: Callable[[], dict[str, Any]], fallback_message: str) -> dict[str, Any]:
    try:
        return callback()
    except ValueError as exc:
        normalized = str(exc).lower()
        state_markers = (
            "state",
            "status",
            "accepted",
            "filed",
            "published",
            "deprecated",
        )
        if any(marker in normalized for marker in state_markers):
            raise GrowthStateConflictError(str(exc) or fallback_message) from exc
        raise


def _assert_output_immutable(before: dict[str, Any], after: dict[str, Any]) -> None:
    immutable_fields = (
        "id",
        "project_id",
        "content_hash",
        "vault_path",
        "idempotency_key",
    )
    if any(before.get(field) != after.get(field) for field in immutable_fields):
        raise RuntimeError("output filing changed immutable output identity")
    if after.get("status") != "filed":
        raise RuntimeError("output filing did not persist the filed state")


def _source(value: dict[str, Any]) -> dict[str, Any]:
    item = _public(value)
    item.pop("raw_content", None)
    return item


def _public(value: Any) -> Any:
    return redact_secrets(value)
