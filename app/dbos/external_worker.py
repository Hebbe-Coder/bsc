"""Governed, cancellable external HTTPS worker execution.

External workers are intentionally not part of the request lifecycle.  A
request first creates a redacted ledger entry, then an isolated asyncio loop
owns the HTTPS call.  Cancellation races the transport task against a
loop-local signal and only records ``cancelled`` after the transport task has
acknowledged cancellation.  A process restart has no such proof, so recovery
marks every unfinished call ``interrupted`` and never replays it.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import httpx
import json
import os
import re
from threading import Lock, RLock, Thread
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from app.artifacts import (
    ArtifactGraphStore,
    ArtifactStatus,
    ArtifactType,
    DecisionArtifact,
    DynamicSOPArtifact,
    MissionArtifact,
)
from app.artifacts.types import ExternalWorkerRunArtifact
from app.knowledge.growth_contracts import ExternalWorkerPolicy, ProjectKnowledgeProfile
from app.knowledge.growth_repository import GrowthRepository


class ExternalWorkerPolicyError(RuntimeError):
    """Raised only after a rejected ledger record has been persisted."""


@dataclass(frozen=True)
class ExternalWorkerResponse:
    """The worker response must point to BSC-owned output artifacts."""

    output_artifact_ids: list[str]
    estimated_cost_microusd: int = 0


AsyncTransport = Callable[[str, bytes, str, int], Awaitable[ExternalWorkerResponse]]
HttpClientFactory = Callable[[httpx.Timeout], httpx.AsyncClient]


def _default_http_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False)


_HTTP_CLIENT_FACTORY: HttpClientFactory = _default_http_client


@dataclass
class _ActiveWorker:
    """In-memory control plane only; durable state lives in the Artifact Graph."""

    future: Future[Any] | None = None
    cancel_event: asyncio.Event | None = None
    cancel_requested: bool = False
    ready: bool = False


class ExternalWorkerSupervisor:
    """Dedicated event loop for cancellable egress, shared by REST and MCP.

    The worker loop prevents a synchronous MCP call or FastAPI request from
    holding the outbound connection.  It deliberately has no persistence: a
    process restart loses the live task and recovery records that uncertainty
    instead of retrying an external side effect.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._active: dict[str, _ActiveWorker] = {}

    def submit(
        self,
        run_id: str,
        operation: Callable[[asyncio.Event], Awaitable[ExternalWorkerRunArtifact]],
    ) -> None:
        with self._lock:
            self._ensure_loop_locked()
            if run_id in self._active:
                raise RuntimeError("external worker is already active")
            active = _ActiveWorker()
            self._active[run_id] = active
            assert self._loop is not None

            async def wrapped() -> ExternalWorkerRunArtifact:
                # ``run_coroutine_threadsafe`` can start promptly on a fast
                # loop, so wait one cooperative turn until registration is
                # complete before reading the control-plane entry.
                while not active.ready:
                    await asyncio.sleep(0)
                cancel_event = asyncio.Event()
                with self._lock:
                    active.cancel_event = cancel_event
                    cancel_requested = active.cancel_requested
                if cancel_requested:
                    cancel_event.set()
                return await operation(cancel_event)

            future = asyncio.run_coroutine_threadsafe(wrapped(), self._loop)
            active.future = future
            active.ready = True
            future.add_done_callback(lambda _: self._remove(run_id, active))

    def request_cancel(self, run_id: str) -> bool:
        """Signal the worker loop without cancelling its root task abruptly."""
        with self._lock:
            active = self._active.get(run_id)
            if active is None or active.future is None or active.future.done():
                return False
            active.cancel_requested = True
            if active.cancel_event is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(active.cancel_event.set)
            return True

    def _remove(self, run_id: str, active: _ActiveWorker) -> None:
        with self._lock:
            if self._active.get(run_id) is active:
                self._active.pop(run_id, None)

    def _ensure_loop_locked(self) -> None:
        if self._loop is not None and self._loop.is_running():
            return
        loop = asyncio.new_event_loop()
        thread = Thread(target=self._run_loop, args=(loop,), name="bsc-external-worker", daemon=True)
        self._loop = loop
        self._thread = thread
        thread.start()

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()


_SUPERVISOR = ExternalWorkerSupervisor()
_LEDGER_LOCK = RLock()


