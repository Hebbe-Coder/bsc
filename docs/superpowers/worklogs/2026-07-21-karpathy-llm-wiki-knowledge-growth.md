# Karpathy LLM Wiki Knowledge Growth Worklog

**Status:** P1-P7 implemented and regression-verified; P8 runtime verification is in progress.
**Owner:** BSC platform
**Design authority:** `docs/superpowers/specs/2026-07-21-karpathy-llm-wiki-knowledge-growth-prd.md`

## Latest Update: DeepSeek Runtime Repair, Context Repair, And Weekly Publication Preservation (2026-07-27)

- Raised the weekly distillation contract to v20. A same-week replacement now requires a complete five-document LLM result when the active bundle already passed the complete LLM gate. Hybrid and deterministic attempts leave the existing Vault directory, hashes, manifest, and database revision untouched. In the configured production path, any real model attempt that degrades preserves an existing weekly bundle, including an initial deterministic one; offline/unconfigured test fallback remains eligible for its established revision behavior.
- Corrected the evidence-budget bottleneck that reduced a 125-record project ledger to one MCP source: daily runs retain the 4,000-character bounded context, while weekly runs now receive a separately audited 10,000-character context. The manifest stores `character_budget`, `character_count`, and `estimated_tokens` for every run.
- A real v18 DeepSeek run proved network and billing recovery with multiple HTTP 200 responses, but exposed two execution defects: complex model responses exhausted their output budget after reasoning, and an all-document rejection fanned out into many low-budget per-document repairs. The run `deepseek-v18-005b46bd92a445d0` was manually terminated only after its Worker had no active task, then durably recorded as `growth_task_timeout`, `retryable=false`, with no weekly artifact published.
- Full weekly generation now receives 4,500 tokens, targeted repair 2,200 tokens, and uses one outer PromptOps sample because the client already performs a bounded lower-temperature JSON repair. If every document fails the deterministic gate, the system performs one complete rewrite; per-document repair remains reserved for a partial failure with accepted files to preserve.
- Growth tasks now have an independent Celery lifecycle of 180 seconds soft and 210 seconds hard. Soft timeout is classified as a retryable, durable growth failure; schedule recovery uses the same hard deadline instead of the global one-hour task timeout.
- An unpublished attempt returns explicit `status=preserved` data with its attempted input hash, preserved input hash, generation evidence, and machine-readable reason. It creates no synthetic distillation row, so a later retry over the same evidence can succeed after the provider recovers.
- Celery records this outcome as `knowledge.growth.distillation.preserved`, with `preserved_count=1`, rather than emitting a completed-artifact event. The model attempt is therefore auditable without a false claim that fresh weekly files exist.
- `tests/knowledge/test_growth_distillation.py` passed: `42 passed`. New regression coverage proves both partial/hybrid and unavailable/invalid model responses cannot change any managed file, archive a replacement revision, or create a fake database artifact after a complete LLM weekly bundle exists; it also proves configured production fallback cannot replace an existing deterministic bundle, weekly and daily evidence budgets remain distinct, and whole-batch rejection does not fan out per document.
- `tests/integration/test_growth_celery.py`, configuration, and Compose contracts passed: `26 passed`. `compileall` passed; `git diff --check` emitted only existing CRLF conversion warnings.
- Live Docker rebuild and a new DeepSeek-backed weekly run with the bounded lifecycle remain the next steps. No v16 output was reclassified as a successful LLM result and no historical run evidence was altered.

## Objective

Deliver a Karpathy-style, Obsidian-compatible, self-maintaining knowledge Wiki for BSC. The system must use immutable evidence, governed Wiki proposals, project-specific `AGENTS.md` rules, persistent evaluation, weekly distillation, and real visual operational state.

## Baseline Confirmed

- `app/knowledge/service.py` already provides idempotent text ingest, project-scoped hybrid retrieval, and derived keyword/TF-IDF/vector indexes.
- `app/knowledge/schema.py` supports portable SQLite/PostgreSQL schema initialization and project-level keys/benchmarks, but has no vault, source lifecycle, proposal, graph, schedule, or distillation domain.
- `app/api/mcp_http.py` already provides MCP JSON-RPC and SSE transports; the current exposed surface has no Wiki maintenance tools.
- `app/core/celery_app.py` and `docker-compose.yml` support optional Celery Worker and Redis, but no Celery Beat scheduler service or knowledge tasks.
- `src/components/UnifiedWorkspace.tsx` is the active application surface. ECharts and React Flow are installed and can render real knowledge data.
- `app/bsc_cloud.db` and `app/bsc_cloud.db-shm` are pre-existing runtime modifications and are intentionally outside this work.

## Progress

| Time | Item | Status | Evidence |
|---|---|---|---|
| 2026-07-21 | Karpathy LLM Wiki reference verified | Complete | Original concept distinguishes immutable raw sources, compiled Markdown Wiki, and evolving agent schema |
| 2026-07-21 | LLM Wiki implementation reviewed | Complete | MCP tools, filesystem authority, lint, citation graph, watcher, local/hosted storage seam reviewed |
| 2026-07-21 | Horizon architecture reviewed | Complete | Treat Horizon as external intelligence/source adapter, not the BSC knowledge authority |
| 2026-07-21 | PRD created | Complete | Knowledge authority, functional requirements, contracts, safety, UX, acceptance, rollout documented |
| 2026-07-21 | Execution index and sub-plan split created | Complete | Eight ordered plans with ownership, contract lock, gates, rollback, and handoff rules |
| 2026-07-21 | Documentation verification | Complete | 1 PRD, 1 execution index, 8 sub-agent plans, and this worklog exist; `git diff --check` passes |
| 2026-07-21 | P1 contracts/schema/repository implemented | Complete | `wiki_contracts.py`, additive Wiki schema, project-scoped `WikiRepository`, optional config flags, and focused tests pass |
| 2026-07-21 | P2 source capture foundation implemented | In Progress | `wiki_source_capture.py` adds immutable SHA-256 capture, same-project hash dedupe, trust/eligibility policy, Horizon signal mapping, and lifecycle transition guard |
| 2026-07-21 | Immutable evidence persistence corrected | Complete | `SourceRecord.raw_content` and additive `knowledge_sources.raw_content` migration retain the exact evidence used by citation-backed compilation |
| 2026-07-21 | P3 rules/context/compiler foundation implemented | Complete | `wiki_rules.py`, `context_pack.py`, and `wiki_compiler.py` parse project rules, construct bounded traceable context, validate provider output, and persist draft proposals/runs only |
| 2026-07-21 | P4 lint and Knowledge Graph foundation implemented | In Progress | `wiki_lint.py` validates proposal Markdown deterministically; `knowledge_graph.py` rebuilds isolated derived page/evidence/proposal edges idempotently |
| 2026-07-21 | P4 persisted evaluation baseline implemented | In Progress | `wiki_evaluator.py` stores project-local citation/SOP/content cases, measures candidate coverage, and truthfully reports missing baselines as unavailable |
| 2026-07-21 | P4 proposal publication gate implemented | In Progress | `proposal_gate.py` stages all operations in an atomic Vault adapter, blocks missing baselines/lint/source failures, and changes proposal/source state only after a successful staged publish |
| 2026-07-21 | P5 durable scheduler foundation implemented | In Progress | `scheduler.py` persists safe schedule intent, calculates next runs, claims project-scoped idempotent runs, and records synchronous mode as unavailable rather than active |
| 2026-07-21 | Obsidian Vault configured and filesystem adapter implemented | Complete | Local `OBSIDIAN_VAULT_ROOT` points to the user's configured Vault; `FilesystemWikiVault` stages and swaps only `projects/<project_id>/` without touching root notes or `.obsidian` |
| 2026-07-21 | Default project and first Obsidian sync completed | Complete | Created BSC project `default`, mapped it to `projects/default/`, created project `AGENTS.md`, and imported the non-empty root Markdown note as validated evidence |
| 2026-07-21 | Weekly distillation generator implemented | In Progress | `distillation.py` atomically produces source-backed knowledge action, content creation, and context-pack Markdown outputs; it blocks empty/cross-project evidence and write conflicts |
| 2026-07-21 | Weekly distillation task and Beat deployment surface implemented | In Progress | `knowledge.execute` loads persisted runs, writes grounded bundles to the configured Vault, records output paths, and reports unavailable inputs truthfully; Celery autodiscovers it and Docker has a dedicated Beat service |
| 2026-07-21 | Horizon intelligence adapter and architecture research implemented | Complete | Deep-read Horizon's staged multi-source pipeline, scoring, enrichment, storage, and MCP contracts; added a filtered/enriched stage importer that preserves run/provenance metadata as validated BSC evidence |
| 2026-07-21 | P6 workspace read API implemented | In Progress | Added project-scoped workspace, source, run, graph, and schedule responses with existing knowledge authorization; source responses redact immutable raw evidence content |
| 2026-07-21 | P6 MCP read tools and HTTP contract implemented | In Progress | Added `wiki_guide`, `wiki_search`, and `wiki_graph` to stdio MCP and HTTP JSON-RPC with mandatory project scope and no raw Vault/evidence-body access |
| 2026-07-21 | Governed REST/MCP write commands implemented | Complete | Shared `WikiCommandService` now creates proposal-only updates, lints, publishes through all gates, persists eval cases, schedules work, and queues only when real Celery is available |
| 2026-07-21 | Published Wiki persistence completed | Complete | One database transaction records published page metadata/revisions, active citations, derived graph edges, proposal state, and source lifecycle after the Vault's atomic swap |
| 2026-07-21 | Weekly distillation registry completed | Complete | The task persists the three semantic output paths and a deterministic source cutoff; a path-ordering defect was detected and corrected by a focused regression test |
| 2026-07-21 | Knowledge workspace review surface expanded | In Progress | The data-backed workspace now loads proposals, persisted pages/revisions/citations and weekly records; it can lint and request gated publication without fabricating state |
| 2026-07-21 | Browser credential boundary corrected | Complete | Knowledge requests use the existing authenticated fetch wrapper with an in-memory key only; no session cookie or local-storage credential is created for `/knowledge/*` |
| 2026-07-21 | Persistent schedule reconciliation implemented | Complete | Beat now invokes a one-minute reconciler that atomically claims due work, queues it, advances only after submission, and releases failed submissions for retry |
| 2026-07-21 | Docker knowledge-volume consistency corrected | Complete | API, Celery Worker, and Beat now share `/data/bsc_cloud.db` and the same `/vault` mount; prior Worker configuration could not execute scheduled Vault work correctly |
| 2026-07-21 | MCP published-page reader implemented | Complete | `wiki_read` now returns a project-scoped published revision, citation metadata, and revision ledger through both stdio and HTTP JSON-RPC |
| 2026-07-21 | Durable knowledge run events and SSE replay implemented | Complete | Every persisted run status appends a monotonic project/run event; REST replay and SSE stream only emit stored events and close after a terminal run |
| 2026-07-21 | Deterministic knowledge health implemented | Complete | Health derives citation coverage, orphan/uncited/stale pages, dangling citations, eligible-evidence gaps, and pending proposals from persisted records without synthetic scores |
| 2026-07-21 | Project Wiki bootstrap implemented and executed | Complete | Added a no-overwrite initializer and ran it for `default`, creating the missing managed overview/index/log files beneath `D:\bsc\projects\default\wiki` |
| 2026-07-21 | Obsidian source-sync execution wired and executed | Complete | `source_sync` now runs the managed-directory-excluding importer; the first real `default` scan completed with zero user notes rather than inventing evidence |
| 2026-07-21 | Evaluation trend and richer distillation context completed | Complete | Evaluation outcomes now persist per run/proposal and weekly distillation includes published Wiki pages rather than only source evidence |
| 2026-07-21 | Horizon HTTP Sidecar adapter completed | Complete | Added opt-in bounded staged-export client with API configuration, credential redaction, response validation, injectable transport, and no direct authority over BSC publication |
| 2026-07-21 | Workspace persisted run timeline completed | Complete | Selecting a run now loads its scoped replayed event ledger and displays real event sequences/types in the Knowledge workspace |
| 2026-07-21 | Manual local task execution and workspace sync control completed | Complete | Explicit local runs now execute through the auditable task path even without Celery; the workspace exposes the same governed Obsidian sync command |
| 2026-07-21 | Local authenticated Wiki runtime configured and smoke-tested | Complete | Added a generated local API key to ignored `.env`; latest application instance authenticated `default` workspace read and synchronous source sync successfully |
| 2026-07-21 | Obsidian Vault remapped after user repository repair | Complete | Detected the actual `.obsidian` Vault at `D:\bsc\bsc`, remapped `default`, bootstrapped a separate managed project directory, and synced without touching user notes |
| 2026-07-21 | Source supersession graph and workspace approval completed | Complete | Changed same-origin sources now retain immutable versions plus `source_supersedes_source` graph edges; validated evidence has an explicit scoped UI/API approval action |
| 2026-07-21 | Structured Obsidian source sync completed | Complete | Extended sync to Markdown, text, JSON, and Canvas; the repaired Vault's Canvas was captured as validated immutable evidence |
| 2026-07-21 | Real LLM Wiki maintenance executor completed | Complete | `wiki_maintenance` now constructs bounded page/source/rule context, invokes the existing SOP LLM adapter only with an explicit real provider, and persists a reviewable proposal/run result |
| 2026-07-21 | Docker full deployment attempted | Blocked External | Compose resolved correctly with the repaired Vault mount, but Docker Desktop could not reach Docker Hub to pull `redis:7-alpine`; no containers were created |
| 2026-07-21 | Docker full deployment retried after VPN enabled | Blocked External | A fresh `docker compose --profile full up -d --build` remained stuck before creating services; direct TCP verification to `registry-1.docker.io:443` failed, and `docker compose ps` remained empty |
| 2026-07-21 | Latest local API end-to-end smoke | Complete | Isolated latest-code server on `127.0.0.1:8001` authenticated `default`, reported its configured Vault, completed real `source_sync`, and replayed four durable run events |
| 2026-07-21 | Browser Knowledge workspace acceptance | Partially Complete | The current Vite workspace rendered the knowledge overlay, in-memory access-key boundary, Sync/Maintain/Refresh controls, evidence/graph/run/automation/review/published-Wiki/distillation/health panels; authenticated data rendering remains coupled to the user-owned legacy `8000` proxy process |

## Implementation Sequence Status

1. P1 vault contracts and schema: complete for contracts, schema, repository, and optional config. Filesystem Vault resolver/bootstrap remains deferred until Obsidian is configured.
2. P2 source capture and Horizon adapter: complete for immutable database evidence capture, trust policy, Horizon item contract, idempotency, and lifecycle guards. Obsidian scan and live Horizon HTTP client are still pending.
3. P3 compiler and project context: complete for rule parsing, bounded context construction, provider-injected draft compilation, provenance/path validation, run/proposal audit records, and an opt-in SOP Builder context bridge. Filesystem-aware page snapshots remain pending.
4. P4 validation, Knowledge Graph, and eval gates: deterministic lint, derived graph edges, persisted evaluation baselines, an atomic in-memory adapter, and a project-scoped Obsidian filesystem adapter are implemented. Page/citation persistence, graph rebuild after publish, and durable recovery remain pending.
5. P5 automation: durable schedule intent, safe cadence validation, next-run calculation, idempotent run claims, truthful unavailable state, and source-backed weekly distillation generation are implemented. Celery task execution, Beat reconciliation, and the scheduled task-to-distillation wiring remain pending.
6. P6 API/MCP: read API plus governed proposal/lint/publish/eval/schedule/run REST commands, replayable run events/SSE, and nine Wiki MCP tools are implemented. Full contract/permission coverage remains pending.
7. P7 workspace: the data-backed Knowledge overlay now includes evidence, graph, runs, schedules, proposal operations with lint/publish controls, persisted Markdown/revision/citation inspection, and weekly records. A full three-column navigation model, source inspector selection, health trends, mobile pane tabs, and authenticated browser acceptance remain pending.
8. P8 full integration and release verification: published page/citation/history/graph persistence, distillation registry, Beat reconciliation, Compose authority wiring, durable run events, and full knowledge/API regression are complete. Real Docker startup/worker/Beat validation and authenticated browser acceptance remain pending; the current blocker is Docker Hub TCP connectivity, not an application failure.

