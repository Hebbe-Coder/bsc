# Task Projection And Restart Recovery Subproject C Work Log

**Started:** 2026-07-19
**Plan:** `docs/superpowers/plans/2026-07-19-task-projection-recovery-subproject-c.md`
**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

## Scope Snapshot

- Persist the task-control projection independently from business output segments.
- Recover work interrupted by an in-process worker restart.

## Task Board

| Task | Status | Evidence | Notes |
|---|---|---|---|
| Projection schema migration | Completed | `tests/orchestrator/test_state.py` | Adds fields with the existing non-destructive SQLite migration path |
| Event projection updates | Completed | `tests/orchestrator/test_lifecycle.py`, `tests/orchestrator/test_runtime_engine.py` | Both engines record stage and final durable event sequence |
| Stable terminal metadata | Completed | `tests/orchestrator/test_lifecycle.py`, `tests/orchestrator/test_runtime_engine.py` | Failed jobs store safe error codes and messages; terminal jobs record completion time |
| Startup recovery | Completed | `tests/orchestrator/test_recovery.py` | Running jobs become `worker_restarted` failures and emit a closing event |
| Status projection API | Completed | `tests/orchestrator/test_api.py` | Status response now includes stage, errors, sequence and timestamps |

## Progress Notes

### 2026-07-19 - Durable Task Projection

- Extended `ProjectDraft` with `current_stage`, `error_code`, `error_message`, `event_seq`, `created_at` and `completed_at`.
- Preserved older rows by extending the existing additive migration and backfilling `created_at` from the historical update timestamp where possible.
- Added `record_event()` so task projections advance only with newly published event sequences; terminal events retain the last active stage.
- Legacy and BusinessRuntime engines now persist their event projection after publishing and write safe terminal failure metadata.

### 2026-07-19 - Restart Recovery

- Added a recovery coordinator that finds only `running` jobs, marks them failed with `worker_restarted`, and emits a terminal `pipeline.failed` event.
- Registered recovery in the FastAPI lifespan after database initialization and covered the startup hook directly.

## Verification

- `python -m pytest tests/orchestrator/test_state.py tests/orchestrator/test_recovery.py tests/orchestrator/test_lifecycle.py tests/orchestrator/test_runtime_engine.py tests/orchestrator/test_api.py -q`
  - Result: `35 passed`, one existing Starlette deprecation warning
- `python -m compileall -q app/agent/state.py app/orchestrator app/api/orchestrate.py app/main.py`
  - Result: passed
- Focused persistence, lifecycle, runtime and dashboard regression suite
  - Result: `69 passed`, one existing Starlette deprecation warning
- `npm run check`
  - Result: passed

## Remaining Scope

- The current persistence remains SQLite-only and in-process. PostgreSQL parity, a durable worker queue, tenant isolation, artifact persistence and production authentication remain separate work.
