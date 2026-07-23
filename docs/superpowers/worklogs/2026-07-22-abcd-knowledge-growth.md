# BSC A/B/C/D Knowledge Growth - Worklog

**Design:** `docs/superpowers/specs/2026-07-22-bsc-abcd-knowledge-growth-product-prd.md`
**Execution index:** `docs/superpowers/plans/2026-07-22-abcd-growth-execution-index.md`
**Consolidated plan:** `docs/superpowers/plans/2026-07-22-abcd-growth-consolidation.md`
**Started:** 2026-07-22
**Status:** P1-P9 implementation and release verification complete in isolated fixtures and the Docker profile; real third-party account calls remain explicitly unclaimed.

## 2026-07-23 Connectivity Audit And Closure

**Trigger:** The project workspace reported that recently added capabilities were not visibly connected end to end.

| Chain | Audit result | Closure evidence |
|---|---|---|
| Studio execution -> governed D outputs | Connected when the project has a Vault mapping and growth context. `run_business_runtime` registers structured deliverables through `OutputCompletionBridge`; unreviewed outputs remain excluded from future context. | Existing Agent OS convergence tests; no false claim for an unmapped user Vault. |
| D output / repeated work -> C method candidates | Broken at the review surface: `MethodDetector` could persist a candidate, but the Growth review queue neither listed nor opened it. | Added repository listing, list/detail REST contracts, review counts, candidate reader, persisted evaluation action, and guarded publication action. |
| Growth workspace -> durable daily/weekly loop | API and Celery task existed, but the Growth workspace had no direct trigger or latest-run feedback, forcing users to switch panels. | Added daily/weekly controls backed by `/knowledge/growth/{project_id}/runs`, then reload the durable run list and display the actual latest status. |
| Runtime -> visual feedback | The Growth workspace now shows candidate review records and last-cycle state alongside the existing A/B/C/D assets, health, trends, and lineage. | Frontend component tests cover candidate opening and durable run submission. |

**Verification after closure:**

- `python -m pytest tests/api/test_growth_api.py tests/knowledge/test_feedback_router.py tests/integration/test_growth_celery.py -q`: 27 passed.
- `npm run test:frontend -- --run src/api/growthApi.test.ts src/components/growth/GrowthWorkspace.test.tsx`: 33 passed.
- `npm run check`, `npm run build`, and `git diff --check`: passed. The existing Vite large-chunk warning remains non-blocking.
- Rebuilt the `bsc-growth-e2e` Docker profile on ports `18082`, `16379`, and `15433`. API health is 200; Worker advertises both `knowledge.execute` and `knowledge.growth.execute`; OpenAPI exposes the new method-proposal routes.

**Remaining external boundary:** A real project Vault still requires a valid Studio access key and a project mapping before user-owned Obsidian files can be touched. This is intentionally not simulated by the audit.

## Status Board

| Plan | State | Evidence | Blocker |
|---|---|---|---|
| P1 Contracts/profile/Vault | Complete | Contracts, schema/Vault tests and final full regression | Additive contracts verified |
| P2 Capture/triage/integrations | Complete | Capture/triage/import tests and isolated fixture lifecycle | Live provider call not claimed |
| P3 Output/feedback/lineage | Complete | Registry/evaluator/router plus A-to-D fixture | Durable lineage verified |
| P4 Method evolution | Complete | Detector/evaluator/gate and regression cases | Promotion and rollback guarded |
| P5 Context/generation | Complete | Scoped context and SOP integration tests | Provenance recorded |
| P6 Automation/distillation | Complete | Scheduler/task/recovery tests plus Redis Worker/Beat runtime | Idempotency and file protection verified |
| P7 API/MCP | Complete | REST/SSE/MCP authorization and compatibility tests | Project isolation verified |
| P8 Workspace/visualization | Complete | 52 frontend tests, build and populated browser checks | Real API data, no mock fallback |
| P9 Integration/release | Complete | Full regression, PostgreSQL parity, performance, Docker rebuild/recovery and browser evidence | External live accounts remain out of scope |

## 2026-07-22 - Consolidated Production Authority

- Combined P1-P9 dependencies, invariants, task groups, exact focused commands, all 20 PRD acceptance scenarios, release exclusions and rollback order into `2026-07-22-abcd-growth-consolidation.md`.
- The nine detailed plans remain the implementation specifications; the consolidation file is now the single closure checklist.
- Added project-scoped Growth context wiring to the legacy orchestrator path. Explicit `project_id` now survives first execution, reviewer loopback and targeted rerun.
- Empty or unconfigured Growth context no longer masks an available Wiki context. Real Growth context preserves profile, page, source, method revision, output, assumption and research-gap metadata.
- Verification: `tests/knowledge/test_growth_context.py`, `tests/orchestrator/test_wiki_methodology_bridge.py`, `tests/orchestrator/test_engine.py` and `tests/orchestrator/test_api.py` passed: 36 tests, one existing Starlette/httpx deprecation warning.
- Completion remains open pending the consolidated P9 lifecycle, PostgreSQL, Docker restart, authorized non-empty browser, performance and full-regression gates.

## 2026-07-22 - PRD Decomposition

### Completed

- Read the approved A/B/C/D product PRD and mapped FR-1 through FR-16 plus all 20 acceptance scenarios.
- Audited the completed 2026-07-21 P1-P8 index and representative implementation plans.
- Confirmed the additive scope: project profile/triage, C methods, D outputs, feedback/lineage, growth context, dual cadence, API/MCP and workspace expansion.
- Created one execution index and nine bounded test-first implementation plans.
- Preserved current runtime database changes and unrelated untracked files without staging or modification.
- Implemented and tested P1-P8 locally without touching the user Vault at `D:\bsc`.

### Contract Decisions

- The prior A/B implementation is a frozen dependency; these plans do not reimplement it.
- D feedback is typed and gated; no unconditional D-to-A or D-to-B route exists.
- P1 owns all new states, persisted entities and lineage contracts to prevent parallel schema drift.
- P6 and P7 are the only production plans permitted to run in parallel, after P5.
- The worklog separates planning completion from production completion; unchecked implementation tasks remain truthful.

### Implementation And Verification

