"""Shared visibility rules for active knowledge-evidence projections."""

from __future__ import annotations

from typing import Any, Mapping


SCOPE_EXCLUSION_REASON = "outside_mapped_project_root"


def is_scope_excluded_source(source: Mapping[str, Any]) -> bool:
    """Return whether a retained audit source must stay out of active views."""
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    exclusion = metadata.get("scope_exclusion") if isinstance(metadata.get("scope_exclusion"), dict) else {}
    return exclusion.get("reason") == SCOPE_EXCLUSION_REASON


def is_active_evidence_source(source: Mapping[str, Any]) -> bool:
    """Keep audit-retained, out-of-boundary sources out of operating views."""
    return not is_scope_excluded_source(source)
