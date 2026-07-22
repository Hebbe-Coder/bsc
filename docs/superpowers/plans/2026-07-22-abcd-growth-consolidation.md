# BSC A/B/C/D Knowledge Growth - Consolidated Production Plan

**Product authority:** `docs/superpowers/specs/2026-07-22-bsc-abcd-knowledge-growth-product-prd.md`
**Detailed plan sources:** `docs/superpowers/plans/2026-07-22-abcd-growth-*.md`
**Evidence ledger:** `docs/superpowers/worklogs/2026-07-22-abcd-knowledge-growth.md`
**Status:** Complete for the integrated fixture and Docker release profile as of 2026-07-22. Live third-party account calls remain explicitly unclaimed.
**Purpose:** This file consolidates P1-P9 into one execution and closure authority. The individual plan files retain detailed task context and file ownership.

## 1. Completion Contract

The product is complete only when all of the following are true at the same revision:

- [x] P1-P8 focused commands pass against the integrated worktree.
- [x] P9 proves the full A -> B -> C -> D -> Review -> B/C/Eval lifecycle with disposable fixtures.
- [x] All 20 PRD acceptance scenarios have direct test or runtime evidence.
- [x] SQLite and PostgreSQL expose equivalent state, isolation and idempotency behavior.
- [x] Docker API, Redis, Worker and Beat start, execute, restart and recover using an isolated Vault.
- [x] REST, SSE and MCP permissions, project scope, pagination and replay pass without placeholder behavior.
- [x] Desktop and mobile browser journeys use authorized, non-empty backend data and cover failure states.
- [x] Performance, accessibility, compatibility, security and rollback gates pass.
- [x] The full Python and frontend regressions pass after the final production edit.
- [x] The worklog records exact commands, counts, runtime evidence, known external boundaries and release scope.
- [x] Runtime databases, user Vault content, secrets, generated output and unrelated user changes are excluded from release scope.

Implemented code without matching evidence is not a completed item. A configured-but-unreachable dependency is `unavailable`, never successful. No UI file-existence check or mock fixture may stand in for backend success.

**Closure evidence:** the full Python suite passed with `983 passed, 11 skipped`; focused frontend tests passed with `52 passed`; type-check, lint and production build passed. The isolated PostgreSQL lifecycle, 10,000-record p95 guard, Docker recovery and authenticated populated browser journeys were exercised. The worklog is the authoritative command and runtime ledger.

## 2. Delivery Graph

```text
P1 Contracts, profile, Vault and persistence
  -> P2 Capture, triage and integrations
  -> P3 Output, feedback and lineage
  -> P4 Method evolution
  -> P5 Context and project-specific generation
       -> P6 Automation and distillation -----+
       -> P7 REST, SSE and MCP ----------------+-> P8 Workspace visualization
                                                -> P9 Integration and release
```

P6 and P7 may run in parallel after P5. P8 consumes the frozen P7 contract. P9 is the only authority allowed to close the product.

## 3. Frozen Product Invariants

### 3.1 Authority

- A evidence is immutable. New bytes create a new source revision.
- B Wiki content changes only through typed proposals, deterministic gates and atomic publication.
- C methods change through method proposals, evaluations, explicit policy and revision rollback.
- D outputs are immutable registrations; replacement creates a new output relation.
- D feedback may create a proposal, correction case or failure case, but D never becomes factual A/B evidence by itself.
- Obsidian is the readable knowledge IDE. The BSC database is authoritative for runs, permissions, proposals, evaluations, feedback, schedules and audit.
- Search indexes and the Knowledge Graph are rebuildable derivatives. The Knowledge Graph remains separate from Artifact Graph.

### 3.2 Scope And Safety

- Every source, page, method, output, evaluation, feedback, schedule, run and edge is project scoped.
- Repository and transport boundaries reject empty scope, foreign IDs, path escape, symlink escape and cyclic generated ancestry.
- Managed writes are atomic, manifest-backed and revision-preserving. User-authored files are never overwritten.
- Raw evidence, credentials and secret-bearing metadata are not returned from reader APIs, logs, prompts or MCP tools.
- Existing Wiki, Skill, orchestrator lifecycle, Artifact Graph and MCP initialize/tools/list/tools/call behavior remains compatible.

