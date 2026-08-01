# Studio Project Context Acceptance

Date: 2026-07-31
Scope: keep the selected Knowledge project aligned across the Studio shell and lazy-loaded workspaces.

## Implementation

- Added an explicit `syncKnowledgeProjectContext` bridge beside the existing Growth bridge.
- `UnifiedWorkspace` now owns the Studio-level project selection and synchronizes it into the Knowledge store before opening a lazy workspace.
- `KnowledgeWorkspace` accepts `activeProjectId` and reports project changes back to the Studio shell, so an in-workspace switch updates the shared context.
- Operations deep links use the same activation path for Knowledge, Growth, and Mission destinations.
- Added regression coverage for selecting, switching, and explicitly clearing the shared Knowledge project without falling back to `default`.
- Fixed the top-header `Growth` transition: it now closes an open Knowledge workspace before mounting Growth, so the selected project is visible in the intended workspace rather than hidden beneath the prior overlay.
- Added an interaction regression that selects a project in Knowledge, opens Growth, and asserts both Growth visibility and preservation of `proj_b8a285642094` in the Growth store.
- Centralized top-level workspace transitions for Knowledge, Growth, Operations, PBOS and Mission. A transition now unmounts every other full-screen workspace before opening its destination; Operations drill-downs reuse that same path.
- Corrected the Operations-to-Growth ordering: project activation completes before the Review stage, record selection and center view are applied, preserving action-queue drill-down context.
- Corrected Mission request ownership: a business run passes its intake request explicitly, while a later header Mission or Operations deep link opens a blank governed mission and cannot repeat a stale auto-start request.

## Automated Verification

- `npm run test:frontend -- src/components/UnifiedWorkspace.test.ts src/components/KnowledgeWorkspace.test.tsx src/store/knowledgeWorkspaceStore.test.ts`
  - 3 files passed, 30 tests passed.
- `npm run build`
  - TypeScript and Vite production build passed.
  - Existing ECharts chunk-size warning remains visible; it is not treated as a hidden pass.
- `git diff --check -- src/components/UnifiedWorkspace.tsx src/components/UnifiedWorkspace.test.ts src/components/KnowledgeWorkspace.tsx`
  - Passed.
- An earlier concurrent PBOS type mismatch was recorded during this worklog's initial acceptance. It is not reproduced in the current shared worktree; no PBOS files were changed by this navigation increment.
- `npx vitest run src/components/UnifiedWorkspace.test.ts`
  - First ran red: Growth mounted while the Knowledge dialog remained present, reproducing the overlay-routing defect.
  - After the focused handler change: 1 file passed, 10 tests passed.
- `npm run check`
  - Passed against the current shared worktree after the navigation regression fix.
- `npm run test:frontend`
  - 23 test files passed, 190 tests passed.
- `npm run build`
  - TypeScript and Vite production build passed. The existing ECharts vendor chunk remains above the 500 kB advisory threshold; this is recorded as a performance follow-up, not a test failure.
- `npx vitest run src/components/UnifiedWorkspace.test.ts`
  - First ran red with 3 failures: Operate, PBOS and Mission mounted while the Knowledge dialog remained open.
  - After the unified transition: 14 tests passed, including the Operations-to-Growth Review target assertion.
  - A second red test reproduced stale Mission auto-start input after closing and reopening Mission. After explicit request ownership: 15 tests passed.
- Current full frontend validation: `npm run test:frontend` -> 23 files passed, 195 tests passed; `npm run check`, `npm run build`, and `git diff --check` passed.

## Live Browser Verification

Browser target: local Studio at `http://127.0.0.1:5174/`.

- Selected `proj_b8a285642094` in the Studio root and preserved an unsubmitted mission draft while opening Knowledge.
- Knowledge loaded the same project without a second project selection. Live state showed a connected Vault, 5/5 verified plugin routes, 9 immutable Horizon signals, 5 published Wiki pages, 28 evidence records, 36 relations, and 100% citation coverage.
- Growth loaded `proj_b8a285642094` and displayed its persisted A/B/C/D inventory, 9 Horizon signals, completed automation state, and weekly distillation.
- PBOS loaded the same project and displayed connected Vault context and governed evidence state.
- Mission loaded `DBOS project ID: proj_b8a285642094`, 8 selected capabilities, and persisted diagnosis/evidence gaps. It correctly remained unexecuted rather than claiming runtime success.
- At a temporary `390x844` viewport, Knowledge loaded successfully with `documentElement.scrollWidth === clientWidth` (`384px` each), so no document-level horizontal overflow was observed.
- Browser application error and warning logs were empty. A non-application telemetry network timeout was not recorded as a Studio error.

## Boundary And Remaining Risk

- This increment proves project-context continuity and does not claim that external Obsidian plugin exports, user business outcomes, PBOS accepted outcomes, or third-party credentials exist.
- The automated navigation verification did not read Vault note bodies, source bodies, or original files; it did not call external services and did not write to the Vault.
- A later local-browser loading check was stopped immediately because its broad accessibility snapshot expanded visible published Wiki text. It is not counted as a browser-acceptance result for this increment. Future browser checks under the no-body boundary must use a dedicated redacted fixture or bounded metadata-only selectors.
- The browser viewport override was reset after responsive verification.

## Knowledge Operations Metric Drill-down

Date: 2026-07-31
Scope: replace static Knowledge Operations decision metrics with authorized, metadata-only contributor drill-downs.

### Boundary

- No Vault, Obsidian, source, Wiki, or output body was read.
- No external service or browser session was used.
- No original user file was written. Tests use isolated temporary databases and frontend fixtures only.
- Contributor contracts allow only record ID, project ID, kind, status, timestamp, bounded system reason, and an existing governed drill-down target. They exclude title, raw content, body, URL content, and citation text.

### Test-First Evidence

- API regression first ran red: `GET /knowledge/operations/portfolio/metrics/qualified_total` and the project equivalent returned `404` because the routes did not exist.
- Frontend regression first ran red: the `Governed assets` metric was a static article and no `Inspect contributors for Governed assets` control existed.
- The implemented service derives contributor totals from the same authorized project snapshots as the overview metric. It supports `qualified_total`, `pending_validation`, `requires_attention`, `durable_references`, and `open_actions` with a bounded `1..100` result limit.
- Portfolio requests retain tenant-administrator requirements; project requests reuse the existing project access enforcement. Unsupported metric keys return a truthful `422` with `operations_invalid_metric`.
- The cockpit now exposes all five decision metrics as keyboard-accessible controls. The contributor panel has loading, empty, unavailable/error, retry, close, and truncated-result states. Selecting a contributor reuses the existing Knowledge, Growth, or DBOS navigation path.

### Automated Verification

- `python -m pytest tests/api/test_knowledge_operations_api.py tests/knowledge/test_operations_service.py -q`
  - 7 tests passed. Coverage includes tenant/project isolation, contributor count equality, truncation, invalid metric handling, and raw-content redaction.
- `npm run test:frontend -- --run src/components/operations/KnowledgeOperationsCockpit.test.tsx`
  - 11 tests passed. Coverage includes the metric request, metadata-only contributor rendering, and governed Knowledge navigation.
- `npm run check`
  - Passed.
- `npm run test:frontend`
  - 23 test files passed, 197 tests passed.
- `npm run build`
  - TypeScript and Vite production build passed. The existing ECharts vendor chunk remains above the 500 kB advisory threshold and is still a performance follow-up.
- `git diff --check -- <scoped knowledge operations files>`
  - Passed. Git reported only repository line-ending normalization warnings.
- Full backend suite attempt: `python -m pytest -q`
  - Not counted as a pass. The command exceeded the 120-second execution window and pytest then raised `OSError: [Errno 22]` while flushing terminal progress output, so no trustworthy suite summary was produced. The scoped 7-test backend regression above remains the accepted verification for this increment; full-suite health is a separate follow-up.

## Governed Manual Information Ingress Receipt Proof

Date: 2026-07-31
Scope: make the Studio's explicit n8n source-check command report completion
only after BSC has persisted matching project-scoped receipts.

### Boundary

