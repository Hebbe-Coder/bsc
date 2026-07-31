# PBOS Runtime Readiness Worklog

## 2026-07-31 Obsidian Local REST Recovery

- **Observed fault:** a recreated API container lost its ephemeral Local REST
  environment and correctly reported `unconfigured`. Vault sync and PBOS
  artifacts remained intact, but the plugin health indicator was no longer a
  real connection.
- **Implementation:** `ObsidianLocalRestConfiguration` now has an enabled,
  read-only fallback to the fixed installed-plugin settings path below the
  mounted Vault. It reads only the local service token, secure-server flag, and
  port; it never scans notes, lists Vault files, imports plugin code, writes to
  Obsidian, or includes credentials in Artifact Graph, Vault projections, logs,
  or REST responses.
- **Runtime proof:** after a Docker rebuild and API recreation, the authorized
  project workspace reported `connected`, `authenticated_manifest_verified`,
  `docker_host_tls`, and plugin version `5.0.2`. A separate `docker exec`
  process with `OBSIDIAN_LOCAL_REST_URL` and
  `OBSIDIAN_LOCAL_REST_API_KEY` explicitly blank returned the same connected
  result with `configuration_source=plugin_config`.
- **Regression proof:**
  `python -m pytest tests/knowledge/test_obsidian_local_rest.py tests/api/test_knowledge_workspace_api.py -q`
  passed `33`; `npx vitest run src/components/KnowledgeWorkspace.test.tsx`
  passed `14`.
- **Browser evidence boundary:** the in-app browser URL policy blocked a local
  Studio navigation after the prior Vite address expired. This is not recorded
  as browser acceptance. The Vite server was restored; API and build evidence
  remain authoritative for this worklog entry.

## PBOS Truth State

- The configured project has a connected Vault, trusted plugin bridge routes,
  Horizon captures, governed Wiki context, a contextual plan, and one
  reviewable but unverified execution outcome.
- It does **not** yet have a declared role, industry, or organization stage,
  nor three comparable accepted outcomes. Therefore it has zero verified
  Capabilities and zero promoted Strategy Genomes. This is the intended
  evidence gate, not a missing persistence path.
- The next human inputs are narrow and non-technical: declare the three
  profile fields in Personal Growth Cockpit, then review real project results
  with evidence, score, and reflection. No code path may infer or auto-accept
  those personal facts.

## Rollback

- Revert the Local REST fallback commit to restore environment-only Local REST
  configuration. Existing Vault sync, PBOS artifacts, and plugin bridge routes
  are additive and unchanged.

## 2026-08-01 Live Connection And Studio Project-Selection Closure

- **Observed fault:** the installed Obsidian Local REST plugin and the project
  `.env` were configured, but a stale process-level
  `OBSIDIAN_LOCAL_REST_ENABLED=false` won Compose interpolation. The API
  correctly returned `unconfigured`; it did not falsely claim a connection.
- **Remediation and runtime proof:** recreated only `bsc-backend` with the
  intended enabled setting, then made the user-level setting consistent for
  future shells. The live workspace for `proj_b8a285642094` now reports
  `connected`, `authenticated_manifest_verified`, `docker_host_tls`, plugin
  version `5.0.2`, and `runtime_env` configuration source. `/ready` returned
  `200` with healthy database and Redis dependencies. No note body, plugin
  code, or credential was read into BSC artifacts, logs, or responses.
- **Studio usability fix:** a new Studio session formerly began as
  `PROJECT: UNSCOPED`, even though two authorized knowledge projects existed.
  The rail now discovers the authorized catalog after runtime access is
  available and presents project names in a select control. A selection clears
  stale context/output state before it opens Knowledge, Growth, DBOS, or PBOS.
  React Strict Mode replay is covered so discovery cannot remain indefinitely
  in `checking projects`.
- **Browser evidence:** real Microsoft Edge acceptance against the local
  Vite Studio selected `Personal Knowledge Intelligence`
  (`proj_b8a285642094`) and opened its Personal Growth Cockpit. The rendered
  personal-loop activation copy is legible. Desktop `1440x980` and mobile
  `390x844` each had equal document client/scroll widths and zero console
  errors.
- **Regression evidence:**
  `pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q`
  passed `78`; Artifact Graph/runtime/wiki/growth/Local REST/workspace API
  coverage passed `140` with one Windows-specific skip; `npm run test:frontend`
  passed `205`; `npm run check`, `npm run build`, and `docker compose config
  --quiet` passed. The production build retains only the non-blocking ECharts
  chunk-size advisory.