### 3.3 Automation

- Daily incremental distillation runs at 17:00 Asia/Shanghai.
- Friday weekly distillation runs at 17:30 Asia/Shanghai.
- `distillations/` is excluded from all capture and distillation inputs.
- The same project, job type, period, cutoff and input hash creates one logical run.
- Celery/Redis-disabled mode reports `unavailable`; it does not simulate recurring execution.

## 4. Consolidated Implementation Work

### P1 - Contracts, Project Profile, Persistence And Vault

**Depends on:** 2026-07-21 Wiki baseline.
**Production boundary:** growth contracts, additive schema, repository, profile and Vault path/write policy.

- [x] P1.1 Prove typed states, transitions, relation types, immutable identity fields and strict serialization.
- [x] P1.2 Prove additive/reopen-safe SQLite and PostgreSQL schema plus atomic project-scoped repository operations.
- [x] P1.3 Prove immutable project profile revisions, compare-and-set behavior, defaults and `AGENTS.md` compatibility.
- [x] P1.4 Prove canonical Vault mapping, binary-safe writes, symlink/path rejection and no-overwrite bootstrap.
- [x] P1.5 Pass isolation, migration, compatibility and rollback verification and record the handoff.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_growth_contracts.py tests\knowledge\test_growth_repository.py tests\knowledge\test_project_profile.py tests\knowledge\test_growth_vault.py tests\knowledge\test_wiki_contracts.py tests\knowledge\test_wiki_schema.py tests\knowledge\test_vault.py -q
```

### P2 - Capture, Triage, Horizon, Feishu And Obsidian

**Depends on:** P1.
**Production boundary:** capture adapters, immutable evidence, five-dimensional triage and external-source provenance.

- [x] P2.1 Prove a common adapter contract for text, binary metadata, timestamps, attachments, source attribution and secret redaction.
- [x] P2.2 Prove deterministic five-dimensional triage, reliability hard gates, reason codes, idempotency and research routing.
- [x] P2.3 Prove Horizon incremental import from staged/run-store artifacts without inventing a Horizon API or direct publication path.
- [x] P2.4 Prove explicit Feishu authorization, document/minutes revision provenance and Obsidian managed-directory exclusions.
- [x] P2.5 Prove contradiction/research/health routing and truthful OCR/transcription/provider unavailability.
- [x] P2.6 Pass capture, triage and integration regression and record the handoff.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_capture_adapters.py tests\knowledge\test_source_triage.py tests\knowledge\test_feishu_import.py tests\knowledge\test_horizon_client.py tests\knowledge\test_horizon_import.py tests\knowledge\test_horizon_run_store.py tests\knowledge\test_wiki_source_capture.py tests\knowledge\test_wiki_sync.py -q
```

### P3 - Output Registry, Evaluation, Feedback And Lineage

**Depends on:** P1-P2.
**Production boundary:** D output registration, content hashing/filing, evaluation, feedback routing and authoritative lineage.

