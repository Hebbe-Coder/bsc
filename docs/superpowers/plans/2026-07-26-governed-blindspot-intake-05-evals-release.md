# P05 Evaluation, Release, And Consolidation

## Objective

Prove the first implementation round with source-backed tests, browser checks,
and a factual consolidation record.

## Scope

- Maintain at least 30 cases spanning build/direct/help/uncertain routing,
  budgets, skipped fields, revert, tier selection, source availability, Vault
  approval, auth, isolation, conversion, and DBOS execution gates.
- Run backend, MCP, frontend, TypeScript, production build, and desktop/mobile
  browser verification.
- Update the worklog after every verification stage.
- Create the consolidation document only after implementation and tests pass.

## Acceptance Commands

    .venv\Scripts\python.exe -m pytest tests/dbos/test_blindspot_intake_contracts.py tests/dbos/test_blindspot_intake_mission_bridge.py tests/dbos/test_blindspot_intake_evidence.py tests/dbos/test_blindspot_intake_evals.py tests/api/test_blindspot_intake_api.py tests/mcp/test_dbos_tools.py tests/mcp/test_dbos_http_contract.py -q
    npm run test:frontend -- src/components/dbos/BlindspotIntakePanel.test.tsx src/components/dbos/BusinessControlCenter.test.tsx
    npm run check
    npm run build
    git diff --check

## Rollback

Set DBOS_BLINDSPOT_INTAKE_ENABLED=false. Do not delete sessions, revisions,
Mission lineage, or approved output artifacts. Consolidation names every
environment-gated check that was not run.
