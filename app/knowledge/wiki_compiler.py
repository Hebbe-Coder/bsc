"""Compile eligible evidence into reviewable Wiki proposals without publishing files."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import ValidationError

from app.knowledge.context_pack import ContextPack, ContextPackBuilder
from app.knowledge.source_triage import source_admission_reason
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

    _SOURCE_CITATION = re.compile(r"\[source:([^\]\s]+)\]")
    _CONTEXT_EXCERPT_ARTIFACT = re.compile(
        r"\[CONTEXT_EXCERPT(?::[^\]]*)?\]|\bcontent\s+truncated\s+in\s+source\b",
        re.IGNORECASE,
    )
    _NON_EVIDENCE_CONTEXT_KINDS = frozenset({
        "constraint",
        "decision",
        "distillation",
        "evaluation",
        "page",
        "rules",
    })

    def __init__(
        self,
        repository: WikiRepository,
        provider: WikiCompilerProvider,
        context_builder: ContextPackBuilder | None = None,
        retrieval_service=None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.context_builder = context_builder or ContextPackBuilder()
        if retrieval_service is None:
            from app.knowledge.service import KnowledgeService

            retrieval_service = KnowledgeService(repo=repository)
        self.retrieval_service = retrieval_service

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
        constraints = task_constraints or []
        sources = self._select_sources(project_id, source_ids, query="\n".join(constraints))
        contradictions = self._contradictions(sources)
        context_pack = self.context_builder.build(
            project_id=project_id,
            rules=rules,
            task_constraints=constraints,
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
                "page_hashes": {
                    str(page.get("id") or page.get("path")): hashlib.sha256(
                        str(page.get("content") or "").encode("utf-8")
                    ).hexdigest()
                    for page in (page_snapshots or [])
                    if page.get("id") or page.get("path")
                },
                "contradictions": contradictions,
            },
            started_at=datetime.now(timezone.utc),
        )
        persisted_run = self.repository.create_run(run)
        try:
            response = self.provider.compile_wiki(self._build_prompt(rules, context_pack, contradictions))
            proposal = self._validate_response(
                project_id, sources, response, context_pack, self._snapshot_revision(page_snapshots or []), contradictions
            )
            persisted_proposal = self.repository.create_proposal(proposal, actor_id=actor_id)
            completed_run = self.repository.update_run_status(
                project_id,
                run.id,
                RunStatus.COMPLETED,
                output_refs={
                    "proposal_id": proposal.id,
                    "context_pack_revision": context_pack.revision,
                    "contradictions": contradictions,
                },
            )
            return WikiCompilationResult(persisted_proposal, completed_run, context_pack)
        except Exception as exc:
            self.repository.update_run_status(project_id, run.id, RunStatus.FAILED, error=str(exc))
            if isinstance(exc, WikiCompilationError):
                raise
            raise WikiCompilationError(str(exc)) from exc

    def _select_sources(self, project_id: str, source_ids: list[str] | None, *, query: str = "") -> list[dict[str, Any]]:
        eligible = [
            source
            for source in self.repository.list_sources(project_id, status=SourceStatus.ELIGIBLE.value)
            if not source_admission_reason(self.repository, project_id, source)
        ]
        if source_ids is None:
            selected = eligible
            if query.strip():
                hits = self.retrieval_service.retrieve(query, project_id=project_id, top_k=32, rerank=True)
                prefix = f"evidence://{project_id}/"
                candidate_ids = {
                    str(hit.get("source"))[len(prefix):]
                    for hit in hits or []
                    if str(hit.get("source") or "").startswith(prefix)
                }
                if candidate_ids:
                    selected = [source for source in eligible if source["id"] in candidate_ids]
        else:
            selected_ids = set(source_ids)
            selected = [source for source in eligible if source["id"] in selected_ids]
            if selected_ids != {source["id"] for source in selected}:
                raise WikiCompilationError(
                    "all sources must exist in this project, be eligible, and pass current project triage"
                )
        if not selected:
            raise WikiCompilationError("no eligible sources selected")
        return selected

    @staticmethod
    def _build_prompt(rules: ProjectRules, context_pack: ContextPack, contradictions: list[dict[str, str]]) -> str:
        contradiction_block = "\n".join(
            f"- {item['source_id']} contradicts {item['contradicts_source_id']} ({item['basis']})"
            for item in contradictions
        ) or "- None detected; do not invent a contradiction."
        return (
            "Compile the supplied project evidence into a reviewable Wiki proposal, not a generic summary. "
            "Distill reusable, project-specific concepts, decisions, or methods that improve a later task. "
            "Every factual statement must be traceable to supplied source IDs. Return only the proposal JSON schema "
            "specified by the Wiki compiler; never claim any file has been published.\n\n"
            f"Rule revision: {rules.revision}\n\nContradiction candidates:\n{contradiction_block}\n\n{context_pack.rendered}"
        )

    @staticmethod
    def _validate_response(
        project_id: str,
        sources: list[dict[str, Any]],
        response: Any,
        context_pack: ContextPack,
        base_revision: str,
        contradictions: list[dict[str, str]],
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
        internal_context_refs = {
            reference
            for reference in context_pack.section_refs
            if reference.partition(":")[0] in WikiCompiler._NON_EVIDENCE_CONTEXT_KINDS
        }
        normalized_operations: list[WikiOperation] = []
        ignored_context_refs: set[str] = set()
        for operation in operations:
            if not operation.path.startswith("wiki/"):
                raise WikiCompilationError("proposal operations may only target wiki/ paths")
            normalized, ignored = WikiCompiler._normalize_operation_evidence(
                operation,
                selected_ids=selected_ids,
                internal_context_refs=internal_context_refs,
            )
            normalized_operations.append(normalized)
            ignored_context_refs.update(ignored)
        operations = normalized_operations
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
            eval_summary={
                "context_pack_revision": context_pack.revision,
                "input_page_ids": list(context_pack.page_ids),
                "input_source_ids": list(context_pack.source_ids),
                "contradictions": contradictions,
                "ignored_internal_context_refs": sorted(ignored_context_refs),
            },
        )

    @classmethod
    def _normalize_operation_evidence(
        cls,
        operation: WikiOperation,
        *,
        selected_ids: set[str],
        internal_context_refs: set[str],
    ) -> tuple[WikiOperation, set[str]]:
        """Remove declared context labels while rejecting every non-evidence citation.

        Context packs deliberately label project rules, pages, evaluations, and
        distillations as ``[kind:id]``. A provider can copy those labels into
        ``source_ids`` even though they are instructions, not immutable evidence.
        Only labels already declared in this context pack are removable; every
        other unknown identifier remains a hard failure.
        """
        ignored: set[str] = set()
        normalized_source_ids: list[str] = []
        for source_id in operation.source_ids:
            if source_id in selected_ids:
                if source_id not in normalized_source_ids:
                    normalized_source_ids.append(source_id)
            elif source_id in internal_context_refs:
                ignored.add(source_id)
            else:
                raise WikiCompilationError(f"operation cites unknown source IDs: {source_id}")

        def replace_citation(match: re.Match[str]) -> str:
            source_id = match.group(1)
            if source_id in selected_ids:
                return match.group(0)
            if source_id in internal_context_refs:
                ignored.add(source_id)
                return ""
            raise WikiCompilationError(f"operation cites unknown source IDs: {source_id}")

        content = cls._SOURCE_CITATION.sub(replace_citation, operation.content)
        if cls._CONTEXT_EXCERPT_ARTIFACT.search(content):
            raise WikiCompilationError("proposal contains a context truncation artifact instead of evidence-grounded prose")
        if not normalized_source_ids:
            raise WikiCompilationError("every automatic operation requires immutable source provenance")
        if operation.operation in {
            WikiOperationType.CREATE,
            WikiOperationType.REPLACE,
            WikiOperationType.APPEND,
        } and not cls._SOURCE_CITATION.search(content):
            raise WikiCompilationError("automatic content operations require an inline citation to a selected source")
        return operation.model_copy(update={"source_ids": normalized_source_ids, "content": content}), ignored

    @staticmethod
    def _contradictions(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
        selected = {source["id"] for source in sources}
        findings: list[dict[str, str]] = []
        recorded_pairs: set[frozenset[str]] = set()
        for source in sources:
            targets = source.get("metadata", {}).get("contradicts_source_ids", [])
            if not isinstance(targets, list):
                continue
            for target in targets:
                if isinstance(target, str) and target in selected and target != source["id"]:
                    recorded_pairs.add(frozenset((source["id"], target)))
                    findings.append({
                        "source_id": source["id"],
                        "contradicts_source_id": target,
                        "basis": "explicit_source_metadata",
                    })
        for position, left in enumerate(sources):
            left_metadata = left.get("metadata") or {}
            left_claims = left_metadata.get("claims") or {}
            if not isinstance(left_claims, dict):
                continue
            left_concepts = WikiCompiler._source_concepts(left_metadata)
            for right in sources[position + 1:]:
                pair = frozenset((left["id"], right["id"]))
                if pair in recorded_pairs:
                    continue
                right_metadata = right.get("metadata") or {}
                right_claims = right_metadata.get("claims") or {}
                if not isinstance(right_claims, dict):
                    continue
                shared_concepts = left_concepts & WikiCompiler._source_concepts(right_metadata)
                conflicting_claims = {
                    key
                    for key in left_claims.keys() & right_claims.keys()
                    if left_claims[key] != right_claims[key]
                }
                if not shared_concepts or not conflicting_claims:
                    continue
                newer, older = sorted(
                    (left, right),
                    key=lambda item: (str(item.get("captured_at") or ""), item["id"]),
                    reverse=True,
                )
                findings.append({
                    "source_id": newer["id"],
                    "contradicts_source_id": older["id"],
                    "basis": "conflicting_structured_claim_recency",
                    "shared_concepts": ",".join(sorted(shared_concepts)),
                    "conflicting_claims": ",".join(sorted(conflicting_claims)),
                })
        return sorted(findings, key=lambda item: (item["source_id"], item["contradicts_source_id"]))

    @staticmethod
    def _source_concepts(metadata: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for field in ("concepts", "entities", "tags", "ai_tags"):
            raw = metadata.get(field) or []
            if isinstance(raw, str):
                raw = [raw]
            if isinstance(raw, list):
                values.update(str(value).strip().lower() for value in raw if str(value).strip())
        return values

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
