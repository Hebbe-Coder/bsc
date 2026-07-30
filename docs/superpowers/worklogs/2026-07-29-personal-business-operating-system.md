# PBOS v1.0 Worklog

## 2026-07-29 Planning

- Defined PBOS as a personal AI-project delivery loop, not a template SOP product.
- Confirmed existing DBOS, Artifact Graph, Growth, Obsidian, Celery, MCP, React Flow, and ECharts foundations.
- Known boundary: GitHub and Feishu remain awaiting authorization until runtime credentials are supplied.

## Implementation Log

| Area | Status | Evidence | Deviation / rollback |
| --- | --- | --- | --- |
| Documentation | completed | PRD, index, eight plan stubs | Delete PBOS-only documents to revert documentation |
| Contracts | completed | `tests/pbos/test_pbos_service.py` 3 passed; Artifact/DBOS regression 21 passed | Remove PBOS ArtifactType entries and service |
| Capture and projection | completed | Local read-only Git/file receipt and conflict-safe L3 projection tests passed; default Vault received profile, plan, execution, outcome and feedback files | Remove `pbos/` managed projections and PBOS ledger files to revert |
| Compiler and evolution | completed | Evidence-poor plan, Mission/profile-aware compilation, three-record promotion and capability evidence tests passed | Current v1 uses deterministic evidence composition; model enhancement remains optional |
| API, MCP, automation, cockpit | completed | `/api/pbos`, MCP Cockpit/report tools, Celery task registration, weekly report, and Growth Cockpit production build verified | Connector credentials remain awaiting authorization by design |
| Release verification | completed | 110 targeted PBOS/DBOS/MCP/knowledge tests passed, 1 existing skip; Docker, authenticated HTTP/Vault loop, production build, desktop and 390px browser checks passed | Browser uses locally installed Edge because Playwright Chromium download timed out |

## Verification

- `./.venv/Scripts/python.exe -m pytest tests/pbos/test_pbos_service.py -q`: 3 passed.
- `./.venv/Scripts/python.exe -m pytest tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py -q`: 21 passed, one existing Starlette/httpx deprecation warning.
- `npm run check`: passed.
- `npm run build`: passed; PBOS Cockpit emitted as a lazy production chunk.
- Authenticated HTTP loop on `127.0.0.1:8012`: profile -> DBOS Mission -> capture-local -> outcome -> feedback -> weekly report completed and projected to `D:\bsc\bsc\projects\default`.
- `docker compose config`: passed.
- `./.venv/Scripts/python.exe -m pytest tests/pbos/test_pbos_service.py tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py tests/test_mcp_http.py -q`: 30 passed.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_sync.py tests/knowledge/test_growth_distillation.py tests/mcp/test_wiki_http_contract.py -q`: 76 passed, 1 skipped.

## 2026-07-29 Feedback Context Closure

- Feedback can now be recorded only against an existing, project-scoped PBOS outcome.
- The next PBOS plan carries bounded `feedback_refs`, graph parent edges, a clearly labelled unverified-feedback rationale, and an explicit execution check for each feedback statement.
- The Personal Growth Cockpit exposes the same bounded feedback set and renders the outcome -> feedback -> next-plan loop. Feedback does not promote an experience or capability until outcome/evidence gates corroborate it.
- Weekly PBOS reports are verified to use the managed Obsidian path `distillations/每周蒸馏/<week>/pbos/`.
- Verification: `./.venv/Scripts/python.exe -m pytest tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py -q` passed 12 tests; `npm run test:frontend` passed 155 tests; `npm run check` and `npm run build` passed. The only build note is the existing large main-entry chunk warning; it does not block the PBOS feedback closure.

## 2026-07-29 Live Runtime And Visual Proof

- Restarted the local BSC API on `127.0.0.1:8012` so validation runs the current code rather than an earlier non-reloading process.
- Corrected the two local Vite proxy targets from the stale `8002` instance to the active `8012` instance. `127.0.0.1:5180` now returns the authenticated current-project PBOS payload through the proxy without exposing the local key to the browser.
- Executed the live default-project loop using the existing outcome and feedback. New plan `art_e437d5397942` contains feedback parent `art_fcb67655fc1a`, one `feedback_refs` entry, an advisory rationale, and a generated feedback action. Its conflict-safe Obsidian projection was written to `pbos/plans/art_e437d5397942.md`.
- Browser acceptance at desktop and 390px mobile verified the same real payload: accepted outcome count, feedback count, quality trend, explicit `Mission -> Plan -> Outcome -> Feedback -> Next plan` lineage, capability empty state, and feedback text. The mobile graph was revised after real screenshot inspection to remove clipping and node overlap.
- Final targeted suite: 110 passed, 1 skipped. Browser checks on `http://127.0.0.1:5190` displayed the real accepted outcome, no API error, and no desktop/390px horizontal overflow. Screenshots: `pbos-desktop-evidence.png`, `pbos-mobile-viewport.png`.