- Ten `2026-07-22-abcd-growth-*.md` files exist: one execution index plus P1-P9.
- Each P1-P9 plan contains goal, dependency, owned/forbidden files, frozen contracts, unchecked test-first tasks, exact verification commands, acceptance criteria, rollback strategy and handoff output.
- The execution index covers FR-1 through FR-16 and freezes the A/B/C/D authority, lifecycle, lineage, automation, compatibility and parallel-boundary contracts.
- `git diff --check -- docs/superpowers/plans docs/superpowers/worklogs` passed.
- `git status --short` shows only the new planning/worklog/PRD files plus pre-existing user/runtime changes: `app/bsc_cloud.db`, `app/bsc_cloud.db-shm`, `.agents/`, `output/resume/`, and `skills-lock.json`.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_scheduler.py tests/knowledge/test_scheduler.py tests/knowledge/test_knowledge_tasks.py tests/integration/test_knowledge_celery.py -q` passed: 18 tests.
- `./.venv/Scripts/python.exe -m pytest tests/mcp/test_growth_tools.py tests/mcp/test_growth_http_contract.py tests/mcp/test_wiki_tools.py tests/mcp/test_wiki_http_contract.py tests/test_mcp_http.py tests/test_mcp_compatibility.py -q` passed: 18 tests.
- `npm run test:frontend` passed initially with 12 tests and again after the responsive scroll-lock change with 13 tests in 5 files; `npm run check` passed; `npm run build` passed; `npm run lint` passed with 194 pre-existing warnings and 0 errors.
- P6 growth jobs are `growth_daily` and `growth_weekly_distillation`, using existing durable `knowledge.execute`/schedule claims; missing feature flags, Vault and broker remain explicit `unavailable` states.
- P7 growth MCP authorization is independent from the legacy Wiki flag but still enforces global/project scope, reader restrictions and `KNOWLEDGE_MCP_WRITE_ENABLED`.
- P8 adds `src/api/growthApi.ts`, `src/components/GrowthWorkspace.tsx`, a Growth entry point in `UnifiedWorkspace`, and responsive styles in `src/index.css`; no mock records are used.
- P9 now has Docker/Redis/Celery and desktop/mobile browser evidence. PostgreSQL, performance, Horizon, Feishu and live LLM evidence remain open and are not claimed.

## 2026-07-22 19:07 - P9 Docker And Browser Acceptance

- **State:** Docker and browser portions complete; P9 remains in progress.
- **Changed files:** responsive scroll lock in `src/components/UnifiedWorkspace.tsx` and `src/index.css`; evidence in this worklog, the execution index and `tests/integration/test_abcd_growth_browser.md`.
- **Verification commands and results:** `npm run test:frontend` passed 13 tests in 5 files; `npm run check` passed; `npm run build` passed; `git diff --check` passed.
- **Runtime evidence:** `docker compose up -d --build bsc-backend celery-worker celery-beat` completed successfully. API was healthy and `/health` returned HTTP 200; Redis returned `PONG`; Celery inspect returned one online worker with `pong`; `knowledge.execute` and `knowledge.reconcile_schedules` were registered; Beat started with `PersistentScheduler` against `redis://redis:6379/0`.
- **Browser evidence:** Docker product `http://127.0.0.1:8002/` loaded authenticated Growth data. At `390x844`, document root client/scroll widths were both 390; at `1280x720`, both were 1280. No whole-page horizontal overflow, control overlap, unavailable error, fake funnel data or blank Growth workspace was observed. A/B/C/D/Review navigation, zero-data funnel, stage assets, lineage and Inspector states rendered.
- **Compatibility:** the existing Studio remains mounted behind the Growth workspace, and closing Growth restores the original surface. Existing orchestrator, Artifact Graph and MCP transport contracts were not changed.
- **Deviations/risks:** the production JavaScript chunk remains above Vite's 500 kB advisory threshold. PostgreSQL parity, 10,000-record p95, restart/replay fixture proof and live Horizon/Feishu/LLM providers are not verified by this entry.
- **Rollback exercised:** the Growth workspace close path and feature isolation are present; destructive rollback was not executed against the user's runtime or Vault.
- **Handoff:** continue P9 Tasks 1-4 and 6 using isolated fixtures only. Do not use `D:\bsc` or runtime SQLite files as release fixtures.

## 2026-07-22 23:15 - P1-P9 Final Closure And Runtime Recovery

- **State:** complete for the integrated codebase, disposable fixtures and Docker release profile.
- **Production changes verified:** source capture/triage, profile and Vault contracts, output feedback lineage, governed methods, project context, daily and Friday distillation, REST/SSE/MCP, and the A/B/C/D/Review workspace are present and exercised. The Inspector no longer exposes raw active-revision JSON, and dense lineage uses a stable A-to-B-to-C-to-D-to-Review layout without unreadable edge-label overlap.
- **Python verification:** `./.venv/Scripts/python.exe -m pytest -q --durations=20` completed with `983 passed, 11 skipped, 3 warnings` in `267.02s`. The only warnings are existing FastAPI/Starlette and Pydantic deprecations. The suite includes the isolated lifecycle, isolation, recovery, PostgreSQL and 10,000-record performance gates.
- **Frontend verification:** focused tests passed `18`; full frontend tests passed `52`; `npm run check` passed; `npm run lint` had `0` errors and `193` pre-existing warnings; `npm run build` passed with the known Vite chunk-size advisory.
- **Docker and PostgreSQL:** `docker build -t bsc-growth-e2e-bsc-backend .` completed. The new image was used to recreate API, Worker and Beat in project `bsc-growth-e2e`. API health at `http://127.0.0.1:18082/health` returned `200` with PostgreSQL connected. PostgreSQL and Redis are healthy; Worker registered `knowledge.execute`, `knowledge.growth.execute` and `knowledge.reconcile_schedules`; Beat connected to Redis with `PersistentScheduler`. The API PostgreSQL reconnect path was tested by restarting PostgreSQL and retrying without an API restart.
- **Live task confirmation:** Redis returned `PONG`. A Worker-dispatched `knowledge.reconcile_schedules` task completed with `queued=0`, `duplicates=0`, `failures=0` and `recovered=0`; this confirms broker, Worker result backend and task return plumbing without creating fake work.
- **Browser acceptance:** authenticated real fixture data populated A/B/C/D/Review, five B pages, one C method, four accepted D outputs and review feedback. Lineage increased from 22 to 23 edges and traversed output to method revision to Wiki page to source. ECharts and React Flow pixel checks were nonblank. Desktop `1280x720` and mobile `390x844` had no document-root horizontal overflow; mobile Inspector focus and Escape close, stage ArrowRight navigation, permission failure, offline API, disabled Growth, PostgreSQL 500/recovery and reduced-motion/contrast checks passed with no console errors or warnings.
- **Release-scope check:** `git diff --check` passed. Runtime database files, `.agents/`, `output/resume/`, `skills-lock.json`, `.env`, `D:\bsc`, generated data and credentials remain excluded from release scope.
- **External boundaries:** Horizon, Feishu and live model-provider account calls were not executed because no authorized live integration run was supplied. This is not represented as successful execution; the implemented unavailable/error contracts were tested instead.
- **Rollback:** additive schema/data is retained. Disable growth feature flags and schedules first, then remove UI/API exposure and bridges in reverse P9-to-P1 order without deleting user Vault files or audit records.
- **Handoff:** all P1-P9 plan checkboxes and all 20 PRD acceptance rows are complete with fixture/runtime evidence. A production rollout requires only normal secret rotation and explicit provider onboarding, not further feature implementation.

## 2026-07-22 23:35 - Current Commit Reverification

- **State:** complete; the committed P1-P9 implementation was independently re-audited after the original closure entry.
- **Plan-to-code audit:** all explicit P1-P9 implementation paths listed in the detailed plans exist in the repository. The only absent path is `app/bsc_cloud.db-shm`, which P9 explicitly excludes as runtime data.
- **Full regression:** `./.venv/Scripts/python.exe -m pytest -q --durations=20` passed with `983 passed, 11 skipped, 3 warnings` in `265.16s`. The skipped cases are external/optional integration boundaries and are not used as completion evidence.
- **P8 frontend:** `npm run test:frontend` passed `52` tests; `npm run check` passed; `npm run lint` reported `0` errors and `193` existing warnings; `npm run build` passed with only the existing Vite chunk-size advisory.
- **P9 PostgreSQL and Docker:** the Docker PostgreSQL lifecycle parity test passed (`1 passed`) against the live `bsc-growth-e2e` database. A new `bsc-growth-e2e-bsc-backend` image was built, then API, Worker and Beat were recreated from it. API health returned `200`; Redis returned `PONG`; PostgreSQL remained healthy; Worker executed `knowledge.reconcile_schedules` successfully; Beat connected through Redis with `PersistentScheduler`.
- **Browser failure truthfulness:** the current Docker workspace opened the Growth surface without console errors. Without an access key, it rendered the expected `authentication required` error and showed no prior project data or mock fallback. Authenticated populated-data journeys remain covered by the committed P9 browser fixture and frontend tests.
- **Test hygiene:** two four-hour-old background growth API test processes from an earlier run were confirmed stale and stopped after the fresh full suite had passed.
- **Scope:** no source change was needed. Runtime databases, `.agents/`, `output/resume/`, `skills-lock.json`, Vault data and credentials remain outside the commit.

