# P8 - A/B/C/D Growth Workspace And Visualization Implementation Plan

**Goal:** Evolve the existing Knowledge Workspace into a useful operations surface for evidence, Wiki knowledge, methods, outputs and review using real P7 data, readable provenance and high-signal visualizations on desktop and mobile.

**Architecture:** Preserve the existing `UnifiedWorkspace` and `KnowledgeWorkspace` shell, store and API patterns. Add a stage rail, center reader/diff/timeline/graph view and right inspector. ECharts renders persisted metric series; React Flow renders bounded lineage slices. No mock data is shown after API failure or during an unavailable state.

**Depends on:** P7 for production API; P1-P6 for fixture semantics.
**Blocks:** P9.
**PRD coverage:** FR-16, metrics and AC 18-19.

## Owned Files

**Create:** `src/components/growth/GrowthWorkspace.tsx`, `src/components/growth/GrowthStageRail.tsx`, `src/components/growth/GrowthAssetList.tsx`, `src/components/growth/GrowthInspector.tsx`, `src/components/growth/GrowthFunnel.tsx`, `src/components/growth/GrowthLineageGraph.tsx`, `src/components/growth/GrowthTrends.tsx`, `src/components/growth/GrowthWorkspace.test.tsx`, `src/components/growth/GrowthVisualizations.test.tsx`, `src/components/growth/GrowthLineageGraph.test.tsx`, `src/api/growthApi.ts`, and `src/api/growthApi.test.ts`.

**Modify:** `src/components/KnowledgeWorkspace.tsx`, `src/components/UnifiedWorkspace.tsx`, `src/store/knowledgeWorkspaceStore.ts`, `src/types/index.ts`, `src/index.css` or the existing workspace stylesheet, and app route registration only for the additive growth view.

**Forbidden:** Fake fallback records, changing backend/MCP contracts, hiding permissions or errors, editing business Artifact Graph visuals, dense promotional hero layouts, unbounded graph rendering, or page-wide UI rewrites unrelated to knowledge growth.

## Frozen Interaction Contract

- Stage rail: A Evidence, B Knowledge, C Methods, D Outputs, Review.
- Center view changes by selected stage: list/reader, Markdown/diff, method revision, output preview/evaluation, or review queue/timeline.
- Inspector always exposes provenance, quality, lineage, feedback and permitted actions for the selected asset.
- Persistent project/profile selector and global search retain selection across stage changes when the asset remains available.
- Funnel, quality debt, citation coverage, method success, output acceptance and time trends use API values and show loading/empty/offline/unavailable/error/permission states.
- Graph filters by `source/page/method/output/feedback`, is bounded to the server slice, and supports selection-to-inspector.
- Desktop uses a stable three-pane layout. Mobile uses stage tabs and an inspector drawer without horizontal overflow or overlapping actions.

## Task 1: API Client, Store And Real States

- [x] Write failing component/store tests for project selection, stage switch, list/detail loading, stale selection, pagination, permission denial, offline, unavailable, empty and error responses.
- [x] Implement typed `growthApi` calls for P7 endpoints with abort/stale-response protection and no silent mock fallback.
- [x] Extend the store with stage, selected asset, inspector state, filter/query, pagination cursor and request status while preserving existing Knowledge Workspace state.
- [x] Verify a failed request never leaves stale success metrics presented as current.
- [x] Run `npm run test:frontend -- src/api/growthApi.test.ts src/store/knowledgeWorkspaceStore.test.ts`.

## Task 2: Stage Rail, Reader, Diff And Inspector

- [x] Write failing tests for stage navigation, keyboard focus, asset selection, citation/source opening, proposal diff, method revision selection, output feedback and permission-gated actions.
- [x] Build the three-pane growth surface using existing visual tokens and operational density; keep headings and controls sized for the tool surface.
- [x] Render Markdown/output previews safely with explicit binary descriptor/download states and no arbitrary HTML execution.
- [x] Show source cutoff, method/context revisions, quality findings, feedback and lineage in the inspector; show a truthful unavailable action state.
- [x] Add responsive stage tabs/drawer at narrow width and verify no horizontal overflow or text/action overlap.
- [x] Run `npm run test:frontend -- src/components/growth/GrowthWorkspace.test.tsx src/components/KnowledgeWorkspace.test.tsx`.

## Task 3: Funnel, Trends And Quality Debt

- [x] Write failing tests for API-derived funnel counts, missing series, zero values, date filters, metric tooltips, empty state and API error state.
- [x] Implement ECharts funnel/line/bar views for A-to-B conversion, B citation coverage, C reuse/success, D acceptance/correction/rejection, contradictions, stale/orphan debt and automation freshness.
- [x] Ensure charts have accessible labels/summary, bounded data points, responsive dimensions and nonblank rendering with real fixture values.
- [x] Keep chart colors semantically distinct and readable; do not use decorative gradients or fake activity.
- [x] Run `npm run test:frontend -- src/components/growth/GrowthVisualizations.test.tsx`.

## Task 4: Filterable Lineage Graph

- [x] Write failing tests for node/edge filters, selection, project scope, server bounds, missing endpoint, empty graph, layout resize and loading/error states.
- [x] Implement React Flow graph using P7 slices with node types for source/page/method/output/feedback and relation labels/tooltips.
- [x] Prevent graph slice from silently loading all records; display truncation/bounds in the UI and offer narrower filters.
- [x] Keep this graph separate from the business Artifact Graph route and semantics.
- [x] Run `npm run test:frontend -- src/components/growth/GrowthLineageGraph.test.tsx`.

## Task 5: Accessibility, Motion And Browser Proof

- [x] Test keyboard navigation, visible focus, semantic labels, icon tooltips, reduced motion, contrast, mobile drawer escape and selection retention.
- [x] Add restrained loading/selection transitions only where they preserve task orientation; no motion-only meaning.
- [x] Execute desktop and mobile browser journeys against real P7 fixture data: project -> stage -> asset -> source -> diff -> method/output -> graph -> weekly distillation.
- [x] Capture screenshots only after functional assertions and record chart/graph nonblank checks.
- [x] Run `npm run check`, `npm run lint`, `npm run build`, and `npm run test:frontend`.

## Acceptance Criteria

- A user can move from any output to its method, context, Wiki page and original source in one project-scoped workflow.
- Funnel/trends/graph values are real persisted values, bounded, filterable and clearly unavailable when the API is unavailable.
- Desktop three-pane and mobile stage/drawer workflows have no overlap, horizontal overflow or lost selection.
- Diff, provenance, quality, feedback and permission states are actionable and understandable without fake success.
- Existing Knowledge Workspace and Artifact Graph UI tests/build remain green.

## Rollback Strategy

Hide the growth route/feature flag and keep the existing Knowledge Workspace. Revert only additive frontend components/client/store fields; do not change backend data or existing graph routes.

## Required Handoff

Provide P9 with fixture URL/data IDs, browser command/results, desktop/mobile screenshots, chart/graph pixel proof, accessibility results, known responsive limits and the exact API contract consumed.
