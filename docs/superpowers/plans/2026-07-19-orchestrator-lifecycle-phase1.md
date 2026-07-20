# Orchestrator Lifecycle Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/orchestrate` a reliable, observable workflow whose persisted terminal state and SSE terminal event drive the React Workspace to fetch and render completed results.

**Architecture:** Keep the existing Orchestrator agents and SQLite draft schema. Add explicit lifecycle transitions to `ProjectDraftRepository`, replace the single-consumer queue with sequenced replayable fan-out, retain background task references, and make the frontend wait for a terminal event before fetching the dashboard. This is an in-process Phase 1 design; durable event storage and BusinessRuntime convergence are separate plans.

**Tech Stack:** Python 3.13 current workspace / FastAPI / asyncio / SQLite / pytest; React 18 / TypeScript / EventSource / Zustand / Vite.

**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

---

## File Structure

**Create:**

- `app/orchestrator/contracts.py` - canonical lifecycle and event models.
- `tests/orchestrator/conftest.py` - isolated SQLite repository fixture for lifecycle tests.
- `tests/orchestrator/test_contracts.py` - model and terminal-state tests.
- `tests/orchestrator/test_sse.py` - replay, fan-out and terminal-close tests.
- `tests/orchestrator/test_lifecycle.py` - engine success/failure persistence tests.

**Modify:**

- `app/agent/state.py` - non-destructive lifecycle transition methods using the existing `status` column.
- `app/orchestrator/sse.py` - sequenced event history and per-subscriber queues.
- `app/orchestrator/engine.py` - started/completed/failed transitions and terminal events.
- `app/api/orchestrate.py` - task registry, status endpoint, canonical SSE endpoint and compatibility alias.
- `src/api/orchestrateApi.ts` - typed event/status contracts and terminal subscription.
- `src/components/UnifiedWorkspace.tsx` - remove 30-second completion timer; fetch dashboard on terminal completion.
- `src/store/workspaceStore.ts` - typed orchestrator result projection.
- `tests/orchestrator/test_api.py` - HTTP 202, status and stream contract tests.
- `tests/orchestrator/test_state.py` - guarded transition coverage.
- `tests/orchestrator/test_engine.py` - lifecycle event-aware FakeBus.
- `tests/orchestrator/test_e2e.py` - lifecycle event-aware FakeBus.
- `tests/orchestrator/test_methodology_e2e.py` - lifecycle event-aware FakeBus.
- `tests/orchestrator/test_rerun.py` - lifecycle event-aware FakeBus.

**Explicitly unchanged:**

- `app/capabilities/runtime.py`
- `app/artifacts/store.py`
- `app/core/async_pipeline.py`
- database table columns
- authentication policy

---

### Task 1: Define Canonical Lifecycle and Event Contracts

**Files:**

- Create: `app/orchestrator/contracts.py`
- Create: `tests/orchestrator/test_contracts.py`

- [x] **Step 1: Write the failing contract tests**

```python
# tests/orchestrator/test_contracts.py
import pytest
from pydantic import ValidationError

from app.orchestrator.contracts import (
    EventType,
    JobStatus,
    OrchestratorEvent,
    is_terminal,
)


def test_terminal_statuses_are_explicit():
    assert is_terminal(JobStatus.COMPLETED)
    assert is_terminal(JobStatus.FAILED)
    assert is_terminal(JobStatus.CANCELLED)
    assert not is_terminal(JobStatus.QUEUED)
    assert not is_terminal(JobStatus.RUNNING)


def test_event_requires_positive_sequence():
    with pytest.raises(ValidationError):
        OrchestratorEvent(
            session_id="s1",
            seq=0,
            type=EventType.PIPELINE_STARTED,
            status="running",
        )


def test_terminal_event_sets_terminal_flag():
    event = OrchestratorEvent(
        session_id="s1",
        seq=1,
        type=EventType.PIPELINE_COMPLETED,
        status="completed",
        terminal=True,
    )
    assert event.terminal is True
    assert event.model_dump(mode="json")["type"] == "pipeline.completed"
```

- [x] **Step 2: Run the tests and verify the missing module failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.orchestrator.contracts'`.

- [x] **Step 3: Add the contract models**

```python
# app/orchestrator/contracts.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
})


def is_terminal(status: JobStatus | str) -> bool:
    try:
        value = status if isinstance(status, JobStatus) else JobStatus(status)
    except ValueError:
        return False
    return value in TERMINAL_STATUSES


class EventType(str, Enum):
    PIPELINE_STARTED = "pipeline.started"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_LOOPBACK = "stage.loopback"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_CANCELLED = "pipeline.cancelled"


class OrchestratorEvent(BaseModel):
    session_id: str = Field(min_length=1)
    seq: int = Field(gt=0)
    type: EventType
    stage: str = "pipeline"
    status: str
    message: str = ""
    terminal: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    session_id: str
    status: JobStatus
    terminal: bool
```

- [x] **Step 4: Run the tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_contracts.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit the contract unit**

```powershell
git add app/orchestrator/contracts.py tests/orchestrator/test_contracts.py
git commit -m "feat(orchestrator): define lifecycle event contracts"
```

---

### Task 2: Add Non-Destructive Lifecycle Transitions

**Files:**