- No n8n webhook, RSS feed, Horizon service, Obsidian/Vault route, or external
  network service was invoked.
- No source, Wiki, derivative, output, or Vault body was read. The new
  verification queries only `knowledge_signal_batches` and
  `knowledge_signal_receipts` metadata in isolated test databases.
- No original user file or runtime credential was written or displayed.

### Test-First Evidence

- A new API regression first failed because the manual dispatcher accepted only
  a project ID and therefore could not verify the BSC receipt ledger. A mocked
  n8n response claiming `unverified-batch` could previously be shown as
  completed without any BSC record.
- The dispatcher now treats n8n's response as an untrusted bounded claim. It
  re-reads the same project's persisted batch status and receipt count before
  returning `completed`. Missing, processing, partial-count mismatch, or other
  unverified claims return `receipt_verification_pending` with zero unverified
  receipt count; persisted partial batches return
  `completed_with_rejections`.
- A frontend regression first failed because the Intel panel rendered the
  pending state as `Source check completed with 0 BSC receipts`. The typed
  client and panel now distinguish verified completion, no fresh items,
  persisted rejections, and pending receipt verification.
- A workflow-contract regression caught a stale assertion that rejected the
  required runtime project binding. It now verifies the intended constraint:
  the disabled workflow uses a signed, five-minute, project-scoped webhook
  flow through environment references only, with no embedded credential
  object, secret value, direct Feishu delivery, or automatic activation.

### Automated Verification

- `python -m pytest tests/api/test_knowledge_intelligence_api.py -q`
  - 6 tests passed, including verified receipts, absent ledger records,
    signature construction, project-writer access, and raw-content redaction.
- `npm run test:frontend -- --run src/components/knowledge/InformationOperationsPanel.test.tsx`
  - 8 tests passed, including truthful pending-state copy.
- Cross-layer operations and information-intelligence regression:
  - 106 tests passed across operations contracts/actions/graph/API/MCP, DBOS,
    Growth, workspace, n8n contracts, and intelligence API/service tools.
- PBOS regression: 77 tests passed.
- `npm run test:frontend`: 23 files and 199 tests passed. A first parallel
  run timed out in an unrelated Evidence Atlas table-preview test; its
  standalone rerun passed (12 tests), and the subsequent serial full suite
  passed. The timeout is not counted as a green run.
- `npm run check`, `npm run lint`, `npm run build`,
  `docker compose --profile full config --quiet`, and `git diff --check`
  passed. Lint has 0 errors and 214 pre-existing warnings. Build retains the
  existing ECharts vendor-chunk advisory above 500 kB.

### Operational Status

- The signed manual n8n endpoint is implemented and code-verified but has not
  been invoked in this increment because external networking is prohibited by
  the active boundary. Its status is implementation complete with external
  operational proof pending; no source capture, receipt, or knowledge value
  was fabricated.

## Deployment Preflight Revalidation

Date: 2026-07-31
Scope: prepare the combined governed n8n manual-run and Knowledge Operations
metric drill-down increment for a clean-image runtime verification.

### Verification

- `uv run pytest tests/api/test_knowledge_intelligence_api.py
  tests/api/test_knowledge_operations_api.py
  tests/knowledge/test_operations_service.py
  tests/test_n8n_information_intelligence_compose.py -q`
  - 16 tests passed. This covers signed manual dispatch, persisted-receipt
    verification, project/tenant access, contributor redaction, and Compose
    workflow constraints.
- `npm run test:frontend --
  src/components/knowledge/InformationOperationsPanel.test.tsx
  src/components/operations/KnowledgeOperationsCockpit.test.tsx`
  - 2 files and 19 tests passed.
- `npm run check`, `npm run build`, `docker compose --profile full config
  --quiet`, and `git diff --check`
  - Passed. The production build still reports the existing ECharts vendor
    chunk advisory (598.72 kB minified); this remains a performance follow-up.

### Runtime Boundary

- The currently running API image predates this increment, so its manual-run
  route is not used as evidence for this code. A clean committed image must be
  deployed before sending the signed request to n8n.
- The local n8n store contains historical workflow imports. Before real
  invocation, the runtime workflow must be reconciled to the committed
  disabled-by-default definition, with only the controlled webhook activated
  for the explicitly configured project. No historical workflow result is
  counted as operational proof.

## Governed Manual Dispatch Audit Trail

Date: 2026-07-31
Scope: make every authorized manual information-dispatch attempt durable and
traceable without retaining source content, credentials, or webhook details.

### Boundary

- No Obsidian/Vault, source, Wiki, derivative, or output body was read.
- No n8n, RSS, Horizon, browser, or external network request was made. The
  n8n HTTP boundary was replaced by local test doubles.
- No original user file was written. Only application code, typed client
  contract, tests, and this worklog changed.
- Audit input/output references hold only a generated request ID, trigger
  kind, verification state, bounded batch IDs, and verified counts. They
  exclude webhook URLs, signatures, secret values, and source payloads.

### Test-First Evidence

- The regression for verified receipts, pending receipt verification, no fresh
  items, and webhook failure first failed with `0 == 3` audit runs. This
  proved that the prior dispatcher returned a response without a durable
  `KnowledgeRun` record.
- The dispatcher now creates and atomically claims one
  `information_manual_dispatch` run before configuration checks or webhook
  work. It records `completed` transport outcomes with an explicit
  verification state, including `receipt_verification_pending`, and records
  configuration or webhook errors as failed runs.
- A separate regression proves that an incomplete configuration creates a
  failed audit record with `configuration_failed` and does not construct an
  HTTP client. This prevents a missing configuration from silently becoming an
  unaudited network attempt.
- The public manual-run response now includes the generated `run_id`; the
  frontend contract retains it for traceability without rendering sensitive
  internals.

### Automated Verification

- `./.venv/Scripts/python.exe -m pytest
  tests/api/test_knowledge_intelligence_api.py -q`
  - Passed: 8 tests. Includes project access, signed payloads, ledger-backed
    receipt proof, all four terminal dispatch outcomes, bounded redaction, and
    rejected configuration without HTTP construction.
- Cross-layer operations and information-intelligence regression:
  - Passed: 104 tests across operations contracts/actions/graph/API/MCP,
    DBOS, Growth, workspace, information-intelligence API/service/tools, and
    n8n workflow contracts.
- `npm run test:frontend -- --run
  src/components/knowledge/InformationOperationsPanel.test.tsx`
  - Passed: 8 tests.
- `npm run check`, `docker compose --profile full config --quiet`, and scoped
  `git diff --check` passed. Git emitted only CRLF normalization warnings.

### Operational Status

- This establishes code-level auditability. It does not prove a real n8n
  execution, RSS capture, external receipt, Obsidian export, or user feedback
  loop. The manual ingress remains implementation complete with external
  operational proof pending under the active no-network boundary.

## Governed RSS Operational Proof

Date: 2026-07-31
Scope: execute the committed signed manual-run path against the configured
project RSS registry, then verify the durable BSC result without displaying
source bodies, credentials, or Vault data.

### Deployment And Runtime Reconciliation

- Committed implementation: `8e0cfd5 feat(knowledge): verify governed
  intelligence operations`.
- Rebuilt and recreated the `bsc-backend`, `celery-worker`, and `celery-beat`
  containers from that commit. API health, PostgreSQL, Redis, Worker, Beat,
  and n8n were healthy after deployment.
- Exported the six pre-existing local n8n workflow records to the encrypted
  n8n volume before reconciliation. Imported the committed workflow,
  deactivated every historical record, and activated only its controlled
  webhook record `z7QYcMmiGAHNFmKg`.
- The workflow's scheduled trigger remains disabled. Activating the workflow
  is necessary only to register its signed production webhook; it does not
  enable unattended daily collection.
- Runtime checks confirmed that BSC intelligence, manual triggering, ingress
  signing, the bound project, the n8n project-ingress key, and the source
  manifest endpoint were configured. An unsigned direct webhook request was
  rejected; no unauthenticated collection occurred.

### Real End-To-End Result

