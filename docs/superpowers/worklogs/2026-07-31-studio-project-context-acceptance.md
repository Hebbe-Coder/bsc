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