- Modify: `app/agent/state.py`
- Create: `tests/orchestrator/conftest.py`
- Modify: `tests/orchestrator/test_state.py`

- [x] **Step 1: Add an isolated repository fixture and failing transition tests**

Create the orchestrator-local fixture:

```python
# tests/orchestrator/conftest.py
import sqlite3

import pytest

from app.agent.state import ProjectDraftRepository


@pytest.fixture
def draft_repo(tmp_path):
    connection = sqlite3.connect(
        str(tmp_path / "orchestrator-state.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    repo = ProjectDraftRepository(connection=connection)
    try:
        yield repo
    finally:
        connection.close()
```

Append to `tests/orchestrator/test_state.py`:

```python
import pytest

from app.orchestrator.contracts import JobStatus


def test_transition_updates_existing_status(draft_repo):
    draft = ProjectDraft(session_id="life-1", idea="x", status="queued")
    draft_repo.save(draft)

    updated = draft_repo.transition("life-1", JobStatus.RUNNING)

    assert updated.status == "running"
    assert draft_repo.get("life-1").status == "running"


def test_terminal_status_cannot_transition(draft_repo):
    draft = ProjectDraft(session_id="life-2", idea="x", status="completed")
    draft_repo.save(draft)

    with pytest.raises(ValueError, match="terminal"):
        draft_repo.transition("life-2", JobStatus.RUNNING)


def test_save_cannot_overwrite_terminal_status(draft_repo):
    draft_repo.save(ProjectDraft(
        session_id="life-3",
        idea="x",
        status="completed",
    ))

    with pytest.raises(ValueError, match="terminal"):
        draft_repo.save(ProjectDraft(
            session_id="life-3",
            idea="x",
            status="running",
        ))


def test_transition_unknown_session_raises(draft_repo):
    with pytest.raises(KeyError, match="missing"):
        draft_repo.transition("missing", JobStatus.FAILED)
```

- [x] **Step 2: Run the state tests and verify the method is missing**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_state.py -q
```

Expected: fixture setup fails because `ProjectDraftRepository.__init__` does not accept `connection`.

- [x] **Step 3: Add connection injection and implement transitions without changing the table schema**

Replace the `ProjectDraftRepository` constructor in `app/agent/state.py` with:

```python
    def __init__(self, connection=None):
        self._db = connection or get_db()
        self._ensure_table()
```

Add to `ProjectDraftRepository` after `get` in `app/agent/state.py`:

```python
    def transition(self, session_id: str, status) -> ProjectDraft:
        from app.orchestrator.contracts import JobStatus, is_terminal

        target = status if isinstance(status, JobStatus) else JobStatus(status)
        draft = self.get(session_id)
        if draft is None:
            raise KeyError(f"session {session_id} not found")
        if is_terminal(draft.status):
            raise ValueError(
                f"session {session_id} already terminal: {draft.status}"
            )
        draft.status = target.value
        self.save(draft)
        return draft
```

At the start of `save`, before updating `draft.updated_at`, guard existing terminal rows:

```python
        from app.orchestrator.contracts import is_terminal

        existing = self.get(draft.session_id)
        if (
            existing is not None
            and is_terminal(existing.status)
            and draft.status != existing.status
        ):
            raise ValueError(
                f"session {draft.session_id} already terminal: {existing.status}"
            )
```

Do not modify `_ensure_table` in this task. Destructive schema migration removal belongs to the persistence plan.

- [x] **Step 4: Run state and contract tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_state.py tests\orchestrator\test_contracts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the lifecycle persistence unit**

```powershell
git add app/agent/state.py tests/orchestrator/conftest.py tests/orchestrator/test_state.py
git commit -m "feat(orchestrator): persist guarded job transitions"
```

---

### Task 3: Replace the Single-Consumer Queue with Replayable Fan-Out

**Files:**

- Modify: `app/orchestrator/sse.py`
- Create: `tests/orchestrator/test_sse.py`

- [x] **Step 1: Write failing replay and fan-out tests**

```python
# tests/orchestrator/test_sse.py
import asyncio

from app.orchestrator.contracts import EventType
from app.orchestrator.sse import SessionEventBus


async def _next(subscription):
    return await asyncio.wait_for(anext(subscription), timeout=0.2)


def test_replays_events_after_sequence():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        await bus.publish("s1", EventType.PIPELINE_STARTED, status="running")
        await bus.publish("s1", EventType.STAGE_STARTED, stage="planner", status="running")
        sub = bus.subscribe("s1", after=1)
        event = await _next(sub)
        await sub.aclose()
        assert event.seq == 2
        assert event.stage == "planner"

    asyncio.run(scenario())


def test_two_subscribers_receive_same_event():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        left = bus.subscribe("s1")
        right = bus.subscribe("s1")
        left_task = asyncio.create_task(_next(left))
        right_task = asyncio.create_task(_next(right))
        await asyncio.sleep(0)
        await bus.publish("s1", EventType.STAGE_STARTED, stage="sop", status="running")
        first, second = await asyncio.gather(left_task, right_task)
        await left.aclose()
        await right.aclose()
        assert first.seq == second.seq == 1

    asyncio.run(scenario())


