# Persistence And Security Subproject C Work Log

**Started:** 2026-07-19
**Plan:** `docs/superpowers/plans/2026-07-19-persistence-security-subproject-c.md`
**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

## Scope Snapshot

- Remove destructive migration behavior from the orchestration task projection store.
- Make SQLite storage paths honor the same configured `DB_PATH` value across legacy and abstracted users.

## Task Board

| Task | Status | Evidence | Notes |
|---|---|---|---|
| Non-destructive ProjectDraft migration | Completed | `tests/orchestrator/test_state.py` | Missing columns are added with `ALTER TABLE`; existing rows and unknown columns remain intact |
| Unsafe schema rejection | Completed | `tests/orchestrator/test_state.py` | Tables without a `session_id` primary key fail clearly and are never dropped |
| SQLite path convergence | Completed | `tests/test_database_config_convergence.py` | Legacy `app.db` and `SQLiteBackend` now use the same `DB_PATH` resolver |
| Focused regression gate | Completed | 57 passed + TypeScript/Python checks | Lifecycle, runtime, dashboard and configuration tests passed |

## Progress Notes

### 2026-07-19 - Safe Task-State Migration

- Replaced `DROP TABLE IF EXISTS agent_project_drafts` behavior with incremental SQLite column additions.
- Preserved existing rows and legacy columns during migration.
- Updated `ProjectDraft.from_row()` to ignore historical columns that are not part of the current projection model.
- Added a fail-closed check for the `session_id` primary key, because SQLite cannot safely add or repair that constraint in place.

### 2026-07-19 - Database Path Convergence

- Added `resolve_sqlite_path()` to `app.core.database` as the configured source of truth for SQLite paths.
- Updated both `SQLiteBackend` and legacy `app.db.get_db()` to use it.
- Default behavior remains compatible with `app/bsc_cloud.db`; configured absolute and relative `DB_PATH` values now work consistently.

## Verification

- `python -m pytest tests/test_database_config_convergence.py tests/test_agent_runtime_convergence.py tests/orchestrator/test_state.py tests/orchestrator/test_api.py tests/orchestrator/test_engine.py tests/orchestrator/test_lifecycle.py tests/orchestrator/test_runtime_engine.py tests/api/test_compiler_dashboard.py tests/api/test_dashboard_evaluation.py tests/api/test_dashboard_evolution.py tests/api/test_dashboard_trusted_audit.py -q`
  - Result: `57 passed`, 1 existing Starlette deprecation warning
- `python -m compileall -q app scripts`
  - Result: passed
- `npm run check`
  - Result: passed

## Known Baseline / Remaining Scope

- `tests/test_core_modules.py` currently has 14 unrelated failures against the existing `LLMService` API contract. The failures concern pre-existing methods and mock payload shape not changed in this slice.
- Remaining Subproject C work is deliberately deferred to later slices: cross-backend migrations, durable event/artifact repositories, tenant isolation, authentication and production readiness checks.