## Deviations And Decisions

- The implementation will adopt LLM Wiki's architecture, not copy or fork its codebase.
- `OBSIDIAN_VAULT_ROOT` is deployment configuration. No local Vault path was discovered or hard-coded.
- Because Obsidian is not ready, no code reads, writes, bootstraps, scans, or mutates a Vault directory.
- P2 is currently implemented as the temporary focused module `app/knowledge/wiki_source_capture.py` instead of the eventual split `source_registry.py`, `source_policy.py`, and `horizon_client.py`. This keeps early behavior cohesive while contracts are still small.
- `knowledge_sources.raw_content` is an additive immutable evidence field. Capture never updates it; deduplication reuses the original row instead of overwriting evidence.
- P3 compilation is deliberately provider-injected and proposal-only: malformed output creates a failed `KnowledgeRun`; no Vault file, published page, graph, or source status changes during compilation.
- The SOP bridge is opt-in and dependency-injected. When disabled it preserves legacy retrieval/generation inputs; when enabled it refuses cross-project context packs and exposes `_knowledge_context` metadata in the SOP result.
- P4 graph rebuild accepts only successfully published page snapshots from a future publication adapter; it never treats untrusted model declarations as graph state.
- Evaluation without project cases has status `unavailable`, not `passed`; an eventual proposal gate must reject this status unless an audited administrator override supplies a reason.
- `InMemoryWikiVault` is a real transactional contract test double, not a production filesystem adapter. It establishes all-or-nothing proposal semantics now; the future Obsidian adapter must retain staged commit/rollback behavior.
- The local Vault is `C:\Users\34216\Documents\Obsidian Vault`; BSC is enabled locally and may write only beneath `projects/<project_id>/`. The `.env` entry is ignored by Git and no pre-existing root note or Obsidian configuration was modified.
- Initial real sync for project `default`: scanned 1 non-empty Markdown note, created 1 evidence record (`欢迎.md`, status `validated`), and skipped 1 empty note. A second sync created 0 records and reported 1 duplicate. Local Vault files are never auto-promoted to publishable evidence.
- Vault connection corrected at user direction: `default` now uses the dedicated root `D:\bsc`, with `projects/default/AGENTS.md` created and repository metadata updated. The prior Documents Vault was left untouched. The first sync against `D:\bsc` returned zero files because the new dedicated Vault is currently empty.
- Weekly distillation is evidence-gated: it generates `knowledge-action.md`, `content-creation.md`, and `context-pack.md` under `distillations/YYYY-Www/` only when the supplied sources are project-scoped and non-empty. No empty D:\bsc report was fabricated.
- `knowledge.execute` now executes persisted weekly-distillation runs against the configured Vault. It leaves source status unchanged and writes only output paths/revision state to the run; recurring schedule reconciliation still needs to enqueue this task from enabled schedule records.
- Horizon is integrated as an intelligence sidecar, not a second source of truth. BSC imports only selected `filtered`/`enriched` `ContentItem` outputs, preserves score/run/URL metadata, and still requires BSC validation, citations, evaluation, and a proposal gate before Obsidian publication.
- Workspace API is additive under `/knowledge`; it requires explicit project scope and reuses existing admin/project-reader authorization. It exposes only provenance metadata for sources, never `raw_content`.
- Wiki MCP tools use the same project-required, metadata-only read boundary. Mutating MCP capabilities remain pending and must create governed proposals/runs rather than filesystem writes.
- Wiki REST and MCP mutations now use `WikiCommandService`; they cannot write arbitrary paths, raw source bodies, or files outside a configured project Vault. Publication always reconstructs the stored proposal and runs existing lint/source/eval gates.
- A publication is durable only after the Vault snapshot succeeds. Its database transaction then records pages, immutable revision snapshots, citations, derived graph edges, proposal publication, and source processing together; a database failure restores the prior Vault snapshot.
- Distillation registry fields are assigned by required filenames rather than generator ordering, so the UI and audit history retain the correct semantic artifact links.
- Celery Beat runs `knowledge.reconcile_schedules` every minute. It reads due persistent schedules, creates an idempotent project/job/due-time claim, enqueues `knowledge.execute`, then advances the schedule with an optimistic expected-next-run check. Failed queue submission is visible as a failed run and remains eligible for retry.
- Compose now mounts the configured host Vault into all three services that can read/write project Wiki state. This is required for deterministic page publication and weekly distillation across API, Worker, and Beat containers.
- `wiki_read` exposes only published Wiki bodies and citation/revision metadata, never raw immutable evidence. It shares the existing mandatory project scope and MCP authentication boundary.
- Knowledge run events are persisted in `knowledge_run_events` with monotonic per-run sequence. Reconnect callers supply `after_sequence`; SSE replays only subsequent durable events and terminates after a terminal run, avoiding inferred progress.
- Health metrics are evidence-derived. Empty projects use `citation_coverage: null` and evaluation `unavailable`, rather than reporting zero as a fabricated quality score.
- Bootstrap creates only missing `AGENTS.md`, `wiki/overview.md`, `wiki/index.md`, and `wiki/log.md` under `projects/<project_id>/`; it never overwrites existing project or Vault-root files. The `default` project kept its existing `AGENTS.md` and received the three missing Wiki pages.
- `source_sync` is now a real executor job: it scans the configured Vault, excludes `.obsidian` and all BSC-managed `projects/` output, captures only user-authored Markdown as immutable evidence, and persists ordered run events/results.
- Every evaluation result, including missing baselines, is persisted with status/score/findings and optional proposal/revision links. Health now exposes the latest persisted evaluation rather than an inferred trend. Weekly distillation includes the current published page catalog in its action and context outputs.
- Horizon now has a safe HTTP client in addition to the immutable import adapter. It only requests configured `filtered`/`enriched` staged exports, rejects malformed/oversized responses and private/loopback targets by default, and remains disabled until explicit deployment configuration is supplied.
- The workspace run ledger now selects a run and reads its persisted event history via `/knowledge/runs/{run_id}/events`; it does not simulate progress locally.
- Local mode distinguishes unavailable recurring scheduling from an explicit manual request. Manual source sync (and other supported task types) now records a queued/running/terminal run through the same execution contract; the workspace Sync control invokes this endpoint.
- A cryptographically generated `API_KEY` is now present only in ignored local `.env`, allowing the security-required Knowledge workspace authorization flow to operate. The secret was not logged, committed, or placed into frontend source.
- The actual Obsidian Vault is `D:\bsc\bsc` (it contains `.obsidian`). BSC now writes only under `D:\bsc\bsc\projects\default`; the prior outer `D:\bsc\projects\default` was left untouched. The imported Obsidian welcome note remains `validated` pending deliberate user approval.
- Source changes at the same `(project_id, source_type, origin)` create a new immutable source, mark the prior nonterminal version `superseded`, and persist a `source_supersedes_source` edge. The workspace approval action changes only `validated -> eligible` through the existing lifecycle guard.
- Obsidian sync now includes `.md`, `.txt`, `.json`, and `.canvas` source files with extension provenance. It continues to exclude `.obsidian`, empty/unreadable files, and all BSC-managed `projects/` content.
- Wiki maintenance reuses the existing OpenAI-compatible SOP LLM client behind a strict structured proposal adapter. Mock mode is deliberately reported as `unavailable`; it cannot fabricate a Wiki proposal. Local `.env` now explicitly selects `deepseek`, but no model call has been made against the welcome/canvas examples.
- Docker `full` deployment was attempted with the actual local `.env` (`OBSIDIAN_VAULT_HOST_PATH=D:\bsc\bsc`, real API/LLM configuration). Docker Desktop attempted a direct HTTPS connection to Docker Hub and timed out before Redis/Ollama could be pulled; `docker compose ps` confirmed no partial containers remain.
- The browser workspace deliberately asks for an access key only in component memory and routes calls through `fetchWrapper`. The key is never persisted; a fresh page must authenticate again. `/knowledge/*` retains its existing no-anonymous-session policy.
- Scheduler cron is intentionally constrained to every 5-59 minutes or daily/weekly fixed times. This makes next-run calculation and operational load bounded; unsupported cron expressions are rejected rather than silently misinterpreted.
- Trusted sources may be automatically eligible; automatic publication still requires deterministic validation and a non-regressing evaluation result.
- The existing Artifact Graph remains a separate business runtime concern.

## Verification Record

- Documentation set: 11 new Markdown files under existing `specs`, `plans`, and `worklogs` directories.
- Plan dependency wording is consistent: P1 -> P2 -> P3 -> P4; P5/P6 parallel; P7 consumes P6; P8 is final integration.
- P1/P2 focused tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_contracts.py tests\knowledge\test_wiki_schema.py tests\knowledge\test_wiki_repository.py tests\knowledge\test_wiki_source_capture.py -q` -> 9 passed, 1 Starlette/httpx deprecation warning.
- P1-P3 focused tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_contracts.py tests\knowledge\test_wiki_schema.py tests\knowledge\test_wiki_repository.py tests\knowledge\test_wiki_source_capture.py tests\knowledge\test_wiki_rules.py tests\knowledge\test_context_pack.py tests\knowledge\test_wiki_compiler.py -q` -> 18 passed, 1 Starlette/httpx deprecation warning.
- P4 lint/graph/compiler tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_lint.py tests\knowledge\test_knowledge_graph.py tests\knowledge\test_wiki_compiler.py tests\knowledge\test_wiki_repository.py -q` -> 8 passed, 1 Starlette/httpx deprecation warning.
- P3 SOP bridge tests: `.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_wiki_methodology_bridge.py tests\orchestrator\test_sop_methodology.py tests\orchestrator\test_agents.py -q` -> 17 passed.
- P4 evaluation tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_evaluator.py tests\knowledge\test_wiki_schema.py tests\knowledge\test_wiki_repository.py -q` -> 4 passed, 1 Starlette/httpx deprecation warning.
- P4 publication-gate tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_proposal_gate.py tests\knowledge\test_wiki_lint.py tests\knowledge\test_wiki_evaluator.py tests\knowledge\test_wiki_repository.py -q` -> 7 passed, 1 Starlette/httpx deprecation warning.
- P5 scheduler tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_scheduler.py tests\knowledge\test_wiki_schema.py tests\knowledge\test_wiki_repository.py -q` -> 5 passed, 1 Starlette/httpx deprecation warning.
- Obsidian filesystem/sync verification: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_vault.py tests\knowledge\test_wiki_sync.py tests\knowledge\test_proposal_gate.py -q` -> 5 passed, 1 Starlette/httpx deprecation warning.
- Weekly distillation tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_distillation.py tests\knowledge\test_vault.py -q` -> 4 passed, 1 Starlette/httpx deprecation warning.
- Knowledge task/scheduler tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_knowledge_tasks.py tests\knowledge\test_scheduler.py tests\knowledge\test_distillation.py -q` -> 7 passed, 1 Starlette/httpx deprecation warning.
- Horizon import tests: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_horizon_import.py tests\knowledge\test_wiki_source_capture.py tests\knowledge\test_knowledge_tasks.py -q` -> 7 passed, 1 Starlette/httpx deprecation warning.
- Full knowledge regression after Horizon/task integration and SQLite lifecycle repair: `.\.venv\Scripts\python.exe -m pytest tests\knowledge -q` -> 196 passed, 1 Starlette/httpx deprecation warning.
- Repaired a pre-existing SQLite test-order failure: backend thread-local keys now use a per-instance UUID, so a collected backend cannot close a newer backend's reused `id(self)` connection.
- Workspace API test: `.\.venv\Scripts\python.exe -m pytest tests\api\test_knowledge_workspace_api.py -q` -> 1 passed, 1 Starlette/httpx deprecation warning.
- Wiki HTTP MCP contract: `.\.venv\Scripts\python.exe -m pytest tests\api\test_wiki_http_contract.py tests\api\test_knowledge_workspace_api.py -q` -> 2 passed, 1 Starlette/httpx deprecation warning.
- Final knowledge regression for this slice: `.\.venv\Scripts\python.exe -m pytest tests\knowledge -q` -> 188 passed, 1 Starlette/httpx deprecation warning.
- Final methodology/SOP regression for this slice: `.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_wiki_methodology_bridge.py tests\orchestrator\test_methodology_bridge.py tests\orchestrator\test_sop_methodology.py tests\orchestrator\test_agents.py -q` -> 22 passed.
- Existing schema/repository regression: `.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_schema_migration.py tests\knowledge\test_schema_production.py tests\knowledge\test_repo_production.py tests\knowledge\test_isolation.py -q` -> 7 passed, 1 Starlette/httpx deprecation warning.
- `git diff --check`: passed; PowerShell reported LF-to-CRLF warnings for touched Python files.
- Unrelated runtime modifications remain excluded: `app/bsc_cloud.db`, `app/bsc_cloud.db-shm`.
- Governed command/API/MCP focused regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_commands.py tests/api/test_wiki_http_contract.py tests/api/test_knowledge_workspace_api.py -q` -> 3 passed, 1 existing Starlette/httpx deprecation warning.
- Publication persistence and weekly registry regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_commands.py tests/knowledge/test_knowledge_tasks.py tests/api/test_knowledge_workspace_api.py -q` -> 4 passed, 1 existing Starlette/httpx deprecation warning.
- Frontend static validation after workspace API changes: `npm run check` and `npm run build` passed. Vite reports an existing 577 kB entry-chunk advisory, not a build failure.
- Authentication and workspace regression after removing an unsafe knowledge-session cookie side effect: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_benchmark_api.py tests/knowledge/test_api_auth.py tests/test_auth_middleware.py tests/knowledge/test_wiki_commands.py tests/knowledge/test_knowledge_tasks.py tests/api/test_knowledge_workspace_api.py tests/api/test_wiki_http_contract.py -q` -> 18 passed, 1 existing Starlette/httpx deprecation warning.
- The full knowledge/API run reached 200 passing tests but initially exposed the benchmark session leakage caused by the rejected temporary session behavior; focused re-run after removal passes. The next full regression should be repeated in the P8 release environment.
- Schedule reconciliation regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_scheduler.py tests/knowledge/test_wiki_schema.py -q` -> 7 passed, 1 existing Starlette/httpx deprecation warning.
- Docker configuration validation: `OBSIDIAN_VAULT_HOST_PATH=D:\bsc API_KEY=verification-only LLM_PROVIDER=mock KNOWLEDGE_WIKI_ENABLED=true docker compose config --quiet` -> passed. Docker image pull/container execution remains unverified because it depends on the external registry/network.
- MCP reader regression: `./.venv/Scripts/python.exe -m pytest tests/api/test_wiki_http_contract.py tests/knowledge/test_wiki_commands.py -q` -> 2 passed, 1 existing Starlette/httpx deprecation warning; `npm run check` passed.
- Durable event/SSE regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_repository.py tests/knowledge/test_knowledge_tasks.py tests/api/test_knowledge_workspace_api.py -q` -> 6 passed, 1 existing Starlette/httpx deprecation warning.
- Health/UI regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_health.py tests/api/test_knowledge_workspace_api.py -q` -> 3 passed; `npm run check` and `npm run build` passed. Vite retains the existing >500 kB entry-chunk advisory.
- Bootstrap regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_bootstrap.py tests/knowledge/test_wiki_commands.py tests/knowledge/test_proposal_gate.py tests/api/test_knowledge_workspace_api.py -q` -> 6 passed, 1 existing Starlette/httpx deprecation warning. Local bootstrap result: `default` created `wiki/overview.md`, `wiki/index.md`, and `wiki/log.md` under `D:\bsc\projects\default`.
- Source-sync regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_scheduler.py -q` -> 8 passed, 1 existing Starlette/httpx deprecation warning. Local `default` source-sync run `2251b4a62bd5` completed with `scanned=0, created=0, duplicates=0, skipped=0` because only managed files are currently present.
- Evaluation/distillation context regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_distillation.py tests/knowledge/test_wiki_evaluator.py tests/knowledge/test_proposal_gate.py -q` -> 10 passed, 1 existing Starlette/httpx deprecation warning.
- Horizon client/import regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_horizon_client.py tests/knowledge/test_horizon_import.py tests/knowledge/test_wiki_source_capture.py -q` -> 7 passed, 1 existing Starlette/httpx deprecation warning; `python -m compileall -q app/knowledge` passed.
- Run timeline/UI regression: `npm run check`, `npm run build`, and `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py tests/knowledge/test_wiki_repository.py -q` -> 3 passed. Vite retains the existing >500 kB entry-chunk advisory.
- Manual execution/workspace sync regression: `npm run check`, `npm run build`, and `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_commands.py tests/knowledge/test_knowledge_tasks.py tests/api/test_knowledge_workspace_api.py -q` -> 8 passed, 1 existing Starlette/httpx deprecation warning. Vite retains the existing >500 kB entry-chunk advisory.
- Authenticated local smoke verification against the latest app instance: `GET /knowledge/workspaces/default` -> `200 configured`; `POST /knowledge/runs {project_id: default, job_type: source_sync}` -> `200 completed synchronous`.
- Vault remap result: bootstrap created `D:\bsc\bsc\projects\default\AGENTS.md` plus Wiki scaffold; source sync scanned one non-empty user Markdown note, detected the existing immutable content hash as a duplicate, and skipped one empty note. Source graph/UI approval regression: `npm run check` and `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py tests/knowledge/test_wiki_source_capture.py tests/knowledge/test_wiki_sync.py -q` -> 10 passed, 1 existing Starlette/httpx deprecation warning.
- Structured sync regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_sync.py tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_wiki_source_capture.py -q` -> 11 passed, 1 existing Starlette/httpx deprecation warning. Latest `default` sync: `scanned=2, created=1, duplicates=1, skipped=1`; `未命名.canvas` and `欢迎.md` are both `validated` evidence.
- Maintenance executor regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_wiki_compiler.py tests/knowledge/test_wiki_rules.py -q` -> 12 passed, 1 existing Starlette/httpx deprecation warning; `python -m compileall -q app/knowledge` passed.
- Full deployment attempt: `docker compose --profile full up -d --build` -> failed at `registry-1.docker.io` pull for `redis:7-alpine` because Docker Desktop has no configured HTTPS proxy/direct connection timed out. `docker compose --profile full ps` -> no running or created services. `docker compose --profile full config --quiet` remains successful.
- Latest full regression after Vault remap, real maintenance adapter, source supersession, structured sync, and local auth setup: `./.venv/Scripts/python.exe -m pytest tests/knowledge tests/api/test_knowledge_workspace_api.py tests/api/test_wiki_http_contract.py -q` -> **212 passed**, 1 existing Starlette/httpx deprecation warning. `npm run build`, `docker compose --profile full config --quiet`, and `git diff --check` also passed; Vite retains the existing >500 kB entry-chunk advisory.
- Docker retry after the user enabled VPN: `docker compose --profile full up -d --build` produced no services before it was stopped as hung; `Test-NetConnection registry-1.docker.io -Port 443` reported `TcpTestSucceeded: False`; `docker compose --profile full ps` remained empty. Production container validation is therefore still not claimed as passed.
- Latest-code local smoke: a separate `uvicorn app.main:app --host 127.0.0.1 --port 8001` process accepted the ignored local API key, returned `configured=True`, `sources=2`, and `runs=3` for `GET /knowledge/workspaces/default`; an explicit `POST /knowledge/runs` source-sync completed and its scoped event endpoint returned four ordered events ending in `knowledge.run.completed`.
- Browser acceptance: the active Vite page rendered the Knowledge workspace after selecting its `Knowledge` control and showed the required project/access-key controls plus all operational panels. It correctly remained unauthenticated until an access key is provided. The running frontend proxies `/knowledge` to the pre-existing non-reloading `8000` server, so authenticated browser data acceptance must be repeated after that user-owned server is restarted to the latest code or a dedicated proxy is launched.

