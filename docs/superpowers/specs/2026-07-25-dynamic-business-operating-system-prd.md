# Dynamic Business OS (DBOS) PRD

**Date:** 2026-07-25
**Status:** In implementation
**Owner:** BSC Studio

## 1. Product Definition

DBOS turns a business situation into a governed execution system. It is not a
library that finds a prewritten SOP by title. It is a compiler:

```text
Business intent + context + constraints + evidence
  -> diagnosis + assumptions + evidence gaps + risks
  -> explainable capability selection
  -> Dynamic SOP + decisions + authorized execution
  -> outcomes + feedback + reusable knowledge
```

The canonical runtime remains the existing `BusinessRuntime`; DBOS is an
additive domain layer that prepares, governs, traces, and visualizes business
missions. Existing `/bsc/*`, orchestrator lifecycle, MCP transport, and A/B/C/D
knowledge-growth semantics are compatibility boundaries, not replacement
targets.

## 2. Problem

The current product can generate a detailed SOP but, without a structured
diagnosis, different users receive variations of one generic template. A
restaurant operations lead facing stalled growth and a SaaS product manager
seeking fast ownership have different operating constraints, decision rights,
risks, evidence, and success measures. A correct product must make those
differences explicit before any workflow is proposed or run.

## 3. Goals and Non-goals

### Goals

1. Produce distinct diagnoses, capability selections, and Dynamic SOPs for
   materially different role, industry, organization-stage, goal, and
   constraint inputs.
2. Preserve traceability from every SOP task to the Mission, diagnosis,
   evidence/assumptions, selected capabilities, decisions, execution events,
   outcome, and feedback.
3. Require a mission confirmation gate before DBOS can cause external effects.
   Confirmation only grants explicitly authorized capabilities.
4. Reuse the governed A/B/C/D knowledge loop as capability, pattern, rule,
   artifact, case, and feedback material rather than treating static SOP files
   as the product.
5. Make current state inspectable in a Business Control Center. The UI must
   show real API data, not simulated health scores or success states.

### Non-goals

- Replacing existing BSC compilation or MCP JSON-RPC/SSE transports.
- Autonomous access to third-party systems without an explicit authorized
  capability binding.
- Treating LLM prose as evidence, confirmation, permission, or execution.
- Publishing unreviewed knowledge methods into the A/B/C/D C layer.

## 4. Personas and Core Scenarios

| Persona | Input | Required DBOS outcome |
| --- | --- | --- |
| New AI product manager | 3 months in role; must independently lead a project | onboarding/diagnostic plan, stakeholder decision cadence, project operating system |
| E-commerce operations lead | 618 is in 30 days; conversion has fallen; limited budget | conversion diagnosis, experiment portfolio, owners/KPIs/kill criteria, daily operating cadence |
| Restaurant chain operations manager | Tier-3 city stores have stalled | traffic, menu, labor, local marketing, store feedback workstreams with risks |
| Consultant/team lead | Needs an evidence-backed client delivery | mission-scoped research, decision log, reviewable deliverables and feedback capture |

## 5. Domain Model and Artifact Graph Mapping

DBOS artifacts are additive `ArtifactType` values. They retain normal
`BaseArtifact` lineage, project isolation, snapshots and status lifecycle.

| Artifact | Responsibility | Parent lineage |
| --- | --- | --- |
| `mission` | requested work, authorization scope, confirmation state | optional business model/evidence |
| `diagnosis` | normalized role, industry, stage, goal, constraints, problem framing | mission |
| `assumption` | testable missing fact used in reasoning | diagnosis (existing type) |
| `evidence` | source-backed fact or explicit absence | diagnosis/assumption (existing type) |
| `gap` | evidence or analysis deficiency | diagnosis (existing type) |
| `capability_selection` | selected/rejected capabilities and score explanations | diagnosis |
| `dynamic_sop` | executable, staged operating system | diagnosis + capability selection |
| `decision` | accepted option/rationale/authority | Dynamic SOP or diagnosis (existing type) |
| `execution_result` | authorized attempt, effects, retries, stop/rollback state | mission + Dynamic SOP |
| `memory` | governed feedback/pattern/case reference | execution result/output |

`Mission` is the authorization root. A `DynamicSOP` is a compilation output,
not a free-standing template. Existing `DeliverableArtifact` remains the
reviewable file/report surface and may reference `dynamic_sop_id`.

## 6. Functional Requirements

### FR-1 Intake and diagnosis

- Provide `career` and `business` intake modes. Both accept a free-text intent
  plus structured role, industry, organization stage, goal, time horizon,
  constraints, stakeholders, decision rights, and authorized capabilities.
- Deterministically normalize and preserve declared facts. Missing critical
  facts become `AssumptionArtifact` and `GapArtifact`; they must not be
  fabricated as facts.
- Identify risks and produce a confirmation preview with pending assumptions,
  evidence gaps, and prohibited external effects.

### FR-2 Explainable capability selection

- Maintain a capability pool with applicability signals for task families,
  roles, industries, organization stages, goals, and constraints.
- Select a composition based on the diagnosis, not the name of an SOP.
- Return per-capability score components and rejection/constraint reasons.
- A selection may include both existing BSC capabilities and DBOS planning
  capabilities. Only registered executable capabilities are eligible to run.

### FR-3 Dynamic SOP compiler

- Compile confirmed diagnostic context into phases, tasks, owners, deliverables,
  metrics, trigger conditions, decision points, risks, checks, and retrospects.
- Every task has a stable id, a selected capability or manual action, a clear
  completion condition and linked source artifacts.
