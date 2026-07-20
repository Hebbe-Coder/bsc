# Durable Event Log Subproject C Work Log

**Started:** 2026-07-19
**Plan:** `docs/superpowers/plans/2026-07-19-durable-event-log-subproject-c.md`
**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

## Scope Snapshot

- Persist the ordered orchestrator event envelope in SQLite.
- Keep SSE fan-out in process while replaying reconnect history from durable storage.

## Task Board

| Task | Status | Evidence | Notes |
|---|---|---|---|
| SQLite event repository | Completed | `tests/orchestrator/test_event_store.py` | Stores the complete event envelope under a per-session primary key |
| Restart replay | Completed | `tests/orchestrator/test_event_store.py` | A replacement bus replays persisted terminal history |
| Sequence continuation | Completed | `tests/orchestrator/test_event_store.py` | New events continue at the durable maximum sequence number |
| API bus integration | Completed | `tests/orchestrator/test_event_store.py` | Global orchestrator bus uses the configured SQLite connection |
| SSE regression gate | Completed | `tests/orchestrator/test_sse.py` | In-memory replay, fan-out and terminal close semantics remain intact |

## Progress Notes

### 2026-07-19 - Durable SSE Event History

- Added `SQLiteEventStore` with an `orchestrator_events` table keyed by `(session_id, seq)`.
- `SessionEventBus` now accepts an optional event store. Before its first event for a session it restores the maximum persisted sequence, persists each new event before fan-out, and reads durable history for replay.
- `/api/orchestrate` now creates its global event bus with `SQLiteEventStore(get_db())`, so its event log uses the same configured SQLite path as the existing task projection.
- In-memory-only buses remain supported for isolated tests and local callers.

## Verification

- `python -m pytest tests/orchestrator/test_event_store.py tests/orchestrator/test_sse.py -q`
  - Result: `8 passed`
- `python -m pytest tests/orchestrator/test_api.py tests/orchestrator/test_lifecycle.py tests/orchestrator/test_runtime_engine.py -q`
  - Result: `18 passed`, one existing Starlette deprecation warning
- `python -m pytest tests/test_agent_runtime_convergence.py tests/test_database_config_convergence.py -q`
  - Result: `10 passed`, one existing Starlette deprecation warning
- Focused persistence, lifecycle, runtime and dashboard regression suite
  - Result: `65 passed`, one existing Starlette deprecation warning
- `python -m compileall -q app/orchestrator app/api/orchestrate.py`
  - Result: passed
- `npm run check`
  - Result: passed

## Known Baseline / Remaining Scope

- `tests/orchestrator/test_agents.py` has three pre-existing mock Agent contract failures: planner and architect payload keys are absent, and reviewer approval is false. The event store is not involved in those code paths.
- Cross-backend migrations, durable task/artifact repositories, tenant isolation, restart job recovery and distributed fan-out remain outside this slice.
