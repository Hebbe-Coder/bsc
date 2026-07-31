# Knowledge Operations Visualization Worklog

## Scope

Plan and implement the tenant-safe Knowledge Operations Visualization System:
organization portfolio, project cockpit, operations metrics, deterministic
action queue, semantic lifecycle graph, REST/MCP read model and responsive
Studio interface.

## Progress

| Time | Item | State | Evidence / deviation |
| --- | --- | --- | --- |
| 2026-07-27 | Baseline audit | Complete | Read existing DBOS PRD/control center, A/B/C/D growth PRD/workspace, ArtifactGraphStore, Knowledge/Growth APIs, repository schema and Studio screenshot. Current visual gap is operational meaning, not merely chart library availability. |
| 2026-07-27 | Product scope decision | Complete | Phase 1 is dual-scope: tenant-admin portfolio plus project cockpit. Generic BI remains Phase 2. |
| 2026-07-27 | PRD, index and plan split | Complete | Added this worklog, one PRD, one dependency index and six executable bounded plans. No production code was changed by this documentation task. |
| 2026-07-27 | P1 Foundations | Complete | Added tenant ownership/backfill, tenant-scoped project lookup and metadata-only operations contracts. Verified project tenant isolation and direct repository migration. |
| 2026-07-27 | P2 Aggregation and actions | Complete | Added read-only `KnowledgeOperationsService`: tenant-scoped portfolio aggregation, real A/B/C/D and DBOS metrics, no-sample states, durable reuse counts and deterministic action queue. 15 focused P1/P2 tests pass. |
| 2026-07-27 | P3 Lifecycle graph | Complete | Added a bounded, read-only Artifact/Wiki/Growth lifecycle projection with lane semantics, scope filtering, redacted labels, relationship filters and cursor metadata. Graph storage was not merged with Artifact Graph or Growth storage. |
| 2026-07-27 | P4 REST and MCP | Complete | Added tenant-authorized portfolio/project/graph REST read models, client contracts, MCP tools and HTTP MCP catalog entries. The transport exposes metadata and references only; raw source bodies, prompts and provider payloads remain excluded. |
| 2026-07-27 | P5 Cockpit UI | Complete | `Operate` now opens the Knowledge Operations cockpit and retains DBOS in `Mission`. Portfolio/project scopes, server-authorized project health summaries, deterministic action drill-downs, ECharts evidence trends, React Flow lifecycle inspection, unavailable states and responsive layouts are implemented against the read model. |
| 2026-07-27 | P6 acceptance audit | Complete | The earlier P6 entry was premature. The audit found and remediated the missing comparable project decision view and imprecise action handoff, then reran browser and regression evidence. These were FR-1/FR-3 gaps, not cosmetic defects. |
| 2026-07-27 | Audit remediation | Complete | Added typed, tenant-authorized `project_summaries` with real freshness, coverage, asset/quality/risk/reuse metrics and highest-priority action. The client does not enumerate projects. The cockpit now shows project health and direct project entry. |
| 2026-07-27 | Exact action handoff | Complete | Actions now expose persisted source refs, project scope and current role with a truthful read-only explanation. Pending proposals open their exact Growth review record; mission-bound DBOS artifacts open the exact DBOS focus inspector; unbound DBOS records remain in the project lifecycle inspector so no arbitrary mission is implied. Knowledge Workspace accepts a one-shot exact target for source/proposal/run/page selection after its server snapshot loads. |
| 2026-07-27 | P6 browser revalidation | Complete | Real desktop Studio revalidated portfolio health, project cockpit, 3 nonblank ECharts panels, persisted risk selection and pending-proposal review selection. A fresh `390x844` mobile pass revalidated the project health entry, graph and exact risk drill-down with no horizontal overflow. |
| 2026-07-27 | Open-project risk action remediation | Complete | Selecting an unbound DBOS risk while already in the same project cockpit now reloads the bounded graph and selects the exact persisted node. Added a focused UI regression test and revalidated the behavior in the mobile Studio. |
| 2026-07-27 | P6 final runtime audit | Complete | Re-ran affected backend/frontend suites, the full Growth API suite, type/build gates, container runtime acceptance and real Compose HTTP/MCP probes. API, PostgreSQL, Redis, Worker and Beat are healthy; portfolio/project/graph return authorized data and an unknown project returns `403`. |
| 2026-07-27 | Project-key tenant propagation remediation | Complete and deployed | Project principals derive their durable project tenant for REST request scope; MCP project/graph calls pass that tenant to the bounded projection. API container hashes match the workspace for the changed API, MCP, auth and lifecycle modules, and the container has no application-source bind mount. |
| 2026-07-27 | Plan execution-contract audit | Complete | Corrected P1's stale nonexistent authorization-test path to current tenant and REST coverage. Added P6's copyable focused regression/build/Compose commands; this changes planning evidence only, not runtime behavior or release status. |
| 2026-07-27 | Final P6 evidence refresh | Complete | Fresh Playwright journeys at `1280x720` and `390x844` rendered three ECharts panels and the React Flow projection with no horizontal overflow. The mobile lifecycle filter drawer opened as an accessible dialog. The live project truthfully reports `0/13` complete risk lineages because durable validation and feedback are absent. |
| 2026-07-27 | Agent-evolution sample integrity | Complete | Fixed the misleading single-run success-rate path. Verification, execution-attempt and Holdout rates now require at least three persisted observations globally and in each rendered time bucket. Under-sampled values retain their real count, return `insufficient_sample`/`null`, and the UI renders an explicit empty state instead of a success line. |
| 2026-07-27 | Project-key REST boundary | Complete | Added an HTTP-through-middleware integration test proving a project reader can read only its bound project and receives `403` for portfolio enumeration, a second same-tenant project and a cross-tenant graph. |
| 2026-07-27 | Final runtime usability audit | Complete | Rebuilt API, Worker and Beat images; confirmed source hashes in the running API. Real Studio validated risk-to-lifecycle selection, pending-proposal-to-Growth review handoff, nonblank ECharts pixels, React Flow nodes, filters and no desktop/mobile horizontal overflow. |