## 2026-07-29 Durable Automation Closure

- Closed the remaining gap between registered PBOS run types and durable execution. `pbos_daily`, `pbos_weekly`, and `pbos_monthly` now claim idempotent `knowledge_runs`, execute through `knowledge.execute`, and persist a report output reference and terminal status.
- Added PBOS cadence defaults at 17:00 daily, 17:30 every Friday, and 17:00 on the first day of each month in `Asia/Shanghai`. The default-schedule API is `/api/pbos/projects/{project_id}/schedules/defaults`; it creates disabled intent rather than claiming execution when Celery is unavailable.
- Added separate Vault projections: daily action at `pbos/reviews/daily/<date>/daily-action.md`, monthly capability report at `pbos/reviews/monthly/<month>/capability-report.md`, and weekly review at `distillations/每周蒸馏/<week>/pbos/personal-growth.md`. Existing user edits remain conflict-safe and are never overwritten.
- Verification: `tests/pbos/test_pbos_scheduler.py`, `tests/pbos/test_pbos_service.py`, and `tests/api/test_pbos_api.py` passed 15 tests. Full focused regression passed 112 tests with 1 existing skip; frontend suite passed 155 tests; `docker compose config` passed.
- Deployment evidence: rebuilt and restarted API, Celery worker, and Celery beat. Installed the three enabled PBOS schedules for project `default`. A real queued daily PBOS job was consumed by the worker and finished `completed`, with the auditable Vault output reference `pbos/reviews/daily/2026-07-29/daily-action.md`.
- Rollback: disable or remove only the three `pbos_*` schedule records, then remove PBOS periodic report files. This does not alter existing weekly-distillation schedules or their five-document output contract.

## 2026-07-29 Docker Ledger Convergence And Browser Reacceptance

- Found that the temporary host API and Docker API were reading different
  Artifact Graph ledgers. Added the tested PBOS-only migration bundle tool in
  `app/pbos/migration.py` and `scripts/migrate_pbos_artifacts.py`; it exports
  only PBOS artifacts plus parent closure, verifies a SHA-256 bundle digest,
  validates parents and conflicts before import, and skips an already imported
  bundle idempotently.
- Exported seven default-project PBOS assets from the retired host ledger,
  created a Docker-ledger backup under the local temporary directory, then
  dry-ran and imported the bundle into the running Docker ledger. A repeated
  dry run skipped all seven assets, proving the migration is idempotent. The
  temporary host API was stopped and Vite now points only to Docker API port
  `8002`, preventing future split-ledger reads.
- Verified through `http://127.0.0.1:5180` rather than a direct database read:
  the Personal Growth Cockpit returned one accepted Outcome and one feedback
  record from the Docker ledger, and its desktop rendering showed the real
  evidence loop. `tests/pbos/test_pbos_migration.py -q` passed with 2 tests.
- Docker API, PostgreSQL, Redis, Celery Worker, Celery Beat, and n8n are
  running; `/ready` returned `200`. The Vite proxy served the migrated PBOS
  payload without exposing the local runtime key to the browser.

## 2026-07-29 Runtime Truth Reconciliation

- Corrected a real runtime defect: PBOS selected the latest Profile and Plan
  by `created_at`, so an older artifact written with a different local clock
  could hide the latest Docker-ledger state. PBOS now selects its current
  state by the last persisted `updated_at`; a regression test covers the
  clock-skew case.
- Tightened the Obsidian context pack. It now skips Excalidraw exports and
  front matter, limits itself to eight bounded text documents, and prioritizes
  active project context, methods, and published Wiki knowledge before old
  outputs. Raw sources and `pbos/` projections remain excluded.