## Current Handoff Contract

## Latest Verification (2026-07-21)

- VPN restored Docker Hub access. `docker pull redis:7-alpine` completed, Redis started as `bsc-backend-redis-1`, and `redis-cli ping` returned `PONG`.
- `docker compose build bsc-backend` completed with the current frontend and backend. A health-checked API container runs at `http://127.0.0.1:8002/live`; it returned `200 {"status":"ok"}` after image rebuild and restart.
- A real deployment defect was fixed: Celery CLI expected `app.core.celery_app.celery`, while the module exposed only a factory. The conventional module entrypoint now reuses `get_celery_app()`. Worker and Beat are launched independently with the Dockerfile HTTP healthcheck disabled; the Compose services carry the same disablement.
- Docker recovery was verified. After a complete API/Worker/Beat restart with persisted Redis/data/Vault mounts, Beat dispatched `knowledge.reconcile_schedules` and Worker consumed it successfully with `queued=0`, `duplicates=0`, `failures=0`.
- Filesystem lifecycle E2E was added. It uses a temporary mapped Vault and validates immutable Obsidian and Horizon evidence, rule preservation, proposal compilation, deterministic evaluation, atomic publication, revisions, citations, graph edges, and processed source state.
- Two correctness defects were fixed during E2E hardening: all configured Vault roots are excluded from source sync (not only `projects/`), and append operations on existing Markdown pages no longer require duplicate YAML frontmatter. Compensating proposals may cite previously published immutable evidence.
- Browser acceptance against the latest dedicated `5176 -> 8001` development pair verified real project data, graph filtering by edge/type/status, desktop layout, mobile pane switching, and ECharts mount lifecycle. At 390x844, hidden inspector charts were not mounted; selecting Inspect mounted all charts at a nonzero 340x180 size. The browser viewport was restored afterward.
- Current regression result: `./.venv/Scripts/python.exe -m pytest tests/knowledge tests/integration tests/api/test_knowledge_workspace_api.py tests/api/test_wiki_http_contract.py tests/test_celery_app.py tests/test_docker_compose_contract.py -q` -> **226 passed**, 1 existing Starlette/httpx deprecation warning. `npm run check`, `npm run build`, `docker compose config --quiet`, and `git diff --check` passed before the final documentation update.
- Remaining release gates are recorded in P8's execution ledger: configure a real LLM provider for maintenance, configure a Horizon endpoint, add a safe review/diff/distillation browser fixture, and run dedicated two-principal MCP transport E2E. These are not marked complete.

- `SourceCaptureService.capture` accepts a normalized `CapturedSourceInput`, computes the content hash, checks same-project duplicates, persists a `SourceRecord`, and returns whether a new record was created.
- `SourceTrustPolicy.assess` promotes trusted/manual or configured trusted-source evidence to `eligible`; unknown external feeds remain `validated`.
- `HorizonSignal.to_source_input` maps Horizon radar items into immutable `horizon_signal` evidence records without performing network calls.
- `SourceCaptureService.transition_source` enforces `SourceStatus` lifecycle rules and rejects illegal regressions.
- `WikiRepository` now exposes `find_source_by_content_hash` and `update_source_status`; all queries remain project-scoped.

## Overnight Execution Management (2026-07-22)

| Workstream | Status | Current evidence / next action |
|---|---|---|
| PRD/P1-P8 evidence audit | Complete | Audited against the active PRD and P8 ledger. Identified project `raw/`/`inbox/` capture and first-class revision restoration as concrete gaps. |
| Project source capture | In progress | Sync now permits the active project's `raw/` and `inbox/` directories while excluding generated Wiki/rules/distillation content and every other configured project root. Focused tests pass; full regression is pending this batch. |
| Revision recovery | In progress | Command, REST contract, typed client, and workspace proposal entry point are being added. The restore operation creates a draft and must still pass lint/evaluation/publication. |
| Multi-project API/MCP E2E | Pending | Add two-principal fixtures after the recovery batch passes. |
| PRD-to-SOP and weekly idempotency E2E | Pending | Add cross-project context and retry/cutoff fixtures after API/MCP isolation coverage. |
| Browser acceptance | Pending | Seed a safe review/diff/run/distillation fixture and verify desktop/mobile navigation after all API changes. |
| External configuration | Deferred until all local work is complete | A real Horizon endpoint/API key and an approved real Wiki LLM provider are the only expected external dependencies. No credential is requested or logged. |

## Overnight Execution Management (2026-07-22, Completion Batch)

| Workstream | Status | Evidence |
|---|---|---|
| Project raw/inbox source capture | Complete | `ObsidianSyncService` now imports only the mapped project's `raw/` and `inbox/` material while excluding managed Wiki/rules/distillation output and all other mapped project roots. `tests/knowledge/test_wiki_sync.py tests/integration/test_knowledge_wiki_e2e.py` passed (4 tests). |
| Governed revision recovery | Complete | Historical page content is recovered only by a normal draft proposal, with current-evidence eligibility checks and append-only log protection. Command/API/workspace tests pass; browser acceptance created and rendered a real three-operation restore draft without publishing it. |
| MCP project isolation | Complete | Wiki MCP tools now resolve global/project principals and enforce project/read-write scope. HTTP JSON-RPC E2E proves project A admin cannot read/write B and project A reader cannot write A; `tests/integration/test_knowledge_mcp_e2e.py` passed. |
| PRD-to-SOP grounding | Complete | `WikiContextProvider` now supplies project rules, published pages/decisions, eligible/processed evidence, recent evaluation summaries, and latest weekly context. The default methodology bridge enables it only for a configured active project. Two-project E2E proves A's prompt has no B material; no-vault retains legacy behavior. |
| Weekly recovery and cutoff | Complete | Weekly outputs and run references now carry a stable source cutoff. E2E proves unavailable-without-evidence, retry lineage after evidence arrival, deterministic same-week reuse, and one durable distillation record. |
| CORS preflight | Complete | `AuthMiddleware` now passes `OPTIONS` to CORS middleware; otherwise authenticated cross-origin development clients fail before reaching the API. Added regression coverage. |
| Browser acceptance | Complete | Isolated fixture API/Vault plus built frontend verified desktop/mobile source provenance, page/revision view, restore-to-diff, graph node filtering, weekly documents/source cutoff, durable run events, and nonblank mobile ECharts. Fixture uses a temporary DB/Vault and `browser-verification` test key only. |
| External configuration | Still deferred | Live Horizon and real Wiki-maintenance LLM remain intentionally unconfigured; no source claims either integration executed. |

### Completion-Batch Verification

- `./.venv/Scripts/python.exe -m pytest tests/integration/test_knowledge_mcp_e2e.py tests/api/test_wiki_http_contract.py tests/test_mcp_http.py tests/test_auth_middleware.py -q` -> 8 passed.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_context_pack.py tests/orchestrator/test_wiki_methodology_bridge.py tests/orchestrator/test_sop_methodology.py tests/integration/test_knowledge_sop_e2e.py -q` -> 8 passed.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_distillation.py tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_scheduler.py tests/integration/test_knowledge_celery.py -q` -> 12 passed.
- Browser fixture: `scripts/seed_knowledge_browser_fixture.py` populated an isolated mapped Vault/SQLite store; the 8003 API and 5178 fixture page used no user Vault or production key.
- Final regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge tests/integration tests/api/test_knowledge_workspace_api.py tests/api/test_wiki_http_contract.py tests/test_celery_app.py tests/test_docker_compose_contract.py -q` -> **231 passed**, 1 existing Starlette/httpx deprecation warning.
- Frontend release checks: `npm run check`, `npm run lint`, and `npm run build` passed. Lint reports 197 pre-existing warnings and no errors; the production build retains the known >500 kB chunk advisory.
- Latest Docker deployment: `docker compose build bsc-backend` rebuilt image `bsc-backend-bsc-backend:latest`; `bsc-backend-app-8002` returned `200 /live`, Redis returned `PONG`, and new Worker consumed `knowledge.reconcile_schedules` with `queued=0`, `duplicates=0`, and `failures=0`. Worker/Beat intentionally run with Docker healthchecks disabled because the image HTTP probe is not valid for Celery processes.
- Release scope: local Docker API/Redis/Worker/Beat and all automated local contracts are current. Live Horizon import and real Wiki maintenance remain external configuration gates; they are not represented as completed.

## Final Completion Audit (2026-07-22)

### Implementation Changes

- Added explicit `KNOWLEDGE_WIKI_AUTO_PUBLISH_ENABLED` and project mapping `metadata.auto_publish_enabled` policy. Automatic publication now requires both flags, trusted-only evidence, passing deterministic gates, and a durable audit run.
- Added administrator publication override with role `admin`, a meaningful reason, persisted lint/evaluation findings, and `knowledge.proposal.override.applied` audit event. Path, source eligibility, and revision integrity gates remain non-overridable.
- Added structured contradiction candidates for shared concepts/entities with conflicting claims ordered by source recency; the compiler exposes review findings without resolving them.
- Added typed terminal failure categories for task configuration, policy, transient dependency, compiler, gate, evaluation, and distillation outcomes.
- Added real Celery broker health probing. Celery-disabled and Redis-unreachable states now report `available:false, mode:manual`; manual work remains auditable and real queue submission never claims success without a reachable broker.
- Fixed the Knowledge workspace terminal-event replay loop: replaying an already-terminal run no longer replaces the selected run object and clears its events.
- Added root test isolation for local `.env` API/LLM settings so legacy tests do not inherit user credentials or thread-local providers.

### Final Verification

- Python: `766 passed, 5 skipped, 3 warnings` from the complete `pytest -q` run. Disposable PostgreSQL 16 then passed both knowledge and orchestrator contracts (`2 passed`). Linux production-image isolation/recovery/Celery suite passed (`6 passed`).
- Frontend: Vitest `9 passed`; `npm run check`, `npm run lint`, and `npm run build` passed. `npm audit --omit=dev` reported 0 vulnerabilities; `pip check`, Bandit, compileall, Compose config, and `git diff --check` passed.
- Runtime: latest image built; API `8002/live` returned `{"status":"ok"}`, Redis `PONG`, Worker/Beat healthy, Beat dispatch and Worker consumption returned `queued=0, duplicates=0, failures=0`. Restart preserved a completed run, event sequence `[1,2]`, schedule, and output references.
- Browser fixture: authenticated desktop at 1440x900 and mobile at 390x844 verified project connection, Wiki page, citation-to-source SHA-256 inspector, revision restore draft and Diff, Lint, run event sequence 1-4, graph filter/node navigation, weekly three-document/source cutoff view, mobile pane retention, no horizontal overflow, five 340x180 ECharts canvases with visible rendered series, and keyboard focus outline.

### External Boundaries

Live Horizon endpoint/API credentials and a real Wiki-maintenance LLM provider remain intentionally unconfigured. Their unavailable behavior is tested and documented; no run, source import, or publication is claimed for either external dependency.

## Final Runtime Rebuild (2026-07-22)

- Rebuilt `bsc-backend-bsc-backend:latest` after the Knowledge workspace terminal-event replay fix. The resulting image digest is `sha256:5d69a130026ffa321befdda19cca77f14c9ba89b0007b0949992ac83da5e5f66`.
- Replaced only `bsc-backend-app-8002`, `bsc-celery-worker`, and `bsc-celery-beat`. The deployment kept `bsc-backend_bsc-network`, the `bsc-data`/`bsc-output` volumes, and the user Vault bind `D:\bsc\bsc:/vault`; ports `8000`, `5174`, and the user Vault were not touched.
- Runtime proof: `GET http://127.0.0.1:8002/live` returned `{"status":"ok"}`, Redis returned `PONG`, all three containers are running on the new digest, and the authenticated workspace status reported `scheduler.available=true, mode=celery`.
- Beat dispatched `knowledge.reconcile_schedules`; Worker consumed it and returned `queued=0, duplicates=0, failures=0, recovered=0`.
- The mounted runtime database currently contains no project, schedule, or run rows. No synthetic records were created to make persistence appear complete; persistence/recovery remains covered by the disposable integration and restart tests recorded above.

