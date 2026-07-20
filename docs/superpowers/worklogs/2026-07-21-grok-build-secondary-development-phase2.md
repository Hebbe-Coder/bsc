# Grok Build Secondary Development Phase 2-4 Worklog

**Date:** 2026-07-21
**Source:** `C:\Users\34216\Downloads\grok-build-main.zip`
**Spec:** `docs/superpowers/specs/2026-07-21-grok-build-secondary-development-phase2.md`

## Current Progress

- [x] Extracted the archive to a temporary read-only analysis directory.
- [x] Confirmed the workspace contains 2,736 files and the relevant Rust crates
  for the TUI, PTY harness, chat state, compaction, plugins, hooks, MCP and tool
  protocol layers.
- [x] Extended the prior architecture report with the requested four areas.
- [x] Created the Phase 2 implementation Spec.
- [x] Implement context policy contracts.
- [x] Implement safe Skill manifest discovery.
- [x] Implement MCP compatibility metadata/normalization.
- [x] Implement the React terminal projection.
- [x] Run focused and full acceptance gates.
- [x] Emit live capability lifecycle events from BusinessRuntime.
- [x] Persist Skill executions and expose history across process restarts.
- [x] Connect Skill Market to backend manifests and execution.
- [x] Implement MCP JSON-RPC HTTP and bidirectional SSE.
- [x] Add the context-policy selector to the Compiler workspace.
- [x] Run live HTTP/SSE, restart-persistence, Windows isolation, and browser UI
  acceptance checks.
- [x] Re-audit Grok pager interaction, layout, rendering, theme, and test
  architecture against the browser workspace.
- [x] Replace the flat workspace with a responsive runtime control room and
  connect the visible controls to real orchestration and Skill execution.

## Evidence Map

| Area | Grok source evidence | BSC target |
| --- | --- | --- |
| Terminal | `xai-grok-pager`, `xai-grok-pager-render`, `ptyctl`, PTY harness | React reducer + orchestrator SSE terminal projection |
| Context | `xai-chat-state`, `xai-grok-compaction`, token estimation | Existing prompt budget plus fresh/fork/resume policies |
| Skills | `xai-grok-plugin-marketplace`, `xai-hooks-plugins-types`, hooks | Safe project-local manifests plus provenance |
| MCP | `xai-grok-mcp`, `xai-computer-hub-mcp-adapter`, tool protocol | Typed compatibility profile and result normalization |
| Product UI | `app_view`, `agent_view/render`, prompt widget, `groknight`, PTY UI tests | Responsive control rail, mission composer, terminal stream, result inspector |

## Engineering Decision

The first implementation slice stays inside the existing FastAPI/React
architecture. It ports behavior contracts, not Rust implementation details or
an arbitrary remote-shell service. Every new capability must be connected to an
existing runtime/API path and covered by a focused regression test.

## Delivered Changes

### Context

- Added `ContextManager`, `ContextPacket`, `ContextUsage`, and explicit
  `fresh/fork/resume` policy handling.
- `fresh` preserves the original request text; inherited context is bounded,
  prioritized, and appended before the current request for fork/resume.
- API validation is fail-closed for missing parents, non-terminal resume,
  cross-browser access, and explicit cross-project inheritance.
- Runtime draft persistence now preserves tenant, project, browser owner,
  creation time, event sequence, and current stage after projection.

### Skills

- Added typed manifest models and safe filesystem discovery with a configured
  root, size limit, canonical path check, and symlink rejection.
- `/api/skill/list` now includes built-in and project-local provenance,
  version, inputs, outputs, entrypoint, and executable state.
- Execution is connected to existing chain classes through an allowlisted
  `chain:` entrypoint. Manifest prompt bodies participate in the existing LLM
  policy; arbitrary Python/Shell entrypoints remain non-executable.
- Added the working `business-discovery` project skill example.
- Added database-backed Skill execution records with status, result/error,
  params, provider, cache status, manifest revision, and timestamps.
- Added `/api/skill/history`; execution lookup now falls back to durable state
  after process restart. Cache clearing also removes the matching execution
  history.
- `SkillMarket` discovers backend manifests and `SkillManager` routes Skills
  without a local implementation through `/api/skill/execute`.

### MCP

- Added typed `McpCompatibilityProfile`, `McpToolResult`, and
  `McpContentBlock` contracts.
- The profile exposes supported JSON-RPC methods, stdio, streamable HTTP, SSE,
  API-key/Bearer auth, and subprocess limits. OAuth remains explicitly
  unsupported.
- Added normalization for text, image, resource/resource-link, structured,
  and error results, plus the `bsc_mcp_compatibility_profile` FastMCP tool.
