# P5 - Knowledge Automation And Weekly Distillation Implementation Plan

**Goal:** Run source synchronization, Horizon capture, Wiki maintenance, quality checks, and dual-track weekly distillation through durable schedules without pretending synchronous/local execution is a background scheduler.

**Architecture:** Reuse the existing optional Celery/Redis deployment model. Add a knowledge task module and Celery Beat only when real Celery is enabled. Persist desired cadence and run state in P1 tables, and claim a database idempotency key before execution so Beat duplication, retries, and manual triggers cannot duplicate weekly artifacts.

**Depends on:** P4. **Parallel after P4:** P6 and P7. **Do not modify:** P1-P4 contracts, raw sources, existing orchestrator worker behavior, MCP routes, or frontend components.

## Owned Files

**Create:** `app/tasks/knowledge_tasks.py`, `app/knowledge/scheduler.py`, `app/knowledge/distillation.py`, `tests/knowledge/test_scheduler.py`, `tests/knowledge/test_knowledge_tasks.py`, `tests/knowledge/test_distillation.py`, and `tests/integration/test_knowledge_celery.py`.

**Modify:** `app/core/celery_app.py`, `app/core/config.py`, `app/config_types.py`, `docker-compose.yml`, `app/knowledge/wiki_service.py`, and `.env.example` when present.

## Job Contract

| Job type | Idempotency key | Output |
|---|---|---|
| `source_sync` | project + source scan cutoff | source sync report/run |
| `horizon_capture` | project + Horizon cursor/run | captured source records |
| `wiki_maintenance` | project + ordered source hashes | proposal/gate run |
| `knowledge_lint_eval` | project + published revision | lint/eval report |
| `weekly_distillation` | project + ISO week + source cutoff | three versioned Markdown outputs |

Every task records `KnowledgeRun` state and retry lineage. A schedule can be enabled only with configured vault, permissions, and real scheduler capability. In synchronous/local mode it returns `unavailable`; it never claims a future schedule is active.

## Task 1: Scheduler Policy And Persistence

- [x] Write failing tests for schedule/cron/timezone validation, project isolation, next-run calculation, pause/resume, duplicate claim, and disabled scheduler result.
- [x] Implement `KnowledgeScheduler` to persist schedule intent, calculate next run, and claim a run transactionally before enqueueing.
- [x] Permit only allowlisted job types and bounded frequency. Require project vault/source policy for source-dependent jobs.
- [x] Route manual `run_now` through the same claim/run path so it cannot bypass audit, idempotency, or P4 gates.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_scheduler.py -q`.

## Task 2: Celery Task Registration And Beat

- [x] Extend Celery autodiscovery for `app.tasks.knowledge_tasks` with JSON-safe arguments: project ID, run ID, and schedule ID.
- [x] Implement task functions that load persisted runs, invoke P2/P3/P4 services, set terminal status, and distinguish retryable from permanent failures.
- [x] Add `celery-beat` to `docker-compose.yml` with the worker's data mounts and environment; do not make the API process the scheduler.
- [x] Dispatch persisted schedules through documented reconciliation/Beat work, not source-coded user schedules.
- [x] Keep `SyncCelery` truthfully unavailable for recurring scheduling and prevent false `last_run_at` updates.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_tasks.py -q` and `docker compose --profile full config`.

## Task 3: Weekly Distillation

- [x] Write failing tests for deterministic week path, source cutoff, duplicate retry, no eligible source, evidence links, no content candidates, and write conflict.
- [x] Build distillation context from published pages, source changes, decisions, gate/eval findings, and project rules with a bounded P3 context pack.
- [x] Write `knowledge-action.md` with changed beliefs, contradictions, unresolved questions, source-backed actions, and source cutoff.
- [x] Write `content-creation.md` with substantiated themes, audience/angle, claim/citation pairs, reusable excerpts, and open research gaps; suggestions must not be presented as verified facts.
- [x] Write `context-pack.md` with compact reusable context, revision/source references, and omissions. Publish all three under `distillations/YYYY-Www/` with atomic write guards.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_distillation.py -q`.

## Task 4: Failure, Recovery, And Operations

- [x] Classify configuration, policy, transient dependency, extraction, compiler, gate, and write-conflict failures with actionable status and retryability.
- [x] Recover only abandoned running jobs; never duplicate a published period.
- [x] Emit metrics for queue delay, runtime, retry count, success/skipped/unavailable state, and distillation freshness.
- [x] Add Redis/Celery integration proof that one scheduled project/week/cutoff produces exactly one auditable run/output set.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_knowledge_celery.py -q`.

## Task 5: Verification And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge -q`, `docker compose --profile full config`, and `git diff --check`.
- [x] Record deployment requirements, disabled-mode behavior, and real integration results in the worklog.

## Acceptance, Rollback, Handoff

- One project/week/cutoff creates one dual-track distillation plus context pack even under retry.
- Worker/Beat failure leaves published Wiki/distillation intact and exposes a failed run.
- Disabled Celery does not report schedules as running; manual work remains auditable.
- Rollback pauses schedules/stops Beat and preserves user files and audit data.
- Handoff P6/P7 with schedule/run/distillation/availability contracts and P8 with Docker proof/configuration.