- Ran a new Docker-ledger Mission `art_40aaffb724d4` without confirmation or
  external side effects. A successful DeepSeek plan `art_f9585ff7c450` proved
  the deployed `llm_contextual` path. The final current plan
  `art_ffc8b3b7085b` cites eight governed Vault paths and includes the declared
  Personal Profile parent, but is explicitly `contextual_deterministic` because
  the immediately preceding provider response was structurally invalid.
  Earlier transient model failures (`response_payload_invalid`,
  `response_truncated`, and one TLS timeout) likewise produced clear fallback
  plans rather than fabricated model output.
- Recorded one real validation execution `art_d8be15ecfd84` with focused test,
  Docker deployment, and authenticated Cockpit readback receipts. Its outcome
  `art_420107532f71` is deliberately `unverified`; it has not promoted an
  Experience, Strategy Genome, or Capability. The live Cockpit shows the
  latest plan, two outcomes, two feedback records, and zero verified
  capabilities.
- Final source verification: the PBOS/Artifact/knowledge regression command
  passed `120 passed, 1 skipped`; `npm run test:frontend` passed `155` tests;
  `npm run check`, `npm run build`, and `docker compose config` passed. The
  Vite build retains its non-blocking large ECharts chunk warning.
- Remaining boundary: GitHub and Feishu still report
  `awaiting_authorization`. No remote content, connector result, or personal
  capability is represented as synchronized or verified.

## 2026-07-29 Final Acceptance Reconciliation

- Corrected the Cockpit's evidence wording. When no capability has verified
  execution evidence, the Today panel now states that its recommendation uses
  declared personal context and governed Vault evidence; it no longer implies
  that a capability or personal asset has been established.
- Added the missing PBOS MCP HTTP contract and REST end-to-end tests referenced
  by the PBOS release plan. The MCP test confirms tool discovery, scoped read
  access, and cross-project denial. The REST loop covers profile -> governed
  Vault context -> plan -> execution receipt -> unverified outcome -> feedback
  -> next plan -> non-promotion.
- Verification on the final source state:
  `./.venv/Scripts/python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py`
  passed 25 tests; `npm run test:frontend` passed 157 tests; `npm run check`
  and `npm run build` passed. The only build observation remains the existing
  non-blocking vendor ECharts chunk-size warning.
- Docker services remain healthy on port 8002. Direct unauthenticated PBOS API
  reads return `authentication required` as intended for the production
  container, rather than bypassing the configured project authorization.

## 2026-07-30 Periodic Task Route Correction

- Found and fixed a real divergence in the legacy Celery convenience tasks:
  `pbos.daily_review` and `pbos.monthly_review` incorrectly delegated to the
  weekly report writer and therefore targeted the weekly-distillation tree.
  All three task entry points now call the same explicit periodic-report
  function with their own run type. The durable `knowledge_runs` scheduler
  path was already typed correctly and remains the authoritative ledger path.
- Added a regression test that freezes the period and proves daily and monthly
  task invocations write only `pbos/reviews/daily/<date>/daily-action.md` and
  `pbos/reviews/monthly/<month>/capability-report.md`; it also proves the daily
  call does not create a weekly-distillation path.
- Verification: the new test first failed with the incorrect
  `distillations/每周蒸馏/daily-<date>/pbos/personal-growth.md` path. After the
  fix, `tests/pbos/test_pbos_scheduler.py` passed 4 tests and the PBOS
  service/API/MCP/integration suite passed 19 tests.
- Rebuilt the live Celery Worker from the current workspace and dispatched one
  isolated `pbos.daily_review` task. The worker completed it successfully and
  wrote the expected managed daily-action projection. The default project's
  three persistent PBOS schedules remain enabled in `Asia/Shanghai`, and its
  existing daily `knowledge_runs` row remains completed with an auditable
  output reference. This check did not modify a user-authored Vault file.

## 2026-07-30 Plan Grounding Visibility

- Full frontend regression found that the Cockpit described governed Vault
  context in its next-action text but did not render the plan's actual context
  references. Added a responsive, read-only `PLAN GROUNDING` panel that shows
  bounded selected references, weekly handoff count, and feedback-input count.
  It explicitly labels these as planning inputs and never turns them into a
  verified capability or personal asset claim.
