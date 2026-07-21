# P8 - Knowledge System Integration And Release Implementation Plan

**Goal:** Prove the complete LLM Wiki knowledge-growth system works from configured Vault and external source capture through governed publication, weekly distillation, APIs/MCP, browser workflows, Docker/Celery operation, recovery, and rollback.

**Architecture:** P8 is an integration/release plan, not a feature-building shortcut. It combines the merged P1-P7 contracts using isolated fixtures and real deployment dependencies where required. It may add test adapters, test fixtures, Docker configuration corrections, and release documentation, but cannot redesign prior domain/API contracts without a PRD update.

**Depends on:** P5, P6, P7
**Do not modify:** raw user Vault data, existing Artifact Graph semantics, unrelated runtime database files, or previously accepted orchestration/MCP behaviors.

## Owned Files

**Create:** `tests/integration/test_knowledge_wiki_e2e.py`, `tests/integration/test_knowledge_isolation.py`, `tests/integration/test_knowledge_recovery.py`, `tests/integration/test_knowledge_mcp_e2e.py`, `tests/integration/test_knowledge_sop_e2e.py`, test fixture Vault content under `tests/fixtures/knowledge_wiki/`, and release evidence in the worklog.

**Modify:** `docker-compose.yml`, `.github/workflows/**`, environment examples, and documentation only when an integration test identifies a concrete configuration defect. Do not add production behavior merely to make a test pass.

## Required End-To-End Fixture

Create two isolated temporary projects with distinct Vault mappings, rules, trusted-source policies, source notes, and evaluation cases. Project A includes a source that changes a process/control. Project B includes a similarly named but conflicting source. The fixture must prove selection by project scope, not simple name matching.

## Task 1: Core Knowledge Lifecycle E2E

- [ ] Configure project A Vault and initialize scaffold without overwriting supplied user `AGENTS.md`.
- [ ] Import an Obsidian source and normalized Horizon signal; demonstrate immutable source hashes and eligible policy state.
- [ ] Compile a multi-page proposal, run lint/evals, publish atomically, and verify overview/index/log/page metadata/citations/graph edges/source processed status.
- [ ] Attempt malformed citation, stale base revision, and failed evaluation proposals; verify all fail without partial published files.
- [ ] Roll back a published page through an auditable compensating proposal and verify graph/history consistency.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_knowledge_wiki_e2e.py tests/integration/test_knowledge_recovery.py -q`.

## Task 2: Isolation, Security, And MCP E2E

- [ ] Test project A credentials/API key/MCP scope cannot list/read/search/modify project B mapping, sources, pages, proposals, runs, graph, schedules, or distillations.
- [ ] Test path traversal, absolute paths, symlink escape, source raw-write attempt, invalid operation, event replay scope, and secret redaction.
- [ ] Start the real HTTP MCP adapter, run `initialize`, `tools/list`, and project-scoped Wiki tools, then verify mutable MCP calls create governed proposal/run state rather than unrestricted writes.
- [ ] Re-run current MCP HTTP/SSE and stdio compatibility tests to prove no regression.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_knowledge_isolation.py tests/integration/test_knowledge_mcp_e2e.py -q`.

## Task 3: SOP, Context, And Weekly Output E2E