- The compiler must produce meaningfully different workstreams when diagnosis
  inputs differ. It must never silently claim a task was executed.

### FR-4 Authorization and execution

- A new mission begins `draft`; only a `confirmed` mission can call execution.
- Confirmation records actor, timestamp, authorized capability names and the
  immutable diagnosis/selection/sop references. An unconfirmed call returns
  `409` before any executor is invoked.
- The execution service accepts only capabilities listed in the mission grant.
  Unknown, unregistered, or ungranted capabilities fail closed and are audited.
- Every attempt stores status, idempotency key, retry count, error, effects,
  stop reason and rollback result. The first implementation only invokes
  registered BSC capabilities; external side effects remain absent until a
  distinct capability declares and is granted them.

### FR-5 Knowledge and memory

- Convert existing A/B/C/D material into read-only inputs: A sources/evidence,
  B wiki concepts/pages, C governed methods, D accepted outputs/feedback.
- Store DBOS feedback as reusable memory candidates with provenance; memory is
  advisory and never bypasses evidence, method gates, or project boundaries.
- The capability selector can use relevant approved methods/patterns only as
  explainable weighting, never as a hard-coded template answer.

### FR-6 API, MCP, UI

- REST APIs cover mission creation/read, diagnosis, confirmation, capability
  selection, SOP compilation/read, execution/read, decision logging, feedback,
  memory, and control-center projection.
- MCP extends the existing HTTP/SSE server with analogous project-required
  tools and its current authorization semantics. It must not add a second
  transport or bypass REST validation.
- Business Control Center shows goal health from persisted artifacts, an
  inspectable reasoning graph, decisions, capability status, Dynamic SOP tasks,
  execution events, and feedback/memory references.

## 7. Data and Lifecycle Contracts

### Mission state machine

```text
draft -> diagnosed -> ready_for_confirmation -> confirmed -> executing
     -> completed | failed | stopped | rolled_back
```

- `draft`, `diagnosed`, and `ready_for_confirmation` may generate artifacts but
  cannot call registered executors.
- `confirmed` is immutable apart from a terminal-state transition. Changed
  diagnosis, authorization, or Dynamic SOP creates a new mission revision.
- A stopped/failed execution records its terminal state and may create a new
  retry execution only with the same mission authorization.

### Contract fields

`MissionArtifact`: `mission_id`, `title`, `intake_mode`, `intent`, `status`,
`authorization`, `confirmed_at`, `confirmed_by`, `revision`.

`DiagnosisArtifact`: `role`, `industry`, `organization_stage`, `goal`,
`time_horizon`, `constraints`, `stakeholders`, `problem_statement`,
`risk_summary`, `coverage`, `missing_fields`.

`CapabilitySelectionArtifact`: `selected` records (`capability_name`, `score`,
`reasons`, `task_family`) and `rejected` records (`name`, `reason`).

`DynamicSOPArtifact`: `title`, `objective`, `phases`, each task with `task_id`,
`title`, `capability_name`, `owner`, `deliverable`, `metric`, `trigger`,
`decision_point`, `risk`, `check`, `retrospect`, and `parent_refs`.

`ExecutionResultArtifact`: `execution_id`, `mission_id`, `capability_name`,
`status`, `attempt`, `idempotency_key`, `effects`, `error`, `rollback`,
`started_at`, `completed_at`.

## 8. Quality, Security, and Reliability

- All artifacts are project scoped and ArtifactGraphStore enforces scope on
  artifact parent links and exports.
- Confirmation and execution are idempotent by Mission/operation key.
- Artifacts retain lineage and can be snapshotted/diffed using the existing
  Artifact Graph. No DBOS route may infer that a failed execution succeeded.
- API body bounds, role checks, and API-key/session semantics match existing
  protected BSC APIs. Reader roles may inspect but never create/confirm/execute.
- Selection and compiler use deterministic rules in the initial implementation;
  LLM enhancement must remain proposal/reviewable and preserve the contract.

## 9. UX Requirements

Desktop Control Center has: mission header and health, context/diagnosis panel,
reasoning graph, capability selection table, Dynamic SOP timeline, decision
log, execution event rail, and memory/feedback strip. Selecting a task exposes
its source links, constraint/risk, actual run status, and rollback information.

Mobile stacks the same information into mission summary, health/confirmation,
timeline, and inspection drawers. No control can display a green execution
state unless a persisted `ExecutionResultArtifact` is successful.

## 10. Acceptance Criteria

1. An e-commerce 618 conversion scenario and an AI product-manager onboarding
   scenario yield different diagnosis fields, selected capability composition,
   Dynamic SOP titles and task families.
2. Before confirmation, execution returns `409`, produces no execution
   artifact, and invokes no executor. After confirmation, execution accepts
   only the granted registered capability set.
3. A Dynamic SOP traverses parent lineage to the Mission, Diagnosis,
   CapabilitySelection, declared gaps/evidence and later execution result.
4. API and MCP requests cannot cross a project boundary or use an ungranted
   capability.
5. Existing Artifact Graph and knowledge-growth regression tests continue to
   pass, alongside new DBOS unit/API/UI tests.
6. Consolidation records actual commands/results, deviations and open risks;
   it must not mark an unimplemented external connector as complete.

## 11. Rollout

Feature flag `DYNAMIC_BUSINESS_OS_ENABLED` defaults enabled in development and
can disable the DBOS router without changing existing BSC routes. Initial
execution is intentionally limited to registered internal BSC capabilities;
external systems require a later explicit capability implementation, policy,
and test suite.
