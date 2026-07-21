"""Governed command service shared by the Wiki REST and MCP transports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.celery_app import is_celery_real
from app.core.config import settings
from app.knowledge.proposal_gate import ProposalGate, ProposalGateError
from app.knowledge.scheduler import KnowledgeScheduler
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_contracts import KnowledgeRun, ProposalStatus, RunStatus, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import ProjectRules, parse_project_rules


class WikiCommandError(ValueError):
    """Raised for a command that cannot safely alter the governed Wiki state."""


class WikiCommandService:
    """Create and execute project-scoped Wiki commands without bypassing the gate."""

    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    def create_proposal(self, payload: dict[str, Any], *, actor_id: str = "") -> dict:
        try:
            proposal = WikiProposal.model_validate({**payload, "manual": True, "status": ProposalStatus.DRAFT})
        except Exception as exc:
            raise WikiCommandError(f"invalid Wiki proposal: {exc}") from exc
        if not proposal.project_id.strip():
            raise WikiCommandError("project_id is required")
        return self.repository.create_proposal(proposal, actor_id=actor_id)

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

    def start_run(self, *, project_id: str, job_type: str, trigger: str) -> dict:
        if not is_celery_real():
            # Local mode has no durable scheduler, but an explicit user action
            # must still execute through the same persisted task contract.
            run = KnowledgeRun(project_id=project_id, run_type=job_type, trigger=trigger, status=RunStatus.QUEUED)
            self.repository.create_run(run)
            from app.tasks.knowledge_tasks import execute_knowledge_run

            result = execute_knowledge_run(project_id, run.id, repository=self.repository)
            return {**result, "execution": "synchronous"}
        scheduler = KnowledgeScheduler(self.repository, scheduler_available=is_celery_real())
        result = scheduler.run_now(project_id=project_id, job_type=job_type, trigger=trigger)
        if result["status"] != "queued":
            return result
        try:
            from app.tasks.knowledge_tasks import knowledge_execute

            task = knowledge_execute.apply_async(args=[project_id, result["run_id"]])
            return {**result, "task_id": task.id}
        except Exception as exc:
            self.repository.update_run_status(project_id, result["run_id"], RunStatus.FAILED, error=f"queue submission failed: {exc}")
            raise WikiCommandError(f"queue submission failed: {exc}") from exc

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
            return FilesystemWikiVault(Path(settings.OBSIDIAN_VAULT_ROOT), project_id)
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
