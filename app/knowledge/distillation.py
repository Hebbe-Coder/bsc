"""Evidence-backed weekly knowledge and content distillation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class DistillationError(ValueError):
    """Raised when a weekly bundle would be ungrounded or overwrite a revision."""


@dataclass(frozen=True)
class WeeklyDistillationBundle:
    week: str
    paths: tuple[str, ...]


class WeeklyDistillationService:
    """Write deterministic three-track weekly output into a Vault's atomic snapshot."""

    def __init__(self, vault) -> None:
        self.vault = vault

    def distill(
        self,
        *,
        project_id: str,
        week: str,
        sources: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        rule_revision: str,
    ) -> WeeklyDistillationBundle:
        if not re.fullmatch(r"\d{4}-W\d{2}", week):
            raise DistillationError("week must use ISO YYYY-Www format")
        self._assert_project(project_id, sources, "sources")
        self._assert_project(project_id, pages, "pages")
        if not sources:
            raise DistillationError("weekly distillation requires at least one eligible source")
        prefix = f"distillations/{week}"
        rendered = {
            f"{prefix}/knowledge-action.md": self._knowledge_action(week, sources, pages),
            f"{prefix}/content-creation.md": self._content_creation(week, sources),
            f"{prefix}/context-pack.md": self._context_pack(project_id, week, sources, pages, rule_revision),
        }
        snapshot = dict(self.vault.contents)
        for path, content in rendered.items():
            existing = snapshot.get(path)
            if existing is not None and existing != content:
                raise DistillationError(f"distillation write conflict at {path}")
            snapshot[path] = content
        self.vault.commit(snapshot)
        return WeeklyDistillationBundle(week=week, paths=tuple(sorted(rendered)))

    @staticmethod
    def _assert_project(project_id: str, records: list[dict[str, Any]], label: str) -> None:
        if any(record.get("project_id") != project_id for record in records):
            raise DistillationError(f"{label} must be project scoped")

    @staticmethod
    def _title(source: dict[str, Any]) -> str:
        first = str(source.get("raw_content") or "").splitlines()[0].lstrip("# ").strip()
        return first or source["id"]

    def _knowledge_action(self, week: str, sources: list[dict[str, Any]], pages: list[dict[str, Any]]) -> str:
        lines = [f"# Knowledge Action - {week}", "", "## Source-backed changes"]
        for source in sources:
            excerpt = " ".join(str(source["raw_content"]).splitlines()[1:]).strip()[:360]
            lines.append(f"- **{self._title(source)}**: {excerpt or 'Review the source directly.'} [source:{source['id']}]")
        lines.extend(["", "## Existing decisions to revisit"])
        if pages:
            lines.extend(f"- [{page['id']}] {page.get('path', '')}" for page in pages)
        else:
            lines.append("- No published project decisions were supplied for this period.")
        lines.extend(["", "## Open questions", "- Confirm whether each new source changes an existing project decision before publishing a Wiki proposal."])
        return "\n".join(lines) + "\n"

    def _content_creation(self, week: str, sources: list[dict[str, Any]]) -> str:
        lines = [f"# Content Creation - {week}", "", "## Evidence-backed themes"]
        for source in sources:
            excerpt = " ".join(str(source["raw_content"]).splitlines()[1:]).strip()[:360]
            lines.extend([
                f"### {self._title(source)}",
                f"- Verified material: {excerpt or 'Read the cited source before drafting.'} [source:{source['id']}]",
                "- Suggested angle: explain the project implication, clearly separating the cited material from your own recommendation.",
            ])
        lines.extend(["", "## Research gaps", "- No uncited statement should be promoted from this file into publishable content."])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _context_pack(project_id: str, week: str, sources: list[dict[str, Any]], pages: list[dict[str, Any]], rule_revision: str) -> str:
        lines = [f"# Context Pack - {week}", "", f"Project: {project_id}", f"Rule revision: {rule_revision}", "", "## Sources"]
        lines.extend(f"- {source['id']}: {source.get('origin', '')}" for source in sources)
        lines.extend(["", "## Wiki pages"])
        lines.extend(f"- {page['id']}: {page.get('path', '')}" for page in pages)
        if not pages:
            lines.append("- No published Wiki pages included.")
        return "\n".join(lines) + "\n"