## Requirement Audit Remediation (2026-07-22)

- Enforced the previously documentary-only feature flags: `KNOWLEDGE_WIKI_ENABLED` gates the new workspace/API and Wiki task execution; `KNOWLEDGE_OBSIDIAN_SYNC_ENABLED`, `KNOWLEDGE_SCHEDULES_ENABLED`, and `KNOWLEDGE_MCP_WRITE_ENABLED` independently gate sync, persistent scheduling, and MCP writes. Workspace responses now expose the active feature policy and the latest source-sync status.
- Closed a derived-index gap: source synchronization now projects the current authoritative Obsidian Wiki snapshot through `WikiSearchIndex`, so user-edited pages are searchable after sync rather than only being persisted in the Wiki metadata tables.
- Hardened filesystem isolation: Vault reads and Obsidian scans skip symlinks, and atomic publication refuses to replace a project containing symlinks. Tests cover outside-root symlinks where the Windows principal permits creation.
- Hardened Horizon URL isolation: protocol-relative stage escapes and cross-origin redirects are rejected before payload consumption; HTTP error statuses become non-sensitive adapter failures.
- Unified proposal provenance: source IDs declared on operations are merged into the proposal source set before lint, evaluation, automatic-publication trust checks, and processed-source transitions.
- New focused tests pass for feature-disabled API/MCP/task states, Wiki index synchronization, symlink isolation, Horizon URL safety, and operation-level provenance. Full Python regression after these remediations: `775 passed, 8 skipped, 3 warnings`.

## Horizon Native Run-Store Deployment (2026-07-22)

- Re-verified the supplied Horizon source and corrected the integration assumption: Horizon has no standalone API service. Its MCP `RunStore` writes reproducible stage artifacts under `data/mcp-runs/<run_id>/`.
- Added `HorizonRunStoreClient` and wired `horizon_capture` to prefer native run artifacts, with the bounded HTTP adapter retained only as a compatibility fallback. Capture audit events and output references now record `source_mode`.
- Added run ID traversal protection, read-only stage allow-listing (`filtered`/`enriched`), symlink rejection, response-size bounds, JSON shape validation, and missing-artifact failure handling.
- Added Docker contracts for a read-only `${HORIZON_RUNS_HOST_PATH}:/horizon-runs:ro` mount on API and Worker only. Beat receives no Horizon path or secret.
- Installed the supplied Horizon repository independently at `D:\bsc\horizon`, generated its documented local `data/config.json`, selected `deepseek/deepseek-chat`, and validated five enabled sources with no missing environment variables. Secrets remain in ignored local `.env` files and were not logged or committed.
- Runtime now uses `HORIZON_ENABLED=true`, host path `D:\bsc\horizon\data\mcp-runs`, and container path `/horizon-runs`. API and Worker see the path as read-only; API reports `horizon_mode=run_store`.
- Replaced the duplicate legacy API/Worker/Beat containers without deleting named volumes, Redis data, the runtime database, or `D:\bsc\bsc`. The Compose deployment is healthy at `http://127.0.0.1:8002/live`; Redis returns `PONG`; the sole Worker registers `knowledge.execute` and `knowledge.reconcile_schedules`.
- Focused adapter/task/Compose regression: `21 passed`, with one existing Starlette/httpx deprecation warning. `docker compose config --quiet` and `git diff --check` pass.
- Expanded knowledge/integration/API/Celery regression: `267 passed, 5 skipped`, with one existing Starlette/httpx deprecation warning. Python compileall also passes.
- Horizon live smoke exposed a Windows GBK console defect in upstream Rich output; rerunning with `PYTHONUTF8=1` resolved it without changing pipeline semantics.
- Executed a cost-bounded live Hacker News flow with five-story fetch cap and no enrichment/summary. Horizon fetched, scored, and retained 2 items in native run `run-20260722T081820Z-8618b8ef`.
- BSC runtime run `799e0e2467fd` consumed that run's `filtered_items.json` through the read-only mount and completed with `source_mode=run_store`, `accepted=2`, `created=2`. Project `horizon-radar` now contains two immutable live evidence records.

## Horizon Continuous Automation (2026-07-22)

- Closed the scheduled-capture contract gap: schedule claims do not contain a Horizon run ID, so `horizon_capture` now discovers the latest unimported native artifact, prefers `enriched`, and falls back to `filtered`.
- A second capture of the same run completes with `skipped=true` and a `knowledge.horizon.capture.skipped` event. It does not create duplicate evidence or a false dependency failure.
- Replaced the temporary recent-run window with a project-scoped database ledger of every completed Horizon run ID, so frequent skip runs cannot cause old artifacts to re-enter discovery after long-running operation.
- Added `scripts/run_horizon_pipeline.py` as an independently executed Horizon producer. It uses Horizon's own service and environment, enforces a single active producer, reclaims only stale lock files, redacts provider keys, atomically writes `producer-state.json`, and marks `bsc_ready_stage` in native run metadata.
- Fixed the API deployment's missing Redis broker/result environment. API schedule availability now resolves `redis://redis:6379/0` and returns `scheduler_broker_available=true`; Worker and Beat retain the same broker contract.
- Registered Windows task `BSC-Horizon-Daily-Radar` for 07:30 Asia/Shanghai with `StartWhenAvailable`, a two-hour execution limit, and `IgnoreNew` overlap policy. Its registered action was executed, returned Windows result `0`, and produced run `run-20260722T083443Z-91791055` with fetched=4, scored=4, kept=2, enriched=2.
- Initialized Obsidian project `projects/horizon-radar` with `AGENTS.md` and managed Wiki files. Persistent BSC schedule `abb271e1e30d65f65579d738` runs `horizon_capture` every 30 minutes in Asia/Shanghai.
- Celery queue proof: run `b320e0a6eb2c` automatically imported the scheduled-task artifact from `enriched_items.json` with accepted=2 and created=2. Forced due reconciliation then created schedule run `ab286a9a4fa6`, completed it as an idempotent skip, and advanced the next run to `2026-07-22T09:00:00+00:00`.
- Focused automation, scheduler, task, producer, and Compose contracts: `28 passed`, with one existing Starlette/httpx deprecation warning. Runtime project `horizon-radar` contains five immutable evidence records after the live proofs.
- Expanded knowledge/integration/API/Celery/producer regression: `275 passed, 5 skipped`, with one existing Starlette/httpx deprecation warning. Compileall, Compose config, and `git diff --check` pass.

## Isolated Workspace Revalidation (2026-07-26)

### Defect Corrected

- The Studio `Runtime access key` field could be rejected even when the target API accepted that key. `vite.config.ts` let a generic `.env` `API_KEY` silently override the key typed into Studio and let file-level proxy targets outrank the process-level target used by `start_isolated_studio.ps1`.
- The proxy now uses only an explicit process-level `BSC_LOCAL_API_KEY` for server-managed loopback authentication, gives explicit process targets precedence over file defaults, and forwards a caller's `Authorization` header when no managed local key is configured.
- `start_isolated_studio.ps1` clears the managed-key variable so browser acceptance always exercises the visible runtime-key control instead of inheriting an unrelated developer credential.

### Evidence

- `src/viteProxyAuth.test.ts`: 4 passing cases verify target precedence, no generic `API_KEY` fallback, explicit managed-key behavior, and production disabling.
- `npm.cmd run check`: passed after the proxy changes.
- Targeted backend regression passed: `66 passed` across Compose contracts, fixture isolation, growth distillation, knowledge tasks, and knowledge-workspace API tests.
- Full frontend regression passed: `14` test files and `113` tests. Production build completed, and lint completed with `0 errors` plus `203` pre-existing warnings.
- `docker compose config --quiet`, `git diff --check`, Docker API `/live` and `/ready` (`200`), and Docker Worker `celery inspect ping` (`pong`) passed.
- A standalone full `pytest -q` attempt exceeded 304 seconds while separate user/workflow single-file pytest processes were active. It is not recorded as passing; the targeted suite above is the verification used for this change.
- Direct authenticated request through `http://127.0.0.1:5190/knowledge/workspaces/browser-demo` returned `200` with `vault.connection.state=ready`, `sources=2`, and `runs=2`. The API was a temporary SQLite fixture backed by a temporary Vault and the known test key `browser-verification`.
- Desktop Studio acceptance verified authenticated project access, a ready Vault, page-to-citation-to-SHA-256 source provenance, two-operation proposal Diff, completed and failed durable runs with ordered events, graph filtering/node navigation, weekly three-document output with stable source cutoff, and the revision-history control.
- Mobile acceptance at `390x844` reported `documentWidth=384` and `bodyWidth=384`, so there was no horizontal overflow. Selecting the weekly bundle, switching `Navigate -> Workspace`, and returning preserved the selected `2026-W30` bundle and its stored documents.
- Visual inspection reached the health-trend region: five `306x180` ECharts canvases rendered source capture and proposal outcome series. The local application console contained no error entries.

### Boundary Statement

- This revalidation did not read a user Vault, Obsidian plugin code, `.env`, or external credentials. It did not claim a real Horizon import or a real Wiki LLM-maintenance run. Those integrations remain governed external runtime configuration, while their unavailable states remain visible in Studio.

## Lint Dependency Remediation (2026-07-26)

- Corrected `ProposalReview` state-reset dependencies in `src/components/KnowledgeWorkspace.tsx`. The effect now depends on stable `proposalId` and `proposalSourceIds` values rather than indirectly reading the full mutable proposal object. This preserves reset behavior when the selected proposal or its evidence changes, without a stale or over-broad Hook dependency.
- Targeted component verification: `npm.cmd run test:frontend -- src/components/KnowledgeWorkspace.test.tsx` -> `1` file, `9` tests passed.
- Complete frontend verification: `npm.cmd run test:frontend` -> `14` files, `113` tests passed; `npm.cmd run check` and `npm.cmd run build` passed.
- `npm.cmd run lint` completed with `0` errors and `202` pre-existing warnings. The corrected Knowledge workspace Hook warning is absent. The known production chunk-size advisory remains non-blocking.
- No full Python regression was claimed in this remediation because a prior full run exceeded its time limit while other workflows were active. This frontend-only correction did not change backend behavior.

## Real Wiki Maintenance Dependency Audit (2026-07-26)

### Runtime Evidence

- Rebuilt and deployed the current Knowledge image to the local Docker stack. `bsc-backend` is healthy on `8002`; PostgreSQL and Redis are healthy; the Celery Worker and Beat are running. `GET /live` and `GET /ready` both returned `200`, and `celery inspect ping` returned `pong`.
- Ran a real `wiki_maintenance` task for the mapped default project. Run `7d28107fad20` selected seven eligible sources and constructed a governed 12,451-character maintenance context. It did not use mock content and did not publish a synthetic proposal.
- The configured DeepSeek provider returned HTTP `402 Payment Required`. The persisted terminal state is `unavailable`, with the redacted error `Wiki LLM provider is unavailable (payment_required)`, failure code `wiki_llm_payment_required`, and four ordered durable events ending in `knowledge.run.unavailable`.
- The provider boundary is now typed: upstream payment, credential, network, rate-limit, and model availability failures are reported as dependency availability outcomes; malformed LLM proposals and request-shape problems remain compiler failures. No upstream body or credential is stored in a run, event, test, or worklog.

### Verification

- `tests/knowledge/test_wiki_llm_provider.py tests/knowledge/test_knowledge_tasks.py`: `24 passed`.
- `tests/promptops/test_promptops.py tests/test_sop_llm_client.py tests/api/test_knowledge_workspace_api.py`: `48 passed`.
- Knowledge regression: `66 passed, 1 skipped`; `compileall app`, `docker compose config --quiet`, and `git diff --check` passed.
- Browser inspection of the local Studio confirms the unauthenticated state is explicit: it displays `Studio access required` and the API response `authentication required`; it does not claim that the protected default project has been synced. The runtime access key was not read from local configuration or entered into the browser.

### Remaining External Gate

- A paid DeepSeek balance or an explicitly configured alternative real model is required before another maintenance run can produce a reviewable Wiki proposal, pass lint/evaluation, and enter the publish gate. This worklog does not mark that downstream evidence chain complete.

## Horizon Daily Capture Reconciliation (2026-07-26)

- Windows task `BSC-Horizon-Daily-Radar` executed at `07:30:01` local time with result `0`; its next scheduled run is `2026-07-27 07:30:00` and it has no missed executions.
- The latest native Horizon artifact `run-20260725T233005Z-974f0eb9` contains four filtered items, plus immutable raw/scored stages. Its ready stage is `filtered`: source collection and deterministic filtering completed, while model-based enrichment degraded because the external provider cannot be paid for at present.
- Reconciled the BSC consumer through the real Celery queue, creating run `987a9ee64fc6`. It produced the durable event sequence `queued -> execution_assigned -> running -> horizon.capture.skipped -> completed` and returned `no_new_artifact` rather than duplicating evidence.
- The idempotent skip is backed by the project ledger: the latest Horizon run ID was already imported. The default project currently contains 59 immutable source records, of which 52 are `horizon_signal` records. This is runtime evidence for the native Horizon run-store to BSC evidence integration, not a fixture or a file-existence assertion.

## Obsidian Source-Sync Runtime Proof (2026-07-26)

- The persistent default-project `source_sync` schedule ran at `23:50` local time. Durable run `0c1f5c1095fe` completed with ordered `queued -> execution_dispatched -> running -> wiki.snapshot.synced -> source.sync.completed -> completed` events.
- It scanned six declared project files, created zero duplicate source records, recognized six existing content hashes as duplicates, skipped one managed/empty boundary item, and rejected or blocked nothing.
- The BSC-to-Obsidian evidence mirror verified 55 eligible records: `created=0`, `updated=0`, `unchanged=55`, `conflicts=0`; four non-eligible records were intentionally not projected. The on-disk `01_Sources/bsc-evidence/` mirror contains 55 Markdown records.
- The same execution indexed six governed Wiki/AGENTS files and found no D-layer output feedback to register. This is the expected honest result while no new user-authored Obsidian material or real production outputs have appeared.

## DeepSeek Recovery and Governed Publication (2026-07-26)

### Runtime Results

- After the provider balance was restored, a direct DeepSeek structured call returned HTTP 200 and a real `wiki_maintenance` execution produced proposal `fcf98725f2d1`. Its four governed operations passed lint with no findings.
- An earlier manual publication was interrupted by an API-container recreation. The proposal was left `approved` and run `567a6ed61d70` was still `running`, without the intended Wiki page in either the Vault or publication index. This was treated as an atomicity defect, not as a successful publish.
- Publication recovery now reconciles stale `wiki_publish` runs against the authoritative Vault. It completes runs only if every typed filesystem effect is present; otherwise it changes `validating` or legacy `approved` proposals to retryable `failed` and records `abandoned_publish`.
- Reconciliation correctly changed `fcf98725f2d1` to `failed` and `567a6ed61d70` to `failed` with `failure.code=abandoned_publish`. No uncommitted concept page was present in `D:\bsc\bsc\projects\default\wiki`.
- The same proposal was then republished through the normal manual gate. Publication run `7eef12bddfad` completed with evaluation score `1.0`; proposal status is `published`; `wiki/concepts/workplace-sop-models.md` now exists in the mounted Obsidian Vault; the database contains seven governed pages and 17 active citation links; the proposal evidence is `processed`.
- A queued post-publication `source_sync` verification run `2a4b6721dacf` completed. It found six duplicate managed project notes, updated seven evidence mirrors, indexed seven Wiki pages, and reported no rejected, blocked, or index failures.

### Retrieval and Maintenance Evidence

