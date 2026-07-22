# P9 - A/B/C/D Integration, Recovery And Release Implementation Plan

**Goal:** Prove the entire A/B/C/D knowledge-growth product works end to end under isolated fixtures and supported runtime profiles, then publish only claims backed by test or runtime evidence.

**Architecture:** P9 is an integration and release gate, not a feature escape hatch. It composes P1-P8 through temporary projects/Vaults and real API, Worker/Beat, Redis, PostgreSQL and browser environments where available. Defects are fixed only within the owning contract; a failing E2E test must not be bypassed with fixtures or success inference.

**Depends on:** P1-P8.
**PRD coverage:** all FRs, reliability/performance/security and all 20 acceptance scenarios.

## Owned Files

**Create:** `tests/integration/test_abcd_growth_e2e.py`, `tests/integration/test_abcd_growth_isolation.py`, `tests/integration/test_abcd_growth_recovery.py`, `tests/integration/test_abcd_growth_postgres.py`, `tests/integration/test_abcd_growth_browser.md`, fixtures under `tests/fixtures/abcd_growth/`, and release evidence in the worklog.

**Modify:** `docker-compose.yml`, `.github/workflows/**`, `.env.example`, release notes and documentation only when integration evidence identifies a concrete configuration defect.

**Forbidden:** Modifying `D:\bsc` user content, staging runtime DB files, changing P1-P8 domain contracts to make tests pass, claiming unavailable Horizon/Feishu/LLM/Docker execution, or changing Artifact Graph/orchestrator/MCP semantics.

## Required Isolated Fixture

Create two disposable projects with distinct Vault mappings, profiles, `AGENTS.md`, sources, methods, outputs and credentials. Project A contains a high-value source and accepted/rejected output cycle. Project B contains similarly named but conflicting material. Include a binary PDF/presentation, a Feishu-shaped revision fixture, Horizon staged artifacts, contradictory sources, one user-authored weekly file and one failed evaluator case.

## Task 1: Full A-to-D Lifecycle

- [x] Write failing E2E tests for capture, hash/dedup, profile-bound triage, eligible source, Wiki proposal/publication, citation/graph, output registration, evaluation, feedback, method proposal/publication and context-backed SOP/content output.
- [x] Prove output feedback routes to a governed Wiki/method proposal or failure case and never directly changes A/B/C authority.
- [x] Verify all records include project, revision, run/context/method/evidence ancestry and are queryable through P7.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_abcd_growth_e2e.py -q`.

## Task 2: Isolation, Security And Compatibility

- [x] Write failing tests for reader/admin/system roles, cross-project IDs/paths/graph edges, symlink escape, raw write, secret redaction, untrusted instructions, bounded payload and cyclic lineage.
- [x] Assert existing Wiki, Artifact Graph, Skill, orchestrator lifecycle, MCP initialize/tools/list/call, HTTP/SSE replay and legacy no-Vault generation behavior.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_abcd_growth_isolation.py tests/mcp/test_growth_http_contract.py tests/mcp/test_wiki_tools.py tests/test_mcp_compatibility.py -q`.

## Task 3: Automation And Recovery

- [x] Write failing tests for duplicate daily/weekly triggers, changed input revision, user-file protection, `distillations/` recursion exclusion, abandoned run, worker restart, Beat replay, missing Redis and disabled scheduler.
- [x] Run the same daily and Friday jobs twice, inspect idempotency/event/manifest records and assert exactly one logical output set per input hash.
- [x] Restart API/Worker/Beat and verify schedule, run, context, output and SSE history remain queryable without duplicate publication.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_abcd_growth_recovery.py -q`.

## Task 4: PostgreSQL And Docker Proof

- [x] Add PostgreSQL schema/lifecycle/isolation tests using the supported compose profile and temporary database; compare SQLite outcomes for state transitions and idempotency.
- [x] Run `docker compose config` and the required profile only after environment checks. Verify API health, Redis `PONG`, Worker task, Beat dispatch, shared Vault/database mount and graceful restart.
- [x] Exercise disabled/missing dependency mode separately and record `unavailable` rather than treating config validation as live success.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_abcd_growth_postgres.py -q` and `docker compose --profile full config`.

## Task 5: Browser And Accessibility Acceptance

- [x] Start frontend/API against real fixture data and execute P8 desktop journey through A/B/C/D/Review, reader, source inspector, diff, method/output feedback, trends, graph and weekly distillation.
- [x] Execute narrow mobile journey: stage tabs, asset selection, inspector drawer, error/permission/empty/unavailable states, keyboard/focus and reduced motion.
- [x] Assert no fake data on API failure, no text/control overlap, no horizontal overflow, chart/graph nonblank pixels and correct project selection.
- [x] Record browser command, viewport, test result and screenshot paths in `tests/integration/test_abcd_growth_browser.md` and the worklog.

## Task 6: Performance, Regression And Release Gate

- [x] Measure list metadata p95 target below 300 ms for 10,000 project records on supported local profile; enforce page and graph bounds (default 500 nodes/edges per slice).
- [x] Run focused integration suites, all Python tests, `npm run check`, `npm run lint`, `npm run build`, `npm run test:frontend`, `git diff --check` and configured security checks.
- [x] Confirm only intended source/test/config/docs files are staged; exclude `app/bsc_cloud.db`, `app/bsc_cloud.db-shm`, `.agents/`, caches, generated output, downloaded archives, and `D:\bsc`.
- [x] Publish a release note with feature flags, `OBSIDIAN_VAULT_ROOT`, Horizon/Feishu/model/Celery settings, migrations, schedules, rollout, alarms, unavailable boundaries and rollback.

## Acceptance Criteria

- All 20 PRD scenarios pass in disposable fixtures or are explicitly marked external/unavailable with evidence; no scenario is silently skipped.
- A/B/C/D state, provenance, lineage, permissions, quality and feedback are durable and project-isolated across restart.
- Daily/Friday automation, Docker Worker/Beat, PostgreSQL, MCP/API and browser workflows meet their gates.
- Existing accepted BSC behavior remains compatible and no user Vault/runtime data is modified by release verification.
- Release claims distinguish implemented code, tested fixture, live runtime evidence and external configuration boundary.

## Rollback Strategy

Pause schedules and disable growth flags first. Roll back P8, P7, P6, P5, P4, P3, P2 and P1 code in reverse order only through additive-safe deployment. Retain source, Wiki, method, output, evaluation, feedback and audit records; preserve user-authored Vault files and prior managed revisions.

## Required Handoff

Append the final worklog entry with changed files, migration IDs, test counts, Docker/PostgreSQL/browser evidence, unavailable dependencies, performance measurements, compatibility statement, release commit scope and rollback result. The final status may be complete only when the execution index and all plan checkboxes match actual evidence.
