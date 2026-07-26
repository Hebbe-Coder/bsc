# P07 DBOS API and MCP

## Goal
Expose project-scoped Mission, diagnosis, confirmation, selection, Dynamic SOP,
execution, feedback/memory and control-center data through REST and MCP.

## Modify
`app/api/dbos_api.py`, `app/main.py`, `app/mcp/server.py`, `app/api/mcp_http.py`,
tests under `tests/api` and `tests/mcp`.

## Do Not Modify
MCP transport framing/auth compatibility or legacy tool responses.

## Test-first Tasks
1. Test create/diagnose/confirm/execute lifecycle and project isolation.
2. Test MCP delegates to the same service and rejects absent project ids.
3. Register API/router/tools and validate public response shape.
4. Run `./.venv/Scripts/python.exe -m pytest tests/api/test_dbos_api.py tests/mcp/test_dbos_tools.py -q`.

## Rollback / Handoff
Remove DBOS router/tool registrations. Handoff REST projections to P08.