## Baseline Findings

- `KnowledgeWorkspace` already loads actual sources, proposals, runs, health,
  trend and knowledge graph data, but currently presents fragmented technical
  indicators and multiple small charts.
- `BusinessControlCenter` has mission-level reasoning, execution, verification,
  risk, evidence and memory data, but its graph is mission-scoped and uses a
  simple grid layout.
- `GrowthLineageGraph` already has a useful source/page/method/candidate/output/
  feedback lane model. It is a visual reference only; the new lifecycle graph
  must not merge it with Artifact Graph storage.
- `knowledge_projects` currently lacks tenant ownership. Portfolio aggregation
  is therefore blocked on P1 migration and authorization work.

## Verification Log

| Command | Result | Notes |
| --- | --- | --- |
| Static repository/API/UI inspection | passed | Confirmed authoritative data sources, existing scopes and visualization limitations without modifying runtime data. |
| Browser inspection of local Studio | passed | Current root is a technical execution workspace. It does not yet provide organization-level asset value, action priority or explainable lifecycle operations. |
| Documentation file existence/readback and `git diff --check` | passed | Confirmed all one PRD, one index, six subplans and this worklog exist; dependency order and file references resolve. |
| `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_contracts.py tests/knowledge/test_operations_schema.py tests/knowledge/test_operations_service.py tests/knowledge/test_operations_actions.py tests/knowledge/test_repo_production.py tests/knowledge/test_project_auth_api.py -q` | passed | 15 passed. Covered tenant filtering, DBOS-unavailable/no-sample states, source-content redaction, metric calculation and action ordering. |
| `npm run build` | passed | Final production TypeScript and Vite build completed. The bundler reported existing large-chunk guidance only. |
| `npm run lint` | passed with warnings | ESLint returned zero errors and 202 existing repository warnings. The operations cockpit and its tests were separately linted with zero warnings. No warning is treated as an acceptance result. |
| `npm run check` | passed | TypeScript project check completed with no errors. |
| `npm run test:frontend -- --run src/api/knowledgeOperationsApi.test.ts src/components/operations/KnowledgeOperationsCockpit.test.tsx` | passed | 2 files and 3 focused client/cockpit tests passed. |
| `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_contracts.py tests/knowledge/test_operations_schema.py tests/knowledge/test_operations_service.py tests/knowledge/test_operations_actions.py tests/knowledge/test_operations_graph.py tests/api/test_knowledge_operations_api.py tests/mcp/test_knowledge_operations_tools.py tests/test_artifact_scope.py tests/api/test_dbos_api.py tests/api/test_growth_api.py tests/api/test_knowledge_workspace_api.py -q` | passed | 60 passed. Verified operations contracts, aggregation, actions, lifecycle graph, REST/MCP authorization and affected DBOS/Growth/Workspace behavior. |
| `git diff --check` | passed | No whitespace errors in the current dirty worktree. |
| `npx eslint src/components/operations/KnowledgeOperationsCockpit.tsx src/components/operations/KnowledgeOperationsCockpit.test.tsx` | passed | The changed cockpit component and focused tests have zero ESLint warnings or errors. |
| Local proxy check | passed | Updated the local Vite proxy target from stale `8002` to `8010` and referenced the already-configured local API key only in Vite server configuration. `GET /knowledge/operations/portfolio` through `5180` returned `200`, `success=true`, `state=available` and one authorized project. No credential was exposed to `import.meta.env` or the browser. |
| Desktop browser: portfolio and cockpit | passed | Real persisted portfolio data rendered one authorized project, verified/pending/risk/reuse metrics, three nonblank ECharts panels and a 14-item deterministic action queue. No document or cockpit horizontal overflow at `1280x720`. |
| Desktop browser: lifecycle graph | passed | Project view rendered 124 raw scoped nodes and 222 scoped edges as five readable semantic lane summaries with six relationship-count chips. The raw graph no longer attempts to fit every record into unreadable cards; lane records remain inspectable in a paged list. |
| Desktop browser: interaction and keyboard | passed | Clicking a lane and selecting a real mission record showed its redacted status/domain/confidence inspector. `Enter` on the Business problem lane switched the inspector from 47 Evidence records to 7 Business problem records. |
| Mobile browser viewport | blocked | The in-app browser viewport capability accepted a `390x844` request but continued reporting `1280x720` after reload. The override was reset. Responsive CSS and desktop overflow checks pass, but this is not a substitute for a real mobile browser screenshot and interaction test. |
| `npm run test:frontend -- --run src/components/operations/KnowledgeOperationsCockpit.test.tsx src/api/knowledgeOperationsApi.test.ts` | passed | 4 focused tests passed. They cover bounded client query serialization, mission-filter propagation to the server, and persisted adjacent-record traversal in the inspector. |
| Live Studio desktop at `1280x720` | passed | The authorized `default` project rendered real decision metrics, three nonblank ECharts panels, 14 deterministic actions, 124 scoped nodes and 222 scoped edges. Selecting a short-identified risk opened its persisted parent diagnosis; the diagnosis inspector exposed connected mission, assumptions, methods, runtime context and routing evaluation records. |
| Live Studio mobile at `390x844` | passed | `window.innerWidth=390`, document client width/scroll width were `384/384` with no horizontal overflow. The `Filters` control opened an accessible dialog containing mission, node type, status and relation controls. Selecting `Risk` changed the real bounded graph to 7 nodes and 0 retained edges; returning to all types restored the full graph. |
| Live governed proposal lint | passed | `POST /knowledge/proposals/d15e77b0f551/lint?project_id=default` through the local authenticated proxy returned `200`, `success=true`, `valid=true`, zero findings. This endpoint requires write authorization but does not publish/reject or alter the user's knowledge content. |
| Live tenant boundary probe | passed | An operations request for an unbound project ID returned `403` without revealing project existence. Dual-tenant and publish/reject behavior remain covered by isolated API/command tests. |
| `npm run build` and `npm run check` | passed | Production Vite build and TypeScript project check completed. Vite reported the repository's existing large-chunk guidance only. |
| Operations/P6 regression suite | passed | 44 tests passed across operations contracts/schema/service/actions/graph, REST/MCP policy, proposal gate and knowledge workspace API. The suite executes publish/reject behavior against isolated temporary stores. |
| Focused cockpit lint and diff check | passed | ESLint for the cockpit and its tests reported zero warnings/errors; `git diff --check` reported no whitespace errors. |
| `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_contracts.py tests/knowledge/test_operations_schema.py tests/knowledge/test_operations_service.py tests/knowledge/test_operations_actions.py tests/knowledge/test_operations_graph.py tests/api/test_knowledge_operations_api.py tests/mcp/test_knowledge_operations_tools.py tests/test_artifact_scope.py tests/api/test_dbos_api.py tests/api/test_growth_api.py tests/api/test_knowledge_workspace_api.py -q` | passed | 63 passed. Added tenant-authorized project summary, metadata-only freshness contract, no cross-tenant portfolio enumeration and action priority coverage. |
| `npm run test:frontend -- --run src/components/operations/KnowledgeOperationsCockpit.test.tsx src/store/knowledgeWorkspaceStore.test.ts src/components/dbos/BusinessControlCenter.test.tsx` | passed | 27 passed. Covers project health entry, action source/scope text, Growth proposal ID handoff, unbound DBOS lifecycle focus, project-safe Knowledge target clearing and DBOS artifact focus. |
| `npm run check` and `npm run build` | passed | TypeScript check and production Vite build passed after the remediation. Vite still reports repository-level large-chunk guidance only. |
| Focused changed-file ESLint | passed | Zero warnings/errors for the changed operations, knowledge target, DBOS focus and API contract files. |
| Live Studio desktop: portfolio -> project -> risk | passed | At `127.0.0.1:5180`, one authorized project showed real project health (`129` assets, `16` verified, `35` risk debt, `7` reuse), three nonblank charts and scoped actions. Opening the project showed the persisted risk `art_85b...` in the lifecycle inspector with its diagnosis connection; no unrelated DBOS mission was opened. |
| Live Studio desktop: action -> Growth review | passed | The real pending proposal `47c674d6c342a1b672287820` opened its selected Growth review record and inspector, including persisted project ID, proposal ID and `review` stage. |
| `npm run test:frontend -- --run src/components/operations/KnowledgeOperationsCockpit.test.tsx` | passed | 5 focused tests passed, including an unbound DBOS action selected while its project cockpit is already open. |
| Focused cockpit ESLint | passed | The cockpit component and focused test reported zero warnings or errors after the action-reload remediation. |
| Live Studio mobile P6 final pass at `390x844` | passed | Portfolio-to-project entry rendered 3 nonblank charts with document width `384/384`. Selecting real action `artifact:art_85b193991155` while the project cockpit was open selected the exact risk and showed its persisted Diagnosis connection. |
| `npm run check`, `npm run build`, `git diff --check` | passed | Final TypeScript and production build passed after the remediation; `git diff --check` found no whitespace errors. Vite emitted only existing large-chunk guidance. |
| P6 affected backend regression suite | passed | 63 tests passed across operations contracts/schema/service/actions/graph, REST/MCP authorization, Artifact Graph scope, DBOS, Growth and Knowledge Workspace APIs. The only warning is FastAPI TestClient's upstream `httpx` deprecation notice. |
| P6 affected frontend regression suite | passed | 30 tests passed across operations API/cockpit, Knowledge Workspace target handoff and Business Control Center exact-artifact focus. |
| `docker compose config --quiet` and runtime status | passed | Compose configuration parsed. API, PostgreSQL, Redis, Celery Worker and Beat were running; API health reported a PostgreSQL connection. Knowledge Wiki, Growth and schedules were enabled in the API container. |
| Compose operations REST/MCP read-only probe | passed | Authenticated portfolio, project and bounded graph requests returned available state; MCP listed and executed all three operations read tools. The probe printed only states/counts, not credentials or source bodies. An unknown project returned `403`. |
| Live Studio desktop P6 re-audit | passed | The risk action selected its exact durable risk, then its exact persisted Diagnosis. The Diagnosis inspector exposed its Mission, Assumption, capability, runtime-context and routing-evaluation connections. Keyboard activation selected the Business problem lane; a Risk filter reduced the real graph from 127 to 7 records and reset cleanly. |
| Live Studio mobile P6 final re-audit at `390x844` | passed | Portfolio health opened the project cockpit; 3 ECharts panels and the React Flow projection rendered. The Filters drawer opened as an accessible dialog, Risk filtering produced 7 real nodes, and `clientWidth`/`scrollWidth` remained `384/384` before and after restoring the full 127-node projection. |
| Project-key tenant propagation regression | passed | 13 tests passed across auth resolution, MCP operations delegation, growth authorization and operations REST. A project key now receives the tenant bound to its project; MCP project and graph calls receive the same tenant. |
| Final affected regression after tenant remediation | passed | 73 backend tests, 30 frontend tests and TypeScript checking passed. Python `compileall` passed for the changed auth/MCP modules. |
| Runtime image verification after tenant remediation | passed | The running API image contains byte-identical current copies of the changed operations API, MCP adapter/server, auth middleware and lifecycle graph modules. Docker inspection confirmed no application-source bind mount; only data, output, Vault and Horizon run mounts are present. |
| `./.venv/Scripts/python.exe -m pytest` (P6 affected suite excluding Growth API) | passed | 46 passed in 50.05s across operations contracts/schema/service/actions/graph, auth resolution, REST/MCP, Artifact Graph, DBOS and Knowledge Workspace APIs. |
| `./.venv/Scripts/python.exe -m pytest tests/api/test_growth_api.py -q` | passed | 23 passed in 196.08s. Earlier 74s/184s command windows were insufficient because the isolated API fixture incurs several seconds per real request; no test deadlock was found. |
| `npm run test:frontend -- --run src/api/knowledgeOperationsApi.test.ts src/components/operations/KnowledgeOperationsCockpit.test.tsx src/store/knowledgeWorkspaceStore.test.ts src/components/dbos/BusinessControlCenter.test.tsx` | passed | 32 passed across client query contracts, cockpit operations, exact Knowledge/Growth handoffs and DBOS artifact focus. |
| `npm run check`, `npm run build`, `git diff --check`, `docker compose config --quiet` | passed | TypeScript checking, production build, whitespace gate and Compose configuration all passed. Vite emitted only its existing large-chunk guidance. |
| `docker compose exec -T bsc-backend python scripts/verify_knowledge_operations_runtime.py` | passed | Isolated persisted A/B/C/D plus DBOS chain passed with `13` nodes, `17` edges and `1` complete risk lineage; it does not write user knowledge or call external providers. |
| Live Compose HTTP/MCP probe | passed | Authenticated portfolio/project/graph returned `200`; the graph contained `133` nodes and `273` edges. Unknown project returned `403`. `tools/list` exposed the three read-only operations tools and `knowledge_operations_project` completed successfully. No credentials or source bodies were printed. |
| Fresh Playwright desktop/mobile evidence | passed | `1280x720` and `390x844` journeys rendered three chart containers and the React Flow projection. Both had `scrollWidth == clientWidth`; the mobile lifecycle filter dialog was visible. Screenshots: `artifacts/knowledge-operations-desktop-graph-final.png`, `artifacts/knowledge-operations-mobile-graph-final.png`, `artifacts/knowledge-operations-mobile-filters-final.png`. |
| Agent-evolution sample gate regressions | passed | 4 service tests and 10 focused cockpit/API tests prove values below three samples are `insufficient_sample`, daily trend rates stay `null`, and the UI does not draw a blank/single-sample success chart. Three persisted samples still calculate the expected rate and median. |
| Project-key REST authorization regression | passed | 8 tests across operations REST, auth resolution and MCP. A project reader cannot enumerate the portfolio or access either another same-tenant project or a cross-tenant graph. |
| Final P6 backend regression | passed | 60 tests across operations contracts/schema/service/actions/graph, auth, REST/MCP, Artifact Graph, DBOS, Knowledge Workspace and governed proposal gates. Proposal publish/reject assertions use isolated test stores and Vaults only. |
| Final P6 frontend/build regression | passed | 33 frontend tests, `npm run check` and `npm run build` passed. Vite emitted only existing large-chunk guidance. |
| Final Growth API regression | passed | 23 tests passed in 197.04s. The duration is caused by real isolated FastAPI request coverage, not a hang. |
| Final Compose runtime acceptance | passed | API, PostgreSQL, Redis, Worker and Beat are healthy after rebuild. The container acceptance harness passed `13` nodes, `17` edges and `1` complete risk lineage; the runtime image source hashes match the workspace. |
| Final Compose REST/MCP probe | passed | Portfolio/project/graph each returned `200`; the observed graph had `135` nodes and `280` edges. Unknown project returned `403`. MCP exposed and executed the three read-only operations tools, with no raw source or provider payload in the graph response. |
| Final browser interaction and pixel audit | passed | Real risk action selected durable `art_85b1...` in the project graph; the pending proposal loaded its exact Growth review record. Desktop ECharts canvases had 9,050/14,728/7,308 visible pixels. Mobile canvases had 7,191/11,750/4,095 visible pixels and five React Flow nodes within a `390px` viewport. Screenshots: `artifacts/knowledge-operations-final-desktop-charts.png`, `artifacts/knowledge-operations-final-mobile-graph.png`, `artifacts/knowledge-operations-action-handoff-final.png`. |

