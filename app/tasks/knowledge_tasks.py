"""Celery entry points for persisted, auditable knowledge jobs."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.celery_app import get_celery_app, is_celery_real
from app.core.config import settings
from app.knowledge.distillation import DistillationError, WeeklyDistillationService
from app.knowledge.context_pack import ContextPackBuilder
from app.knowledge.horizon_client import HorizonClient, HorizonClientError
from app.knowledge.horizon_import import HorizonImportService
from app.knowledge.horizon_run_store import (
    HorizonRunStoreClient,
    HorizonRunStoreEmptyError,
    resolve_horizon_run_store_location,
)
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.growth_scheduler import GrowthScheduleCoordinator
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.obsidian_output_sync import ObsidianOutputSyncService
from app.knowledge.wiki_sync import ObsidianSyncService
from app.knowledge.wiki_compiler import WikiCompilationError, WikiCompiler
from app.knowledge.proposal_gate import ProposalGateError
from app.knowledge.wiki_index import WikiSearchIndex
from app.knowledge.wiki_llm_provider import SOPWikiCompilerProvider
from app.knowledge.growth_contracts import KnowledgeFailureCode, KnowledgeFailureRecord
from app.knowledge.wiki_contracts import RunStatus
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import parse_project_rules, RuleValidationError
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge import metrics as knowledge_metrics
from app.tasks.growth_tasks import (
    GROWTH_RUN_TYPES,
    execute_growth_run,
    growth_execute,
    recover_abandoned_growth_runs,
)


@dataclass(frozen=True)
class KnowledgeFailure:
    category: str
    code: str
    retryable: bool


def classify_knowledge_failure(exc: Exception) -> KnowledgeFailure:
    message = str(exc).lower()
    if isinstance(exc, HorizonClientError):
        return KnowledgeFailure("transient_dependency", "horizon_unavailable", True)
    if isinstance(exc, WikiCompilationError):
        return KnowledgeFailure("compiler", "compiler_failed", False)
    if isinstance(exc, ProposalGateError) or "publication gate" in message:
        return KnowledgeFailure("gate", "publication_gate_failed", False)
    if isinstance(exc, DistillationError) and "conflict" in message:
        return KnowledgeFailure("write_conflict", "distillation_conflict", False)
    if isinstance(exc, UnicodeError):
        return KnowledgeFailure("extraction", "extraction_failed", False)
    if isinstance(exc, PermissionError):
        return KnowledgeFailure("policy", "permission_denied", False)
    if "not configured" in message or "required" in message:
        return KnowledgeFailure("configuration", "configuration_missing", False)
    return KnowledgeFailure("transient_dependency", "unexpected_dependency_failure", True)


def _record_terminal_failure(
    repo: WikiRepository,
    *,
    project_id: str,
    run_id: str,
    status: RunStatus,
    message: str,
    failure: KnowledgeFailure,
    output_refs: dict | None = None,
) -> dict:
    event = repo.append_run_event(
        project_id=project_id,
        run_id=run_id,
        event_type="knowledge.run.failure_recorded",
        payload={"failure": failure.__dict__, "message": message[:2_000]},
    )
    failure_code = _failure_record_code(failure)
    failure_id = ""
    try:
        growth_repo = repo if isinstance(repo, GrowthRepository) else GrowthRepository.borrow(repo)
        stored = growth_repo.create_failure_record(
            KnowledgeFailureRecord(
                project_id=project_id,
                code=failure_code,
                severity="warning" if status is RunStatus.UNAVAILABLE else "error",
                summary=message,
                run_id=run_id,
                event_sequence=event["sequence"],
                evidence_refs=[f"run:{run_id}", f"event:{event['id']}"],
                root_cause=f"{failure.category}:{failure.code}",
                retryable=failure.retryable,
            )
        )
        failure_id = str(stored["id"])
    except Exception:
        # A terminal run must still record its original failure when an additive
        # diagnostics table is unavailable during recovery or migration.
        failure_id = ""
    refs = {
        **(output_refs or {}),
        "failure": failure.__dict__,
        "failure_record_id": failure_id,
    }
    repo.update_run_status(project_id, run_id, status, error=message, output_refs=refs)
    return {
        "status": status.value,
        "run_id": run_id,
        "error": message,
        "failure": failure.__dict__,
    }


def _failure_record_code(failure: KnowledgeFailure) -> KnowledgeFailureCode:
    if failure.code.startswith("horizon_"):
        return KnowledgeFailureCode.SOURCE_CAPTURE_FAILURE
    if failure.category == "configuration":
        return KnowledgeFailureCode.CONFIGURATION_DRIFT
    if failure.category == "extraction":
        return KnowledgeFailureCode.CHUNK_SEGMENTATION
    if failure.category == "policy":
        return KnowledgeFailureCode.TOOL_MISUSE
    if failure.category == "write_conflict":
        return KnowledgeFailureCode.PROJECT_SCOPE_INTERFERENCE
    if failure.category == "gate":
        return KnowledgeFailureCode.EVALUATION_BLIND_SPOT
    return KnowledgeFailureCode.DEPENDENCY_UNREADY


def _imported_horizon_run_ids(repository: WikiRepository, project_id: str) -> set[str]:
    return repository.list_completed_horizon_run_ids(project_id)


def execute_knowledge_run(
    project_id: str, run_id: str, schedule_id: str = "", week: str = "", repository: WikiRepository | None = None
) -> dict:
    """Execute one persisted job; unsupported or ungrounded work remains explicitly unavailable."""
    started_perf = time.perf_counter()
    repo = repository or WikiRepository()
    owns_repository = repository is None
    run = None
    try:
        run = repo.get_run(project_id, run_id)
        if not run:
            raise ValueError("knowledge run not found")
        if run["status"] in {"completed", "failed", "cancelled", "unavailable"}:
            return {
                "status": run["status"],
                "run_id": run_id,
                "duplicate": True,
                "output_refs": run.get("output_refs") or {},
            }
        growth_run = run["run_type"] in {"growth_daily", "growth_weekly_distillation"}
        if growth_run and not settings.KNOWLEDGE_GROWTH_ENABLED:
            return _record_terminal_failure(
                repo,
                project_id=project_id,
                run_id=run_id,
                status=RunStatus.UNAVAILABLE,
                message="Knowledge growth feature is disabled",
                failure=KnowledgeFailure("configuration", "knowledge_growth_disabled", False),
            )
        if not growth_run and not settings.KNOWLEDGE_WIKI_ENABLED:
            return _record_terminal_failure(
                repo,
                project_id=project_id,
                run_id=run_id,
                status=RunStatus.UNAVAILABLE,
                message="Project Wiki feature is disabled",
                failure=KnowledgeFailure("configuration", "knowledge_wiki_disabled", False),
            )
        if growth_run:
            return execute_growth_run(
                project_id,
                run_id,
                schedule_id=schedule_id,
                week=week,
                repository=repo,
            )
        repo.update_run_status(project_id, run_id, RunStatus.RUNNING)
        if run["run_type"] == "source_sync":
            if not settings.KNOWLEDGE_OBSIDIAN_SYNC_ENABLED:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="Obsidian synchronization feature is disabled",
                    failure=KnowledgeFailure("configuration", "obsidian_sync_disabled", False),
                )
            mapping = repo.get_vault(project_id)
            if not settings.OBSIDIAN_VAULT_ROOT or not mapping:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="Obsidian Vault is not configured",
                    failure=KnowledgeFailure("configuration", "vault_not_configured", False),
            )
            report = ObsidianSyncService(repo, Path(settings.OBSIDIAN_VAULT_ROOT)).sync(project_id=project_id)
            managed_vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
            if managed_vault.project_root.is_dir():
                snapshot = managed_vault.contents
                repo.record_publication(project_id=project_id, contents=snapshot, source_ids=[])
                report["wiki_index"] = WikiSearchIndex(repo).sync_wiki_snapshot(
                    project_id=project_id,
                    contents=snapshot,
                )
                report["wiki_pages"] = len([path for path in snapshot if path == "AGENTS.md" or path.startswith("wiki/")])
                repo.append_run_event(
                    project_id=project_id,
                    run_id=run_id,
                    event_type="knowledge.wiki.snapshot.synced",
                    payload={"pages": report["wiki_pages"]},
                )
            else:
                report["wiki_pages"] = 0
                report["wiki_index"] = {"indexed": 0, "removed": 0, "failures": []}
            # Snapshot rebuilding replaces derived Wiki edges. Register D-layer
            # output lineage afterwards so its run-to-output audit edge persists.
            growth_repo = repo if isinstance(repo, GrowthRepository) else GrowthRepository.borrow(repo)
            report["output_feedback"] = ObsidianOutputSyncService(
                growth_repo, Path(settings.OBSIDIAN_VAULT_ROOT)
            ).sync(project_id=project_id, run_id=run_id)
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.source.sync.completed", payload=report
            )
            repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs={"sync": report})
            return {"status": "completed", "run_id": run_id, "sync": report}
        if run["run_type"] == "horizon_capture":
            run_store_location = resolve_horizon_run_store_location(
                runs_root=settings.HORIZON_RUNS_ROOT,
                host_path=settings.HORIZON_RUNS_HOST_PATH,
            )
            if not settings.HORIZON_ENABLED or not (run_store_location.configured or settings.HORIZON_API_BASE_URL):
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="Horizon artifact source is not configured",
                    failure=KnowledgeFailure("configuration", "horizon_not_configured", False),
                    output_refs={"outcome": "configuration_error", "source_mode": "unconfigured", "items_observed": 0},
                )
            horizon_run_id = str(run["input_refs"].get("horizon_run_id") or "").strip()
            stage = str(run["input_refs"].get("stage") or "filtered")
            discovery = not horizon_run_id
            if discovery and not run_store_location.available:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    message="Horizon run ID is required for the HTTP compatibility source",
                    failure=KnowledgeFailure("configuration", "horizon_run_id_missing", False),
                    output_refs={"outcome": "configuration_error", "source_mode": "http", "items_observed": 0},
                )
            source_mode = "run_store" if run_store_location.available else "http"
            try:
                if run_store_location.available:
                    run_store = HorizonRunStoreClient(
                        runs_root=run_store_location.path,
                        max_response_bytes=settings.HORIZON_MAX_RESPONSE_BYTES,
                    )
                    if discovery:
                        response = run_store.fetch_latest_stage(
                            exclude_run_ids=_imported_horizon_run_ids(repo, project_id)
                        )
                        horizon_run_id = response.run_id
                        stage = response.stage
                    else:
                        response = run_store.fetch_stage(run_id=horizon_run_id, stage=stage)
                else:
                    response = HorizonClient(
                        base_url=settings.HORIZON_API_BASE_URL,
                        api_key=settings.HORIZON_API_KEY,
                        stage_url_template=settings.HORIZON_STAGE_URL_TEMPLATE,
                        timeout_seconds=settings.HORIZON_TIMEOUT_SECONDS,
                        max_response_bytes=settings.HORIZON_MAX_RESPONSE_BYTES,
                        allow_private_network=settings.HORIZON_ALLOW_PRIVATE_NETWORK,
                    ).fetch_stage(run_id=horizon_run_id, stage=stage)
                report = HorizonImportService(repo).import_items(
                    project_id=project_id,
                    run_id=response.run_id,
                    stage=response.stage,
                    items=response.items,
                    capture_run_id=run_id,
                )
            except HorizonRunStoreEmptyError:
                report = {"accepted": 0, "created": 0, "duplicates": 0, "rejected": 0, "skipped": True}
                repo.append_run_event(
                    project_id=project_id,
                    run_id=run_id,
                    event_type="knowledge.horizon.capture.skipped",
                    payload={"reason": "no_new_artifact", "source_mode": "run_store", "discovery": True},
                )
                output_refs = {
                    "horizon": report,
                    "horizon_run_id": "",
                    "stage": "",
                    "source_mode": "run_store",
                    "discovery": True,
                    "outcome": "no_new_artifact",
                    "items_observed": 0,
                }
                repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs=output_refs)
                return {"status": "completed", "run_id": run_id, "horizon": report, "output_refs": output_refs}
            except HorizonClientError as exc:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    message=str(exc),
                    failure=classify_knowledge_failure(exc),
                    output_refs={
                        "outcome": "channel_error",
                        "source_mode": source_mode,
                        "horizon_run_id": horizon_run_id,
                        "stage": stage,
                        "discovery": discovery,
                        "items_observed": 0,
                    },
                )
            items_observed = len(response.items)
            outcome = "empty_result" if items_observed == 0 else "processed"
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.horizon.capture.completed",
                payload={
                    "horizon_run_id": horizon_run_id,
                    "stage": stage,
                    "source_mode": source_mode,
                    "run_store_resolution": run_store_location.mode if source_mode == "run_store" else "http",
                    "discovery": discovery,
                    "outcome": outcome,
                    "items_observed": items_observed,
                    **report,
                },
            )
            repo.update_run_status(
                project_id,
                run_id,
                RunStatus.COMPLETED,
                output_refs={
                    "horizon": report,
                    "horizon_run_id": horizon_run_id,
                    "stage": stage,
                    "source_mode": source_mode,
                    "run_store_resolution": run_store_location.mode if source_mode == "run_store" else "http",
                    "discovery": discovery,
                    "outcome": outcome,
                    "items_observed": items_observed,
                },
            )
            return {"status": "completed", "run_id": run_id, "horizon": report}
        if run["run_type"] == "wiki_maintenance":
            if not settings.OBSIDIAN_VAULT_ROOT:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="Obsidian Vault is not configured",
                    failure=KnowledgeFailure("configuration", "vault_not_configured", False),
                )
            mapping = repo.get_vault(project_id)
            if not mapping:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="project Vault mapping is not configured",
                    failure=KnowledgeFailure("configuration", "vault_mapping_missing", False),
                )
            vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
            rules_path = vault.project_root / "AGENTS.md"
            if not rules_path.is_file():
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="project AGENTS.md is required",
                    failure=KnowledgeFailure("configuration", "project_rules_missing", False),
                )
            page_snapshots = []
            for page in repo.list_pages(project_id):
                content = repo.get_page_content(project_id, page["id"])
                if content:
                    page_snapshots.append({**page, "content": content["content"]})
            if not any(page.get("path") == "AGENTS.md" for page in page_snapshots):
                page_snapshots.append({"project_id": project_id, "path": "AGENTS.md", "content": rules_path.read_text(encoding="utf-8")})
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
                failure = (
                    KnowledgeFailure("configuration", "wiki_llm_provider_not_configured", False)
                    if status is RunStatus.UNAVAILABLE
                    else classify_knowledge_failure(exc)
                )
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=status,
                    message=reason,
                    failure=failure,
                )
            repo.append_run_event(
                project_id=project_id, run_id=run_id, event_type="knowledge.proposal.created",
                payload={"proposal_id": result.proposal["id"], "compiler_run_id": result.run["id"]},
            )
            publication = {"status": "review_required"}
            mapping_policy = mapping.get("metadata") or {}
            if settings.KNOWLEDGE_WIKI_AUTO_PUBLISH_ENABLED and mapping_policy.get("auto_publish_enabled") is True:
                from app.knowledge.wiki_commands import WikiCommandError, WikiCommandService

                try:
                    publication = WikiCommandService(repo).publish_proposal(
                        project_id=project_id,
                        proposal_id=result.proposal["id"],
                        publication_mode="automatic",
                        actor_id="knowledge-task",
                        actor_role="system",
                    )
                except WikiCommandError as exc:
                    failure = KnowledgeFailure("gate", "publication_gate_failed", False)
                    output_refs = {
                        "proposal_id": result.proposal["id"],
                        "compiler_run_id": result.run["id"],
                        "failure": failure.__dict__,
                    }
                    repo.update_run_status(
                        project_id,
                        run_id,
                        RunStatus.FAILED,
                        error=str(exc),
                        output_refs=output_refs,
                    )
                    return {
                        "status": "failed",
                        "run_id": run_id,
                        "proposal_id": result.proposal["id"],
                        "failure": failure.__dict__,
                    }
            output_refs = {
                "proposal_id": result.proposal["id"],
                "compiler_run_id": result.run["id"],
                "publication": publication,
            }
            repo.update_run_status(project_id, run_id, RunStatus.COMPLETED, output_refs=output_refs)
            return {
                "status": "completed",
                "run_id": run_id,
                "proposal_id": result.proposal["id"],
                "publication": publication,
            }
        if run["run_type"] == "knowledge_lint_eval":
            mapping = repo.get_vault(project_id)
            if not settings.OBSIDIAN_VAULT_ROOT or not mapping:
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="Obsidian Vault is not configured",
                    failure=KnowledgeFailure("configuration", "vault_not_configured", False),
                )
            vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
            rules_path = vault.project_root / "AGENTS.md"
            if not rules_path.is_file():
                return _record_terminal_failure(
                    repo,
                    project_id=project_id,
                    run_id=run_id,
                    status=RunStatus.UNAVAILABLE,
                    message="project AGENTS.md is required",
                    failure=KnowledgeFailure("configuration", "project_rules_missing", False),
                )
            rules = parse_project_rules(rules_path.read_text(encoding="utf-8"))
            pages = []
            for page in repo.list_pages(project_id):
                content = repo.get_page_content(project_id, page["id"])
                pages.append({**page, "content": content["content"] if content else ""})
            sources = repo.list_sources(project_id)
            lint = WikiLint().lint_project(project_id=project_id, rules=rules, pages=pages, sources=sources)
            candidate_sources = sorted({
                citation["source_id"] for citation in repo.list_citations(project_id, include_stale=False)
            })
            evaluation = WikiEvaluator(repo).evaluate(
                project_id=project_id,
                wiki_revision=hashlib.sha256(
                    "|".join(f"{page['id']}:{page['content_hash']}" for page in pages).encode("utf-8")
                ).hexdigest(),
                candidate={
                    "source_ids": candidate_sources,
                    "retrieved_source_ids": candidate_sources,
                    "content": "\n".join(page["content"] for page in pages),
                },
            )
            output = {
                "lint": {"valid": lint.valid, "findings": [finding.model_dump() for finding in lint.findings]},
                "evaluation": evaluation.model_dump(),
            }
            terminal = (
                RunStatus.UNAVAILABLE if evaluation.status == "unavailable"
                else RunStatus.COMPLETED if lint.valid and evaluation.status == "passed"
                else RunStatus.FAILED
            )
            if terminal is not RunStatus.COMPLETED:
                output["failure"] = KnowledgeFailure(
                    "gate",
                    "evaluation_baseline_missing" if terminal is RunStatus.UNAVAILABLE else "knowledge_quality_regression",
                    False,
                ).__dict__
            repo.append_run_event(
                project_id=project_id,
                run_id=run_id,
                event_type="knowledge.quality.completed",
                payload={"lint_valid": lint.valid, "evaluation_status": evaluation.status},
            )
            repo.update_run_status(
                project_id,
                run_id,
                terminal,
                error="" if terminal is RunStatus.COMPLETED else "knowledge quality gate did not pass",
                output_refs=output,
            )
            return {"status": terminal.value, "run_id": run_id, **output}
        if run["run_type"] != "weekly_distillation":
            return _record_terminal_failure(
                repo,
                project_id=project_id,
                run_id=run_id,
                status=RunStatus.UNAVAILABLE,
                message="knowledge executor not configured",
                failure=KnowledgeFailure("configuration", "executor_not_configured", False),
            )
        from app.knowledge.source_triage import source_admission_reason

        sources = [
            source
            for source in repo.list_sources(project_id, status="eligible")
            if not source_admission_reason(repo, project_id, source)
        ]
        if not sources:
            return _record_terminal_failure(
                repo,
                project_id=project_id,
                run_id=run_id,
                status=RunStatus.UNAVAILABLE,
                message="no eligible source evidence",
                failure=KnowledgeFailure("policy", "no_eligible_evidence", False),
            )
        mapping = repo.get_vault(project_id)
        if not settings.OBSIDIAN_VAULT_ROOT or not mapping:
            return _record_terminal_failure(
                repo,
                project_id=project_id,
                run_id=run_id,
                status=RunStatus.UNAVAILABLE,
                message="Obsidian Vault is not configured",
                failure=KnowledgeFailure("configuration", "vault_not_configured", False),
            )
        vault = FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, mapping["vault_path"])
        rules_path = vault.project_root / "AGENTS.md"
        rule_revision = hashlib.sha256(
            rules_path.read_bytes() if rules_path.exists() else b""
        ).hexdigest()
        selected_week = week or _iso_week()
        pages = []
        for page in repo.list_pages(project_id):
            content = repo.get_page_content(project_id, page["id"])
            pages.append({**page, "content": content["content"] if content else ""})
        evaluations = repo.list_eval_runs(project_id, limit=20)
        contradictions = [
            {"source_id": source["id"], "contradicts_source_id": target}
            for source in sources
            for target in source.get("metadata", {}).get("contradicts_source_ids", [])
            if isinstance(target, str)
        ]
        context_pack = None
        try:
            rules = parse_project_rules(rules_path.read_text(encoding="utf-8"))
            context_pack = ContextPackBuilder(max_characters=8_000).build(
                project_id=project_id,
                rules=rules,
                pages=pages,
                sources=sources,
                evaluations=[
                    {
                        "id": evaluation["id"],
                        "project_id": project_id,
                        "content": f"Status: {evaluation['status']}; findings: {evaluation.get('summary', {}).get('findings', [])}",
                    }
                    for evaluation in evaluations
                ],
            )
        except RuleValidationError:
            context_pack = None
        source_cutoff = WeeklyDistillationService.source_cutoff(sources)
        bundle = WeeklyDistillationService(vault).distill(
            project_id=project_id,
            week=selected_week,
            sources=sources,
            pages=pages,
            rule_revision=rule_revision,
            source_cutoff=source_cutoff,
            evaluations=evaluations,
            contradictions=contradictions,
            context_pack=context_pack,
        )
        distillation = repo.record_distillation(
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
            output_refs={
                "week": selected_week,
                "paths": list(bundle.paths),
                "schedule_id": schedule_id,
                "source_cutoff": source_cutoff,
                "distillation_id": distillation["id"],
            },
        )
        return {
            "status": "completed",
            "run_id": run_id,
            "paths": list(bundle.paths),
            "source_cutoff": source_cutoff,
            "distillation_id": distillation["id"],
        }
    except DistillationError as exc:
        failure = classify_knowledge_failure(exc)
        repo.update_run_status(
            project_id,
            run_id,
            RunStatus.FAILED,
            error=str(exc),
            output_refs={"failure": failure.__dict__},
        )
        return {"status": "failed", "run_id": run_id, "error": str(exc), "failure": failure.__dict__}
    except Exception as exc:
        failure = classify_knowledge_failure(exc)
        if run is not None:
            repo.update_run_status(
                project_id,
                run_id,
                RunStatus.FAILED,
                error=str(exc),
                output_refs={"failure": failure.__dict__},
            )
        return {"status": "failed", "run_id": run_id, "error": str(exc), "failure": failure.__dict__}
    finally:
        if run is not None:
            persisted = repo.get_run(project_id, run_id)
            if persisted and persisted["status"] in {"completed", "failed", "cancelled", "unavailable"}:
                try:
                    created = datetime.fromisoformat(str(persisted["created_at"]).replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    queue_delay_ms = max(0.0, (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() * 1000.0)
                except (TypeError, ValueError):
                    queue_delay_ms = 0.0
                knowledge_metrics.metrics.record_knowledge_run(
                    status=persisted["status"],
                    queue_delay_ms=queue_delay_ms,
                    runtime_ms=(time.perf_counter() - started_perf) * 1000.0,
                    retry_count=1 if persisted.get("retry_of") else 0,
                    distillation_freshness_seconds=0.0 if persisted["run_type"] == "weekly_distillation" and persisted["status"] == "completed" else None,
                )
        if owns_repository:
            repo.close()


def _iso_week() -> str:
    value = date.today().isocalendar()
    return f"{value.year}-W{value.week:02d}"


def reconcile_knowledge_schedules(now: datetime | None = None) -> dict:
    """Claim due persistent schedules and enqueue runs exactly once per due instant."""
    if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
        return {"queued": 0, "duplicates": 0, "failures": 0, "recovered": 0, "unavailable": True}
    repo = WikiRepository()
    current = now or datetime.now(timezone.utc)
    queued = 0
    duplicates = 0
    failures = 0
    try:
        scheduler = KnowledgeScheduler(repo, scheduler_available=True)
        durable_growth_tasks = bool(settings.CELERY_ENABLED and is_celery_real())
        growth_recovery = (
            recover_abandoned_growth_runs(
                repo,
                now=current,
                timeout_seconds=max(60, settings.CELERY_TASK_TIMEOUT),
                dispatch=lambda project_id, run_id: _submit_task(growth_execute, [project_id, run_id]),
            )
            if durable_growth_tasks
            else {"recovered": 0, "failures": 0}
        )
        failures += growth_recovery["failures"]
        recovered = scheduler.recover_abandoned_runs(now=current, timeout_seconds=max(60, settings.CELERY_TASK_TIMEOUT))
        growth_scheduler = GrowthScheduleCoordinator(repo, scheduler_available=True)
        for schedule in repo.list_due_schedules(current.isoformat()):
            due_at = str(schedule["next_run_at"])
            growth_job = schedule["job_type"] in GROWTH_RUN_TYPES
            if growth_job:
                if not durable_growth_tasks:
                    repo.set_schedule_enabled(
                        project_id=schedule["project_id"],
                        schedule_id=schedule["id"],
                        enabled=False,
                        next_run_at="",
                    )
                    failures += 1
                    continue
                parsed_due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                claim = growth_scheduler.claim_scheduled_run(schedule, due_at=parsed_due_at)
                if claim.get("status") == "waiting_for_daily":
                    continue
                claimed_run = repo.get_run(schedule["project_id"], claim["run_id"])
                idempotency_key = str((claimed_run or {}).get("input_refs", {}).get("idempotency_key") or "")
            else:
                idempotency_key = f"{schedule['id']}:{due_at}"
                claim = scheduler.claim_run(
                    project_id=schedule["project_id"],
                    job_type=schedule["job_type"],
                    idempotency_key=idempotency_key,
                    trigger="schedule",
                )
            if not claim["claimed"]:
                duplicates += 1
                if _run_was_dispatched(repo, schedule["project_id"], claim["run_id"]):
                    _advance_claimed_schedule(repo, scheduler, schedule, due_at, current)
                    continue
                # A broker can acknowledge a task to the wrong runtime when
                # two deployments shared the default queue. No dispatch event
                # means this durable claim has no proof it reached the owner,
                # so re-submit it through the current runtime's routed queue.
                try:
                    selected_task = growth_execute if growth_job else knowledge_execute
                    _submit_task(selected_task, [schedule["project_id"], claim["run_id"], schedule["id"]])
                    _record_dispatched_run(
                        repo,
                        schedule["project_id"],
                        claim["run_id"],
                        schedule_id=schedule["id"],
                        due_at=due_at,
                        growth_job=growth_job,
                    )
                    if _advance_claimed_schedule(repo, scheduler, schedule, due_at, current):
                        queued += 1
                    else:
                        duplicates += 1
                except Exception as exc:
                    failures += 1
                    if not growth_job:
                        repo.update_run_status(schedule["project_id"], claim["run_id"], RunStatus.FAILED, error=f"queue recovery failed: {exc}")
                continue
            try:
                selected_task = growth_execute if growth_job else knowledge_execute
                _submit_task(selected_task, [schedule["project_id"], claim["run_id"], schedule["id"]])
                _record_dispatched_run(
                    repo,
                    schedule["project_id"],
                    claim["run_id"],
                    schedule_id=schedule["id"],
                    due_at=due_at,
                    growth_job=growth_job,
                )
                advanced = _advance_claimed_schedule(repo, scheduler, schedule, due_at, current)
                if advanced:
                    queued += 1
                else:
                    duplicates += 1
            except Exception as exc:
                failures += 1
                if not growth_job:
                    repo.update_run_status(schedule["project_id"], claim["run_id"], RunStatus.FAILED, error=f"queue submission failed: {exc}")
                    repo.release_schedule_claim(
                        project_id=schedule["project_id"], job_type=schedule["job_type"], idempotency_key=idempotency_key
                    )
        return {
            "queued": queued,
            "duplicates": duplicates,
            "failures": failures,
            "recovered": len(recovered) + growth_recovery["recovered"],
        }
    finally:
        repo.close()


def _submit_task(task, args: list[str]):
    submitted = task.apply_async(args=args)
    if hasattr(submitted, "failed") and submitted.failed():
        raise RuntimeError(str(getattr(submitted, "info", "queue submission failed")))
    return submitted


def _run_was_dispatched(repository: WikiRepository, project_id: str, run_id: str) -> bool:
    return any(
        event["event_type"] in {"knowledge.run.execution_dispatched", "knowledge.growth.dispatched"}
        for event in repository.list_run_events(project_id=project_id, run_id=run_id)
    )


def _record_dispatched_run(
    repository: WikiRepository,
    project_id: str,
    run_id: str,
    *,
    schedule_id: str,
    due_at: str,
    growth_job: bool,
) -> None:
    payload = {"schedule_id": schedule_id, "due_at": due_at}
    repository.append_run_event(
        project_id=project_id,
        run_id=run_id,
        event_type="knowledge.run.execution_dispatched",
        payload=payload,
    )
    if growth_job:
        repository.append_run_event(
            project_id=project_id,
            run_id=run_id,
            event_type="knowledge.growth.dispatched",
            payload=payload,
        )


def _advance_claimed_schedule(
    repository: WikiRepository,
    scheduler: KnowledgeScheduler,
    schedule: dict,
    due_at: str,
    current: datetime,
) -> bool:
    next_run = scheduler.next_run(
        schedule["cron"], current, timezone_name=str(schedule.get("timezone") or "UTC")
    ).isoformat()
    return repository.advance_schedule(
        schedule_id=schedule["id"],
        expected_next_run_at=due_at,
        next_run_at=next_run,
        last_run_at=current.isoformat(),
    )


celery_app = get_celery_app()


@celery_app.task(name="knowledge.execute")
def knowledge_execute(project_id: str, run_id: str, schedule_id: str = "", week: str = "") -> dict:
    return execute_knowledge_run(project_id, run_id, schedule_id=schedule_id, week=week)


@celery_app.task(name="knowledge.reconcile_schedules")
def knowledge_reconcile_schedules() -> dict:
    return reconcile_knowledge_schedules()