- BSC invoked `POST /knowledge/intelligence/projects/proj_b8a285642094/manual-runs`
  with a fresh signed payload. n8n read the BSC project source manifest,
  collected the registered RSS feed, and submitted five signed `SignalBatch`
  records.
- BSC returned `completed`, with `batch_count=5`, `receipt_count=5`, and
  `verification.state=verified`. Each claimed batch was independently found
  in BSC's persisted signal-batch and receipt ledger before the response was
  returned.
- All five new batches are `completed`. Each represents an existing canonical
  source and is recorded as `duplicate_source`; no duplicate source record was
  created. This is the intended immutable-evidence and idempotency behavior.
- The current-day redacted daily brief is `available` with `complete`
  coverage. Its ten persisted receipts include one earlier new capture and
  nine repeat discoveries. This aggregate is not presented as ten new
  knowledge assets.
- Feishu delivery remains truthfully `unavailable` because no delivery
  configuration is present. The BSC daily brief is available for Studio,
  Obsidian projection, and later governed distillation; no external delivery
  was faked.
- Published Wiki page count remains `5`, unchanged by this run. RSS discovery
  did not publish a Wiki page, proposal, Skill, method, SOP, or content item.

### Release State

- n8n ingestion is now `implemented_with_operational_proof`: a real source
  registry to signed batch to BSC receipt to daily-brief chain has completed.
- Scheduled collection, optional Feishu mirroring, additional third-party
  connector credentials, and human review/publication remain independent,
  explicitly configured capabilities. They are not implied by this proof.

### Browser Boundary Check

- Opened the local Studio at `http://127.0.0.1:5180/`, opened Knowledge, and
  verified that an unauthenticated browser session remains unscoped: it shows
  no authorized project, no historical fallback, and disabled project actions.
- The browser did not receive or submit the local API key. Supplying a runtime
  access key through a browser field is a separate sensitive-data action and
  was deliberately not performed as part of this unattended verification.
- The rendered Knowledge workspace correctly exposes the `Intel` view and
  governed connection states, but a fully authorized visual check remains
  dependent on a user-authenticated Studio session. This does not weaken the
  API, receipt-ledger, or component-test evidence above.

## Local REST Probe And Dispatch Audit

Date: 2026-07-31
Scope: make the installed Obsidian Local REST integration observable without
reading plugin files or note bodies, and retain a bounded audit record for
every BSC-initiated n8n source check.

### Implementation And Verification

- Committed implementation: `ffe3f60 feat(knowledge): probe local obsidian
  rest safely`.
- The Local REST probe accepts only an explicitly configured local HTTPS
  endpoint, performs one bounded manifest request with an environment-only
  token, and returns only state, detail code, transport, plugin identity, and
  a bounded version. It cannot list, read, or write Obsidian notes.
- `uv run pytest tests/knowledge/test_obsidian_local_rest.py
  tests/api/test_knowledge_workspace_api.py
  tests/api/test_knowledge_intelligence_api.py
  tests/test_n8n_information_intelligence_compose.py -q`
  - 41 tests passed.
- `npm run test:frontend -- src/components/KnowledgeWorkspace.test.tsx
  src/components/knowledge/InformationOperationsPanel.test.tsx`
  - 2 files and 22 tests passed.
- `npm run check`, `docker compose --profile full config --quiet`, and
  `git diff --check` passed before deployment.

### Runtime Result

- Rebuilt the API image from `ffe3f60`; the replacement API container is
  healthy. n8n, PostgreSQL, Redis, Worker, and Beat remain healthy.
- A real signed manual RSS check created audit run `d76c34d5ead9` with status
  `completed`. Its bounded output reports five claimed batches, five verified
  batches, five verified receipts, and no pending batch IDs. The API response
  and the persisted run ledger agree.
- The project workspace returns Local REST state `unconfigured` with detail
  `disabled` and transport `not_configured`. Because no runtime Local REST
  token and endpoint were supplied, BSC did not read a plugin configuration,
  open an Obsidian note, or make a connector request.

### Remaining External Boundary

- Turning this status into `connected` requires the user to explicitly set
  `OBSIDIAN_LOCAL_REST_ENABLED`, a local HTTPS endpoint, and the plugin token
  in ignored runtime configuration. BSC will then perform only the manifest
  health probe; filesystem Vault sync remains the source/knowledge path.

## Obsidian Local REST Boundary Regression

Date: 2026-07-31
Scope: keep the optional Local REST health indicator inside its explicit,
metadata-only, authorized boundary.

### Boundary

- No Local REST endpoint, Obsidian process, Vault file, plugin setting, source
  body, or original user file was read or modified.
- No network request was made. The new API seam regression replaces
  `httpx.Client` with a failing sentinel and uses a temporary database.
- The indicator remains a health probe only. It is not a source bridge and it
  neither lists files nor reads/writes note content.

### Verification

- `./.venv/Scripts/python.exe -m pytest
  tests/api/test_knowledge_workspace_api.py
  tests/knowledge/test_obsidian_local_rest.py -q`
  - Passed: 31 tests. The added Workspace regression proves that an
    unauthenticated request is rejected before probe construction, and that a
    configured-but-disabled connector produces `unconfigured` without
    constructing an HTTP client.
- `npm run test:frontend -- --run
  src/components/KnowledgeWorkspace.test.tsx`
  - Passed: 14 tests, including redacted connected/rejected Local REST status
    presentation.
- `npm run check` and scoped `git diff --check` passed. Git emitted only CRLF
  normalization warnings.

### Operational Status

- Local REST remains optional. This regression verifies fail-closed behavior
  in code; it does not claim a new authenticated plugin connection, Obsidian
  restart, or evidence import in this increment.

### Composite Revalidation

- The combined local regression command covering Operations, DBOS, Growth,
  Workspace, information intelligence, n8n contracts, and Local REST passed
  with `110 passed, 1 warning`.
- The combined focused frontend command for Knowledge Workspace and governed
  information operations passed with `22 passed`.
- `npm run build` passed with the existing ECharts vendor chunk advisory
  (`598.72 kB` minified); `docker compose --profile full config --quiet`
  passed; `git diff --check` passed with only CRLF normalization warnings.
- Full frontend regression `npm run test:frontend` passed with `23` files and
  `200` tests. `npm run lint` passed with `0` errors and `214` existing
  warnings after moving the pure Local REST display formatter out of the
  component module; `npm run check` remained green.

## Full Regression And Runtime Recheck

Date: 2026-07-31
Scope: verify the current integrated knowledge-intelligence implementation
after the durable manual-dispatch audit regression was repaired.

### Automated Verification

- `./.venv/Scripts/python.exe -m pytest -q`
  - Passed: 1605 tests. Skipped: 14 environment-dependent tests. No failures.
  - The suite includes the four-outcome `information_manual_dispatch` audit
    regression and all current API, DBOS, MCP, knowledge, orchestration, and
    integration contracts.
- `npm run test:frontend`
  - Passed: 23 test files and 200 tests.
- `npm run check`
  - Passed: TypeScript project check completed without errors.
- `npm run build`
  - Passed: Vite production build completed successfully.
  - Follow-up: the existing ECharts vendor bundle is 598.72 kB minified and
    emits Vite's chunk-size advisory. This is a performance optimization item,
    not a build failure or a claim that code splitting has been completed.

### Runtime Recheck

- Docker reports the BSC API, PostgreSQL, Redis, and n8n containers as
  `healthy`; Celery worker and beat are running.
- This check neither reads nor writes source bodies, Vault files, external
  credentials, or Obsidian plugin data. It confirms local service liveness,
  not a new external capture or authenticated browser-session proof.

## E1 Metadata-Only Release Gate

Date: 2026-07-31
Scope: make the personal knowledge ecosystem consolidation decision executable
without allowing fixtures, paths, URLs, credentials, or source bodies into the
release packet.

### Implementation

- Added `app/knowledge/ecosystem_release_gate.py` with the frozen
  `e1-knowledge-ecosystem-v1` contract and nine required O1-O6/integration
  evidence IDs.
- The packet schema rejects unknown fields, duplicate IDs, unsafe durable IDs,
  non-timezoned timestamps, and any attempted `raw_content` field.
