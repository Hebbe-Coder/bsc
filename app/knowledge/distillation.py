"""Evidence-backed weekly knowledge and content distillation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.knowledge.context_pack import ContextPack


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
        source_cutoff: str = "",
        evaluations: list[dict[str, Any]] | None = None,
        contradictions: list[dict[str, Any]] | None = None,
        context_pack: ContextPack | None = None,
    ) -> WeeklyDistillationBundle:
        if not re.fullmatch(r"\d{4}-W\d{2}", week):
            raise DistillationError("week must use ISO YYYY-Www format")
        self._assert_project(project_id, sources, "sources")
        self._assert_project(project_id, pages, "pages")
        if not sources:
            raise DistillationError("weekly distillation requires at least one eligible source")
        source_cutoff = source_cutoff or self.source_cutoff(sources)
        prefix = f"distillations/{week}"
        rendered = {
            f"{prefix}/knowledge-action.md": self._knowledge_action(
                week, sources, pages, source_cutoff, evaluations or [], contradictions or []
            ),
            f"{prefix}/content-creation.md": self._content_creation(week, sources, source_cutoff),
            f"{prefix}/context-pack.md": self._context_pack(
                project_id, week, sources, pages, rule_revision, source_cutoff, context_pack
            ),
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
    def source_cutoff(sources: list[dict[str, Any]]) -> str:
        """Return the stable immutable-evidence cutoff for one weekly bundle."""
        return hashlib.sha256(
            "|".join(
                f"{source['id']}:{source.get('content_hash') or hashlib.sha256(str(source.get('raw_content') or '').encode('utf-8')).hexdigest()}"
                for source in sorted(sources, key=lambda item: item["id"])
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _title(source: dict[str, Any]) -> str:
        first = str(source.get("raw_content") or "").splitlines()[0].lstrip("# ").strip()
        return first or source["id"]

    def _knowledge_action(
        self,
        week: str,
        sources: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        source_cutoff: str,
        evaluations: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
    ) -> str:
        lines = [f"# Knowledge Action - {week}", "", f"Source cutoff: `{source_cutoff}`", "", "## Changed beliefs"]
        changed = [source for source in sources if source.get("supersedes_id")]
        if changed:
            lines.extend(
                f"- {source['id']} supersedes {source['supersedes_id']}; review every citation to the prior evidence. [source:{source['id']}]"
                for source in changed
            )
        else:
            lines.append("- No source supersession was recorded in this cutoff.")
        lines.extend(["", "## Contradictions"])
        if contradictions:
            lines.extend(
                f"- {item.get('source_id', '')} conflicts with {item.get('contradicts_source_id', '')}; resolution remains pending review."
                for item in contradictions
            )
        else:
            lines.append("- No explicit contradiction relation was recorded.")
        lines.extend(["", "## Quality gate findings"])
        quality_findings = [
            finding
            for evaluation in evaluations
            for finding in (evaluation.get("summary", {}).get("findings") or [])
        ]
        if quality_findings:
            lines.extend(f"- {finding.get('code', 'finding')}: {finding.get('detail', '')}" for finding in quality_findings)
        else:
            lines.append("- No persisted evaluation finding was supplied for this cutoff.")
        lines.extend(["", "## Source-backed actions"])
        for source in sources:
            excerpt = " ".join(str(source["raw_content"]).splitlines()[1:]).strip()[:360]
            lines.append(f"- Review **{self._title(source)}** and decide whether it changes a project control: {excerpt or 'Review the source directly.'} [source:{source['id']}]")
        lines.extend(["", "## Existing decisions to revisit"])
        if pages:
            lines.extend(f"- [{page['id']}] {page.get('path', '')}" for page in pages)
        else:
            lines.append("- No published project decisions were supplied for this period.")
        lines.extend(["", "## Unresolved questions", "- Which findings require a Wiki proposal, and which remain observations pending stronger evidence?"])
        return "\n".join(lines) + "\n"

    def _content_creation(self, week: str, sources: list[dict[str, Any]], source_cutoff: str) -> str:
        lines = [f"# Content Creation - {week}", "", f"Source cutoff: `{source_cutoff}`", "", "## Evidence-backed themes"]
        for source in sources:
            excerpt = " ".join(str(source["raw_content"]).splitlines()[1:]).strip()[:360]
            audience = str(source.get("metadata", {}).get("audience") or "project stakeholders")
            lines.extend([
                f"### {self._title(source)}",
                f"- Audience: {audience}",
                f"- Claim/citation pair: {excerpt or 'Read the cited source before drafting.'} [source:{source['id']}]",
                "- Suggested angle (not a verified fact): explain the project implication and label recommendations explicitly.",
                f"- Reusable excerpt: \"{excerpt[:180] or 'No reusable excerpt until the source is reviewed.'}\" [source:{source['id']}]",
            ])
        lines.extend(["", "## Research gaps", "- No uncited statement should be promoted from this file into publishable content."])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _context_pack(
        project_id: str,
        week: str,
        sources: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        rule_revision: str,
        source_cutoff: str,
        context_pack: ContextPack | None,
    ) -> str:
        lines = [f"# Context Pack - {week}", "", f"Project: {project_id}", f"Rule revision: {rule_revision}", f"Source cutoff: `{source_cutoff}`", "", "## Sources"]
        lines.extend(f"- {source['id']}: {source.get('origin', '')}" for source in sources)
        lines.extend(["", "## Wiki pages"])
        lines.extend(f"- {page['id']}: {page.get('path', '')}" for page in pages)
        if not pages:
            lines.append("- No published Wiki pages included.")
        lines.extend(["", "## Bounded context"])
        if context_pack:
            lines.extend([
                f"- Context revision: {context_pack.revision}",
                f"- Character budget: {context_pack.character_budget}",
                f"- Included sections: {', '.join(context_pack.section_refs) or 'none'}",
                f"- Omitted references: {', '.join(context_pack.omitted_refs) or 'none'}",
                "",
                context_pack.rendered,
            ])
        else:
            lines.append("- Bounded P3 context was unavailable; use only the explicit source/page references above.")
        return "\n".join(lines) + "\n"
