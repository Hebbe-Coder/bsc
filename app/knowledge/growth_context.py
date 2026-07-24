"""Bounded, deterministic context construction for project-specific generation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.generation_provenance import redact_secrets, sanitize_untrusted_text
from app.knowledge.source_triage import source_admission_reason


class ContextOmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    reason: str


class GrowthContextPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    revision: str = Field(min_length=64, max_length=64)
    context_hash: str = Field(min_length=64, max_length=64)
    profile_revision: int = Field(ge=0)
    rules_revision: str = Field(min_length=1)
    rendered: str
    rendered_sections: tuple[str, ...] = ()
    character_budget: int = Field(ge=512)
    character_count: int = Field(ge=0)
    token_budget: int = Field(ge=1)
    estimated_tokens: int = Field(ge=0)
    provenance: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    project_context_source_ids: tuple[str, ...] = ()
    page_ids: tuple[str, ...] = ()
    index_refs: tuple[str, ...] = ()
    method_revision_ids: tuple[str, ...] = ()
    output_ids: tuple[str, ...] = ()
    rejected_output_ids: tuple[str, ...] = ()
    regression_constraints: tuple[str, ...] = ()
    evaluation_ids: tuple[str, ...] = ()
    feedback_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    research_gaps: tuple[str, ...] = ()
    omitted_refs: tuple[str, ...] = ()
    omissions: tuple[ContextOmission, ...] = ()
    source_cutoff: str = ""
    creation_run_id: str = ""
    task: str
    index_fallback_used: bool = False


@dataclass(frozen=True)
class _Candidate:
    priority: int
    kind: str
    ref: str
    revision: str
    content: str

    @property
    def key(self) -> tuple[int, str, str, str]:
        return (self.priority, self.kind, self.ref, self.revision)


class GrowthContextBuilder:
    """Build a bounded context in B -> A -> C -> D/review order."""

    _STATUS_ALLOWED = {"", "active", "approved", "accepted", "eligible", "processed", "published", "filed"}
    MAX_CHARACTERS = 48_000
    MINIMUM_SOURCE_EXCERPT_CHARACTERS = 640

    def __init__(self, max_characters: int = 12_000, *, characters_per_token: int = 4) -> None:
        if max_characters < 512:
            raise ValueError("max_characters must be at least 512")
        if max_characters > self.MAX_CHARACTERS:
            raise ValueError(f"max_characters must not exceed {self.MAX_CHARACTERS}")
        if characters_per_token < 1:
            raise ValueError("characters_per_token must be positive")
        self.max_characters = max_characters
        self.characters_per_token = characters_per_token

    def build(
        self,
        *,
        project_id: str,
        profile: dict[str, Any],
        rules: str,
        task: str,
        pages: Iterable[dict[str, Any]] = (),
        sources: Iterable[dict[str, Any]] = (),
        project_contexts: Iterable[dict[str, Any]] = (),
        methods: Iterable[dict[str, Any]] = (),
        outputs: Iterable[dict[str, Any]] = (),
        evaluations: Iterable[dict[str, Any]] = (),
        feedback: Iterable[dict[str, Any]] = (),
        weekly_distillation: Iterable[dict[str, Any]] = (),
        assumptions: Iterable[str] = (),
        research_gaps: Iterable[str] = (),
        rules_revision: str = "",
        source_cutoff: str = "",
        creation_run_id: str = "",
        retrieval_refs: Iterable[str] = (),
        index_available: bool = True,
    ) -> GrowthContextPack:
        profile_revision = int(profile.get("revision", 0) or 0)
        resolved_rules_revision = rules_revision or hashlib.sha256((rules or "").encode("utf-8")).hexdigest()[:16]
        omissions: list[ContextOmission] = []
        provenance = [f"profile:{profile_revision}", f"rules:{resolved_rules_revision}"]
        candidates: list[_Candidate] = []
        seen: set[tuple[str, str]] = set()
        seen_revisions: set[tuple[str, str]] = set()

        groups = (
            (10, "page", pages, "content"),
            (15, "project_context", project_contexts, "raw_content"),
            (20, "source", sources, "raw_content"),
            (30, "method", methods, "body"),
            (40, "output", outputs, "content"),
            (50, "evaluation", evaluations, "content"),
            (60, "feedback", feedback, "content"),
            (70, "distillation", weekly_distillation, "content"),
        )
        for priority, kind, records, field in groups:
            ordered_records = sorted(
                list(records),
                key=lambda record: (
                    str(record.get("id") or ""),
                    str(record.get("revision") or record.get("revision_id") or record.get("content_hash") or ""),
                    hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest(),
                ),
            )
            for record in ordered_records:
                self._validate_scope(project_id, kind, record)
                ref = str(record.get("id") or "").strip()
                if not ref:
                    continue
                if kind == "page" and self._is_rules_page(record):
                    omissions.append(ContextOmission(ref=f"page:{ref}", reason="rules_bound_separately"))
                    continue
                if kind == "page" and self._is_audit_log(record):
                    omissions.append(ContextOmission(ref=f"page:{ref}", reason="audit_log_not_generation_context"))
                    continue
                candidate_kind = kind
                candidate_priority = priority
                if kind == "page" and self._is_navigation_index(record):
                    candidate_kind = "index"
                    # Navigation helps retrieval, but generated conclusions must
                    # prefer published B-layer concepts and immutable evidence.
                    candidate_priority = 80
                elif kind == "page":
                    candidate_priority = self._published_page_priority(record, default=priority)
                ref_key = (candidate_kind, ref)
                if ref_key in seen:
                    omissions.append(ContextOmission(ref=f"{candidate_kind}:{ref}", reason="duplicate"))
                    continue
                seen.add(ref_key)
                status = str(record.get("status") or "").lower()
                if kind == "method" and status not in {"approved", "published"}:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="method_not_approved"))
                    continue
                if kind == "output" and status in {"rejected", "archived", "superseded"}:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="failure_example_prose_excluded"))
                    findings = (record.get("quality") or {}).get("findings") or record.get("findings") or []
                    constraint = f"Do not reuse rejected output {ref} as evidence or prose. Evaluator findings: {findings}"
                    candidates.append(_Candidate(45, "constraint", ref, self._revision(record, constraint), constraint))
                    continue
                if kind == "output" and status not in {"accepted", "filed"}:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="output_not_accepted"))
                    continue
                if kind == "project_context" and status not in {"captured", "validated", "eligible", "processed"}:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="project_context_unavailable"))
                    continue
                if kind in {"source", "page"} and status not in self._STATUS_ALLOWED:
                    reason = "failed_reliability" if status in {"failed", "rejected", "quarantined", "untrusted"} else "stale_or_ineligible"
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason=reason))
                    continue
                content = str(record.get(field) or "").strip()
                if not content:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="empty"))
                    continue
                revision = self._revision(record, content)
                revision_key = (kind, revision)
                if kind in {"source", "page"} and revision_key in seen_revisions:
                    omissions.append(ContextOmission(ref=f"{kind}:{ref}", reason="duplicate_content"))
                    continue
                if kind in {"source", "page"}:
                    seen_revisions.add(revision_key)
                candidates.append(_Candidate(candidate_priority, candidate_kind, ref, revision, content))

        requested_refs = {str(item) for item in retrieval_refs if str(item)}
        if requested_refs:
            selected_candidates: list[_Candidate] = []
            for item in candidates:
                if item.ref in requested_refs or f"{item.kind}:{item.ref}" in requested_refs:
                    selected_candidates.append(item)
                else:
                    omissions.append(ContextOmission(ref=f"{item.kind}:{item.ref}", reason="retrieval_not_selected"))
            candidates = selected_candidates

        mandatory = (
            self._trusted_section("profile", str(profile_revision), json.dumps(redact_secrets(profile), ensure_ascii=False, sort_keys=True, default=str)),
            self._trusted_section("rules", resolved_rules_revision, str(redact_secrets(rules or ""))),
            self._trusted_section("task", "request", str(redact_secrets(task or ""))),
        )
        # A growth run must not turn into a rules-only prompt. Reserve a
        # bounded excerpt for A-layer evidence before fitting trusted metadata.
        evidence_reserve = self._evidence_reserve(candidates, mandatory_count=len(mandatory))
        rendered_sections: list[str] = []
        used = 0
        for index, section in enumerate(mandatory):
            remaining_required = len(mandatory) - index - 1
            # Reserve both content and separators for the required sections
            # that follow. Without this, a near-limit rules document could
            # leave the final task section two characters over budget.
            separator = 2 if rendered_sections else 0
            reserve = (remaining_required * 50) + evidence_reserve
            available = max(0, self.max_characters - used - separator - reserve)
            fitted = self._fit(section, available)
            if fitted:
                rendered_sections.append(fitted)
                used += separator + len(fitted)

        included_candidates: list[_Candidate] = []
        for item in sorted(candidates, key=lambda candidate: candidate.key):
            section = self._untrusted_section(item)
            if len("\n\n".join([*rendered_sections, section])) > self.max_characters:
                omissions.append(ContextOmission(ref=f"{item.kind}:{item.ref}", reason="budget"))
                continue
            rendered_sections.append(section)
            included_candidates.append(item)

        source_candidates = [item for item in sorted(candidates, key=lambda candidate: candidate.key) if item.kind == "source"]
        if source_candidates and not any(item.kind == "source" for item in included_candidates):
            source = source_candidates[0]
            while included_candidates and self._remaining_budget(rendered_sections) < self.MINIMUM_SOURCE_EXCERPT_CHARACTERS:
                evictable = [
                    (index, candidate)
                    for index, candidate in enumerate(included_candidates)
                    if candidate.kind != "page" or sum(item.kind == "page" for item in included_candidates) > 1
                ]
                if not evictable:
                    break
                # Remove the least authoritative included candidate first. This
                # preserves at least one substantive B page alongside A evidence.
                evict_index, evicted = max(
                    evictable,
                    key=lambda item: (item[1].priority, item[1].kind == "index", item[1].ref),
                )
                included_candidates.pop(evict_index)
                rendered_sections.pop(len(rendered_sections) - len(included_candidates) - 1 + evict_index)
                omissions.append(ContextOmission(ref=f"{evicted.kind}:{evicted.ref}", reason="budget_reserved_for_source"))

            excerpt = self._bounded_untrusted_section(source, self._remaining_budget(rendered_sections))
            if excerpt:
                rendered_sections.append(excerpt)
                included_candidates.append(source)
                omissions = [
                    item for item in omissions
                    if not (item.ref == f"source:{source.ref}" and item.reason == "budget")
                ]
                omissions.append(ContextOmission(ref=f"source:{source.ref}", reason="excerpted_for_budget"))

        included: dict[str, list[str]] = {
            kind: []
            for kind in (
                "index",
                "page",
                "project_context",
                "source",
                "method",
                "output",
                "constraint",
                "evaluation",
                "feedback",
                "distillation",
            )
        }
        for item in included_candidates:
            included[item.kind].append(item.ref if item.kind != "method" else item.revision)
            provenance_kind = "output" if item.kind == "constraint" else item.kind
            provenance.extend((f"{provenance_kind}:{item.ref}", f"{provenance_kind}:{item.ref}@{item.revision}"))

        rendered = "\n\n".join(rendered_sections)
        if len(rendered) > self.max_characters:
            raise RuntimeError("context renderer exceeded its character budget")
        explicit_assumptions = tuple(dict.fromkeys(["assumption:unresolved_claims", *[str(item) for item in assumptions if str(item)]]))
        explicit_gaps = tuple(dict.fromkeys(str(item) for item in research_gaps if str(item)))
        context_hash = hashlib.sha256(
            json.dumps(
                {
                    "project_id": project_id,
                    "source_cutoff": source_cutoff,
                    "rendered": rendered,
                    "omissions": [item.model_dump() for item in omissions],
                    "assumptions": explicit_assumptions,
                    "research_gaps": explicit_gaps,
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        omission_refs = tuple(dict.fromkeys(item.ref for item in omissions))
        return GrowthContextPack(
            project_id=project_id,
            revision=context_hash,
            context_hash=context_hash,
            profile_revision=profile_revision,
            rules_revision=resolved_rules_revision,
            rendered=rendered,
            rendered_sections=tuple(rendered_sections),
            character_budget=self.max_characters,
            character_count=len(rendered),
            token_budget=max(1, self.max_characters // self.characters_per_token),
            estimated_tokens=math.ceil(len(rendered) / self.characters_per_token),
            provenance=tuple(dict.fromkeys(provenance)),
            source_ids=tuple(included["source"]),
            project_context_source_ids=tuple(included["project_context"]),
            page_ids=tuple(included["page"]),
            index_refs=tuple(included["index"]),
            method_revision_ids=tuple(included["method"]),
            output_ids=tuple(included["output"]),
            rejected_output_ids=tuple(included["constraint"]),
            regression_constraints=tuple(
                f"Rejected output {ref} is a failure pattern and must not be reused as factual evidence."
                for ref in included["constraint"]
            ),
            evaluation_ids=tuple(included["evaluation"]),
            feedback_ids=tuple(included["feedback"]),
            assumptions=explicit_assumptions,
            research_gaps=explicit_gaps,
            omitted_refs=omission_refs,
            omissions=tuple(omissions),
            source_cutoff=source_cutoff,
            creation_run_id=creation_run_id,
            task=task,
            index_fallback_used=not index_available,
        )

    @staticmethod
    def _validate_scope(project_id: str, kind: str, record: dict[str, Any]) -> None:
        if record.get("project_id") != project_id:
            raise ValueError(f"{kind} records must be project scoped")

    def _remaining_budget(self, sections: list[str]) -> int:
        used = len("\n\n".join(sections))
        separator = 2 if sections else 0
        return max(0, self.max_characters - used - separator)

    def _evidence_reserve(self, candidates: Iterable[_Candidate], *, mandatory_count: int) -> int:
        if not any(candidate.kind == "source" for candidate in candidates):
            return 0
        mandatory_floor = (mandatory_count * 48) + (max(0, mandatory_count - 1) * 2)
        return min(
            self.MINIMUM_SOURCE_EXCERPT_CHARACTERS,
            max(0, self.max_characters - mandatory_floor),
        )

    @staticmethod
    def _bounded_untrusted_section(candidate: _Candidate, available: int) -> str:
        section = GrowthContextBuilder._untrusted_section(candidate)
        if len(section) <= available:
            return section
        marker = "\n[CONTEXT_EXCERPT: content truncated; consult the immutable source]\n"
        room = available - len(marker)
        if room < 160:
            return ""
        head = max(1, (room * 3) // 4)
        tail = max(1, room - head)
        return f"{section[:head]}{marker}{section[-tail:]}"

    @staticmethod
    def _revision(record: dict[str, Any], content: str) -> str:
        for key in ("revision", "revision_id", "active_revision_id", "content_hash", "updated_at", "created_at"):
            value = str(record.get(key) or "").strip()
            if value:
                return value
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _trusted_section(kind: str, ref: str, content: str) -> str:
        return f"## [{kind}:{ref}]\n{content.strip()}"

    @staticmethod
    def _untrusted_section(candidate: _Candidate) -> str:
        role = {
            "page": "PUBLISHED_B_KNOWLEDGE",
            "index": "NAVIGATION_INDEX_NOT_AUTHORITY",
            "project_context": "PROJECT_CONTEXT_NOT_FACTUAL_EVIDENCE",
            "source": "EXACT_A_EVIDENCE",
            "method": "APPROVED_METHOD_GUIDANCE_NOT_FACTUAL_EVIDENCE",
            "output": "ACCEPTED_STYLE_EXAMPLE_NOT_FACTUAL_EVIDENCE",
            "constraint": "REJECTED_OUTPUT_REGRESSION_CONSTRAINT",
            "evaluation": "EVALUATOR_FINDING_NOT_FACTUAL_EVIDENCE",
            "feedback": "USER_FEEDBACK_NOT_FACTUAL_EVIDENCE",
            "distillation": "PRIOR_SYNTHESIS_NOT_FACTUAL_EVIDENCE",
        }.get(candidate.kind, "UNTRUSTED_DATA")
        data = sanitize_untrusted_text(
            f"[DATA_ROLE: {role}]\n{candidate.content}",
            data_kind=candidate.kind,
            ref_id=candidate.ref,
        )
        return f"## [{candidate.kind}:{candidate.ref}@{candidate.revision}]\n{data}"

    @staticmethod
    def _is_navigation_index(record: dict[str, Any]) -> bool:
        path = str(record.get("path") or "").replace("\\", "/").lower()
        page_kind = str(record.get("page_kind") or record.get("kind") or "").lower()
        return page_kind in {"index", "navigation"} or path.endswith("/index.md") or path == "wiki/index.md"

    @staticmethod
    def _is_rules_page(record: dict[str, Any]) -> bool:
        return str(record.get("path") or "").replace("\\", "/") == "AGENTS.md"

    @staticmethod
    def _is_audit_log(record: dict[str, Any]) -> bool:
        return str(record.get("path") or "").replace("\\", "/") == "wiki/log.md"

    @staticmethod
    def _published_page_priority(record: dict[str, Any], *, default: int) -> int:
        path = str(record.get("path") or "").replace("\\", "/").lower()
        page_kind = str(record.get("page_kind") or record.get("kind") or "").lower()
        if path.startswith(("wiki/concepts/", "wiki/decisions/", "wiki/sops/")) or page_kind in {"concept", "decision", "sop"}:
            return min(default, 10)
        if path == "wiki/overview.md" or page_kind == "brief":
            return max(default, 30)
        return default

    @staticmethod
    def _fit(section: str, available: int) -> str:
        if available <= 0:
            return ""
        if len(section) <= available:
            return section
        marker = "\n[TRUNCATED_FOR_BUDGET]"
        if available <= len(marker):
            return section[:available]
        return section[: available - len(marker)] + marker


class GrowthContextService:
    """Assemble project context from authoritative growth records."""

    MAX_RECORDS = 500
    MAX_FILE_BYTES = 64 * 1024

    def __init__(self, repository: Any, vault_root: Path | str, *, builder: GrowthContextBuilder | None = None) -> None:
        self.repository = repository
        self.vault_root = Path(vault_root).resolve()
        self.builder = builder or GrowthContextBuilder()

    def build_context(
        self,
        *,
        project_id: str,
        task: str,
        source_cutoff: str = "",
        creation_run_id: str = "",
    ) -> GrowthContextPack:
        if not project_id.strip():
            raise ValueError("project_id is required")
        profile = self.repository.get_profile(project_id) or {
            "project_id": project_id,
            "revision": 0,
            "availability": "profile_unconfigured",
        }
        project_root = self._project_root(project_id)
        rules, rules_revision, rule_gaps = self._rules(project_id, project_root)
        pages = self._pages(project_id)
        sources: list[dict[str, Any]] = []
        project_contexts: list[dict[str, Any]] = []
        for source in self.repository.list_sources(project_id):
            metadata = source.get("metadata") or {}
            is_project_context = (
                str(source.get("source_type") or "") == "obsidian_project_context"
                or str(metadata.get("obsidian_workspace_role") or "") == "project_context"
            )
            if is_project_context:
                if (
                    metadata.get("source_present") is not False
                    and source.get("status") in {"captured", "validated", "eligible", "processed"}
                ):
                    project_contexts.append(source)
                continue
            if (
                source.get("status") in {"eligible", "processed"}
                and not source_admission_reason(self.repository, project_id, source)
            ):
                sources.append(source)
        sources = sources[: self.MAX_RECORDS]
        project_contexts = project_contexts[: self.MAX_RECORDS]
        methods = self._methods(project_id)
        outputs = self._outputs(project_id, project_root)
        return self.builder.build(
            project_id=project_id,
            profile=profile,
            rules=rules,
            rules_revision=rules_revision,
            task=task,
            pages=pages,
            sources=sources,
            project_contexts=project_contexts,
            methods=methods,
            outputs=outputs,
            evaluations=self._evaluations(project_id),
            feedback=self._feedback(project_id),
            weekly_distillation=self._distillations(project_id, project_root),
            research_gaps=rule_gaps,
            source_cutoff=source_cutoff,
            creation_run_id=creation_run_id,
            index_available=any(self.builder._is_navigation_index(page) for page in pages),
        )

    def _project_root(self, project_id: str) -> Path | None:
        mapping = self.repository.get_vault(project_id)
        if not mapping or not self.vault_root.is_dir():
            return None
        from app.knowledge.vault import FilesystemWikiVault

        return FilesystemWikiVault(
            self.vault_root,
            project_id,
            str(mapping.get("vault_path") or ""),
        ).project_root

    def _rules(self, project_id: str, project_root: Path | None) -> tuple[str, str, list[str]]:
        from app.knowledge.wiki_rules import build_default_agents_rules, parse_project_rules

        path = project_root / "AGENTS.md" if project_root else None
        if path and path.is_file() and not path.is_symlink():
            text = self._read_text(path, project_root)
            parsed = parse_project_rules(text)
            if parsed.project_id != project_id:
                raise ValueError("AGENTS.md project_id does not match the requested project")
            return text, parsed.revision, []
        fallback = build_default_agents_rules(project_id)
        parsed = parse_project_rules(fallback)
        return fallback, parsed.revision, ["project_agents_rules_unavailable"]

    def _pages(self, project_id: str) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for page in self.repository.list_pages(project_id)[: self.MAX_RECORDS]:
            revision = self.repository.get_page_content(project_id, page["id"])
            if not revision:
                continue
            pages.append(
                {
                    **page,
                    "project_id": project_id,
                    "status": "published",
                    "revision": revision.get("id") or revision.get("content_hash") or "",
                    "content": revision.get("content") or "",
                }
            )
        return pages

    def _methods(self, project_id: str) -> list[dict[str, Any]]:
        revisions: list[dict[str, Any]] = []
        for method in self.repository.list_methods(project_id, status="published", limit=self.MAX_RECORDS):
            revision_id = str(method.get("active_revision_id") or "")
            revision = self.repository.get_method_revision(project_id, revision_id) if revision_id else None
            if not revision or revision.get("method_id") != method.get("id") or revision.get("status") != "published":
                continue
            revisions.append(
                {
                    **revision,
                    "id": revision["id"],
                    "project_id": project_id,
                    "status": "published",
                    "method_id": method["id"],
                    "method_slug": method.get("slug") or "",
                    "revision": revision["id"],
                }
            )
        return revisions

    def _outputs(self, project_id: str, project_root: Path | None) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for output in self.repository.list_outputs(project_id, limit=self.MAX_RECORDS):
            # Keep pending records visible to the context builder as omission
            # evidence, without reading their unreviewed body from the Vault.
            # This makes the D-layer review boundary auditable while preserving
            # the rule that only accepted/filed prose can become context.
            if output.get("status") not in {
                "registered", "evaluating", "accepted", "filed", "rejected"
            }:
                continue
            content = ""
            if (
                output.get("status") in {"accepted", "filed"}
                and project_root
                and str(output.get("mime_type") or "").startswith("text/")
            ):
                content = self._read_relative(project_root, str(output.get("vault_path") or ""))
            outputs.append({**output, "content": content})
        return outputs

    def _evaluations(self, project_id: str) -> list[dict[str, Any]]:
        records = self.repository.list_output_evaluations(project_id, limit=self.MAX_RECORDS)
        return [
            {
                **record,
                "project_id": project_id,
                "content": json.dumps(
                    {
                        "output_id": record.get("output_id"),
                        "quality": record.get("quality"),
                        "status": record.get("status"),
                        "findings": record.get("findings") or [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for record in records
        ]

    def _feedback(self, project_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record in self.repository.list_feedback(project_id, limit=self.MAX_RECORDS):
            content = "\n".join(
                value
                for value in (
                    str(record.get("feedback_type") or ""),
                    str(record.get("correction") or ""),
                    str(record.get("comment") or ""),
                )
                if value
            )
            if content:
                records.append({**record, "project_id": project_id, "content": content})
        return records

    def _distillations(self, project_id: str, project_root: Path | None) -> list[dict[str, Any]]:
        if not project_root:
            return []
        records: list[dict[str, Any]] = []
        for record in self.repository.list_growth_distillations(project_id, kind="weekly", limit=10):
            sections = [self._read_relative(project_root, str(path)) for path in record.get("paths") or []]
            content = "\n\n".join(section for section in sections if section)
            if content:
                records.append(
                    {
                        **record,
                        "project_id": project_id,
                        "revision": record.get("input_hash") or record.get("id") or "",
                        "content": content,
                    }
                )
        return records

    def _read_relative(self, project_root: Path, relative_path: str) -> str:
        if not relative_path:
            return ""
        candidate = (project_root / Path(relative_path.replace("\\", "/"))).resolve()
        if project_root.resolve() not in candidate.parents:
            raise ValueError("context file escaped the project Vault")
        if not candidate.is_file() or candidate.is_symlink():
            return ""
        return self._read_text(candidate, project_root)

    def _read_text(self, path: Path, project_root: Path) -> str:
        resolved = path.resolve()
        root = project_root.resolve()
        if root not in resolved.parents:
            raise ValueError("context file escaped the project Vault")
        with resolved.open("rb") as handle:
            payload = handle.read(self.MAX_FILE_BYTES + 1)
        suffix = ""
        if len(payload) > self.MAX_FILE_BYTES:
            payload = payload[: self.MAX_FILE_BYTES]
            suffix = "\n[TRUNCATED_FOR_FILE_LIMIT]"
        try:
            return payload.decode("utf-8") + suffix
        except UnicodeDecodeError:
            return ""