- **Still intentionally user-owned:** the current project has one reviewable
  unverified outcome, zero accepted learning-eligible outcomes, zero verified
  Capabilities, and zero Strategy Genomes. Role, industry, and organization
  stage must be declared by the owner, then three comparable receipt-backed,
  reflected, explicitly accepted AI-project deliveries are required before
  PBOS may promote personal methods. Obsidian bridge folders remain
  `awaiting_export`/`awaiting_output` until installed plugins create real
  files; GitHub and Feishu remain `awaiting_authorization`.

## 2026-08-01 Owner-Authorized PBOS First-Loop Activation

- **Declared personal model:** with the owner's explicit authorization, the
  active project now has a declared `PersonalProfile` for a personal AI
  product and knowledge-system builder in the AI Agent, knowledge-engineering,
  and personal-productivity domain. The declared stage is personal project
  validation and product delivery. These fields are marked as owner-declared
  planning context, never inferred capability evidence.
- **Real Mission and plan:** created Mission `art_29b5a8e637fb`, a bounded
  first-loop delivery that may only read governed Vault/Wiki context and
  create a reviewable action-evidence card. Its Diagnosis
  `art_6de5aedb6273` has coverage `1.0`, no missing context fields, and a
  passed routing evaluation. The latest immutable Personal Execution Plan
  `art_2f590ef620e0` used DeepSeek `deepseek-v4-flash` in `llm_contextual`
  mode with 12 governed references. The plan remains `context_grounded`, not
  `personalized`, because it has not earned reusable personal evidence.
- **Real receipt loop:** execution `art_9fe97c4566a8` captured five
  server-verified workspace receipts and a three-minute reflection. Outcome
  `art_42228bf60845` records the observed configuration result and remains
  `unverified`; feedback `art_ebd452a0b116` is a direction for the next plan,
  not a verified pattern. No external capability, connector, source mutation,
  publication, or outcome acceptance occurred.
- **Product repair:** explicit `comparison_context` is now canonical instead
  of being concatenated with profile fields. This prevents identical future
  deliveries from splitting across Strategy Genome evidence cohorts. Chinese
  Missions also localize the full phase contract, including title, rationale,
  inputs, outputs, checks, and decision point, when a model returns English
  display text. The live API response was checked from UTF-8 bytes: all three
  latest phase contracts contain Chinese in every user-facing field.
- **Verification:**
  `python -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q`
  passed `79`. Rebuilt only the `bsc-backend` container and confirmed its
  health. Authenticated live API readback confirmed `llm_contextual`, DeepSeek,
  12 context references, the canonical comparison context, the five receipts,
  and `learning_evidence_required` rather than a fabricated personal method.
- **Browser boundary:** the supported browser-control runtime failed before
  binding to the existing Studio tab with a local kernel-assets path error.
  This entry does not claim a new browser acceptance run. The prior Studio
  desktop/mobile acceptance remains valid for the unchanged layout; the
  latest data presentation was verified through API and component regression
  tests. Rollback is limited to the comparison-context/localization source
  change and a rebuild; immutable Mission, plan, receipt, pending Outcome,
  and feedback records stay auditable.

## 2026-08-01 Execution Attribution And Personal-Learning Gate

- **Observed gap:** `WorkExecutionRecordArtifact` recorded receipts and
  reflection but did not distinguish owner work from agent work. That allowed
  a technically accepted, agent-only delivery to satisfy the former evolution
  predicate and risk an incorrect personal Capability or Strategy Genome
  claim.
- **Implemented contract:** every new execution now carries
  `execution_attribution` (`owner`, `mixed`, `agent`, or `unattributed`) and
  an optional bounded `owner_contribution`. Historical records deserialize as
  `unattributed`, retain their full audit trail, and are non-promotable until
  an owner performs the one-time explicit attribution review. `mixed` work requires a
  recorded personal contribution. `agent` and `unattributed` work can be
  reviewed as delivery evidence but cannot become personal-learning evidence.
- **Surface integration:** REST capture/manual endpoints, the BSC workspace
  capture path, L3 Vault projections, Cockpit execution summaries, and the
  three-minute reflection form now carry the same contract. The Cockpit asks
  the owner to state who performed the work and explains that agent-only
  receipts remain auditable rather than becoming a personal skill claim.
