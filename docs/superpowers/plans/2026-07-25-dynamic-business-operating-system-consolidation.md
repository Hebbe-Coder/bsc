# Dynamic Business OS First-Round Consolidation

**Date:** 2026-07-25
**Status:** First-round implementation verified
**PRD:** `docs/superpowers/specs/2026-07-25-dynamic-business-operating-system-prd.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-25-dynamic-business-operating-system.md`

## Implemented Architecture

DBOS is an additive, project-scoped domain over the existing Artifact Graph.
It does not retrieve a fixed SOP by title. A persisted Mission follows this
traceable path:

```text
Mission
  -> Diagnosis + Evidence + Assumptions + Gaps + Risks
  -> CapabilitySelection
  -> DynamicSOP
  -> reviewer Decision Log + explicit capability grants
  -> redacted RuntimeContext + auditable RunCheckpoint
  -> audited ExecutionResult + TaskVerification or interrupted/manual-retry state
  -> outcome-linked candidate Memory
```

`MissionArtifact` is the authorization root. Existing `BusinessRuntime`,
orchestrator lifecycle, Artifact Graph semantics, MCP HTTP/SSE transport, and
A/B/C/D knowledge-growth governance were preserved.

## Plan Reconciliation

| Plan | Delivered behavior | Evidence |
| --- | --- | --- |
| P01 contracts/artifacts | Added Mission, Diagnosis, Evidence, Assumption, Gap, Risk, CapabilitySelection, DynamicSOP, ExecutionResult, TaskVerification, Memory, RuntimeContext and RunCheckpoint types. DBOS has additive Artifact Graph export grouping; Decisions are task-bound. | `tests/dbos/test_contracts.py`, `tests/test_artifact_scope.py` |
| P02 diagnosis/intake | Business/career context is normalized; source-backed evidence, stakeholders, decision rights, success metrics, hypotheses, risks and missing facts are persisted as evidence, gaps or assumptions rather than fabricated claims. | `tests/dbos/test_dbos_flow.py` |
| P03 capability selection | Profile/signal scoring selects and rejects capabilities from role, industry, organization stage, goal, constraints, evidence coverage, stakeholders and decision rights. Exact task-family matches from governed A/B/C/D metadata add an explainable bounded score component; cross-project, untrusted or unapproved records do not. Commerce, restaurant, product, consulting and general contexts have distinct scoring paths. | Context-divergence and memory tests; authenticated dual-scenario HTTP check |
| P04 Dynamic SOP compiler | Compiles profile-specific phases, task owners, deliverables, metrics, triggers, decision points, risks, checks, retrospects and quality gates with parent references. Matching knowledge signal IDs become task lineage and require an applicability check, never a replacement for current evidence. Ecommerce emits funnel work; AI product work emits problem-to-adoption work. | Context-divergence and knowledge-signal tests; authenticated dual-scenario HTTP check |
| P05 execution autonomy | Confirmation grants a reviewed subset only; each task additionally requires a persisted matching decision; unconfirmed/ungranted calls fail closed; attempts, idempotency, checkpoints, stop, rollback and manual restart recovery remain audited. | Flow, API and runtime-recovery tests |
| P06 knowledge/memory | Reads only project-scoped governed metadata. Trusted/reviewed eligible/processed sources, published pages, accepted/filed outputs and approved/published methods are converted into bounded task-family signals; raw bodies are never read. Outcome feedback remains a candidate Memory artifact. | `tests/dbos/test_memory.py` |
| P07 API/MCP | REST covers Mission list/lifecycle, decision, execution, feedback, stop, rollback and control center. MCP delegates the same lifecycle controls to the scoped service with existing auth gates. | API/MCP tests |
| P08 control center | Studio `Operate` opens a real-data view with Mission selection, reviewer authorization, evidence/gaps/risks, scored capability rationale, Dynamic SOP task inspection, React Flow lineage, Decision Log, redacted context snapshot, manual-retry state, verified execution ledger, feedback memory, Mission stop and task rollback. The 390px layout has no horizontal overflow. | Vitest, production build and browser acceptance |
| P09 release | Focused regression, frontend test, Vite build, authenticated HTTP divergence/execution, and desktop/mobile browser acceptance completed. | Commands and runtime evidence below |

## Interfaces And Artifact Mapping