## 2026-07-23 - Studio Runtime Connectivity And Live Agent OS Trial

- **State:** complete.
- **Changed files:** `vite.config.ts`, `.env.example`, `src/components/UnifiedWorkspace.tsx`, `src/components/UnifiedWorkspace.test.ts`, `src/index.css`, `docker-compose.yml`, and `tests/test_docker_compose_contract.py`.
- **Contracts:** Vite reads `VITE_API_PROXY_TARGET` through `loadEnv`, preserving the local API default while allowing the e2e Docker API on port 18082. The Studio accepts a session-only BSC runtime access key and translates transport and 401 failures into actionable messages. Docker API containers always receive the in-network Redis URL instead of attempting `localhost`.
- **Tests first:** focused runtime error tests passed (2), the complete frontend suite passed (54), and the Compose contract suite passed (4).
- **Verification commands and results:** `npm run test:frontend`, `npm run check`, and `npm run build` passed before the final runtime validation. `npm run lint` completed with 0 errors and 193 existing warnings. `docker compose config --quiet` and `git diff --check` passed.
- **Runtime evidence:** rebuilt the `bsc-growth-e2e` API, Worker and Beat image set. The API health endpoint returned 200 with PostgreSQL, Redis, Celery and DeepSeek provider all healthy. An authorized browser run reached `POST /agent/analyze` with HTTP 200, executed 11 Agent OS capability stages in LLM mode, generated 34 artifacts and returned 9 evidence gaps. The visible result reported 51% constraint coverage and recommended a controlled pilot rather than a full rollout. No `Failed to fetch`, unauthenticated fallback, mock result or fabricated success was observed.
- **Credential handling:** authorized test credentials were supplied only as transient container/runtime input. They were not added to source, `.env`, Vault content, output files, the worklog, or the commit.
- **Compatibility:** the change is additive to the Studio and does not change existing orchestrator, MCP or Artifact Graph semantics. The same Docker health profile now uses the actual Compose network Redis address.
- **Deviations/risks:** the production JavaScript chunk-size advisory remains. The runtime key is intentionally session-only, so a browser reload requires entry again; persistent client-side credential storage is deliberately not implemented.
- **Rollback exercised:** removing `VITE_API_PROXY_TARGET` restores the default local API proxy. Recreating the test containers without transient credential inputs removes the live-provider session without touching named volumes or the Obsidian Vault.

## 2026-07-23 - Agent OS Knowledge Context And Obsidian Plugin Export Integration

- **State:** implementation complete; user-Vault execution remains deliberately unverified until a mapped project is selected in the Studio.
- **Problem corrected:** Agent OS previously created a transient project, bypassed the Growth/Wiki context services, and discarded SOP/strategy/report model outputs. A `fresh` run therefore looked knowledge-aware in the product but was structurally generic.
- **Changed contracts:** `DeliverableArtifact` now persists SOP, strategy, optimization and decision-brief outputs with actions, differentiators and evidence gaps. Growth context is retrieved first, Wiki is the bounded fallback, and the injected Vault text is never returned to the browser. Runtime metadata reports only the context-pack revision, governed references, omissions and research gaps.
- **Studio behavior:** the control rail now uses the same project ID as the Knowledge workspace for Agent OS, Board and Compiler requests. A run displays `used` only after the backend confirms a context pack; it otherwise exposes the unavailable reason. The result inspector displays real project deliverables instead of falling back to objective strings.
- **Obsidian plugin boundary:** BSC continues to ignore `.obsidian` configuration and executes no third-party plugin code. A mapped project may opt into `bsc-plugins.json`; declared `filesystem_drop` exports under `raw/` or `inbox/` are captured as immutable evidence with plugin provenance. The Knowledge workspace reports supported manifest adapters and does not claim unknown plugins are connected.
- **Tests first and focused verification:** `tests/test_capability_deliverables.py`, `tests/test_context_policy.py`, `tests/test_agent_runtime_convergence.py`, and `tests/knowledge/test_wiki_sync.py` passed with `30 passed, 1 skipped`. The assertions cover fresh-context injection, no context-text response leak, persisted SOP/report deliverables, stable export order, and plugin-export provenance.
- **Frontend and runtime verification:** `npm run test:frontend` passed `54`; `npm run check` and `npm run build` passed; `npm run lint` had `0` errors and `194` existing warnings. `docker compose -p bsc-growth-e2e ps` confirmed healthy API, PostgreSQL and Redis plus active Worker and Beat. `git diff --check` passed.
- **Deployment recovery:** the updated image was rebuilt and deployed to `bsc-growth-e2e`. A separate `bsc-backend` project owns port `8002`, so this environment was explicitly restored on its existing `18082` API, `16379` Redis and `15433` PostgreSQL bindings. `/health` returned `ok`; `/agent/health` correctly required authentication and was not bypassed.
- **Full-suite result:** `986 passed, 11 skipped, 1 failed` in 274.90 seconds. The failure is the pre-existing asynchronous endpoint timing threshold at `tests/orchestrator/test_api.py:306`: the shared runtime SQLite state persisted a `202` creation request above 0.2 seconds. It is unrelated to the knowledge/context assertions and remains visible rather than treated as passing. Best-effort metrics were moved off the response path; the timing case still depends on the user runtime database and must be rerun against an isolated test database before release acceptance.
- **Safety:** no Vault contents, `.obsidian` configuration, credentials, or runtime database files were read into source, tests, or this worklog. No unreviewed Agent OS deliverable was written into the D-layer output folder.

## 2026-07-23 - Knowledge Runtime Loop And Plugin Capture Evidence

- **State:** complete.
- **Problem corrected:** an Agent OS run could read mapped Growth context but its structured deliverables stopped in the Artifact Graph. `fork` and `resume` counted persistent project context without inserting it into the actual prompt. Plugin status represented manifest configuration rather than a confirmed captured export.
- **Changed contracts:** completed Growth-context runs now register each structured deliverable as a project-scoped D-layer output with source/page/method/context lineage. Outputs are `registered` and require the existing evaluator/feedback gate before reuse. Runtime metadata returns only registration IDs and status. Pending D outputs are surfaced as `output_not_accepted` omissions without their body being read into a future context pack.
- **Plugin boundary:** plugin adapters now report `awaiting_export` until `source_sync` captures a declared `filesystem_drop` export; then they report captured-source counts and timestamp. BSC still neither reads `.obsidian` configuration nor executes a third-party plugin.
- **Tests first and focused verification:** `tests/test_context_policy.py`, `tests/test_agent_runtime_convergence.py`, `tests/knowledge/test_wiki_sync.py`, and `tests/integration/test_growth_output_bridges.py` passed with `39 passed, 1 skipped`. The isolated end-to-end fixture proves context injection, D-layer materialization, provenance, prompt/credential exclusion, and pending-output non-reuse.
- **Frontend verification:** `npm run check`, `npm run test:frontend` (`54 passed`), `npm run build`, and `git diff --check` passed. The build still reports the pre-existing large-chunk advisory.
- **Runtime evidence:** rebuilt and recreated `bsc-growth-e2e` API, Worker and Beat with the updated image. The API on `http://127.0.0.1:18082/health` returned `200`; API health, Worker, Beat, Redis and PostgreSQL containers are up. The API is configured for its existing SQLite runtime in this environment, so no claim of an API-to-PostgreSQL migration is made here.
- **Safety:** no live Vault files, actual plugin configuration, credentials, or runtime database contents were used as fixtures. The test Vault and database are temporary isolated paths.