- The decision has exactly the E1 states: `release_ready`,
  `implemented_with_operational_proof_pending`, and `not_release_ready`.
  Missing or pending evidence remains pending; failed evidence and fixture
  substitution are hard blockers.
- The output matrix contains only evidence ID, state, proof class, bounded ID
  count, and safe detail code. It never emits packet values such as paths,
  URLs, credentials, prompts, provider payloads, or source content.

### Test-First Evidence

- The new regression initially failed during collection because the gate module
  did not exist (`ModuleNotFoundError`), then passed after implementation.
- `./.venv/Scripts/python.exe -m pytest
  tests/knowledge/test_ecosystem_release_gate.py -q`
  - Passed: 7 tests covering missing/pending evidence, fixture substitution,
    failed evidence, complete real metadata, source-body rejection, unsafe
    identifiers, timestamps, and duplicate packet IDs.

### Boundary And Status

- No Vault, source, Wiki, output, plugin, credential, or external service was
  read or written. All release packets in tests are synthetic metadata-only
  fixtures and are explicitly not operational proof.
- The evaluator is now capable of producing `release_ready` only for a fully
  populated real-evidence packet, but no such packet was supplied or fabricated
  in this increment. The overall E1 status remains
  `implemented_with_operational_proof_pending`.
- Post-gate `npm run build` passed; the existing ECharts chunk-size advisory
  remains the only build warning.

## E1 Workspace Release Projection

Date: 2026-07-31
Scope: expose the E1 consolidation decision in the authorized Knowledge
Workspace without treating configured services, UI state, or source records as
release evidence.

### Test-First Evidence

- The new workspace API regression first failed with `KeyError: 'release_gate'`.
  This proved that the evaluator existed only in its unit tests and the Studio
  could not display the current release boundary.
- `GET /knowledge/workspaces/{project_id}` now returns the one metadata-only
  `_workspace_release_gate()` decision. It starts from an empty packet, so it
  is deterministically `implemented_with_operational_proof_pending` until a
  separate durable-evidence workflow supplies the required handoff.
- The typed Studio contract displays the gate in both the connection path and
  status strip. It distinguishes `Ready`, `Pending`, and `Blocked`; it does
  not turn a successful Local REST probe, mapped Vault, plugin folder, or
  published page into a release claim.
- Frontend presentation regression covers unevaluated, pending, and blocked
  messages. Backend regression covers all nine missing evidence IDs and
  asserts that source-body and credential field names are absent from the
  response.

### Automated Verification

- `./.venv/Scripts/python.exe -m pytest
  tests/api/test_knowledge_workspace_api.py::test_workspace_status_exposes_an_honest_release_gate_without_source_bodies_or_secrets
  tests/knowledge/test_ecosystem_release_gate.py -q`
  - Passed: 8 tests. The only warning is FastAPI's upstream TestClient
    deprecation warning.
- `npm run test:frontend -- src/components/KnowledgeWorkspace.test.tsx`
  - Passed: 1 file, 15 tests.
- `npm run check`
  - Passed.
- `git diff --check`
  - Passed. Git reported existing CRLF normalization advisories only.
- `./.venv/Scripts/python.exe -m pytest
  tests/api/test_knowledge_workspace_api.py
  tests/knowledge/test_obsidian_local_rest.py
  tests/knowledge/test_ecosystem_release_gate.py -q`
  - Passed: 42 tests. This combined rerun includes the workspace projection,
    Local REST redaction/fail-closed behavior, and E1 gate invariants.
- `npm run test:frontend -- src/components/KnowledgeWorkspace.test.tsx`,
  `npm run check`, and `npm run build`
  - Passed on 2026-08-01. The production build retains the existing ECharts
    vendor-chunk advisory at 598.72 kB minified; it is not hidden or counted
    as a completed performance optimization.

### Boundary And Status

- No Obsidian Vault body, source body, Wiki/output body, plugin code, token,
  external endpoint, or original user file was read or written in this
  increment. The endpoint computes a fixed metadata-only missing-evidence
  decision and does not call a network client.
- The visible E1 status is intentionally not `release_ready`. All nine
  operational proof categories remain missing until separately collected,
  durable, project-authorized evidence is reviewed. No fixture or UI state is
  used to reduce that gap.

### Runtime Reverification (2026-08-01)

- Rebuilt the BSC API image and verified API, PostgreSQL, Redis, Celery Worker,
  Celery Beat, and n8n are running; the API health endpoint reports all
  declared dependencies as available.
- The first Local REST container probe correctly returned
  `unavailable/transport_unavailable`. Diagnosis showed Docker host routing was
  resolvable but the installed plugin service had no running Obsidian process
  or listening local port. BSC did not retry indefinitely, relax TLS, or claim
  a connection.
- Started the locally installed Obsidian application. After its plugin service
  initialized, three independent container probes and one authorized Workspace
  API request all returned `connected/authenticated_manifest_verified` for
  `obsidian-local-rest-api` version `5.0.2` via `docker_host_tls`.
- The project metadata read found two ready Vaults. One already contains two
  captured `obsidian-excalidraw-plugin` source exports and one registered
  `codex-agent` output; every other registered route reports its honest
  `awaiting_export` or `awaiting_output` state. This check only read status
  counters and plugin identifiers, never note bodies or output content.
- The Workspace E1 response remained
  `implemented_with_operational_proof_pending` with nine missing evidence
  categories. A stable connector, live services, captured plugin exports, and
  registered output are useful operational facts, but they are not silently
  reclassified as the complete reviewed evidence packet.

## Durable Release Evidence Activation (2026-08-01)

### Implementation

- Added the project-scoped `knowledge_release_evidence` ledger with immutable
  revisions, safe durable identifiers, and no body, URL, prompt, credential,
  or provider-payload column.
- `GET /knowledge/workspaces/{project_id}` now evaluates the latest ledger
  revision per evidence category. Separate REST endpoints list, submit pending
  evidence, and let only a tenant administrator review it as verified real
  evidence. Project-scoped keys cannot review evidence or read another
  project's ledger.
- Added typed Studio API methods for the ledger. The Workspace retains its
  read-only release-proof status metric; it no longer assumes an empty packet
  when durable reviewed evidence exists.

### Test And Runtime Evidence

- The first full repository regression exposed the missing ledger REST routes:
  two workspace tests received `404` instead of their required review-gated
  responses. This was fixed rather than suppressed.
- Focused regression after the implementation passed: `44 passed` for the
  Workspace API, Local REST, and E1 evaluator contracts. Frontend API and
  Workspace tests passed `24`; `npm run check` and `npm run build` passed.
- A live authorized API run found a project with persisted
  `obsidian-excalidraw-plugin` captures. It submitted a pending
  `o3_real_plugin_exports` record and then performed the administrator review
  using three existing immutable `source:<id>` references. The resulting
  verified record is revision `2`; no source body was read or copied.
- The reviewed project now reports eight missing release-evidence categories.
  A separate authorized project remains at nine missing categories with an
  empty ledger, proving that the review did not cross a project boundary.
- A Compose recreation initially inherited a higher-priority process setting
  of `OBSIDIAN_LOCAL_REST_ENABLED=false`; BSC truthfully reported
  `unconfigured`. Recreating with the explicit enabled setting restored the
  connected runtime probe. A fresh process with URL and key removed also
  authenticated through the mounted plugin configuration, proving both
  supported paths without printing either secret.

### Current Boundary

- The system has real, reviewed proof for plugin-origin evidence capture only.
  Eight required E1 categories, including feedback-cycle and browser proof,
  remain pending and the release gate remains
  `implemented_with_operational_proof_pending`. The ledger does not equate
  connected services or generated UI state with the remaining operational
  evidence.

### Full Regression

- Serial full backend regression passed `1637 passed, 14 skipped` after the
  native async Agent dispatch improvement. It includes the release ledger,
  project isolation, A/B/C/D performance, and the SOP/Risk parallel latency
  gate.
- Full frontend regression passed `24 files, 211 tests`. Lint completed with
  `0` errors and the repository's existing `214` warnings; Compose full-profile
  rendering and `git diff --check` passed.