`/api/dbos` provides project-scoped Mission list/create/diagnose/confirm,
control-center projection, execution, feedback-memory, task-bound decision,
stop, rollback and startup recovery operations. Reader roles remain read-only.

MCP provides `dbos_create_mission`, `dbos_diagnose_mission`,
`dbos_confirm_mission`, `dbos_execute_mission`, `dbos_control_center`,
`dbos_record_feedback`, `dbos_record_decision`, `dbos_stop_mission` and
`dbos_rollback_execution`, plus established compact compatibility aliases. No
second DBOS transport or in-memory state exists.

Each Dynamic SOP task references its Diagnosis and CapabilitySelection. A
Decision is parented by the Mission, Dynamic SOP and task lineage. Every
execution receives a redacted RuntimeContext manifest and append-only Run
Checkpoints. Real/API capability output receives a TaskVerification artifact;
absent declared Artifact Graph output types fail closed. A restart converts an
in-flight attempt to `interrupted`, restores the Mission to confirmed state,
and refuses automatic replay; a new manual
idempotency key is required. Memory is parented by an audited execution. The
control-center graph is projected from persisted Artifact Graph data, not
synthetic client state.

Knowledge reuse is additive and bounded: the adapter maps only declared,
structured A/B/C/D metadata to an allowed task family. A matching signal is
stored in `CapabilitySelection.metadata.knowledge_context.signals`, raises a
visible `knowledge_evidence` score component, is included in the relevant
`DynamicSOPTask.parent_refs`, and adds a pre-reuse quality gate. Source,
page and output bodies never enter selection, compiler output or runtime
manifests. This preserves project isolation and provenance without claiming an
Obsidian read or a semantic retrieval run.

## Resolved Deviations

- The initial compiler had decision-point prose but no persisted Decision Log.
  This is now a task-bound `DecisionArtifact` with REST, MCP, UI and tests.
- Persisted Missions needed a usable return path. A project-scoped Mission
  list and selector were added so a user is not required to copy artifact ids.
- Execution remains limited to registered internal BSC capabilities. This is
  an intentional first-round safety boundary, not an unverified success claim.
- Runtime state initially had no restart-safe trace. Context manifests are now
  redacted (no raw prompts, source bodies, model output or credentials), and
  startup recovery records interruption rather than replaying a capability.
- Early Dynamic SOP tasks were structurally traceable but too generic. The
  compiler now uses diagnosed profiles and signals to emit different workstreams,
  metrics and quality gates, while selection stores score components, reasons
  and rejected capabilities for review.
- Earlier `api` execution could finish without proving its declared output. A
  durable `TaskVerificationArtifact` now records a passed or failed verdict and
  prevents missing output from being reported as a successful capability.
- Knowledge artifacts were initially retained only as context IDs. Governed,
  exact task-family signals now materially change the selection explanation and
  score, Dynamic SOP lineage and reuse quality gate, while raw Vault data stays
  out of the DBOS prompt/runtime surface.

## Verification Evidence

```powershell
.\.venv\Scripts\python.exe -m pytest tests\dbos tests\api\test_dbos_api.py tests\mcp\test_dbos_tools.py tests\mcp\test_dbos_http_contract.py tests\test_artifact_scope.py -q
# 29 passed; one existing Starlette/httpx deprecation warning

npm run test:frontend -- --run src/api/dbosApi.test.ts src/components/dbos/BusinessControlCenter.test.tsx
# 10 passed

npm run check
npm run build
# passed (TypeScript + Vite; Vite only reports chunk-size guidance)

Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5182/
# StatusCode 200

# Authenticated real HTTP lifecycle on current source, with no displayed key:
# execution returned 409 before confirmation and before a task-matched Decision,
# then completed after both gates. `dbos-verified-execution-e2e-20260725b`
# has a real internal nanobot/api run, TaskVerification=passed and 16 graph nodes.

# Authenticated dual-scenario check:
# ecommerce compiled `traffic -> product view -> cart -> payment -> repeat order`;
# AI product management compiled `user problem -> product decision -> delivery
# milestone -> adoption signal`. Capability selection and workstreams differed.

