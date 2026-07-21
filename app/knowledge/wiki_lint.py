"""Deterministic validation for reviewable Wiki proposals."""

from __future__ import annotations

import re
from typing import Iterable

import yaml
from pydantic import BaseModel, ConfigDict

from app.knowledge.wiki_contracts import WikiOperationType, WikiProposal
from app.knowledge.wiki_rules import ProjectRules

_SOURCE_REF = re.compile(r"\[source:([^\]\s]+)\]")
_WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")


class WikiLintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: str
    code: str
    path: str
    artifact_ref: str = ""
    message: str


class WikiLintReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[WikiLintFinding, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.findings


class WikiLint:
    """Parse Markdown as data and report all deterministic proposal findings."""

    def lint_proposal(
        self,
        proposal: WikiProposal,
        *,
        rules: ProjectRules,
        source_ids: set[str],
        existing_paths: Iterable[str] = (),
    ) -> WikiLintReport:
        findings: list[WikiLintFinding] = []
        operations = proposal.operations
        proposal_paths = {operation.path for operation in operations}
        existing_paths = set(existing_paths)
        known_paths = existing_paths | proposal_paths
        substantive = [operation for operation in operations if operation.path not in {"wiki/index.md", "wiki/log.md"}]
        if substantive and "wiki/index.md" not in proposal_paths:
            findings.append(self._finding("missing_index_update", "wiki/index.md", "Substantive changes require a Wiki index update."))
        if substantive and "wiki/log.md" not in proposal_paths:
            findings.append(self._finding("missing_log_update", "wiki/log.md", "Substantive changes require an append-only ledger entry."))
        for operation in operations:
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
            for source_id in _SOURCE_REF.findall(operation.content):
                if source_id not in source_ids:
                    findings.append(self._finding("unknown_source", operation.path, f"Citation references unknown source: {source_id}", source_id))
            for target in _WIKI_LINK.findall(operation.content):
                normalized = target if target.endswith(".md") else f"{target}.md"
                if normalized not in known_paths:
                    findings.append(self._finding("dangling_page_link", operation.path, f"Link target does not exist: {normalized}", normalized))
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
        return WikiLintFinding(severity="error", code=code, path=path, artifact_ref=artifact_ref, message=message)