## 2026-07-23 - Vault Connection And Plugin Bridge Correction

- **State:** implementation complete; live user-Vault mutation remains intentionally pending authenticated user action.
- **Problem corrected:** the Studio runtime key and Knowledge Workspace key entry were duplicated, so a user could authenticate the Agent OS but still see an unauthenticated Vault surface. The plugin path required manually creating a manifest outside the product, so installed plugins had no usable handoff path.
- **Changed contracts:** Knowledge Workspace now consumes the Studio session-only runtime key and reports that shared state instead of collecting a second credential. Workspace status returns the configured relative project Vault path. An authenticated project admin can register governed `filesystem_drop` export bridges through `PUT /knowledge/workspaces/{project_id}/plugins`; the endpoint validates unique plugin IDs, bounded manifests, and paths under `raw/` or `inbox/`, then atomically writes only `bsc-plugins.json` in the mapped project boundary.
- **Plugin evidence:** the bridge status stays `awaiting_export` until `source_sync` captures an actual exported document. The endpoint-to-manifest-to-sync fixture proves a declared Readwise-style export becomes immutable `obsidian_plugin:readwise` evidence with plugin provenance. BSC still does not inspect or execute `.obsidian` plugin configuration.
- **Verification:** `python -m pytest tests/api/test_knowledge_workspace_api.py tests/knowledge/test_wiki_sync.py -q` passed with `14 passed, 1 skipped`; `npm run check`, `npm run test:frontend` (`55 passed`), `npm run build`, and `git diff --check` passed. Production build retains only the existing large-chunk advisory.
- **Browser evidence:** the local Studio at `http://127.0.0.1:5174/` shows one shared `Studio access required` state with Sync, Maintain and Map Vault disabled while unauthenticated. It no longer displays a second access-key field, no access is fabricated, and the empty health card reads `Health unavailable` rather than `Evaluation undefined`.
- **Docker deployment:** rebuilt and recreated `bsc-growth-e2e` API, Worker and Beat from this source state. `http://127.0.0.1:18082/health` returned HTTP 200, PostgreSQL and Redis stayed healthy, and the live OpenAPI document confirms `/knowledge/workspaces/{project_id}/plugins` is deployed.
- **Next real-run requirement:** enter the existing runtime access key once in Studio, choose the intended project ID, map the relative project folder, initialize Wiki, register each actual plugin export directory, and run source sync. This is the only remaining step needed to establish evidence from the real Vault; it was not bypassed or simulated against `D:\bsc`.

## 2026-07-23 - Runtime Connectivity Closure

- **State:** deployed and verified. The Studio, durable runtime, PostgreSQL, Redis cache/event stream and Celery workers now use one connected service graph.
- **Problem corrected:** the prior Docker profile ran API/Worker/Beat on SQLite and memory cache while PostgreSQL and Redis were only sidecar containers. The frontend was serving current source on `5174`, but its proxy target had to be verified rather than inferred. The prior PostgreSQL data volume also belonged to an incompatible historical cluster, so it could not be safely adopted by the configured application role.
- **Changed contracts:** API, Worker and Beat now require healthy Redis and PostgreSQL dependencies, use PostgreSQL as their only database backend, use Redis for cache and event transport, and derive the internal database URL from the PostgreSQL service credentials. Redis and PostgreSQL are default Compose services. The original PostgreSQL volume remains untouched as rollback material; the active cluster uses `postgres-data-v2`.
- **Migration safety:** added `app/core/sqlite_postgres_migration.py` and `scripts/migrate_sqlite_to_postgres.py`. The utility defaults to dry-run, refuses a non-empty target, writes a JSON-only operational report, and creates an SQLite native backup snapshot before copying. It excludes only rebuildable FTS internals and `schema_migrations`; it never reads or writes the Obsidian Vault.
- **Applied migration:** the current runtime SQLite snapshot contained 66 tables and 847 rows. It migrated 840 business rows across 60 tables into the new PostgreSQL database. The remaining seven rows were `knowledge_fts_*` internals and schema metadata, all intentionally rebuildable. A pre-copy SQLite snapshot and migration report are retained in the Docker data volume.
- **Verification:** PostgreSQL migration, growth parity, Wiki persistence, orchestrator persistence and Compose tests passed (`10 passed`). `docker compose config --quiet`, `compileall`, and `git diff --check` passed. Runtime `/health` and `/ready` report PostgreSQL and Redis `ok`; the live container instantiates `RedisEventBus` and `RedisCache`; Celery worker ping passed and registered `knowledge.execute` plus `knowledge.growth.execute`.
- **Browser evidence:** the user-facing `5174` Studio proxy returned API `401` rather than falling through to Vite, proving it reaches the live API. The Knowledge workspace mounted without browser errors and truthfully displayed `Studio access required`; no unauthenticated Vault, plugin, source, run, or schedule state was fabricated.
- **Rollback:** restore `postgres-data` as the PostgreSQL mount or point the Compose services back to SQLite; the original SQLite runtime file and the immutable pre-cutover snapshot remain available. No user Vault file, `.obsidian` configuration, `.env`, or secret was inspected or changed.
- **Remaining live boundary:** the platform infrastructure is connected. A real A-to-B-to-C-to-D Vault adoption still requires entering the existing Studio runtime key, mapping the intended project, initializing it if needed, and running the governed cycle. That boundary is intentionally user-authorized rather than bypassed.

## Entry Template

## 2026-07-23 - Vault Connection Truth And Plugin Export Usability

- **State:** complete for product diagnostics and deployment; real project authorization remains intentionally pending.
- **Problem observed:** the current Studio showed an unauthenticated `default` project and therefore no live Vault or plugin evidence. The prior UI also treated a persisted Vault mapping as an implied connection and exposed a single technical plugin form, making installed-plugin export status hard to diagnose or correct.
- **Changed contracts:** workspace status now distinguishes unconfigured, unavailable, mapped-but-uninitialized, incomplete, and ready project Vault states without reading user-authored Vault content. The Workspace exposes a verifiable access-to-Vault-to-plugin-export-to-governed-use path, plugin presets, multiple declared export paths, bridge editing/removal, and source-level plugin provenance.
- **Safety:** BSC still does not inspect `.obsidian`, run plugin code, read live Vault content during status checks, or treat a bridge registration as a captured source.
- **Verification:** focused workspace/sync tests passed (`14 passed, 1 skipped`); the broader knowledge verification passed (`40 passed, 3 skipped`); the frontend suite passed (`56 passed`); type checking, production build and diff checks passed. The production bundle retains the existing chunk-size advisory.
- **Browser and deployment evidence:** desktop and 390px mobile browser runs both showed the explicit unauthenticated path: Studio access required, no Vault boundary, no plugin bridge and no published context. Docker API, Worker and Beat were rebuilt from this source; the API returned HTTP 200 and the deployed OpenAPI still exposes the plugin bridge endpoint.
- **Remaining live proof:** enter the session-only Studio access key, select the intended mapped project, declare each installed plugin's actual `raw/` or `inbox/` export paths, then run Sync. The workspace will only mark a bridge captured after it has created immutable source records; it will not mark plugin installation or registration as success.

## 2026-07-23 - Real Knowledge Loop Reverification And Publication Gate Repair