- **Live deployment and proof:** rebuilt only `bsc-backend` and confirmed
  `healthy`; `/ready` returned `ok` with PostgreSQL and Redis healthy. The
  authenticated live Cockpit for `proj_b8a285642094` returned two historic
  executions, both `unattributed`, zero accepted outcomes, zero
  learning-eligible outcomes, zero Capabilities, zero Strategy Genomes, and
  `learning_evidence_required`. This is the required safe downgrade of
  pre-attribution records, not a data-loss event.
- **Regression evidence:**
  `python -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q`
  passed `83`; the independent Artifact/Runtime/Wiki/Growth suite passed
  `103` with `1 skipped`; `npm run test:frontend` passed `206`; `npm run
  check` passed. New tests prove three agent-only accepted deliveries cannot
  promote a Capability, mixed work without a stated owner contribution cannot
  enter evolution, and a legacy unattributed record remains auditable but
  non-promotable.
- **Browser boundary and rollback:** supported in-app browser initialization
  again failed before binding with a local kernel-assets path error, so no new
  screenshot claim is made for this data-only UI update. Rollback is to revert
  the attribution fields, service gate, API/UI payloads, and tests, then
  rebuild `bsc-backend`; existing Artifact and Vault records remain intact.

## 2026-08-01 Legacy Attribution Review Closure

- **Implemented review path:** an owner can now review a legacy
  `unattributed` `WorkExecutionRecord` once through
  `POST /api/pbos/projects/{project_id}/executions/{execution_id}/attribution-review`.
  The request requires `owner`, `mixed`, or `agent` plus a non-empty review
  note; `mixed` additionally requires a bounded personal-contribution
  statement. The original action and receipt data is not replaced. The
  artifact stores timestamp, note, prior attribution, new attribution, and
  source `explicit_owner_attribution_review` in its audit history.
- **No attribution rewrite:** a second review is rejected. The endpoint does
  not accept an Outcome, assign a score, or create an Experience, Capability,
  or Strategy Genome. Existing outcome/receipt/reflection gates still apply.
- **Cockpit integration:** `EXECUTION ATTRIBUTION REVIEW` lists only legacy
  records, offers owner/mixed/agent choices, requires a review note, and asks
  for a personal contribution only for mixed work. It disappears after the
  audited update. New three-minute reflections keep their explicit attribution
  at creation time.
- **Verification and deployment:** focused PBOS/API/integration tests passed
  `50`; Cockpit tests passed `18`; TypeScript check passed. Rebuilt
  `bsc-backend`, confirmed it healthy, and read the live Cockpit. Both current
  legacy execution records report `unattributed` with
  `attribution_reviewable=true`; no review was submitted on the owner's
  behalf. The live learning state remains zero eligible outcomes, zero
  Capabilities, and zero Strategy Genomes.
- **Final verification surface:**
  `python -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q`
  passed `85`; the Artifact/Runtime/Wiki/Growth suite passed `103` with `1`
  existing platform skip; `npm run test:frontend` passed `207`; `npm run
  check`, `npm run build`, and `docker compose config --quiet` passed. The
  production build has only the pre-existing ECharts chunk-size advisory.

## 2026-08-01 Obsidian Local REST Runtime Repair

- **Observed configuration fault:** the host `.env` and the installed
  `obsidian-local-rest-api` plugin both had Local REST enabled, with the
  plugin listening on its configured local TLS port. The running
  `bsc-backend` container nevertheless received
  `OBSIDIAN_LOCAL_REST_ENABLED=false` because a stale process-level
  environment variable won Docker Compose interpolation. The workspace
  correctly reported `unconfigured/disabled`; no note content was read or
  written during diagnosis.
- **Repair:** removed only the stale process override for the Compose
  invocation and recreated `bsc-backend` without dependencies. The persisted
  user-level setting remains enabled, the container received the intended
  value, and no Vault, Artifact Graph, source, output, or credential was
  modified.
- **Live evidence:** the protected workspace readback for
  `proj_b8a285642094` reports Vault sync `completed` with `39` active
  sources and Local REST `connected`,
  `authenticated_manifest_verified`, `docker_host_tls`, runtime-env
  configuration, and plugin version `5.0.2`. `/ready` reports both
  PostgreSQL and Redis healthy.
- **Plugin boundary audit:** Clipper, Xiaohongshu Importer, and Zotero
  Integration destination settings match their trusted bridge declarations;
  Copilot and Real Claudian output routes are prepared. Their declared
  folders currently contain zero normal plugin exports or reviewed outputs,
  so all five remain truthfully `awaiting_export` or `awaiting_output`.
  The existing evidence inventory is external intelligence (`16` Horizon
  signals, `12` primary-web captures, `10` RSS items, and `1` manual upload),
  not personal plugin-derived evidence.