- The workspace evidence ledger now renders the complete authoritative gate
  matrix, including requirements with no submitted record. A missing row is a
  visible missing requirement, never a hidden absence or an inferred success.

## E1 Metadata Ledger Regression And Studio Review Surface

Date: 2026-08-01
Scope: make the existing metadata-only E1 release ledger inspectable and
reviewable in Studio while preserving the no-body, no-provider, no-Vault-write
boundary.

### Implementation

- Added `ReleaseEvidenceLedger` to the Knowledge Workspace inspector. It
  displays only evidence ID, state, proof class, timestamp, durable IDs,
  detail code, revision, and recorded role.
- Project administrators can append only `pending`, `unavailable`, or
  `failed` observations. There is no control for editing `release_ready` or
  for submitting a verified claim.
- The administrator review form is visible only to the tenant `admin`; it
  remains disabled until the reviewer supplies a timestamp, one or more
  durable IDs, and a safe review code. The backend remains the authority for
  project scope and review acceptance.
- Expanded the frozen release-evidence contract regression to reject Vault
  paths, source URLs, API keys, provider payloads, prompts, and source bodies.
  The MCP project-scope assertion now matches the established Chinese access
  error rather than weakening the permission check.

### Verification

- `./.venv/Scripts/python.exe -m pytest
  tests/knowledge/test_ecosystem_release_gate.py
  tests/api/test_knowledge_workspace_api.py::test_workspace_status_exposes_an_honest_release_gate_without_source_bodies_or_secrets
  tests/api/test_knowledge_workspace_api.py::test_workspace_release_evidence_requires_admin_review_and_changes_only_the_project_gate
  tests/api/test_knowledge_workspace_api.py::test_workspace_release_evidence_rejects_unreviewed_verified_claims_and_source_bodies
  tests/mcp/test_wiki_tools.py::test_mcp_release_evidence_is_read_only_project_scoped_and_redacted -q`
  passed: `16 passed`.
- `npm run test:frontend -- src/components/KnowledgeWorkspace.test.tsx
  src/components/knowledge/ReleaseEvidenceLedger.test.tsx
  src/api/knowledgeWorkspaceApi.test.ts` passed: `27 passed`.
- `npm run check` and `npm run build` passed. The existing ECharts vendor
  chunk advisory remains `598.72 kB` minified.
- `npm run lint` completed with `0` errors and `214` existing warnings; no
  new lint error was introduced by the release-evidence surface.
- `git diff --check` found no whitespace errors; only repository-wide CRLF
  normalization advisories were emitted.

### Boundary And Status

- This increment did not read any Obsidian/Vault/source/Wiki/output body,
  did not call an external service, and did not write back to any original
  file. Tests used isolated temporary databases and mocked browser requests.
- The UI does not convert observations, connector status, or a visible table
  into release proof. E1 remains `implemented_with_operational_proof_pending`
  until the remaining project-authorized external evidence is separately
  observed and reviewed.

## Studio Release-Matrix And Authorization-Gate Repair

Date: 2026-08-01
Scope: turn the E1 release matrix into an inspectable Studio surface and
repair a real browser crash without reading knowledge bodies, accessing an
external service, or writing to a Vault/original file.

### Observed Defects And Repair

- The API already returned the nine-category E1 matrix, but the Studio type
  discarded it and rendered only submitted ledger records. An unsubmitted
  proof category was therefore invisible to the operator.
- A local Studio browser run at `127.0.0.1:5180` also exposed an unhandled
  `response.evidence[0]` access when the list field was absent. Opening
  Knowledge then produced a blank page rather than a bounded unavailable
  state.
- `ReleaseEvidenceLedger` now merges the gate matrix with persisted metadata,
  so every required category is visible as `missing`, `pending`, `failed`, or
  `verified`; no missing check is silently omitted.
- An incomplete list response now preserves the workspace, renders all nine
  requirements as unverified, and shows a bounded protocol warning. It never
  interprets an incomplete response as real evidence.
- The ledger is now explicitly gated on an authorized, selected project. Before
  Studio verifies access, it performs no ledger request and presents only the
  project-access prompt. This avoids an unauthorized/legacy response being
  misclassified as project release data.

### Test-First And Browser Evidence

- Added failing regressions for missing matrix rows, omitted `evidence` arrays,
  and unauthorised pre-project rendering. They initially demonstrated the
  invisible row, React `TypeError`, and premature request respectively.
- `npm run test:frontend -- src/components/knowledge/ReleaseEvidenceLedger.test.tsx
  src/components/KnowledgeWorkspace.test.tsx` passed: `21 passed`.
- Complete frontend regression passed: `24` files and `213` tests. `npm run
  check` and `npm run build` passed; the existing ECharts `598.72 kB` advisory
  remains visible.
- Browser verification used only the local Studio. On desktop, the repaired
  unauthorized workspace displayed the selected-project access message, no
  protocol error, and zero fabricated release rows. At `390x844`, the same
  state remained nonblank with `documentScrollWidth=384`,
  `workspaceScrollWidth=378`, and `workspaceClientWidth=378`; there was no
  document-level horizontal overflow. The temporary viewport override was
  restored after the test.
- The current full backend baseline independently passed immediately before
  this UI-only repair: `1635 passed, 14 skipped` in approximately six minutes.

### Boundary And Remaining Proof

- No release status was advanced. The no-access browser session intentionally
  did not read or submit a ledger item, and the repaired display continues to
  report project selection/authorization as a prerequisite.
- E1 remains `implemented_with_operational_proof_pending`. Real user-origin
  source confirmation, reviewed output feedback, and the remaining separately
  observed release categories cannot be replaced by a UI or test fixture.

## Local REST Runtime Environment Repair (2026-08-01)

### Implementation

- Replaced direct Compose interpolation of `OBSIDIAN_LOCAL_REST_*` on the API
  service with the optional, Git-ignored `./.env.runtime` file. This prevents
  stale parent-process settings from overriding the operator's local runtime.
- The local runtime file enables only the existing plugin-settings fallback.
  The Obsidian Local REST token remains in the mounted Vault's plugin settings;
  it was not copied into Compose, source control, logs, or this record.
- Added a Compose contract regression to ensure the API service retains the
  optional runtime file and cannot reintroduce direct Local REST interpolation.

### Verified Runtime Evidence

- `./.venv/Scripts/python.exe -m pytest tests/test_docker_compose_contract.py
  tests/knowledge/test_obsidian_local_rest.py
  tests/api/test_knowledge_workspace_api.py -q` passed: `49 passed`.
- `docker compose config --quiet` passed.
- After `docker compose up -d --no-deps --force-recreate bsc-backend`, the API
  container became healthy. Its bounded probe reported `connected`,
  `authenticated_manifest_verified`, `docker_host_tls`, plugin-config source,
  and Local REST plugin version `5.0.2`.
- An authorized BSC workspace API read for `proj_b8a285642094` returned the
  same connected Local REST status and `vault.connection.state=ready`.

### Boundary

- This repair verifies connector identity and authentication only. It does not
  read note bodies, list Vault content, or claim that any awaiting plugin
  export has been synchronized.

### Full Regression

- `./.venv/Scripts/python.exe -m pytest -q` completed after the runtime
  repair: `1637 passed, 14 skipped` in `342.67s`. The run reported three
  pre-existing deprecation warnings (Starlette TestClient and two Pydantic
  `.dict()` calls); no test failed.
- `npm run test:frontend` passed: `24` test files and `211` tests. `npm run
  check` and `npm run build` also passed.
- The production build emits the existing Vite advisory for the `598.72 kB`
  minified ECharts vendor chunk. It is a performance follow-up, not a failed
  build or a release-evidence claim.

## Copilot Replacement Recheck (2026-08-01)

- Read the active Obsidian community-plugin inventory without reading Copilot
  settings or provider credentials. `copilot` is enabled; `realclaudian` is
  installed for local history but disabled.