## Boundaries And Risks

- The working tree already contains many unrelated modified/untracked files.
  This initiative must stage or commit only its own files when a later explicit
  commit is requested.
- Portfolio data may never be calculated client-side by iterating arbitrary
  project IDs; P1 must establish tenant-scoped server authorization first.
- No code path may call a generated result, pending run or unverified output a
  verified knowledge asset.
- Live external provider, Horizon and Obsidian outcomes remain unavailable
  unless their existing durable run records prove execution.
- P2 does not claim that any knowledge is valuable. It exposes only persisted
  publication, verification, reuse and review facts; value remains a business
  decision backed by those records.
- Real user data can change while the local scheduler or capture pipeline is
  running. Counts in the cockpit are therefore observed facts at render time,
  not release fixtures or stable business-value claims.
- Live proposal publication/rejection was intentionally not run against the
  user's Vault during validation. The verified lint action exercises the
  authorized governed route without changing knowledge; publish/reject remain
  covered in isolated temporary-database tests.
- P6 now has desktop and fresh mobile browser evidence for the project-health
  entry and exact action handoff. The remaining external-provider outcomes are
  intentionally not claimed without durable run records.
- The default project's live lifecycle audit currently reports no complete
  risk lineages. The exact missing lanes can change as real records arrive;
  this is operational evidence of incomplete follow-through, not a
  release-fixture failure. The cockpit exposes the gap instead of
  manufacturing completion.

