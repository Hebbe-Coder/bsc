"""Deterministic validation for reviewable Wiki proposals."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

import yaml
from pydantic import BaseModel, ConfigDict

from app.knowledge.wiki_contracts import WikiOperationType, WikiProposal
from app.knowledge.wiki_rules import ProjectRules, RuleValidationError, parse_project_rules

_SOURCE_REF = re.compile(r"\[source:([^\]\s]+)\]")
_WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")


class WikiLintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: str
    code: str
    path: str
    artifact_ref: str = ""
    message: str
    remediation: str


class WikiLintReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[WikiLintFinding, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


class WikiLint:
    """Parse Markdown as data and report all deterministic proposal findings."""

    def lint_proposal(
        self,
        proposal: WikiProposal,
        *,
        rules: ProjectRules,
        source_ids: set[str],
        existing_paths: Iterable[str] = (),
        existing_contents: dict[str, str] | None = None,
    ) -> WikiLintReport:
        findings: list[WikiLintFinding] = []
        operations = proposal.operations
        proposal_paths = {operation.path for operation in operations}
        existing_paths = set(existing_paths)
        known_paths = existing_paths | proposal_paths
        substantive = [
            operation for operation in operations
            if operation.path not in {"AGENTS.md", "wiki/index.md", "wiki/log.md", "wiki/overview.md"}
        ]
        archive_only_repair = bool(substantive) and all(
            operation.operation is WikiOperationType.ARCHIVE for operation in substantive
        )
        if substantive and "wiki/index.md" not in proposal_paths:
            findings.append(self._finding("missing_index_update", "wiki/index.md", "Substantive changes require a Wiki index update."))
        if substantive and "wiki/log.md" not in proposal_paths:
            findings.append(self._finding("missing_log_update", "wiki/log.md", "Substantive changes require an append-only ledger entry."))
        if (
            substantive
            and "wiki/overview.md" not in proposal_paths
            and not self._existing_overview_covers_replacements(substantive, existing_contents or {})
        ):
            findings.append(self._finding("missing_overview_update", "wiki/overview.md", "Substantive changes require a project overview update."))
        for operation in operations:
            if operation.path == "AGENTS.md":
                if operation.operation is not WikiOperationType.REPLACE:
                    findings.append(self._finding("agents_not_replace", operation.path, "AGENTS.md must be replaced as one reviewable rules document."))
                if not operation.expected_content_hash:
                    findings.append(self._finding("agents_missing_revision", operation.path, "AGENTS.md updates require the current content hash."))
                try:
                    parse_project_rules(operation.content)
                except RuleValidationError:
                    findings.append(self._finding("invalid_agents_rules", operation.path, "AGENTS.md must remain a valid project rules document."))
                continue
            if not operation.path.startswith(rules.write_root):
                findings.append(self._finding("forbidden_path", operation.path, "Operation is outside the configured Wiki root."))
                continue
            if operation.path == "wiki/log.md":
                if operation.operation is not WikiOperationType.APPEND:
                    findings.append(self._finding("log_not_append", operation.path, "wiki/log.md may only be appended."))
                continue
            if operation.operation not in {WikiOperationType.CREATE, WikiOperationType.REPLACE, WikiOperationType.APPEND}:
                continue
            frontmatter = self._frontmatter(operation.content)
            requires_frontmatter = operation.operation in {WikiOperationType.CREATE, WikiOperationType.REPLACE} or operation.path not in existing_paths
            if operation.path != "wiki/index.md" and requires_frontmatter:
                if frontmatter is None:
                    findings.append(self._finding("missing_frontmatter", operation.path, "Wiki pages require YAML frontmatter."))
                elif frontmatter.get("kind") not in rules.allowed_page_kinds:
                    findings.append(self._finding("invalid_page_kind", operation.path, "Frontmatter kind is not allowed by AGENTS.md."))
            citations = _SOURCE_REF.findall(operation.content)
            if (
                operation.path not in {"wiki/index.md", "wiki/log.md"}
                and not citations
                and not (
                    archive_only_repair
                    and operation.path == "wiki/overview.md"
                    and operation.operation is WikiOperationType.APPEND
                )
            ):
                findings.append(self._finding("missing_source_citation", operation.path, "Substantive Wiki updates require an immutable source citation."))
            for source_id in citations:
                if source_id not in source_ids:
                    findings.append(self._finding("unknown_source", operation.path, f"Citation references unknown source: {source_id}", source_id))
            for target in _WIKI_LINK.findall(operation.content):
                normalized = target if target.endswith(".md") else f"{target}.md"
                if normalized not in known_paths:
                    findings.append(self._finding("dangling_page_link", operation.path, f"Link target does not exist: {normalized}", normalized))
        return WikiLintReport(findings=tuple(findings))

    @staticmethod
    def _existing_overview_covers_replacements(
        substantive: list,
        existing_contents: dict[str, str],
    ) -> bool:
        """Avoid duplicate navigation entries when a linked page is only revised."""
        overview = existing_contents.get("wiki/overview.md", "")
        return bool(overview) and bool(substantive) and all(
            operation.operation is WikiOperationType.REPLACE
            and f"[[{operation.path}]]" in overview
            for operation in substantive
        )

    def lint_project(
        self,
        *,
        project_id: str,
        rules: ProjectRules,
        pages: Iterable[dict],
        sources: Iterable[dict],
        now: datetime | None = None,
        stale_after_days: int = 90,
    ) -> WikiLintReport:
        """Validate one published project snapshot without executing Markdown content."""
        pages = list(pages)
        sources = list(sources)
        if any(page.get("project_id") != project_id for page in pages):
            raise ValueError("pages must be project scoped")
        if any(source.get("project_id") != project_id for source in sources):
            raise ValueError("sources must be project scoped")
        current = now or datetime.now(timezone.utc)
        source_ids = {str(source["id"]) for source in sources}
        paths = {str(page["path"]): page for page in pages}
        incoming: set[str] = set()
        findings: list[WikiLintFinding] = []
        for page in pages:
            path = str(page["path"])
            content = str(page.get("content") or "")
            if path not in {"AGENTS.md", "wiki/index.md", "wiki/log.md"}:
                metadata = self._frontmatter(content)
                if metadata is None:
                    findings.append(self._finding("missing_frontmatter", path, "Published Wiki pages require YAML frontmatter."))
                elif metadata.get("kind") not in rules.allowed_page_kinds:
                    findings.append(self._finding("invalid_page_kind", path, "Published page kind is not allowed by AGENTS.md."))
                citations = _SOURCE_REF.findall(content)
                if not citations:
                    findings.append(self._finding("missing_source_citation", path, "Substantive Wiki pages require at least one immutable source citation."))
                for source_id in citations:
                    if source_id not in source_ids:
                        findings.append(self._finding("unknown_source", path, f"Citation references unknown source: {source_id}", source_id))
            for target in _WIKI_LINK.findall(content):
                normalized = target if target.endswith(".md") else f"{target}.md"
                if normalized not in paths:
                    findings.append(self._finding("dangling_page_link", path, f"Link target does not exist: {normalized}", normalized))
                else:
                    incoming.add(normalized)
            updated_at = str(page.get("updated_at") or "")
            if updated_at:
                try:
                    parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed < current - timedelta(days=stale_after_days):
                        findings.append(self._finding("stale_page", path, f"Page has not changed for more than {stale_after_days} days."))
                except ValueError:
                    findings.append(self._finding("invalid_timestamp", path, "Page update timestamp is not ISO-8601."))
        roots = {"AGENTS.md", "wiki/index.md", "wiki/overview.md", "wiki/log.md"}
        for path in sorted(set(paths) - incoming - roots):
            findings.append(self._finding("orphan_page", path, "No published Wiki page links to this page."))
        return WikiLintReport(findings=tuple(findings))

    @staticmethod
    def _frontmatter(content: str) -> dict | None:
        if not content.startswith("---\n"):
            return None
        end = content.find("\n---", 4)
        if end < 0:
            return None
        try:
            parsed = yaml.safe_load(content[4:end])
        except yaml.YAMLError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _finding(code: str, path: str, message: str, artifact_ref: str = "") -> WikiLintFinding:
        remediation = {
            "missing_frontmatter": "Add valid YAML frontmatter with an allowed page kind.",
            "invalid_page_kind": "Use a page kind allowed by AGENTS.md.",
            "missing_source_citation": "Attach at least one resolvable [source:<id>] citation.",
            "unknown_source": "Replace the reference with an immutable source from this project.",
            "dangling_page_link": "Create the target through a governed proposal or remove the link.",
            "missing_index_update": "Update wiki/index.md in the same proposal.",
            "missing_overview_update": "Update wiki/overview.md in the same proposal.",
            "missing_log_update": "Append an audit entry to wiki/log.md in the same proposal.",
            "agents_not_replace": "Replace AGENTS.md as one complete, reviewable rules document.",
            "agents_missing_revision": "Attach the current AGENTS.md SHA-256 as expected_content_hash.",
            "invalid_agents_rules": "Keep required rule sections and valid YAML frontmatter in AGENTS.md.",
            "log_not_append": "Use an append operation for wiki/log.md.",
            "forbidden_path": "Move the operation under the configured wiki/ write root.",
            "orphan_page": "Link the page from a relevant index, overview, or concept page.",
            "stale_page": "Review the page against current evidence and publish a governed update if needed.",
            "invalid_timestamp": "Store an ISO-8601 update timestamp.",
        }.get(code, "Resolve the finding before publication.")
        return WikiLintFinding(
            severity="error",
            code=code,
            path=path,
            artifact_ref=artifact_ref,
            message=message,
            remediation=remediation,
        )
