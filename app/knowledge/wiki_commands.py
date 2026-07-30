"""Governed command service shared by the Wiki REST and MCP transports."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.celery_app import is_celery_broker_available, is_celery_real
from app.core.config import settings
from app.knowledge.proposal_gate import ProposalGate, ProposalGateError
from app.knowledge.scheduler import KnowledgeScheduler, ScheduleValidationError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import KnowledgeRun, ProposalStatus, RunStatus, WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import ProjectRules, parse_project_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService
from app.knowledge.obsidian_source_projection import ObsidianSourceProjection


class WikiCommandError(ValueError):
    """Raised for a command that cannot safely alter the governed Wiki state."""


class WikiCommandService:
    """Create and execute project-scoped Wiki commands without bypassing the gate."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def create_proposal(self, payload: dict[str, Any], *, actor_id: str = "") -> dict:
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id:
            raise WikiCommandError("project_id is required")
        vault = self._vault(project_id)
        operation_source_ids = [
            str(source_id)
            for operation in payload.get("operations") or []
            if isinstance(operation, dict)
            for source_id in operation.get("source_ids") or []
            if str(source_id)
        ]
        payload = {
            **payload,
            "source_ids": list(dict.fromkeys(
                [str(source_id) for source_id in payload.get("source_ids") or [] if str(source_id)]
                + operation_source_ids
            )),
        }
        payload = self._with_overview_operation(payload, vault.contents)
        if not payload.get("base_revision"):
            payload = {**payload, "base_revision": ProposalGate.project_revision(vault.contents)}
        try:
            proposal = WikiProposal.model_validate({**payload, "manual": True, "status": ProposalStatus.DRAFT})
        except Exception as exc:
            raise WikiCommandError(f"invalid Wiki proposal: {exc}") from exc
        return self.repository.create_proposal(proposal, actor_id=actor_id)

    @staticmethod
    def _with_overview_operation(payload: dict[str, Any], existing: dict[str, str]) -> dict[str, Any]:
        operations = list(payload.get("operations") or [])
        substantive = [
            operation for operation in operations
            if isinstance(operation, dict) and operation.get("path") not in {"wiki/index.md", "wiki/log.md", "wiki/overview.md"}
        ]
        if not substantive or any(
            isinstance(operation, dict) and operation.get("path") == "wiki/overview.md" for operation in operations
        ):
            return payload
        source_ids = list(dict.fromkeys(str(value) for value in payload.get("source_ids") or [] if str(value)))
        citations = " ".join(f"[source:{source_id}]" for source_id in source_ids)
        overview_content = existing.get("wiki/overview.md", "")
        missing_overview_links = [
            f"[[{operation['path']}]]"
            for operation in substantive
            if operation.get("path") and f"[[{operation['path']}]]" not in overview_content
        ]
        if "wiki/overview.md" in existing and not missing_overview_links and all(
            operation.get("operation") == "replace" for operation in substantive
        ):
            return payload
        links = ", ".join(missing_overview_links or [
            f"[[{operation['path']}]]" for operation in substantive if operation.get("path")
        ])
        if "wiki/overview.md" in existing:
            overview = {
                "operation": "append",
                "path": "wiki/overview.md",
                "content": f"\n- Governed update: {links}. {citations}\n",
                "source_ids": source_ids,
            }
        else:
            overview = {
                "operation": "create",
                "path": "wiki/overview.md",
                "content": (
                    "---\ntitle: Project Overview\nkind: brief\nstatus: draft\n---\n"
                    f"# Project Overview\n\n- Governed update: {links}. {citations}\n"
                ),
                "source_ids": source_ids,
            }
        return {**payload, "operations": [*operations, overview]}

    def capture_source(self, payload: dict[str, Any], *, actor_id: str = "") -> dict:
        try:
            source_input = CapturedSourceInput.model_validate(payload)
        except Exception as exc:
            raise WikiCommandError(f"invalid immutable source payload: {exc}") from exc
        if not self.repository.get_vault(source_input.project_id):
            raise WikiCommandError("project Vault mapping is not configured")
        run = KnowledgeRun(
            project_id=source_input.project_id,
            run_type="source_capture",
            trigger="http",
            actor_id=actor_id,
            status=RunStatus.QUEUED,
            input_refs={"source_type": source_input.source_type, "origin": source_input.origin},
        )
        self.repository.create_run(run)
        self.repository.update_run_status(source_input.project_id, run.id, RunStatus.RUNNING)
        try:
            source_input = source_input.model_copy(update={"capture_run_id": run.id})
            result = SourceCaptureService(self.repository).capture(source_input)
            source = result.source
            mirror = self._sync_evidence_mirror(source_input.project_id, source["id"])
            attempt = self.repository.list_source_capture_attempts(
                source_input.project_id,
                run_id=run.id,
                limit=1,
            )
            self.repository.append_run_event(
                project_id=source_input.project_id,
                run_id=run.id,
                event_type="knowledge.source.captured",
                payload={
                    "source_id": source["id"],
                    "created": result.created,
                    "status": source["status"],
                    "capture_attempt_id": attempt[0]["id"] if attempt else "",
                    "capture_outcome": attempt[0]["outcome"] if attempt else "",
                    "evidence_mirror": mirror,
                },
            )
            if source["status"] == "eligible":
                self.repository.append_run_event(
                    project_id=source_input.project_id,
                    run_id=run.id,
                    event_type="knowledge.source.eligible",
                    payload={"source_id": source["id"]},
                )
            self.repository.update_run_status(
                source_input.project_id, run.id, RunStatus.COMPLETED,
                output_refs={
                    "source_id": source["id"],
                    "created": result.created,
                    "capture_attempt_id": attempt[0]["id"] if attempt else "",
                    "evidence_mirror": mirror,
                },
            )
            return {"source": source, "created": result.created, "run_id": run.id}
        except Exception as exc:
            self.repository.update_run_status(source_input.project_id, run.id, RunStatus.FAILED, error=str(exc))
            raise WikiCommandError(str(exc)) from exc

    def lint_proposal(self, *, project_id: str, proposal_id: str) -> dict:
        proposal = self._proposal(project_id, proposal_id)
        vault = self._vault(project_id)
        report = WikiLint().lint_proposal(
            proposal,
            rules=self._rules(project_id, vault),
            source_ids=self._proposal_source_ids(proposal),
            existing_paths=vault.contents,
            existing_contents=vault.contents,
        )
        return {"proposal_id": proposal_id, "valid": report.valid, "findings": [item.model_dump() for item in report.findings]}

    def publish_proposal(
        self,
        *,
        project_id: str,
        proposal_id: str,
        publication_mode: str = "manual",
        actor_id: str = "",
        actor_role: str = "",
        override_reason: str = "",
    ) -> dict:
        proposal = self._proposal(project_id, proposal_id)
        vault = self._vault(project_id)
        run = KnowledgeRun(
            project_id=project_id,
            run_type="wiki_publish",
            trigger="command",
            actor_id=actor_id,
            status=RunStatus.QUEUED,
            input_refs={
                "proposal_id": proposal_id,
                "base_revision": proposal.base_revision,
                "affected_paths": [operation.path for operation in proposal.operations],
                "expected_hashes": {
                    operation.path: operation.expected_content_hash
                    for operation in proposal.operations
                    if operation.expected_content_hash
                },
                "publication_mode": publication_mode,
                "override_requested": bool(override_reason.strip()),
            },
        )
        self.repository.create_run(run)
        self.repository.update_run_status(project_id, run.id, RunStatus.RUNNING)
        self.repository.append_run_event(
            project_id=project_id,
            run_id=run.id,
            event_type="knowledge.proposal.validation.started",
            payload={"proposal_id": proposal_id},
        )
        try:
            result = ProposalGate(self.repository, vault).publish(
                proposal=proposal,
                rules_text=self._rules_text(project_id, vault),
                publication_mode=publication_mode,
                actor_id=actor_id,
                actor_role=actor_role,
                override_reason=override_reason,
                audit_run_id=run.id,
            )
            self.repository.append_run_event(
                project_id=project_id,
                run_id=run.id,
                event_type="knowledge.proposal.published",
                payload={
                    "proposal_id": proposal_id,
                    "paths": result["paths"],
                    "evaluation_score": result["evaluation_score"],
                },
            )
            self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.COMPLETED,
                output_refs={"proposal_id": proposal_id, "publication": result},
            )
            return {**result, "run_id": run.id}
        except Exception as exc:
            self.repository.append_run_event(
                project_id=project_id,
                run_id=run.id,
                event_type="knowledge.proposal.validation.failed",
                payload={"proposal_id": proposal_id, "error_type": type(exc).__name__},
            )
            self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.FAILED,
                error=str(exc),
                output_refs={"proposal_id": proposal_id, "failure": {"code": "publication_gate_failed"}},
            )
            raise WikiCommandError(str(exc)) from exc

    def save_eval_case(self, *, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict:
        return WikiEvaluator(self.repository).save_case(
            project_id=project_id, case_id=case_id, case_type=case_type, expected=expected
        )

    def configure_schedule(
        self, *, project_id: str, job_type: str, cron: str, timezone_name: str = "Asia/Shanghai"
    ) -> dict:
        if not settings.KNOWLEDGE_SCHEDULES_ENABLED:
            raise WikiCommandError("knowledge schedules feature disabled")
        return KnowledgeScheduler(self.repository, scheduler_available=self._scheduler_available()).configure(
            project_id=project_id, job_type=job_type, cron=cron, timezone_name=timezone_name
        )

    def set_schedule_enabled(self, *, project_id: str, schedule_id: str, enabled: bool) -> dict:
        schedule = self.repository.get_schedule(project_id, schedule_id)
        if not schedule:
            raise WikiCommandError("knowledge schedule not found")
        if enabled and not self._scheduler_available():
            raise WikiCommandError("durable scheduler unavailable; use a manual run instead")
        next_run_at = ""
        if enabled:
            try:
                next_run_at = KnowledgeScheduler.next_run(
                    str(schedule["cron"]),
                    datetime.now(timezone.utc),
                    timezone_name=str(schedule.get("timezone") or "UTC"),
                ).isoformat()
            except ScheduleValidationError as exc:
                raise WikiCommandError(str(exc)) from exc
        return self.repository.set_schedule_enabled(
            project_id=project_id, schedule_id=schedule_id, enabled=enabled, next_run_at=next_run_at
        )

    def reject_proposal(self, *, project_id: str, proposal_id: str) -> dict:
        proposal = self.repository.get_proposal(project_id, proposal_id)
        if not proposal:
            raise WikiCommandError("Wiki proposal not found")
        if proposal["status"] not in {ProposalStatus.DRAFT.value, ProposalStatus.VALIDATING.value, ProposalStatus.APPROVED.value}:
            raise WikiCommandError("only un-published proposals can be rejected")
        return self.repository.update_proposal_status(project_id, proposal_id, ProposalStatus.REJECTED)

    def create_rollback_proposal(
        self, *, project_id: str, page_id: str, revision_id: str, actor_id: str = ""
    ) -> dict:
        """Create a draft that restores a prior page body through the normal publication gates."""
        page = self.repository.get_page(project_id, page_id)
        current = self.repository.get_page_content(project_id, page_id) if page else None
        revision = self.repository.get_page_revision_content(project_id, page_id, revision_id) if page else None
        if not page or not current or not revision:
            raise WikiCommandError("published Wiki page revision not found")
        if page["path"] == "wiki/log.md":
            raise WikiCommandError("wiki/log.md is append-only and cannot be restored by replacement")
        if revision["content_hash"] == current["content_hash"]:
            raise WikiCommandError("selected revision is already the published page")

        source_ids = list(dict.fromkeys(re.findall(r"\[source:([^\]\s]+)\]", revision["content"])))
        publishable_statuses = {"eligible", "processed"}
        unavailable = [
            source_id for source_id in source_ids
            if not (source := self.repository.get_source(project_id, source_id)) or source["status"] not in publishable_statuses
        ]
        if unavailable:
            raise WikiCommandError("selected revision relies on non-publishable evidence: " + ", ".join(unavailable))

        vault = self._vault(project_id)
        current_hash = hashlib.sha256(current["content"].encode("utf-8")).hexdigest()
        evidence = " " + " ".join(f"[source:{source_id}]" for source_id in source_ids) if source_ids else ""
        operations = [
            WikiOperation(
                operation=WikiOperationType.REPLACE,
                path=page["path"],
                content=revision["content"],
                expected_content_hash=current_hash,
                source_ids=source_ids,
            ),
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content=f"\n- Restored [[{page['path']}]] from revision {revision['version']}.{evidence}\n",
                source_ids=source_ids,
            ),
        ]
        if page["path"] != "wiki/index.md":
            operations.insert(
                1,
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/index.md",
                    content=f"\n- Restored [[{page['path']}]] from revision {revision['version']}.{evidence}\n",
                    source_ids=source_ids,
                ),
            )
        if page["path"] != "wiki/overview.md":
            operations.insert(
                -1,
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/overview.md",
                    content=f"\n- Restored [[{page['path']}]] from revision {revision['version']}.{evidence}\n",
                    source_ids=source_ids,
                ),
            )
        proposal = WikiProposal(
            project_id=project_id,
            base_revision=ProposalGate.project_revision(vault.contents),
            source_ids=source_ids,
            operations=operations,
            rationale=f"Restore {page['path']} from published revision {revision['version']}.",
            manual=True,
        )
        return self.repository.create_proposal(proposal, actor_id=actor_id)

    def start_run(
        self,
        *,
        project_id: str,
        job_type: str,
        trigger: str,
        input_refs: dict[str, Any] | None = None,
        retry_of: str | None = None,
    ) -> dict:
        try:
            KnowledgeScheduler._validate_job_type(job_type)
        except ScheduleValidationError as exc:
            raise WikiCommandError(str(exc)) from exc
        run = KnowledgeRun(
            project_id=project_id,
            run_type=job_type,
            trigger=trigger,
            status=RunStatus.QUEUED,
            input_refs=input_refs or {},
            retry_of=retry_of,
        )
        if not is_celery_real():
            # Local mode has no durable scheduler, but an explicit user action
            # must still execute through the same persisted task contract.
            self.repository.create_run(run)
            from app.tasks.knowledge_tasks import execute_knowledge_run

            result = execute_knowledge_run(project_id, run.id, repository=self.repository)
            return {**result, "execution": "synchronous"}
        if not is_celery_broker_available():
            return self._record_broker_unavailable(run)
        self.repository.create_run(run)
        try:
            if job_type in {"growth_daily", "growth_weekly_distillation"}:
                # Growth owns a tighter timeout/recovery contract than generic
                # Wiki work. Manual and retry runs must use that same task.
                from app.tasks.growth_tasks import growth_execute

                task = growth_execute.apply_async(args=[project_id, run.id])
                task_name = "knowledge.growth.execute"
            else:
                from app.tasks.knowledge_tasks import knowledge_execute

                task = knowledge_execute.apply_async(args=[project_id, run.id])
                task_name = "knowledge.execute"
            self._record_celery_assignment(run, task.id, task_name=task_name)
            return {"status": "queued", "run_id": run.id, "task_id": task.id}
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=f"queue submission failed: {exc}")
            raise WikiCommandError(f"queue submission failed: {exc}") from exc

    def retry_run(self, *, project_id: str, run_id: str) -> dict:
        run = self.repository.get_run(project_id, run_id)
        if not run:
            raise WikiCommandError("knowledge run not found")
        if run["status"] not in {RunStatus.FAILED.value, RunStatus.UNAVAILABLE.value, RunStatus.CANCELLED.value}:
            raise WikiCommandError("only terminal failed, unavailable, or cancelled runs can be retried")
        return self.start_run(
            project_id=project_id,
            job_type=run["run_type"],
            trigger="retry",
            input_refs=run.get("input_refs") or {},
            retry_of=run_id,
        )

    def recover_abandoned_publications(
        self,
        *,
        now: datetime | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, int]:
        """Reconcile interrupted manual publication against the authoritative Vault."""
        if timeout_seconds < 60:
            raise WikiCommandError("publication recovery timeout must be at least 60 seconds")
        current = now or datetime.now(timezone.utc)
        recovered = 0
        failed = 0
        for run in self.repository.list_running_runs():
            if run.get("run_type") != "wiki_publish":
                continue
            value = str(run.get("updated_at") or run.get("started_at") or run.get("created_at") or "")
            try:
                updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if updated > current - timedelta(seconds=timeout_seconds):
                continue
            project_id = str(run["project_id"])
            proposal_id = str((run.get("input_refs") or {}).get("proposal_id") or "")
            proposal = self.repository.get_proposal(project_id, proposal_id) if proposal_id else None
            if proposal and proposal.get("status") == ProposalStatus.PUBLISHED.value:
                self.repository.update_run_status(
                    project_id,
                    str(run["id"]),
                    RunStatus.COMPLETED,
                    output_refs={
                        "proposal_id": proposal_id,
                        "publication": {"status": ProposalStatus.PUBLISHED.value, "recovered": True},
                    },
                )
                recovered += 1
                continue
            if proposal:
                try:
                    typed = self._proposal(project_id, proposal_id)
                    vault = self._vault(project_id)
                    contents = vault.contents
                    if ProposalGate.effects_applied(typed, contents):
                        self.repository.record_publication(
                            project_id=project_id,
                            proposal_id=proposal_id,
                            contents=contents,
                            source_ids=sorted(ProposalGate._proposal_source_ids(typed)),
                        )
                        self.repository.update_run_status(
                            project_id,
                            str(run["id"]),
                            RunStatus.COMPLETED,
                            output_refs={
                                "proposal_id": proposal_id,
                                "publication": {"status": ProposalStatus.PUBLISHED.value, "recovered": True},
                            },
                        )
                        recovered += 1
                        continue
                except (OSError, ValueError, ProposalGateError, WikiCommandError):
                    pass
                if proposal.get("status") in {ProposalStatus.VALIDATING.value, ProposalStatus.APPROVED.value}:
                    summary = dict(proposal.get("eval_summary") or {})
                    summary["publication_error"] = "abandoned_publish_recovered"
                    self.repository.update_proposal_review(project_id, proposal_id, ProposalStatus.FAILED, summary)
            self.repository.update_run_status(
                project_id,
                str(run["id"]),
                RunStatus.FAILED,
                error="abandoned publish recovered before a durable publication",
                output_refs={
                    "proposal_id": proposal_id,
                    "failure": {"category": "transient_dependency", "code": "abandoned_publish", "retryable": True},
                },
            )
            failed += 1
        return {"recovered": recovered, "failed": failed}

    def cancel_run(self, *, project_id: str, run_id: str) -> dict:
        run = self.repository.get_run(project_id, run_id)
        if not run:
            raise WikiCommandError("knowledge run not found")
        if run["status"] not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise WikiCommandError("only queued or running knowledge runs can be cancelled")
        return self.repository.update_run_status(
            project_id,
            run_id,
            RunStatus.CANCELLED,
            error="cancelled by an authorized user",
            output_refs={"cancelled": True},
        )

    def read_distillation(self, *, project_id: str, distillation_id: str) -> dict:
        record = self.repository.get_distillation(project_id, distillation_id)
        if not record:
            raise WikiCommandError("weekly distillation not found")
        vault = self._vault(project_id)
        snapshot = vault.contents
        paths = (record["knowledge_path"], record["content_path"], record["context_path"])
        documents = {path: snapshot[path] for path in paths if path in snapshot}
        if len(documents) != len(paths):
            raise WikiCommandError("weekly distillation files are missing from the configured Vault")
        return {"distillation": record, "documents": documents}

    def start_horizon_capture(self, *, project_id: str, horizon_run_id: str, stage: str, trigger: str) -> dict:
        if stage not in {"filtered", "enriched"}:
            raise WikiCommandError("Horizon stage must be filtered or enriched")
        run = KnowledgeRun(
            project_id=project_id,
            run_type="horizon_capture",
            trigger=trigger,
            status=RunStatus.QUEUED,
            # No ID requests a safe run-store discovery. An explicit ID is kept
            # for replaying a known Horizon run during an audit.
            input_refs={"horizon_run_id": horizon_run_id.strip(), "stage": stage},
        )
        self.repository.create_run(run)
        if not is_celery_real():
            from app.tasks.knowledge_tasks import execute_knowledge_run

            return {**execute_knowledge_run(project_id, run.id, repository=self.repository), "execution": "synchronous"}
        if not is_celery_broker_available():
            return self._record_broker_unavailable(run)
        try:
            from app.tasks.knowledge_tasks import knowledge_execute

            task = knowledge_execute.apply_async(args=[project_id, run.id])
            self._record_celery_assignment(run, task.id)
            return {"status": "queued", "run_id": run.id, "task_id": task.id}
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=f"queue submission failed: {exc}")
            raise WikiCommandError(f"queue submission failed: {exc}") from exc

    def _record_celery_assignment(
        self, run: KnowledgeRun, task_id: object, *, task_name: str = "knowledge.execute"
    ) -> None:
        """Persist the broker handoff so a queued run remains auditable after reconnect."""
        payload = {
            "execution": "celery",
            "task_name": task_name,
            "task_id": str(task_id),
        }
        self.repository.append_run_event(
            project_id=run.project_id,
            run_id=run.id,
            event_type="knowledge.run.execution_assigned",
            payload=payload,
        )
        if run.run_type in {"growth_daily", "growth_weekly_distillation"}:
            self.repository.append_run_event(
                project_id=run.project_id,
                run_id=run.id,
                event_type="knowledge.growth.dispatched",
                payload={**payload, "trigger": run.trigger},
            )

    def _record_broker_unavailable(self, run: KnowledgeRun) -> dict:
        if not self.repository.get_run(run.project_id, run.id):
            self.repository.create_run(run)
        failure = {
            "category": "transient_dependency",
            "code": "celery_broker_unavailable",
            "retryable": True,
        }
        self.repository.update_run_status(
            run.project_id,
            run.id,
            RunStatus.UNAVAILABLE,
            error="durable scheduler unavailable because the Celery broker is unreachable",
            output_refs={"failure": failure},
        )
        return {"status": "unavailable", "run_id": run.id, "failure": failure}

    def _proposal(self, project_id: str, proposal_id: str) -> WikiProposal:
        record = self.repository.get_proposal(project_id, proposal_id)
        if not record:
            raise WikiCommandError("Wiki proposal not found")
        try:
            # Persistence has audit-only columns (for example ``actor_id``) that
            # intentionally do not belong to the immutable proposal contract.
            payload = {key: value for key, value in record.items() if key in WikiProposal.model_fields}
            return WikiProposal.model_validate(payload)
        except Exception as exc:
            raise WikiCommandError(f"stored Wiki proposal is invalid: {exc}") from exc

    @staticmethod
    def _proposal_source_ids(proposal: WikiProposal) -> set[str]:
        return set(proposal.source_ids) | {
            source_id
            for operation in proposal.operations
            for source_id in operation.source_ids
        }

    @staticmethod
    def _scheduler_available() -> bool:
        return (
            settings.KNOWLEDGE_SCHEDULES_ENABLED
            and is_celery_real()
            and is_celery_broker_available()
        )

    def _sync_evidence_mirror(self, project_id: str, source_id: str) -> dict:
        """Best-effort source projection that does not change capture authority."""
        if not settings.OBSIDIAN_VAULT_ROOT:
            return {"status": "unavailable", "reason": "vault_not_configured"}
        try:
            report = ObsidianSourceProjection(
                self.repository, Path(settings.OBSIDIAN_VAULT_ROOT)
            ).sync(project_id=project_id, source_ids=[source_id])
            return {"status": "completed", **report}
        except (OSError, ValueError, ProposalGateError):
            return {"status": "failed", "reason": "vault_projection_failed"}

    def _vault(self, project_id: str) -> FilesystemWikiVault:
        configured = self.repository.get_vault(project_id)
        if not configured:
            raise WikiCommandError("project Vault mapping is not configured")
        if not settings.OBSIDIAN_VAULT_ROOT:
            raise WikiCommandError("OBSIDIAN_VAULT_ROOT is not configured")
        try:
            return FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id, configured["vault_path"])
        except ProposalGateError as exc:
            raise WikiCommandError(str(exc)) from exc

    def _rules(self, project_id: str, vault: FilesystemWikiVault) -> ProjectRules:
        rules = parse_project_rules(self._rules_text(project_id, vault))
        if rules.project_id != project_id:
            raise WikiCommandError("AGENTS.md project_id does not match the requested project")
        return rules

    def _rules_text(self, project_id: str, vault: FilesystemWikiVault) -> str:
        path = vault.project_root / "AGENTS.md"
        if not path.is_file():
            raise WikiCommandError("project AGENTS.md is required before lint or publication")
        return path.read_text(encoding="utf-8")