- **State:** complete for the isolated browser lifecycle; the real user Vault remains untouched.
- **Problem observed:** the browser-initiated `wiki_maintenance` run accepted a generic structured response whose operations omitted the required `operation` field. The first mapped-Vault initialization also exposed a Windows `os.replace` permission failure; the retry after the Vault fix succeeded.
- **Compiler correction:** `SOPWikiCompilerProvider` now gives the model the exact governed operation schema, validates it before the compiler consumes it, and sends one schema-only repair request for a malformed response. It never infers `create`, `replace`, or `append`, so an invalid model response cannot cause an unintended Vault write.
- **Real model/browser evidence:** an isolated project under `output/knowledge-e2e-proof` mapped a temporary Vault, registered a Readwise-style `raw/readwise` plugin bridge, synced an actual exported Markdown document into immutable `obsidian_plugin:readwise` evidence, promoted it, and ran maintenance through the browser. The configured external model returned a reviewable four-operation proposal with one immutable source reference; no user Vault, `.obsidian` configuration, raw user evidence, or credential was read or written.
- **Publication gate repair:** the first manual publication correctly stopped at `missing evaluation baseline`, but the UI had no way to define the project-specific baseline. The proposal view now persists a user-defined content/SOP/citation/retrieval case before the normal validation-and-publish action. In the isolated flow, constraints `source reference` and `explicit owner` plus mandatory citations yielded a passing score of `1.0` and published seven managed files. A stale selected-proposal state after success was also corrected.
- **Graph and runtime evidence:** the browser relationship graph showed the plugin export, `Knowledge Loop` page, `wiki_cites_source`, `wiki_links_to`, and `proposal_changes_page` relations. A real Agent OS run on the same `knowledge-e2e` project reported `USED`, `4 pages, 1 sources`, `5 governed references`, and a persisted context-pack revision. It registered four D-layer outputs as pending evaluation rather than silently reusing them.
- **Verification:** `python -m pytest tests/knowledge/test_wiki_llm_provider.py tests/knowledge/test_wiki_compiler.py tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_vault.py tests/knowledge/test_wiki_bootstrap.py tests/api/test_knowledge_workspace_api.py -q` passed (`40 passed, 3 skipped`). Focused frontend API/component tests passed (`7 passed`); `npm run check`, `npm run build`, and `git diff --check` passed. The only build note is the existing Vite chunk-size advisory.
- **Scope and remaining boundary:** the integration bridge intentionally handles explicit plugin exports in `raw/` or `inbox/`; it does not execute or inspect arbitrary `.obsidian` plugin code. Applying the same mapping, bridge registration, and review workflow to `D:\bsc` still requires an authenticated action in the user-facing Studio and was not simulated.

## 2026-07-23 - Standard Obsidian Layout And Plugin-Role Correction

- **State:** implementation complete; real project activation remains pending the authenticated Studio action.
- **Problem corrected:** the supplied Obsidian workflow uses `00_Inbox/` and `01_Sources/`, but the bridge only allowed the newer `raw/` and `inbox/` aliases. Its former Claudian and HyperFrames presets also implied that every installed plugin was a source exporter, which would wait forever for a file those plugins do not produce.
- **Changed contracts:** declared `filesystem_drop` paths now accept project-relative `00_Inbox/`, `01_Sources/`, `raw/`, and `inbox/` roots. Sync permits only those A-layer roots inside a mapped project and continues to exclude `wiki/`, skills, review, and `04_Outputs/` from evidence capture. The Studio presets now map Horizon, Web Clipper, social imports, Feishu CLI, Docxer, and Importer to their documented folders; legacy paths remain available.
- **Plugin truthfulness:** Claudian is identified as an Obsidian-to-Codex companion, while Markdown formatter and HyperFrames are output tools. None is displayed as an evidence source merely because it is installed or registered. Only an exported file captured by Sync receives immutable evidence and plugin provenance.
- **Verification:** `./.venv/Scripts/python.exe -m pytest -q tests/knowledge/test_wiki_sync.py tests/api/test_knowledge_workspace_api.py` passed with `15 passed, 1 skipped`; `npm run check` and `git diff --check` passed. The new fixture proves Web Clipper and Docxer exports from the standard folders are captured with plugin identity while a `04_Outputs` document is not re-ingested.
- **Remaining live proof:** authenticate the Studio once, map the intended project-relative folder, select the matching preset for each plugin's configured export directory, and press Sync. The runtime must report captured-source counts before any plugin is considered connected; this has not been fabricated against the user Vault.

## 2026-07-23 - Plugin Layout Runtime Deployment

- **State:** deployed and verified; live Vault adoption remains explicitly unverified.
- **Frontend verification:** `npm run test:frontend` passed with `59 passed`; `npm run build` passed. The only build diagnostic is the existing Vite chunk-size advisory.
- **Runtime verification:** `docker compose -p bsc-growth-e2e up -d --build bsc-backend celery-worker celery-beat` rebuilt and recreated all three services. The API at `http://127.0.0.1:18082/health` returned HTTP 200, API health was `healthy`, PostgreSQL was `healthy`, and Redis returned `PONG`.
- **Deployment scope:** the newly deployed runtime accepts the standard source-export roots and serves the updated plugin presets. This Docker profile continues to use its configured SQLite API database; the separate PostgreSQL service remains healthy, and no migration claim is made.
- **Live boundary:** the open Studio session has no verified runtime access key, so no project Vault was mapped or mutated and no installed plugin was marked captured. The authenticated product workflow, not direct filesystem inspection, is the remaining proof path.

## 2026-07-23 - Obsidian Output Feedback Loop Completion

- **State:** implemented and verified with an isolated project Vault; user-Vault authorization remains deliberately separate.
- **Problem corrected:** the original bridge treated every plugin as a source exporter. This left HyperFrames and Markdown formatter results outside the governed D layer, so the A-to-B-to-C-to-D feedback loop was incomplete. An initial implementation also showed that recording D-layer lineage before the Wiki snapshot could lose the run-to-output edge when the derived graph rebuilt.
- **Changed contracts:** `bsc-plugins.json` now has two explicit adapters. `filesystem_drop` imports evidence only from `00_Inbox/`, `01_Sources/`, `raw/`, or `inbox/`; `filesystem_output` copies only files from a dedicated child of `04_Outputs/` or `outputs/` into immutable project-scoped D-layer storage. Output originals are never moved or modified, receive `registered` status with declared provenance gaps, and cannot re-enter a context pack until the existing evaluator and feedback lifecycle accepts them.
- **Task behavior:** `source_sync` rebuilds the managed Wiki snapshot first, then adopts declared output feedback so the persisted `run -> output` lineage survives the graph refresh. The temporary growth repository borrows, rather than closes, the caller's database backend, preserving existing task injection and recovery behavior.
- **Studio behavior:** presets distinguish evidence imports from output feedback. HyperFrames and Markdown formatter use `filesystem_output`; the bridge table reports pending output counts separately from captured evidence counts. Claudian remains an explicit companion, not a falsely captured file source.
- **Verification:** `./.venv/Scripts/python.exe -m pytest -q tests/knowledge/test_obsidian_output_sync.py tests/knowledge/test_wiki_sync.py tests/api/test_knowledge_workspace_api.py tests/knowledge/test_knowledge_tasks.py` passed with `30 passed, 1 skipped`; `npm run test:frontend` passed with `59 passed`; `npm run check` passed. The task fixture proves one source sync performs output registration, leaves the plugin original unchanged, writes an immutable managed copy, retains `registered` lifecycle state, and persists the run-to-output lineage.
- **Safety gates:** broad `04_Outputs/` and `outputs/` roots are rejected so BSC cannot rescan its own managed D-layer copies. Unlisted output folders and temporary files are ignored. No direct read of `.obsidian`, user credentials, or the real Vault was performed.
- **Runtime deployment:** rebuilt and recreated `bsc-growth-e2e` API, Worker, and Beat from this source state. `http://127.0.0.1:18082/health` returned HTTP 200; API health, PostgreSQL, and Redis were healthy, and Redis returned `PONG`.