- Verification: the focused Cockpit suite passed after the addition, as did
  `npm run check`. Full backend collection (1501 tests), full frontend suite,
  `docker compose config`, and `git diff --check` completed successfully.
- Browser screenshot reacceptance is not claimed by this entry: the current
  browser-control session has no active Studio tab bound to it. The component
  has focused DOM coverage and production build coverage; a new active Studio
  tab is still required for a fresh desktop/mobile screenshot audit.

## 2026-07-30 Cockpit Usability And Access Recovery

- Replaced the PBOS cockpit's detached light card layout with a compact Studio-aligned
  evidence desk. The current loop, connector trust state, health ledger, declared
  context, reflection capture, scored outcome trend, and workflow lineage now use a
  single dense operational hierarchy. This is a presentation change only: no Artifact
  Graph, outcome, authorization, or promotion rule was loosened.
- Added an explicit access boundary to the cockpit. With no runtime key it does not
  issue a PBOS request; with a rejected key it reports an actionable Studio access
  state instead of leaking a raw HTTP error. The recovery control closes the cockpit
  and returns focus to the existing runtime-key field in the Studio rail.
- Added frontend regression coverage for missing and rejected access sessions. The
  component suite, all frontend tests, TypeScript check, and production build passed:
  `9` targeted tests; `162` frontend tests; `npm run check`; and `npm run build`.
- Browser acceptance against the authenticated local Studio used the real Docker-ledger
  PBOS payload (1 accepted outcome, 2 feedback inputs, 0 verified capabilities). At
  desktop and 390px mobile the panel loaded without API errors or horizontal overflow;
  the six workflow lineage nodes had non-overlapping bounds. The production Docker
  container rebuild/readback is recorded separately below after deployment.
- Rebuilt and restarted the production `bsc-backend` Docker service. `/ready` returned
  `200` and the live `http://127.0.0.1:8002` Studio rendered the new no-key recovery
  screen. Its `Open runtime access` action closed the cockpit and focused the existing
  `Runtime access key` control, confirming the recovery path works without an API read
  or credential exposure.

## 2026-07-30 Grounded Plan Visualization

- The cockpit now separates planning evidence from personal capability claims.
  Its Plan Grounding panel and React Flow lineage display the actual weekly
  handoff count, governed Vault-reference count, and feedback-input count for
  the active plan rather than a static Mission-to-Plan diagram.
- React Flow now projects `weekly handoff / Vault refs -> current plan ->
  outcomes -> feedback -> next plan`, plus the separate outcome-to-capability
  gate. Input, plan, and feedback nodes have distinct visual states, while a
  missing weekly handoff remains visibly missing rather than being invented.
- Verification: `npm run test:frontend -- --run
  src/components/pbos/PersonalGrowthCockpit.test.tsx`, `npm run check`, and
  `npm run build` passed; the full frontend regression suite also passed with
  `162` tests. A live protected Studio readback showed one weekly handoff,
  eight Vault references, two feedback inputs, and zero promoted capabilities.
  Desktop and 390px mobile checks found no horizontal overflow and no overlap
  across the seven lineage nodes.

## 2026-07-30 DeepSeek Structured Plan Recovery And Fresh Live Loop

- Closed the remaining PBOS model-quality reliability gap without weakening
  evidence rules. The structured client now accepts documented OpenAI-compatible
  text variants, emits safe response-shape diagnostics only, and performs a
  second JSON-mode repair attempt with a bounded larger output budget. It never
  reads, stores, or promotes `reasoning_content`, model response bodies, or
  credentials.
- The PBOS compiler now requests two bounded structured attempts (`2600`, then
  `5200` tokens) and records only safe shape/attempt metadata when it must fall
  back. This differentiates a provider truncation or proxy-shape defect from an
  invented personalized result. New regression coverage proves the repair
  budget, legacy completion shape, safe private-reasoning flag, and persisted
  PBOS fallback diagnostics.
- A fresh isolated Docker/Vault project `pbos-llm-proof-20260730` exercised the
  production REST path: Mission `art_ac151ffde5bc` -> Profile
  `art_33ddfc2ae3ae` -> Diagnosis `art_0a422a628df1` -> DeepSeek Personal Plan
  `art_63e4d5e0b020`. The plan used the explicit solo-AI-product-engineer
  diagnosis and the governed Vault boundary
  `03_Projects/active/ai-delivery-boundary.md`, projected to
  `pbos/plans/art_63e4d5e0b020.md`, and reported `compiler_metadata.mode =
  llm_contextual` with provider `deepseek` / model `deepseek-v4-pro`.