# Current user-facing chain after the stale-process correction:
# http://127.0.0.1:8007 is the current-source backend and
# http://127.0.0.1:5185 is the current-code Studio proxy. Mission and
# control-center reads returned 200 there without an Authorization header from
# the browser, including the persisted adaptive compilation result.
# The older 8000 Uvicorn process rejects Horizon's capture_run_id. The earlier
# 5180 -> 8004 proxy remains recorded as historical Horizon verification:
# POST http://127.0.0.1:5180/knowledge/horizon/capture for
# run-20260725T143221Z-3f4e0c7e returned completed through that earlier proxy.

# Isolated real adaptive Dynamic SOP compilation on current source:
# a 618 ecommerce Mission included a 12 percent cart-conversion drop, no new
# acquisition budget, margin/inventory constraints, named stakeholders and
# decision authority. PromptOps returned `adaptive_compilation=completed` and
# all five task titles/deliverables were materially customized; the deterministic
# routing evaluation also returned passed. No capability dispatch, Vault write,
# or third-party side effect occurred.

# Default project governed-context verification:
# the current Obsidian/Growth pack had profile revision 2, one published page,
# two admitted sources and one published method revision with no research gaps.
# A real isolated compile carried five audited context references and generated
# evidence-specific AI code-review verification tasks; routing evaluation passed.

# Browser acceptance in the active http://127.0.0.1:5180 Studio:
# Operate loaded the verified ecommerce Mission and visibly rendered its source
# evidence, capability scoring, task inspection, decision lineage, 16-node graph
# and `completed | verification: passed` ledger entry. Desktop and 390px mobile
# were checked; the mobile layout uses a 384px content viewport with no horizontal
# overflow. No external connector was invoked.

# Current-source governance lifecycle on refreshed http://127.0.0.1:8000,
# authenticated in-process with no displayed credential and with loopback proxy
# bypass: `dbos-governance-live-95008d0f9e` completed a controlled internal
# execution and persisted `rolled_back` (16 graph nodes); the separate
# `dbos-stop-live-7cae3ddfdb` Mission was confirmed then stopped before dispatch
# and persisted zero execution results.
```

The regression evidence covers cross-context compilation divergence, Artifact
Graph project isolation, confirmation gating, ungranted-capability rejection,
task-output verification, idempotent execution, scoped approved-method use,
governed source/page/output task-family reuse, raw-body exclusion,
REST/MCP service sharing, task-decision enforcement, restart/manual-retry
behavior, and rendered Control Center evidence/authorization/decision/context
and responsive states.

The final affected regression added `tests/knowledge/test_wiki_repository.py`
and `tests/knowledge/test_method_evolution.py` to the DBOS suite: `35 passed`
with one existing Starlette/httpx deprecation warning. `npm run check` and
`npm run build` both passed; Vite reports only existing chunk-size guidance.

## Rollback

Set `DYNAMIC_BUSINESS_OS_ENABLED=false` to refuse DBOS routes and tools. BSC,
orchestrator and knowledge paths remain available. DBOS artifacts stay intact
for audit; removing the `Operate` entry is an independent UI rollback.

## Residual Risks And Next Iteration

1. **Diagnosis quality:** add domain-specific evidence collection and reviewer
   edits for stakeholders, decision rights and quantitative baselines.
2. **Capability-selection quality:** add calibrated scenario evaluation and
   compare against approved historical methods without restoring templates.
3. **Execution reliability:** add external-effect adapters, dry-run contracts,
   retry policy tests and browser E2E coverage for failure/stop/rollback paths.
4. **Knowledge learning effect:** evaluate whether each bounded knowledge
   signal improved a reviewed outcome, then promote candidate memory only
   through the existing A/B/C/D gates. Adaptive compilation now consumes an
   audited, sanitized `GrowthContextService` pack only when explicitly
   requested; raw ungoverned Vault content remains intentionally out of DBOS.
5. **Experience quality:** add automated browser coverage for task failure,
   stop and rollback paths, plus inspected effects and source-link navigation.

The Horizon evidence channel has one audited run: producer run
`run-20260725T143221Z-3f4e0c7e` fetched and scored eight records, retained two,
and BSC import `0ddf3d091623` created two governed source records. Both were
correctly left in `validated/archive` by project triage because they did not
meet the project's relevance threshold. No Obsidian write, third-party side
effect, or other external-system run is marked complete without its own
audited execution evidence.
