"""Current source-admission checks for reusable output lifecycle actions."""

from __future__ import annotations

from typing import Any

from app.knowledge.source_triage import source_admission_reason


ADMITTED_SOURCE_STATUSES = frozenset({"eligible", "processed"})
_GENERATED_SOURCE_TYPES = frozenset({"generated_output", "output", "synthetic"})


class OutputSourceAdmissionError(ValueError):
    """Raised when a reusable output references evidence that is no longer admitted."""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        self.issues = issues
        source_ids = ", ".join(item["source_id"] for item in issues)
        super().__init__(
            "output source admission changed for "
            f"{source_ids}; regenerate the output or remove the invalid source reference before evaluation, "
            "acceptance, filing, or reuse"
        )


def output_source_admission_issues(repository: Any, output: dict[str, Any]) -> list[dict[str, str]]:
    """Return bounded, metadata-only issues for every current output source ref.

    ``source_refs`` are immutable generation lineage and attached evidence refs
    are mutable review lineage. Both must be checked because either can drift
    after an output was registered. Generated internal sources are lineage
    records, not external evidence, so they do not require A-layer admission.
    """
    source_ids: list[str] = []
    for value in output.get("source_refs") or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in source_ids:
            source_ids.append(normalized)
    evidence = repository.list_output_evidence_references(
        str(output.get("project_id") or ""), str(output.get("id") or "")
    )
    for value in evidence.get("source_ids") or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in source_ids:
            source_ids.append(normalized)

    issues: list[dict[str, str]] = []
    project_id = str(output.get("project_id") or "")
    for source_id in source_ids:
        source = repository.get_source(project_id, source_id)
        if not source:
            issues.append({"source_id": source_id, "code": "missing_source_reference", "status": "missing"})
            continue
        if str(source.get("source_type") or "") in _GENERATED_SOURCE_TYPES:
            continue
        status = str(source.get("status") or "")
        if status not in ADMITTED_SOURCE_STATUSES:
            issues.append({"source_id": source_id, "code": "source_status_not_admitted", "status": status or "unknown"})
            continue
        reason = source_admission_reason(repository, project_id, source)
        if reason:
            issues.append({"source_id": source_id, "code": reason, "status": status})
    return issues


def assert_output_sources_admitted(repository: Any, output: dict[str, Any]) -> None:
    """Enforce current admission without mutating the output or its sources."""
    issues = output_source_admission_issues(repository, output)
    if issues:
        raise OutputSourceAdmissionError(issues)