- The initial live SOP context build selected the published `wiki/concepts/workplace-sop-models.md` page and its evidence, but revealed that legacy reranking assumed every repository owned `get_project`. `WikiRepository` does not, so retrieval fell back after an `AttributeError`.
- `get_reranker` now capability-checks `get_project` before reading project-level reranker configuration. Wiki-backed retrieval falls back to the configured global reranker without an exception. Regression tests for reranking, context packs, and retrieval passed: `14 passed`.
- After redeployment, the live default-project context build was 11,977 characters and included both the published SOP page and an immutable source. No rerank-fallback error was emitted.
- A further governed maintenance run `826a77d4a3e7` terminated before any model call with `no eligible sources selected`. The live source ledger contains 31 `validated`, 9 `processed`, 1 `rejected`, and 18 `superseded` records, with no `eligible` records. This is the intended anti-repeat boundary: community or untriaged Horizon signals cannot be silently promoted to trusted evidence merely to make a model run.

### Verification and Deployment

- Focused publication recovery regression: `tests/knowledge/test_proposal_gate.py tests/knowledge/test_wiki_commands.py tests/knowledge/test_scheduler.py tests/knowledge/test_knowledge_tasks.py -q` -> `46 passed`.
- Rebuilt the local API, Worker, and Beat images without changing PostgreSQL, Redis, or the mounted Vault. `docker compose ps`, `GET /live`, and `GET /ready` confirm all services are healthy at `http://127.0.0.1:8002`.
- `git diff --check` remains clean apart from existing line-ending advisories. The worktree intentionally still contains broader uncommitted work; no unrelated file was staged or reverted.

### Existing Automation Cross-Check

- The `growth_daily` schedule is enabled for `17:00 Asia/Shanghai`, following the `08:00` Horizon capture schedule; weekly distillation remains enabled for Friday `17:30`, and Wiki maintenance for `17:15`. This ordering gives new signals a project-profile triage pass before scheduled Wiki maintenance.
- Latest generated daily growth run `c1f7d03f0c87` is runtime evidence of the complete A/B/C/D loop. It wrote `distillations/每周蒸馏/2026-W30/每日增量/2026-07-26.md`, used 213 bounded inputs, and recorded one successful `deepseek-v4-pro` `knowledge_distillation` call through PromptOps (`2,992` reported tokens, including `1,664` cached and `1,073` reasoning tokens). The audit is attached to the run as `prompt_049dcbecc4ef4761b9c099a1c510fa1b`.
- That daily run's declared Obsidian/plugin sync triaged 37 records with `eligible=6` and `pending_review=31` at execution time. The later explicit triage pass produced the same conservative result for the current 31 pending signals: 30 archive decisions and one non-admitted reference candidate. No source was promoted by a template or a model assertion alone.

## DeepSeek Runtime Closure And PostgreSQL Retrieval Repair (2026-07-27)

### Real Runtime Evidence

- DeepSeek is configured and the model balance is usable. A real weekly growth run `65be57b07369` completed through Celery for `default` and generated the durable `2026-W31` bundle under `D:\bsc\bsc\projects\default\distillations\每周蒸馏\2026-W31`.
- The run persisted five governed documents, a source cutoff, input fingerprint, and a `knowledge.growth.model.completed` event. PromptOps recorded one completed `deepseek-v4-pro` `knowledge_distillation` call (`prompt_580b36fe0dda4bffa547a938ce4f5397`) with 2,918 reported tokens and no retry.
- A manual maintenance run `906ffd9e85ea` completed as the intended auditable no-op when no currently eligible source exists. Its event stream ends with `knowledge.wiki.maintenance.noop`; it created no failure record and did not bypass source-admission policy merely to invoke a model.
- A real project-scoped SOP composition completed through PromptOps using `deepseek-v4-pro`. The resulting SOP had a growth context pack with three immutable source references and three published-Wiki page references; the redacted audit ledger records six context references and one provider call.
- The protected live workspace endpoint was requested in-process with the configured key, without printing or reading it into this worklog. It returned HTTP 200 for `default`, with Vault state `ready`, 114 source records, five durable schedules, and retained run history.

### Defects Corrected

- PostgreSQL schema setup now uses a session-scoped advisory lock around the complete knowledge migration rather than a transaction-scoped lock. This closes the observed concurrent `CREATE INDEX IF NOT EXISTS` deadlock during independent repository process initialization.
- `KeywordBackend` now detects PostgreSQL before attempting SQLite FTS5 `MATCH`/`bm25`. PostgreSQL follows the existing project-scoped lexical `LIKE` path directly, so valid SOP context retrieval does not emit a syntax error and silently degrade first.

### Verification

- Focused regression: `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_schema.py tests/knowledge/test_keyword.py tests/knowledge/test_knowledge_tasks.py -q` -> `28 passed`, with one existing Starlette/httpx deprecation warning.
- Rebuilt and deployed API, Worker, and Beat. API `/ready` returned 200 and Celery ping returned `pong`.
- Three concurrent fresh repository processes each completed schema initialization after deployment. A real PostgreSQL retrieval returned five scoped chunks, and a subsequent real SOP generation completed without a new `knowledge_fts MATCH` or `bm25(knowledge_fts)` PostgreSQL log entry.

### Deliberate Boundary

- The currently empty eligible-source set means the next Wiki maintenance cycle will remain a completed no-op until a source passes the project-specific admission policy. This is correct: the weekly growth and SOP paths may consume the governed project context, but they cannot auto-promote rejected, validated, or superseded evidence into publishable Wiki claims.

## Weekly Retry Repair And DeepSeek Daily Proof (2026-07-27)

### Defect Corrected

- A retried `weekly_distillation` run could recalculate its period from the current date when the retry dispatcher did not resend the optional `week` argument. `execute_knowledge_run` now persists the explicitly supplied week before execution, and the distillation handler resolves its period in the order: dispatcher argument, persisted run input, current ISO week. A retry therefore remains bound to the original cutoff and output bundle rather than writing into a later week.

### Verification And Deployment

- Targeted retry and repository suite: `31 passed` across Celery retry, repository, and knowledge-task tests.
- Broader knowledge regression: `554 passed, 3 skipped` across `tests/knowledge`, growth-Celery, knowledge-Celery, and workspace API coverage.
- Rebuilt `bsc-backend`, `celery-worker`, and `celery-beat` without replacing PostgreSQL, Redis, or the mounted Vault. The API is healthy on `http://127.0.0.1:8002`; PostgreSQL and Redis are healthy; Worker and Beat are running.

### Real Runtime Evidence

- Submitted daily growth run `cfe345f15bf9` through the authenticated project API. It was processed by Celery and completed with the durable event sequence `queued -> execution_assigned -> growth.started -> obsidian_sync.completed -> model.completed -> distillation.completed -> completed`.
- The run scanned the declared Obsidian bridge and retained the truthful plugin state: one configured Clipper export was already captured; other configured import/export plugins remain `awaiting_export` until their first real files appear.
- PromptOps recorded one completed DeepSeek `deepseek-v4-pro` `knowledge_distillation` call (`prompt_3dedfdd4e0934223b6232fde8f2420e9`) with no retry. The governed daily artifact was written to `distillations/每周蒸馏/2026-W31/每日增量/2026-07-27.md`.
- Manual review confirmed the artifact is source-cited, distinguishes evidence from project implications, and records its unresolved question and next verification action. It is a daily knowledge increment, not a published Wiki claim or a substitute for a multi-source research report.

## DeepSeek Pro Semantic Triage And Reference-Only Authoring Gate (2026-07-27)

### Real Runtime Evidence

- The manual semantic-triage path was exercised against immutable Horizon source `25fca60224c4` through the protected local API. No credential, raw source body, or provider response body was logged.
- The first implementation routed this lightweight task to `deepseek-v4-flash` when `KNOWLEDGE_GROWTH_LLM_MODEL` was empty, despite the project-level `DEEPSEEK_MODEL` being `deepseek-v4-pro`. The evaluator now inherits the configured DeepSeek model only for a DeepSeek-backed workspace; other providers retain PromptOps routing.
- A real Pro request exposed a second integration defect: the previous 900-token completion budget could be consumed by model reasoning and leave an empty final JSON response. A same-input, no-persistence diagnostic passed at 1,800 tokens. The governed manual evaluator now reserves 1,800 tokens and persists a stable provider failure category when a structured call is unavailable.
- Semantic evaluator revision `semantic-source-triage-v3` completed through DeepSeek Pro in 20,100 ms. PromptOps run `prompt_078c7033ae6749f9a07fdab2052743ba` recorded model `deepseek-v4-pro`; the source received relevance=75, value=70, freshness=95, outputability=70, connectedness=80, priority=77, reliability pass, and disposition `reference`.
- The source was explicitly moved to `eligible` through the protected API for a controlled proposal test. Maintenance run `2c55e47eba9f` produced draft proposal `9b021089aa1c`; automatic publication was disabled and the proposal remained `review_required`.

### Quality Correction

- Manual proposal review found a substantive quality mismatch: a secondary source whose model review required primary-system-card verification had been expanded into strong durable claims. Lint alone was valid, but the proposal did not satisfy the project evidence threshold for standalone publication.
- Proposal `9b021089aa1c` was explicitly rejected. It was never published, no generated Wiki page was written to the Obsidian Vault, and no source was marked processed from that proposal.
- `reference` now means searchable and reviewable evidence only. It returns `project_triage_reference_requires_corroboration` to authoring paths, preventing a single reference from independently driving Wiki compilation, growth distillation, candidate extraction, or method creation. Only current, reliable `knowledge_candidate` decisions can author durable knowledge; reference material requires corroborating candidate evidence.
- Post-deployment maintenance run `31820d260466` proved the rule on the real project: the source remains `eligible` for traceability, its authoring reason is `project_triage_reference_requires_corroboration`, and the Celery task completed as `no_eligible_sources` with publication `not_applicable`.

### Verification And Deployment

- Python knowledge regression: `530 passed, 3 skipped`; knowledge/growth API regression: `40 passed`; frontend Knowledge workspace regression: `16 passed`; `npm.cmd run check` and `git diff --check` passed.
- Rebuilt only `bsc-backend`, `celery-worker`, and `celery-beat`. API `http://127.0.0.1:8002/live` returned 200, PostgreSQL/Redis remained healthy, and `celery inspect ping` returned `pong` from one Worker.

## DeepSeek-Funded Proposal Quality Gate (2026-07-27)

### Runtime Safety Action

- After DeepSeek balance recovery, a real candidate-source maintenance run created draft `71d679ad2614`. Lint passed, but human review found the Wiki prose repeated a context-budget disclosure (the source excerpt was truncated) and included non-evidence popularity data. The proposal was rejected through the authenticated local API before publication. It never wrote a Vault page or altered source status.

### Compiler Hardening

- The Wiki compiler now rejects both the canonical `CONTEXT_EXCERPT` marker and Chinese restatements such as `源摘录内容被截断` or `原始资料不完整`. This prevents a provider from laundering a bounded-context warning into durable knowledge. The regression suite covers English and Chinese variants; a complete visible evidence statement with immutable inline citation remains required for every automatic content operation.

## Horizon Discovery To Primary Evidence Boundary (2026-07-27)

- Root-cause review showed that Horizon discovery records can contain both source excerpts and Horizon-owned rationale or engagement metadata. These fields are useful for prioritization, but are not publishable factual evidence.
- New Horizon imports keep the selected item content and source URL in the immutable discovery record while retaining AI summary, rationale, and scores only as labeled metadata. A `horizon_signal` remains searchable and triageable, but now always requires an independently captured primary source before it can author a Wiki proposal.
- The Workspace now exposes a governed public HTTPS primary-capture endpoint. It blocks credentials, private/reserved addresses, non-default HTTPS ports, unsafe redirects, oversized bodies, and non-text content; it records the requested/final URL, response SHA-256, content type, and extraction revision. The resulting `primary_web` evidence is review-only until its project-specific triage passes and an operator explicitly promotes its status.
- Focused compiler, source-triage, Horizon-import, and primary-web-capture regressions passed (`43 passed`); the full API contract verification and local Docker deployment remain the next steps before a live primary-source proof is recorded.
- Live public-web verification found transient upstream connection failures from GitHub despite successful direct retries. Primary capture now retries only retryable transport failures a bounded number of times; it never retries a security rejection, invalid redirect, non-text response, or oversized body, and it still persists nothing until a complete response is captured.
- The first real primary-source proposal (`c9aa93581925`) was lint-clean but rejected during human quality review because it translated an MCP glossary without a project-specific decision, workflow change, or operating boundary. This is recorded as a quality failure, not a successful Wiki result. Manual maintenance now accepts bounded source selection and task constraints, forwards them into the deterministic context pack, and the model schema explicitly rejects generic source recaps in favor of a named project integration, applicability boundary, and next validation action.
- A constrained maintenance run `fd59698a5bde` failed without creating a proposal when the model cited an old page's unrelated source ID. The compiler retained the hard provenance rejection. Its prompt now enumerates the only allowed immutable source IDs and states that page citations are navigation context rather than permission to reuse their evidence. The next retry uses ASCII-escaped JSON transport for Chinese task constraints so shell encoding cannot alter the stored instruction.
- A subsequent two-source draft `63ce7283f09f` was rejected after lint found invalid `type` frontmatter. Review also showed derived page snapshots had consumed the bounded context before selected source evidence, causing the model to treat implementation facts as incomplete. `ContextPackBuilder` now supports evidence-first ordering; Wiki maintenance uses it so rules and task constraints are followed by selected immutable sources, with pages admitted only from remaining budget.

## DeepSeek MCP Gateway Decision And Quality-Path Repair (2026-07-27)

### Real Runtime Evidence

- Docker API, PostgreSQL, Redis, Celery Worker, and Beat were healthy before execution. A direct DeepSeek Pro Wiki-maintenance call completed through Celery; the provider returned HTTP 200 and no credential or response body was written to this record.
- First draft `29dff07fce0f` passed mechanical lint but was rejected before publication: it inferred an unsupported sampling policy and used an invalid `tools/list` validation. This is retained as an auditable rejection and did not modify the Vault.
- A second constrained DeepSeek run `bcc94868e8e7` created draft `89eb270733e2` from only the official MCP architecture record `c9a36eba7694` and the BSC implementation snapshot `cb2f17ebf938`. Lint passed with no findings.
- Live MCP transport checks confirmed unauthenticated `/api/mcp` returns HTTP 401 and an authorized JSON-RPC `initialize` returns a valid result. The BSC evidence mirror for `cb2f17ebf938` has matching database fingerprint, rendered fingerprint, and Vault file hash with the managed read-only marker.
- Project isolation and non-destructive projection regressions passed (`4 passed`). The proposal then published through the normal Proposal Gate as `89eb270733e2`, evaluation score `1.0`, without override. It created `wiki/decisions/mcp-gateway-project-boundary.md`, updated the ledgers, and rebuilt the searchable Wiki index to eight pages.

### Quality Gate Repair

- The first post-publication whole-project lint/eval run truthfully failed: lint was valid, but evaluation was `not_applicable` because all evaluation cases were path-scoped and the whole-project task omitted candidate page paths.
- Added two project-local regression cases for the published decision: cited source IDs and required content/citation constraints. The task still returned `not_applicable`, proving the integration gap was in the executor rather than the newly added data.
- `knowledge_lint_eval` now passes the authoritative published page paths into `WikiEvaluator`. The quality-task regression now uses a scoped evaluation case, so it fails if those paths are removed again.

### Verification Before Redeploy

- `tests/knowledge/test_knowledge_tasks.py`, `tests/knowledge/test_wiki_evaluator.py`, `tests/knowledge/test_proposal_gate.py`, `tests/knowledge/test_obsidian_source_projection.py`, and `tests/integration/test_knowledge_mcp_e2e.py`: `41 passed` with one existing Starlette/httpx deprecation warning.
- `compileall app` and `git diff --check` passed. API, Worker, and Beat were rebuilt without replacing PostgreSQL, Redis, or the mounted Vault; `/ready` returned dependency status `ok` and Celery ping returned `pong`.
- The redeployed full-project quality run `595a8addbc4b` completed: lint is valid, evaluation passed with score `1.0`, and evaluation coverage is `1.0`. The published page has an identical SHA-256 in the BSC database and mapped Vault, and the persisted graph contains its two `wiki_cites_source` plus two `decision_uses_evidence` edges.

