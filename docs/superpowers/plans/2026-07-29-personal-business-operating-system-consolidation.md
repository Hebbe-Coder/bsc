# PBOS v1.0 First-Round Consolidation

## Current Implementation Evidence

- Added durable, project-scoped PBOS Artifact Graph assets for profile, capability, personal execution plan, execution record, outcome, feedback, experience, Strategy Genome version, and promotion.
- Added an evidence-first PBOS service and isolated `/api/pbos` registration. It uses the same DBOS project authorization and ledger boundary.
- Added local, read-only evidence receipts for Git HEAD and explicitly declared in-root files. Receipts record identifiers/hashes, not file contents.
- Added conflict-safe Obsidian L3 projections below `pbos/`, an evidence-only weekly report below `distillations/每周蒸馏/<week>/pbos/`, Celery report task entry points, MCP Cockpit/report tools, and a lazy Personal Growth Cockpit with ECharts and React Flow.
- Verified an authenticated default-project loop: profile -> DBOS Mission -> capture-local Git/file receipts -> accepted outcome -> feedback -> weekly Vault report.
- Closed the durable automation boundary: `pbos_daily`, `pbos_weekly`, and `pbos_monthly` use the existing `knowledge_runs` ledger, idempotency claims, Celery queue, terminal status, and output references. Daily and monthly reports use separate conflict-safe PBOS paths; the weekly report remains under the existing `每周蒸馏` hierarchy.
- Installed the three PBOS schedules for `default` in the deployed Docker runtime and verified an actual worker-consumed daily job completed with a Vault output reference. This is runtime evidence, not a simulated scheduler response.

## Runtime Evidence Reconciled 2026-07-29

- The initial Docker Cockpit was not a sufficient completion proof: an older
  locally-clocked Profile and Plan sorted ahead of newer Docker-ledger assets.
  PBOS now chooses current Profile, Plan, feedback, outcomes, and strategy
  versions by persisted `updated_at`. Regression coverage prevents the stale
  state from reappearing.
- The current default-project PBOS chain is real and inspectable:
  `art_40aaffb724d4` Mission -> `art_ffc8b3b7085b` current Personal Execution
  Plan; its recorded validation lineage is
  `art_37cdf0d57c5d` Plan -> `art_d8be15ecfd84` execution ->
  `art_420107532f71` unverified outcome -> `art_af2b5eb0527c` feedback. The
  current Plan uses eight governed Obsidian
  context references spanning the active project control plane, a method and
  its evaluation contract, published Wiki concepts, and governance decisions.
- A prior plan `art_f9585ff7c450` was generated through the deployed
  `/api/pbos` endpoint in `llm_contextual` mode after the model service
  recovered. The final current plan is an explicitly contextual deterministic
  fallback because a later provider response violated the structured-output
  contract; it retains personal focus, governed context, and evidence gaps but
  never claims a model result.
- The recorded validation execution contains three reviewable receipts:
  focused PBOS tests, Docker rebuild/restart, and authenticated Cockpit
  readback. Its outcome is `unverified`, so the Cockpit correctly reports
  zero verified capabilities. A historic accepted outcome remains visible as
  prior ledger history but is not treated as evidence that the current user
  has grown a capability.
- GitHub and Feishu remain `awaiting_authorization`. These connector paths are
  not included in the current Plan as a synchronization fact and no remote
  data has been used as personal evidence.

## Verified Commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_service.py -q
# 3 passed
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py -q
# 21 passed; one existing dependency deprecation warning
npm run check
# passed
npm run build
# passed; PBOS Cockpit is a lazy chunk
docker compose config
# passed
```

## Automation Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_growth_distillation.py tests/integration/test_knowledge_celery.py -q
# 112 passed, 1 skipped
npm run test:frontend
# 21 files / 155 tests passed
docker compose up -d --build bsc-backend celery-worker celery-beat
# deployed successfully
```

