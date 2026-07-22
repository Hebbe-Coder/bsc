# BSC A/B/C/D Knowledge Growth - Execution Index

**Design authority:** `docs/superpowers/specs/2026-07-22-bsc-abcd-knowledge-growth-product-prd.md`
**Baseline authority:** `docs/superpowers/plans/2026-07-21-karpathy-llm-wiki-knowledge-growth-index.md`
**Consolidated production plan:** `docs/superpowers/plans/2026-07-22-abcd-growth-consolidation.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-22-abcd-knowledge-growth.md`
**Status:** P1-P9 implementation and release verification complete in the isolated fixture and Docker profile; live provider-account calls are not claimed.
**Delivery model:** Nine bounded plans with test-first handoff

## 1. Scope And Baseline

The 2026-07-21 P1-P8 implementation is a completed dependency, not work to repeat. It already supplies immutable A-layer sources, governed B-layer Wiki publication, project-scoped retrieval, Knowledge Graph, durable runs and schedules, weekly distillation, REST/MCP transport, and the initial Knowledge Workspace.

This execution set implements the PRD's additive A/B/C/D growth loop:

```text
Capture -> A Evidence -> B Knowledge -> C Method -> D Output -> Review -> B/C/Eval
```

The new production surface is project profile and triage, first-class C and D records, authoritative cross-stage lineage, output feedback and evaluation, method evolution, growth-aware context, dual-cadence distillation, API/MCP expansion, and the A/B/C/D/Review workspace.

## 2. Delivery Order

```text
P1 Contracts, profile, Vault and persistence
  -> P2 Capture, triage and integrations
  -> P3 Output, feedback and lineage
  -> P4 Method evolution
  -> P5 Context and project-specific generation
       -> P6 Automation and distillation -----+
       -> P7 REST and MCP ---------------------+-> P8 Workspace visualization
                                                -> P9 Integration and release
```

P6 and P7 may execute in parallel only after P5 has merged and the P1 contracts are frozen. P8 may prepare static design fixtures after P1, but production API wiring starts only after P7. P9 starts after P1-P8 acceptance commands pass.

| ID | Plan | PRD coverage | Primary output | Depends on |
|---|---|---|---|---|
| P1 | `2026-07-22-abcd-growth-contracts-profile-vault.md` | FR-1, FR-8 foundations; AC 6, 17, 20 | Additive domain/schema, profile, safe Vault paths, lineage repository | 2026-07-21 P1-P8 |
| P2 | `2026-07-22-abcd-growth-capture-triage-integrations.md` | FR-2, FR-3, FR-5, FR-12, FR-13; AC 1-4, 16, 19 | Multi-channel capture, deterministic triage, research routing | P1 |
| P3 | `2026-07-22-abcd-growth-output-feedback-lineage.md` | FR-8, FR-9, FR-10; AC 10-12 | D registry, quality evaluation, feedback routing, lineage | P1, P2 |
| P4 | `2026-07-22-abcd-growth-method-evolution.md` | FR-6; AC 7-8 | C registry, proposals, revisions, promotion and rollback | P3 |
| P5 | `2026-07-22-abcd-growth-context-generation.md` | FR-4, FR-7, FR-14; AC 5, 9, 12 | Growth context packs and project-specific PRD/SOP/content wiring | P2, P3, P4 |
| P6 | `2026-07-22-abcd-growth-automation-distillation.md` | FR-11 plus operations; AC 13-15, 19 | Daily and Friday idempotent jobs, recovery and managed files | P5 |
| P7 | `2026-07-22-abcd-growth-api-mcp.md` | FR-15 plus permissions; AC 17, 20 | Project-scoped REST/SSE/MCP contracts | P5 |
| P8 | `2026-07-22-abcd-growth-workspace-visualization.md` | FR-16 plus metrics; AC 18-19 | A/B/C/D/Review operations workspace and real visualizations | P7 |
| P9 | `2026-07-22-abcd-growth-integration-release.md` | Reliability, performance, all AC | End-to-end, Docker, PostgreSQL, browser and release proof | P1-P8 |

## 3. Frozen Cross-Plan Contracts

A plan may extend these contracts additively. Renaming a state, relation, path, event, or authority requires a PRD change and a worklog decision before implementation.

### 3.1 Authority And Safety

