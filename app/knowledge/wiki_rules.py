"""Parsing and validation for a project's authoritative ``AGENTS.md`` rules."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


REQUIRED_RULE_SECTIONS = (
    "Project Scope",
    "Evidence Hierarchy",
    "Allowed Page Kinds",
    "Frontmatter Schema",
    "Citation Convention",
    "Contradiction Policy",
    "SOP Requirements",
    "Content Voice",
    "Maintenance Workflow",
)

_VALID_PAGE_KIND = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class RuleValidationError(ValueError):
    """Raised when project-authored Wiki rules cannot govern a proposal safely."""


class ProjectRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    allowed_page_kinds: tuple[str, ...] = Field(min_length=1)
    write_root: str = "wiki/"
    sections: frozenset[str]
    body: str
    revision: str

    @field_validator("allowed_page_kinds")
    @classmethod
    def validate_page_kinds(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or not all(_VALID_PAGE_KIND.fullmatch(value) for value in values):
            raise ValueError("page_kinds must be unique, lowercase page-kind identifiers")
        return values

    @field_validator("write_root")
    @classmethod
    def validate_write_root(cls, value: str) -> str:
        if value != "wiki/":
            raise ValueError("write_root must be wiki/")
        return value


def build_default_agents_rules(project_id: str) -> str:
    """Return a compact baseline; project authors can extend it without replacement."""
    if not project_id.strip():
        raise ValueError("project_id is required")
    return f"""---
project_id: {project_id}
page_kinds: [concept, decision, brief, sop, index]
write_root: wiki/
---
# Project Knowledge Rules

## Project Scope
Keep all claims, decisions, and outputs scoped to this project.

## Evidence Hierarchy
Prefer primary evidence; label assumptions and unresolved evidence.

## Allowed Page Kinds
Use only the page kinds declared in frontmatter.

## Frontmatter Schema
Every page declares title, kind, status, and citations.

## Metadata Contract
BSC-controlled identifiers, hashes, capture timestamps, and managed flags are
projection metadata. Editing an Obsidian property does not change lifecycle or
authorization state.

## Citation Convention
Every factual claim links to one or more source IDs.

## Contradiction Policy
Keep competing claims visible and request review; do not silently resolve them.

## SOP Requirements
Separate project evidence from general recommendations and name assumptions.

## Content Voice
Write concise, factual, audience-appropriate material.

## Maintenance Workflow
Produce reviewable proposals only; publication requires validation and approval.
"""


def parse_project_rules(text: str) -> ProjectRules:
    """Parse user-maintained rules without rewriting their Markdown body."""
    frontmatter, body = _split_frontmatter(text)
    try:
        metadata: dict[str, Any] = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise RuleValidationError(f"invalid AGENTS.md frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise RuleValidationError("AGENTS.md frontmatter must be a mapping")

    sections = frozenset(re.findall(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    missing = [section for section in REQUIRED_RULE_SECTIONS if section not in sections]
    if missing:
        raise RuleValidationError("missing required AGENTS.md sections: " + ", ".join(missing))
    page_kinds = metadata.get("page_kinds")
    if not isinstance(page_kinds, list):
        raise RuleValidationError("page_kinds must be a YAML list")
    revision = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        return ProjectRules(
            project_id=str(metadata.get("project_id") or "").strip(),
            allowed_page_kinds=tuple(str(item) for item in page_kinds),
            write_root=str(metadata.get("write_root") or ""),
            sections=sections,
            body=body,
            revision=revision,
        )
    except Exception as exc:
        raise RuleValidationError(str(exc)) from exc


def _split_frontmatter(text: str) -> tuple[str, str]:
    # Obsidian may preserve the Windows CRLF convention. Parse structural
    # delimiters consistently while callers retain the original text hash.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        raise RuleValidationError("AGENTS.md must start with YAML frontmatter")
    boundary = normalized.find("\n---", 4)
    if boundary < 0:
        raise RuleValidationError("AGENTS.md frontmatter is not closed")
    frontmatter = normalized[4:boundary]
    body = normalized[boundary + 4:].lstrip("\n")
    return frontmatter, body