## DeepSeek SOP Projection And D-Layer Runtime Proof (2026-07-27)

### Defect Corrected

- A real DeepSeek Agent OS run exposed a Studio projection defect: the runtime did create a typed `DeliverableArtifact(kind="sop")`, but `runtime_response_to_project_state` discarded it and displayed generic `workflow` entries as SOPs. The resulting UI object had no title, sections, actions, evidence gaps, or citations even though those fields existed in the artifact graph.
- The projection now gives authored SOP deliverables priority over the generic workflow fallback. It retains the exact title, summary, differentiators, sections, actions, evidence gaps, and model-returned direct source references. Governed context references are displayed separately as provenance and do not falsely inflate direct citation coverage.
- The SOP capability prompt now receives the original project brief as well as the business model. It requires source references to exactly match identifiers present in the governed brief and requires unsupported facts to remain in `evidence_gaps`.

### Real Runtime Evidence

- A live `deepseek-v4-pro` SOP capability run used the default project's growth context and published-Wiki provenance. It produced a Chinese `BSC` knowledge-operations SOP with seven sections and seven executable actions, including the primary-capture `403` handling boundary, proposal review, daily growth, weekly distillation, and Obsidian feedback.
- The model cited only official MCP source `c9a36eba7694`, which was present in its governed context. It explicitly recorded unavailable source `22053520b666` as an evidence gap rather than inventing support. The projected SOP had citation coverage `1.0`, no invalid source references, and a distinct context record with four Wiki page IDs.
- The same generated deliverable was registered through `OutputCompletionBridge` as output `70c270356bd568366b9c197f`, audit run `9b3f0fbbf3c9d969f9d833a3`. It is intentionally `registered`, not accepted or reusable: it awaits real usage evaluation and feedback before any method or Wiki promotion.
- The resulting Obsidian file exists at `outputs/2026/70c270356bd568366b9c197f/bsc-knowledge-operations-sop-art_72bf484f9ed7.md`. Its SHA-256 matches the registry, and inspection confirmed the direct source reference, `403` procedure, and evidence-gap section are present.

### Verification And Operational Boundary

- Regression: `tests/test_capability_deliverables.py`, `tests/orchestrator/test_runtime_engine.py`, `tests/integration/test_growth_output_bridges.py`, and `tests/integration/test_growth_sop_context.py` -> `16 passed`.
- A direct primary capture of the official OpenAI incident URL still returned upstream HTTP `403`; no incomplete primary source was persisted and no Horizon signal was promoted as a substitute.
- During two broad `/agent/analyze` / asynchronous orchestration attempts, Docker event history showed an external `SIGTERM`, container destroy, and replacement image while the work was executing. The system correctly marked interrupted sessions as `worker_restarted`; this was not treated as a completed SOP. The successful single-capability proof above was isolated from that concurrent deployment and performed after confirming the replacement image contained the corrected source.

## Failure Ledger Reconciliation After DeepSeek Recovery (2026-07-27)

### Audit Basis

- The live health snapshot was read from the PostgreSQL-backed ledger: eight Wiki pages, 118 source records, 21 active citations, citation coverage `1.0`, no dangling or stale citations, no pending proposal, and a latest Wiki evaluation score of `1.0`.
- Three historical open failure records were inspected together with their immutable run event streams. This audit does not rewrite a failed run, delete its evidence, or convert it to success.
- The three currently uncited eligible records remain deliberately uncited: two are Horizon discovery signals and one is a BSC artifact. None will be used to manufacture a Wiki page or improve a dashboard counter. Horizon signals still require independent primary capture and current project-triage admission; the artifact still requires provenance review.

### Reconciliation Decision

- `51159ab172f943b8a3e157d9`: the compiler rejected an unknown source ID before creating a proposal or writing a Vault page. The non-existent ID was confirmed absent. Subsequent provenance-bounded compilations completed without the defect, so the historical incident can be closed without retrying stale input.
- `c5ce64121d96450ca5b17d33`: the old `no eligible sources selected` record was a normal business no-op incorrectly represented as a compiler failure. Current maintenance preserves the same admission boundary as completed `no_eligible_sources` work and never promotes evidence merely to invoke a model.
- `982eff74cdfb449cb33d9ffc`: the provider's earlier invalid structured response remains attached to its failed run. Later governed DeepSeek Pro executions completed successfully, so the incident can be closed as recovered without replaying historical input or treating the original run as successful.

### Applied Result

- The three failure records were resolved through the durable repository lifecycle with actor `system:knowledge-reconciliation` and `retry_scheduled=false`. The original run statuses remain `failed`; their event logs and diagnostic evidence are retained.
- A post-write ledger query returned zero remaining open failure records. This changes operational incident state only; it does not claim that a rejected proposal, an unavailable source, or a former model response became valid knowledge.

## Obsidian Evidence Projection Draft Review (2026-07-27)

- A live Celery `wiki_maintenance` run `3cb7ef24c7cb` used DeepSeek Pro with only the complete implementation snapshot `f4adf06369c9`. It created draft `ab103273dc80`; automatic publication remained disabled.
- The draft was rejected after manual source-level review. It correctly preserved the no-plugin-execution boundary, but incorrectly claimed that an MCP `/mcp` route returns immutable source bodies. The snapshot proves `ObsidianSourceProjection` is a BSC-managed read-only Vault projection; it does not prove that MCP route behavior. The actual HTTP prefix is `/api/mcp`, and route behavior was outside the selected evidence.
- The rejection is persisted in the proposal's review summary with the factual reasons and a constrained next action. No Wiki page, index entry, log entry, source lifecycle change, or Vault file was written by the rejected proposal.

### Corrected Publication

- A second bounded DeepSeek Pro draft `484459a4099f` was also rejected before publication. It improved the scope but conflated `source_id` with `content_hash` and overstated the read-only label as a technical prohibition on all local edits. The review records those exact corrections rather than accepting a near miss.
- A manually reviewed proposal `326eb084cc98` was then created from the same complete implementation snapshot. It documents only the implemented projection lifecycle: database authority, managed frontmatter, the `metadata.sync=obsidian` duplicate-prevention rule, and conflict-on-divergence behavior. It explicitly excludes import success, plugin execution, plugin export capture, and output-feedback claims.
- The proposal passed Wiki lint with no findings. Two project-scoped evaluation cases were registered before publication: required citation of `f4adf06369c9`, and required `metadata.sync=obsidian`, `content_hash`, and `conflicts` constraints.
- Manual publication run `5f8bc1a5c9c7` completed without an override. The Proposal Gate recorded evaluation score and coverage `1.0`, updated the search index to nine pages, and published `wiki/decisions/bsc-managed-evidence-projection.md`.
- Final database-to-Vault verification used the configured `/vault/projects/default` mapping, corresponding to `D:\bsc\bsc\projects\default` on the host. The published page exists, its filesystem SHA-256 equals database hash `d212dc7196ede5dcb6de8da1a6cf45f0274b7cadb2e1ebb3a634ce06db66e538`, and it has an active citation to `f4adf06369c9`.
- Focused regression `tests/knowledge/test_obsidian_source_projection.py tests/knowledge/test_wiki_commands.py tests/knowledge/test_proposal_gate.py -q` passed: `22 passed` with one existing dependency deprecation warning. Current health has nine pages, 25 active citations, full citation coverage, no dangling or stale citations, no pending proposals, and no open failures.

## Horizon Producer And Scheduled Capture Live Acceptance (2026-07-27)

### Producer Evidence

- Horizon at `D:\bsc\horizon` is configured to use `deepseek-v4-pro` through `DEEPSEEK_API_KEY`; the credential was only resolved at runtime and was never written to this worklog, command output, or a new configuration file.
- A direct native MCP pipeline run `run-20260726T233008Z-68b25bf3` fetched 8 public candidates, scored all 8 with DeepSeek, and retained 4 `filtered` records. It completed with GitHub, Hacker News, and RSS inputs. Google News and Reddit connection failures remained source-level diagnostics; they were not represented as successful collection.
- Protected API capture run `16ab4117ba55` consumed that exact staged artifact from the mounted run-store. Celery recorded the full queued, assigned, running, capture-completed, and completed event sequence. It accepted and created 4 `horizon_signal` records, mirrored all four into `01_Sources/bsc-evidence/`, and left every new source `validated` with `primary_capture_required=true`.

### Durable Schedule Evidence

- The production entry point `scripts/run_horizon_pipeline.py` was executed with Horizon's own virtual environment and `--no-enrich`. Run `run-20260726T233902Z-ad2b72ef` fetched 8, scored 8, retained 4, wrote `producer-state.json`, and completed without degradation. Skipping enrichment is intentional for the radar-to-evidence path: BSC imports the grounded item URL/content as a discovery signal and does not treat generated background prose as primary evidence.
- Windows Scheduled Task `BSC-Horizon-Producer` is registered for 07:45 daily, runs the bounded producer with a 10-minute execution limit, starts when available, and ignores overlapping instances. It uses interactive local-user logon, so the Windows user session must be available; this is not a headless cloud scheduler claim.
- The task was started immediately for verification. It exited with code 0 and produced `run-20260726T234347Z-e2389f94` with 8 fetched, 8 scored, and 4 retained items. Its next natural execution is scheduled for 2026-07-28 07:45 local time.
- The existing BSC persistent `horizon_capture` schedule remains at 08:00 Asia/Shanghai, after the producer window. Discovery-mode capture run `620f3932f5ac` automatically selected the newest task-produced run, observed 4 items, accepted all 4, created 2 new sources, and recorded 2 idempotent duplicates. The 2 new sources were projected to Obsidian evidence files and still require independent primary capture before authoring.

### Remaining Operational Limits

- Horizon source availability is intentionally visible in every producer run. Google News and Reddit were unreachable in the live runs, while the successful GitHub, Hacker News, and RSS stages still formed a valid partial collection. No failed source was silently replaced with model-generated content.
- The scheduled chain now has real producer and consumer proof. Its next unattended natural execution depends on the local Windows interactive session and the existing Docker API, Worker, Beat, PostgreSQL, Redis, shared run-store, and Horizon source network paths remaining available.

## Governed Encoding Repair And Mobile Acceptance (2026-07-27)

### Published repair

- A historical encoding defect was found in the published `wiki/decisions/bsc-managed-evidence-projection.md` page and `wiki/index.md`; the Vault files contained literal question marks and a stale escaped navigation line.
- A replacement proposal `e885d717250d` was created from the existing processed implementation snapshot `f4adf06369c9`. It replaced the decision and index, appended the audit log, and received the automatic overview operation required by the Wiki contract.
- Proposal lint passed with no findings. The publication run `51d8722a61ed` passed the persisted evaluation with score `1.0`, committed atomically, and rebuilt the search index with no indexing failures. The decision page now states the database-authoritative projection boundary, `metadata.sync=obsidian` duplicate prevention, hash-based `conflicts`, and the limit that plugin installation is not export execution.

### Mobile defect and verification

- The authorized Studio was checked at a 390x844 viewport against live PostgreSQL-backed data. The first inspection exposed a real CSS defect: the mobile Vault tree had a 190px height limit but no internal overflow, so its decision links spilled into the Evidence list.
- `src/index.css` now gives the bounded mobile Vault tree `overflow: auto` and `overscroll-behavior: contain`. Frontend component tests passed (`10 passed`) and TypeScript check passed.
- After a live page reload, the tree measured 190px client height and 336px content height, with the Evidence header below the tree and the first evidence card below that header. The document width was 384px with no horizontal overflow. Studio access, Vault readiness, Horizon run-store status, plugin bridge status, 100% citation coverage, and the repaired Chinese decision title were all visible from live data.

## DeepSeek v12 Weekly Distillation Quality Closure (2026-07-27)

### Observed Gap

- Live v11 run `7751db3ba718` completed with a real DeepSeek `deepseek-v4-pro` call and the v11 provenance gate, but only two of five weekly documents passed the strict Markdown, citation, uncertainty, and unsupported-project-state checks. The other three were explicitly marked as deterministic fallbacks (`mode=hybrid`); this was treated as a quality failure, not as full semantic-generation acceptance.
- The prior corrective path asked the model to regenerate the complete five-document object even when only a subset was rejected. It also retained only the final PromptOps record in the manifest, which under-reported the number of quality-repair provider calls.

### Implemented Repair

- Raised `GrowthDistillationService.DISTILLATION_CONTRACT_REVISION` to `12`. The weekly prompt now includes a pre-return self-check for headings, size, evidence citation, and uncertainty.
- The configured DeepSeek provider now supports a targeted retry contract: an initial batch still produces five documents, while a repair request can return JSON only for the rejected document slots. Already accepted documents are preserved and only validated repairs replace rejected files.
- PromptOps evidence is scoped per knowledge run and aggregates every successful initial/repair invocation. Multi-call manifests retain per-prompt run records and folded provider usage; one-call runs remain backward-compatible with the existing compact evidence shape.
- Focused regression added a four-accepted/one-rejected scenario. It proves that only the rejected document is requested on retry, no fallback remains after repair, and both provider calls are represented in the manifest usage totals.

### Verification And Live Acceptance

- Focused regression and contracts: `tests/knowledge/test_growth_distillation.py`, `tests/test_config_sop_llm.py`, and `tests/test_docker_compose_contract.py` -> `39 passed`; `compileall` and `git diff --check` passed (aside from existing CRLF warnings).
- Rebuilt and deployed API, Celery Worker, and Celery Beat. `/ready` returned HTTP 200 with PostgreSQL and Redis healthy; Worker ping returned `pong`; the running container reported distillation revision `12` and a 150-second growth-model timeout.
- Live run `22407473e02c` completed through Celery with the event chain `queued -> execution_assigned -> growth.started -> obsidian_sync.completed -> model.completed -> distillation.completed -> completed`.
- Its manifest proves `mode=llm`, `provider=deepseek`, `model=deepseek-v4-pro`, contract revision `12`, five LLM documents, zero fallback documents, and one complete provider-accounted call (`prompt_e9a0e794904949f6aa866d6a96273553`). This run did not need a quality retry; the targeted-retry path is covered by the focused regression rather than falsely claimed as a live event.

## DeepSeek Weekly Distillation Bounded-Call Validation (2026-07-27)

### Implemented

- Added `PromptRequest.max_structured_attempts` and threaded it into `SOPLLMClient.chat_structured`. Knowledge growth explicitly sets the value to `1`, so a provider JSON repair cannot silently multiply one governed render into two provider requests.
- Raised the semantic weekly contract to revision `22`. A weekly run is bounded to an initial render plus at most one batch repair. Production never fans out one failed document into separate requests. The repair asks only for the rejected document keys.
- Weekly full generation has a `6,500` token ceiling. Small targeted repairs have a `4,500` token floor because the observed reasoning budget can otherwise consume a `3,200` token response before two Markdown documents are produced.
- Growth task limits are now `240s` soft and `270s` hard. They cover the two-call weekly contract while remaining independently bounded from the generic Celery timeout.

### Verification

- Regression set: `tests/test_sop_llm_client.py`, `tests/promptops/test_promptops.py`, `tests/knowledge/test_growth_distillation.py`, `tests/integration/test_growth_celery.py`, `tests/test_config_sop_llm.py`, and `tests/test_docker_compose_contract.py` completed with `104 passed` and one existing Starlette/httpx deprecation warning.
- API and Worker were rebuilt. `/ready` returned PostgreSQL and Redis `ok`; Celery ping returned `pong`. Beat remains intentionally stopped while the weekly model-output issue is unresolved, so it cannot create unattended paid retries.
- Live runs `1475e8637a18`, `65094c9327bb`, `52081522c71f`, and `0b8dbcbab9f5` all reached durable `completed` run status with a `distillation.preserved` event when their weekly bundle was incomplete. No run overwrote the existing Vault week and no run was reported as published.

### Runtime Finding And Handoff

