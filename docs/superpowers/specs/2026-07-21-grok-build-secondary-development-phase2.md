# Grok Build Secondary Development Phase 2-4

**Status:** Implemented and verified
**Date:** 2026-07-21
**Source:** `C:\Users\34216\Downloads\grok-build-main.zip`
**Related report:** `docs/superpowers/specs/2026-07-20-grok-build-architecture-and-secondary-development.md`

## Objective

补充 Grok Build 的可视化终端界面、上下文管理、Skill 插件生态和 MCP
兼容层分析，并把与现有 BSC FastAPI/React/BusinessRuntime 边界匹配的部分
落地。目标是获得相同的工程行为契约，不把 Rust TUI 或 Grok 专有服务直接
复制进 BSC，避免形成不能运行的平行壳层。

## Evidence From Grok Build

### Visual terminal

- `xai-grok-pager` owns the full-screen Ratatui application, prompt editor,
  dashboard, modal state, scrollback, tool blocks, task panes, and settings.
- `xai-grok-pager-render` separates terminal probing, ANSI/Markdown/code/image/
  Mermaid rendering, hyperlinks, themes, selection, and safe buffers from the
  application state.
- `ptyctl` and `xai-grok-pager-pty-harness` provide a real terminal process,
  scripted input, screen snapshots, scroll invariants, resize storms, and
  persistence tests. The UI is verified through behavior, not only component
  snapshots.
- The state flow is `Input/ACP event -> Action -> reducer -> Effect ->
  TaskResult -> Action`; rendering never owns runtime work.

### Product interaction and visual language

- The pager keeps a dedicated prompt strip, scrollback, contextual shortcuts,
  overlays, queues, task panes, and optional timeline in one stateful layout.
  Input does not disappear when runtime activity changes.
- `AgentView::draw` computes layout from current state and delegates rendering
  to focused widgets. Its explicit prompt height, terminal-size handling,
  viewport/timeline rules, and focused-input state are a behavioral contract,
  not a decorative TUI pattern.
- The GrokNight theme is a neutral grayscale ramp with deliberate semantic
  accents: blue/cyan for navigation and live state, green for success, amber
  for warnings, and rose/red for errors. It avoids broad gradient surfaces.
- The PTY suite verifies queueing, interjection, selection, resize, focus,
  prompt input, scrolling, modal dismissal, and streaming behavior. The BSC
  browser workspace therefore needs observable state and browser acceptance,
  not screenshot-only styling.

### Context management

- `xai-chat-state` is an actor with exclusive mutable conversation state,
  persistence, usage ledger, rewind capture, tool-call repair, and event
  notifications. Readers query a handle instead of mutating shared maps.
- `xai-grok-compaction` has separate full-replace, history, inter-turn, and
  intra-turn strategies. Selection never splits an assistant tool request from
  its tool results.
- Fork, fresh, and resume are explicit policies. Fork removes parent-only
  instructions and old repeated context; resume validates identity instead of
  silently starting a new session.

### Skill/plugin ecosystem

- `xai-grok-plugin-marketplace` loads an indexed catalog first and falls back to
  filesystem scanning. Entries describe skills, hooks, agents, MCP, keywords,
  domains, version and provenance.
- Marketplace paths are parsed and canonicalized before joining a root, with
  symlink escape checks. Installation and discovery are separate operations.
- `xai-hooks-plugins-types` is the typed component contract; hooks and skills
  are discoverable data until an execution policy explicitly enables them.
- Before this implementation, BSC's `SkillManager` was only a client-side
  execution coordinator, backend `/api/skill/list` was hardcoded, and execution
  state was process-local. Phase 2 added manifest discovery and provenance;
  Phase 3 connected the market to the backend registry and made execution
  history durable.

### MCP compatibility layers

```text
Transport (stdio / HTTP stream)
        -> JSON-RPC initialize, tools/list, tools/call
        -> typed tool/content normalization
        -> capability/auth/isolation policy
        -> BSC capability executor and event projection
```

- `xai-grok-mcp` owns wire/server discovery, HTTP/SSE, OAuth configuration,
  credentials and ACP transport concerns.
