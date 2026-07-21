# Karpathy LLM Wiki Knowledge Growth - Implementation Index

**Design authority:** `docs/superpowers/specs/2026-07-21-karpathy-llm-wiki-knowledge-growth-prd.md`
**Execution status:** P1 contracts/repository implemented; P2 immutable evidence capture foundation implemented; P3 rules/context/proposal compiler foundation implemented
**Working log:** `docs/superpowers/worklogs/2026-07-21-karpathy-llm-wiki-knowledge-growth.md`

## Delivery Order

```text
P1 Vault contracts
  -> P2 Source capture + Horizon
  -> P3 Wiki compiler + context
  -> P4 Quality, graph + evals
  -> P5 Automation + distillation
  -> P6 MCP + HTTP/SSE API
  -> P7 Knowledge workspace visualization
  -> P8 Integration + release
```

P5 and P6 may execute in parallel only after P4's public contracts are merged. P7 may prepare design scaffolding after P4, but it consumes the frozen P6 API/event contract before functional implementation. P8 starts only when all predecessor acceptance commands pass.

| ID | Plan | Primary output | Depends on |
|---|---|---|---|
| P1 | `2026-07-21-knowledge-vault-contracts.md` | Vault resolver, domain contracts, schema, isolated repository API | None |
| P2 | `2026-07-21-knowledge-source-capture-horizon.md` | Obsidian sync, source registry, Horizon adapter | P1 |
| P3 | `2026-07-21-knowledge-wiki-compiler-context.md` | Project rules, proposal compiler, context-pack/SOP bridge | P1, P2 |
| P4 | `2026-07-21-knowledge-quality-graph-evals.md` | Lint, graph, patch gates, eval baseline | P1, P2, P3 |
| P5 | `2026-07-21-knowledge-automation-distillation.md` | Beat scheduling, jobs, weekly outputs | P4 |
| P6 | `2026-07-21-knowledge-mcp-api.md` | Governed REST, SSE, MCP Wiki tools | P4 |
| P7 | `2026-07-21-knowledge-workspace-visualization.md` | Browser knowledge workspace and visualizations | P6 |
| P8 | `2026-07-21-knowledge-integration-release.md` | End-to-end proof, Docker and release evidence | P5, P6, P7 |

## Contract Lock

The following boundaries are cross-plan contracts. A sub-agent must not change them without a PRD update and an explicit entry in the worklog:

- Obsidian raw sources are immutable to BSC automation and LLM/MCP calls.
- Published Wiki Markdown is the readable synthesis authority; BSC search indexes are derived.
- All new records and APIs require `project_id`; project authorization cannot fall back to an unscoped query.
- Wiki changes travel as typed proposals and are published only after P4 gates.
- Knowledge Graph is distinct from the existing Artifact Graph.
- Existing `/knowledge` operations, current MCP transports, and orchestrator lifecycle semantics remain compatible.
- Celery synchronous fallback may execute user-invoked work but must never present a durable schedule as active.

## File Ownership

| Area | Owning plan | Other plans may |
|---|---|---|
| `app/knowledge/wiki_contracts.py`, `vault.py`, schema migrations | P1 | import public contracts only |
| source registry, filesystem sync, Horizon adapter | P2 | call public service only |
| Wiki compiler, context pack, methodology bridge | P3 | consume proposal/context contracts |
| lint, citations, Knowledge Graph, evaluators | P4 | consume read-only reports |
| knowledge Celery tasks and Beat configuration | P5 | enqueue documented tasks only |
| HTTP/SSE routes and MCP handlers | P6 | consume API clients/contracts only |
| `src/components/knowledge/**`, knowledge frontend API/store | P7 | import exported view only |
| Docker release proof, E2E fixtures, release docs | P8 | add test-only adapters only |

## Required Handoff From Every Sub-Agent

1. A short worklog entry with completed task IDs, changed files, commands run, exact results, and deviations.
2. Focused tests for every newly introduced contract or failure path, then the relevant regression suite.
3. No generated databases, cache files, user vault files, or downloaded archives staged for commit.
4. A compatibility statement confirming whether existing API/MCP/frontend behavior changed.
5. A clean `git diff --check` result before handoff.

## Integration Gates

- P1-P4: isolated schema and file-system tests, project isolation tests, proposal atomicity tests, and existing knowledge regression tests pass.
- P5: real Celery/Redis/Beat execution is demonstrated in Docker; disabled mode truthfully reports unavailable scheduling.
- P6: JSON-RPC initialize/tools/list/tools/call and SSE replay pass with project-scoped Wiki tools.
- P7: TypeScript check/lint/build and browser desktop/mobile workflows pass using real backend data.
- P8: full Python suite, frontend checks, Docker compose verification, no untracked runtime data, and a release worklog record pass.

## Rollback Rules

- Each plan is independently revertible. Do not combine plans in a single commit.
- Schema additions must be additive and idempotent; no existing knowledge or Artifact Graph table is dropped or repurposed.
- A failed Wiki proposal rolls back by not changing published files. A published revision rolls back through a new, auditable proposal.
- Disabling feature flags must restore existing BSC behavior without deleting a user's Obsidian files or BSC audit records.

## Implemented Slices

- P1: typed project-scoped contracts, additive schema, and `WikiRepository` are implemented and tested. Vault filesystem resolution remains deferred until a configured Obsidian Vault exists.
- P2: captured evidence is persisted immutably as `raw_content` plus SHA-256 hash, with project-local deduplication, trust policy, Horizon signal mapping, and source lifecycle guards. Obsidian scanning and live Horizon HTTP transport remain deferred.
- P3: `AGENTS.md` parsing, bounded context packs with omission records, a provider-injected compiler that persists only draft proposals/runs, and an opt-in SOP Builder context bridge are implemented and tested. Wiki file publishing and filesystem-aware page snapshots remain pending.