- **Clipper interaction check:** invoking the installed Clipper's empty
  `obsidian://obsidian-clipper` protocol action did not create a file in the
  configured project bridge. The published Clipper documentation confirms
  that a normal capture is initiated by its browser extension or bookmarklet
  from a real web highlight, not by an empty local protocol call. This result
  is recorded as a non-capture rather than being converted into synthetic
  knowledge. A normal browser capture remains the first required external
  action for this bridge.
- **Regression and rollback:**
  `python -m pytest tests/knowledge/test_obsidian_local_rest.py tests/api/test_knowledge_workspace_api.py -q`
  passed `37`; focused Knowledge Workspace frontend tests passed `24`; and
  `docker compose config --quiet` passed. Rollback is to recreate only
  `bsc-backend` with Local REST disabled. Filesystem Vault sync remains
  independent of this optional read-only manifest probe.

## 2026-08-01 PBOS Worker Context Parity Repair

- **Observed production failure:** authenticated API reads for the active
  project returned a context-grounded plan with twelve governed references,
  while the Worker saw no plan and wrote a generic `capture_required` daily
  action. The first real `pbos.daily_review` task completed successfully but
  exposed this substantive context-loss defect.
- **Root cause:** the API configured `DBOS_DATA_ROOT=/data/dbos`; the Worker
  mounted `bsc-data:/data` but had no `DBOS_DATA_ROOT`, so it read an
  image-local empty Artifact Graph. This made asynchronous reports diverge
  from API and Studio state.
- **Repair:** added `DBOS_DATA_ROOT=/data/dbos` to `celery-worker` and a
  Compose regression assertion requiring API and Worker to share the durable
  ledger mount. Recreated only the Worker and verified it reports the intended
  runtime value and responds to Celery `ping`.
- **Real queue proof:** queued `pbos.daily_review` refreshed
  `pbos/reviews/daily/2026-07-31/daily-action.md`; queued
  `pbos.weekly_report` refreshed
  `distillations/每周蒸馏/2026-W31/pbos/personal-growth.md`. Both are
  conflict-safe managed files with integrity markers, an actionable current
  plan, the personal-learning gate, and `12` current Vault/Wiki reference
  identifiers. No Outcome was accepted or promoted by either task.
- **Final regression:** PBOS REST/MCP/integration passed `85`; Artifact,
  Runtime, Wiki, and growth coverage passed `103` with `1` existing skip;
  frontend passed `207`; TypeScript check, production build, and Compose
  configuration passed. Browser-control initialization remains unavailable
  because of the local Codex kernel-assets error, so no new screenshot claim
  is made. Rollback is to remove the Worker `DBOS_DATA_ROOT` setting, recreate
  the Worker, and leave all durable report and Artifact history intact.

## 2026-08-01 Active Knowledge-Feed And Vault-Lane Audit

- **External evidence is active:** the protected workspace reports Horizon
  enabled with an available run store. Its latest completed import accepted
  and created `7` filtered signals; the current project has `16` durable
  Horizon sources among `39` active governed sources. This is a real imported
  run, not a configured-but-empty connector.
- **Knowledge distillation is active:** the latest completed weekly growth run
  used `141` bounded lineage, source, page, output, and profile inputs through
  the configured DeepSeek generation path. It wrote the five managed weekly
  artifacts under `distillations/每周蒸馏/2026-W31/`; the separate PBOS weekly
  review now consumes the same active plan context without replacing those
  five knowledge outputs.
- **Personal-memory lanes are ready:** `00_Inbox`, `01_Sources`,
  `02_Assets`, `03_Projects/active`, `04_Outputs`, `06_Skills`, `methods`,
  and `outputs` all exist in the active Vault. Project context files placed by
  the owner in `03_Projects/active` are a supported governed input path, so
  personal work capture does not depend on a third-party plugin. Those lanes
  are currently empty; that is reported as missing personal evidence rather
  than filled with generated content.

## 2026-08-01 PBOS Shanghai-Time Direct-Task Repair

- **Observed boundary:** direct `pbos.daily_review` and
  `pbos.monthly_review` compatibility tasks derived their output period from
  the Worker container's UTC calendar. A manual job near midnight in
  `Asia/Shanghai` could therefore file the report under the prior local date,
  despite the persisted PBOS schedule contract using Shanghai time.