## 2026-07-23 - Plugin Output Evidence And Review Closure

- **State:** complete in source and isolated verification; live user-Vault adoption still requires the authenticated Studio workflow.
- **Problem corrected:** external Obsidian plugin exports could be copied into immutable D-layer storage, but they had no way to bind their claims to project A-layer evidence or complete the existing output-evaluation gate. This made a bridge appear connected while its result could not legitimately become reusable knowledge.
- **Changed contracts:** a project writer can attach deduplicated, project-local eligible/processed A-layer source IDs or published page IDs only while a D-layer output is `registered`. The operation appends only `output_used_source`/`output_used_page` lineage; it does not update D registration references or any D registration field, and locks once evaluation begins. Output content hash, Vault path, registration key, plugin original, and registration provenance remain unchanged. Cross-project, generated, untriaged, and post-evaluation evidence links are rejected.
- **Studio behavior:** the Growth inspector now loads eligible A-layer candidates for a pending plugin output, lets an authorized user attach them, exposes five explicit quality dimensions with persisted findings, and then retains the existing feedback and filing gates. A standalone plugin output has no review form until evidence is linked; the UI does not claim groundedness or acceptance from a plugin export alone.
- **Error-boundary correction:** state-transition API wrappers now translate missing resources to structured `404` responses instead of leaking a server exception. This was found by the new cross-project evidence test.
- **Verification:** `./.venv/Scripts/python.exe -m pytest -q tests/api/test_growth_api.py tests/knowledge/test_output_evaluator.py tests/knowledge/test_obsidian_output_sync.py` passed (`22 passed`). The wider knowledge/runtime set passed (`52 passed, 1 skipped`), full frontend tests passed (`62 passed`), `npm run check` and `npm run build` passed, and `git diff --check` passed. The production build continues to report only the existing Vite large-chunk advisory.
- **Runtime deployment:** rebuilt and recreated the `bsc-growth-e2e` API, Worker, and Beat after this source change. The API at `http://127.0.0.1:18082/health` returned `200`, API/PostgreSQL were healthy, Redis returned `PONG`, and deployed OpenAPI exposes `POST /knowledge/projects/{project_id}/outputs/{output_id}/evidence`. The Studio's `/knowledge/growth/...` call is the compatible non-schema alias of this same project-scoped handler.

## 2026-07-23 - Growth Jobs Consume Obsidian Exports And Semantic Context

- **State:** complete in source, isolated end-to-end fixtures, real provider proof, and Docker runtime; no real user Vault was accessed.
- **Problem corrected:** a configured plugin bridge was only used when a separate `source_sync` run occurred. Scheduled `growth_daily` could therefore generate a deterministic record dump before it had captured the plugin's A-layer material or registered its D-layer output. The original dual-track distillation also rendered fixed JSON inventories, leaving accepted external outputs out of the semantic synthesis.
- **Changed contracts:** every growth run now first reads only declared `bsc-plugins.json` exports, captures `filesystem_drop` files as A evidence, records deterministic triage decisions, registers `filesystem_output` files as immutable D outputs, and persists a `knowledge.growth.obsidian_sync.*` event plus source/output/plugin counts in the run result. Untrusted plugin evidence remains `validated` and reviewable; it is not promoted into factual context automatically.
- **Semantic distillation:** the bounded growth context now reads accepted/filed text D copies as `ACCEPTED_STYLE_EXAMPLE_NOT_FACTUAL_EVIDENCE`. A configured non-mock provider receives only the redacted, bounded context and must return the managed daily or weekly document shape. Generated citations are checked against selected A/B IDs; exact `id@revision` echoes are normalized to stable IDs before validation. The new `KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED` setting is deliberately explicit: source/test defaults are `false` for repeatability and cost control, while API/Worker/Beat Docker defaults are `true`. Invalid, disabled, or unavailable provider output records `generation.mode=deterministic` with a reason instead of pretending a model ran.
- **Feedback/lineage correction:** accepted feedback resolves external evidence through the combined registration-and-lineage view. A plugin output can therefore create a reviewable Wiki proposal after a reviewer attached eligible A evidence, while its D registration fields remain byte-for-byte unchanged.
- **Tests first:** added the daily plugin export fixture, provider narrative validation/normalization fixture, and attached-lineage feedback fixture before their production implementations.
- **Verification:** the final focused knowledge/plugin/API/context/runtime/config suite passed `117 passed, 1 skipped`; frontend suite passed `62 passed`; `npm run check`, `npm run build`, `python -m py_compile`, and `git diff --check` passed. The build keeps the pre-existing large-chunk advisory. A full unscoped `pytest -q` run reached its five-minute command ceiling without a failure report and is recorded as a residual test-runtime limitation rather than a pass.
- **Runtime evidence:** rebuilt `bsc-growth-e2e` API, Worker, and Beat after the explicit semantic flag was added. `http://127.0.0.1:18082/health` returned HTTP 200; Redis returned `PONG`; `celery inspect ping` returned one healthy worker. The container reports `KNOWLEDGE_GROWTH_SEMANTIC_DISTILLATION_ENABLED=True`. An isolated container-only A-layer source was distilled through the configured DeepSeek runtime with persisted metadata `generation.mode=llm`, `provider=deepseek`, and `model=deepseek-chat`; no user Vault path, content, or secret was printed.
- **Compatibility and rollback:** no existing Wiki, MCP, Artifact Graph, output registration, or Obsidian plugin contract was renamed. Disabling the existing Obsidian sync flag makes the new preflight visibly unavailable while preserving prior distillation behavior; a missing/invalid model response falls back to the existing deterministic writer with an auditable manifest reason.
- **Live boundary:** the runtime cannot legitimately call the real Vault until Studio has an authenticated project mapping and the project's actual plugin export folders are declared. The first authenticated daily run will expose captured, pending-review, and registered-output counts in its persisted run record rather than claiming connection from configuration alone.

## 2026-07-23 - Knowledge Workspace Growth-Cycle Activation

- **State:** source and browser UI complete; real user-Vault proof remains pending one authenticated Studio session.
- **Problem corrected:** the self-growing loop existed in the worker as `growth_daily` and `growth_weekly_distillation`, but the Knowledge Workspace only exposed direct sync and legacy tasks. A user could not schedule the integrated loop from the Obsidian workspace, and the workspace reported direct-sync status while hiding the last loop's plugin, triage, output, and distillation evidence.
- **Changed contracts:** `GET /knowledge/workspaces/{project_id}` now returns a bounded `growth` summary for the latest daily or weekly loop. It includes only status and numeric A-layer capture, D-layer output-registration, and triage counts; it never returns raw Vault files, model context, or provider payloads. The Studio exposes a `Growth cycle` action, daily `17:00` and Friday `17:30` schedule presets, and an explicit connection-path step that reports the last persisted loop result.
- **Safety:** the cycle captures only manifest-declared plugin folders, leaves untrusted exports validated pending review, and does not auto-publish Wiki pages. Direct `Sync` remains available for a narrow import/registration pass; `Growth cycle` is the complete capture-triage-distillation operation.
- **Tests first:** added an API test that persists a daily growth run and verifies the public bounded summary, plus a frontend test requiring both real growth job options and their expected cadences.
- **Verification:** `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py tests/integration/test_growth_celery.py tests/knowledge/test_obsidian_output_sync.py -q` passed (`19 passed`); `npm run test:frontend` passed (`63 passed`); `npm run check`, `npm run build`, and `git diff --check` passed. The only build note remains the existing large-chunk advisory.
- **Browser evidence:** the running Studio at `http://127.0.0.1:5174/` displayed the new `Growth cycle` action and explicit `No integrated daily or weekly growth run yet` state while unauthenticated. It showed no mock counts or claimed plugin connection.
- **Runtime deployment:** rebuilt and recreated the local `bsc-growth-e2e` API, Worker, Beat, and Redis with this source state. An initial host-port collision with the separate `bsc-backend` project was corrected without stopping that project: this profile now runs on API `18082`, Redis `16379`, and PostgreSQL `15433`. API health returned `200`, Redis returned `PONG`, and `celery inspect ping` returned one online worker.
- **Handoff:** enter the session-only runtime access key in Studio, map the intended project-relative Vault folder, initialize its Wiki, register each actual plugin export preset/path, then run `Growth cycle`. Only a run whose persisted status and counts are visible in Studio constitutes real Obsidian adoption.

