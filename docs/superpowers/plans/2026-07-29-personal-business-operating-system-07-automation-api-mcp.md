# PBOS Plan 07: Automation, API, And MCP

## Goal And Dependencies

Depends on Plans 01-04 and may run with Plans 05-06. Expose the personal loop
through `/api/pbos`, existing MCP authorization, and durable Celery/Redis
scheduling without breaking growth or five-document distillation outputs.

## Ownership And Prohibitions

- May change `app/api/pbos_api.py`, `app/pbos/scheduler.py`,
  `app/pbos/reports.py`, PBOS task bindings, MCP registration, and focused
  API/scheduler/MCP tests.
- Must preserve REST/MCP transports, project authorization, and existing
  knowledge-distillation contracts.
- Must not execute external effects for an unconfirmed Mission or leak a
  credential into reports.

## Test-First Tasks

1. Cover profile, plan, execution, outcome, feedback, evolution, Cockpit,
   today action, weekly report, and schedule API contracts.
2. Persist/recover daily, weekly, and monthly schedules and write reports below
   `distillations/每周蒸馏/<week>/pbos/`.
3. Reuse project authorization for MCP and REST, verifying reader/write
   separation and cross-project denial.
4. Ensure read-only calls add no artifacts and failures retain durable retry
   and run-state metadata.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_scheduler.py tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/knowledge/test_growth_distillation.py tests/integration/test_knowledge_celery.py -q
docker compose config
```

Rollback disables PBOS schedule intent and route/tool binding while retaining
completed run records. Handoff contains schedule IDs, next-run timestamps,
contract table, and worker availability.