- **Repair:** added `_shanghai_date()` in `app/tasks/pbos_tasks.py` and made
  both direct task entry points use it. Scheduled runs remain driven by their
  already persisted local period; this repair aligns manual and scheduled
  semantics without changing report content, authorization, or promotion.
- **Regression:** a new cross-day test proves `2026-07-31 16:30 UTC` maps to
  `2026-08-01` in Shanghai. The scheduler suite passed `6`; the complete
  PBOS REST/MCP/integration suite passed `86`; TypeScript check passed.
- **Live queue proof:** rebuilt only `celery-worker`, confirmed `ping`, then
  queued real daily and monthly tasks through `bsc_docker_knowledge`. They
  produced `pbos/reviews/daily/2026-08-01/daily-action.md` and
  `pbos/reviews/monthly/2026-08/capability-report.md`, respectively. Both
  reports have a managed integrity marker and `12` current Vault/Wiki context
  references. Neither task accepted an Outcome or changed any personal
  learning state.

## 2026-08-01 UTF-8 Profile Repair And First Technical PBOS Loop

- **Observed input-quality defect:** an earlier ad-hoc Windows PowerShell API
  request encoded Chinese JSON through its legacy request-body path. Its
  recorded Profile and Mission fields contained literal question marks, which
  prevented the personal compiler from reading the declared Chinese role and
  constraints. This was a client encoding defect in the live activation
  procedure, not a permission to reinterpret or delete its historical
  Artifacts.
- **Repair and data authority:** created the owner-declared planning input
  `D:/bsc/bsc/projects/proj_b8a285642094/03_Projects/active/PBOS-v1-personal-delivery-brief.md`.
  It explicitly declares that it is a planning context, not a delivery,
  quality score, or capability claim. A UTF-8 `HttpClient` request then wrote
  Profile `art_57b589d3bb7b`; byte-level readback confirmed the Chinese role
  string is UTF-8 rather than question marks. The older artifacts remain
  audit history.
- **Real contextual compilation:** created the unconfirmed Mission
  `art_055276148486`, diagnosed it, and compiled plan `art_54959f6b2f08`.
  Its compiler metadata is `llm_contextual` with provider `deepseek`, no final
  LLM failure, three bounded phases, twelve governed context references, and
  an explicit citation to the owner Brief. It contains reflection and
  side-effect contracts, has no visible encoding loss, and remains
  `ready_for_confirmation`; no external capability was granted or run.
- **Actual technical evidence loop:**
  `python -m pytest tests/pbos/test_pbos_contextual_compiler.py tests/pbos/test_pbos_service.py -q`
  passed `67`. The live PBOS API captured those reviewed code/test paths as
  agent-attributed execution `art_94d464e16716`, with five server-verified
  receipts and a recorded reflection. Its outcome `art_f36b0dd50df1` is
  deliberately `unverified`, has no quality score, and is ineligible for
  evolution because it is agent work. It did not create a Capability or
  Strategy Genome claim.
- **Live authorization proof:** a real request to execute
  `knowledge_wiki_compile` against the unconfirmed Mission returned HTTP
  `409`. The PBOS execution count was one before and one after the request;
  no external execution or personal-learning transition occurred.
- **Front-end release ledger closure:** the existing workspace mount and API
  contract were completed by `ReleaseEvidenceLedger`. Its focused permission
  tests passed `3`, including reader read-only behavior, project-admin
  observation recording, and administrator-only verification requiring a
  timestamp, durable IDs, and detail code. The ledger remains metadata-only.
- **Final verification:**
  `python -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q`
  passed `86`; Artifact/DBOS/Wiki/growth coverage passed `103` with `1`
  designed skip; `npm run test:frontend` passed `24` suites and `210` tests;
  `npm run check`, `npm run build`, and `docker compose config --quiet`
  passed. The build has the existing ECharts chunk-size advisory only.
- **Post-repair schedule proof:** after the Worker completed a normal restart,
  real Celery task `d31563c7-360e-47ea-8767-41ff5b2ffcde` ran
  `pbos.daily_review` and wrote
  `pbos/reviews/daily/2026-08-01/daily-action.md`. Its current action is
  `read the owner brief and freeze acceptance criteria`; it cites twelve governed references including
  the new owner Brief. The managed SHA-256 footer was recomputed and verified,
  the report says no verified capability update exists, and the agent outcome
  remains explicitly ineligible for personal learning.
