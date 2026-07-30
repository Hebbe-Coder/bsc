"""Proposal-only publication gate with an atomic, replaceable Vault adapter."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy

from app.knowledge.wiki_contracts import ProposalStatus, SourceStatus, WikiOperationType, WikiProposal
from app.knowledge.wiki_evaluator import WikiEvaluator
from app.knowledge.wiki_lint import WikiLint
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import parse_project_rules
from app.knowledge.wiki_index import WikiSearchIndex
from app.knowledge.source_triage import source_admission_reason


class ProposalGateError(ValueError):
    """Raised before any publish side effect when a gate cannot be satisfied."""


class InMemoryWikiVault:
    """Atomic Vault test double; future filesystem adapters must preserve this contract."""

    def __init__(self, contents: dict[str, str] | None = None) -> None:
        self.contents = dict(contents or {})

    def stage(self, proposal: WikiProposal) -> dict[str, str]:
        staged = deepcopy(self.contents)
        for operation in proposal.operations:
            is_agents_rules = operation.path == "AGENTS.md"
            if not operation.path.startswith("wiki/") and not is_agents_rules:
                raise ProposalGateError("proposal writes are restricted to the generated wiki/ boundary")
            if operation.destination_path and not operation.destination_path.startswith("wiki/"):
                raise ProposalGateError("proposal destinations are restricted to the generated wiki/ boundary")
            if is_agents_rules and operation.operation is not WikiOperationType.REPLACE:
                raise ProposalGateError("AGENTS.md may only be replaced through a governed proposal")
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

    def __init__(self, repository: WikiRepository, vault: InMemoryWikiVault, *, search_index=None) -> None:
        self.repository = repository
        self.vault = vault
        self.lint = WikiLint()
        self.evaluator = WikiEvaluator(repository)
        self.search_index = search_index or WikiSearchIndex(repository)

    def publish(
        self,
        *,
        proposal: WikiProposal,
        rules_text: str,
        publication_mode: str = "manual",
        actor_id: str = "",
        actor_role: str = "",
        override_reason: str = "",
        audit_run_id: str = "",
    ) -> dict:
        if publication_mode not in {"manual", "automatic"}:
            raise ProposalGateError("publication mode must be manual or automatic")
        override_reason = override_reason.strip()
        override = bool(override_reason)
        if override:
            if publication_mode != "manual" or actor_role != "admin":
                raise ProposalGateError("administrator permission is required for a publication override")
            if len(override_reason) < 8:
                raise ProposalGateError("administrator override requires a meaningful reason")
            if not audit_run_id:
                raise ProposalGateError("administrator override requires an auditable publication run")
        persisted = self.repository.get_proposal(proposal.project_id, proposal.id)
        if not persisted or persisted["status"] not in {ProposalStatus.DRAFT.value, ProposalStatus.FAILED.value}:
            raise ProposalGateError("proposal must exist in draft or retryable failed status")
        if proposal.base_revision.startswith("vault:") and proposal.base_revision != self.project_revision(self.vault.contents):
            raise ProposalGateError("revision conflict: the project Wiki changed after this proposal was compiled")
        proposal_source_ids = self._proposal_source_ids(proposal)
        sources = [self.repository.get_source(proposal.project_id, source_id) for source_id in proposal_source_ids]
        publishable_source_states = {SourceStatus.ELIGIBLE.value, SourceStatus.PROCESSED.value}
        if any(source is None or source["status"] not in publishable_source_states for source in sources):
            raise ProposalGateError("all proposal sources must remain eligible or previously published")
        blocked_sources = [
            source["id"]
            for source in sources
            if source is not None
            and source["status"] == SourceStatus.ELIGIBLE.value
            and source_admission_reason(self.repository, proposal.project_id, source)
        ]
        if blocked_sources:
            raise ProposalGateError("proposal sources require current project triage: " + ", ".join(sorted(blocked_sources)))
        if publication_mode == "automatic":
            mapping = self.repository.get_vault(proposal.project_id) or {}
            policy = mapping.get("metadata") or {}
            if policy.get("auto_publish_enabled") is not True:
                raise ProposalGateError("project source policy does not permit automatic publication")
            if not sources or any(source.get("trust_level") != "trusted" for source in sources):
                raise ProposalGateError("automatic publication requires only trusted source evidence")
        self.repository.update_proposal_status(proposal.project_id, proposal.id, ProposalStatus.VALIDATING)
        try:
            rules = parse_project_rules(rules_text)
        except Exception:
            self.repository.update_proposal_review(
                proposal.project_id,
                proposal.id,
                ProposalStatus.FAILED,
                {**proposal.eval_summary, "validation_error": "invalid_project_rules"},
            )
            raise
        lint_report = self.lint.lint_proposal(
            proposal,
            rules=rules,
            source_ids=proposal_source_ids,
            existing_paths=self.vault.contents,
            existing_contents=self.vault.contents,
        )
        lint_findings = [finding.model_dump() for finding in lint_report.findings]
        if not lint_report.valid and not override:
            self.repository.update_proposal_review(
                proposal.project_id,
                proposal.id,
                ProposalStatus.FAILED,
                {**proposal.eval_summary, "lint_findings": lint_findings},
            )
            raise ProposalGateError("lint failed: " + ", ".join(finding.code for finding in lint_report.findings))
        try:
            evaluation = self.evaluator.evaluate(
                project_id=proposal.project_id,
                proposal_id=proposal.id,
                wiki_revision=proposal.base_revision,
                candidate={
                    "source_ids": sorted(proposal_source_ids),
                    "content": "\n".join(operation.content for operation in proposal.operations),
                    "paths": [operation.path for operation in proposal.operations],
                },
            )
        except Exception:
            self.repository.update_proposal_review(
                proposal.project_id,
                proposal.id,
                ProposalStatus.FAILED,
                {**proposal.eval_summary, "validation_error": "evaluation_execution_failed"},
            )
            raise
        if evaluation.status not in {"passed", "not_applicable"} and not override:
            self.repository.update_proposal_review(
                proposal.project_id,
                proposal.id,
                ProposalStatus.FAILED,
                {**proposal.eval_summary, "evaluation": evaluation.model_dump()},
            )
            raise ProposalGateError("evaluation baseline did not pass: " + (evaluation.skipped_reason or evaluation.status))
        review_summary = {
            **proposal.eval_summary,
            "lint_findings": lint_findings,
            "evaluation": evaluation.model_dump(),
            "publication_policy": {
                "mode": publication_mode,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "override_applied": override,
            },
        }
        if override:
            review_summary["publication_policy"]["override_reason"] = override_reason
        # Preserve the validation result without presenting an uncommitted
        # proposal as approved when the host stops between authorities.
        self.repository.update_proposal_review(
            proposal.project_id,
            proposal.id,
            ProposalStatus.VALIDATING,
            review_summary,
        )
        if audit_run_id:
            self.repository.append_run_event(
                project_id=proposal.project_id,
                run_id=audit_run_id,
                event_type=(
                    "knowledge.proposal.override.applied"
                    if override
                    else "knowledge.proposal.publication.policy.accepted"
                ),
                payload={
                    "proposal_id": proposal.id,
                    "mode": publication_mode,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "override_reason": override_reason if override else "",
                    "lint_findings": lint_findings,
                    "evaluation_status": evaluation.status,
                },
            )
        before = self.vault.contents
        expected_content_hashes = {
            page["path"]: page["content_hash"]
            for page in self.repository.list_pages(proposal.project_id)
            if page["path"] in before
        }
        try:
            staged_before_publication = self.vault.stage(proposal)
            staged = self._materialize_published_statuses(staged_before_publication)
            materialized_status_paths = self._materialized_status_paths(staged_before_publication, staged)
            self.vault.commit(staged)
            self.repository.record_publication(
                project_id=proposal.project_id,
                proposal_id=proposal.id,
                contents=staged,
                source_ids=sorted(proposal_source_ids),
                expected_content_hashes=expected_content_hashes,
            )
        except Exception:
            self.vault.commit(before)
            self.repository.update_proposal_review(
                proposal.project_id,
                proposal.id,
                ProposalStatus.FAILED,
                {**review_summary, "publication_error": "atomic_commit_failed"},
            )
            raise
        try:
            indexing = self.search_index.sync_wiki_snapshot(project_id=proposal.project_id, contents=staged)
        except Exception:
            indexing = {"indexed": 0, "removed": 0, "failures": [{"path": "*", "code": "index_backend_exception"}]}
        return {
            "status": ProposalStatus.PUBLISHED.value,
            "proposal_id": proposal.id,
            "paths": sorted(staged),
            "evaluation_score": evaluation.score,
            "publication_policy": review_summary["publication_policy"],
            "indexing": indexing,
            "materialized_status_paths": materialized_status_paths,
        }

    @staticmethod
    def effects_applied(proposal: WikiProposal, contents: dict[str, str]) -> bool:
        """Check every typed postcondition before recovering an interrupted publish."""
        for operation in proposal.operations:
            current = contents.get(operation.path)
            if operation.operation in {WikiOperationType.CREATE, WikiOperationType.REPLACE}:
                if current != ProposalGate._materialize_published_status(operation.path, operation.content):
                    return False
            elif operation.operation is WikiOperationType.APPEND:
                if current is None or not current.endswith(operation.content):
                    return False
            elif operation.operation is WikiOperationType.ARCHIVE:
                if current is not None:
                    return False
            elif operation.operation is WikiOperationType.MOVE:
                if current is not None or contents.get(operation.destination_path) is None:
                    return False
        return True

    def reconcile_published_statuses(self, *, project_id: str) -> dict:
        """Backfill only missing Vault status metadata for persisted Wiki pages.

        This is an idempotent compatibility migration for pages published before
        the frontmatter status contract existed. It refuses to write when a
        managed Vault page differs from its durable BSC revision, so it cannot
        overwrite a user edit while repairing metadata.
        """
        before = self.vault.contents
        persisted_pages = self.repository.list_pages(project_id)
        original_contents: dict[str, str] = {}
        published_contents: dict[str, str] = {}
        expected_content_hashes: dict[str, str] = {}
        for page in persisted_pages:
            path = str(page["path"])
            revision = self.repository.get_page_content(project_id, str(page["id"]))
            if revision is None:
                raise ProposalGateError(f"published page revision is unavailable: {path}")
            current_content = str(revision["content"])
            original_contents[path] = current_content
            published_contents[path] = self._materialize_published_status(path, current_content)
            expected_content_hashes[path] = str(page["content_hash"])

        changed_paths = sorted(
            path for path, content in published_contents.items() if original_contents[path] != content
        )
        if not changed_paths:
            return {"state": "already_materialized", "paths": [], "indexing": None}

        for path in changed_paths:
            if before.get(path) != original_contents[path]:
                raise ProposalGateError(f"publication status migration conflict at {path}")

        staged = dict(before)
        staged.update({path: published_contents[path] for path in changed_paths})
        try:
            self.vault.commit(staged)
            self.repository.record_publication(
                project_id=project_id,
                contents=published_contents,
                source_ids=[],
                expected_content_hashes=expected_content_hashes,
            )
        except Exception:
            self.vault.commit(before)
            raise
        try:
            indexing = self.search_index.sync_wiki_snapshot(project_id=project_id, contents=published_contents)
        except Exception:
            indexing = {"indexed": 0, "removed": 0, "failures": [{"path": "*", "code": "index_backend_exception"}]}
        return {"state": "reconciled", "paths": changed_paths, "indexing": indexing}

    @staticmethod
    def _materialize_published_statuses(contents: dict[str, str]) -> dict[str, str]:
        """Project the durable publication state into Obsidian page metadata.

        The database is authoritative, but Obsidian views and Dataview query
        frontmatter. A successfully published B-layer page must therefore never
        continue to advertise itself as a draft in the Vault snapshot.
        """
        return {
            path: ProposalGate._materialize_published_status(path, content)
            for path, content in contents.items()
        }

    @staticmethod
    def _materialized_status_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
        return sorted(path for path, content in after.items() if before.get(path) != content)

    @staticmethod
    def _materialize_published_status(path: str, content: str) -> str:
        if not path.startswith("wiki/") or not path.endswith(".md"):
            return content
        frontmatter = re.match(
            r"\A(?P<opening>---\r?\n)(?P<body>.*?)(?P<closing>\r?\n---(?=\r?\n|\Z))",
            content,
            flags=re.DOTALL,
        )
        if not frontmatter:
            return content
        body = frontmatter.group("body")
        line_ending = "\r\n" if "\r\n" in frontmatter.group("opening") else "\n"
        if re.search(r"(?m)^status\s*:[^\r\n]*$", body):
            normalized_body = re.sub(r"(?m)^status\s*:[^\r\n]*$", "status: published", body, count=1)
        else:
            separator = "" if not body or body.endswith(("\n", "\r")) else line_ending
            normalized_body = f"{body}{separator}status: published"
        return f"{frontmatter.group('opening')}{normalized_body}{frontmatter.group('closing')}{content[frontmatter.end():]}"

    @staticmethod
    def project_revision(contents: dict[str, str]) -> str:
        """Hash the publishable Wiki/rule snapshot, excluding generated distillations and raw evidence."""
        records = [
            f"{path}:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            for path, content in sorted(contents.items())
            if path == "AGENTS.md" or path.startswith("wiki/")
        ]
        return "vault:" + hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()

    @staticmethod
    def _proposal_source_ids(proposal: WikiProposal) -> set[str]:
        return set(proposal.source_ids) | {
            source_id
            for operation in proposal.operations
            for source_id in operation.source_ids
        }