- A second real compiler run after the reflection also returned
  `llm_contextual`: execution `art_7eec706ad538` -> deliberately unverified
  outcome `art_8eb0f911f885` -> feedback `art_66805ff644bd` -> next plan
  `art_98cc5818bff3`. The next plan contains the feedback parent/reference and
  its own Obsidian projection. This proves feedback changes the next planning
  context while preserving the no-promotion gate.
- The technical validation outcome intentionally has no accepted quality score:
  it records the real `125 passed, 1 skipped` PBOS/Artifact/knowledge command,
  production readiness readback, and Vault projection. It is not represented as
  a user-accepted AI-project delivery, Capability, Experience, or Strategy
  Genome.
- Runtime verification: the production container was checked to contain the
  new two-attempt compiler and safe attempt ledger. Docker API, PostgreSQL,
  Redis, worker, and beat were healthy; `docker compose config --quiet` and
  `git diff --check` passed. Frontend verification passed `162` tests; `npm run
  check` and `npm run build` passed (the existing ECharts chunk-size warning
  remains non-blocking).
- Browser acceptance loaded the isolated project's actual Cockpit payload via
  the local authenticated proxy. It displayed one governed Vault reference,
  one unverified outcome, one feedback input, zero active strategies, and zero
  verified capabilities. At 390px, the measured content width was 384px with
  no horizontal overflow, and the screenshot showed no overlapping panel text.
  The browser later rejected a temporary viewport reset, so this entry claims
  the live desktop DOM inspection and the completed mobile screenshot only;
  it does not invent a second desktop screenshot.
- Rollback: remove only the PBOS structured-output repair, diagnostics, and
  related tests to restore the old one-shot behavior. Do not remove the
  isolated Vault project or reclassify its unverified outcome as personal
  evidence. GitHub and Feishu remain `awaiting_authorization`.

## 2026-07-30 Docker Recovery Readback

- Docker Desktop restarted while a discretionary default-project recompilation
  request was starting. The request produced no result and was not counted as
  a plan, execution, or Vault write. After the runtime recovered, production
  API readback confirmed durable recovery rather than an in-memory illusion:
  both `default` and `pbos-llm-proof-20260730` retained their Profile, current
  plan, Outcome, and Feedback artifacts.
- The recovered default project reports two outcomes, two feedback items, zero
  verified capabilities, and a current `llm_contextual` plan. The isolated
  project reports one outcome, one feedback item, zero capabilities, and a
  current `llm_contextual` plan. This verifies project isolation, persistence,
  honest non-promotion, and structured-LLM recovery across a real runtime
  restart.

## 2026-07-30 Governed Wiki Context Wiring

- Identified and closed a source-level integration defect: the PBOS API used a
  plain filesystem scan that could read arbitrary `wiki/` files and did not
  use the task-specific retrieval already available to the knowledge system.
  This made a published page available to the orchestrator without reliably
  grounding PBOS plans.
- Added `PBOSGovernedContextProvider`. It accepts Mission title, intent,
  goal, and constraints as retrieval inputs; obtains only BSC-published Wiki
  pages through `WikiContextProvider`; and records both immutable page
  revision references and processed supporting source hashes in
  `knowledge_context_refs`. Plain Vault context remains a bounded supplement
  for current project work, but `wiki/` is no longer a filesystem-scanned
  bypass around the publication gate.
- Regression coverage proves a physical unpublished Wiki file cannot enter a
  plan while a retrieved published page with a processed source citation does.
  PBOS receives the selected page and its source lineage, not a synthetic
  summary. PBOS contextual compiler, service, API, Wiki publication, source
  triage, task, and recovery regression completed with `150 passed`.
- Deployment boundary: this PBOS context wiring passes local Python
  compilation, TypeScript checking, and production frontend build, but Docker
  Desktop BuildKit stopped emitting progress while rebuilding the updated
  image. Existing Docker API, Worker, Beat, PostgreSQL, Redis, and the already
  deployed Wiki-status repair remain healthy. This entry deliberately does not
  claim that the new PBOS provider has been loaded by the current container;
  it requires a successful image rebuild and the same real Mission-to-plan
  readback before runtime closure.

