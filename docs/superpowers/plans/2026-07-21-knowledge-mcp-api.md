# P6 - Knowledge MCP And API Implementation Plan

**Goal:** Expose governed Wiki capabilities to browser and MCP clients while preserving existing BSC knowledge APIs, MCP initialization, HTTP JSON-RPC, SSE, authentication, and project isolation.

**Architecture:** Add a dedicated knowledge-workspace REST router and service adapters over P1-P5 facades. Extend the existing stdio MCP server and HTTP JSON-RPC tool registry with typed Wiki tools. Reuse current authorization dependencies and SSE event semantics; do not create a second transport or permit direct filesystem access from request handlers.

**Depends on:** P4. **Parallel after P4:** P5 and P7. **Do not modify:** raw source files, existing `/knowledge` request/response fields, MCP transport handshake behavior, or Artifact Graph APIs.

## Owned Files

**Create:** `app/api/knowledge_workspace_api.py`, `app/api/knowledge_workspace_sse.py`, `app/mcp/wiki_tools.py`, `tests/api/test_knowledge_workspace_api.py`, `tests/api/test_knowledge_workspace_sse.py`, `tests/mcp/test_wiki_tools.py`, and `tests/mcp/test_wiki_http_contract.py`.

**Modify:** `app/main.py`, `app/mcp/server.py`, `app/api/mcp_http.py`, `app/mcp/compatibility.py` only for accurate capability metadata, `app/knowledge/wiki_service.py`, and existing authorization helpers only for reusable project-scoped dependencies.

## Public API Contract

Keep existing `/knowledge` routes unchanged. Add `/knowledge/workspaces` for mapping/bootstrap/status; `/knowledge/sources` for list/inspect/reprocess/reject; `/knowledge/wiki` for tree/read/history/proposal/lint/graph; `/knowledge/runs` for start/read/retry/stream; `/knowledge/schedules` for configure/pause/run-now; and `/knowledge/distillations` for list/read/generate.

All write endpoints require project admin/write permission. Read endpoints require project read permission. Callers provide `project_id` explicitly; missing scope is validation failure, never a global query. Responses expose typed states, not raw exceptions or absolute filesystem paths.

## MCP Contract

Add `wiki_guide`, `wiki_search`, `wiki_read`, `wiki_propose_update`, `wiki_apply_update`, `wiki_lint`, `wiki_graph`, `wiki_distill`, and `wiki_schedule`. Each input requires project scope and JSON-schema validation. Mutating calls create/queue governed runs/proposals; no tool performs arbitrary filesystem or shell work. Existing text/image/resource normalization remains unchanged.

## Task 1: REST Router And Authorization

- [ ] Add failing route tests for missing project ID, reader/admin permissions, invalid mapping, source transition, proposal conflict, schedule unavailable, and unknown resource IDs.
- [ ] Implement typed request/response Pydantic models without duplicating P1 domain models.
- [ ] Register the router in `app/main.py`; reuse current response envelope and auth conventions.
- [ ] Map service conflicts to actionable status/code and redact sensitive paths, credentials, and internal errors.
- [ ] Keep handlers thin: authorization, request validation, facade call, normalized response.
- [ ] Verify with `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py -q`.

## Task 2: Runs And Server-Sent Events

- [ ] Reuse sequenced orchestrator-style event semantics for knowledge runs: no timer-inferred progress and no process-local-only completion claim.
- [ ] Add capture, eligibility, proposal, validation, publish, lint, distillation, retry, and terminal events with project/run identity and monotonic sequence.
- [ ] Implement replay from durable run/event records. Reconnect resumes after caller sequence and rejects cross-project events.
- [ ] Test ordered replay, reconnect, cancellation, terminal close, permissions, stale sequence, and failure state.
- [ ] Verify with `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_sse.py -q`.

## Task 3: MCP Wiki Tools

- [ ] Add unit tests for input validation, project isolation, read result, proposal-only write behavior, gate error mapping, graph query, and scheduler-unavailable state.
- [ ] Implement tool handlers against the service facade and register them in the existing stdio server.
- [ ] Add matching HTTP JSON-RPC tool specifications/handlers while retaining existing tool names and initialization behavior.
- [ ] Update compatibility profile only to describe actual support; do not claim OAuth or unimplemented protocol features.
- [ ] Verify live JSON-RPC `initialize`, `tools/list`, and every Wiki `tools/call` plus existing tool compatibility using `./.venv/Scripts/python.exe -m pytest tests/mcp/test_wiki_tools.py tests/mcp/test_wiki_http_contract.py -q`.

## Task 4: Contract And Compatibility Regression

- [ ] Freeze frontend-consumable workspace, source, proposal, run, schedule, graph, health, and distillation shapes.
- [ ] Verify HTTP/MCP error results retain actionable non-sensitive message/code pairs.
- [ ] Run current knowledge API and MCP HTTP/SSE regression suites; removing an existing endpoint field blocks release.
- [ ] Record request examples and compatibility evidence in the worklog.
- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py tests/api/test_knowledge_workspace_sse.py tests/mcp/test_wiki_tools.py tests/mcp/test_wiki_http_contract.py -q`, then `./.venv/Scripts/python.exe -m pytest tests/knowledge tests/integration/mcp -q`, and finally `git diff --check`.

## Acceptance, Rollback, Handoff

- Browser/API/MCP callers inspect real project-scoped state but cannot bypass proposal/gate policy.
- SSE replay is ordered and project-isolated; reconnect reports persisted run truth.
- Existing `knowledge_ask`, HTTP/SSE MCP initialization, stdio behavior, and current clients remain compatible.
- Rollback unregisters only new routes/tools/flags and leaves audit/proposal data intact.
- Handoff P7 with stable API/event/error contracts and fixtures; hand P8 API/MCP compatibility evidence.