## 2026-07-23 - Feishu Operating Standard And Governed Studio Import

- **State:** source implementation and contract verification complete; real user-Vault adoption remains an authenticated Studio action.
- **Reference alignment:** studied authenticated Feishu document revision `644` and codified its A raw material -> B distillation -> C reusable methods -> D real outputs -> review feedback loop in `docs/superpowers/specs/2026-07-23-feishu-abcd-knowledge-growth-standard.md`. The standard preserves the reference workflow's compounding behavior while retaining BSC's evidence, evaluation and publication gates.
- **Problem corrected:** Feishu imports were available as a service and as an optional filesystem bridge, but the Studio had no governed direct route for a user-selected CLI/export payload. That left a critical capture path dependent on manual folder conventions rather than a visible, auditable product action.
- **Changed contracts:** `POST /knowledge/sources/feishu/import` accepts one explicit export under the caller's scoped write authorization. It creates a `feishu_import` run, captures only normalized `feishu_document` or `feishu_minutes` A evidence, persists source ID/type/revision in ordered run events, and returns a raw-content-redacted source view. Credentials are rejected before capture; BSC does not fetch Feishu or retain third-party authentication material.
- **Studio behavior:** Knowledge Workspace now exposes **Import Feishu**. It reads one locally selected JSON export, rejects malformed/oversized payloads before sending, selects the imported evidence after success, and opens the persisted run timeline. Existing `feishu-cli` Obsidian bridge remains available for file-based ingestion.
- **Tests first:** added backend coverage for project scope, document revision provenance, duplicate handling, audit run persistence, response redaction and credential non-persistence; added typed frontend API coverage for scoped export submission.
- **Verification:** focused workspace/API tests passed (`9 passed`); the wider workspace/Feishu/sync/output/task/Celery suite passed (`46 passed, 1 skipped`); full frontend tests passed (`64 passed`); `npm run check`, `npm run build`, and final `git diff --check` passed. The production build retains only the existing large-chunk advisory.
- **Browser evidence:** the running Studio at `http://127.0.0.1:5174/` showed the new **Import Feishu** action and its JSON input. Without a runtime access key, the action was visibly disabled, the workspace declared `Studio access required`, and the desktop document had no horizontal overflow. This is a truthful permission-state check, not an import success claim.
- **Runtime deployment:** rebuilt `bsc-growth-e2e` API, Worker and Beat from this source. A first restart inherited the other profile's occupied `8002` host port and therefore did not start; the profile was immediately recreated on its isolated `18082/16379/15433` ports without stopping the other project. API health returned `200`, deployed OpenAPI exposes `/knowledge/sources/feishu/import`, PostgreSQL is healthy, Redis returned `PONG`, and `celery inspect ping` reported one online worker.
- **Compatibility and rollback:** this is additive to existing Feishu export service and filesystem bridge. Disabling the endpoint/action leaves immutable source/run records intact and does not change Wiki, Artifact Graph, MCP or scheduler semantics.
- **Live boundary:** no real Feishu account, user Vault path, `.obsidian` plugin code or third-party credential was accessed by this change. A real adoption claim requires the Studio to authenticate, the user to select an export, and the resulting `feishu_import` record to be visible in the mapped project.

## 2026-07-23 - Full Obsidian Project Workspace Bootstrap

- **State:** implemented, tested and deployed; user-Vault initialization still requires the authenticated Studio action.
- **Problem corrected:** the previous bootstrap created only `AGENTS.md` plus three Wiki files. It therefore left an almost empty Obsidian project without the A evidence intake, B knowledge structure, C method home, D output paths, review queue or distillation destination promised by the product PRD. It also falsely considered that minimal baseline ready.
- **Changed contracts:** initialization now atomically creates the missing project-relative A/B/C/D layout: documented `00_Inbox/` and `01_Sources/` tool-export roots, compatible `raw/` and `inbox/` roots, Wiki topic directories, `methods/`, `outputs/`, `04_Outputs/`, review/failure/correction paths, `distillations/每周蒸馏/`, attachments, and `.bsc/`. A root `README.md` explains the live workflow without inventing factual content or being registered as B-layer knowledge. Existing user files and binaries remain unchanged.
- **Truthful readiness:** Workspace status now reports a mapped project as incomplete if either required baseline files or any operational directory is absent. Studio names the missing files/folders and offers **Initialize workspace**, which reports file and folder counts after the same governed Vault transaction succeeds.
- **Tests first:** added coverage for complete layout creation, idempotent re-initialization, preservation of user notes, safe empty-directory creation in the atomic Vault transaction, and API readiness transition from an old minimal baseline to the complete layout.
- **Verification:** workspace/bootstrap/Vault/sync/task API suite passed (`37 passed, 1 skipped`); full frontend suite passed (`64 passed`); `npm run check`, `npm run build`, and `git diff --check` passed. The build has only the existing large-chunk advisory.
- **Runtime deployment:** rebuilt and restarted the isolated `bsc-growth-e2e` API, Worker and Beat on `18082/16379/15433`. API health returned `200`, PostgreSQL is healthy, Redis returned `PONG`, and one Celery worker answered ping.
- **Live boundary:** the current Studio session has no runtime access key, so this change has not guessed a Vault mapping or mutated the user Vault. After Studio authentication, mapping the intended project directory and pressing **Initialize workspace** is the audited operation that will materialize this layout.

## Entry Template

## 2026-07-23 - Authenticated Project Activation And Context Evidence Guard

