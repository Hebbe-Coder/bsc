# Durable Event Log Subproject C Implementation Plan

**Goal:** Make orchestrator SSE events durable across process restarts while preserving the existing in-memory fan-out behavior.

**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

---

## Scope

This is the second implementation slice of Subproject C.

### In This Slice

- Persist ordered orchestrator events in the configured SQLite database.
- Resume per-session event sequence numbers from durable storage after a restart.
- Replay persisted events, including a terminal event, to reconnecting SSE subscribers.
- Wire the `/api/orchestrate` process-wide event bus to the durable event store.

### Deferred

- A versioned cross-backend migration runner for SQLite and PostgreSQL.
- Durable task, artifact and tenant repositories.
- Restart recovery that marks orphaned running jobs as `worker_restarted`.
- Cross-process event fan-out and a distributed task queue.
- Tenant authorization and authenticated production SSE access.

## Exit Criteria

- Recreating `SessionEventBus` with the same SQLite connection replays the prior terminal event history.
- The first event after recreating a bus has the next durable sequence number.
- Existing in-memory replay, multiple subscriber and terminal-close behavior remains unchanged.
- `/api/orchestrate` constructs its global bus with the configured SQLite event store.