- [x] P3.1 Prove immutable output registration from Skill, orchestrator and export bridges with exact run/context/method/evidence ancestry.
- [x] P3.2 Prove evaluation lifecycle, quality records, accepted/rejected state gates and no synthetic factual authority.
- [x] P3.3 Prove accepted/corrected/rejected/rated/reused feedback routes to governed proposals or regression cases.
- [x] P3.4 Prove deterministic lineage edges, duplicate suppression, project isolation and generated-ancestor cycle rejection.
- [x] P3.5 Prove `accepted -> filed` validates Vault path and SHA-256 while preserving output identity and provenance.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_output_registry.py tests\knowledge\test_output_evaluator.py tests\knowledge\test_feedback_router.py tests\knowledge\test_generation_provenance.py tests\integration\test_growth_output_bridges.py -q
```

### P4 - Governed Method Evolution

**Depends on:** P3.
**Production boundary:** C method detection, registry, revision evaluation, policy gates, promotion, deprecation and rollback.

- [x] P4.1 Prove comparable-use grouping and the three-success threshold; fewer uses cannot auto-promote.
- [x] P4.2 Prove immutable method/revision/proposal records and legal candidate-to-published lifecycle transitions.
- [x] P4.3 Prove regression-aware evaluation, privileged method approval and prompt-only automatic-promotion restrictions.
- [x] P4.4 Prove execution resolves an exact published revision and records it on every output.
- [x] P4.5 Prove `published -> deprecated`, supersession, idempotency, optimistic locking, audit and rollback.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_method_detector.py tests\knowledge\test_method_registry.py tests\knowledge\test_method_evaluator.py tests\knowledge\test_method_gate.py tests\knowledge\test_method_evolution.py -q
```

### P5 - Growth Context And Project-Specific Generation

**Depends on:** P2-P4.
**Production boundary:** bounded A/B/C/D context, provenance, PRD-to-SOP/content wiring and research-gap feedback.

- [x] P5.1 Prove deterministic, budgeted, project-isolated selection of profile, rules, B pages, eligible A sources, exact C revisions and governed D examples.
- [x] P5.2 Prove context hashes include assumptions, omissions and research gaps and redact untrusted instructions/secrets.
- [x] P5.3 Prove legacy and business-runtime PRD/SOP paths receive explicit project scope through first run, loopback and rerun.
- [x] P5.4 Prove Growth context takes precedence only when it contains real project knowledge; otherwise Wiki/legacy fallback remains truthful.
- [x] P5.5 Prove outputs record context pack, exact IDs/revisions, citations, assumptions and research gaps.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_growth_context.py tests\knowledge\test_generation_provenance.py tests\integration\test_growth_sop_context.py tests\orchestrator\test_wiki_methodology_bridge.py tests\orchestrator\test_engine.py tests\orchestrator\test_api.py -q
```

### P6 - Daily And Weekly Automation

**Depends on:** P5.
**Production boundary:** persisted schedule intent, idempotent Celery jobs, daily/Friday distillation, manifests and recovery.

- [x] P6.1 Prove timezone-aware daily/Friday schedule creation, reconciliation, ownership and disabled/unavailable semantics.
- [x] P6.2 Prove daily incremental and weekly dual-track distillation, input cutoff/hash, revision archive and user-file protection.
- [x] P6.3 Prove Worker/Beat dispatch, retry, abandoned-run recovery, restart replay and exactly-once logical outcomes.
- [x] P6.4 Prove Codex prompt generation matches persisted cadence and never claims a non-executed automation.
- [x] P6.5 Prove `distillations/` exclusion prevents daily/weekly recursive self-ingestion.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_growth_scheduler.py tests\knowledge\test_growth_distillation.py tests\knowledge\test_codex_automation_prompt.py tests\integration\test_growth_celery.py tests\integration\test_abcd_growth_recovery.py -q
```

### P7 - Project-Scoped REST, SSE And MCP

**Depends on:** P5.
**Production boundary:** authenticated growth REST, replayable events and compatible MCP tools.

- [x] P7.1 Prove reader/admin/system permission matrix, project scope, bounded payloads and stable error envelopes.
- [x] P7.2 Prove real REST lifecycle actions for profiles, sources, methods/revisions/deprecation, outputs/filing, feedback, runs, schedules and graph.
- [x] P7.3 Prove SSE ordering, cursor replay, disconnect recovery and project authorization.
- [x] P7.4 Prove MCP initialize/tools/list/tools/call compatibility, argument validation and no raw evidence or cross-project access.
- [x] P7.5 Prove pagination bounds, optimistic-lock conflicts, audit actor/reason and absence of placeholder `operation_unavailable` behavior.