- The Copilot custom-prompt directory and the governed
  `projects/default/04_Outputs/copilot/` route both exist. The protected BSC
  workspace API reports no active Claudian adapter and one Copilot
  `filesystem_output` adapter with `path_status=ready` and
  `capture_state=ready_for_first_output`.
- No Copilot-authored Markdown file exists in the output route yet, so its
  runtime status remains `awaiting_output` with zero registered outputs. This
  is not treated as a completed content or feedback loop.

## Copilot Project-Scoped Delivery Closure (2026-08-01)

### Actual Correction

- The live Copilot `defaultSaveFolder` already points to the current BSC
  project. The Chinese `BSC 知识审查与沉淀` command still referenced the
  historical `default` project, so its output path and frontmatter project ID
  were corrected to `proj_b8a285642094`.
- Strengthened this project's `AGENTS.md` rather than relying on the legacy
  project's rules. It now declares output/method/review page kinds, evidence
  boundaries, context-specific SOP requirements, a Copilot reviewed-output
  contract, and A/B/C/D maintenance and feedback rules.
- No provider setting, Keychain record, chat transcript, or user-authored
  content was read, copied, or changed.

### Runtime Acceptance

- A protected workspace API read confirmed the Copilot adapter is trusted,
  `filesystem_output`, `path_status=ready`, and
  `runtime_configuration=destination_matches_bridge`. The adapter accurately
  remains `awaiting_output` until a reviewed file exists.
- Triggered real run `2f7329f57cab` through the protected BSC API and waited
  for the Celery `source_sync` terminal result. It completed with Copilot
  output-feedback counts `scanned=0`, `registered=0`, `duplicates=0`,
  `rejected=0`, and `blocked=0`; empty output was not fabricated or promoted.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_sync.py
  tests/knowledge/test_obsidian_output_sync.py
  tests/api/test_knowledge_workspace_api.py -q` passed: `59 passed, 1
  skipped`.

### Remaining User Action

- In Obsidian Copilot, use either `BSC Project Delivery` or `BSC 知识审查与沉淀`
  for a real task, review the result, and intentionally save one Markdown
  deliverable in the configured Copilot output folder. That authentic user
  action is the only missing event needed to exercise capture, evaluation, and
  feedback with real content; the platform must not synthesize it as a test
  substitute.

### Prompt Truthfulness Refinement

- The delivery command now distinguishes review-ready Markdown from a saved
  file: it creates a file only with an explicit write capability and user save
  intent, otherwise it names the proposed file and says that it remains
  unsaved. The Chinese review command has the same rule.
- A static Vault contract check confirmed both commands contain no historical
  `default` project path or project ID, bind to `proj_b8a285642094`, and retain
  the no-false-save rule. A fresh protected workspace read still reports the
  trusted Copilot bridge as `destination_matches_bridge` and
  `ready_for_first_output`; the API container remains healthy.

## Deployed Ledger Recheck (2026-08-01)

- The released Studio surface now receives the full release-gate matrix and
  renders every E1 category, including absent evidence. An older or incomplete
  response no longer crashes the workspace: it leaves all requirements visible
  as unverified and shows a bounded protocol error instead.
- The ledger does not issue a request before Studio has verified the selected
  project's authorization. This prevents a legacy or unauthorised response
  from being rendered as project proof.
- The deployed API reports the same matrix truth as Studio: only project index
  2 has one reviewed real-proof row (`o3_real_plugin_exports`, revision `2`,
  three durable IDs); the remaining eight requirements are missing. Project
  index 1 remains empty and isolated.
- Regression after deployment: focused Workspace/Ledger tests passed `20`,
  the complete frontend suite passed `213`, the Python suite passed `1638`
  with `14` designed skips, and the production build passed. This is an
  inspectable operational-proof surface, not a claim that the remaining
  evidence or business value has been established.

## Copilot Automatic Capture Recheck (2026-08-01)

- The persistent `growth_daily` schedule is enabled for `17:00`
  `Asia/Shanghai`. Its worker synchronizes declared Obsidian exports and
  D-layer outputs before daily distillation, so a reviewed Copilot file does
  not depend on a manual API call for eventual capture.
- Scheduled daily run `fe209111de91` recorded `trigger=schedule`, completed
  successfully, and persisted a completed sync with Copilot output counts
  `scanned=0`, `registered=0`, `duplicates=0`, `rejected=0`, and `blocked=0`.
  This proves the scheduled path executes and remains honest while no reviewed
  Copilot file exists.

## Obsidian Configuration Read Boundary Regression (2026-08-01)

### Boundary

- No Vault source, Wiki, output, or original user file was read, changed, or
  written during this increment. All fixtures use isolated temporary paths.
- No HTTP client, local listener, external network, browser, plugin code, or
  credential was accessed. The tests explicitly reject HTTP construction and
  socket connection while the Local REST configuration fallback is evaluated.
- The only permitted future read remains the bounded JSON settings file for an
  explicitly installed plugin. A settings path that contains a symlink is not
  a permitted configuration input.

### Test-First Evidence And Correction

- Added two deterministic regression tests that simulate a plugin `data.json`
  path resolving to a source note. The first red run failed because both the
  Local REST fallback and the plugin destination-status probe resolved the
  path before checking it, then attempted to read the protected source body.
- Both code paths now check every component from the configured Vault root to
  the declared plugin settings file before resolving it. Any symlink produces
  the bounded `plugin_settings_unsafe_path` state and performs no source-body
  read, source write, or network operation.
- The simulation does not require Windows symlink privileges, so the security
  assertions execute in CI and on this host instead of becoming skipped tests.

### Verification

- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_obsidian_local_rest.py
  tests/knowledge/test_wiki_sync.py -q` passed: `34 passed, 1 skipped`.
- `./.venv/Scripts/python.exe -m pytest
  tests/api/test_knowledge_workspace_api.py -q` passed: `30 passed`.
- The one skipped test is the pre-existing real-symlink capability check for
  the current Windows principal; the new safety assertions are not skipped.

### Status

- This is a local configuration-boundary hardening step. It does not assert a
  new export, source capture, content outcome, or feedback-loop result.

## Integrated Regression After Configuration Boundary Hardening (2026-08-01)

### Scope

- Revalidated the integrated application after rejecting symlinked plugin
  settings before resolution. This run used only tests, local build tooling
  and Compose configuration parsing; it did not call a third-party service,
  browser session, Obsidian REST endpoint, Vault sync, or knowledge schedule.
- No user Vault source, Wiki text, output body, plugin source code, original
  file, credential, or provider payload was read, written, logged, or used as
  a fixture.

### Verification

- `./.venv/Scripts/python.exe -m pytest -q` passed: `1641 passed, 14
  skipped, 3 warnings` in `288.67s`. Skips remain environment/real-service
  conditions and are not counted as operational proof. Warnings are the
  existing Starlette TestClient deprecation and two Pydantic `.dict()`
  deprecations.
- `npm run test:frontend` passed: `24` files and `213` tests.
- `npm run check` passed.
- `npm run lint` completed with `0` errors and `214` existing warnings.
- `npm run build` passed. The existing `vendor-echarts` bundle advisory
  remains `598.72 kB` minified and is retained as a performance follow-up.
- `docker compose --profile full config --quiet` and `git diff --check`
  passed. Git emitted only the repository's existing CRLF normalization
  notices.

### Release Truth

- The integrated code and its local regression gate are green. E1 remains
  `implemented_with_operational_proof_pending`: three real project cycles,
  actual enabled-plugin exports, a real evaluated output with feedback, and
  their non-fabricated release evidence still require user-origin work. None
  of those items has been elevated from fixture, folder, schedule, or UI state.

## Release Ledger Action Guidance (2026-08-01)

### Product Correction

- The Studio evidence ledger formerly surfaced only E1's machine-oriented
  category IDs. A missing gate was visible but did not explain the required
  business proof or the next operator action, forcing the user to consult the
  implementation plan.
- Each of the nine fixed gates now has an accessible business label, required
  proof statement, and next-action instruction. Missing or pending rows retain
  their exact technical ID and status while explaining the path to a legitimate
  proof record.
