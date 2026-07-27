"""Deterministic, project-scoped context packs for Wiki-grounded generation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.knowledge.vault import FilesystemWikiVault
from app.knowledge.wiki_repository import WikiRepository
from app.knowledge.wiki_rules import ProjectRules
from app.knowledge.wiki_rules import parse_project_rules


class ContextPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    rule_revision: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    rendered: str
    character_budget: int = Field(ge=512)
    character_count: int = Field(ge=0)
    page_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    omitted_refs: tuple[str, ...] = ()
    retrieval_refs: tuple[str, ...] = ()
    section_refs: tuple[str, ...] = ()
    weekly_distillation_id: str = ""
    token_budget: int = Field(ge=128)


class ContextPackBuilder:
    """Select full sections in deterministic priority order without cross-project leaks."""

    MINIMUM_SOURCE_EXCERPT_CHARACTERS = 640

    def __init__(self, *, max_characters: int = 12_000) -> None:
        if max_characters < 512:
            raise ValueError("max_characters must be at least 512")
        self.max_characters = max_characters

    def build(
        self,
        *,
        project_id: str,
        rules: ProjectRules,
        task_constraints: Iterable[str] = (),
        decisions: Iterable[dict[str, Any]] = (),
        pages: Iterable[dict[str, Any]] = (),
        sources: Iterable[dict[str, Any]] = (),
        evaluations: Iterable[dict[str, Any]] = (),
        weekly_distillation: dict[str, Any] | None = None,
        retrieval_refs: Iterable[str] = (),
        sources_first: bool = False,
    ) -> ContextPack:
        if rules.project_id != project_id:
            raise ValueError("rules must be project scoped")
        sections: list[tuple[str, str, str, str]] = [("rules", project_id, "Project Rules", rules.body)]
        sections.extend(
            ("constraint", f"constraint-{index}", "Task Constraint", text)
            for index, text in enumerate(task_constraints, start=1)
            if text.strip()
        )
        source_sections = self._records("source", "Evidence", project_id, sources, "raw_content")
        page_sections = [
            *self._records("decision", "Decision", project_id, decisions, "content"),
            *self._records("page", "Wiki Page", project_id, pages, "content"),
        ]
        sections.extend(source_sections if sources_first else page_sections)
        sections.extend(page_sections if sources_first else source_sections)
        sections.extend(self._records("evaluation", "Quality Evaluation", project_id, evaluations, "content"))
        if weekly_distillation:
            sections.extend(self._records("distillation", "Weekly Distillation", project_id, [weekly_distillation], "content"))

        included: list[tuple[str, str, str]] = []
        omitted: list[str] = []
        for kind, ref_id, label, content in sections:
            rendered = f"## [{kind}:{ref_id}] {label}\n{content.strip()}\n"
            if self._rendered_length(included, rendered) > self.max_characters:
                omitted.append(ref_id)
                continue
            included.append((kind, ref_id, rendered))

        source_candidates = [section for section in sections if section[0] == "source"]
        if source_candidates and not any(kind == "source" for kind, _, _ in included):
            minimum = min(self.MINIMUM_SOURCE_EXCERPT_CHARACTERS, max(160, self.max_characters // 2))
            while included and self._remaining_budget(included) < minimum:
                # Rules and explicit task constraints remain governing context;
                # published pages are derived material and can yield to A-layer evidence.
                removable_index = next(
                    (
                        index
                        for index in range(len(included) - 1, -1, -1)
                        if included[index][0] not in {"rules", "constraint"}
                    ),
                    None,
                )
                if removable_index is None:
                    break
                kind, ref_id, _ = included.pop(removable_index)
                omitted.append(f"{kind}:{ref_id}:budget_reserved_for_source")

            kind, ref_id, label, content = source_candidates[0]
            excerpt = self._bounded_section(
                kind=kind,
                ref_id=ref_id,
                label=label,
                content=content,
                # Existing sections retain their trailing newline when joined,
                # so the next section consumes an additional blank-line pair.
                available=max(0, self._remaining_budget(included) - (2 if included else 0)),
            )
            if excerpt:
                included.append((kind, ref_id, excerpt))
                omitted = [item for item in omitted if item != ref_id]
                omitted.append(f"{ref_id}:excerpted_for_budget")

        rendered = "\n".join(section for _, _, section in included).strip()
        page_ids = [ref_id for kind, ref_id, _ in included if kind == "page"]
        source_ids = [ref_id for kind, ref_id, _ in included if kind == "source"]
        section_refs = [f"{kind}:{ref_id}" for kind, ref_id, _ in included]
        revision = hashlib.sha256(
            f"{project_id}|{rules.revision}|{rendered}".encode("utf-8")
        ).hexdigest()
        return ContextPack(
            project_id=project_id,
            rule_revision=rules.revision,
            revision=revision,
            rendered=rendered,
            character_budget=self.max_characters,
            character_count=len(rendered),
            page_ids=tuple(page_ids),
            source_ids=tuple(source_ids),
            omitted_refs=tuple(omitted),
            retrieval_refs=tuple(dict.fromkeys(str(ref) for ref in retrieval_refs if str(ref))),
            section_refs=tuple(section_refs),
            weekly_distillation_id=str(weekly_distillation.get("id") or "") if weekly_distillation else "",
            token_budget=self.max_characters // 4,
        )

    def _rendered_length(self, included: list[tuple[str, str, str]], next_section: str = "") -> int:
        rendered = "\n".join([*(section for _, _, section in included), next_section]).strip()
        return len(rendered)

    def _remaining_budget(self, included: list[tuple[str, str, str]]) -> int:
        return max(0, self.max_characters - self._rendered_length(included))

    @staticmethod
    def _bounded_section(*, kind: str, ref_id: str, label: str, content: str, available: int) -> str:
        prefix = f"## [{kind}:{ref_id}] {label}\n"
        normalized_content = content.strip()
        full = f"{prefix}{normalized_content}\n"
        if len(full) <= available:
            return full
        marker = "\n[CONTEXT_EXCERPT: content truncated; consult the immutable source]\n"
        room = available - len(prefix) - len(marker)
        if room < 160:
            return ""
        head = max(1, (room * 3) // 4)
        tail = max(1, room - head)
        return (
            f"{prefix}{ContextPackBuilder._head_at_boundary(normalized_content, head)}"
            f"{marker}{ContextPackBuilder._tail_at_boundary(normalized_content, tail)}\n"
        )

    @staticmethod
    def _head_at_boundary(content: str, limit: int) -> str:
        candidate = content[:limit].rstrip()
        boundary = max(candidate.rfind(marker) for marker in ("\n", ".", "!", "?", "。", "！", "？"))
        if boundary >= max(80, limit // 2):
            return candidate[:boundary + 1].rstrip()
        return candidate

    @staticmethod
    def _tail_at_boundary(content: str, limit: int) -> str:
        candidate = content[-limit:].lstrip()
        boundaries = [candidate.find(marker) + 1 for marker in ("\n", ".", "!", "?", "。", "！", "？")]
        boundary = min((index for index in boundaries if index > 0), default=0)
        if 0 < boundary <= len(candidate) // 2:
            return candidate[boundary:].lstrip()
        return candidate

    @staticmethod
    def _records(
        kind: str,
        label: str,
        project_id: str,
        records: Iterable[dict[str, Any]],
        content_field: str,
    ) -> list[tuple[str, str, str, str]]:
        output = []
        for record in records:
            if record.get("project_id") != project_id:
                raise ValueError(f"{kind} records must be project scoped")
            ref_id = str(record.get("id") or record.get("path") or "")
            content = str(record.get(content_field) or "").strip()
            if not ref_id or not content:
                continue
            output.append((kind, ref_id, label, content))
        return output


class WikiContextProvider:
    """Build a bounded, traceable SOP/content context from one project Wiki."""

    def __init__(
        self,
        repository: WikiRepository | None = None,
        *,
        vault_root: Path | str | None = None,
        max_characters: int = 12_000,
        retrieval_service=None,
    ) -> None:
        self.repository = repository or WikiRepository()
        self.vault_root = Path(vault_root) if vault_root else Path(settings.OBSIDIAN_VAULT_ROOT) if settings.OBSIDIAN_VAULT_ROOT else None
        self.builder = ContextPackBuilder(max_characters=max_characters)
        if retrieval_service is None:
            from app.knowledge.service import KnowledgeService

            retrieval_service = KnowledgeService(repo=self.repository)
        self.retrieval_service = retrieval_service

    def build_context(self, *, project_id: str, task_constraints: Iterable[str] = ()) -> ContextPack | None:
        """Return ``None`` when the project has no configured Wiki authority."""
        task_constraints = tuple(task_constraints)
        mapping = self.repository.get_vault(project_id)
        if not mapping or self.vault_root is None:
            return None
        vault = FilesystemWikiVault(self.vault_root, project_id, mapping["vault_path"])
        rules_path = vault.project_root / "AGENTS.md"
        if not rules_path.is_file():
            return None
        rules = parse_project_rules(rules_path.read_text(encoding="utf-8"))
        if rules.project_id != project_id:
            raise ValueError("AGENTS.md project_id does not match the requested project")

        decisions: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        for page in self.repository.list_pages(project_id):
            content = self.repository.get_page_content(project_id, page["id"])
            if not content:
                continue
            item = {**page, "content": content["content"]}
            (decisions if page.get("page_kind") == "decision" else pages).append(item)

        sources = [
            source
            for status in ("eligible", "processed")
            for source in self.repository.list_sources(project_id, status=status)
        ]
        retrieval_refs = self._candidate_refs(project_id, task_constraints)
        if retrieval_refs:
            selected_page_paths = {ref for ref in retrieval_refs if ref == "AGENTS.md" or ref.startswith("wiki/")}
            selected_source_ids = retrieval_refs - selected_page_paths
            decisions = [item for item in decisions if item.get("path") in selected_page_paths]
            pages = [item for item in pages if item.get("path") in selected_page_paths]
            sources = [item for item in sources if item.get("id") in selected_source_ids]
        evaluations = [
            {
                "id": evaluation["id"],
                "project_id": project_id,
                "content": self._render_evaluation(evaluation),
            }
            for evaluation in self.repository.list_eval_runs(project_id, limit=5)
        ]
        weekly = self._latest_distillation(project_id, vault)
        return self.builder.build(
            project_id=project_id,
            rules=rules,
            task_constraints=task_constraints,
            decisions=decisions,
            pages=pages,
            sources=sources,
            evaluations=evaluations,
            weekly_distillation=weekly,
            retrieval_refs=sorted(retrieval_refs),
        )

    def _candidate_refs(self, project_id: str, task_constraints: Iterable[str]) -> set[str]:
        query = "\n".join(str(item).strip() for item in task_constraints if str(item).strip())
        if not query:
            return set()
        hits = self.retrieval_service.retrieve(query, project_id=project_id, top_k=24, rerank=True)
        references: set[str] = set()
        for hit in hits or []:
            source = str(hit.get("source") or "")
            evidence_prefix = f"evidence://{project_id}/"
            wiki_prefix = f"wiki://{project_id}/"
            if source.startswith(evidence_prefix):
                references.add(source[len(evidence_prefix):])
            elif source.startswith(wiki_prefix):
                references.add(source[len(wiki_prefix):])
        return references

    def _latest_distillation(self, project_id: str, vault: FilesystemWikiVault) -> dict[str, Any] | None:
        records = self.repository.list_distillations(project_id)
        if not records:
            return None
        record = records[0]
        content = vault.contents.get(record["context_path"], "")
        if not content:
            return None
        return {"id": record["id"], "project_id": project_id, "content": content}

    @staticmethod
    def _render_evaluation(evaluation: dict[str, Any]) -> str:
        summary = evaluation.get("summary") or {}
        score = summary.get("score", "")
        findings = summary.get("findings") or []
        return f"Status: {evaluation.get('status', '')}; score: {score}; findings: {findings}"
