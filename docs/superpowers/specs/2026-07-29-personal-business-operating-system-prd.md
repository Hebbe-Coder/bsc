# PBOS v1.0: Personal Loop Engineering System

## 1. Product Definition

PBOS (Personal Business Operating System) is BSC's personal loop-engineering
layer for a solo AI-project builder. It connects the user's knowledge, real
delivery receipts, observed outcomes, and reflection so the next Mission is
compiled into a personal execution strategy. It is not a fixed SOP library,
generic productivity chatbot, or automatic claim that the user has mastered a
skill.

The v1 launch scenario is personal AI-project delivery: product design,
knowledge-engineering, code changes, test/build verification, and reflection.
The system is valuable only when each completed loop makes the next loop more
grounded in the user's own evidence.

## 2. Daily Product Loop

1. **Today:** recommend the highest-value next action, why it matters, its
   governed inputs, success check, decision point, and known evidence gap.
2. **Execute:** capture local Git/build/test/BSC/Vault receipts without reading
   secrets or treating an agent execution as user capability.
3. **Reflect:** collect a three-minute record of change, result, blocker,
   adjustment, attribution, and optional owner contribution.
4. **Review:** create an explicit Outcome only after a receipt and reflection;
   the owner accepts/rejects it and provides an observed quality/result.
5. **Grow:** eligible comparable outcomes form Experience candidates,
   Capability evidence, and immutable Strategy Genome versions for a later
   Mission.

Evidence-poor input produces a capture plan, never an invented personalized
conclusion. A plan may use declared profile and governed knowledge context,
but it must say when personal learning evidence is still missing.

## 3. Users And Jobs

| User/job | PBOS outcome |
| --- | --- |
| Solo AI builder preparing a delivery week | A priority action and executable plan based on current Mission, constraints, and evidence gaps. |
| Builder completing a code/product change | A receipt-backed execution record and short reflection, not another document template. |
| Builder reviewing what worked | An auditable Outcome and feedback direction, with no automatic success claim. |
| Builder repeating similar projects | A verified personal Strategy Genome only after comparable evidence reaches the promotion threshold. |
| Knowledge-system operator | A traceable view of sources, Obsidian memory, Horizon signals, methods, outputs, and personal-growth state. |

## 4. Authority And Storage

- **Raw material:** immutable A-layer source records and files remain the
  original source of truth.
- **Obsidian:** personal memory layer. L1 contains raw material, L2 contains
  methods/decisions/failures, and L3 contains BSC-owned PBOS projections. A
  manual L3 edit is a review candidate, never a direct ledger overwrite.
- **BSC Artifact Graph:** lifecycle, authorization, lineage, execution,
  outcome, feedback, evolution, audit, and project isolation authority.
- **Search/index:** derived and rebuildable. It cannot independently prove a
  capability, outcome, or external synchronization.
- **External systems:** GitHub and Feishu remain read-only and scoped. Their
  absence is `awaiting_authorization`, not a simulated connection.

Managed PBOS projections are below `projects/<project>/pbos/`. Weekly reports
are written beneath `distillations/每周蒸馏/<week>/pbos/` without replacing the
existing five-document knowledge-distillation output.

## 5. Artifact Graph Model

```text
PersonalProfile -> Capability
Mission -> PersonalExecutionPlan -> WorkExecutionRecord -> WorkOutcome
WorkOutcome -> WorkFeedback -> Experience -> Capability
Experience + Capability -> StrategyGenome -> SOPVersion -> next Mission
```

| Artifact | Required truth boundary |
| --- | --- |
| `PersonalProfile` | Owner-declared role, focus, resources, preferences, and constraints. It is not skill proof. |
| `Capability` | Level/confidence/growth data linked to accepted, attributable evidence only. |
| `PersonalExecutionPlan` | Mission-specific phases, actions, decision points, risks, success checks, and cited inputs. |
| `WorkExecutionRecord` | Captured actions, tool receipts, reflection, attribution, and context. |
| `WorkOutcome` | Observed result, acceptance decision, quality, impacts, comparison context, and failure state. |
| `WorkFeedback` | A sourced direction for the next plan. It is not accepted evidence by itself. |
| `Experience` | Extracted success/failure pattern with scope, boundary, and confidence. |
| `SOPVersion` / Strategy Genome | Immutable executable strategy: applicability, inputs, rules, paths, tools, risks, failure boundaries, metrics, verification, cases, and evidence. |
| `SOPPromotion` | Audited promotion/rollback event with genome diff and evidence chain. |