- **Remaining truth boundary:** the active project still has zero accepted,
  owner-attributed outcomes, zero verified Capabilities, and zero active
  Strategy Genomes. The system is now ready to learn from real personal work,
  but no agent-run technical test is presented as the owner's capability.

## 2026-08-01 Scoped Delivery Commit

- Committed the audited PBOS/knowledge ecosystem implementation as
  `9928271` (`feat(pbos): deliver evidence-grounded personal operating system`).
  The commit contains `45` explicitly selected implementation, UI, test, and
  evidence-document files; no runtime key or Vault-authored content was
  included.
- The subsequent integration hardening increment prefers a native async Agent
  entrypoint when one is available, while retaining thread isolation for
  synchronous Agents. Its regression covers both entrypoint selection and the
  SOP/Risk parallel latency gate; it is intentionally kept separate from the
  PBOS feature commit for reviewability.

## 2026-08-01 Copilot Output Bridge Alignment

- The operator selected Copilot as the active Obsidian AI path and explicitly
  excluded Claudian. Removed `realclaudian` from Obsidian's enabled-plugin
  list and replaced the project bridge manifest through the authorized
  workspace API. The installed Claudian package was left untouched; BSC now
  governs only Clipper, Xiaohongshu Importer, Zotero Integration, and Copilot.
- Corrected Copilot's own `defaultSaveFolder` from the unmanaged global
  `copilot/copilot-conversations` location to
  `projects/proj_b8a285642094/04_Outputs/copilot`. No model credential was
  copied into Obsidian, BSC Artifacts, logs, or this worklog.
- Added a bounded, read-only `defaultSaveFolder` probe to
  `ObsidianPluginManifest`. A bridge now reports `configured` only when the
  public Copilot destination matches the declared project output route; a
  different destination reports `mismatch`. The probe reads neither saved
  conversations nor plugin source code.
- Test-first evidence: the new Copilot route test failed before the probe with
  `declared_only`, then passed after the implementation. The focused test pair
  passed `2`; the sync, workspace API, and Celery growth regression passed
  `68 passed, 1 skipped`.
- Runtime evidence: rebuilt and recreated only `bsc-backend`; PostgreSQL,
  Redis, n8n, Celery Worker, and Celery Beat remained running. An authorized
  live workspace read now reports Copilot as `trusted`, `path_status=ready`,
  `runtime_configuration=configured`, and `awaiting_output` with zero output
  records. This is the correct pre-first-output state, not a synchronization
  claim.
- Remaining user-owned boundary: Copilot has no configured provider credential
  and no saved, reviewed Markdown output yet. It cannot be marked captured or
  registered until an actual Copilot conversation is saved into the configured
  folder and a governed growth Sync records it. Rollback is to restore the
  prior Copilot folder and re-register that explicit bridge; doing so would
  intentionally return the route to `mismatch` against PBOS's output contract.

## 2026-08-01 Runtime Redeploy And Release-Evidence Recheck

- Rebuilt the API, Worker, and Beat images from the audited follow-up change.
  Docker Compose encountered a container-name replacement race after images
  had built successfully. The recovery removed only the four verified,
  project-labelled, stateless API/Worker/Beat replacement containers and then
  recreated Worker and Beat through Compose. PostgreSQL, Redis, n8n, queues,
  and persistent volumes remained running and intact.
- The final Compose state has one healthy API, one Worker, and one Beat. The
  Worker registers the knowledge and PBOS task families and Beat starts its
  persistent scheduler normally.
- An authorized metadata-only workspace read from inside the deployed API
  reports Obsidian Local REST `connected` with
  `authenticated_manifest_verified`, `docker_host_tls`, plugin-config source,
  and plugin version `5.0.2` for both authorized projects. No token, endpoint,
  note body, output body, or plugin source was printed or retained.
- Project isolation remains visible in the deployed ledger: project index 1
  has no recorded proof and nine missing E1 categories; project index 2 alone
  has reviewed `o3_real_plugin_exports` at revision `2`, with a real proof
  class and three durable reference identifiers, leaving eight categories
  missing. Both projects honestly remain
  `implemented_with_operational_proof_pending`.
- Final regression on this deployed increment: `1638 passed, 14 skipped` in
  `308.03s` for the Python suite; `24` frontend files and `213` tests passed;
  `npm run build` passed; lint completed with `0` errors and `214` existing
  warnings. The existing ECharts bundle-size advisory remains a follow-up, not
  a false success or release decision.