def test_terminal_event_closes_subscription():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        await bus.publish(
            "s1",
            EventType.PIPELINE_COMPLETED,
            status="completed",
            terminal=True,
        )
        sub = bus.subscribe("s1")
        event = await _next(sub)
        assert event.terminal is True
        try:
            await _next(sub)
            assert False, "subscription must close after terminal event"
        except StopAsyncIteration:
            pass

    asyncio.run(scenario())


def test_legacy_dict_publish_remains_compatible():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        event = await bus.publish(
            "s1",
            {"stage": "planner", "status": "running", "msg": "start"},
        )
        assert event.type == EventType.STAGE_STARTED
        assert event.message == "start"

    asyncio.run(scenario())
```

- [x] **Step 2: Run the tests and verify the old API fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_sse.py -q
```

Expected: failures because `history_limit`, typed `publish`, replay and fan-out are not implemented.

- [x] **Step 3: Implement bounded history and subscriber fan-out**

Replace `app/orchestrator/sse.py` with:

```python
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import AsyncIterator

from app.orchestrator.contracts import EventType, OrchestratorEvent


_CLOSE = object()


class SessionEventBus:
    def __init__(self, history_limit: int = 256):
        self._history_limit = history_limit
        self._history: dict[str, deque[OrchestratorEvent]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def publish(
        self,
        session_id: str,
        event_type: EventType | str | dict,
        *,
        stage: str = "pipeline",
        status: str = "",
        message: str = "",
        terminal: bool = False,
        data: dict | None = None,
    ) -> OrchestratorEvent:
        if isinstance(event_type, dict):
            legacy = event_type
            stage = legacy.get("stage", stage)
            status = legacy.get("status", status if status else "running")
            message = legacy.get("msg", legacy.get("message", message))
            event_type = {
                "running": EventType.STAGE_STARTED,
                "done": EventType.STAGE_COMPLETED,
                "loopback": EventType.STAGE_LOOPBACK,
            }.get(status, EventType.STAGE_COMPLETED)
            data = {**(data or {}), "legacy": True}
        async with self._lock:
            self._seq[session_id] += 1
            event = OrchestratorEvent(
                session_id=session_id,
                seq=self._seq[session_id],
                type=event_type,
                stage=stage,
                status=status,
                message=message,
                terminal=terminal,
                data=data or {},
            )
            self._history[session_id].append(event)
            subscribers = tuple(self._subscribers.get(session_id, ()))

        for queue in subscribers:
            await queue.put(event)
        return event

    async def subscribe(
        self,
        session_id: str,
        after: int = 0,
    ) -> AsyncIterator[OrchestratorEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            replay = [
                event for event in self._history.get(session_id, ())
                if event.seq > after
            ]
            terminal_replayed = bool(replay and replay[-1].terminal)
            if not terminal_replayed:
                self._subscribers[session_id].add(queue)

        try:
            for event in replay:
                yield event
                if event.terminal:
                    return
            while True:
                item = await queue.get()
                if item is _CLOSE:
                    return
                yield item
                if item.terminal:
                    return
        finally:
            async with self._lock:
                self._subscribers[session_id].discard(queue)
                if not self._subscribers[session_id]:
                    self._subscribers.pop(session_id, None)

    async def close(self, session_id: str) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.pop(session_id, ()))
        for queue in subscribers:
            await queue.put(_CLOSE)
```

- [x] **Step 4: Run the SSE and existing engine tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_sse.py tests\orchestrator\test_engine.py -q
```

Expected: new SSE tests and existing engine tests pass. The temporary dictionary compatibility branch keeps this commit deployable until Task 4 migrates the engine to typed events.

- [ ] **Step 5: Commit the event bus unit**

```powershell
git add app/orchestrator/sse.py tests/orchestrator/test_sse.py
git commit -m "feat(orchestrator): add replayable fan-out event bus"
```

---

### Task 4: Persist Success and Failure Terminal States in the Engine

**Files:**

- Modify: `app/orchestrator/engine.py`
- Modify: `tests/orchestrator/test_engine.py`
- Modify: `tests/orchestrator/test_e2e.py`
- Modify: `tests/orchestrator/test_methodology_e2e.py`
- Modify: `tests/orchestrator/test_rerun.py`
- Create: `tests/orchestrator/test_lifecycle.py`

- [x] **Step 1: Add lifecycle tests with an isolated repository**

```python
# tests/orchestrator/test_lifecycle.py
import asyncio

import pytest

from app.agent.state import ProjectDraft
from app.orchestrator.contracts import EventType
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.sse import SessionEventBus


class Stub:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def run(self, **kwargs):
        if self.error:
            raise self.error
        return self.payload


def _agents(planner_error=None):
    return {
        "planner": Stub(
            {"project": {"name": "x"}, "requirements": []},
            error=planner_error,
        ),
        "architect": Stub({"business_model": {}}),
        "sop": Stub({"sop": {}}),
        "risk": Stub({"risk": {}}),
        "reviewer": Stub({"review": {"approved": True, "gaps": []}}),
        "presenter": Stub({"presentation": {}}),
    }