- `xai-computer-hub-mcp-adapter` uses an `McpTransport` seam, performs
  initialize plus tools/list, creates one typed handler per tool, and maps
  text/image/resource content back to a common tool output wire type.
- BSC already has a stdio FastMCP server and an isolated subprocess runner.
  Phase 2 added an explicit compatibility profile and normalization seam.
  Phase 3 adds concrete JSON-RPC HTTP and SSE transports over the same isolated
  tools, without coupling business code to FastMCP internals.

## Target BSC Architecture

```mermaid
flowchart LR
    Input["React input / SSE / MCP"] --> Reducer["Workspace event reducer"]
    Reducer --> Terminal["Visual terminal projection"]
    Reducer --> Dashboard["Business dashboard"]
    API["FastAPI orchestrator"] --> Event["Durable typed events"]
    Event --> Reducer
    Runtime["BusinessRuntime"] --> Event
    Runtime --> Context["Context policy + budget"]
    Runtime --> Skills["Manifest skill registry"]
    Runtime --> MCP["MCP compatibility layer"]
```

### Canonical contracts

1. `ContextPolicy`: `fresh`, `fork`, `resume`.
2. `TerminalEvent`: a renderable projection of a typed runtime event; it is
   append-only, sequence-ordered, and never inferred from a timer.
3. `SkillManifest`: id, version, description, source, inputs, outputs, prompt
   body, hooks, agents and MCP references; filesystem discovery is fail-closed
   for unsafe paths.
4. `McpCompatibilityProfile`: transport, protocol methods, content blocks,
   auth mode and isolation mode supported by the BSC adapter.

## Execution Plan

### Phase A: analysis and contracts

- [x] Extract the archive and map the relevant crates.
- [x] Extend the architecture report with terminal, context, plugin and MCP
  evidence.
- [x] Define this implementation Spec and its acceptance gates.

### Phase B: backend foundations

- [x] Add explicit context policies and deterministic fork/resume normalization
  on top of the existing prompt budget.
- [x] Add safe Skill manifest discovery with built-in and project-local
  provenance, without executing untrusted manifest content.
- [x] Add a typed MCP compatibility profile and content normalization seam.
- [x] Add focused contract tests for all three foundations.

### Phase C: visual terminal workspace

- [x] Extend the existing orchestrator event contract with renderable tool,
  child and terminal metadata without changing terminal job semantics.
- [x] Add a React event reducer and terminal-style live panel wired to the same
  SSE stream as the dashboard.
- [x] Preserve reconnect, stale-event rejection, error, cancellation, and
  mobile layout behavior.

### Phase D: acceptance

- [x] Python focused and full regression tests pass.
- [x] TypeScript check, ESLint and production build pass.
- [x] Contract tests prove context isolation, manifest path safety, MCP result
  normalization, and terminal event ordering.
- [x] Worklog records implementation evidence and residual non-goals.

### Phase E: runtime convergence and transport delivery

- [x] Emit `capability.started`, `capability.completed`, and
  `capability.failed` while BusinessRuntime is executing, with persisted SSE
  replay as the transport boundary.
- [x] Persist Skill execution state in the configured database and expose
  queryable execution history across process restarts.
- [x] Connect the frontend Skill market to backend manifests and the approved
  execution endpoint.
- [x] Implement MCP JSON-RPC HTTP plus bidirectional SSE for `initialize`,
  `ping`, `tools/list`, and `tools/call`.
- [x] Add the `fresh/fork/resume` selector and parent-session input to the real
  compiler workspace.
- [x] Prove all paths through unit, full-regression, live HTTP/SSE, process
  restart, Windows Job Object, and browser rendering checks.

### Phase F: product workspace convergence

- [x] Replace the flat shell with a responsive control rail, multiline mission
  composer, terminal projection, and result inspector driven by real state.
- [x] Make context policy and runtime capability states visible without
  inventing a parallel progress model.
- [x] Make backend-discovered Skills searchable, inspectable, and executable
  against the current mission from the main workspace.
- [x] Verify real browser orchestration, Skill execution, mobile layout, and
  auto-mode boundary behavior.

## Non-goals

