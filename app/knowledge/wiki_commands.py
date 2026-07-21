"""Governed command service shared by the Wiki REST and MCP transports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.celery_app import is_celery_real
from app.core.config import settings
from app.knowledge.proposal_gate import ProposalGate, ProposalGateError
from app.knowledge.scheduler import KnowledgeScheduler, ScheduleValidationError
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import KnowledgeRun, ProposalStatus, RunStatus, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import ProjectRules, parse_project_rules
from app.knowledge.wiki_source_capture import CapturedSourceInput, SourceCaptureService


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
        if not payload.get("base_revision"):
            vault = self._vault(project_id)
            payload = {**payload, "base_revision": ProposalGate.project_revision(vault.contents)}
        try:
            proposal = WikiProposal.model_validate({**payload, "manual": True, "status": ProposalStatus.DRAFT})
        except Exception as exc:
            raise WikiCommandError(f"invalid Wiki proposal: {exc}") from exc
        return self.repository.create_proposal(proposal, actor_id=actor_id)

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
            result = SourceCaptureService(self.repository).capture(source_input)
            source = result.source
            self.repository.append_run_event(
                project_id=source_input.project_id,
                run_id=run.id,
                event_type="knowledge.source.captured",
                payload={"source_id": source["id"], "created": result.created, "status": source["status"]},
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
                output_refs={"source_id": source["id"], "created": result.created},
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
            source_ids=set(proposal.source_ids),
            existing_paths=vault.contents,
        )
        return {"proposal_id": proposal_id, "valid": report.valid, "findings": [item.model_dump() for item in report.findings]}

    def publish_proposal(self, *, project_id: str, proposal_id: str) -> dict:
        proposal = self._proposal(project_id, proposal_id)
        vault = self._vault(project_id)
        try:
            return ProposalGate(self.repository, vault).publish(
                proposal=proposal,
                rules_text=self._rules_text(project_id, vault),
            )
        except ProposalGateError as exc:
            raise WikiCommandError(str(exc)) from exc

    def save_eval_case(self, *, project_id: str, case_id: str, case_type: str, expected: dict[str, Any]) -> dict:
        return WikiEvaluator(self.repository).save_case(
            project_id=project_id, case_id=case_id, case_type=case_type, expected=expected
        )

    def configure_schedule(
        self, *, project_id: str, job_type: str, cron: str, timezone_name: str = "Asia/Shanghai"
    ) -> dict:
        return KnowledgeScheduler(self.repository, scheduler_available=is_celery_real()).configure(
            project_id=project_id, job_type=job_type, cron=cron, timezone_name=timezone_name
        )

    def set_schedule_enabled(self, *, project_id: str, schedule_id: str, enabled: bool) -> dict:
        schedule = self.repository.get_schedule(project_id, schedule_id)
        if not schedule:
            raise WikiCommandError("knowledge schedule not found")
        if enabled and not is_celery_real():
            raise WikiCommandError("durable scheduler unavailable; use a manual run instead")
        next_run_at = ""
        if enabled:
            try:
                next_run_at = KnowledgeScheduler.next_run(str(schedule["cron"]), datetime.now(timezone.utc)).isoformat()
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
        self.repository.create_run(run)
        try:
            from app.tasks.knowledge_tasks import knowledge_execute

            task = knowledge_execute.apply_async(args=[project_id, run.id])
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
        if not horizon_run_id.strip():
            raise WikiCommandError("Horizon run ID is required")
        run = KnowledgeRun(
            project_id=project_id,
            run_type="horizon_capture",
            trigger=trigger,
            status=RunStatus.QUEUED,
            input_refs={"horizon_run_id": horizon_run_id, "stage": stage},
        )
        self.repository.create_run(run)
        if not is_celery_real():
            from app.tasks.knowledge_tasks import execute_knowledge_run

            return {**execute_knowledge_run(project_id, run.id, repository=self.repository), "execution": "synchronous"}
        try:
            from app.tasks.knowledge_tasks import knowledge_execute

            task = knowledge_execute.apply_async(args=[project_id, run.id])
            return {"status": "queued", "run_id": run.id, "task_id": task.id}
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=f"queue submission failed: {exc}")
            raise WikiCommandError(f"queue submission failed: {exc}") from exc

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
