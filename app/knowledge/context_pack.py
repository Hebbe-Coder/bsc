"""Deterministic, project-scoped context packs for Wiki-grounded generation."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.wiki_rules import ProjectRules


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
