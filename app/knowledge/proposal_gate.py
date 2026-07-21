"""Proposal-only publication gate with an atomic, replaceable Vault adapter."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from app.knowledge.wiki_contracts import ProposalStatus, SourceStatus, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import parse_project_rules


class ProposalGateError(ValueError):
    """Raised before any publish side effect when a gate cannot be satisfied."""


class InMemoryWikiVault:
    """Atomic Vault test double; future filesystem adapters must preserve this contract."""

    def __init__(self, contents: dict[str, str] | None = None) -> None:
        self.contents = dict(contents or {})

    def stage(self, proposal: WikiProposal) -> dict[str, str]:
        staged = deepcopy(self.contents)
        for operation in proposal.operations:
            current = staged.get(operation.path, "")
            if operation.expected_content_hash and self._hash(current) != operation.expected_content_hash:
                raise ProposalGateError(f"revision conflict at {operation.path}")
            if operation.operation is WikiOperationType.CREATE:
                if operation.path in staged:
                    raise ProposalGateError(f"page already exists: {operation.path}")
                staged[operation.path] = operation.content
            elif operation.operation is WikiOperationType.REPLACE:
                if operation.path not in staged:
                    raise ProposalGateError(f"page does not exist: {operation.path}")
                staged[operation.path] = operation.content
            elif operation.operation is WikiOperationType.APPEND:
                staged[operation.path] = current + operation.content
            elif operation.operation is WikiOperationType.ARCHIVE:
                staged.pop(operation.path, None)
            elif operation.operation is WikiOperationType.MOVE:
                if operation.path not in staged or operation.destination_path in staged:
                    raise ProposalGateError(f"invalid move: {operation.path}")
                staged[operation.destination_path] = staged.pop(operation.path)
        return staged

    def commit(self, staged: dict[str, str]) -> None:
        self.contents = staged

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ProposalGate:
    """Validate first, stage all pages, then publish source/proposal state together."""

    def __init__(self, repository: WikiRepository, vault: InMemoryWikiVault) -> None:
        self.repository = repository
        self.vault = vault
        self.lint = WikiLint()
        self.evaluator = WikiEvaluator(repository)

    def publish(self, *, proposal: WikiProposal, rules_text: str) -> dict:
        persisted = self.repository.get_proposal(proposal.project_id, proposal.id)
        if not persisted or persisted["status"] != ProposalStatus.DRAFT.value:
            raise ProposalGateError("proposal must exist in draft status")
        sources = [self.repository.get_source(proposal.project_id, source_id) for source_id in proposal.source_ids]
        if any(source is None or source["status"] != SourceStatus.ELIGIBLE.value for source in sources):
            raise ProposalGateError("all proposal sources must remain eligible")
        rules = parse_project_rules(rules_text)
        lint_report = self.lint.lint_proposal(
            proposal,
            rules=rules,
            source_ids=set(proposal.source_ids),
            existing_paths=self.vault.contents,
        )
        if not lint_report.valid:
            raise ProposalGateError("lint failed: " + ", ".join(finding.code for finding in lint_report.findings))
        evaluation = self.evaluator.evaluate(
            project_id=proposal.project_id,
            proposal_id=proposal.id,
            wiki_revision=proposal.base_revision,
            candidate={
                "source_ids": proposal.source_ids,
                "content": "\n".join(operation.content for operation in proposal.operations),
            },
        )
        if evaluation.status != "passed":
            raise ProposalGateError("evaluation baseline did not pass: " + (evaluation.skipped_reason or evaluation.status))
        staged = self.vault.stage(proposal)
        before = self.vault.contents
        try:
            self.vault.commit(staged)
            self.repository.record_publication(
                project_id=proposal.project_id,
                proposal_id=proposal.id,
                contents=staged,
                source_ids=proposal.source_ids,
            )
        except Exception:
            self.vault.commit(before)
            raise
        return {
            "status": ProposalStatus.PUBLISHED.value,
            "proposal_id": proposal.id,
            "paths": sorted(staged),
            "evaluation_score": evaluation.score,
        }