- A evidence remains immutable. A new version creates a new source record; automation never edits source bytes.
- B Wiki changes use the existing `WikiProposal` gates and atomic publication path.
- C method changes use `MethodProposal`; prompt-only automatic publication is policy-gated.
- Code, hooks, agents, filesystem commands, and new MCP permissions require explicit administrator approval.
- D outputs are immutable registrations. Replacement creates a new output/version relation.
- D never becomes A or published B directly. Feedback creates typed proposals, correction cases, failure cases, or new external source capture.
- Obsidian is the readable knowledge IDE. BSC database records are authoritative for runs, permissions, proposals, evaluations, feedback, schedules, and audit.
- Knowledge Graph remains distinct from the existing business Artifact Graph.

### 3.2 States And Relations

- Triage dispositions: `research_topic`, `knowledge_candidate`, `reference`, `archive`, `ignore`.
- Method states: `candidate`, `validating`, `approved`, `published`, `rejected`, `deprecated`, `superseded`.
- Output states: `registered`, `evaluating`, `accepted`, `rejected`, `filed`, `archived`, `superseded`.
- Feedback types: `accepted`, `rejected`, `corrected`, `rated`, `reused`.
- Relations: `source_supports_page`, `source_contradicts_source`, `page_informs_method`, `output_used_source`, `output_used_page`, `output_used_method_revision`, `output_produced_by_run`, `feedback_evaluates_output`, `output_proposes_page`, `output_proposes_method`, `method_supersedes_method`.
- All records and edges carry `project_id`; repositories reject unscoped reads and cross-project endpoints.
- Lineage rejects duplicate deterministic edges and any path that makes generated output its own evidence ancestor.

### 3.3 Filesystem And Automation

- The active Vault is `D:\bsc\bsc`; managed project roots are below `projects/` unless configuration explicitly changes them.
- New weekly output is below `distillations/每周蒸馏/<YYYY-Www>/`; historical `distillations/<week>/` remains readable.
- Daily cadence is 17:00 and Friday cadence is 17:30 in `Asia/Shanghai`.
- `distillations/` is excluded from automation inputs.
- Managed writes are atomic, manifest-backed, revision-preserving, and refuse to overwrite unmarked user files.
- Identical project, job type, period, cutoff, and `input_hash` produce one logical run.
- Celery/Redis-disabled mode reports scheduling as `unavailable`; it does not simulate recurring execution.

### 3.4 Compatibility

- Existing Wiki APIs, knowledge query behavior, Skill Registry, Skill execution history, orchestrator lifecycle, Artifact Graph, MCP initialize/tools/list/tools/call, HTTP/SSE replay, and error envelope remain compatible.
- Existing projects and `AGENTS.md` files work with defaults and are never silently rewritten.
- Existing runtime databases, user Vault content, and historical output files are not backfilled at install time.
- SQLite and PostgreSQL must expose equivalent lifecycle and isolation behavior.

## 4. File Ownership And Parallel Boundaries

| Area | Owner | Other plans may |
|---|---|---|
| Growth contracts, schema, profile, Vault path policy, lineage repository | P1 | import public types and call repositories |
| Capture adapters, triage service, Feishu/Horizon source mapping | P2 | request capture/triage through service API |
| Output registry, evaluator, feedback router, completion bridges | P3 | read accepted outputs and evaluation summaries |
| Method registry, proposal gate, evaluator, execution selection | P4 | resolve published revisions; never mutate directly |
| Context selection, generation provenance and compiler bridges | P5 | consume frozen context-pack contract |
| Growth Celery jobs, cadence, distillation writer | P6 | enqueue documented job types |
| REST schemas/routes, SSE growth events, MCP growth tools | P7 | frontend imports generated/manual client contract only |
| Frontend API/store/components/styles and browser component tests | P8 | consume P7 API; no backend behavior changes |
| E2E fixtures, deployment corrections, release evidence/docs | P9 | fix integration defects within owner contracts |

No sub-agent may modify another plan's owned production files without recording the need in the worklog and handing the change back to the owner. P9 may correct deployment wiring but may not redesign domain behavior to make an E2E test pass.

## 5. Execution Rules