- Guidance explicitly distinguishes real plugin export, multimodal
  extraction/reference, visualization inspection, feedback effect, service
  recovery, authorization, and desktop/mobile evidence. It does not offer a
  shortcut to mark a requirement verified.

### Boundary

- The ledger still renders and stores only bounded metadata. The new guidance
  contains no source body, URL, prompt, credential, Vault path, or provider
  response. It does not invoke Source Sync, Local REST, browser automation,
  external services, or any write to an original file.
- Administrator review still requires observed time, durable IDs and an
  explicit real-proof decision. Project readers remain read-only.

### Verification

- The new regression first failed because the missing O4 row exposed only
  `o4_extraction_reference`. After implementation it passed with `7` ledger
  tests, including metadata redaction and disabled unauthorized loading.
- `npm run check` passed.
- `npm run test:frontend` passed: `24` files and `214` tests.
- `npm run build` passed. The existing ECharts vendor advisory remains
  `598.72 kB` minified; it is recorded as a performance follow-up, not hidden.

### Form Usability Follow-Up

- The read-only rows became actionable, but both evidence selectors still
  rendered only internal category IDs. The observation and administrator-review
  selectors now render `Business label (stable_id)` while retaining the same
  stable `option.value` sent to the API.
- A regression first failed because `o4_extraction_reference` and
  `o1_secure_boundary_restart` remained the accessible option names. It now
  proves that both selectors expose the business labels and preserve the
  stable ID for submission.
- Focused ledger regression passed: `8` tests. `npm run check`, the complete
  frontend suite (`24` files, `215` tests), and `npm run build` passed. The
  existing ECharts vendor advisory remains unchanged.

## PBOS Historical Text Quarantine (2026-08-01)

- Copilot remains the only active Obsidian AI entry point for this project;
  Claudian is disabled and does not participate in the workspace flow.
- The authorized PBOS API read exposed three unverified outcomes and one
  feedback record. One outcome and the feedback contained unreadable legacy
  text. The backend record, receipt identifiers, and audit lineage were not
  modified.
- PBOS now quarantines that text at the presentation boundary: it does not
  appear in the textarea or feedback list, the user sees an explicit
  unreadable-history notice, and a pending result cannot be accepted from an
  unreadable prefill. Readable historical summaries retain the previous
  review behavior.
- Tests and gates after the change: `24` frontend files and `216` tests,
  `npm run check`, `npm run lint` (`0` errors, `214` existing warnings), and
  `npm run build` all passed. Studio returned HTTP `200` on port `5180`.
- Browser visual automation was attempted but the current in-app browser
  bridge failed before tab connection because its kernel-assets path was
  unavailable. This record intentionally leaves visual confirmation pending
  instead of treating the HTTP response as a visual acceptance claim.

## User-Assisted Zotero Export Probe (2026-08-01)

- The active personal knowledge project is `proj_b8a285642094`; the historical
  `default` project is not the current plugin target. The installed Zotero
  Desktop Connector configuration points to the active project's declared
  route `projects/proj_b8a285642094/01_Sources/zotero`.
- A user-triggered Zotero import created the real file
  `projects/proj_b8a285642094/01_Sources/zotero/Li2023.md`, but the file size
  is `0` bytes. This proves an export attempt, not a usable source capture.
  No source sync was started, and no file body was read.
- The empty export is excluded from E1 operational proof. The next operator
  action is to import a Zotero item that contains a real note (or a genuinely
  authored literature note), then recheck that the generated file is
  non-empty before running the governed BSC `Sync` action.
- A subsequent user-triggered import updated the same file but yielded only
  `3` bytes. It remains a contentless export attempt and is still excluded
  from capture. The user must select an actual Zotero child note with
  substantive authored content, rather than only its parent bibliographic
  record, before a governed sync can be attempted.
- Configuration readback clarified that the Zotero `noteImportFolder` is
  already the correct active-project route, while the UI field labelled
  `Output Path` controls the per-note filename template. It had been changed
  to the old `default` directory. The required value for that field is
  `{{citekey}}.md`; the folder must remain the active-project route. This
  correction is operator-guided and no plugin configuration was changed by
  the backend.
- User correction was verified from bounded configuration metadata: the
  active-project import folder remains
  `projects/proj_b8a285642094/01_Sources/zotero`, the output template is
  restored to `{{citekey}}.md`, and the user-exported `Li2023.md` is now
  `3715` bytes. This is a valid pre-capture condition, not a captured BSC
  source or release proof. A governed source sync still needs explicit
  authorization because it will read the newly exported file body.
- Subsequent bounded readback showed that the governed sync did run after the
  user export: source `f4278140ca7f` now represents the Zotero file with
  `validated` status and `untrusted` trust level. This is real A-layer
  capture, not trust promotion. The source body was not printed or copied
  into this record; a source review/admission decision is still required
  before it can support Wiki claims.
- A live semantic triage was then executed for `f4278140ca7f`. The evaluator
  returned disposition `ignore` with priority `30`, while the API explicitly
  returned `explicit_approval_required` and kept the source at `validated`.
  No automatic admission or Wiki publication occurred. This confirms the
  source trust gate is operational, including the negative recommendation
  path; human override is the only remaining route if this source is truly
  needed for the project.

## Authorized Zotero Source Sync (2026-08-01)

- After the user explicitly authorized the current project's governed source
  sync, the local protected API queued run `ff9bf33ed83d` for
  `proj_b8a285642094`. The Celery worker completed it at
  `2026-08-01T03:58:13Z`; no external URL or provider was invoked.
- Durable run output reported `scanned=5`, `created=3`, `duplicates=2`,
  `rejected=0`, `deleted=0`, `skipped=0`, and `blocked=0`. Its bounded
  multimodal extractor summary was `attempted=3`, `complete=3`, and
  `partial=0`. The evidence mirror completed with `adopted=1`, `created=0`,
  `updated=0`, `unchanged=39`, `conflicts=0`; output-feedback registration
  remained truthfully `0`.
- The trusted Zotero connector now reports `captured` with one captured source.
  Its source record is `f4278140ca7f`, has plugin provenance
  `obsidian_plugin:obsidian-zotero-desktop-connector`, and belongs to
  `proj_b8a285642094`. A project-scoped source read returned 47 records and
  every returned record had that same project ID. No source body was exposed
  by the verification reads and no original Obsidian export was modified.
- This completes real A-layer capture for this export. It does not approve a
  source, publish Wiki knowledge, create a method or output, or satisfy the
  remaining E1 evidence gates. Those actions require their own governed
  review and authorization.

## Governed Zotero Review and Growth Cycle (2026-08-01)

### Historical Revision Repair

- A legacy concurrent daily publisher had left one historical database row
  without a matching immutable Vault archive. The repair does not copy the
  current daily document or manufacture an archive for that row.
- The damaged row is now retained only as bounded audit metadata with status
  `superseded_artifact_missing`; its output paths and file hashes are cleared.
  A same-input rerun receives a deterministic successor identity, so the
  database unique key cannot present a new publication as the old artifact.
- API revision selection excludes that status from current revisions. A
  history read can disclose the state, but it has no readable output path.
- Regression coverage passed for the repair, stable successor identity, and
  API currentness behavior. The complete affected suite passed:
  `121 passed, 1 warning` across daily distillation, Growth API, and knowledge
  workspace API tests. The warning is the existing Starlette TestClient
  deprecation.

### Live Run Evidence

- Docker Compose rebuilt and restarted the API and Celery worker from the
  repaired source. The API health endpoint returned `200`; API, Worker,
  PostgreSQL, Redis, Beat, and n8n were running, and the worker loaded
  distillation contract revision `33`.
- With explicit project authorization, the protected Growth API queued run
  `410ac265bf7e` for `proj_b8a285642094`. The run completed through governed
  Obsidian sync, model execution, distillation publication, and durable run
  completion events. No source body, provider response, credential, or prompt
  was printed or copied into this worklog.
- The completed run generated one managed daily artifact from `152` bounded
  input records. Its recorded generation mode is `llm` using the configured
  Growth provider and model; no deterministic fallback or failure category was
  recorded. The worker queue was empty after completion.