## 6. Functional Requirements

### PBOS-01 Personal Model

The system creates project-scoped artifacts and rejects cross-project reads or
writes. Profile fields are explicitly declared and visibly distinct from
verified Capability evidence.

### PBOS-02 Evidence Capture

PBOS can capture approved local Git, test, build, BSC workspace, and Vault
receipts. Server-captured receipt metadata is required for learning. Client
claims, credentials, source bodies, and paths outside the authorized workspace
are rejected or redacted.

### PBOS-03 Obsidian Integration

PBOS projects L3 assets with managed ownership markers and Dataview-compatible
frontmatter. The filesystem bridge is one-way and non-destructive. Local REST
may provide a bounded authenticated health check but must not expose its key.

### PBOS-04 Personal Execution Compiler

For a confirmed Mission, compile a plan from Mission/diagnosis, declared
profile, verified Capability/Experience/Strategy assets, resources,
constraints, governed Vault/Wiki context, feedback, and evidence gaps. Two
different personal contexts must produce materially different plans.

The plan includes objective, rationale, phases, actions, inputs, reviewable
outputs, checks, decision branches, risks, success criteria, reflection entry,
and capture plan. A Chinese Mission receives Chinese user-facing actions except
technical identifiers/commands.

### PBOS-05 Review And Learning

An Outcome cannot become learning-eligible without observed delivery result,
server receipt, reflection, owner or documented mixed attribution, explicit
acceptance, and quality score. Agent-only work stays auditable but cannot
promote personal capability.

### PBOS-06 Strategy Evolution

Promotion requires at least three comparable complete records, no severe
failure, and either median quality improvement of at least ten points or a
resolved prior hard failure. One severe failure or two comparable regressions
rolls the active strategy back. Older versions and diffs remain immutable.

### PBOS-07 Cockpit

`PersonalGrowthCockpit` exposes today's action, project health,
personalization readiness, D-layer review queue, attribution/outcome review,
Capability evidence, strategy assets, failure patterns, React Flow lineage,
and data-backed trends. Empty/unavailable states must be explicit.

### PBOS-08 Connectors

GitHub and Feishu require explicit scoped authorization and durable read
receipts. They are read-only. Without them the Cockpit returns
`awaiting_authorization`; PBOS does not infer access from another API key.

### PBOS-09 Automation

Celery/Redis schedules daily action refresh, weekly PBOS report, and monthly
capability report with durable intent, recovery state, retries, and audit
events. Jobs never claim external completion without a receipt.

### PBOS-10 APIs And MCP

The public PBOS domain is `/api/pbos/projects/{project_id}` and contains
profile, plan, execution, attribution, outcome, feedback, evolution, cockpit,
today-action, report, and schedule routes. MCP uses the same project
authorization and does not bypass REST safety gates.

## 7. Interaction And Visualization

The daily page answers: what to do next, why now, what evidence is missing,
what happened, what needs review, and whether a personal method has actually
been earned. The mobile control path at `390x844` must preserve readable
controls and avoid horizontal overflow. ECharts and React Flow visualize only
bounded, traceable ledger records; no fabricated score or growth trend is
permitted.

## 8. Safety, Security, And Non-Goals

- Mission confirmation is required before any external side effect.
- Existing DBOS authorization, MCP transport, and Artifact Graph semantics are
  preserved.
- Remote credentials never enter Artifact Graph, Vault, logs, browser state,
  reports, or API responses.
- Copilot conversation archives are not native D-layer output. A transcript
  import is an explicit registered review package and cannot create learning.
- v1 has no team comparison/ranking, connector write-back, automatic personal
  performance claim, or universal multi-profession template library.

## 9. Acceptance Criteria

1. Contrasting role, industry, stage, constraints, or prior evidence yields
   materially different diagnosis/plan/capability selection.
2. No unconfirmed Mission creates an external side effect.
3. Every visible plan/outcome/promotion/rollback traces to Mission, inputs,
   evidence, decisions, receipts, and feedback where applicable.
4. Missing evidence is explicit; no imported archive, model output, or
   agent-run test becomes a personal Capability by itself.
5. Strategy promotion and rollback meet the v1 rules and retain version diff.
6. Desktop and `390x844` Studio views render real selected-project state with
   no incoherent overlap or horizontal page overflow.
7. Consolidation reflects current code/tests/runtime/browser proof and keeps
   external authorization, native exports, real multimedia, and owner review
   marked pending until their evidence actually exists.