**Focused gate:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_growth_api.py tests\api\test_growth_sse.py tests\mcp\test_growth_tools.py tests\mcp\test_growth_http_contract.py tests\mcp\test_wiki_tools.py tests\test_mcp_compatibility.py -q
```

### P8 - A/B/C/D/Review Workspace And Visualization

**Depends on:** P7.
**Production boundary:** real API client/store, stage workspace, inspector/diff, funnel/trends and bounded lineage graph.

- [x] P8.1 Prove API/store loading, pagination, selection and empty/loading/permission/offline/503/500 states without fake fallback.
- [x] P8.2 Prove A/B/C/D/Review navigation, reader, revision diff, source inspector, method/output actions and feedback.
- [x] P8.3 Prove persisted-record funnel, time trends, quality debt and no success inference from file presence.
- [x] P8.4 Prove filterable lineage traversal from output through method/page/source with bounded React Flow nodes/edges.
- [x] P8.5 Prove desktop/mobile layout, keyboard/focus, reduced motion, contrast, chart pixels, no overlap/overflow and clean console.

**Focused gate:**

```powershell
npm run test:frontend
npm run check
npm run lint
npm run build
```

### P9 - Integration, Recovery And Release

**Depends on:** P1-P8.
**Production boundary:** disposable end-to-end fixture, runtime parity, browser proof, performance, compatibility and release evidence.

- [x] P9.1 Prove full A-to-D lifecycle plus accepted/rejected feedback and method evolution through P7 interfaces.
- [x] P9.2 Prove two-principal project isolation, roles, paths, secrets, untrusted content, graph bounds and compatibility.
- [x] P9.3 Prove duplicate daily/weekly dispatch, changed-input archive, user-file protection, restart/replay and unavailable modes.
- [x] P9.4 Prove PostgreSQL parity and Docker API/Redis/Worker/Beat health, task execution, graceful restart and durable queryability.
- [x] P9.5 Prove authorized non-empty desktop/mobile browser journeys, accessibility and real visualization pixels.
- [x] P9.6 Prove 10,000-record metadata p95 below 300 ms, full regression, clean release scope and exercised rollback.

**Focused gates:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_abcd_growth_e2e.py tests\integration\test_abcd_growth_isolation.py tests\integration\test_abcd_growth_recovery.py tests\integration\test_abcd_growth_postgres.py tests\integration\test_abcd_growth_performance.py -q
docker compose --profile full config
```

## 5. PRD Acceptance Matrix

| AC | Required proof | Owner | State |
|---|---|---|---|
| 1 | Article capture is immutable, hashed, deduplicated and triaged | P1/P2/P9 | Passed: capture/triage and isolated E2E tests |
| 2 | Horizon imports only new staged artifacts and cannot publish directly | P2/P9 | Passed: staged-artifact import contract tests |
| 3 | Unreliable high-score source remains ineligible | P2/P9 | Passed: deterministic triage tests |
| 4 | Contradiction creates explicit research work, never fabricated resolution | P2/P9 | Passed: triage/health route tests |
| 5 | Wiki multi-page/index/citation/graph publication is atomic | Baseline/P5/P9 | Passed: Wiki contract and E2E regression |
| 6 | Binary PDF/presentation survives publication | P1/P9 | Passed: Vault binary preservation tests |
| 7 | Three comparable successes create a method candidate | P3/P4/P9 | Passed: method detector tests |
| 8 | Regressing method revision cannot become published | P4/P9 | Passed: method evaluator/gate tests |
| 9 | PRD-to-SOP records profile/rules/A/B/C IDs and assumptions | P5/P9 | Passed: project-scoped SOP context integration |
| 10 | Every output records project/run/context/method/hash/quality | P3/P9 | Passed: output registry/evaluator tests |
| 11 | Accepted D creates governed proposal with external ancestry | P3/P9 | Passed: feedback routing and E2E tests |
| 12 | Rejected D creates regression case and is excluded from factual context | P3/P5/P9 | Passed: feedback/context tests |
| 13 | Duplicate daily execution yields one logical result | P6/P9 | Passed: recovery/idempotency tests |
| 14 | Changed Friday input archives the previous managed revision | P6/P9 | Passed: weekly revision tests |
| 15 | User-authored weekly file is not overwritten | P1/P6/P9 | Passed: managed-file protection tests |
| 16 | Feishu import preserves project and document revision provenance | P2/P9 | Passed: explicit import fixture tests |
| 17 | Cross-project A/B/C/D/graph/API/MCP access is rejected | P1/P7/P9 | Passed: isolation and MCP HTTP tests |
| 18 | Desktop/mobile output-to-method-to-page-to-source journey works | P8/P9 | Passed: authenticated Docker browser evidence |
| 19 | Missing Redis/Horizon/model/OCR/transcription/Vault is truthful | P1/P2/P6/P8/P9 | Passed: unavailable-state tests and browser failure checks |
| 20 | Wiki/Artifact Graph/Skill/orchestration/MCP regressions pass | All/P9 | Passed: full Python/frontend regressions |

