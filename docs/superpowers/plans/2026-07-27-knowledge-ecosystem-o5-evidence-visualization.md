# O5 - Evidence Visualization And Dual Views

## Goal

Expose authorized evidence, extraction and reference state through BSC and
Obsidian views that support review and action rather than presentation-only
charts.

**Depends on:** O3.
**May run in parallel with:** O4 using frozen fixture contracts.
**Blocks:** O6 and E1.

## Owned Surfaces

**Create:** evidence workspace read-model endpoints, typed frontend client,
store slices, components and browser tests.
**Modify:** Knowledge Workspace, managed Obsidian view templates and only the
read-only MCP evidence tools required by the frozen API.
**Do not modify:** DBOS graph semantics, operations portfolio authorization,
extractor persistence, source mutation paths, user-authored Vault layout or
Artifact Graph storage.

## Interaction Contract

- Evidence Atlas shows bounded source/extraction/review/freshness distributions
  with denominator, time window, filters, units and no-sample state.
- Reference Browser opens one authorized source, page, URL, citekey or typed
  anchor. It renders metadata and a redacted availability descriptor, not raw
  body content by default.
- Table Explorer paginates rows and links each cell/view to table/extractor
  provenance. Image/Figure Inspector exposes safe region coordinates and OCR
  uncertainty. Research Timeline shows durable timestamps only.
- Reference Network and Workspace Map use React Flow for typed persisted edges
  with filters, truncation notices and keyboard-accessible list alternatives.
- Every visual interaction must open an exact persisted target within the same
  project. Stale, restricted, missing and unavailable states remain visible.

## Input, Output, Permissions, And Redaction

- **Inputs:** O2's frozen metadata vocabulary, O3 route-state vocabulary and
  O4 metadata-only evidence records or their declared fixtures. The UI may not
  infer a positive state from absent records or turn a fixture into a real
  capture claim.
- **Outputs:** bounded, filterable summaries, graph nodes/edges, timeline
  entries and exact project-local drill-down targets. Every aggregate carries
  its denominator, window, filters and `no_sample`/unavailable state when
  applicable.
- **Access:** REST, MCP and browser queries use the same server-side project
  authorization. The client receives only authorized project IDs and cannot
  supply a cross-project record ID to escape a selection boundary.
- **Redaction:** detail views are metadata-only by default. No raw source,
  derivative text, OCR/transcript content, prompt, provider response, local
  path, credential or third-party plugin configuration is rendered or emitted
  through REST, MCP, browser state, telemetry, screenshots or tests.

## Test-First Tasks

1. First write focused failing tests for API redaction, tenant/project scope, pagination,
   no-sample behavior, anchor resolution, graph bounds, stale selection and
   responsive rendering.

## Implementation Tasks

2. Implement one authorized read service for evidence assets, extraction
   artifacts, tables, references and capability state. REST and MCP delegate
   to it; neither route creates or changes evidence.
3. Add Evidence Atlas, Reference Browser, Table Explorer, Image/Figure
   Inspector, Research Timeline, Reference Network and Workspace Map to the
   existing Knowledge Workspace using ECharts and React Flow.
4. Add accessible table/list alternatives, focus behavior, visible filter
   state, reduced-motion support and exact BSC/Obsidian drill-down links.
5. Generate lightweight Dataview/Bases mirror views from O2's metadata
   registry. They expose navigation only and cannot override BSC state.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_evidence_api.py tests/mcp/test_knowledge_evidence_tools.py -q
npm run test:frontend -- --run src/api/knowledgeEvidenceApi.test.ts src/components/knowledge/EvidenceWorkspace.test.tsx
npm run check
npm run build
```

Playwright must prove desktop and `390x844` behavior: nonblank charts/graph,
no horizontal overflow, keyboard access, empty/unavailable states and exact
record selection for a chart value, table cell, image region, URL and edge.

## Failure, Rollback, Worklog, And Handoff

Hide evidence views behind their feature flag while retaining read models and
records. Hand O6 screenshot paths, browser assertions, API examples, known
capability gaps and accessibility results. The handoff also carries changed
files, API schema revision, fixture/real-data distinction, exact acceptance
output, feature-flag state and the narrow rollback action. The shared worklog
records API and browser commands, exit results, viewport, authorized
fixture/record IDs, graph/chart behavior, overflow/accessibility outcome,
unavailable capability state, deviation, and rollback action. A screenshot or
rendered chart alone is not evidence of a working drill-down or real-data claim.
