# P6 - Knowledge Operations Validation And Release

## Goal

Integrate and prove the complete knowledge-operations chain across tenancy,
real persisted records, API/MCP, UI, accessibility and release boundaries.

**Depends on:** P5.
**Release owner:** This plan is the only plan that can mark the feature ready.

## Owned Files

**Create/Modify:** integration tests, browser test harnesses, release notes and
the shared worklog. Minimal fixes in upstream P1-P5 surfaces require explicit
handoff notes and their focused regression suites.

**Do not modify:** unrelated dirty worktree files, credentials, production
Vault content, historic artifacts or existing accepted plan documents.

## Tasks

1. Establish isolated tenant/project fixtures containing A/B/C/D records,
   Mission reasoning, risks, executions, verification, feedback and absence
   cases.
2. Run API/MCP end-to-end authorization tests: tenant admin, project admin,
   project reader, global reader, unknown project and cross-tenant attempts.
3. Verify metric/action/graph consistency against underlying durable records;
   confirm no raw source or prompt leaves an operations response.
4. Run desktop and mobile browser journeys: portfolio -> project -> action ->
   graph inspector -> existing proposal/mission detail; validate nonblank
   ECharts/React Flow pixels, no overlap and keyboard interaction.
5. Run focused suites, full affected DBOS/Wiki/Growth/MCP regressions,
   `npm run check`, `npm run lint`, `npm run build`, `git diff --check` and
   Docker/Compose checks when local images are available.
6. Record exact commands, data fixtures, screenshots, outcomes, remaining
   external dependencies and rollback point in the worklog.

## Required Verification Commands

Run the following commands from the repository root. Record their exact output
and any omitted live-provider assertions in the shared worklog.

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_contracts.py tests/knowledge/test_operations_schema.py tests/knowledge/test_operations_service.py tests/knowledge/test_operations_actions.py tests/knowledge/test_operations_graph.py tests/knowledge/test_auth_resolve.py tests/api/test_knowledge_operations_api.py tests/mcp/test_knowledge_operations_tools.py tests/test_artifact_scope.py tests/api/test_dbos_api.py tests/api/test_growth_api.py tests/api/test_knowledge_workspace_api.py -q
npm run test:frontend -- --run src/api/knowledgeOperationsApi.test.ts src/components/operations/KnowledgeOperationsCockpit.test.tsx src/store/knowledgeWorkspaceStore.test.ts src/components/dbos/BusinessControlCenter.test.tsx
npm run check
npm run build
git diff --check
docker compose config --quiet
```

When the local browser and Compose services are available, repeat the
portfolio-to-project-to-action journey at `1280x720` and `390x844`, then run
the documented read-only REST/MCP authorization probe. Do not replace these
live checks with mocked browser responses.

## Acceptance Criteria

Release requires every PRD acceptance criterion, explicit unavailable states,
zero cross-scope disclosures, and browser proof at desktop/mobile widths.

## Rollback And Handoff

If a gate fails, disable the additive operations feature/router and hide the
cockpit; retain additive tenant metadata and do not delete user knowledge data.
Provide commit range, migrations, feature flag/default, command results,
screenshots, fixture scope, API/MCP compatibility statement, known limits and
deferred Phase 2 BI boundary.
