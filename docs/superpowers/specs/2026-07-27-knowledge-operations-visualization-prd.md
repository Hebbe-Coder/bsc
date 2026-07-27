# Knowledge Operations Visualization System PRD

**Date:** 2026-07-27
**Status:** Implemented; runtime acceptance passed
**Owner:** BSC Studio
**Extends:** `2026-07-25-dynamic-business-operating-system-prd.md` and `2026-07-22-bsc-abcd-knowledge-growth-product-prd.md`
**Execution index:** `docs/superpowers/plans/2026-07-27-knowledge-operations-visualization-index.md`

## 1. Product Definition

Business Agent OS must not stop at storing knowledge, showing a generated SOP,
or listing a Memory. It must operate knowledge as a decision asset:

```text
Business problem
  -> AI reasoning and Artifact Graph
  -> governed knowledge deposition
  -> validation and outcome feedback
  -> reusable experience in the next decision
```

The Knowledge Operations Visualization System is a dual-scope operating
surface. An organization portfolio lets leaders compare authorized projects;
a project cockpit lets a responsible user trace a decision from business need
to evidence, reasoning, risk, method, execution, verification, and feedback.

It is not a new source of truth. DBOS Artifact Graph, Wiki/Growth records,
Vault Markdown, run ledgers, and evaluation records retain their existing
authority. The cockpit is a read-only, rebuildable operations projection plus
permission-gated links to existing review actions.

## 2. Users And Decision Jobs

| User | Scope | Decision question | Required outcome |
| --- | --- | --- | --- |
| Enterprise manager | Tenant portfolio | Where is knowledge producing verified value; which project needs intervention? | Comparable project health, risks, growth and action queue |
| Business owner | Authorized project | Which methods and experiences are proven and reusable? | Evidence-backed methods, outcome history and reuse signals |
| Project lead | One project / mission | What is missing or risky in the active plan? | Traceable gaps, assumptions, risks, failed verification and next action |
| AI Agent / MCP client | Authorized project | What proven context should influence the next decision? | Typed, redacted operations summary and provenance references |

The product deliberately does not optimize for developers reading raw logs. A
technical ledger remains available as a drill-down, but the first screen must
answer value, quality, risk, and action questions.

## 3. Goals And Non-goals

### Goals

1. Show which project knowledge assets are growing, validated, reused, or
   accumulating quality debt from persisted records only.
2. Make the chain from Mission/PRD to assumptions, risks, constraints, Dynamic
   SOP/method, verification, memory and feedback inspectable.
3. Give managers an organization-level portfolio without allowing cross-project
   or cross-tenant data disclosure.
4. Give project users an actionable review queue that delegates to existing
   proposal, execution, verification and detail workflows.
5. Show agent improvement through actual verification, retry and evaluation
   evidence rather than simulated accuracy or success claims.

### Non-goals

- Replacing the Wiki, Growth Workspace, Business Control Center, or Artifact
  Graph with a second persistence model.
- Merging knowledge graph and business Artifact Graph semantics or IDs.
- Creating a generic dashboard with manually entered KPI values.
- Claiming an LLM inference, scheduled job, proposal or external execution
  completed when no durable record proves it.
- Introducing Metabase or Superset as the Phase 1 interaction surface. Those
  are possible Phase 2 consumers of stabilized operations contracts.

## 4. Authority, Scope And Isolation

| Data domain | Authority | Cockpit responsibility |
| --- | --- | --- |
| DBOS Mission, diagnosis, artifacts, execution, verification, memory | Project Artifact Graph | Read project-scoped lineage and health |
| A/B/C/D source, page, method, output, feedback, lineage | Growth/Wiki repository and Vault | Read conversion, quality, reuse and provenance |
| Raw source material and Vault files | Immutable source record / user filesystem | Expose only authorized metadata, references and approved preview paths |
| Search indexes and graph views | Rebuildable projections | Never treated as authority |
| Schedules and runs | Knowledge runtime ledger | Show actual freshness, failure and unavailable state |

`knowledge_projects` becomes tenant-scoped before a portfolio API exists.
Legacy rows are explicitly backfilled to `DEFAULT_TENANT_ID`; new records carry
the request tenant. An admin may see only projects in its tenant. Project keys,
project readers and project admins may read exactly their bound project. Reader
and project-reader roles remain read-only.

The visualization joins domains only by persisted, scoped references: project
ID, mission ID, artifact parent IDs, run references, runtime `source_ids`,
`method_ids`, and persisted growth lineage. An absent link is shown as absent,
not inferred from labels or generated prose.

## 5. Operational Metrics

Every aggregate returns a generated timestamp, source coverage and an explicit
`unavailable` or `insufficient_sample` reason when the required records do not
exist.

| Metric | Calculation from durable records | Forbidden interpretation |
| --- | --- | --- |
| Asset growth | Created records grouped by A source, B page, C method, D output, feedback/memory and time bucket | Counting generated text as verified value |
| Quality state | `verified`, `pending_validation`, `requires_attention` based on publication, accepted/verified outcome, lint/eval, citation, stale/orphan/contradiction and failure records | A fabricated single "knowledge score" |
| Reuse value | Count of persisted output, context or mission references to an approved/published method or memory | Treating a view or retrieval attempt as business success |
| Risk debt | Open DBOS risks/gaps, evidence gaps, failed/unverified executions, stale/orphan/citation debt and unresolved failures | Hiding risks because a SOP exists |
| Agent evolution | Verification pass rate, median persisted execution attempt, routing holdout outcome, knowledge evaluation series and context-compaction occurrences; every rate or median requires at least three persisted observations, including within each rendered time bucket | Calling unmeasured behavior "accuracy" or presenting a one-run result as an improvement trend |