- [ ] Compile a PRD/SOP for project A after publication. Verify context-pack ID, selected pages/sources, cited constraints, explicit assumptions, and absence of project B content.
- [ ] Compare against a no-vault project to ensure legacy compatibility and clear `knowledge_context_used` behavior.
- [ ] Run the weekly job twice for the same project/week/cutoff. Verify one durable output set, correct source cutoff, linked evidence, retry lineage, and both knowledge/action plus content-creation reports.
- [ ] Verify scheduler-disabled mode reports unavailable and manual execution still creates a normal auditable run.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_knowledge_sop_e2e.py tests/integration/test_knowledge_celery.py -q`.

## Task 4: Docker And Recovery Validation

- [ ] Validate compose configuration for backend, Redis, Celery Worker, and Celery Beat with shared database/Vault mounts and required environment variables.
- [ ] Bring up the required profile only after configuration checks pass. Execute source sync, maintenance, and distillation against a disposable fixture; record service health and terminal run records.
- [ ] Restart API and worker/beat services between runs. Verify completed runs, published revisions, schedules, and SSE replay remain queryable; no run is duplicated on recovery.
- [ ] Test a missing Redis/disabled Celery scenario separately and confirm truthful unavailable status without failed startup.
- [ ] Record exact Docker availability limitations if Docker Hub/network access prevents a real container run; do not mark this gate passed without evidence.

## Task 5: Browser And Accessibility Acceptance

- [ ] Start the frontend/backend against real fixture data and execute the P7 desktop journey: select project, read page, open citation/source, inspect proposal diff, observe run event, filter graph, and open weekly context pack.
- [ ] Execute mobile journey at a narrow viewport: switch panes, retain selection, inspect error/permission/empty states, and ensure no text/action overlaps.
- [ ] Verify keyboard navigation, visible focus, icon labels/tooltips, reduced motion, rendered chart/graph nonblank pixels, and no fake data shown during API failure.
- [ ] Capture screenshots only as verification artifacts; functional browser assertions are required before visual review.

## Task 6: Release Gate And Documentation

- [ ] Run focused integration suites, complete Python regression, `npm run check`, `npm run lint`, `npm run build`, `git diff --check`, and configured security/static checks.
- [ ] Confirm only intended source/docs/test/config files are staged; explicitly exclude `app/bsc_cloud.db`, `app/bsc_cloud.db-shm`, cache directories, generated graph output, and user Vault files.
- [ ] Update the worklog with results, test counts, Docker evidence, browser scenarios, known non-goals, and rollback verification.
- [ ] Prepare a release note that describes required configuration (`OBSIDIAN_VAULT_ROOT`, feature flags, Horizon and Celery settings), migration behavior, rollout sequence, and operational alarms.

## Execution Ledger (2026-07-21)

| Gate | Status | Evidence |
|---|---|---|
| Source-to-publish filesystem lifecycle | Complete | `tests/integration/test_knowledge_wiki_e2e.py` creates a mapped Vault, imports Obsidian and Horizon evidence, compiles a proposal, passes evaluation, publishes atomically, and verifies citations, revisions, graph edges, and processed sources. |
| Stale proposal, lint, evaluation, and compensation gates | Complete | `tests/knowledge/test_proposal_gate.py` and `tests/knowledge/test_wiki_lint.py` cover stale base revisions, missing baselines, processed-evidence compensating proposals, and append semantics. |
| Docker API/Redis/Celery/Beat proof | Complete | Local image build succeeded; `bsc-backend-app-8002` is healthy on port 8002, Redis returned `PONG`, and Beat dispatched `knowledge.reconcile_schedules` to the restarted Worker. |
| Full profile with Ollama and live LLM maintenance | Pending external configuration | The deployed Worker can execute scheduled jobs, but real maintenance requires an explicitly configured `KNOWLEDGE_WIKI_LLM_PROVIDER`; Ollama is intentionally not downloaded or started by this release proof. |
| Horizon sidecar live capture | Pending external configuration | The bounded client/import contract is tested; no production Horizon endpoint or credential has been configured. |
| Full browser proposal/run/weekly journey | Pending fixture data | Desktop and mobile workspace, graph filtering, real Vault/evidence state, and chart lifecycle are accepted. A safely seeded review/diff/distillation browser fixture is still required for every P8 interaction. |
| Role/MCP adversarial E2E | Pending dedicated fixtures | Existing API and HTTP contract regression passes. Dedicated two-principal MCP transport E2E remains required before a multi-user release claim. |

## Acceptance, Rollback, Handoff

- The full chain is source-backed, project-isolated, atomic on failure, evaluable, traceable, and visible in the browser/MCP without fabricated state.
- Docker/Celery proof is required for scheduled production claims; otherwise release scope is explicitly manual/local only.
- Existing BSC compiler, Artifact Graph, knowledge retrieval, MCP transport, and UI regressions all pass.
- Rollback pauses schedules and disables feature flags first, then reverts code/schema only through additive-safe deployment procedures; raw Vault files, source records, and audit history are retained.
- Final handoff contains worklog evidence, command results, deployment configuration, release note, and a concise list of unresolved external dependencies.