def test_success_persists_completed_and_emits_terminal(draft_repo):
    draft_repo.save(ProjectDraft(session_id="ok-1", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = OrchestratorEngine(_agents(), repo=draft_repo, bus=bus)

    asyncio.run(engine.run_pipeline("ok-1", "x"))

    assert draft_repo.get("ok-1").status == "completed"
    events = list(bus._history["ok-1"])
    assert events[-1].type == EventType.PIPELINE_COMPLETED
    assert events[-1].terminal is True


def test_failure_persists_failed_and_emits_terminal(draft_repo):
    draft_repo.save(ProjectDraft(session_id="bad-1", idea="x", status="queued"))
    bus = SessionEventBus()
    engine = OrchestratorEngine(
        _agents(planner_error=RuntimeError("planner exploded")),
        repo=draft_repo,
        bus=bus,
    )

    with pytest.raises(RuntimeError, match="planner exploded"):
        asyncio.run(engine.run_pipeline("bad-1", "x"))

    assert draft_repo.get("bad-1").status == "failed"
    events = list(bus._history["bad-1"])
    assert events[-1].type == EventType.PIPELINE_FAILED
    assert events[-1].terminal is True
    assert "planner exploded" not in events[-1].message


def test_cancellation_persists_cancelled_and_emits_terminal(draft_repo):
    class BlockingPlanner:
        async def run(self, **kwargs):
            await asyncio.sleep(60)

    async def scenario():
        agents = _agents()
        agents["planner"] = BlockingPlanner()
        draft_repo.save(ProjectDraft(
            session_id="cancel-1",
            idea="x",
            status="queued",
        ))
        bus = SessionEventBus()
        engine = OrchestratorEngine(agents, repo=draft_repo, bus=bus)
        task = asyncio.create_task(engine.run_pipeline("cancel-1", "x"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return bus

    bus = asyncio.run(scenario())
    assert draft_repo.get("cancel-1").status == "cancelled"
    events = list(bus._history["cancel-1"])
    assert events[-1].type == EventType.PIPELINE_CANCELLED
    assert events[-1].terminal is True
```

- [x] **Step 2: Run lifecycle tests and verify terminal behavior is absent**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_lifecycle.py -q
```

Expected: tests fail because the engine never transitions to terminal states or publishes terminal events.

- [x] **Step 3: Update engine event emission and wrap the pipeline lifecycle**

In `app/orchestrator/engine.py`, import:

```python
from app.orchestrator.contracts import EventType, JobStatus
```

Replace `_emit` with:

```python
    async def _emit(
        self,
        sid,
        stage,
        status,
        msg="",
        *,
        event_type=None,
        terminal=False,
        data=None,
    ):
        if event_type is None:
            event_type = {
                "running": EventType.STAGE_STARTED,
                "done": EventType.STAGE_COMPLETED,
                "loopback": EventType.STAGE_LOOPBACK,
            }.get(status, EventType.STAGE_COMPLETED)
        return await self.bus.publish(
            sid,
            event_type,
            stage=stage,
            status=status,
            message=msg,
            terminal=terminal,
            data=data,
        )
```

Rename the existing `run_pipeline` body to `_run_stages`, preserving its stage logic and return value. Add this public wrapper:

```python
    async def run_pipeline(self, session_id: str, idea: str) -> dict:
        if self.repo.get(session_id) is None:
            self.repo.save(ProjectDraft(
                session_id=session_id,
                idea=idea,
                status=JobStatus.QUEUED.value,
            ))
        self.repo.transition(session_id, JobStatus.RUNNING)
        await self._emit(
            session_id,
            "pipeline",
            "running",
            "Pipeline started",
            event_type=EventType.PIPELINE_STARTED,
        )
        try:
            state = await self._run_stages(session_id, idea)
            self.repo.transition(session_id, JobStatus.COMPLETED)
            await self._emit(
                session_id,
                "pipeline",
                "completed",
                "Pipeline completed",
                event_type=EventType.PIPELINE_COMPLETED,
                terminal=True,
            )
            return state
        except asyncio.CancelledError:
            self.repo.transition(session_id, JobStatus.CANCELLED)
            await self._emit(
                session_id,
                "pipeline",
                "cancelled",
                "Pipeline cancelled",
                event_type=EventType.PIPELINE_CANCELLED,
                terminal=True,
            )
            raise
        except Exception:
            self.repo.transition(session_id, JobStatus.FAILED)
            await self._emit(
                session_id,
                "pipeline",
                "failed",
                "Pipeline failed",
                event_type=EventType.PIPELINE_FAILED,
                terminal=True,
            )
            raise
```

Change `_save` so it preserves the current persisted status instead of forcing `running`:

```python
        current = self.repo.get(session_id)
        draft = ProjectDraft(
            session_id=session_id,
            idea=state.get("idea", ""),
            project=state.get("project", {}),
            requirements=state.get("requirements", []),
            business_model=state.get("business_model", {}),
            sop=state.get("sop", {}),
            risk=state.get("risk", {}),
            review=state.get("review", {}),
            presentation=state.get("presentation", {}),
            status=current.status if current else JobStatus.RUNNING.value,
            messages=state.get("messages", []),
        )
```

In `tests/orchestrator/test_engine.py`, `tests/orchestrator/test_e2e.py`, `tests/orchestrator/test_methodology_e2e.py`, and `tests/orchestrator/test_rerun.py`, replace each FakeBus `publish(self, session_id, event)` method with `publish(self, session_id, event_type, **kwargs)` and store the normalized event:

```python
class FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, session_id, event_type, **kwargs):
        self.events.append({"type": str(event_type), **kwargs})
```

Move every direct engine test onto the isolated `draft_repo` fixture so terminal session IDs remain immutable and repeated test runs are deterministic.

In `tests/orchestrator/test_engine.py`, change the factory and every test:

```python
def make_engine(repo):
    # keep the existing StubAgent and agents dictionary unchanged
    return OrchestratorEngine(agents=agents, repo=repo, bus=FakeBus())


def test_pipeline_writes_six_segments(draft_repo):
    eng = make_engine(draft_repo)
    # existing assertions remain unchanged
```

Apply the same signature change to the other five tests in that file: add `draft_repo` to each test function and replace every `make_engine()` with `make_engine(draft_repo)`, including `eng2` in `test_pipeline_runs_without_risk_agent`.

In `tests/orchestrator/test_e2e.py`, inject the fixture into the golden test and engine:

```python
def test_golden_content_moderation(draft_repo):
    # existing stub classes remain unchanged
    eng = OrchestratorEngine(
        agents={
            "planner": A(), "architect": B(), "sop": S(),
            "risk": K(), "reviewer": R(), "presenter": P(),
        },
        repo=draft_repo,
        bus=FakeBus(),
    )
```

In `tests/orchestrator/test_rerun.py`, pass the fixture through its factory:

```python
def make(repo):
    # keep the existing agents dictionary unchanged
    return OrchestratorEngine(agents=agents, repo=repo, bus=FakeBus())


def test_rerun_risk_propagates_to_reviewer_and_presenter(draft_repo):
    eng = make(draft_repo)
    # existing test body remains unchanged
```

In `tests/orchestrator/test_methodology_e2e.py`, add `draft_repo` to both test signatures and pass `repo=draft_repo` to both `OrchestratorEngine` constructors:

```python
eng = OrchestratorEngine(
    agents=_make_agents(sop_payload, bm_payload, bridge),
    repo=draft_repo,
    bus=FakeBus(),
)
```

- [x] **Step 4: Run lifecycle and full orchestrator tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator -q
```

Expected: all orchestrator tests pass, including three lifecycle tests.

- [ ] **Step 5: Commit the terminal lifecycle unit**

```powershell
git add app/agent/state.py app/orchestrator/engine.py tests/orchestrator
git commit -m "feat(orchestrator): persist and emit terminal lifecycle"
```

---

### Task 5: Manage Background Tasks and Expose Status and Event Endpoints

**Files:**

- Modify: `app/api/orchestrate.py`
- Modify: `tests/orchestrator/test_api.py`

- [x] **Step 1: Add failing API contract tests**

Append to `tests/orchestrator/test_api.py` using its existing authenticated client fixture:

```python
def test_create_returns_202_and_discovery_urls(client, monkeypatch):
    _enable_auth(monkeypatch)

    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    response = client.post(
        "/api/orchestrate",
        json={"idea": "test business"},
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"].endswith(body["session_id"])
    assert body["events_url"].endswith(body["session_id"] + "/events")


def test_create_rejects_duplicate_session_id(client, monkeypatch):
    import uuid

    async def blocked_run(self, session_id, idea):
        return {}

    _enable_auth(monkeypatch)
    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    sid = f"dup-{uuid.uuid4().hex[:8]}"
    payload = {"idea": "test business", "session_id": sid}
    first = client.post(
        "/api/orchestrate",
        json=payload,
        headers={"Authorization": "Bearer test-key-123"},
    )
    second = client.post(
        "/api/orchestrate",
        json=payload,
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert first.status_code == 202
    assert second.status_code == 409


def test_status_endpoint_returns_terminal_flag(client, monkeypatch):
    _enable_auth(monkeypatch)

    async def blocked_run(self, session_id, idea):
        return {}

    monkeypatch.setattr(
        "app.orchestrator.engine.OrchestratorEngine.run_pipeline",
        blocked_run,
    )
    created = client.post(
        "/api/orchestrate",
        json={"idea": "test business"},
        headers={"Authorization": "Bearer test-key-123"},
    ).json()
    repo = ProjectDraftRepository()
    repo.transition(created["session_id"], "running")
    repo.transition(created["session_id"], "completed")

    response = client.get(
        f"/api/orchestrate/{created['session_id']}",
        headers={"Authorization": "Bearer test-key-123"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["terminal"] is True


def test_cancel_requests_the_retained_task(client, monkeypatch):
    import uuid

    from app.api import orchestrate as orchestrate_api
    from app.agent.state import ProjectDraft, ProjectDraftRepository

    class Cancellable:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    _enable_auth(monkeypatch)
    sid = f"cancel-{uuid.uuid4().hex[:8]}"
    ProjectDraftRepository().save(ProjectDraft(
        session_id=sid,
        idea="x",
        status="running",
    ))
    task = Cancellable()
    orchestrate_api._tasks[sid] = task
    try:
        response = client.delete(
            f"/api/orchestrate/{sid}",
            headers={"Authorization": "Bearer test-key-123"},
        )
    finally:
        orchestrate_api._tasks.pop(sid, None)

    assert response.status_code == 202
    assert response.json()["cancel_requested"] is True
    assert task.cancelled is True


def test_resume_cursor_uses_last_event_id_header():
    from starlette.requests import Request
    from app.api import orchestrate as orchestrate_api

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/orchestrate/s1/events",
        "headers": [(b"last-event-id", b"7")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
        "scheme": "http",
    })

    assert orchestrate_api._resume_after(request, after=3) == 7


def test_unknown_status_returns_404(client, monkeypatch):
    _enable_auth(monkeypatch)
    response = client.get(
        "/api/orchestrate/missing-session",
        headers={"Authorization": "Bearer test-key-123"},
    )
    assert response.status_code == 404
```

- [x] **Step 2: Run API tests and verify the contract fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_api.py -q
```

Expected: failures for HTTP 202, missing discovery URLs and missing status endpoint.

- [x] **Step 3: Implement task retention, safe callbacks and canonical endpoints**

In `app/api/orchestrate.py`, import:

```python
import logging

from app.orchestrator.contracts import JobStatus, is_terminal

logger = logging.getLogger(__name__)
```

Add module state and helper:

```python
_tasks: dict[str, asyncio.Task] = {}


def _retain_task(session_id: str, coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks[session_id] = task

    def done(completed: asyncio.Task):
        if _tasks.get(session_id) is completed:
            _tasks.pop(session_id, None)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error(
                "orchestrator background task failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(done)
    return task
```

Change task creation and response:

```python
@router.post("", status_code=202)
async def orchestrate(request: Request):
    body = await request.json()
    idea = body.get("idea")
    if not isinstance(idea, str) or not idea.strip():
        raise HTTPException(400, "idea required")
    sid = body.get("session_id") or uuid.uuid4().hex[:12]
    repo = ProjectDraftRepository()
    if repo.get(sid) is not None:
        raise HTTPException(status_code=409, detail="session already exists")
    repo.save(ProjectDraft(
        session_id=sid,
        idea=idea.strip(),
        status=JobStatus.QUEUED.value,
    ))
    llm = LLMService()
    engine = OrchestratorEngine(agents=build_agents(llm), repo=repo, bus=_bus)
    _retain_task(sid, engine.run_pipeline(sid, idea.strip()))
    return {
        "session_id": sid,
        "status": JobStatus.QUEUED.value,
        "status_url": f"/api/orchestrate/{sid}",
        "events_url": f"/api/orchestrate/{sid}/events",
    }
```

Add status and canonical event endpoints before the existing dashboard endpoint:

```python
@router.get("/{session_id}")
async def get_status(session_id: str):
    draft = ProjectDraftRepository().get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session_id,
        "status": draft.status,
        "terminal": is_terminal(draft.status),
    }


@router.delete("/{session_id}", status_code=202)
async def cancel(session_id: str):
    draft = ProjectDraftRepository().get(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="session not found")
    if is_terminal(draft.status):
        return {
            "session_id": session_id,
            "status": draft.status,
            "cancel_requested": False,
        }
    task = _tasks.get(session_id)
    if task is None:
        raise HTTPException(status_code=409, detail="task is not active")
    task.cancel()
    return {
        "session_id": session_id,
        "status": draft.status,
        "cancel_requested": True,
    }


def _resume_after(request: Request, after: int) -> int:
    raw = request.headers.get("last-event-id")
    if raw is None:
        return after
    try:
        return max(after, int(raw))
    except ValueError:
        return after


def _event_response(session_id: str, after: int):
    async def event_gen():
        async for event in _bus.subscribe(session_id, after=after):
            payload = event.model_dump(mode="json")
            yield (
                f"id: {event.seq}\n"
                f"event: {event.type.value}\n"
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{session_id}/events")
async def events(request: Request, session_id: str, after: int = 0):
    if ProjectDraftRepository().get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _event_response(session_id, _resume_after(request, after))
```

Keep `/stream` as a compatibility alias and delegate to `_event_response`:

```python
@router.get("/stream")
async def stream(request: Request, session_id: str, after: int = 0):
    if ProjectDraftRepository().get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _event_response(session_id, _resume_after(request, after))
```

Ensure `/stream` is declared before `/{session_id}` so FastAPI does not interpret `stream` as a session ID.

Update the existing `test_orchestrate_runs` assertion from `status_code == 200` to `status_code == 202`.

- [x] **Step 4: Run API and orchestrator tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator -q
```

Expected: all orchestrator tests pass.

- [ ] **Step 5: Commit the API lifecycle unit**

```powershell
git add app/api/orchestrate.py tests/orchestrator/test_api.py
git commit -m "feat(api): expose managed orchestrator lifecycle"
```

---

### Task 6: Drive the React Workspace from Terminal Events

**Files:**

- Modify: `src/api/orchestrateApi.ts`
- Modify: `src/components/UnifiedWorkspace.tsx`
- Modify: `src/store/workspaceStore.ts`
- Test: TypeScript check plus focused browser/API smoke test

- [x] **Step 1: Define typed frontend contracts**

Replace `src/api/orchestrateApi.ts` with:

```typescript
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface StartOrchestrateResponse {
  session_id: string;
  status: JobStatus;
  status_url: string;
  events_url: string;
}

export interface OrchestratorEvent {
  session_id: string;
  seq: number;
  type:
    | 'pipeline.started'
    | 'stage.started'
    | 'stage.completed'
    | 'stage.loopback'
    | 'pipeline.completed'
    | 'pipeline.failed'
    | 'pipeline.cancelled';
  stage: string;
  status: string;
  message: string;
  terminal: boolean;
  timestamp: string;
  data: Record<string, unknown>;
}

export async function startOrchestrate(
  idea: string,
): Promise<StartOrchestrateResponse> {
  const response = await fetch('/api/orchestrate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idea }),
  });
  if (!response.ok) {
    throw new Error(`orchestrate failed: ${response.status}`);
  }
  return response.json() as Promise<StartOrchestrateResponse>;
}

export async function cancelOrchestrate(sessionId: string): Promise<void> {
  const response = await fetch(
    `/api/orchestrate/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(`cancel failed: ${response.status}`);
  }
}

export function subscribeStream(
  response: StartOrchestrateResponse | string,
  onEvent: (event: OrchestratorEvent) => void,
  onTransportError: () => void = () => undefined,
): EventSource {
  const url = typeof response === 'string'
    ? `/api/orchestrate/stream?session_id=${encodeURIComponent(response)}`
    : response.events_url;
  const source = new EventSource(url);
  const eventTypes: OrchestratorEvent['type'][] = [
    'pipeline.started',
    'stage.started',
    'stage.completed',
    'stage.loopback',
    'pipeline.completed',
    'pipeline.failed',
    'pipeline.cancelled',
  ];
  const handle = (raw: MessageEvent<string>) => {
    onEvent(JSON.parse(raw.data) as OrchestratorEvent);
  };
  eventTypes.forEach((type) => source.addEventListener(type, handle as EventListener));
  source.onerror = onTransportError;
  return source;
}
```

- [x] **Step 2: Make workspace state accept the dashboard projection**

Replace `src/store/workspaceStore.ts` with:

```typescript
import { create } from 'zustand';
import type { DashboardData } from '../api/compilerDashboardApi';

interface WorkspaceState {
  sessionId: string | null;
  idea: string;
  project: Record<string, unknown>;
  requirements: unknown[];
  businessModel: DashboardData['business_model'];
  sop: DashboardData['sop'];
  review: Record<string, unknown>;
  presentation: Record<string, unknown>;
  risk: DashboardData['risk'];
  stages: Record<string, string>;
  log: { stage: string; msg: string }[];
  set: (patch: Partial<WorkspaceState>) => void;
  pushLog: (stage: string, msg: string) => void;
  setStage: (stage: string, status: string) => void;
  applyDashboard: (dashboard: DashboardData) => void;
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  sessionId: null,
  idea: '',
  project: {},
  requirements: [],
  businessModel: {},
  sop: {
    sops: [],
    _citation_coverage: { coverage: 0, covered: 0, total: 0, flagged: [] },
  },
  review: {},
  presentation: {},
  risk: {
    overall_score: null,
    gate: { decision: 'PENDING', reason: '' },
    coverage: { total: 0, covered: 0, coverage_pct: 0, uncovered_ids: [] },
    risks: [],
  },
  stages: {},
  log: [],
  set: (patch) => set(patch),
  pushLog: (stage, msg) => set((state) => ({
    log: [...state.log, { stage, msg }],
  })),
  setStage: (stage, status) => set((state) => ({
    stages: { ...state.stages, [stage]: status },
  })),
  applyDashboard: (dashboard) => set({
    businessModel: dashboard.business_model,
    sop: dashboard.sop,
    risk: dashboard.risk,
  }),
}));
```

- [x] **Step 3: Remove the completion timer and fetch the dashboard on terminal success**

In `src/components/UnifiedWorkspace.tsx`, keep the dashboard import and replace the existing orchestrator import with:

```typescript
import { fetchCompilerDashboard } from '../api/compilerDashboardApi';
import {
  cancelOrchestrate,
  startOrchestrate,
  subscribeStream,
  type OrchestratorEvent,
} from '../api/orchestrateApi';
```

Read `applyDashboard` from the store:

```typescript
const applyDashboard = useWorkspace((state) => state.applyDashboard);
```

Replace the compile-mode subscription and `setTimeout` block with:

```typescript
        let source: EventSource | null = null;
        source = subscribeStream(
          res,
          (event: OrchestratorEvent) => {
            const status = event.status || 'running';
            setPipelineStages((previous) => ({
              ...previous,
              [event.stage]: status,
            }));
            addLog(
              'stage',
              `[${event.stage}] ${event.type}${event.message ? `: ${event.message}` : ''}`,
            );

            if (!event.terminal) return;
            source?.close();
            setCompiling(false);

            if (event.type === 'pipeline.completed') {
              void fetchCompilerDashboard(res.session_id)
                .then((dashboard) => {
                  applyDashboard(dashboard);
                  setDashData(dashboard);
                  addLog('result', 'Pipeline completed');
                })
                .catch((dashboardError: unknown) => {
                  const message = dashboardError instanceof Error
                    ? dashboardError.message
                    : 'Dashboard request failed';
                  setError(message);
                  addLog('error', message);
                })
                .finally(() => setLoading(false));
              return;
            }

            const message = event.message || `Pipeline ended with ${event.status}`;
            setError(message);
            addLog('error', message);
            setLoading(false);
          },
          () => {
            addLog('system', 'Event stream disconnected; browser will retry');
          },
        );
```

Delete the fixed 30-second timer completely. Do not mark transport disconnect as pipeline failure because native EventSource reconnects automatically.

Replace `PipelineProgress`'s local-only cancel handler with:

```typescript
onCancel={() => {
  if (!sessionId) return;
  addLog('system', 'Cancellation requested');
  void cancelOrchestrate(sessionId).catch((cancelError: unknown) => {
    const message = cancelError instanceof Error
      ? cancelError.message
      : 'Cancellation request failed';
    setError(message);
    addLog('error', message);
  });
}}
```

Do not clear `loading` or `compiling` in this handler. The `pipeline.cancelled` terminal event owns the final UI transition.

- [x] **Step 4: Run TypeScript verification**

Run:

```powershell
npm run check
```

Expected: command exits with code 0.

- [x] **Step 5: Run backend regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator tests\api\test_compiler_dashboard.py tests\api\test_dashboard_evaluation.py tests\api\test_dashboard_evolution.py tests\api\test_dashboard_trusted_audit.py -q
```

Expected: all selected tests pass.

- [x] **Step 6: Perform one end-to-end mock smoke test**

Start the backend:

```powershell
$env:LLM_PROVIDER='mock'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
npm run dev -- --host 127.0.0.1
```

Open the Vite URL, select Compiler, submit a short structured PRD, and verify all of the following:

- Progress is driven by received stage events.
- The UI does not complete at a fixed 30-second boundary.
- The EventSource connection closes after `pipeline.completed`.
- Risk, coverage, audit and evaluation panels render from the dashboard response.
- A forced planner exception produces an error terminal event and leaves no infinite spinner.

- [ ] **Step 7: Commit the frontend lifecycle unit**

```powershell
git add src/api/orchestrateApi.ts src/components/UnifiedWorkspace.tsx src/store/workspaceStore.ts
git commit -m "feat(workspace): render orchestrator terminal results"
```

---

### Task 7: Phase 1 Regression Gate and Documentation Sync

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md` only if implementation exposed a factual contract correction
- Run: focused and collection test gates

- [x] **Step 1: Document the canonical lifecycle endpoints**

Add a concise section to `README.md` after Quick Start:

```markdown
## Orchestrator lifecycle

- `POST /api/orchestrate` creates a queued analysis and returns status/event URLs.
- `GET /api/orchestrate/{session_id}` returns the persisted lifecycle state.
- `DELETE /api/orchestrate/{session_id}` requests cooperative cancellation.
- `GET /api/orchestrate/{session_id}/events` streams ordered SSE events and closes at the terminal event.
- `GET /api/orchestrate/dashboard/{session_id}` returns the completed analysis projection.

The `/api/orchestrate/stream?session_id=...` endpoint is a temporary compatibility alias.
```

- [x] **Step 2: Run the Phase 1 test gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator tests\api\test_compiler_dashboard.py tests\api\test_dashboard_evaluation.py tests\api\test_dashboard_evolution.py tests\api\test_dashboard_trusted_audit.py -q
npm run check
```

Expected: both commands exit with code 0.

- [x] **Step 3: Confirm full-suite collection and record pre-existing blockers separately**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected for Phase 1: no new collection errors. The current baseline error from `tests/test_repositories.py` importing deleted `app.core.cache_service` is outside this phase; it must remain the only collection blocker until the Delivery and Cleanup plan repairs compatibility imports.

- [x] **Step 4: Run the placeholder and contract consistency scan**

Run:

```powershell
$patterns = @('T' + 'BD', 'T' + 'ODO', 'implement' + ' later', 'fill' + ' in')
Select-String -Path docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md,docs/superpowers/plans/2026-07-19-orchestrator-lifecycle-phase1.md -Pattern $patterns
rg -n "pipeline\.completed|pipeline\.failed|pipeline\.cancelled" app/orchestrator src/api/orchestrateApi.ts
```

Expected: the placeholder scan prints no matches; event names appear consistently in backend and frontend contracts.

- [ ] **Step 5: Commit documentation and gate results**

```powershell
git add README.md docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md docs/superpowers/plans/2026-07-19-orchestrator-lifecycle-phase1.md
git commit -m "docs: define orchestrator lifecycle contract"
```

---

## Phase 1 Definition of Done

- [x] `POST /api/orchestrate` returns HTTP 202 with status and event URLs.
- [x] Every job reaches exactly one persisted terminal status.
- [x] Success, failure and cancellation emit exactly one terminal event.
- [x] Events have strictly increasing per-session sequence numbers.
- [x] Reconnecting with `after` replays retained events.
- [x] Two subscribers receive identical event sequences.
- [x] The React Workspace has no fixed completion timer.
- [x] Completed jobs fetch and render the dashboard projection.
- [x] Failed jobs stop the spinner and show a safe error.
- [x] Existing orchestrator and dashboard tests pass.
- [x] `npm run check` passes.

## Self-Review

**Spec coverage:** Tasks 1-5 cover lifecycle, event ordering, replay, fan-out, task retention and HTTP discovery. Task 6 closes the frontend result loop. Task 7 documents and gates the phase.

**Scope discipline:** The plan does not migrate BusinessRuntime, database backends, authentication or deployment. Each remains an explicit subproject in the design Spec.

**Type consistency:** Backend `JobStatus` values match frontend `JobStatus`; backend `EventType` values match the frontend event union; terminal event names are identical across engine, API and UI.

**Rollback:** Each task is independently revertible. The compatibility `/stream` route remains available, existing dashboard payloads are unchanged, and no database columns are added.
