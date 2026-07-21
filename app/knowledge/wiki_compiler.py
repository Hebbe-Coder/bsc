"""Compile eligible evidence into reviewable Wiki proposals without publishing files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import ValidationError

from app.knowledge.context_pack import ContextPack, ContextPackBuilder
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceStatus, WikiOperation, WikiOperationType, WikiProposal
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import ProjectRules, parse_project_rules


class WikiCompilerProvider(Protocol):
    def compile_wiki(self, prompt: str) -> dict[str, Any]: ...


class WikiCompilationError(ValueError):
    """Raised when a provider output cannot become a safe, reviewable proposal."""


@dataclass(frozen=True)
class WikiCompilationResult:
    proposal: dict[str, Any]
    run: dict[str, Any]
    context_pack: ContextPack


class WikiCompiler:
    """A proposal-only compiler: evidence and published Vault state remain unchanged."""

    def __init__(
        self,
        repository: WikiRepository,
        provider: WikiCompilerProvider,
        context_builder: ContextPackBuilder | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.context_builder = context_builder or ContextPackBuilder()

    def compile_maintenance(
        self,
        *,
        project_id: str,
        source_ids: list[str] | None,
        trigger: str,
        rules_text: str,
        actor_id: str = "",
        task_constraints: list[str] | None = None,
        page_snapshots: list[dict[str, Any]] | None = None,
    ) -> WikiCompilationResult:
        rules = parse_project_rules(rules_text)
        sources = self._select_sources(project_id, source_ids)
        context_pack = self.context_builder.build(
            project_id=project_id,
            rules=rules,
            task_constraints=task_constraints or [],
            pages=page_snapshots or [],
            sources=sources,
        )
        run = KnowledgeRun(
            project_id=project_id,
            run_type="wiki_maintenance",
            trigger=trigger,
            status=RunStatus.RUNNING,
            actor_id=actor_id,
            input_refs={
                "source_ids": [source["id"] for source in sources],
                "source_hashes": {source["id"]: source["content_hash"] for source in sources},
                "rule_revision": rules.revision,
                "context_pack_revision": context_pack.revision,
            },
            started_at=datetime.now(timezone.utc),
        )
        persisted_run = self.repository.create_run(run)
        try:
            response = self.provider.compile_wiki(self._build_prompt(rules, context_pack))
            proposal = self._validate_response(
                project_id, sources, response, context_pack, self._snapshot_revision(page_snapshots or [])
            )
            persisted_proposal = self.repository.create_proposal(proposal, actor_id=actor_id)
            completed_run = self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.COMPLETED,
                output_refs={"proposal_id": proposal.id, "context_pack_revision": context_pack.revision},
            )
            return WikiCompilationResult(persisted_proposal, completed_run, context_pack)
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=str(exc))
            if isinstance(exc, WikiCompilationError):
                raise
            raise WikiCompilationError(str(exc)) from exc

    def _select_sources(self, project_id: str, source_ids: list[str] | None) -> list[dict[str, Any]]:
        eligible = self.repository.list_sources(project_id, status=SourceStatus.ELIGIBLE.value)
        if source_ids is None:
            selected = eligible
        else:
            selected_ids = set(source_ids)
            selected = [source for source in eligible if source["id"] in selected_ids]
            if selected_ids != {source["id"] for source in selected}:
                raise WikiCompilationError("all sources must exist in this project and be eligible")
        if not selected:
            raise WikiCompilationError("no eligible sources selected")
        return selected

    @staticmethod
    def _build_prompt(rules: ProjectRules, context_pack: ContextPack) -> str:
        return (
            "Compile the supplied project evidence into a JSON Wiki proposal. "
            "Return an object with rationale and operations only. Every operation must use wiki/ paths "
            "and cite only supplied source IDs. Do not claim any file has been published.\n\n"
            f"Rule revision: {rules.revision}\n\n{context_pack.rendered}"
        )

    @staticmethod
    def _validate_response(
        project_id: str,
        sources: list[dict[str, Any]],
        response: Any,
        context_pack: ContextPack,
        base_revision: str,
    ) -> WikiProposal:
        if not isinstance(response, dict):
            raise WikiCompilationError("provider response must be an object")
        selected_ids = {source["id"] for source in sources}
        try:
            operations = [WikiOperation.model_validate(value) for value in response.get("operations", [])]
        except ValidationError as exc:
            raise WikiCompilationError(f"invalid proposal operations: {exc}") from exc
        if not operations:
            raise WikiCompilationError("proposal requires at least one operation")
        for operation in operations:
            if not operation.path.startswith("wiki/"):
                raise WikiCompilationError("proposal operations may only target wiki/ paths")
            if not operation.source_ids:
                raise WikiCompilationError("every automatic operation requires source provenance")
            unknown = set(operation.source_ids) - selected_ids
            if unknown:
                raise WikiCompilationError("operation cites unknown source IDs: " + ", ".join(sorted(unknown)))
        operations.append(
            WikiOperation(
                operation=WikiOperationType.APPEND,
                path="wiki/log.md",
                content="\n- Draft proposal compiled from " + ", ".join(sorted(selected_ids)) + ".\n",
                source_ids=sorted(selected_ids),
            )
        )
        if not any(operation.path == "wiki/index.md" for operation in operations):
            operations.append(
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/index.md",
                    content="\n- Pending review: " + ", ".join(operation.path for operation in operations[:-1]) + ".\n",
                    source_ids=sorted(selected_ids),
                )
            )
        if not any(operation.path == "wiki/overview.md" for operation in operations):
            changed_paths = [
                operation.path for operation in operations
                if operation.path not in {"wiki/index.md", "wiki/log.md"}
            ]
            operations.append(
                WikiOperation(
                    operation=WikiOperationType.APPEND,
                    path="wiki/overview.md",
                    content="\n- Evidence-backed Wiki update: " + ", ".join(
                        f"[[{path}]]" for path in changed_paths
                    ) + " " + " ".join(f"[source:{source_id}]" for source_id in sorted(selected_ids)) + "\n",
                    source_ids=sorted(selected_ids),
                )
            )
        return WikiProposal(
            project_id=project_id,
            base_revision=base_revision,
            source_ids=sorted(selected_ids),
            operations=operations,
            rationale=str(response.get("rationale") or ""),
            eval_summary={"context_pack_revision": context_pack.revision},
        )

    @staticmethod
    def _snapshot_revision(pages: list[dict[str, Any]]) -> str:
        if not pages:
            return ""
        records = [
            f"{page['path']}:{hashlib.sha256(str(page.get('content') or '').encode('utf-8')).hexdigest()}"
            for page in sorted(pages, key=lambda item: str(item.get("path") or ""))
            if str(page.get("path") or "") == "AGENTS.md" or str(page.get("path") or "").startswith("wiki/")
        ]
        return "vault:" + hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest() if records else ""
