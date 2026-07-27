# P4 - Knowledge Operations REST And MCP

## Goal

Expose the authorized operations read model through one REST service and
compatible MCP read tools.

**Depends on:** P2 and P3.
**Blocks:** P5-P6.

## Owned Files

**Create:** operations API client tests and MCP tool tests.

**Modify:** `app/api/knowledge_operations_api.py`, route registration,
`app/api/mcp_http.py`, MCP catalog/delegation, `src/api/knowledgeOperationsApi.ts`
and its tests.

**Do not modify:** existing MCP HTTP/SSE framing, DBOS mutation routes, Growth
routes, proposal/execution authorization or frontend workspace components.

## Public API

- `GET /knowledge/operations/portfolio?from=&to=`: admin, current tenant only.
- `GET /knowledge/operations/projects/{project_id}?from=&to=&mission_id=`:
  authorized project reader/admin.
- `GET /knowledge/operations/projects/{project_id}/graph?...`: authorized,
  bounded lifecycle slice.
- MCP tools mirror these read methods and require a project ID except portfolio,
  which requires an admin role.

All responses expose `generated_at`, `scope`, `state`, `coverage`, and typed
empty/unavailable errors. No response exposes raw sources, prompts, credentials
or unredacted provider payloads.

## Tasks

1. Write failing REST/MCP/client tests for roles, tenant isolation, validation,
   intervals, graph bounds, serialization and unavailable errors.
2. Route all handlers through P2/P3 services and shared P1 authorization; do
   not reimplement aggregation in transport code.
3. Add typed client loading/error contracts with abort/stale-response safety.
4. Preserve existing API/MCP regression behavior and run
   `./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_operations_api.py tests/mcp/test_knowledge_operations_tools.py -q` plus
   `npm run test:frontend -- --run src/api/knowledgeOperationsApi.test.ts`.

## Acceptance Criteria

REST and MCP return identical authorized semantics; a project key cannot invoke
portfolio. The client distinguishes permission, offline, empty and unavailable
states without rendering stale success values.

## Rollback And Handoff

Remove the additive router/tools and client calls. Hand P5 response fixtures,
errors, action drill-down targets and graph rendering bounds.