- **State:** complete for the validated activation and context-guard slice; live Horizon/Feishu exports and D-layer plugin outputs remain intentionally pending their real source files.
- **Live activation:** Studio verified the local runtime session as `admin`; project `default` was mapped through the product API to `projects/default` and initialized. The governed initializer created the managed README and 35 project-local operational directories. No direct filesystem inspection or modification of the Vault or `.obsidian` plugin code was used.
- **Declared bridges:** registered `Horizon news capture` as the A-layer `00_Inbox/auto-capture` evidence bridge and `Markdown formatter output feedback` as the D-layer `04_Outputs/articles` bridge. Both correctly remain `awaiting_*` until their declared folders receive actual exports.
- **First governed input:** captured the repository's ABCD knowledge-growth PRD as a user-authorized `manual_upload` source with immutable hash, project-local origin and `eligible` lifecycle status. This is a real source record, not a fixture or a claim that Horizon/Feishu was called.
- **First growth run:** Studio queued `growth_daily`; Celery completed the declared-export sync and produced `distillations/每周蒸馏/2026-W30/每日增量/2026-07-23.md`. The persisted run records zero plugin exports, two untrusted generated baseline sync records pending review, and no registered D outputs. It does not claim a live Horizon/Feishu import.
- **Deviation found:** the 32KB original PRD was eligible but omitted from the 4,000-character distillation context after bootstrap pages consumed the budget. The initial daily artifact therefore recorded deterministic fallback rather than knowledge-backed semantic output. This was treated as a correctness defect, not a successful knowledge-use result.
- **Correction:** added a bounded evidence guard in `GrowthContextBuilder`. When a large eligible source would otherwise be omitted, the context evicts lower-priority rendered material as needed and preserves a redacted head-and-tail excerpt marked `CONTEXT_EXCERPT`, with `excerpted_for_budget` audit metadata. The immutable original remains unchanged.
- **Tests first:** added a regression test for a large eligible source plus bootstrap-page budget pressure. `./.venv/Scripts/python.exe -m pytest -q tests/knowledge/test_growth_context.py` passed: `8 passed`.
- **Runtime verification:** rebuilt and recreated the isolated API, Worker, Beat, Redis and PostgreSQL profile on `18082/16379/15433` without stopping the unrelated service on port `8002`. `/health` and `/ready` returned `ok`; one Celery worker answered `ping`. A second daily run completed with the original PRD source ID in `context.source_ids` and persisted `generation.mode=llm`, `provider=deepseek`, `model=deepseek-chat`. The generation and source consumption are therefore both runtime facts, not unit-test claims.
- **Archive audit:** the supplied Xuan archive was reviewed and documented at `docs/superpowers/research/2026-07-23-xuan-skill-package-architecture-audit.md`. It is a 27-card Markdown prompt library, not an executable Skill package. The report defines its governed A-to-C adoption path and rejects direct template activation.

## 2026-07-23 - Horizon Native Capture Fusion, Wiki Publication, And Scheduled Growth

- **State:** complete for the live `default` project path. Horizon is now an operating A-layer producer in the deployed BSC runtime, rather than a standalone research reference or a UI-only connection card.
- **Runtime cutover:** the preserved SQLite snapshot was copied into the active Compose-owned PostgreSQL `postgres-data-v2` cluster through `scripts/migrate_sqlite_to_postgres.py`. The guarded report is at `.runtime-migration/2026-07-23-horizon-cutover/postgres-v2-apply-report.json`; the original snapshot and prior volume remain rollback material. Row-count verification included 11 sources, 9 Wiki pages, 46 knowledge runs, 275 indexed chunks, citations, graph edges, schedules, and durable run events.
- **Service proof:** the rebuilt API, Worker, Beat, PostgreSQL, and Redis containers are healthy. The API health endpoint returned 200, a Worker answered `ping`, Beat uses `PersistentScheduler`, and an explicit schedule-reconciliation task returned `queued=0`, `duplicates=0`, `failures=0`, `recovered=0` outside a due window.
- **Live Horizon evidence:** native run-store run `run-20260722T233024Z-6c887af5` is recorded as completed for project `default`. It created two immutable, reviewed `horizon_signal` sources, both accepted as eligible: the GigaToken source and the AI-assisted mathematical reasoning source. Workspace status reports `HorizonEnabled=true`, `HorizonCapturedSources=2`, and the completed native run ID without exposing source bodies.
- **Wiki maintenance and quality gate:** real `wiki_maintenance` run `9b66368bd6c4` used the configured DeepSeek provider and created proposal `fa396ec873e5`. The proposal passed lint with no findings. Publication initially stopped because the fresh project had no evaluation baseline; no override was used. Two project-local baseline cases were then created for the two Horizon source IDs and the required GigaToken/Terrence Tao cited concepts. The same proposal passed evaluation with score `1.0` and was published through the normal gate by run `0aa4d440e5ab`.
- **Vault result:** the governed write added `wiki/concepts/simd-optimized-tokenization.md` and `wiki/concepts/ai-assisted-mathematical-reasoning.md`, updated the Wiki ledgers, rebuilt seven searchable Wiki pages, and changed both Horizon sources to `processed`. This is an A-to-B transition with citations and proposal/revision lineage, not a template file drop.
- **Growth result:** live `growth_weekly_distillation` run `bfb0f1705ff3` completed using `generation.mode=llm`, `provider=deepseek`, and `model=deepseek-chat`. It wrote the five managed current-week artifacts plus manifest and immutable revisions beneath `projects/default/distillations/每周蒸馏/2026-W30/`.
- **Persistent cadence:** five enabled schedules now use `Asia/Shanghai`: `source_sync` daily 17:00, `horizon_capture` daily 17:05, `wiki_maintenance` daily 17:15, `growth_daily` daily 17:25, and `growth_weekly_distillation` Friday 17:40. The next executions are persisted in PostgreSQL and are reconciled by Celery Beat every minute.
- **Boundary and rollback:** the Horizon filesystem plugin bridge correctly remains `awaiting_export` because this live integration reads Horizon's native run-store rather than pretending that an unrelated folder export occurred. Disable the five schedules first to pause future work; published Wiki pages can be restored by the existing revision proposal flow, and neither immutable source records nor the original SQLite snapshot are deleted.

## 2026-07-23 - Installed Obsidian Plugin Bridge Activation And Verification

- **State:** complete for BSC-side plugin bridge activation; awaiting the first real export from each user-operated Obsidian plugin.
- **Installed-plugin mapping:** after confirming the enabled Vault plugins, the authenticated `default` project manifest was atomically updated through `PUT /knowledge/workspaces/default/plugins`. It preserves the existing Horizon A-layer and Markdown output D-layer bridges, and adds `obsidian-clipper -> 00_Inbox/web-clipper`, `xiaohongshu-importer -> 00_Inbox/social`, `docxer -> 01_Sources/docxer`, and `obsidian-importer -> 01_Sources/importer`.
- **Claudian boundary:** Claudian is a Vault-local coding collaborator, not an evidence exporter. It remains subject to `AGENTS.md`, the project directory boundary, proposal review, citations, and the B/C/D lifecycle; it is deliberately not registered as an A-layer source that could bypass provenance.
- **Runtime evidence:** the live Workspace readback reports the mapped `projects/default` Vault as `ready` and all four newly registered A-layer bridges as `awaiting_export`, rather than claiming connection from installation alone. Manual source-sync run `d7e2e6a747d6` completed through queued, running, Wiki-snapshot, source-sync, and completed events. It scanned only the declared capture surface, produced no new source and no output registration, and indexed seven existing Wiki pages without failures.
- **Configuration boundary:** no third-party `.obsidian` plugin code or settings was executed, edited, or inferred. The Xiaohongshu plugin currently declares its own `XHS Notes` default folder outside the mapped project boundary, so its plugin-side save location must be changed through its own Obsidian settings to `projects/default/00_Inbox/social` before BSC can legitimately capture its next export. The other bridges likewise become captured only after their plugins write a real file into their declared project folder.
- **Rollback:** replacing `bsc-plugins.json` through the same authenticated endpoint with the prior two-entry manifest removes the four new bridges without changing sources, outputs, Wiki pages, schedules, or plugin-owned settings.

### `<date/time> - <plan/task>`

- **State:** in progress / complete / blocked
- **Changed files:**
- **Contracts:**
- **Tests first:**
- **Verification commands and results:**
- **Runtime evidence:**
- **Compatibility:**
- **Deviations/risks:**
- **Rollback exercised:**
- **Handoff:**