## 2026-07-30 PBOS Governed Context Deployment Closure

- The prior deployment boundary is superseded. The Docker API, Worker, and
  Beat were rebuilt and restarted after the PBOS provider repair; `/ready`
  returned `200`, the container loaded `mcp==1.28.1` with `FastMCP`, and the
  active Celery worker returned `pong` through the configured Redis control
  plane.
- The live proof uncovered and corrected a budget-edge defect: when a long
  selected evidence source displaced a retrieved page from rendered context,
  PBOS lost the page reference. `PBOSGovernedContextProvider` now retains only
  retrieval-selected, BSC-published pages as immutable planning references and
  attaches their processed citation lineage. It does not scan `wiki/` from the
  filesystem or expose unpublished content.
- A temporary, discarded Artifact Graph inside the production API container
  compiled a default-project Obsidian plugin-extension Mission. Its resulting
  plan carried both the actual published page revision
  `wiki:6d695376a04e63d49958c84c@eb769555c96456a076186ecc81468f5b350ce0bd489589696cdfff4d93274a53`
  and source revision
  `source:d868c7bd34af@5c71bef8236b9dcaeb55216e523afc503fb12f0d15f6f0738b7bc9dde0c69b0c`.
  No fabricated mission, plan, or Vault content was persisted for this check.
- Regression: `tests/pbos/test_pbos_contextual_compiler.py -q` passed with
  `10 passed`, including the source-budget displacement case. The live Wiki
  snapshot remains lint-clean with 10 pages, 153 sources, 37 citations,
  citation coverage `1.0`, no dangling/stale citations or pending proposals,
  and 78 persisted graph edges.

## 2026-07-30 Daily Action And Personal-Evidence Closure

- Corrected a product-level gap in the daily loop. The report previously
  rendered only the plan title and a legacy BSC-owned report could remain stale
  without an integrity footer. `PBOSService.today_action()` now deterministically
  selects the first unfinished compiler phase action, its success check,
  rationale, plan/Mission IDs, and governed references. It is exposed at
  `GET /api/pbos/projects/{project_id}/today-action`, returned from Cockpit,
  rendered in the cockpit header, and written into daily/weekly/monthly PBOS
  projections.
- Periodic reports now carry a `pbos-managed-sha256` footer. Untouched
  BSC-managed reports, including the one-time legacy format, can refresh; a
  user edit after the footer resolves to `conflict` and is never overwritten.
  This keeps the managed daily action current without taking ownership of
  human-authored changes.
- Added a separate `eligible_personal_outcomes` health measure and per-outcome
  eligibility observations. An accepted result still requires an execution,
  actions, tool receipts, reflection, and quality score before it can teach a
  personal method. The default ledger's historical `accepted` technical test
  has no reflection, so it remains visible but explicitly reports `not eligible
  for personal learning`; it does not create a Capability, Experience, or
  Strategy Genome.
- Live validation used the durable `knowledge_runs` path, not a test fixture:
  run `ca71623ad429` (`pbos_daily`, `manual_validation`) completed and wrote
  `pbos/reviews/daily/2026-07-30/daily-action.md` in the mapped default Vault.
  It selected the current contextual plan's acceptance-card action, cited eight
  governed planning references, and retained the evidence gap. A protected
  in-container REST readback returned `recommended`, the same plan ID,
  eight references, `eligible_personal_outcomes=0`, `verified_capabilities=0`,
  and `active_strategies=0`.
- Verification: `pytest tests/pbos/test_pbos_service.py tests/pbos/test_pbos_scheduler.py
  tests/api/test_pbos_api.py tests/integration/test_pbos_e2e.py -q` passed
  (`24 passed`); focused Cockpit tests passed (`4 passed`); `npm run check`
  passed; Docker API, Worker, and Beat were rebuilt and `/ready` returned 200.
  The final in-container production build completed with only the existing
  non-blocking ECharts chunk-size advisory.
- Rollback: remove `today_action`, the report integrity-footer renderer, and
  their focused tests; existing reports retain their latest BSC-managed body.
  Do not reclassify technical validation outcomes as user-accepted personal
  evidence. Three comparable real AI-project deliveries with reviewable
  receipts, quality, and reflection are still required before the evolution
  gate can promote a personal method.
