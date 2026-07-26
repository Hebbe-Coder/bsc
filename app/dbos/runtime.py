"""Inspectable context composition and restart-safe DBOS execution recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any

from app.artifacts import (
    ArtifactGraphStore,
    ArtifactStatus,
    DiagnosisArtifact,
    ExecutionResultArtifact,
    MissionArtifact,
    RunCheckpointArtifact,
    RuntimeContextArtifact,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _estimate_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return math.ceil(len(encoded.encode("utf-8")) / 4)


class RuntimeContextBuilder:
    """Build a redacted context manifest before a DBOS runtime step.

    The manifest records policy, artifact lineage and governed knowledge IDs,
    while raw prompts, source bodies, model output and credentials remain out
    of the runtime ledger.
    """

    REVISION = "dbos-context-v1"
    CONTEXT_WINDOW_TOKENS = 32_000
    COMPACTION_THRESHOLD = 0.75

    def build(
        self,
        *,
        mission: MissionArtifact,
        diagnosis: DiagnosisArtifact,
        selection: Any,
        knowledge_context: dict[str, Any] | None,
        purpose: str = "execution",
        audience: str = "primary",
    ) -> RuntimeContextArtifact:
        knowledge = knowledge_context if isinstance(knowledge_context, dict) else {}
        source_ids = self._ids(knowledge.get("source_ids"))
        method_ids = self._ids(knowledge.get("method_ids"))
        manifest = {
            "revision": self.REVISION,
            "purpose": purpose,
            "audience": audience,
            "mission_id": mission.artifact_id,
            "mission_revision": mission.revision,
            "diagnosis_id": diagnosis.artifact_id,
            "selection_id": str(getattr(selection, "artifact_id", "")),
            "mission_context_fields": sorted(str(key) for key in mission.context if str(key)),
            "diagnosis_fields": [
                field for field, value in {
                    "role": diagnosis.role,
                    "industry": diagnosis.industry,
                    "organization_stage": diagnosis.organization_stage,
                    "goal": diagnosis.goal,
                    "time_horizon": diagnosis.time_horizon,
                    "constraints": diagnosis.constraints,
                    "stakeholders": diagnosis.stakeholders,
                    "decision_rights": diagnosis.decision_rights,
                }.items() if value
            ],
            "knowledge": {
                "availability": str(knowledge.get("availability") or "unavailable"),
                "source_ids": source_ids,
                "method_ids": method_ids,
                "page_ids": self._ids(knowledge.get("page_ids")),
                "output_ids": self._ids(knowledge.get("output_ids")),
            },
        }
        estimated_tokens = _estimate_tokens(manifest)
        snapshot = RuntimeContextArtifact(
            project_id=mission.project_id,
            label=f"Runtime context: {mission.title}"[:140],
            mission_id=mission.artifact_id,
            audience=audience,
            purpose=purpose,
            context_revision=self.REVISION,
            referenced_artifact_ids=[mission.artifact_id, diagnosis.artifact_id, str(getattr(selection, "artifact_id", ""))],
            source_ids=source_ids,
            method_ids=method_ids,
            context_fields=manifest["mission_context_fields"] + manifest["diagnosis_fields"],
            prompt_fingerprint=_fingerprint({
                "revision": self.REVISION,
                "purpose": purpose,
                "audience": audience,
                "data_policy": "redacted_artifact_manifest_only",
            }),
            input_fingerprint=_fingerprint(manifest),
            estimated_tokens=estimated_tokens,
            context_window_tokens=self.CONTEXT_WINDOW_TOKENS,
            compaction_threshold=self.COMPACTION_THRESHOLD,
            compaction_required=estimated_tokens >= int(self.CONTEXT_WINDOW_TOKENS * self.COMPACTION_THRESHOLD),
            parent_ids=[mission.artifact_id, diagnosis.artifact_id, str(getattr(selection, "artifact_id", ""))],
            source_agent="dbos_runtime_context",
            tags=["dbos", "runtime_context", "redacted"],
        )
        snapshot.snapshot_id = snapshot.artifact_id
        return snapshot

    @staticmethod
    def _ids(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item) for item in value if str(item)))[:100]


def record_run_checkpoint(
    store: ArtifactGraphStore,
    execution: ExecutionResultArtifact,
    *,
    checkpoint_status: str,
    reason: str = "",
    resumed_from_execution_id: str = "",
) -> RunCheckpointArtifact:
    """Append a runtime checkpoint without overwriting prior lifecycle facts."""
    checkpoint = RunCheckpointArtifact(
        project_id=execution.project_id,
        label=f"{checkpoint_status}: {execution.capability_name}"[:140],
        mission_id=execution.mission_id,
        execution_id=execution.artifact_id,
        capability_name=execution.capability_name,
        idempotency_key=execution.idempotency_key,
        attempt=execution.attempt,
        checkpoint_status=checkpoint_status,
        context_snapshot_id=execution.context_snapshot_id,
        reason=reason[:500],
        resumed_from_execution_id=resumed_from_execution_id,
        checkpointed_at=_timestamp(),
        parent_ids=[execution.artifact_id, *([execution.context_snapshot_id] if execution.context_snapshot_id else [])],
        source_agent="dbos_runtime_ledger",
        tags=["dbos", "run_checkpoint", checkpoint_status],
    )
    checkpoint.checkpoint_id = checkpoint.artifact_id
    store.add(checkpoint)
    return checkpoint


def recover_interrupted_runs(store: ArtifactGraphStore) -> list[ExecutionResultArtifact]:
    """Mark in-flight work as interrupted after a restart without replaying it."""
    interrupted = [
        item for item in store.get_by_project(store._project_id)
        if isinstance(item, ExecutionResultArtifact) and item.execution_status == "executing"
    ]
    recovered: list[ExecutionResultArtifact] = []
    mission_ids: set[str] = set()
    for execution in interrupted:
        recovered_execution = execution.model_copy(update={
            "execution_status": "interrupted",
            "status": ArtifactStatus.FAILED,
            "error": "runtime restarted before a terminal execution result was recorded",
            "stop_reason": "process_restart_manual_retry_required",
            "completed_at": _timestamp(),
        })
        store.update(recovered_execution)
        record_run_checkpoint(
            store,
            recovered_execution,
            checkpoint_status="interrupted",
            reason="process restart; automatic replay is prohibited",
        )
        recovered.append(recovered_execution)
        mission_ids.add(recovered_execution.mission_id)

    for mission_id in mission_ids:
        mission = store.get(mission_id)
        if not isinstance(mission, MissionArtifact) or mission.mission_status != "executing":
            continue
        store.update(mission.model_copy(update={
            "mission_status": "confirmed",
            "status": ArtifactStatus.CONFIRMED,
            "authorization": {
                **mission.authorization,
                "last_runtime_recovery": {
                    "at": _timestamp(),
                    "policy": "manual_retry_required",
                },
            },
        }))
    return recovered


__all__ = ["RuntimeContextBuilder", "record_run_checkpoint", "recover_interrupted_runs"]
