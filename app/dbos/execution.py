"""Mission confirmation and fail-closed internal capability execution."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.artifacts import (
    ArtifactGraphStore,
    ArtifactStatus,
    ArtifactType,
    ExecutionResultArtifact,
    MissionArtifact,
    TaskVerificationArtifact,
)
from app.capabilities import CapabilityExecutor, CapabilityRegistry

from .runtime import record_run_checkpoint


class DBOSExecutionError(RuntimeError):
    """Base class for persisted DBOS execution policy failures."""


class MissionNotFoundError(DBOSExecutionError):
    pass


class MissionStateError(DBOSExecutionError):
    pass


class MissionNotConfirmedError(DBOSExecutionError):
    pass


class UnauthorizedCapabilityError(DBOSExecutionError):
    pass


class ManualRetryRequiredError(DBOSExecutionError):
    pass


class MissionExecutionService:
    """Applies mission grants before any registered executor can run."""

    def __init__(self, store: ArtifactGraphStore, registry: CapabilityRegistry, executor: Any | None = None) -> None:
        self.store = store
        self.registry = registry
        self.executor = executor

    def confirm(self, mission: MissionArtifact, *, actor_id: str, authorized_capabilities: list[str]) -> MissionArtifact:
        granted = sorted({str(item).strip() for item in authorized_capabilities if str(item).strip()})
        if mission.mission_status == "confirmed":
            prior = sorted(mission.authorization.get("authorized_capabilities", []))
            if prior == granted:
                return mission
            raise MissionStateError("confirmed mission authorization is immutable")
        if mission.mission_status != "ready_for_confirmation":
            raise MissionStateError("mission is not ready for confirmation")
        if not granted:
            raise UnauthorizedCapabilityError("mission confirmation requires at least one capability grant")
        selection = mission.authorization.get("selection")
        selected = set(selection.get("selected_capabilities", [])) if isinstance(selection, dict) else set()
        invalid = [name for name in granted if name not in selected or not self.registry.get(name)]
        if invalid:
            raise UnauthorizedCapabilityError("mission grants must be selected registered capabilities")
        confirmed = mission.model_copy(
            update={
                "mission_status": "confirmed",
                "status": ArtifactStatus.CONFIRMED,
                "confirmed_by": actor_id,
                "confirmed_at": _timestamp(),
                "authorization": {
                    **mission.authorization,
                    "authorized_capabilities": granted,
                    "confirmed_by": actor_id,
                },
            }
        )
        self.store.update(confirmed)
        return confirmed

    async def execute(
        self,
        mission: MissionArtifact,
        *,
        capability_name: str,
        dynamic_sop_id: str,
        idempotency_key: str,
        context_snapshot_id: str = "",
        context: dict[str, Any],
        callback: Callable[[str, dict[str, Any]], Awaitable[Any] | Any] | None = None,
    ) -> ExecutionResultArtifact:
        # A terminal mission may still receive the original idempotency retry.
        # Return the audited result before evaluating the live transition gate;
        # this cannot invoke an executor or create another attempt.
        existing = self._existing_result(mission.artifact_id, capability_name, idempotency_key)
        if existing is not None:
            if existing.execution_status == "interrupted":
                raise ManualRetryRequiredError(
                    "interrupted execution requires an explicit new idempotency key for a manual retry"
                )
            return existing
        if mission.mission_status != "confirmed":
            raise MissionNotConfirmedError("mission must be confirmed before execution")
        capability = self.registry.get(capability_name)
        granted = set(mission.authorization.get("authorized_capabilities", []))
        if capability is None or capability_name not in granted:
            self._record_denied_attempt(mission, capability_name, dynamic_sop_id, idempotency_key, "capability is not registered or granted")
            raise UnauthorizedCapabilityError("capability is not registered or granted for this mission")

        started = _timestamp()
        result = ExecutionResultArtifact(
            project_id=mission.project_id,
            label=f"Execution: {capability_name}"[:140],
            mission_id=mission.artifact_id,
            dynamic_sop_id=dynamic_sop_id,
            capability_name=capability_name,
            execution_id=f"exec_{uuid4().hex[:16]}",
            execution_status="executing",
            attempt=self._next_attempt(mission.artifact_id, capability_name),
            idempotency_key=idempotency_key,
            context_snapshot_id=context_snapshot_id,
            parent_ids=[mission.artifact_id, dynamic_sop_id, *([context_snapshot_id] if context_snapshot_id else [])],
            status=ArtifactStatus.EXECUTING,
            started_at=started,
            source_agent="dbos_execution",
        )
        self.store.add(result)
        record_run_checkpoint(self.store, result, checkpoint_status="dispatch_started")
        self._set_mission_status(mission, "executing", ArtifactStatus.EXECUTING)
        try:
            outcome = await self._dispatch(capability, capability_name, context, callback)
        except Exception as exc:
            failed = result.model_copy(
                update={
                    "execution_status": "failed",
                    "status": ArtifactStatus.FAILED,
                    "error": _safe_error(exc),
                    "completed_at": _timestamp(),
                }
            )
            self.store.update(failed)
            record_run_checkpoint(self.store, failed, checkpoint_status="failed", reason=failed.error)
            self._set_mission_status(mission, "failed", ArtifactStatus.FAILED)
            return failed
        verification = self._verify_real_output_contract(capability, result, outcome)
        if verification is not None and verification.verification_status != "passed":
            failed = result.model_copy(
                update={
                    "execution_status": "failed",
                    "status": ArtifactStatus.FAILED,
                    "error": "; ".join(verification.findings)[:400],
                    "stop_reason": "task_verification_failed",
                    "effects": [_effect_summary(capability_name, outcome)],
                    "completed_at": _timestamp(),
                }
            )
            self.store.update(failed)
            record_run_checkpoint(self.store, failed, checkpoint_status="failed", reason=failed.error)
            self._set_mission_status(mission, "failed", ArtifactStatus.FAILED)
            return failed
        effects = [_effect_summary(capability_name, outcome)]
        if verification is not None:
            effects.append({
                "kind": "task_verification",
                "verification_id": verification.artifact_id,
                "status": verification.verification_status,
            })
        completed = result.model_copy(
            update={
                "execution_status": "completed",
                "status": ArtifactStatus.COMPLETED,
                "effects": effects,
                "completed_at": _timestamp(),
            }
        )
        self.store.update(completed)
        record_run_checkpoint(self.store, completed, checkpoint_status="completed")
        self._set_completion_state(mission)
        return completed

    def _verify_real_output_contract(
        self,
        capability: Any,
        execution: ExecutionResultArtifact,
        outcome: Any,
    ) -> TaskVerificationArtifact | None:
        """Verify only a provider-reported real result, never synthetic callbacks.

        Internal planning callbacks are useful for deterministic tests and do not
        claim a deliverable was produced. A real capability result must prove
        that every declared output artifact type is present in this project.
        """
        # Nanobot reports provider-backed executions as ``api`` while direct
        # adapter runs use ``real``. Both can claim persisted outputs and must
        # satisfy the same Artifact Graph contract. Mock/fallback/callback
        # results intentionally remain unverified rather than being promoted.
        if str(getattr(outcome, "mode", "")).lower() not in {"real", "api"}:
            return None
        produced_ids = [str(value) for value in getattr(outcome, "artifacts_produced", []) or [] if str(value)]
        return self._verify_declared_outputs(capability, execution, produced_ids)

    def reconcile_completed_verifications(
        self,
        *,
        mission_id: str = "",
    ) -> list[TaskVerificationArtifact]:
        """Backfill missing proof for historic provider-backed executions.

        Older ledgers can contain a completed ``api`` or ``real`` execution
        from before task-verification artifacts were persisted. Reconciliation
        reads only the already-recorded effect IDs and declared capability
        contract. It never invokes a provider, repeats a capability, or marks
        callbacks/fallbacks as verified.
        """
        existing_execution_ids = {
            item.execution_id
            for item in self.store.get_by_type(ArtifactType.TASK_VERIFICATION)
            if isinstance(item, TaskVerificationArtifact)
        }
        reconciled: list[TaskVerificationArtifact] = []
        affected_missions: set[str] = set()
        for execution in self.store.get_by_type(ArtifactType.EXECUTION_RESULT):
            if not isinstance(execution, ExecutionResultArtifact):
                continue
            if execution.execution_status != "completed":
                continue
            if mission_id and execution.mission_id != mission_id:
                continue
            if execution.execution_id in existing_execution_ids:
                continue
            effect = self._provider_effect(execution)
            if effect is None:
                continue
            capability = self.registry.get(execution.capability_name)
            if capability is None:
                verification = self._record_unresolvable_verification(
                    execution,
                    "The historical capability is no longer registered; its declared output contract cannot be reconciled.",
                )
            else:
                verification = self._verify_declared_outputs(
                    capability,
                    execution,
                    [str(value) for value in effect.get("artifact_ids", []) if str(value)],
                )
            reconciled.append(verification)
            affected_missions.add(execution.mission_id)
            if verification.verification_status == "passed":
                record_run_checkpoint(
                    self.store,
                    execution,
                    checkpoint_status="verification_reconciled_passed",
                    reason="Historical provider-backed output contract reconciled from persisted artifact IDs.",
                )
                continue
            corrected = execution.model_copy(
                update={
                    "execution_status": "failed",
                    "status": ArtifactStatus.FAILED,
                    "error": "; ".join(verification.findings)[:400],
                    "stop_reason": "task_verification_failed",
                }
            )
            self.store.update(corrected)
            record_run_checkpoint(
                self.store,
                corrected,
                checkpoint_status="verification_reconciled_failed",
                reason=corrected.error,
            )
            mission = self.store.get(execution.mission_id)
            if isinstance(mission, MissionArtifact):
                self._set_mission_status(mission, "failed", ArtifactStatus.FAILED)

        for affected_mission_id in affected_missions:
            mission = self.store.get(affected_mission_id)
            if isinstance(mission, MissionArtifact) and mission.mission_status != "failed":
                self._set_completion_state(mission)
        return reconciled

    def _verify_declared_outputs(
        self,
        capability: Any,
        execution: ExecutionResultArtifact,
        produced_ids: list[str],
    ) -> TaskVerificationArtifact:
        expected = {item.value for item in getattr(capability, "output_artifact_types", [])}
        produced_types: set[str] = set()
        missing_ids: list[str] = []
        for artifact_id in produced_ids:
            artifact = self.store.get(artifact_id)
            if artifact is None:
                missing_ids.append(artifact_id)
                continue
            produced_types.add(artifact.artifact_type.value)
        missing_types = sorted(expected - produced_types)
        findings: list[str] = []
        if missing_ids:
            findings.append("Reported output artifact ids were not found in the mission project: " + ", ".join(missing_ids))
        if missing_types:
            findings.append("Declared output types were not produced: " + ", ".join(missing_types))
        verification = TaskVerificationArtifact(
            project_id=execution.project_id,
            label=f"Verify execution: {execution.capability_name}"[:140],
            mission_id=execution.mission_id,
            execution_id=execution.execution_id,
            dynamic_sop_id=execution.dynamic_sop_id,
            capability_name=execution.capability_name,
            verification_status="passed" if not findings else "failed",
            declared_output_types=sorted(expected),
            produced_artifact_ids=produced_ids,
            findings=findings or ["All declared output artifact types are present in the mission project."],
            verified_at=_timestamp(),
            parent_ids=[execution.artifact_id, execution.dynamic_sop_id],
            source_agent="dbos_task_verifier",
            tags=["dbos", "task_verification"],
        )
        self.store.add(verification)
        return verification

    def _record_unresolvable_verification(
        self,
        execution: ExecutionResultArtifact,
        finding: str,
    ) -> TaskVerificationArtifact:
        verification = TaskVerificationArtifact(
            project_id=execution.project_id,
            label=f"Verify execution: {execution.capability_name}"[:140],
            mission_id=execution.mission_id,
            execution_id=execution.execution_id,
            dynamic_sop_id=execution.dynamic_sop_id,
            capability_name=execution.capability_name,
            verification_status="failed",
            findings=[finding],
            verified_at=_timestamp(),
            parent_ids=[execution.artifact_id, execution.dynamic_sop_id],
            source_agent="dbos_task_verifier",
            tags=["dbos", "task_verification", "reconciled"],
        )
        self.store.add(verification)
        return verification

    @staticmethod
    def _provider_effect(execution: ExecutionResultArtifact) -> dict[str, Any] | None:
        for effect in execution.effects:
            if not isinstance(effect, dict):
                continue
            if effect.get("kind") != "registered_bsc_capability":
                continue
            if str(effect.get("mode", "")).lower() not in {"real", "api"}:
                continue
            artifact_ids = effect.get("artifact_ids")
            if not isinstance(artifact_ids, list):
                artifact_ids = []
            return {"artifact_ids": artifact_ids}
        return None

    def _existing_result(self, mission_id: str, capability_name: str, idempotency_key: str) -> ExecutionResultArtifact | None:
        for item in self.store.get_by_type(ArtifactType.EXECUTION_RESULT):
            if not isinstance(item, ExecutionResultArtifact):
                continue
            if item.mission_id == mission_id and item.capability_name == capability_name and item.idempotency_key == idempotency_key:
                return item
        return None

    def _next_attempt(self, mission_id: str, capability_name: str) -> int:
        attempts = [
            item.attempt
            for item in self.store.get_by_type(ArtifactType.EXECUTION_RESULT)
            if isinstance(item, ExecutionResultArtifact)
            and item.mission_id == mission_id
            and item.capability_name == capability_name
        ]
        return max(attempts, default=0) + 1

    async def _dispatch(self, capability: Any, name: str, context: dict[str, Any], callback: Callable[[str, dict[str, Any]], Awaitable[Any] | Any] | None) -> Any:
        if callback is not None:
            value = callback(name, context)
            return await value if inspect.isawaitable(value) else value
        if self.executor is None:
            self.executor = CapabilityExecutor(self.store)
        execution = await self.executor.execute(capability, input_text=str(context.get("intent") or ""), project_id=str(context.get("project_id") or ""))
        if str(getattr(execution, "status", "")) not in {"success", "completed"}:
            raise DBOSExecutionError(str(getattr(execution, "error", "capability execution failed")))
        return execution

    def _record_denied_attempt(self, mission: MissionArtifact, capability_name: str, dynamic_sop_id: str, idempotency_key: str, reason: str) -> None:
        result = ExecutionResultArtifact(
            project_id=mission.project_id,
            label=f"Rejected execution: {capability_name}"[:140],
            mission_id=mission.artifact_id,
            dynamic_sop_id=dynamic_sop_id,
            capability_name=capability_name,
            execution_id=f"exec_{uuid4().hex[:16]}",
            execution_status="rejected",
            idempotency_key=idempotency_key,
            error=reason,
            stop_reason="authorization_denied",
            parent_ids=[mission.artifact_id, dynamic_sop_id],
            status=ArtifactStatus.FAILED,
            started_at=_timestamp(),
            completed_at=_timestamp(),
            source_agent="dbos_execution",
        )
        self.store.add(result)

    def _set_mission_status(self, mission: MissionArtifact, state: str, status: ArtifactStatus) -> None:
        current = self.store.get(mission.artifact_id)
        if not isinstance(current, MissionArtifact):
            return
        self.store.update(current.model_copy(update={"mission_status": state, "status": status}))

    def _set_completion_state(self, mission: MissionArtifact) -> None:
        """Keep a confirmed mission open until every granted capability has evidence."""
        current = self.store.get(mission.artifact_id)
        if not isinstance(current, MissionArtifact):
            return
        granted = {str(name) for name in current.authorization.get("authorized_capabilities", []) if str(name)}
        completed = {
            item.capability_name
            for item in self.store.get_by_type(ArtifactType.EXECUTION_RESULT)
            if isinstance(item, ExecutionResultArtifact)
            and item.mission_id == current.artifact_id
            and item.execution_status == "completed"
        }
        if granted and granted.issubset(completed):
            self._set_mission_status(current, "completed", ArtifactStatus.COMPLETED)
            return
        self._set_mission_status(current, "confirmed", ArtifactStatus.CONFIRMED)

    def stop(self, mission: MissionArtifact, reason: str) -> MissionArtifact:
        if mission.mission_status in {"completed", "failed", "rolled_back"}:
            raise MissionStateError("terminal mission cannot be stopped")
        stopped = mission.model_copy(
            update={
                "mission_status": "stopped",
                "status": ArtifactStatus.STOPPED,
                "authorization": {**mission.authorization, "stop_reason": reason.strip()},
            }
        )
        self.store.update(stopped)
        return stopped

    def rollback(self, execution: ExecutionResultArtifact, reason: str) -> ExecutionResultArtifact:
        if execution.execution_status not in {"completed", "failed", "rejected"}:
            raise MissionStateError("execution is not in a rollback-eligible state")
        rolled_back = execution.model_copy(
            update={
                "execution_status": "rolled_back",
                "status": ArtifactStatus.ROLLED_BACK,
                "rollback": {"status": "recorded", "reason": reason.strip(), "at": _timestamp()},
            }
        )
        self.store.update(rolled_back)
        mission = self.store.get(execution.mission_id)
        if isinstance(mission, MissionArtifact):
            self._set_mission_status(mission, "rolled_back", ArtifactStatus.ROLLED_BACK)
        return rolled_back


def _effect_summary(capability_name: str, outcome: Any) -> dict[str, Any]:
    if hasattr(outcome, "artifacts_produced"):
        return {
            "kind": "registered_bsc_capability",
            "capability_name": capability_name,
            "artifact_ids": list(getattr(outcome, "artifacts_produced", []) or []),
            "backend": str(getattr(outcome, "backend", "")),
            "mode": str(getattr(outcome, "mode", "")),
        }
    if isinstance(outcome, dict):
        effect = str(outcome.get("effect") or outcome.get("status") or "internal capability completed")
        return {"kind": "registered_bsc_capability", "capability_name": capability_name, "effect": effect[:500]}
    return {"kind": "registered_bsc_capability", "capability_name": capability_name, "effect": str(outcome)[:500]}


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:400]}"


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