- Revision metadata now reports one quarantined missing-artifact history row,
  zero such rows marked current, and a latest current daily revision in LLM
  mode. This is real Growth-cycle evidence only: it does not override the
  Zotero triage recommendation, promote source trust, publish Wiki claims, or
  fabricate an output-feedback loop.

## Copilot First Real Output Registration (2026-08-01)

- The earlier `awaiting_output` state in this record was accurate at its
  timestamp. It is superseded by a later real Obsidian action: Copilot
  generated and automatically saved
  `projects/proj_b8a285642094/04_Outputs/copilot/PBOS_v1_Execution_Plan@20260801_123122.md`.
- The first provider attempt exhausted the `6000` output-token limit and
  produced no final content. Copilot then generated a complete Brief-grounded
  plan after its model setting was changed in the plugin UI to `12000`; the
  saved conversation retains both attempts as immutable history. The second
  response is bounded, evidence-aware, and does not claim an executed result.
- Governed run `60ae633c6ec4` completed through the live Celery `source_sync`
  path. The output route scanned one file with no rejection or block, and the
  project now has two registered Copilot output versions with distinct hashes.
  The bridge reports `registered_output`, `trusted`, and
  `destination_matches_bridge`; the D-layer records remain review-pending.
- This is completion of the real Copilot output bridge, not completion of the
  personal-learning loop. Owner review, an observed Outcome, and two more
  comparable delivery records are still required before promotion. GitHub and
  Feishu still correctly report `awaiting_authorization`.

## Copilot Output Provenance Rollout (2026-08-01)

- The deployed parser now recognizes bounded metadata produced by the real
  Copilot conversation export: provider, model, topic title, Markdown type,
  revision marker, and same-project context paths. It deliberately excludes
  prompts, Keychain values, cross-project paths, source/page lineage, and any
  learning or acceptance decision.
- Fresh records will carry this metadata. The two existing registered versions
  remain immutable and keep their historical `external_plugin` / `unknown`
  metadata; they are not silently rewritten to make the bridge appear newer
  than it was. This is verified compatibility behavior, not a failure.
- Normal run `fa4da88cad62` completed after deployment. Its output-feedback
  report was `scanned=1`, `registered=0`, `duplicates=1`, `rejected=0`,
  `blocked=0`, proving the legacy Copilot file is still accepted as an
  immutable duplicate. The actual next Copilot-generated export is the only
  valid path for a new D-layer version carrying parsed model metadata.

## Prior Governed Zotero Review State (2026-08-01)

- A bounded post-run read confirmed source `f4278140ca7f` remains
  `validated` and `untrusted`. Its then-current semantic triage was completed with
  disposition `archive` and failed reliability; it did not receive automatic
  admission, trust promotion, Wiki publication, or use as a trusted claim.
- The completed Growth cycle therefore proves the governed execution path and
  its LLM daily artifact, not the validity of this particular Zotero item. An
  explicit human approval with a documented reason remains required before
  any non-trusted source can enter authoring-eligible knowledge.

## Reauthorized Zotero Review and Growth Run (2026-08-01)

- The user explicitly authorized a further governed review and Growth cycle
  for source `f4278140ca7f` in `proj_b8a285642094`. The protected semantic
  review endpoint completed without exposing the source body, prompt,
  credential, or provider response. Its returned recommendation was `ignore`
  with failed reliability and `explicit_approval_required`; the source remains
  `validated` / `untrusted`. No lifecycle transition, trust promotion, Wiki
  publication, method creation, or output registration occurred.
- The metadata-only `SourceReferenceProjector` was run for that source. It
  created `0` reference links, found `0` existing links, and skipped `1`
  invalid or non-bibliographic metadata value. Local paths and source content
  were not converted into a synthetic citation. The source therefore still
  has no legitimate URL, DOI, or citation-key link, and the O4 traceability
  gap remains open.
- The protected Growth API queued daily run `f48c450f3d6a`; Celery completed
  it with `8` durable events and no run error. It reconciled the declared
  Obsidian routes without new captures, rejections, or blocks. The immutable
  audit manifest contained `160` bounded input records, including this source
  for accounting, but it listed `f4278140ca7f` in
  `daily_excluded_source_ids`. The source was absent from both selected context
  sources and citation sources, so it could not influence the resulting
  knowledge content.
- The run returned `preserved`, not a new daily publication. Its generation
  metadata was `deterministic`, while the currently published daily artifact
  is LLM-generated. The publication guard recorded
  `incomplete_llm_generation_cannot_replace_published_daily`, leaving the
  existing managed LLM artifact intact and creating no replacement output
  path. This is the intended anti-regression behavior, not successful new
  content generation.
- The project has real evidence that review, source exclusion, durable
  scheduling, sync, and preservation are operational. It does not close the
  evidence-link gap, authorize this source for authoring, or establish the
  feedback/release proof required for `release_ready`.

## Copilot Transcript Boundary Repair (2026-08-01)

- Claudian remains replaced by Obsidian Copilot. Copilot's automatic
  `defaultSaveFolder` is now the active project's separate conversation
  archive, `copilot/copilot-conversations`; the governed reviewed-output
  bridge remains `04_Outputs/copilot`. The configuration was changed without
  reading or recording plugin credentials.
- The prior Copilot file was a conversation transcript, not a reviewed
  delivery: it lacked `bsc_output_contract: v1` and contained a truncated
  generation attempt. It was moved unchanged from the reviewed-output route
  into the conversation archive. SHA-256 equality was checked before and
  after the move; no transcript body was copied into this worklog.
- The two historical registrations for that transcript,
  `9aca690865dde8cf706fbbe6` (run `410ac265bf7e`) and
  `a949e1ebd933e81ea9ddb74e` (run `2c5d307c67d9`), are retained as immutable
  audit artifacts but were evaluated through the protected BSC output API as
  `rejected` with quality `0`. Their persisted findings are
  `copilot_output_contract_missing` and `copilot_transcript_not_reviewed`.
  They are not accepted knowledge, evidence, or a Copilot delivery.
- The deployed output bridge now rejects every Copilot file without the BSC
  v1 output contract. A valid, same-project Copilot delivery with that
  contract remains registerable exactly once and is still review-pending;
  automatic conversation saves cannot cross into the D-layer.
- A real governed `source_sync` run, `580e5deeec8a`, completed after the
  migration. Its output-feedback summary reported `scanned=0`,
  `registered=0`, and `rejected=0` for the now-empty reviewed-output route.
  The active runtime readback reports Copilot as `configured` with
  `conversation_archive_separated_from_reviewed_output`, `awaiting_output`,
  and `ready_for_first_output`; rejected history is no longer presented as a
  current registered output.
- Docker Compose rebuilt the API, Celery Worker, and Beat from this source;
  health checks confirmed PostgreSQL, Redis, Celery, the LLM provider, and the
  document parser are available. Verification passed with
  `32 passed, 1 skipped` for the focused Obsidian suites and
  `1660 passed, 14 skipped` for the complete pytest suite. The only warnings
  are the pre-existing Starlette TestClient and Pydantic deprecations.
- Remaining boundary: the first genuine Copilot deliverable must be manually
  reviewed and saved to `04_Outputs/copilot/` with valid BSC v1 frontmatter.
  It will then enter `registered` review status; no automatic save, chat
  transcript, or unverified response may be represented as completed work.

## Knowledge Workspace Triage Metric Correction (2026-08-01)

- **Observed defect:** the Knowledge Workspace rendered `eligible/evaluated`
  as a `passed triage` ratio. These counters describe different lifecycle
  populations, so the display could show an impossible-looking value and
  falsely imply a pass rate.
- **Repair:** the UI now shows evidence captured, outputs registered,
  evaluated, eligible, and awaiting-review counts as separate governed states.
  No source, output, triage disposition, or growth record was changed.
- **Verification:** the focused frontend regression test and TypeScript check
  passed. The authorized Studio displayed the corrected state text for the
  current project; the former ratio label was absent.
- **Boundary:** the correction improves truthful operational visibility only.
  It does not turn eligible sources into approved claims, nor make an
  unreviewed Copilot output a verified learning artifact.