The current post-reconciliation command results are:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\pbos tests\api\test_pbos_api.py tests\test_artifact_store_durability.py tests\test_agent_runtime_convergence.py tests\knowledge\test_wiki_sync.py tests\knowledge\test_growth_distillation.py tests\integration\test_knowledge_celery.py -q
# 120 passed, 1 skipped
npm run test:frontend
# 21 files / 155 tests passed
npm run check
# passed
npm run build
# passed; non-blocking large ECharts chunk warning
docker compose config
# passed
```

The deployed `default` project has enabled `pbos_daily`, `pbos_weekly`, and `pbos_monthly` schedules in `Asia/Shanghai`. A manually queued PBOS daily review was consumed by the live worker, reached `completed`, and recorded `pbos/reviews/daily/2026-07-29/daily-action.md` as its Vault output. GitHub and Feishu continue to report `awaiting_authorization`; no remote connector was represented as synchronized.

## Remaining External Boundary

- GitHub and Feishu correctly remain `awaiting_authorization`; no credentials were supplied and no remote sync is claimed.
- Playwright's bundled Chromium download timed out, so browser acceptance used the installed Microsoft Edge executable through Playwright. Desktop and 390px mobile checks loaded the actual accepted outcome through the current-source API with no error or horizontal overflow. Evidence is stored under the Codex visualization workspace.

## Rollback

Remove the PBOS-only module, API registration, PBOS ArtifactType entries, tests, and documents. Existing DBOS and Growth artifacts have not been migrated or reinterpreted.

## Next Iteration Priority

1. Add structured-provider health tracking and an output-quality evaluation so an LLM fallback can be retried only after a healthy response contract is observed.
2. Collect user-accepted outcomes and three-minute reflections from actual AI-project deliveries before proposing any Experience, Strategy Genome, or Capability promotion.
3. Authorize GitHub/Feishu read-only connectors only when scoped credentials are intentionally supplied.

## Final Acceptance Update

- The final source verification added the plan's previously absent PBOS MCP
  contract and REST integration tests. The concrete command below passed 25
  tests and now matches the release-plan acceptance surface:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py
# 25 passed
npm run test:frontend
# 23 files / 157 tests passed
npm run check
# passed
npm run build
# passed; existing non-blocking vendor ECharts chunk-size warning
```

- The Personal Growth Cockpit's zero-capability state is explicitly honest:
  declared profile and governed Vault context can guide a plan, but neither is
  presented as verified capability evidence. Real Strategy Genome and
  Capability promotion remain intentionally incomplete until three comparable,
  accepted real deliveries meet the evolution gates.

## 2026-07-30 Model Reliability And Live Loop Evidence

- The DeepSeek PBOS compiler no longer makes a single structured-output attempt.
  It retries JSON mode with a bounded larger completion budget, supports
  documented OpenAI-compatible legacy text payloads, and keeps the model's
  private reasoning and response body outside logs, Artifact Graph records, and
  Obsidian. If both attempts fail, the plan records only a safe response shape
  and attempt ledger before returning the evidence-grounded deterministic
  fallback.
- Source evidence: `tests/test_sop_llm_client.py` and
  `tests/pbos/test_pbos_contextual_compiler.py` cover output-budget repair,
  legacy text compatibility, private-reasoning non-use, and safe fallback
  metadata. The focused client/compiler run passed `28` tests; the PBOS REST,
  MCP, and integration run passed `30` tests. The broader PBOS/Artifact/
  knowledge command passed `125`, with one existing skip.
- Runtime evidence: project `pbos-llm-proof-20260730` used a fresh profile,
  governed Obsidian project note, DBOS diagnosis, and production `/api/pbos`
  endpoint. Two consecutive DeepSeek plans (`art_63e4d5e0b020` and
  `art_98cc5818bff3`) were persisted with `compiler_metadata.mode =
  llm_contextual`. The latter references feedback `art_66805ff644bd`, proving
  `Mission -> Plan -> Execution -> Outcome -> Feedback -> Next Plan` in the
  same project ledger and its `pbos/` Vault projections.
- The actual execution record is deliberately conservative: outcome
  `art_8eb0f911f885` is `unverified` and zero Capability/Strategy assets are
  shown in the live Cockpit. The plan is context-grounded, not yet an earned
  personal method, because no three comparable user-accepted AI deliveries
  exist. This is expected product behavior, not an incomplete persistence or
  UI path.
- Production container inspection confirmed it runs the retry-enabled compiler;
  its services were healthy. `npm run test:frontend` passed `162` tests;
  `npm run check`, `npm run build`, and `docker compose config --quiet` passed.
  Browser readback of the isolated project confirmed the actual one-reference,
  one-unverified-outcome, one-feedback, zero-capability payload. At 390px its
  measured page width was 384px, with no horizontal overflow.

## Remaining Product Evidence

1. Collect three comparable, complete, user-accepted AI-project deliveries
   from ordinary PBOS use before evaluating a Strategy Genome or Capability.
   Test fixtures and technical-validation results remain excluded by design.
2. Continue recording provider health over normal use. The compiler now repairs
   transient structured-output failures and diagnoses fallbacks safely, but no
   external provider can be truthfully guaranteed never to time out.
3. GitHub and Feishu remain read-only `awaiting_authorization`; no remote data
   was claimed as synchronized or used as personal evidence.

## Recovery Evidence

- A Docker Desktop restart interrupted a discretionary default-project plan
  request before it returned; no partial response was represented as an
  Artifact or a Vault projection. Once healthy, authenticated Cockpit readback
  recovered both the default and isolated project ledgers. Their current plans
  both report `llm_contextual`, while their Capability counts remain zero. This
  is direct runtime evidence that model-plan persistence, project isolation,
  and evidence gates survive a service restart.

