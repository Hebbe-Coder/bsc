# Persistence And Security Subproject C Implementation Plan

**Goal:** Replace destructive task-state schema handling with safe migrations and converge SQLite access through one configured path before introducing durable tenant, project and session persistence.

**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

---

## Scope

This is the first implementation slice of Subproject C.

### In This Slice

- Replace `ProjectDraftRepository` table recreation with non-destructive SQLite column migrations.
- Preserve existing draft rows and unknown legacy columns during migration.
- Fail clearly when the required `session_id` primary key is missing instead of attempting destructive repair.
- Make the legacy SQLite compatibility layer and `SQLiteBackend` resolve `DB_PATH` through one configuration helper.
- Add focused regression tests for migration safety and database-path convergence.

### Deferred

- A versioned cross-backend migration runner for SQLite and PostgreSQL.
- Durable job/event/artifact repository tables and restart recovery.
- Explicit `tenant_id` boundaries and authorization enforcement for orchestrator/session APIs.
- Production startup failure semantics for unavailable PostgreSQL and related dependencies.

## Exit Criteria For This Slice

- A legacy `agent_project_drafts` table with missing fields is upgraded without row or unknown-column loss.
- An unsafe table without `session_id` primary key is rejected without being dropped.
- Legacy and abstracted SQLite users resolve the same configured database path.
- Focused lifecycle/runtime/database tests pass.