- The final revision `22` run used two complete, provider-accounted DeepSeek Pro calls in `159,594 ms`: `16,230` total tokens, including `6,403` reasoning tokens. Only two of five documents passed the deterministic source/citation/uncertainty/project-state gate; the batch repair did not make the bundle complete. The existing bundle input hash `698142b8d1a46781426b2ccbe6af5f2bf2b8163eafe767d26f4da51463edc790` remains preserved.
- This is not a Docker, Vault, database, scheduler, network, credential, timeout, or atomic-publication failure. It is a reproducible quality/format compatibility limit of `deepseek-v4-pro` for this multi-document governed JSON contract. The next implementation must add non-content-retaining validation reason codes and evaluate a provider/model profile specialized for strict JSON generation before automatic weekly scheduling is re-enabled.
- Independent post-run verification of `D:\bsc\bsc\projects\default\distillations\每周蒸馏\2026-W31` confirmed exactly five distinct UTF-8 documents. Every document hash matches `manifest.json`, has at least two `##` sections, contains only allowed source/page citations, has an explicit uncertainty marker, and has no unsupported project-state assertion. No non-evidence bracket reference or invalid context citation was found.

## DeepSeek Weekly Distillation Publication And Scheduler Recovery (2026-07-27)

### Implemented

- Raised the governed weekly contract to revision `25`. Validation now records only non-content rejection codes (`invalid_shape`, `missing_citation`, `invalid_reference`, `too_short`, `missing_sections`, `missing_uncertainty`, and `unsupported_project_state`) in a failed or hybrid manifest; rejected model text is not retained.
- Weekly documents now have distinct evidence-first roles: decision boundary, verification actions, content angles, carry-forward context, and method experiment. The prompt requires a visible uncertainty heading and distinguishes source-backed facts from unverified project activity.
- A run remains bounded to an initial generation, one batch repair, and only when exactly one document remains, one strict single-document repair. It never fans out into a per-document retry loop. The strict repair preserves the accepted four documents and requests only the remaining JSON slot.
- The growth lifecycle now has explicit `390s` soft and `420s` hard limits, covering the three-call maximum while retaining a finite task boundary. Defaults, Compose contracts, and tests were updated together.
- Fixed a frontend test fixture that no longer satisfied the evidence-graph response contract after `omitted_edge_count` became mandatory. This was a build blocker only; no evidence-graph behavior was changed.

### Verification

- Focused backend regression suite completed with `112 passed` and one existing Starlette/httpx deprecation warning. It covers the new rejection codes, targeted document contracts, bounded batch repair, final strict repair, PromptOps usage accounting, Celery limits, and Compose environment contracts.
- `npm run build` and `npx vitest run src/components/knowledge/EvidenceWorkspace.test.tsx` passed. The production Docker image then rebuilt successfully; API `/ready` reported PostgreSQL and Redis healthy, and the Worker answered Celery `ping`.
- The first revision `25` run `139e0624a161` encountered a temporary Docker DNS failure before a provider request. It recorded `generation.reason=network_error`, preserved the published bundle, and made no model-output success claim. Container DNS and HTTPS were verified immediately afterward; unauthenticated HTTPS reached DeepSeek and returned the expected `401`.
- Live retry `b21616bbe91e` completed via the protected API and Celery chain. Its events are `queued -> execution_assigned -> growth.started -> obsidian_sync.completed -> model.completed -> distillation.completed -> completed`. The manifest proves `mode=llm`, `provider=deepseek`, `model=deepseek-v4-pro`, contract revision `25`, five LLM documents, zero fallback documents, two quality repairs, and three provider calls.
- The published Vault bundle at `D:\bsc\bsc\projects\default\distillations\每周蒸馏\2026-W31` contains exactly `00-本周总结.md` through `04-方法迭代.md`. Every disk SHA-256 matches `manifest.json`; every file has three `##` sections, 1,452-1,803 non-whitespace characters, one or more permitted source/page citations, an uncertainty marker, and no unsupported project-state match.

### Scheduler And Runtime Closure

- `celery-beat` has been restarted and the durable schedule coordinator is consuming its one-minute reconciliation task through the same Redis queue as the Worker. The API reports `scheduler=true` for both enabled growth schedules: daily at `17:00` Asia/Shanghai and weekly distillation at `17:30` every Friday Asia/Shanghai.
- An old host-side Uvicorn process was still bound to `127.0.0.1:8002`, causing Studio to read stale scheduler state while Docker served the validated runtime through its own port relay. It was stopped after identifying its exact command line. `http://127.0.0.1:8002/ready` now reaches the Docker API and reports healthy dependencies; the host-visible schedule endpoint reports `scheduler_available=true`.
- A temporary external DNS outage remains a visible runtime dependency. On such an outage the weekly task preserves the previous valid bundle rather than overwriting it or falsely declaring a publication; a later scheduled run can retry from the same governed input boundary.

## DeepSeek Daily Distillation Budget Repair And Live Acceptance (2026-07-29)

### Observed Runtime Gap

- After the DeepSeek balance was restored, the Docker runtime was audited without exposing credentials. DeepSeek, semantic distillation, Growth, schedules, Vault sync, and the project-scoped write permission were all enabled.
- A first live daily run (`59db9e075820`) completed its storage lifecycle but honestly used deterministic content after the provider returned HTTP 200 without final structured content. A privacy-bounded structural probe confirmed that `deepseek-v4-pro` returns OpenAI-compatible `content` and `reasoning_content`; the full daily prompt had exhausted its former 1,200-token completion budget during reasoning.

### Applied Repair

- Increased the daily structured-generation budget to 3,600 tokens. An empty completion with `finish_reason=length` is now classified as `response_truncated` rather than the ambiguous `response_payload_invalid`.
- The client never treats hidden reasoning as final user-facing JSON. Added regression coverage for both the daily budget and an empty length-limited completion.
- `tests/test_sop_llm_client.py` plus `tests/knowledge/test_growth_distillation.py` passed: `73 passed`.

### Live Acceptance

- API, Worker, and Beat images were rebuilt. Docker API, PostgreSQL, Redis, Worker, and Beat were healthy before the follow-up run.
- Follow-up live run `36864f564523` completed on `deepseek-v4-pro`: one reported provider call, zero retry, `mode=llm`, `llm_documents=[daily]`, and zero fallback documents. Its event chain is `queued -> execution_assigned -> growth.started -> obsidian_sync.completed -> model.completed -> distillation.completed -> completed`.
- The published Vault file `D:\bsc\bsc\projects\default\distillations\每周蒸馏\2026-W31\每日增量\2026-07-29.md` passed managed-file, ownership marker, input/body hash, citation, and persisted SHA-256 verification. Earlier same-day content remains in the revision archive and was not overwritten in place.
- Post-repair integration regression `tests/integration/test_growth_celery.py`, `tests/api/test_growth_api.py`, `tests/mcp/test_wiki_http_contract.py`, and `tests/mcp/test_knowledge_evidence_tools.py` passed: `38 passed`. TypeScript `npm run check` passed; the rebuilt production image also completed `npm run build`.
- A post-deploy authorized JSON-RPC `initialize` request to `/api/mcp` returned protocol `2025-06-18` and `bsc-engine 5.0.0` without an error. This confirms the live model repair did not break MCP transport compatibility.

## Horizon Freshness And Producer-Failure Integrity Repair (2026-07-29)

### Audit Finding

- The managed Vault was reachable at `D:\bsc\bsc\projects\default`; the live workspace reported `ready`, 137 immutable source records, eight durable schedules, and a completed growth loop. PBOS projections and its daily report were also present, with unverified action material kept explicitly ungrounded.
- The Horizon producer's latest two run directories each contained only `raw_items.json` with zero items. The latest `producer-state.json` recorded `HZ_EMPTY_INPUT: No items available for scoring.` after GitHub, Hacker News, RSS, Reddit, OSS Insight, and Google News each returned an empty result.
- Before this repair, automatic BSC discovery could ignore that producer failure and select an older unpublished staged artifact. That behavior risks presenting stale intelligence as current collection.

### Applied Repair

- `HorizonRunStoreClient` now checks the producer status sidecar during automatic discovery. A failure newer than the newest unpublished enriched/filtered artifact raises a dedicated producer-failure error. A successful later stage supersedes an older failure.
- Automatic discovery now applies a 48-hour freshness ceiling through `HORIZON_MAX_ARTIFACT_AGE_HOURS`. Historical artifact import remains possible only through an explicit run ID, preserving deliberate backfill without silently treating it as fresh news.
- `knowledge.execute` maps both conditions into durable, project-scoped failures: `producer_failure / horizon_producer_failed` and `stale_artifact / horizon_artifact_stale`. The workspace API and Knowledge Workspace label producer failure and stale backlog separately from a genuine empty result.
- Compose passes the freshness contract to both API and worker. No source body, API key, or user-authored Vault content was added to logs or work records.

### Verification And Live Result

- Focused backend regression: `tests/knowledge/test_horizon_run_store.py`, `tests/knowledge/test_knowledge_tasks.py`, `tests/api/test_knowledge_workspace_api.py`, and `tests/test_docker_compose_contract.py` -> `61 passed`.
- `npm run check` passed. Focused frontend tests for the API contract and Knowledge Workspace -> `18 passed`. `docker compose config --no-interpolate --quiet` passed.
- Rebuilt and restarted the production API and Celery Worker. A protected live `POST /knowledge/horizon/capture` created run `1acbe68e9b28`; the Worker consumed it and persisted `failed`, `outcome=producer_failure`, `failure.code=horizon_producer_failed`, `retryable=true`, and failure record `1aa38607b1ac4d5b9ab52907` with root cause `transient_dependency:horizon_producer_failed`.
- The live workspace endpoint now reports the same failure state. It did not import an older run as today's information. The source-side empty collection remains an open, retryable operational incident rather than a fabricated successful update.
- Final regression after the integration-fixture and PBOS API-wrapper corrections: full backend suite -> `1466 passed, 13 skipped`; full frontend suite -> `21 files / 155 passed`; `npm run check` and `docker compose config --no-interpolate --quiet` passed. The skipped tests retain their existing external-environment prerequisites and are not represented as executed acceptance.

### Remaining Boundary

- The BSC consumer path is now truthful and protected from stale automatic import. Restoring actual Horizon intake still depends on public source availability and Horizon's configured source rules; it is not solved by generating substitute signals. The next producer run can recover naturally, and its later successful stage will supersede the recorded failure.

## Horizon Concurrent Import Claim And Live Producer Validation (2026-07-29)

### Implemented

- Added the project-scoped `knowledge_horizon_import_claims` ledger. Its database unique key is `(project_id, horizon_run_id, horizon_stage, horizon_item_id)`; it records the captured content hash, owning BSC run, lease, terminal state, and the immutable `source_id` actually used.
- `HorizonImportService` now claims each accepted Horizon item before creating evidence. A second worker reports a duplicate rather than creating a parallel `horizon_signal`; successful capture atomically binds the claim to the source. Capture exceptions release the claim, and an expired 15-minute lease can be safely reclaimed after a worker crash.
- The producer script defaults now use a 48-hour overlap and 300-second stage budget. The active Horizon profile uses four scoring workers, a bounded 1,536-token score budget, and the BSC-relevant public source set.

### Verification

- Added SQLite concurrency, release-after-failure, and expired-lease recovery coverage in `tests/knowledge/test_horizon_import.py`. Added an optional PostgreSQL contract in `tests/integration/test_knowledge_postgresql.py`.
- Focused Horizon regression passed: `tests/knowledge/test_horizon_import.py`, `tests/knowledge/test_knowledge_tasks.py`, `tests/knowledge/test_horizon_run_store.py`, `tests/api/test_knowledge_workspace_api.py`, and `tests/test_horizon_producer_script.py` -> `67 passed`.
- Full regression after the change passed: Python -> `1482 passed, 14 skipped`; frontend -> `23 files / 160 passed`; `npm run check` and `docker compose config --no-interpolate --quiet` passed. The skipped PostgreSQL pytest contracts require a host `TEST_POSTGRES_URL`; the same new claim operation was exercised directly against the running Docker PostgreSQL service.
- Rebuilt and restarted the production API, Worker, and Beat images. Container-side PostgreSQL verification proved one project claim is accepted, a duplicate claim is rejected, a second project remains isolated, and completion binds the expected source ID.

### Live Result

- The prior 72-hour run `run-20260729T154353Z-64a6ed6d` was audited after deployment: it has 10 `horizon_signal` records, every record remains `validated`, all 10 have Vault projections, and none has a Wiki citation.
- A first producer attempt from BSC's Python environment failed at `HZ_IMPORT_FAILED`; this was recorded as a producer failure and not misreported as an empty collection. The root cause was a Horizon runtime dependency mismatch. Retrying through Horizon's own complete Python environment succeeded and superseded that failure.
- Live no-enrichment producer run `run-20260729T160830Z-4e18a3cc` completed with `fetched=34`, `scored=34`, and `kept=9`. BSC imported it with `accepted=9`, `created=5`, `duplicates=4`, and a completed Vault mirror. The four duplicates are expected overlap reuse. All nine ledger claims are completed and bind nine `validated` `horizon_signal` records with zero Wiki citations.

### Remaining Boundary

- Google News and Reddit were unreachable during the successful producer run. Their failures remain source diagnostics; RSS, Hacker News, and GitHub yielded the 34 real candidates. No generated substitute was inserted for unavailable channels.

## Source Sync Recovery And Runtime Regression (2026-07-30)

### Implemented

- Added a dedicated `900s` abandoned-run recovery window for the five-minute
  `source_sync` schedule. The scheduler now uses this only for source
  synchronization; longer-running knowledge jobs retain the global Celery
  timeout. An interrupted sync is recorded as `failed` with
  `abandoned_run` and remains retryable, rather than appearing indefinitely
  as `running` or being overwritten by a later schedule claim.
- Passed the recovery setting through application configuration, the API and
  Worker Compose environment, and the durable schedule reconciler. Regression
  coverage asserts the isolated timeout, non-source-job compatibility, and the
  Compose contract.

### Verification

- The rebuilt Docker API, Worker, Beat, PostgreSQL, Redis, and n8n services
  were healthy. The old orphaned source-sync ledger entry was terminally
  recorded as `failed / abandoned_run`; a later real source-sync run completed
  without modifying immutable prior evidence.
- `pytest tests/knowledge/test_scheduler.py tests/knowledge/test_knowledge_tasks.py
  tests/test_config_sop_llm.py tests/test_docker_compose_contract.py
  tests/knowledge/test_growth_distillation.py tests/integration/test_abcd_growth_e2e.py
  tests/integration/test_pbos_e2e.py -q` passed with `106 passed`.
- `docker compose --profile full config --quiet` passed. This validation does
  not read Vault note bodies, plugin source code, or credentials.

### Boundary

- Recovery and scheduling are operational proof for the BSC side of the
  loop, not a claim that a third-party Obsidian plugin has exported content.
  User-origin Claudian and Zotero files remain required before their own
  capture paths can be promoted beyond `awaiting_export`.

## Claudian Output Lineage Contract (2026-07-30)

### Implemented

- Reclassified Claudian as an agent-workspace producer. Its configured Vault
  attachment folder is no longer presented as an automatic chat-export
  destination. The bridge becomes a registered D-layer route only after the
  agent writes an actual file below `04_Outputs/claudian/`.
- Added a bounded `bsc_output_contract: v1` for external agent deliverables.
  It retains declared title, output kind, goal, audience, channel, and only
  already-resolvable source/page references. A mismatched project declaration
  or unknown reference is rejected instead of crossing projects or creating
  synthetic lineage.

### Verification

- Added route-semantic, provenance-lineage, cross-project rejection, and CRLF
  parsing coverage. The affected backend integration/API suite passed with
  `112 passed, 1 skipped`; workspace frontend tests passed with `44 passed`;
  TypeScript and production builds passed.
- Rebuilt Docker API, Worker, and Beat. Runtime route readback is
  `agent_workspace`, `ready_for_first_output`, and `registered_outputs=0`.
  Celery `inspect ping` returned `pong`; scheduled source-sync run
  `298cea42ee58` completed with zero output files observed or registered.