The Phase 1 action queue has a frozen priority order: critical/high unresolved
risk; missing evidence or failing verification; unverified execution; critical
unvalidated assumption; pending proposal; stale/orphan/contradictory knowledge;
then lower severity maintenance. Ties use severity, oldest unresolved timestamp,
and stable ID. Each item names the underlying records and recommended existing
action; it never auto-publishes or executes work.

## 6. Functional Requirements

### FR-1 Portfolio And Project Operations Views

- An admin can select tenant portfolio or a project. Portfolio cards/table show
  only authorized project metadata, asset movement, quality state, risk debt,
  freshness, and highest-priority action.
- A project cockpit provides current state, interval selector, mission filter,
  trends, action queue, quality distribution and drill-down to existing detail
  workspaces.
- No frontend client loops through project IDs to synthesize a portfolio. The
  server applies tenancy and authorization before aggregation.

### FR-2 Explainable Lifecycle Projection

- Render a bounded React Flow projection with semantic lanes: Business
  Problem/Mission, Assumption, Risk/Constraint, Method/Dynamic SOP,
  Validation, Memory/Feedback; evidence/source records form a supporting
  evidence rail.
- Use only persisted edges and redacted runtime context references. Nodes show
  type, status, confidence when the authoritative artifact supplies it, and
  connection count.
- Support project, mission, type, status, relation and time filters. Truncation
  and missing endpoints are visible, never silently omitted.

### FR-3 Operational Review Actions

- An action opens the exact existing proposal, source, task, execution,
  verification, method/output or mission inspector.
- Authorized proposal publish/reject/lint controls reuse the established API
  and refresh from the server result. The cockpit adds no duplicate mutation
  state machine.
- Actions unavailable to the current role are visible as read-only context with
  a truthful reason, not a disabled control that implies hidden success.

### FR-4 Agent And Knowledge Health

- Trend charts group a bounded, selectable time period; zero, unknown, failed,
  stale and unavailable states remain distinguishable.
- The system may show verification and holdout rates only with sufficient
  persisted sample records. It must not relabel model calls, generated content,
  or queued work as verified outcomes.
- A late/missing scheduler, unavailable model, failed capture or absent Vault
  remains an operational alert rather than a healthy zero.

### FR-5 API And MCP Read Model

- REST exposes tenant portfolio, project cockpit, bounded lifecycle graph and
  action queue through typed read-only projections.
- MCP exposes equivalent authorized read tools; REST remains the policy owner.
  It cannot bypass tenant/project checks, raw-content redaction or existing
  proposal/execution gates.

## 7. UX And Visual Requirements

`Operate` becomes the first-class entry to the new Knowledge Operations
Cockpit. Existing Knowledge Workspace remains the source/Wiki/review surface;
Business Control Center remains the mission execution detail surface.

1. **Top bar:** scope switcher, project/mission selector, time range, data
   freshness and data-coverage disclosure.
2. **Decision strip:** verified reusable assets, pending validation, risk debt,
   open review actions and explicit unavailable state.
3. **Action queue:** a focused, ranked list with source, effect, owner scope
   and a direct drill-down.
4. **Value and quality:** one comparable asset-growth chart and one clear
   quality/risk composition chart, not a column of disconnected miniature
   charts.
5. **Lifecycle explorer:** semantic lanes, filters, selected-node inspector
   and source-to-feedback traceability.
6. **Agent evolution:** a succinct series for verification/attempt/holdout
   evidence, with insufficient-sample treatment.

Desktop uses a composed operations workspace with stable dimensions and an
inspector panel. Mobile moves filters into a drawer and stacks summaries,
charts and graph without horizontal overflow. Semantic colors distinguish
verified, pending, warning, critical and unavailable conditions. Motion only
helps orientation and respects `prefers-reduced-motion`.

## 8. Quality, Security And Performance

- Raw source bodies, prompts, credentials, provider payloads and cross-project
  references are never returned by portfolio projections.
- Portfolio endpoints are tenant and role filtered before aggregation; a caller
  cannot discover another project through a count, graph edge or error message.
- Aggregation period is bounded; graph endpoints are paginated/bounded and
  return truncation metadata. The frontend never requests unbounded lineage.
- Action ranking is deterministic and testable. Time series and derived states
  carry their source count and query interval.
- The operations UI has loading, empty, permission, offline, unavailable and
  error states. A stale success card cannot remain visible after a failed
  refresh.

## 9. Acceptance Criteria

1. An admin with two tenant projects receives only those projects in the
   portfolio; a project-scoped key cannot access portfolio or another project.
2. A project cockpit computes counts, quality and actions from fixture records
   spanning source, Wiki, method, output, Artifact Graph, execution and
   feedback, with no mocked fallback values.
3. A user can traverse one active risk from Mission to evidence/assumption,
   Dynamic SOP/method, verification result and feedback/memory in the graph.
4. A pending proposal can be opened, linted/published/rejected through the
   existing governed flow; the cockpit refreshes only after the actual server
   response.
5. No sample data produces a fabricated agent accuracy or green health state;
   the UI labels insufficient data and unavailable dependencies explicitly.
6. Desktop and mobile browser tests prove charts and graph render nonblank,
   controls are accessible, text/actions do not overlap, and unauthorized data
   is absent.
7. Existing DBOS, Wiki/Growth, MCP transport and Artifact Graph regressions
   remain green.

## 10. Phase 2 Boundary

Once the operations contracts and metric meanings are stable, expose a
versioned export/semantic model to Metabase or Superset for department,
portfolio and historical BI. That layer supplements the cockpit; it must not
become an alternative authority or write path.
