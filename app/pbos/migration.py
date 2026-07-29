"""Audited, idempotent migration for PBOS Artifact Graph assets."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from app.artifacts import ArtifactGraphStore, ArtifactType, BaseArtifact
from app.artifacts.types import ARTIFACT_CLASS_MAP


BUNDLE_VERSION = "pbos-artifact-bundle/v1"
PBOS_TYPES = frozenset({
    ArtifactType.PERSONAL_PROFILE,
    ArtifactType.CAPABILITY,
    ArtifactType.PERSONAL_EXECUTION_PLAN,
    ArtifactType.WORK_EXECUTION_RECORD,
    ArtifactType.WORK_OUTCOME,
    ArtifactType.WORK_FEEDBACK,
    ArtifactType.EXPERIENCE,
    ArtifactType.SOP_VERSION,
    ArtifactType.SOP_PROMOTION,
})

_ROOT_ORDER = {
    ArtifactType.MISSION: 0,
    ArtifactType.DIAGNOSIS: 1,
    ArtifactType.PERSONAL_PROFILE: 2,
    ArtifactType.CAPABILITY: 3,
    ArtifactType.EXPERIENCE: 4,
    ArtifactType.PERSONAL_EXECUTION_PLAN: 5,
    ArtifactType.WORK_EXECUTION_RECORD: 6,
    ArtifactType.WORK_OUTCOME: 7,
    ArtifactType.WORK_FEEDBACK: 8,
    ArtifactType.SOP_VERSION: 9,
    ArtifactType.SOP_PROMOTION: 10,
}


class PBOSMigrationError(ValueError):
    """Raised before a migration can change the destination graph."""


def export_bundle(source: ArtifactGraphStore) -> dict[str, Any]:
    """Export PBOS assets and their complete parent closure in parent-first order."""
    roots = [
        artifact.artifact_id
        for artifact_id in source.list_all()
        for artifact in [source.get(artifact_id)]
        if artifact is not None and artifact.artifact_type in PBOS_TYPES
    ]
    included: set[str] = set()
    collecting: set[str] = set()

    def collect(artifact_id: str) -> None:
        if artifact_id in included:
            return
        if artifact_id in collecting:
            raise PBOSMigrationError(f"cyclic parent edge at {artifact_id}")
        artifact = source.get(artifact_id)
        if artifact is None:
            raise PBOSMigrationError(f"missing required parent artifact {artifact_id}")
        collecting.add(artifact_id)
        for parent_id in artifact.parent_ids:
            collect(parent_id)
        collecting.remove(artifact_id)
        included.add(artifact_id)

    for root in roots:
        collect(root)

    ordered: list[BaseArtifact] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        if artifact_id in visiting:
            raise PBOSMigrationError(f"cyclic parent edge at {artifact_id}")
        artifact = source.get(artifact_id)
        if artifact is None:
            raise PBOSMigrationError(f"missing required parent artifact {artifact_id}")
        visiting.add(artifact_id)
        for parent_id in artifact.parent_ids:
            visit(parent_id)
        visiting.remove(artifact_id)
        visited.add(artifact_id)
        ordered.append(artifact)

    ordered_ids = sorted(included, key=lambda artifact_id: (
        _ROOT_ORDER.get(getattr(source.get(artifact_id), "artifact_type", None), 99),
        artifact_id,
    ))
    for artifact_id in ordered_ids:
        visit(artifact_id)

    scope = {
        "tenant_id": source._tenant_id,
        "project_id": source._project_id,
        "session_id": source._session_id,
    }
    payload: dict[str, Any] = {
        "version": BUNDLE_VERSION,
        "scope": scope,
        "artifacts": [artifact.model_dump(mode="json") for artifact in ordered],
    }
    payload["integrity_sha256"] = _bundle_digest(payload)
    return payload


def import_bundle(destination: ArtifactGraphStore, bundle: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Validate a bundle completely, then add only non-conflicting assets."""
    _validate_bundle(destination, bundle)
    artifacts = [_deserialize(raw) for raw in bundle["artifacts"]]
    bundle_ids = {artifact.artifact_id for artifact in artifacts}
    additions: list[BaseArtifact] = []
    skipped: list[str] = []

    for artifact in artifacts:
        for parent_id in artifact.parent_ids:
            if parent_id not in bundle_ids and destination.get(parent_id) is None:
                raise PBOSMigrationError(f"destination is missing parent artifact {parent_id}")
        existing = destination.get(artifact.artifact_id)
        if existing is None:
            additions.append(artifact)
        elif _semantically_equal(existing, artifact):
            skipped.append(artifact.artifact_id)
        else:
            raise PBOSMigrationError(f"destination conflict for artifact {artifact.artifact_id}")

    if not dry_run:
        for artifact in additions:
            destination.add(deepcopy(artifact))

    return {
        "state": "dry_run" if dry_run else "imported",
        "added_ids": [artifact.artifact_id for artifact in additions],
        "skipped_ids": skipped,
        "artifact_count": len(artifacts),
    }


def _validate_bundle(destination: ArtifactGraphStore, bundle: dict[str, Any]) -> None:
    if bundle.get("version") != BUNDLE_VERSION:
        raise PBOSMigrationError("unsupported PBOS bundle version")
    if not isinstance(bundle.get("artifacts"), list):
        raise PBOSMigrationError("PBOS bundle artifacts must be a list")
    if bundle.get("integrity_sha256") != _bundle_digest(bundle):
        raise PBOSMigrationError("PBOS bundle integrity check failed")
    expected_scope = {
        "tenant_id": destination._tenant_id,
        "project_id": destination._project_id,
        "session_id": destination._session_id,
    }
    if bundle.get("scope") != expected_scope:
        raise PBOSMigrationError("PBOS bundle scope does not match destination")
    seen: set[str] = set()
    for raw in bundle["artifacts"]:
        artifact = _deserialize(raw)
        if artifact.artifact_id in seen:
            raise PBOSMigrationError(f"duplicate bundle artifact {artifact.artifact_id}")
        if artifact.project_id != destination._project_id:
            raise PBOSMigrationError(f"artifact {artifact.artifact_id} is outside destination project")
        missing_parents = [parent_id for parent_id in artifact.parent_ids if parent_id not in seen and destination.get(parent_id) is None]
        if missing_parents:
            raise PBOSMigrationError(f"bundle is not parent-first for {artifact.artifact_id}")
        seen.add(artifact.artifact_id)


def _deserialize(raw: Any) -> BaseArtifact:
    if not isinstance(raw, dict):
        raise PBOSMigrationError("PBOS bundle artifact must be an object")
    try:
        artifact_type = ArtifactType(str(raw.get("artifact_type") or ""))
        model = ARTIFACT_CLASS_MAP[artifact_type]
    except (KeyError, ValueError) as exc:
        raise PBOSMigrationError("PBOS bundle contains an unknown artifact type") from exc
    return model.model_validate(raw)


def _bundle_digest(bundle: dict[str, Any]) -> str:
    signed = {key: value for key, value in bundle.items() if key != "integrity_sha256"}
    return sha256(json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _semantically_equal(left: BaseArtifact, right: BaseArtifact) -> bool:
    left_data = left.model_dump(mode="json")
    right_data = right.model_dump(mode="json")
    left_data.pop("updated_at", None)
    right_data.pop("updated_at", None)
    return left_data == right_data