### Boundary

- No BSC script wrote a file into the Claudian output route. The final
  plugin-origin proof requires an actual Claudian request to write a durable
  deliverable and a later evaluation/feedback action, so the governed loop
  remains `implemented_with_operational_proof_pending` rather than claiming
  release readiness prematurely.

## 2026-07-30 Published-State Repair: Live Closure

- The earlier note that the Docker image predated published-status
  reconciliation is superseded. The deployed publication gate projects
  durable BSC state into each managed Wiki page's top-level
  `status: published` field before the Vault snapshot and database revision
  are committed. Project lint reports a durable published page that says
  otherwise as `invalid_publication_status`.
- A real primary capture of the official Obsidian API README
  (`d868c7bd34af`) was used to compile and publish
  `wiki/concepts/obsidian-plugin-extension.md`. The first publication
  exposed stale `draft` frontmatter. Rather than editing the file, the
  repair created proposal `4a18d3a7e85f`, passed lint with zero findings,
  passed the persisted evaluation at score `1.0`, and published through run
  `ee3c56125438`. It corrected five existing published pages plus their
  navigation and audit entry without changing evidence claims.
- Post-publication runtime readback against Docker PostgreSQL and the managed
  Vault found no remaining draft or non-published Wiki frontmatter, project
  lint valid with zero findings, and the Obsidian page at version `2` with
  content hash
  `eb769555c96456a076186ecc81468f5b350ce0bd489589696cdfff4d93274a53`.
  Its active citation remains `d868c7bd34af`; the persisted graph contains
  the matching citation edge. Knowledge health reported 10 pages, 153
  sources, 37 active citations, citation coverage `1.0`, no orphan or
  uncited pages, no dangling or stale citations, no pending proposals, and a
  latest persisted evaluation status of `passed`.
- Regression evidence: the combined Wiki/API/task/recovery/PBOS suite passed
  `150 passed`; TypeScript `npm run check` and the production frontend
  build passed. The build keeps the pre-existing ECharts bundle-size warning;
  it is recorded as a performance follow-up and is not claimed fixed here.

## 2026-07-30 PBOS Published-Context Runtime Closure

### Defect And Repair

- A live no-write PBOS proof found that retrieval located the published
  Obsidian plugin page and its source, but a long evidence excerpt could use
  the bounded context budget and remove the page from rendered sections.
  `PBOSGovernedContextProvider` then used only rendered page sections, so the
  compiled plan fell back to working-note references despite the successful
  governed retrieval.
- The provider now retains retrieval-selected paths only when the corresponding
  BSC Wiki page is durably `published`. Those immutable page revisions are
  combined with their processed citation lineage; arbitrary Vault files still
  cannot enter this path. This is a reference-layer repair, not an expansion
  of the prompt body or a bypass of the publication gate.
- Added a regression that makes a source reservation displace a large selected
  page from the rendered context and proves the PBOS result still exposes the
  published page plus its source hash. `tests/pbos/test_pbos_contextual_compiler.py
  -q` passed with `10 passed`.

### Deployed Verification

- Rebuilt and restarted the Docker API, Celery Worker, and Beat images from the
  repaired workspace. `http://127.0.0.1:8002/ready` returned `200`; container
  validation imported `mcp.server.fastmcp.FastMCP` from the intentionally
  pinned `mcp==1.28.1`; and Celery `inspect ping` returned `pong` from the
  running worker.
- A temporary Artifact Graph was created inside the API container for a
  default-project Mission about the Obsidian plugin extension, then discarded.
  It wrote no Mission or plan to the user's durable graph. The compiled plan
  included the published-page reference
  `wiki:6d695376a04e63d49958c84c@eb769555c96456a076186ecc81468f5b350ce0bd489589696cdfff4d93274a53`
  and its processed evidence reference
  `source:d868c7bd34af@5c71bef8236b9dcaeb55216e523afc503fb12f0d15f6f0738b7bc9dde0c69b0c`.
- Post-restart project verification remained clean: published-Wiki lint had
  zero findings, health reported 10 pages, 153 sources, 37 citations,
  citation coverage `1.0`, zero dangling or stale citations, no pending
  proposals, and 78 persisted graph edges. The existing ECharts bundle-size
  warning remains a recorded performance follow-up, not a resolved claim.

## 2026-07-30 Custom SOP Model Path Verification

- The default project's PBOS context now has a verified real-model route in
  addition to its governed deterministic fallback. `PBOS_LLM_TIMEOUT_SECONDS`
  gives structured PBOS compilation a `120s` independent provider budget;
  API and Worker receive the setting through Compose while Beat does not.
- A temporary Docker-resident Artifact Graph used the configured DeepSeek
  provider to compile a project-specific knowledge-growth Mission. A bounded
  second structured attempt succeeded after the first produced no final
  content. The resulting discarded plan was `llm_contextual`, carried
  published Wiki/source lineage, and had three distinct phases rather than a
  template-only fallback. This test did not create a user-visible SOP,
  revision, source, output, or Vault file.
- Regression evidence: PBOS/API/MCP/integration/configuration/Compose suite
  `57 passed`; `npm run check`, Compose validation, Worker ping, and deployed
  runtime timeout readback passed. Existing external plugin routes remain
  truthfully `awaiting_export` or `awaiting_output` until their installed
  Obsidian plugins produce real files; BSC did not synthesize such exports.

## PBOS Contextual Plan Projection (2026-07-30)

- A real, provider-backed PBOS compilation now closes the knowledge-to-work
  loop for the default project. Durable plan `art_329d1014ff28` used five
  published Wiki references, fourteen processed source references, and three
  bounded Vault references before its three-phase contextual plan was written
  to `pbos/plans/art_329d1014ff28.md`.
- The projection is a D-layer working artifact with explicit compiler metadata,
  not new source evidence. It did not alter immutable A-layer captures,
  published B-layer citations, or plugin capture state. Provider failures
  remain safe, visible metadata and no longer trigger a futile structured
  repair request for payment or credential errors.
- Follow-up verification passed `82` PBOS/API/MCP/integration/configuration
  and LLM-client tests, five Cockpit component tests, TypeScript checking,
  the production frontend build, and the full Compose configuration contract.

## 2026-07-30 Growth Dispatch And Semantic Daily Closure

### Implemented

- Corrected growth recovery dispatch evidence. A queued growth run with either
  `knowledge.run.execution_assigned` or `knowledge.growth.dispatched` is now
  treated as already handed to Celery and will not be enqueued again by Beat
  recovery. New growth submissions from both the Wiki command service and the
  idempotent growth API now record the growth-specific dispatch event with the
  task ID and trigger while retaining the generic Celery assignment event.
- Added a regression for the production failure shape: a queued manual daily
  growth run with only the legacy assignment event must remain queued with zero
  recovery dispatches. The scheduler's generic duplicate branch recognizes the
  same assignment proof.
- Reworked daily semantic distillation from one-shot fallback into a bounded
  quality loop. Invalid model output is classified without retaining model
  body (`invalid_shape`, `missing_citation`, `missing_sections`,
  `invalid_reference`, or `unsupported_project_state`), then a configured
  provider may make exactly one citation-ledger constrained repair. The
  citation, project-state, ownership, hash, and atomic-Vault checks are not
  relaxed. Distillation contract revision is now `27` so same-day content is
  an auditable managed revision rather than an overwrite.

### Verified

- Focused command/API/Celery recovery tests passed `46`; the expanded
  growth/Obsidian/API/Celery suite passed `124 passed, 1 skipped`.
  `compileall`, `git diff --check`, and `docker compose --profile full config
  --quiet` passed.
- Rebuilt API, Celery Worker, and Beat. The deployed API returned `/ready`
  `200`, and deployed Worker inspection returned `pong`.
- The first post-recharge real daily run `c3cb8bf570a7` completed with 576
  governed inputs and a valid managed output, but its model response failed
  the daily output gate and was truthfully recorded as deterministic fallback.
  No unvalidated model text was persisted.
- After the repair, real default-project run `d809320a6084` completed through
  DeepSeek `deepseek-v4-pro` in `llm` mode. Its persisted distillation
  `d27404968c2aa5f8e2e56ec8` created the managed daily artifact at
  `distillations/每周蒸馏/2026-W31/每日增量/2026-07-30.md`. One correlated
  model execution was retained as metadata only; the final artifact passed
  managed ownership and hash validation. Its event sequence contains one
  assignment, one growth dispatch, one model completion, and no
  `knowledge.growth.duplicate_delivery` event.

### Remaining Boundary

- The actual daily knowledge loop is now operating with governed model output,
  but third-party Obsidian plugin routes remain correctly in
  `awaiting_export` or `awaiting_output` until those plugins create real files
  in their declared project directories. No synthetic plugin export or output
  acceptance was created for this verification.

## 2026-07-30 Semantic Weekly Runtime Closure

- Real default-project weekly run `f4cf667a653d` completed through
  `deepseek/deepseek-v4-pro` after two bounded provider invocations. The
  quality gate requested one constrained repair and accepted all five required
  weekly documents; the persisted record `c349e7026bc148be242aa2c7` is
  `mode=llm`, has `llm_document_count=5`, `fallback_document_count=0`, and
  `quality_retry_count=1`.
- The five managed paths in `distillations/每周蒸馏/2026-W31/` passed the
  persisted manifest, ownership-marker, and file-hash validation. The prior
  complete bundle was only eligible for replacement because the new bundle was
  complete; the guard would have retained it for a partial or invalid model
  response.
- The persisted event stream contains one assignment, one growth dispatch, one
  correlated model-completion record, and one completion; it contains no
  `knowledge.growth.duplicate_delivery` event. This verifies the repaired
  dispatch contract against both real daily and real weekly model workloads.

## 2026-07-30 Horizon Primary Evidence And Profile-Bound Proposal

### Live Intake

- The production Horizon run `run-20260729T160830Z-4e18a3cc` was imported into
  project `proj_b8a285642094` through the read-only native run store. The
  filtered stage contained nine scored signals; all nine were persisted as
  `horizon_signal` discovery records with `primary_capture_required=true`.
  Concurrent capture requests contended only on the durable import claim and
  produced exactly nine signal records, not duplicate evidence.
- All nine signal URLs were then captured as bounded public HTTPS primary
  evidence. Each capture passed private-network, redirect, content-type,
  response-size, extraction, hash, and signal-to-primary linkage checks. None
  of the radar summaries was promoted as primary evidence.
- Before final review, the project's knowledge profile was updated from its
  empty revision `0` to revision `1`: four project research domains, six
  intended output types, Chinese operating language, evidence threshold `75`,
  explicit-review publication policy, and outcome-backed method promotion.
  The earlier revision-0 reviews remain auditable but are intentionally stale.

### Model Review And Proposal

- A real-model semantic triage ran once per captured primary source under
  profile revision `1`. All nine evaluations completed reliably using
  `semantic-source-triage-v3`: four `knowledge_candidate`, two `reference`,
  and three `ignore`. The reference and ignore material remains validated but
  is not authoring evidence.
- Delegated operator approval made only the four reliable, profile-bound
  primary candidates `eligible`. Each approval records its triage ID, profile
  revision, evaluator revision, and exact supporting Horizon signal. This did
  not publish a page or alter immutable source bodies.
- Wiki maintenance run `91b6d67ddb7d` compiled those four eligible sources
  into draft proposal `786db8f24191`. The proposal contains four cited
  operations, including the candidate concept page
  `wiki/concepts/agent-policy-adherence-failures.md`, and reports
  `publication=review_required`. It remains `draft`; no Obsidian Wiki file was
  published by this run.

### Verification And Remaining Boundary

- Proposal lint passed with zero findings. The live health snapshot reports
  30 project sources, four eligible authoring sources, zero dangling or stale
  citations, one pending proposal, and no persisted quality-evaluation trend
  because the proposal has not been published.
- The next deliberately unexecuted boundary is explicit review and publication
  of proposal `786db8f24191`. Until that action occurs, its cited sources are
  correctly reported as uncited eligible evidence and the generated page is not
  treated as usable PBOS or weekly-distillation knowledge.

## 2026-07-30 Personal Knowledge Intelligence Live Closure

### Published Knowledge

- The delegated manual review was completed through the governed publication
  endpoint. Proposal `786db8f24191` is now `published` with a recorded
  evaluation score of `1.0`; the published concept page is
  `wiki/concepts/agent-policy-adherence-failures.md`.
- The four reviewed primary evidence records (`6d535597e335`, `25f7a2c18f19`,
  `00f21204a550`, and `95ffcbe545ee`) transitioned to `processed`. Readback
  confirmed their presence in persisted `wiki_cites_source` graph edges.
- Post-publication health was clean: 5 pages, 30 sources, 5 citations, 100%
  citation coverage, no dangling or stale citations, no uncited eligible
  sources, no pending proposals, no contradictions, and a passing evaluation
  baseline. The published Vault page has `status: published` front matter.

### Profile-Bound Weekly Distillation

- A direct synchronous attempt was interrupted when the Docker API container
  was externally recreated. It made no new persisted weekly output. The retry
  used durable Celery run `ae448b20d062` with the fixed idempotency key
  `manual-post-publish-weekly-2026W31-r1` and completed once without retries or
  duplicate delivery.
- The new weekly distillation `6f5b8ec41253b4f384e44955` generated five
  managed documents for `2026-W31` in `llm` mode using
  `deepseek/deepseek-v4-pro`. It used profile revision `1`, contained no
  fallback documents, and was bound to input hash
  `cd4bfe76b52d83010c4bc06a785488dd23462b5107b998c962f3d0a77c223969`.
- API readback checked every generated document without retaining its body:
  all five have the managed ownership marker, the exact input-hash marker, at
  least two Markdown sections, one or more persisted source/page citations,
  and an explicit uncertainty marker. The managed next-context handoff is the
  fourth document of the current `2026-W31` weekly bundle under the project's
  `distillations/` tree.

### Context And Automation

- A live PBOS governed-context read returned `available` with 8 bounded
  documents and 12 traceable references. It includes published Wiki context,
  a managed evidence mirror, and the new weekly handoff; no raw Vault corpus
  was passed through the plan boundary.
- Persistent automation is enabled and scheduler-backed: daily growth at
  `17:00` and weekly distillation at Friday `17:30`, both in
  `Asia/Shanghai`. The last run status for both schedules is `completed`.
- This project has no PBOS Mission, personal profile, execution record, or
  outcome in its Artifact Graph. No synthetic personalized plan, output, or
  outcome was created. Personalization can begin only after a real Mission and
  user-provided working context exist.

### Remaining External Boundary

- Obsidian third-party plugins still have no real export or output files in
  their declared project paths. Their integration state remains
  `awaiting_export`/`awaiting_output`; the filesystem source, output, and
  context channels are the only verified ingestion paths at this point.

## 2026-07-31 Governed PRD-to-SOP Response Budgeting

- **Gap closed:** Chinese project PRDs with a broad evidence context could
  consume the provider response before the required structured SOP was
  complete. The generator now uses a bounded 16,000-character context pack,
  a compact 4-to-6 phase response contract, and one 10,000-token structured
  attempt. This preserves project-specific evidence references while reserving
  completion capacity for valid JSON.
- **Safety retained:** the prompt still permits only supplied source/page
  identifiers, keeps assumptions and research gaps explicit, and rejects
  generic templates. A response is not a published method, accepted output,
  or proof of an executed SOP.
- **Verification:** `pytest tests/knowledge/test_prd_to_sop.py
  tests/api/test_growth_api.py tests/integration/test_knowledge_sop_e2e.py
  tests/integration/test_abcd_growth_e2e.py -q` passed `35`; `npm run check`,
  `npm run build`, `docker compose config --quiet`, and `git diff --check`
  passed.
- **Rollback:** revert the PRD-to-SOP request settings and prompt limits
  together. Existing runs, context packs, and SOP artifacts remain immutable
  ledger history.
