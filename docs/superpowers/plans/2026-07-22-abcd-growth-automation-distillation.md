# P6 - Growth Automation And Dual-Track Distillation Implementation Plan

**Goal:** Run truthful, project-scoped daily and weekly growth maintenance with durable scheduling, idempotent input manifests, atomic managed files, retry/recovery and the required Codex automation prompt contract.

**Architecture:** Reuse the existing `KnowledgeScheduler`, Celery Worker/Beat and Redis deployment. Add growth job types after P5 context contracts. Persist desired schedules and claim keys in BSC; Celery performs work only when available. The daily 17:00 job writes an incremental digest. Friday 17:30 writes the managed six-file weekly bundle under `distillations/每周蒸馏/<YYYY-Www>/`.

**Depends on:** P5.
**Parallel with:** P7.
**PRD coverage:** FR-11, reliability/operations; AC 13-15 and 19.

## Owned Files

**Create:** `app/knowledge/growth_scheduler.py`, `app/knowledge/growth_distillation.py`, `app/knowledge/codex_automation_prompt.py`, `app/tasks/growth_tasks.py`, `tests/knowledge/test_growth_scheduler.py`, `tests/knowledge/test_growth_distillation.py`, `tests/knowledge/test_codex_automation_prompt.py`, and `tests/integration/test_growth_celery.py`.

**Modify:** `app/knowledge/scheduler.py`, `app/knowledge/distillation.py`, `app/tasks/knowledge_tasks.py`, `app/core/celery_app.py`, `app/core/config.py`, `app/config_types.py`, `docker-compose.yml`, `.env.example` and schedule API wiring only for growth job registration.

**Forbidden:** Treating a local Codex automation prompt as proof that BSC executed, reading prior `distillations/` as new evidence, overwriting user-authored files, changing existing Wiki distillation semantics, or making API/Beat process act as the scheduler.

## Frozen Public Contracts

- Daily job: project-scoped, `17:00`, `Asia/Shanghai`, incremental A/B/C/D changes, contradictions, candidates, actions and evidence index.
- Weekly job: Friday `17:30`, `Asia/Shanghai`, after daily completion, output `00-本周总结.md`, `01-知识行动.md`, `02-内容创作.md`, `03-下周上下文包.md`, `04-方法迭代.md`, and `manifest.json` under `distillations/每周蒸馏/<YYYY-Www>/`.
- Existing repositories with mojibake historical path names remain readable; new managed paths use the PRD's canonical names.
- Input manifest excludes `distillations/`, records source cutoff and hash, and is immutable for the run.
- Same project/job/period/cutoff/input hash is one logical run; changed input creates a managed revision after preserving the prior generated revision.
- A managed file is overwritten only when its manifest/ownership marker proves it was generated; an unmarked user-authored file is never overwritten.

## Task 1: Schedule Intent And Cadence

- [x] Write failing tests for timezone/cadence, Friday ordering, pause/resume, project policy, duplicate claim, manual run and scheduler-disabled availability.
- [x] Implement growth schedule defaults and persisted schedule intent without changing existing scheduler job semantics.
- [x] Ensure daily and weekly schedules use separate idempotency keys and weekly readiness checks against the daily run.
- [x] Generate the Codex automation prompt/config artifact that says how to inspect `D:\bsc`, run the project-scoped distillation, save the summary and report unavailable state; it must not claim it executed.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_scheduler.py tests/knowledge/test_scheduler.py -q`.

## Task 2: Incremental And Weekly Distillation

- [x] Write failing tests for no-change no-op, changed input, daily digest, weekly six-file bundle, source cutoff, contradictions, output feedback, prior revision archive, user-file protection and recursive-input exclusion.
- [x] Build incremental input from A/B/C/D/review records plus bounded P5 context; do not treat prior generated distillation as source evidence.
- [x] Write all files to a temporary sibling directory, validate manifest/hash/reference paths, then atomically publish the directory.
- [x] Include evidence-backed knowledge actions, content candidates with claim/citation pairs, next-week context, method iteration and a machine-readable manifest.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_distillation.py tests/knowledge/test_distillation.py -q`.

## Task 3: Celery Worker/Beat And Recovery

- [x] Write failing tests for task registration, retryable/permanent errors, abandoned run recovery, duplicate worker delivery, Redis missing, disabled Celery and restart replay.
- [x] Implement growth task functions that load persisted run/schedule IDs, claim before work, emit ordered events and distinguish unavailable from failed.
- [x] Add Beat reconciliation using persisted schedules; API and synchronous Celery fallback never present recurring schedules as active.
- [x] Validate Docker profile has shared Vault/database mounts and required env without forcing image pulls in unit tests.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_growth_celery.py tests/knowledge/test_knowledge_tasks.py -q` and `docker compose --profile full config`.

## Task 4: Metrics And Automation Evidence

- [x] Persist queue delay, runtime, retry count, duplicate/no-op count, input count/hash, output paths, freshness and failure category.
- [x] Ensure summary files report processed projects, source cutoff, input count, outputs and failures truthfully.
- [x] Test automation prompt/output injection safety and secret redaction.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_codex_automation_prompt.py tests/knowledge/test_growth_scheduler.py tests/knowledge/test_growth_distillation.py -q`.

## Task 5: Verification And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_scheduler.py tests/knowledge/test_growth_distillation.py tests/knowledge/test_codex_automation_prompt.py tests/integration/test_growth_celery.py tests/knowledge/test_distillation.py -q`.
- [x] Run `git diff --check` and `git status --short`.
- [x] Record Docker/Redis/Beat real evidence or the exact external limitation; never mark live scheduling passed from config output alone.

## Acceptance Criteria

- Repeated daily/weekly triggers with identical input create one auditable output set; changed input preserves a prior managed revision.
- Daily 17:00 and Friday 17:30 are project-scoped and timezone-correct; Friday does not race daily writes.
- Distillation files are atomic, evidence-linked, non-recursive and cannot overwrite user-authored content.
- Worker/Beat restart and retry recover without duplicate logical runs; disabled dependencies report unavailable.
- The Codex prompt is usable as an automation instruction but its generated report distinguishes requested, attempted, completed and unavailable work.

## Rollback Strategy

Pause growth schedules, stop Beat growth tasks and keep already-published distillation revisions. Disable the prompt/config integration separately. Existing P5 context and 2026-07-21 distillation behavior remains available.

## Required Handoff

Provide P7/P8 with schedule/run event schemas, output path/manifest contract, freshness metrics, unavailable semantics, Docker env requirements and the exact automation prompt artifact. Include one no-op and one changed-input evidence set.