- Added `/api/mcp`, `/api/mcp/compatibility`, `/api/mcp/sse`, and
  `/api/mcp/messages/{session_id}` with initialize, ping, tool discovery, tool
  calls, notification handling, JSON-RPC errors, and SSE session cleanup.
- Live testing exposed that the prior 512MB Windows Job Object limit killed a
  valid domain analyzer before it could emit JSON. The default is now 1024MB,
  documented in `.env.example`, with a real Windows subprocess regression test
  and a diagnostic `worker_terminated` error.

### Visual terminal

- Added live `capability.started`, `capability.completed`, and
  `capability.failed` events with parent stage, execution, artifact, retry, and
  model-usage metadata. Result projection remains as a compatibility fallback
  for runners that do not accept an event sink.
- Added a Zustand-backed ordered event reducer with a 500-event bound,
  per-session sequence tracking, duplicate/stale rejection, and cross-session
  isolation.
- Added `AgentTerminal` and wired it to the same credentialed SSE stream used
  by the dashboard. It renders sequence, time, stage, event type, messages,
  structured payloads, error/cancel states, and responsive mobile layout.
- Added a real Compiler workspace control for Fresh, Fork, Resume, and parent
  session id. Browser checks confirmed the terminal, all three policies, and
  the conditional parent input render in the running Vite application.

### Product workspace and interaction

- Re-read the upstream pager rather than copying its terminal appearance. The
  implementation follows its durable interaction contracts: input stays in a
  dedicated composer, rendering is a projection of state rather than a timer,
  runtime actions are visible next to their consequence, and keyboard hints
  only advertise a real action.
- Replaced the single-line input and two empty panels with a three-region
  workspace: profile/context/capability rail, multiline mission composer plus
  event terminal, and a sticky result inspector. The layout collapses to an
  explicit mobile sequence at 390px.
- Built a neutral dark surface system using the upstream GrokNight approach:
  gray foundations, restrained cyan/blue navigation, green only for the primary
  run action, and amber/rose for runtime states. Legacy light result widgets are
  normalized inside the inspector so output remains part of one product.
- Exposed the existing backend Skill registry as an interactive catalog that
  searches manifests, shows source/version/execution permissions, invokes an
  approved Skill against the current mission, and renders the durable execution
  result. The composer passes its active text or saved session mission so the
  catalog does not silently run without context.
- Corrected Auto mode matching to use English word boundaries. `onboarding`
  no longer matches the `board` signal and therefore cannot accidentally start
  a board review.
- Replaced the stale UI-only six-stage rail with the eight actual capability
  lifecycle names emitted by `BusinessRuntime`, keeping the progress display
  truthful to SSE events.

## Verification Evidence

- Focused contract tests: context, Skill registry/execution, MCP
  normalization, runtime capability events, and frontend reducer all pass.
- Focused Phase 3 suite: `33 passed` before the live-resource fix; MCP runner
  and HTTP regression after the fix: `8 passed`.
- Final full Python suite: `646 passed, 3 skipped, 3 warnings` from 649
  collected tests. The three skipped cases require PostgreSQL or external
  real-model credentials.
- Frontend: `npm run check` passed; `npm run lint` passed with 0 errors and
  195 existing warnings; `npm run build` passed with 1,833 modules transformed.
- Quality: `scripts/quality_inventory.py --root .` reported no encoding risks
  or unreachable Python modules; `git diff --check` passed.
- Live MCP: initialize, tools/list, compatibility tool call, and an isolated
  `analyze_domain` call passed over `/api/mcp`; bidirectional SSE returned a
  JSON-RPC ping response through the generated session endpoint.
- Live Skill: `business-discovery` completed with the mock provider and
  execution `exec-371ce1f0` remained queryable after two API process restarts.
- Live runtime: session `ff2813136535` emitted 20 ordered events, including 8
  capability start/completion pairs, and terminated with `pipeline.completed`.
- Browser: the Vite workspace rendered Compiler, Fresh/Fork/Resume, Runtime
  terminal, the conditional parent-session input, and the responsive 390px
  control room without a load failure. A real Compiler session
  (`0dd12824be0d`) emitted 20 ordered runtime events and reached
  `pipeline.completed` through the new UI. A project-local `Business Discovery`
  Skill was selected in the new catalog and completed through the approved
  backend route with its result rendered in the dialog.

## Residual Non-Goals

- The terminal is a controlled runtime-event projection, not an arbitrary PTY
  or shell service.
- OAuth remains explicitly unsupported; API-key and Bearer authentication are
  implemented for the HTTP/SSE MCP surface.
- Arbitrary Python, shell, or downloaded Skill entrypoints remain disabled;
  only allowlisted `chain:` entrypoints execute.

## Final Acceptance Update

The implementation is ready to commit locally. Remote push and CI execution
remain separate release actions and are intentionally not performed by this
task without explicit authorization.