1. Begin each task with a failing contract, repository, service, integration, or UI test. Record the red test and the passing result.
2. Implement the smallest production path that satisfies the frozen contract; do not add fake records, fixture fallback, or file-existence-derived success.
3. Run focused tests after each task and the plan regression command before handoff.
4. Keep database migrations additive and idempotent. Never drop or repurpose existing tables or columns.
5. Use canonical project-relative paths, symlink checks, bounded reads/writes, secret redaction, and project authorization at repository boundaries.
6. Do not stage `app/bsc_cloud.db`, `app/bsc_cloud.db-shm`, caches, generated output, downloaded archives, `D:\bsc` content, or unrelated user changes.
7. Mark a checkbox complete only when production code and its verification evidence exist.
8. A unavailable external dependency is a truthful release boundary, not a passed live-integration gate.

## 6. Required Handoff Contract

Every sub-agent must append one worklog entry containing:

- plan ID and completed task IDs;
- files created and modified;
- schema/API/event contract changes;
- exact commands and pass/fail/skip counts;
- runtime evidence for any Docker, Celery, Horizon, Feishu, model, or browser claim;
- compatibility statement and known limitations;
- rollback actions exercised;
- next-plan inputs, including fixture IDs and public symbols;
- `git status --short` and `git diff --check` confirmation.

## 7. Integration Gates

| Gate | Required evidence |
|---|---|
| Domain | Schema migration/reopen, lifecycle, idempotency, path safety, cycle and project-isolation tests pass on SQLite; PostgreSQL runs in P9 |
| C/D loop | A real terminal Skill/orchestrator/export output registers once, evaluates, accepts/rejects, routes feedback and preserves evidence ancestry |
| Method | Three-use threshold, policy approval, regression prevention, privileged method approval and rollback are proven |
| Context | PRD/SOP/content output records profile/rules/context/method revisions, citations, assumptions and omissions |
| Automation | Repeated daily/Friday dispatch no-ops correctly, changed input archives a managed revision, user files survive, restart recovery is durable |
| API/MCP | Reader/admin/system permissions, pagination, bounded graph, JSON-RPC compatibility and SSE replay pass |
| UI | Real backend data drives funnel/trends/graph; desktop/mobile, keyboard, reduced-motion, failure and unavailable states pass |
| Release | Full Python/frontend regressions, Docker Worker/Beat, PostgreSQL, security, performance and backward compatibility pass |

## 8. Completion Definition

The PRD is 100 percent implemented only when all P1-P9 checkboxes have implementation evidence, all 20 acceptance scenarios pass, P9 records real runtime results, and no external boundary is described as executed without proof. Documentation creation alone does not advance production completion.

## 9. Rollback Order

1. Pause growth schedules and disable the A/B/C/D growth feature flags.
2. Stop new output/method bridges while retaining records and user files.
3. Revert UI and API exposure without deleting audit history.
4. Revert production code plan by plan in reverse order.
5. Leave additive schema in place unless a separately tested data migration is approved; never delete A/B/C/D content as rollback.

## 10. Current Implementation Evidence

The entries below describe implemented production slices, not closed plans. The P1-P9 task checkboxes remain the completion authority and are checked only after their exact verification commands and handoff evidence pass.

- **P1-P5:** Domain contracts, project profile, source triage, output/feedback/lineage, method evolution and growth context are implemented in `app/knowledge/` with focused SQLite tests.
- **P6:** `growth_daily` and `growth_weekly_distillation` are accepted by the persistent scheduler and execute through `knowledge.execute`; daily/weekly idempotency, Vault protection, timezone cadence and unavailable semantics are tested. Docker Redis, Worker registration and Beat persistent-scheduler runtime checks pass.
- **P7:** Growth REST routes and `knowledge_growth_*` MCP tools are registered. HTTP JSON-RPC tool listing, argument validation, disabled state, project scope and reader/write authorization are tested.
- **P8:** `src/components/GrowthWorkspace.tsx` is mounted from `UnifiedWorkspace` and consumes real P7 data for stage navigation, funnel, records, lineage and inspection. Frontend tests, TypeScript check, production build and authenticated Docker browser checks at `390x844` and `1280x720` pass without whole-page horizontal overflow.
- **P9:** Isolated A-to-D/recovery fixtures, PostgreSQL parity, 10,000-record performance, Docker API/Redis/Worker/Beat recovery, and authenticated desktop/mobile browser gates passed. Live Horizon, Feishu and model-provider account calls remain external configuration boundaries, not completion claims.