## Post-Consolidation Runtime Closure: Daily Action And Evidence Eligibility

- The first-round implementation now also has a concrete daily entrypoint:
  `GET /api/pbos/projects/{project_id}/today-action` is a side-effect-free
  projection of the first unfinished action in the current Personal Execution
  Plan. It returns the plan/Mission lineage, success check, rationale, and
  governed context references. Cockpit and periodic reports consume this same
  projection, preventing a separate template-only daily writer.
- BSC-managed periodic projections contain a content hash footer. The default
  project's real `knowledge_runs` record `ca71623ad429` completed on
  2026-07-30 and refreshed
  `pbos/reviews/daily/2026-07-30/daily-action.md`. The result names the
  current acceptance-card action and eight actual governed Vault references.
  A report edited after its footer returns `conflict`; unowned content is not
  overwritten.
- The Cockpit separates `accepted_outcomes` from
  `eligible_personal_outcomes`. The latter requires accepted quality, execution
  actions, receipts, and a reflection. Runtime REST readback confirmed the
  default project has a recommended action, eight grounding references, zero
  learning-eligible outcomes, zero capabilities, and zero strategy assets.
  The old accepted technical validation outcome is labelled ineligible because
  it lacks a reflection, so it cannot distort personal growth claims.
- Verified after the final source state: PBOS service/scheduler/API/integration
  suite `24 passed`; focused Cockpit suite `4 passed`; TypeScript checking and
  Docker production build passed; API/Worker/Beat restarted and `/ready`
  returned `200`. The build's ECharts chunk advisory remains non-blocking.
- The remaining product-evidence condition is intentional and unchanged:
  collect three comparable, real, user-accepted AI-project deliveries with
  receipts, scores, and three-minute reflections before any Strategy Genome,
  Experience, or Capability is promoted. GitHub and Feishu remain
  `awaiting_authorization` and are not treated as data sources.

## Post-Consolidation Integrity Fix: Clipper Health-Check Exclusion

- A BSC-created Clipper destination health-check file had been presented as a
  captured source when a historical rejected record still referenced that
  path. The Vault was empty; the Studio projection was wrong. The source sync
  now excludes this marker before path-observation reconciliation, preserving
  the rejected record as audit history while setting `source_present=false`.
- The focused regression suite passed (`23 passed, 1 skipped`). After an API
  and worker rebuild, a real default-project Vault sync recorded one legacy
  record as no longer present and created no evidence. Authenticated API
  readback returned a configured Vault and Clipper `awaiting_export` with zero
  captured sources and an empty export observation.
- This changes no PBOS learning evidence. The live Cockpit still has a
  real today-action projection but zero promoted Capabilities and zero Strategy
  Genomes until the documented three-delivery, accepted-outcome gate is met.

## Post-Consolidation Product Closure: Evidence-Backed Reflections

- **Deviation resolved:** the original Cockpit could collect a three-minute
  reflection but could not attach a receipt or explicitly record an accepted,
  scored outcome in the same execution. The UI therefore could not produce an
  evolution-eligible result through normal use. It now offers a BSC-workspace
  evidence field, explicit acceptance, and quality score in one guarded flow.
- **Implemented contract:** `POST /api/pbos/projects/{project_id}/missions/{mission_id}/capture-bsc-workspace`
  captures only allowlisted project-relative paths. It stores server-observed
  hashes and optional Git identity, rejects unavailable or unsafe paths with
  `422`, and does not expose source bytes. The general execution endpoint
  treats caller-provided receipts as unverified even when a caller supplies a
  `verified=true` field.
- **Artifact Graph mapping:** the server-captured `WorkExecutionRecord` owns
  the verified receipt and reflection; `WorkOutcome` owns the user acceptance
  and score; `WorkFeedback` remains optional. `Experience`, `Capability`, and
  immutable `SOPVersion` still require three comparable accepted outcomes with
  the original quality or hard-failure gates. This preserves the PRD's
  no-fabricated-growth invariant.
- **Runtime evidence:** after rebuilding the production API, a container-local
  capture of `app/pbos/service.py` produced a real `local_file` hash receipt.
  A manual receipt claim was downgraded to `verified=false` and could not
  satisfy evolution; `.env` capture was rejected with `422`; `/ready` and the
  authenticated Cockpit returned `200`.
- **Verification:** PBOS REST/MCP/integration tests `45 passed`; shared
  Artifact/DBOS/knowledge tests `99 passed, 1 skipped`; frontend tests
  `167 passed`; `npm run check`, `npm run build`, and `docker compose config
  --quiet` passed. Rollback removes only the capture endpoint and Cockpit
  controls; persisted evidence stays audit-visible and no record is promoted
  by rollback.
