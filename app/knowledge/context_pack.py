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


class ContextPackBuilder:
    """Select full sections in deterministic priority order without cross-project leaks."""

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
    ) -> ContextPack:
        if rules.project_id != project_id:
            raise ValueError("rules must be project scoped")
        sections: list[tuple[str, str, str, str]] = [("rules", project_id, "Project Rules", rules.body)]
        sections.extend(
            ("constraint", f"constraint-{index}", "Task Constraint", text)
            for index, text in enumerate(task_constraints, start=1)
            if text.strip()
        )
        sections.extend(self._records("decision", "Decision", project_id, decisions, "content"))
        sections.extend(self._records("page", "Wiki Page", project_id, pages, "content"))
        sections.extend(self._records("source", "Evidence", project_id, sources, "raw_content"))
        sections.extend(self._records("evaluation", "Quality Evaluation", project_id, evaluations, "content"))
        if weekly_distillation:
            sections.extend(self._records("distillation", "Weekly Distillation", project_id, [weekly_distillation], "content"))

        included: list[str] = []
        omitted: list[str] = []
        page_ids: list[str] = []
        source_ids: list[str] = []
        used = 0
        for kind, ref_id, label, content in sections:
            rendered = f"## [{kind}:{ref_id}] {label}\n{content.strip()}\n"
            if used + len(rendered) > self.max_characters:
                omitted.append(ref_id)
                continue
            included.append(rendered)
            used += len(rendered)
            if kind == "page":
                page_ids.append(ref_id)
            elif kind == "source":
                source_ids.append(ref_id)
        rendered = "\n".join(included).strip()
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
        )

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
    ) -> None:
        self.repository = repository or WikiRepository()
        self.vault_root = Path(vault_root) if vault_root else Path(settings.OBSIDIAN_VAULT_ROOT) if settings.OBSIDIAN_VAULT_ROOT else None
        self.builder = ContextPackBuilder(max_characters=max_characters)

    def build_context(self, *, project_id: str, task_constraints: Iterable[str] = ()) -> ContextPack | None:
        """Return ``None`` when the project has no configured Wiki authority."""
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
        )

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
