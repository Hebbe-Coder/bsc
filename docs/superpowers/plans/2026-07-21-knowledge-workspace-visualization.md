# P7 - Knowledge Workspace And Visualization Implementation Plan

**Goal:** Add a real, fast, inspectable Knowledge workspace to BSC's active `UnifiedWorkspace`, using backend-backed vault/page/proposal/run/graph data instead of placeholder cards or decorative visualizations.

**Architecture:** Preserve the current single React application and integrate a Knowledge mode/view rather than introducing a competing shell. Build a typed API client and small feature-local components. Use existing React Flow for the relationship graph, existing ECharts for trends, Lucide icons for controls, and the BSC runtime event stream for live maintenance state.

**Depends on:** P6. **May begin design/type scaffolding after P4 but must not mock a new backend contract.** **Do not modify:** backend behavior, existing orchestration event reducer semantics, unrelated presentation-editor components, or global visual assets.

## Owned Files

**Create:** `src/api/knowledgeWorkspaceApi.ts`, `src/store/knowledgeWorkspaceStore.ts`, `src/components/knowledge/KnowledgeWorkspace.tsx`, `src/components/knowledge/VaultTree.tsx`, `src/components/knowledge/WikiReader.tsx`, `src/components/knowledge/SourceInspector.tsx`, `src/components/knowledge/ProposalDiff.tsx`, `src/components/knowledge/KnowledgeRunPanel.tsx`, `src/components/knowledge/KnowledgeGraph.tsx`, `src/components/knowledge/KnowledgeHealth.tsx`, `src/components/knowledge/DistillationBrowser.tsx`, and focused component/unit tests following the repository's current frontend test approach.

**Modify:** `src/components/UnifiedWorkspace.tsx`, `src/index.css`, and existing frontend API-policy tests only where they must recognize the new governed endpoints.

## Interaction Contract

### Desktop

- The workspace has a persistent mode switch between current orchestration and Knowledge, not a hidden secondary route.
- Knowledge mode uses stable three columns: vault/project tree, primary page/diff/run surface, and evidence/health inspector. Resizing content must not move controls or cause overlapping text.
- The top utility bar exposes project status, sync/maintenance action, scheduler state, and context-pack/distillation access. Use icons with accessible names/tooltips where compact controls are used.
- Selecting a graph edge, citation, source, proposal operation, or run event navigates to the corresponding real record in the adjacent panel.

### Mobile

- Use explicit tabs/drawers for Tree, Page, Evidence, and Activity. Preserve the active selection while changing panel.
- Diff, source references, long paths, error messages, and charts must wrap or scroll within their own container; no horizontal viewport overflow.
- Respect reduced motion and keyboard focus behavior already established by the workspace.

### Visual Language

- Continue the existing restrained BSC studio palette and semantic status colors. Avoid a separate fake terminal, broad gradients, decorative graph backgrounds, or stacked cards.
- Graph colors encode node type/status and all labels map to actual entity names. Health charts show data ranges, no synthetic KPI values.
- Markdown renders frontmatter-derived metadata, citations, links, Mermaid/code blocks only after safe rendering/sanitization choices are confirmed; raw HTML cannot execute.

## Task 1: Typed Client And State

- [x] Add failing tests for request construction, project ID propagation, API error normalization, SSE reconnection/event de-duplication, and stale project response rejection.
- [x] Implement TypeScript interfaces directly from P6 response/event contracts. Do not use `any`, invented mock values, or a local parallel data model.
- [x] Implement feature-local Zustand state for selected project/page/source/proposal/run, loading/error state, graph filters, activity sequence, and mobile active pane.
- [x] Reuse the existing EventSource lifecycle discipline: close prior streams on project/run change, reject duplicate/stale/cross-run events, and show terminal state from backend events.
- [x] Verify with `npm run check` and the focused frontend contract tests.

## Task 2: Vault, Page, Evidence, And Proposal Review

- [x] Implement tree loading/expansion, path-safe labels, empty vault, unconfigured vault, permission denied, and source-sync status states.
- [x] Render selected Markdown page with title/frontmatter, backlinks, citations, and source anchors. A citation click opens the immutable source inspector, including origin, hash, trust/policy status, and user-curation distinction.
- [x] Implement proposal comparison as semantic operation list plus readable before/after diff. Publish/reject/retry controls must reflect P6 permission/status and show the returned run/proposal ID.
- [x] Never imply publication while a proposal is validating or queued. Do not allow edit/write controls in raw source panels.
- [x] Add component tests for empty/error/loading, navigation, citation selection, proposal conflict, and writer versus reader control visibility.

## Task 3: Activity, Schedules, And Distillation

- [x] Render run timeline from P6 events/history with source/proposal/gate/diff links and terminal failure reason.
- [x] Show scheduler availability, next run, last result, paused/disabled state, and manual run action. Disabled Celery must read as unavailable, not pending.
- [x] Render weekly folders and the three distillation documents with source cutoff/revision metadata and links back to source/page context.
- [x] Add accessible non-blocking loading states and retry commands for network failure; do not poll aggressively or fabricate activity.

## Task 4: Health Trends And Knowledge Graph

- [x] Render ECharts trends from real health/evaluation data: source throughput, citation coverage, stale/orphan count, proposal/gate success, and evaluation delta. Missing data must render an explicit empty state.
- [x] Build React Flow nodes/edges from P6 graph contract with node type, status, age, and provenance. Support filter by page/source/proposal/edge type/status and fit/reset controls.
- [x] Ensure selecting any node/edge updates the existing selected record rather than opening an unrelated static modal.
- [x] Bound graph rendering for large projects through backend filters/pagination or local visible-node limits; record truncation to the user.
- [x] Test graph filter/navigation, no-data graph, large-graph cap, chart resize, and reduced-motion behavior.

## Task 5: Unified Workspace Integration And Browser Acceptance

- [x] Integrate the feature as a first-class workspace mode, preserving existing Auto/Agent OS/Compiler/Board actions and their tests.
- [x] Ensure mode switch preserves current orchestrator session and knowledge selection independently.
- [x] Run `npm run check`, `npm run lint`, and `npm run build`.
- [x] Use browser acceptance against a real backend fixture: desktop vault-to-citation-to-source-to-proposal flow; live run timeline; graph filtering; weekly output; mobile pane switching; permission/error/unavailable scheduler state.
- [x] Capture the actual verification result in the worklog, including viewport sizes and any accessibility fix.

## Acceptance, Rollback, Handoff

- Every visible page, citation, graph edge, health metric, and run state comes from a typed backend response/event.
- Desktop and mobile flows preserve readable text, focus, action availability, and stable layout.
- Existing orchestration workspace behavior remains available and all TypeScript/lint/build checks pass.
- Rollback removes the Knowledge mode feature flag/component entry only; it cannot remove user vault content or server audit state.
- Handoff P8 with exact browser scenarios, backend fixture requirements, frontend command results, and any known rendering limits.
