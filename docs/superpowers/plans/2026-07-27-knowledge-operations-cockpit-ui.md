# P5 - Knowledge Operations Cockpit UI

## Goal

Build a decision-oriented Organization/Project cockpit inside
`UnifiedWorkspace` from P4 real data, while preserving existing Knowledge
Workspace and Business Control Center detail workflows.

**Depends on:** P4.
**Blocks:** P6.

## Owned Files

**Create:** `src/components/operations/KnowledgeOperationsCockpit.tsx`,
portfolio/project panels, action queue, lifecycle graph, trend components and
focused tests.

**Modify:** `src/components/UnifiedWorkspace.tsx`,
`src/api/knowledgeOperationsApi.ts`, relevant store state and `src/index.css`.

**Do not modify:** existing Knowledge Workspace/Growth data semantics, DBOS
control-center behavior, backend contracts, raw data rendering or unrelated
Studio layouts.

## Frozen Interaction Contract

- `Operate` opens the cockpit; scope is portfolio for an admin and project for
  every other role. A project/mission/time selector changes only server-backed
  data.
- First viewport answers: verified reusable assets, pending validation, risk
  debt, action count and freshness/coverage.
- Action queue is ranked P2 data and opens the exact existing proposal/source/
  mission/detail route. Mutations reuse existing guarded APIs and refresh after
  response.
- ECharts renders one asset-value growth view, one quality/risk composition
  view and an agent-evidence trend. React Flow renders P3 lanes and inspector.
- Desktop uses stable overview + workspace + inspector dimensions. Mobile
  stacks data and opens filters/inspector in accessible drawers; no horizontal
  overflow, clipped controls or decorative fake graph.

## Tasks

1. Write failing component tests for role scope, loading/empty/error states,
   action selection, unavailable metrics, chart/graph inputs and deep links.
2. Implement typed state/data fetches; avoid stale display after scope/filter
   changes and never seed placeholder metrics.
3. Implement semantic chart colors, accessible data summaries/tooltips,
   deterministic graph lanes, relation/type filters and selected-node
   provenance inspector.
4. Add keyboard focus, icon tooltips, reduced-motion behavior and responsive
   visual regression coverage.
5. Run `npm run test:frontend -- --run src/components/operations src/api/knowledgeOperationsApi.test.ts`, `npm run check`, and `npm run build`.

## Acceptance Criteria

Users can move from portfolio to project, prioritized action, source lineage
and existing review/mission detail without synthetic state. The UI renders
truthful unavailable states and maintains readable layout on desktop and mobile.

## Rollback And Handoff

Hide the new cockpit route and leave all existing workspaces intact. Hand P6
real API fixture IDs, desktop/mobile screenshots, graph/chart nonblank proof
and known responsive limits.