- Do not vendor the 2,736-file Rust workspace into BSC.
- Do not implement a general-purpose arbitrary shell/PTY service in the first
  phase; the BSC terminal panel is a controlled runtime-event projection.
- Do not execute arbitrary code from a downloaded Skill manifest.
- Do not claim OAuth support. HTTP JSON-RPC and SSE are implemented and tested,
  but no OAuth client flow is registered.
- Do not modify the already accepted platform-convergence lifecycle semantics.

## Acceptance Criteria

1. A user can see live, ordered runtime activity in a terminal-style panel and
   the panel reconnects from the last event sequence.
2. A capability can receive a bounded `fresh`, `fork`, or `resume` context with
   no parent-session leakage and observable budget metadata.
3. Project-local Skill manifests appear through the existing skill API with
   source/provenance and cannot escape their configured root.
4. MCP compatibility is represented by typed metadata and content normalization;
   text, image, resource and error results preserve their meaning.
5. Existing orchestrator, dashboard, production LLM policy and MCP stdio
   behavior remain backward compatible.
6. MCP clients can initialize, enumerate tools, call a real isolated tool over
   HTTP, and exchange JSON-RPC messages over a live SSE session.
7. Skill executions remain queryable after the API process restarts, and the
   frontend market discovers project-local manifests from the backend.

## Implementation Evidence

- `app/core/context_policy.py` implements bounded `fresh`, `fork`, and
  `resume` packets with observable usage metadata. The API validates parent
  session identity, terminal state, tenant, project, and browser scope.
- `app/skills/manifest.py` and `app/skills/registry.py` discover typed
  `SKILL.md` manifests, reject unsafe paths and symlink escapes, expose
  provenance through `/api/skill/list`, and execute only approved `chain:`
  entrypoints. `skills/business-discovery/SKILL.md` is a working project
  manifest example.
- `app/skills/execution_store.py` stores running, completed, failed, cached, and
  manifest-revision metadata. `/api/skill/history` and execution lookup survive
  process restarts; `SkillManager` and `SkillMarket` consume backend manifests
  and execute approved backend-only Skills.
- `app/mcp/compatibility.py` reports actual stdio, streamable HTTP, SSE,
  API-key/Bearer, and subprocess-isolation support. `app/api/mcp_http.py`
  implements JSON-RPC `initialize`, `ping`, `tools/list`, and `tools/call`, plus
  live SSE message routing. OAuth remains explicitly unsupported.
- The Windows Job Object default was raised from 512MB to 1024MB after live
  testing proved the lower limit killed a valid domain-analysis worker. A real
  subprocess regression test now protects the runnable default.
- `app/orchestrator/runtime_engine.py` emits ordered live capability start,
  completion, or failure events with parent-stage and execution metadata. The React
  `terminalEventReducer` rejects duplicate, stale, and cross-session events;
  `AgentTerminal` renders the same SSE stream with mobile-safe layout.
- `ContextPolicyControl` exposes Fresh, Fork, and Resume in the actual Compiler
  workspace and sends `context_policy` plus `parent_session_id` to the API.
- The React workspace is now a product-level projection of the runtime: the
  left rail shows real BusinessRuntime capabilities, the central composer owns
  multiline mission input and keyboard submission, `AgentTerminal` projects
  SSE events, and the inspector groups decision evidence. The design follows
  GrokNight's neutral terminal palette rather than adding a fake Grok shell.
- `SkillMarket` now opens from the workspace header, discovers the backend
  manifest registry, reveals provenance/version/permission metadata, and runs
  a selected approved Skill with the active or persisted mission. Auto mode
  uses bounded English word matching so incidental substrings cannot select a
  wrong workflow.
- Live evidence: a mock-runtime orchestration emitted 20 ordered events,
  including 16 capability lifecycle events, and ended in
  `pipeline.completed`; MCP HTTP, real isolated `analyze_domain`, bidirectional
  SSE, Skill process-restart persistence, and browser rendering all passed.
- Verification: full Python regression, `npm run check`, `npm run lint` with
  zero errors, `npm run build`, `scripts/quality_inventory.py`, and
  `git diff --check` pass. Exact final counts are recorded in the worklog.
