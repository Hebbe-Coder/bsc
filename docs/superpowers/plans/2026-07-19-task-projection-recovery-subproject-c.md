# Task Projection And Restart Recovery Subproject C Implementation Plan

**Goal:** Persist the orchestrator task projection required for status inspection and make interrupted in-process jobs recover deterministically at service startup.

**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

---

## Scope

This is the third implementation slice of Subproject C.

### In This Slice

- Safely migrate `agent_project_drafts` with current stage, error, event sequence and lifecycle timestamp fields.
- Advance the task projection whenever either orchestrator engine publishes an event.
- Persist stable, user-safe failure metadata for legacy and BusinessRuntime pipelines.
- Recover `running` jobs during FastAPI startup as failed jobs with `worker_restarted` and a terminal event.
- Include task projection metadata in the orchestrator status endpoint.

### Deferred

- PostgreSQL migration parity and a versioned migration runner.
- Durable queue execution, worker ownership or cross-process task cancellation.
- Tenant, project and session authorization boundaries.
- Artifact repository normalization and retention policies.

## Exit Criteria

- Existing Draft tables gain projection columns without data loss.
- Status reads expose current stage, event sequence, errors and lifecycle timestamps.
- Both execution engines persist their final sequence and terminal metadata.
- Startup recovery changes only orphaned `running` jobs and produces a terminal `pipeline.failed` event with `worker_restarted`.