## 2026-07-29 Docker Data And Responsive Reacceptance

- Revalidated the portfolio through the Vite proxy after converging the Studio
  on the Docker API. The server-authorized payload reported 2 authorized
  projects, 172 durable records, and 31 evidence-ranked actions. No portfolio
  total was recomputed in the browser.
- Browser acceptance at 390x844 confirmed the portfolio cockpit, metrics,
  project cards, charts, and action queue render without horizontal overflow.
  The mobile title hierarchy was corrected in `src/index.css`: the category
  label and `Decision cockpit` heading now stack vertically rather than being
  compressed into one line. This changes presentation only; data and access
  semantics are unchanged.
- Verification: `npm run test:frontend --
  src/components/operations/KnowledgeOperationsCockpit.test.tsx` passed 8
  tests and `npm run check` passed. Browser checks observed no console errors.

## 2026-07-31 Growth Health Visualization Semantics Correction

- A live, server-authorized Growth workspace read exposed a misleading metric:
  the project had `177` evidence records, `11` Wiki pages, `1` method and
  `11` outputs, but the UI rendered the final inventory ratio as a `C to D`
  conversion of `1100%`. Outputs can be independently grounded and one method
  can be reused, so this ratio is neither a lifecycle conversion nor a measure
  of method impact.
- Replaced the funnel with a horizontal A/B/C/D inventory chart and changed
  the summary to only three source-backed coverage facts: evidence admitted,
  methods published, and outputs verified. The view now labels itself as
  persisted inventory and coverage rather than a conversion snapshot. It does
  not infer method use, business value, or a causal rate from layer counts.
- Regression coverage verifies real bounded ratios and rejects the old `200%`
  presentation. `npm run test:frontend -- --run
  src/components/growth/GrowthVisualizations.test.tsx
  src/components/growth/GrowthWorkspace.test.tsx` passed with `38` tests;
  `npm run check` and `npm run build` passed.
- The Compose API, Worker and Beat were rebuilt after the frontend change.
  API readiness returned `200`, Celery returned `pong`, and PostgreSQL, Redis
  and n8n remained healthy. A post-change browser reload was blocked by the
  local browser URL policy, so it is deliberately not recorded as a fresh
  visual acceptance pass. The pre-change authorized read is recorded only as
  the defect observation; a new desktop/mobile visual pass remains required
  when the browser connection is available.