## 6. Current Evidence Snapshot

This snapshot is informative, not a completion claim. The final worklog entry supersedes it.

- **P1-P5:** Full-suite and P9 fixture coverage now proves contracts, capture, triage, output/feedback lineage, governed methods and scoped context together.
- **P6:** Redis-backed Worker/Beat start, task registration, idempotency, restart recovery, weekly revision archive and user-file protection are verified.
- **P7:** REST, SSE and MCP lifecycle, authorization, project isolation, replay and unavailable paths are covered without placeholder success behavior.
- **P8:** The real-data workspace was verified at `1280x720` and `390x844`, including chart and graph pixel checks, keyboard/drawer behavior, no root overflow and clean console.
- **P9:** Full Python, frontend, PostgreSQL parity, performance, Docker rebuild/recovery and browser gates are complete. A real Feishu/Horizon/model provider account call is not asserted because no authorized live integration run was supplied; code reports that boundary truthfully as unavailable when not configured.

## 7. Final Verification Order

1. Run P1-P5 focused suites and fix contract or lifecycle defects.
2. Run P6/P7 focused suites in parallel-safe order and fix recovery/transport defects.
3. Run P9 SQLite lifecycle, isolation and recovery suites.
4. Run PostgreSQL parity and isolated Docker API/Redis/Worker/Beat execution/restart.
5. Seed authorized non-empty fixture data and complete desktop/mobile browser and accessibility proof.
6. Run performance, all Python tests, all frontend tests/check/lint/build and `git diff --check`.
7. Audit every AC row and P1-P9 checkbox against current evidence.
8. Update individual plans, this consolidation file, worklog and release notes to match evidence exactly.
9. Confirm release scope excludes prohibited/runtime/user files before commit or push.

## 8. Prohibited Release Scope

Never stage, modify for verification, or publish:

- `app/bsc_cloud.db`
- `app/bsc_cloud.db-shm`
- `.agents/`
- `output/resume/`
- `skills-lock.json`
- caches, generated output and downloaded archives
- the user Vault at `D:\bsc`
- `.env`, API keys, model keys, tokens or credential-bearing fixture content

## 9. Rollback Order

1. Pause growth schedules and disable Growth feature flags.
2. Stop new output/method bridges while retaining records and user files.
3. Remove P8 and P7 exposure without deleting audit history.
4. Revert P6 through P1 production code in reverse dependency order.
5. Retain additive schema unless a separate tested migration is approved.
6. Verify legacy Wiki, Skill, orchestrator, Artifact Graph and MCP paths after rollback.

## 10. Required Final Handoff

The final handoff must include the final revision, intended files, schema/API/event changes, exact pass/fail/skip counts, Docker/PostgreSQL/browser/performance evidence, unavailable external dependencies, compatibility result, rollback result, `git status --short`, `git diff --check` and release commit scope. Completion may be declared only when this file, all detailed plans and the worklog agree with the evidence.