class ExternalWorkerService:
    def __init__(self, store: ArtifactGraphStore, repository: GrowthRepository, *, environment: str | None = None) -> None:
        self.store = store
        self.repository = repository
        self.environment = (environment or os.getenv("BSC_RUNTIME_ENV", "development")).strip().lower()

    def start(
        self,
        *,
        mission_id: str,
        dynamic_sop_id: str,
        capability_name: str,
        worker_id: str,
        model_id: str,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
        estimated_cost_microusd: int = 0,
        transport: AsyncTransport | None = None,
    ) -> ExternalWorkerRunArtifact:
        """Persist a queued attempt and schedule it outside the caller lifecycle."""
        with _LEDGER_LOCK:
            prepared = self._prepare(
                mission_id=mission_id,
                dynamic_sop_id=dynamic_sop_id,
                capability_name=capability_name,
                worker_id=worker_id,
                model_id=model_id,
                endpoint=endpoint,
                payload=payload,
                idempotency_key=idempotency_key,
                estimated_cost_microusd=estimated_cost_microusd,
            )
            if isinstance(prepared, ExternalWorkerRunArtifact):
                return prepared
            mission, profile, policy, body, host, secret = prepared
            queued = self._record(
                mission, dynamic_sop_id, capability_name, worker_id, model_id, host,
                profile.revision, policy, "queued", idempotency_key, body,
                estimated_cost_microusd, "",
            )
        try:
            _SUPERVISOR.submit(
                queued.artifact_id,
                lambda cancel_event: self._execute_record(
                    queued.artifact_id,
                    endpoint=endpoint,
                    body=body,
                    secret=secret,
                    policy=policy,
                    transport=transport or _https_transport,
                    cancel_event=cancel_event,
                ),
            )
        except Exception as exc:
            return self._mark_failed(queued, exc, estimated_cost_microusd)
        return queued

    async def execute(
        self,
        *,
        mission_id: str,
        dynamic_sop_id: str,
        capability_name: str,
        worker_id: str,
        model_id: str,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
        estimated_cost_microusd: int = 0,
        transport: AsyncTransport | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> ExternalWorkerRunArtifact:
        """Execute directly for controlled integration tests and adapters.

        REST and MCP use :meth:`start`; this method exists so a caller with an
        explicit event loop can test the same transport/cancellation contract
        without turning a test double into a claimed provider execution.
        """
        with _LEDGER_LOCK:
            prepared = self._prepare(
                mission_id=mission_id,
                dynamic_sop_id=dynamic_sop_id,
                capability_name=capability_name,
                worker_id=worker_id,
                model_id=model_id,
                endpoint=endpoint,
                payload=payload,
                idempotency_key=idempotency_key,
                estimated_cost_microusd=estimated_cost_microusd,
            )
            if isinstance(prepared, ExternalWorkerRunArtifact):
                return prepared
            mission, profile, policy, body, host, secret = prepared
            queued = self._record(
                mission, dynamic_sop_id, capability_name, worker_id, model_id, host,
                profile.revision, policy, "queued", idempotency_key, body,
                estimated_cost_microusd, "",
            )
        return await self._execute_record(
            queued.artifact_id,
            endpoint=endpoint,
            body=body,
            secret=secret,
            policy=policy,
            transport=transport or _https_transport,
            cancel_event=cancel_event or asyncio.Event(),
        )

    def request_cancel(self, run_id: str, *, reason: str) -> ExternalWorkerRunArtifact:
        """Request cancellation and leave the terminal verdict to the transport.

        A request is not a cancellation proof.  The record remains
        ``cancellation_requested`` until the isolated loop either observes the
        signal before dispatch or delivers cancellation to the active HTTP task.
        """
        with _LEDGER_LOCK:
            run = self.store.get(run_id)
            if not isinstance(run, ExternalWorkerRunArtifact):
                raise KeyError("external worker run was not found in this project")
            if run.worker_status in {"completed", "failed", "rejected", "cancelled", "interrupted"}:
                return run
            requested = run.model_copy(update={
                "worker_status": "cancellation_requested",
                "reason": _cancellation_reason(reason),
                "cancellation_requested_at": _timestamp(),
                "status": ArtifactStatus.ACTIVE,
            })
            self.store.update(requested)
        if _SUPERVISOR.request_cancel(run_id):
            return requested

        # An active task should always be known to the process.  If it is not,
        # BSC cannot prove whether an external request reached the provider.
        # Preserve that uncertainty and require a new manual idempotency key.
        with _LEDGER_LOCK:
            latest = self._run(run_id)
            if latest.worker_status in {"completed", "failed", "rejected", "cancelled", "interrupted"}:
                return latest
            interrupted = requested.model_copy(update={
                "worker_status": "interrupted",
                "status": ArtifactStatus.INTERRUPTED,
                "reason": "cancellation could not reach a live worker; external side effect is unknown and will not be replayed",
                "completed_at": _timestamp(),
                "recovered_at": _timestamp(),
            })
            self.store.update(interrupted)
            return interrupted

    def recover_interrupted(self) -> list[ExternalWorkerRunArtifact]:
        """Mark durable non-terminal calls as uncertain after a process restart."""
        with _LEDGER_LOCK:
            recovered: list[ExternalWorkerRunArtifact] = []
            for item in self.store.get_by_type(ArtifactType.EXTERNAL_WORKER_RUN):
                if not isinstance(item, ExternalWorkerRunArtifact):
                    continue
                if item.worker_status not in {"queued", "executing", "cancellation_requested"}:
                    continue
                interrupted = item.model_copy(update={
                    "worker_status": "interrupted",
                    "status": ArtifactStatus.INTERRUPTED,
                    "reason": "process restart left an external worker unresolved; BSC did not automatically replay the outbound request",
                    "completed_at": _timestamp(),
                    "recovered_at": _timestamp(),
                })
                self.store.update(interrupted)
                recovered.append(interrupted)
            return recovered

    def _prepare(
        self,
        *,
        mission_id: str,
        dynamic_sop_id: str,
        capability_name: str,
        worker_id: str,
        model_id: str,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
        estimated_cost_microusd: int,
    ) -> tuple[MissionArtifact, ProjectKnowledgeProfile, ExternalWorkerPolicy, bytes, str, str] | ExternalWorkerRunArtifact:
        mission = self.store.get(mission_id)
        if not isinstance(mission, MissionArtifact):
            raise ExternalWorkerPolicyError("mission does not exist")
        profile = ProjectKnowledgeProfile.model_validate(
            self.repository.get_profile(mission.project_id) or {"project_id": mission.project_id}
        )
        existing = self._existing(mission.artifact_id, capability_name, idempotency_key)
        if existing is not None:
            return existing
        body = json.dumps(
            {"model_id": model_id, "input": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        policy = profile.external_worker_policy
        host = (urlparse(endpoint).hostname or "").lower()
        reason = self._rejection_reason(
            mission, policy, dynamic_sop_id, capability_name, worker_id, model_id,
            endpoint, host, estimated_cost_microusd,
        )
        if reason:
            self._record(
                mission, dynamic_sop_id, capability_name, worker_id, model_id, host,
                profile.revision, policy, "rejected", idempotency_key, body,
                estimated_cost_microusd, reason,
            )
            raise ExternalWorkerPolicyError(reason)
        secret = self._resolve_secret(policy.credential_ref)
        if not secret:
            reason = "server-side credential reference is unavailable"
            self._record(
                mission, dynamic_sop_id, capability_name, worker_id, model_id, host,
                profile.revision, policy, "rejected", idempotency_key, body,
                estimated_cost_microusd, reason,
            )
            raise ExternalWorkerPolicyError(reason)
        return mission, profile, policy, body, host, secret

    async def _execute_record(
        self,
        run_id: str,
        *,
        endpoint: str,
        body: bytes,
        secret: str,
        policy: ExternalWorkerPolicy,
        transport: AsyncTransport,
        cancel_event: asyncio.Event,
    ) -> ExternalWorkerRunArtifact:
        with _LEDGER_LOCK:
            run = self._run(run_id)
            if run.worker_status == "cancellation_requested" or cancel_event.is_set():
                return self._mark_cancelled(run, "cancelled before external request dispatch")
            if run.worker_status != "queued":
                return run
            executing = run.model_copy(update={
                "worker_status": "executing",
                "status": ArtifactStatus.EXECUTING,
                "outbound_started_at": _timestamp(),
            })
            self.store.update(executing)

        transport_task = asyncio.create_task(
            transport(endpoint, body, secret, policy.timeout_seconds),
            name=f"external-worker-transport:{run_id}",
        )
        cancellation_task = asyncio.create_task(cancel_event.wait(), name=f"external-worker-cancel:{run_id}")
        done, _ = await asyncio.wait({transport_task, cancellation_task}, return_when=asyncio.FIRST_COMPLETED)

        # A completed response wins a simultaneous race: by then BSC cannot
        # truthfully promise that cancellation prevented the provider effect.
        if transport_task in done:
            cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)
            try:
                response = transport_task.result()
            except Exception as exc:
                return self._mark_failed(executing, exc, executing.estimated_cost_microusd)
            return self._complete(executing, response, policy)

        transport_task.cancel()
        cancelled = await asyncio.gather(transport_task, return_exceptions=True)
        transport_result = cancelled[0] if cancelled else None
        if not isinstance(transport_result, asyncio.CancelledError):
            # The task may have won while cancellation was propagated. Do not
            # manufacture a cancelled result when the transport did not
            # acknowledge cancellation.
            if isinstance(transport_result, Exception):
                return self._mark_failed(executing, transport_result, executing.estimated_cost_microusd)
            return self._mark_interrupted(executing, "transport cancellation was not acknowledged; outbound effect is unknown")
        return self._mark_cancelled(executing, "HTTP transport cancelled before a worker response was accepted")

    def _complete(
        self,
        run: ExternalWorkerRunArtifact,
        response: ExternalWorkerResponse,
        policy: ExternalWorkerPolicy,
    ) -> ExternalWorkerRunArtifact:
        with _LEDGER_LOCK:
            actual_cost = max(0, response.estimated_cost_microusd)
            spent = sum(
                item.estimated_cost_microusd
                for item in self._policy_runs(run.project_id, policy)
                if item.worker_status == "completed" and item.artifact_id != run.artifact_id
            )
            if actual_cost > policy.max_cost_microusd - spent:
                return self._mark_failed(
                    run,
                    ExternalWorkerPolicyError("worker reported a cost above the remaining project budget"),
                    actual_cost,
                )
            output_ids = list(dict.fromkeys(str(value) for value in response.output_artifact_ids if str(value)))
            if not output_ids:
                return self._mark_failed(
                    run,
                    ExternalWorkerPolicyError("worker response did not identify a BSC-owned output artifact"),
                    actual_cost,
                )
            invalid = [artifact_id for artifact_id in output_ids if not self._is_project_output(artifact_id, run.project_id)]
            if invalid:
                return self._mark_failed(
                    run,
                    ExternalWorkerPolicyError("worker response referenced missing or cross-project output artifacts"),
                    actual_cost,
                )
            current = self._run(run.artifact_id)
            cancellation_note = ""
            if current.worker_status == "cancellation_requested":
                cancellation_note = "; cancellation arrived after the worker response and could not undo the accepted provider effect"
            source = current if current.worker_status == "cancellation_requested" else run
            completed = source.model_copy(update={
                "worker_status": "completed",
                "status": ArtifactStatus.COMPLETED,
                "output_artifact_ids": output_ids,
                "estimated_cost_microusd": actual_cost,
                "reason": (current.reason + cancellation_note)[:400],
                "completed_at": _timestamp(),
            })
            self.store.update(completed)
            return completed

    def _mark_failed(self, run: ExternalWorkerRunArtifact, exc: Exception, actual_cost: int) -> ExternalWorkerRunArtifact:
        with _LEDGER_LOCK:
            current = self._run(run.artifact_id)
            source = current if current.worker_status == "cancellation_requested" else run
            failure_count = self._failure_count(run.project_id, run.worker_id) + 1
            failed = source.model_copy(update={
                "worker_status": "failed",
                "status": ArtifactStatus.FAILED,
                "failure_count": failure_count,
                "estimated_cost_microusd": max(0, actual_cost),
                "escalated": failure_count >= 2,
                "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
                "completed_at": _timestamp(),
            })
            self.store.update(failed)
            return failed

    def _mark_cancelled(self, run: ExternalWorkerRunArtifact, reason: str) -> ExternalWorkerRunArtifact:
        with _LEDGER_LOCK:
            current = self._run(run.artifact_id)
            source = current if current.worker_status == "cancellation_requested" else run
            cancelled = source.model_copy(update={
                "worker_status": "cancelled",
                "status": ArtifactStatus.CANCELLED,
                "reason": (current.reason or reason)[:400],
                "cancelled_at": _timestamp(),
                "completed_at": _timestamp(),
            })
            self.store.update(cancelled)
            return cancelled

    def _mark_interrupted(self, run: ExternalWorkerRunArtifact, reason: str) -> ExternalWorkerRunArtifact:
        with _LEDGER_LOCK:
            interrupted = run.model_copy(update={
                "worker_status": "interrupted",
                "status": ArtifactStatus.INTERRUPTED,
                "reason": reason[:400],
                "completed_at": _timestamp(),
                "recovered_at": _timestamp(),
            })
            self.store.update(interrupted)
            return interrupted

    def _rejection_reason(
        self,
        mission: MissionArtifact,
        policy: ExternalWorkerPolicy,
        dynamic_sop_id: str,
        capability: str,
        worker_id: str,
        model_id: str,
        endpoint: str,
        host: str,
        cost: int,
    ) -> str:
        if mission.mission_status != "confirmed":
            return "external worker requires a confirmed mission"
        granted = {str(value) for value in mission.authorization.get("authorized_capabilities", [])}
        if capability not in granted:
            return "capability is not granted for this mission"
        if not self._has_task_decision(mission, dynamic_sop_id, capability):
            return "external worker requires a persisted decision for its Dynamic SOP task"
        if not policy.enabled:
            return "external worker policy is disabled"
        if self.environment not in set(policy.allowed_environments):
            return "runtime environment is not allowed by the external worker policy"
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not host or host not in set(policy.allowed_https_hosts):
            return "endpoint is not an allowlisted HTTPS host"
        if worker_id not in set(policy.worker_ids) or model_id not in set(policy.allowed_model_ids) or capability not in set(policy.allowed_capabilities):
            return "worker, model or capability is not allowed by the project policy"
        runs = self._policy_runs(mission.project_id, policy)
        if len([run for run in runs if run.worker_status != "rejected"]) >= policy.max_calls:
            return "external worker call budget is exhausted"
        active_states = {"queued", "executing", "cancellation_requested"}
        if len([run for run in runs if run.worker_status in active_states]) >= policy.max_concurrent:
            return "external worker concurrency budget is exhausted"
        spent = sum(run.estimated_cost_microusd for run in runs if run.worker_status == "completed")
        if cost < 0 or spent + cost > policy.max_cost_microusd:
            return "external worker cost budget is exhausted"
        return ""

    def _existing(self, mission_id: str, capability_name: str, idempotency_key: str) -> ExternalWorkerRunArtifact | None:
        if not idempotency_key:
            return None
        matches = [
            item for item in self.store.get_by_type(ArtifactType.EXTERNAL_WORKER_RUN)
            if isinstance(item, ExternalWorkerRunArtifact)
            and item.mission_id == mission_id
            and item.capability_name == capability_name
            and item.idempotency_key == idempotency_key
        ]
        return max(matches, key=lambda item: item.created_at) if matches else None

    def _run(self, run_id: str) -> ExternalWorkerRunArtifact:
        item = self.store.get(run_id)
        if not isinstance(item, ExternalWorkerRunArtifact):
            raise KeyError("external worker run was not found in this project")
        return item

    def _has_task_decision(self, mission: MissionArtifact, dynamic_sop_id: str, capability_name: str) -> bool:
        sop = self.store.get(dynamic_sop_id)
        task_ids = {
            task.task_id
            for phase in sop.phases
            for task in phase.tasks
            if task.capability_name == capability_name
        } if isinstance(sop, DynamicSOPArtifact) else set()
        for item in self.store.get_by_project(mission.project_id):
            if not isinstance(item, DecisionArtifact) or mission.artifact_id not in item.parent_ids:
                continue
            metadata = item.metadata if isinstance(item.metadata, dict) else {}
            if str(metadata.get("dynamic_sop_id") or "") == dynamic_sop_id and str(metadata.get("capability_name") or "") == capability_name:
                return True
            if str(metadata.get("task_id") or "") in task_ids:
                return True
        return False

    def _record(
        self,
        mission: MissionArtifact,
        dynamic_sop_id: str,
        capability: str,
        worker_id: str,
        model_id: str,
        host: str,
        revision: int,
        policy: ExternalWorkerPolicy,
        state: str,
        key: str,
        body: bytes,
        cost: int,
        reason: str,
    ) -> ExternalWorkerRunArtifact:
        statuses = {
            "queued": ArtifactStatus.ACTIVE,
            "executing": ArtifactStatus.EXECUTING,
            "completed": ArtifactStatus.COMPLETED,
            "cancelled": ArtifactStatus.CANCELLED,
            "interrupted": ArtifactStatus.INTERRUPTED,
        }
        artifact = ExternalWorkerRunArtifact(
            project_id=mission.project_id,
            label=f"External worker: {worker_id}"[:140],
            mission_id=mission.artifact_id,
            dynamic_sop_id=dynamic_sop_id,
            capability_name=capability,
            worker_id=worker_id,
            model_id=model_id,
            egress_host=host,
            credential_ref=policy.credential_ref,
            policy_revision=revision,
            worker_status=state,
            idempotency_key=key,
            input_fingerprint=hashlib.sha256(body).hexdigest(),
            estimated_cost_microusd=max(0, cost),
            timeout_seconds=policy.timeout_seconds,
            call_index=len(self._policy_runs(mission.project_id, policy)) + 1,
            reason=reason[:400],
            requested_at=_timestamp(),
            parent_ids=[mission.artifact_id, dynamic_sop_id] if dynamic_sop_id else [mission.artifact_id],
            status=statuses.get(state, ArtifactStatus.FAILED),
            source_agent="external_worker_governance",
            tags=["dbos", "external_worker", state],
        )
        self.store.add(artifact)
        return artifact

    def _policy_runs(self, project_id: str, policy: ExternalWorkerPolicy) -> list[ExternalWorkerRunArtifact]:
        return [
            item for item in self.store.get_by_type(ArtifactType.EXTERNAL_WORKER_RUN)
            if isinstance(item, ExternalWorkerRunArtifact)
            and item.project_id == project_id
            and item.credential_ref == policy.credential_ref
        ]

    def _failure_count(self, project_id: str, worker_id: str) -> int:
        return len([
            item for item in self.store.get_by_type(ArtifactType.EXTERNAL_WORKER_RUN)
            if isinstance(item, ExternalWorkerRunArtifact)
            and item.project_id == project_id
            and item.worker_id == worker_id
            and item.worker_status == "failed"
        ])

    def _is_project_output(self, artifact_id: str, project_id: str) -> bool:
        artifact = self.store.get(artifact_id)
        return artifact is not None and artifact.project_id == project_id

    @staticmethod
    def _resolve_secret(reference: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", reference or ""):
            return ""
        return os.getenv("BSC_EXTERNAL_WORKER_SECRET_" + reference.upper().replace("-", "_"), "")


async def _https_transport(endpoint: str, body: bytes, secret: str, timeout_seconds: int) -> ExternalWorkerResponse:
    """Perform one HTTPS POST with no inherited proxy or credential settings."""
    timeout = httpx.Timeout(timeout_seconds)
    async with _HTTP_CLIENT_FACTORY(timeout) as client:
        response = await client.post(
            endpoint,
            content=body,
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        )
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("external worker response must be a JSON object")
    return ExternalWorkerResponse(
        output_artifact_ids=list(data.get("output_artifact_ids") or []),
        estimated_cost_microusd=int(data.get("estimated_cost_microusd") or 0),
    )


def recover_interrupted_external_workers(store: ArtifactGraphStore) -> list[ExternalWorkerRunArtifact]:
    """Recovery hook for startup; it never starts or retries a provider request."""
    repository = _RecoveryRepository()
    return ExternalWorkerService(store, repository).recover_interrupted()


class _RecoveryRepository:
    """Only satisfies the constructor because recovery never reads a profile."""

    def get_profile(self, project_id: str) -> None:  # pragma: no cover - defensive boundary
        del project_id
        return None


def _cancellation_reason(reason: str) -> str:
    value = reason.strip()
    return f"cancellation requested: {value}"[:400] if value else "cancellation requested by an authorized user"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "AsyncTransport",
    "ExternalWorkerPolicyError",
    "ExternalWorkerResponse",
    "ExternalWorkerService",
    "recover_interrupted_external_workers",
]
