# P7 - Growth REST, SSE And MCP API Implementation Plan

**Goal:** Expose the A/B/C/D/review lifecycle through project-scoped, backward-compatible REST, SSE and MCP operations with consistent authorization, pagination, idempotency and audit behavior.

**Architecture:** Extend the current knowledge API, workspace API, SSE event stream and `app/mcp/wiki_tools.py`/server dispatch. New routes call P1-P6 services; mutable operations create governed proposal/run/feedback/schedule state. Existing MCP transport and JSON-RPC envelopes remain unchanged.

**Depends on:** P5.
**Parallel with:** P6.
**Blocks:** P8 and P9.
**PRD coverage:** FR-15 and permissions/safety; AC 17, 19 and 20.

## Owned Files

**Create:** `app/api/growth_api.py`, `app/api/growth_ws.py`, `app/mcp/growth_tools.py`, `tests/api/test_growth_api.py`, `tests/api/test_growth_sse.py`, `tests/mcp/test_growth_tools.py`, and `tests/mcp/test_growth_http_contract.py`.

**Modify:** `app/api/knowledge_api.py`, `app/api/knowledge_workspace_api.py`, `app/api/mcp_http.py`, `app/mcp/server.py`, `app/mcp/wiki_tools.py`, route registration and generated/manual frontend contract types only where additive.

**Forbidden:** Changing existing status/error envelope, MCP initialize/tools/list semantics, SSE replay ordering, project auth rules, direct Vault writes, or exposing business Artifact Graph as knowledge lineage.

## Frozen Public API Surface

REST groups are project-scoped and paginated:

- `GET/PATCH /knowledge/projects/{project_id}/profile`
- `GET /knowledge/projects/{project_id}/growth/assets?stage=A|B|C|D|review`
- `POST /knowledge/projects/{project_id}/sources` and `GET .../sources/{id}/triage`
- `GET/POST /knowledge/projects/{project_id}/methods`, `GET .../methods/{id}/revisions`, proposal review/publish/deprecate and execution resolve
- `POST/GET .../outputs`, output evaluation, feedback and filing
- `GET .../growth/lineage`, `GET .../growth/summary`, `POST .../growth/review`
- `GET/POST .../schedules`, `POST .../runs`, `GET .../runs/{id}/events` and weekly distillation read endpoints

MCP tools use namespaced `knowledge_growth_*` names and return project-scoped IDs, state, provenance, pagination cursor and availability. Mutable tools never imply publication merely because a call returned 200.

## Task 1: REST Schemas And Permission Matrix

- [x] Write failing tests for profile, asset list, triage, method, output, feedback, lineage, summary, schedule, run and distillation schemas including pagination/bounds.
- [x] Implement request/response models with project ID required and stable machine-readable error codes.
- [x] Apply reader/admin/system permissions from the index to every route; deny cross-project path/query substitution.
- [x] Redact secrets and bound body, metadata, graph slice and response sizes.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/api/test_growth_api.py tests/test_api_auth.py tests/knowledge/test_project_auth_api.py -q`.

## Task 2: Growth REST Routes And Events

- [x] Implement read routes using repository pagination and deterministic ordering; never use file existence as success.
- [x] Implement mutable routes through governed P1-P6 services and return accepted/queued/unavailable/failed status truthfully.
- [x] Emit growth events with project, run, asset, sequence, actor, terminal flag and redacted data; preserve existing event streams.
- [x] Write SSE replay/last-event tests for gap, terminal, reconnect, cross-project and bounded event payload.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/api/test_growth_api.py tests/api/test_growth_sse.py tests/mcp/test_wiki_http_contract.py -q`.

## Task 3: MCP Tools And Compatibility

- [x] Write failing JSON-RPC tests for `initialize`, `tools/list`, each growth tool, invalid project, reader mutation, admin gate, unavailable scheduler, duplicate call and malformed arguments.
- [x] Add namespaced tools for profile/assets/source triage/method/output/feedback/lineage/summary/review/schedule/run/distillation.
- [x] Return existing MCP error envelope and preserve current Wiki tools, HTTP/SSE and stdio compatibility.
- [x] Ensure document/Vault content is data, not execution instruction, and no tool grants shell/filesystem/MCP capability.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/mcp/test_growth_tools.py tests/mcp/test_growth_http_contract.py tests/mcp/test_wiki_tools.py tests/test_mcp_compatibility.py -q`.

## Task 4: API Contract Documentation And Client Fixture

- [x] Add a machine-readable fixture or OpenAPI snapshot for representative list/detail/mutation/event responses without embedding secrets or user data.
- [x] Document idempotency headers/fields, optimistic revisions, status values, availability states and project authorization.
- [x] Verify legacy `/knowledge`, Skill, Artifact Graph and orchestrator API tests remain unchanged.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/api/test_growth_api.py tests/api/test_growth_sse.py tests/mcp/test_growth_tools.py tests/mcp/test_growth_http_contract.py tests/mcp/test_wiki_tools.py -q`.

## Task 5: Verification And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/api/test_growth_api.py tests/api/test_growth_sse.py tests/mcp/test_growth_tools.py tests/mcp/test_growth_http_contract.py tests/mcp/test_wiki_tools.py tests/test_mcp_compatibility.py -q`.
- [x] Run `git diff --check` and `git status --short`.
- [x] Record real HTTP/MCP initialize/tools/call and SSE replay evidence or mark live dependency unavailable.

## Acceptance Criteria

- Reader/admin/system behavior matches the permission matrix for every A/B/C/D/review read or mutation.
- All mutable calls create governed state and expose durable status; no route directly mutates raw sources or published Wiki/method files.
- Pagination and graph/event bounds are enforced; cross-project access, malformed input, secret leakage and replay confusion fail closed.
- Existing MCP/Wiki/API/SSE contracts pass without behavioral regression.

## Rollback Strategy

Disable growth routes/tools via feature flag while leaving existing knowledge/Wiki/MCP routes active. Keep audit/run records and additive schemas. Revert route registration only after clients see a documented unavailable response.

## Required Handoff

Provide P8 with route URLs, JSON schemas, tool names, permission/error/availability states, pagination/event behavior and a fixture base URL/credentials model. Provide P9 with compatibility test commands and real adapter evidence.
