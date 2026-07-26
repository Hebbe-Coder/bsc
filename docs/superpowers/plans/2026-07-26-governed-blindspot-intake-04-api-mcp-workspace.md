# P04 REST, MCP, And Control Center

## Objective

Expose the governed Intake service through established transports and make
persisted state usable in Studio.

## Scope

- Add strict REST models/routes for session lifecycle, answers, revert, tier,
  recommendations, conversion, and approved export.
- Add one authorization-preserving dbos_intake MCP facade and HTTP catalog
  schema; do not add transport.
- Extend TypeScript DBOS types/client and BusinessControlCenter with
  classification, a single-question card, budget, revision, direct path, tier,
  source state, conversion, and export control.

## Prohibited

- Routes, MCP, and UI cannot duplicate policy or claim execution success.
- Reader credentials remain read-only; UI cannot hide unavailable state.

## Tests First

Cover authenticated REST/MCP actions, reader denial, cross-project denial,
frontend direct/clarify/exit states, revert, tier/convert, unavailable
recommendations, and 390px layout.

Acceptance commands:

    .venv\Scripts\python.exe -m pytest tests/api/test_blindspot_intake_api.py tests/mcp/test_dbos_tools.py tests/mcp/test_dbos_http_contract.py -q
    npm run test:frontend -- src/components/dbos/BlindspotIntakePanel.test.tsx src/components/dbos/BusinessControlCenter.test.tsx

## Rollback And Handoff

Disable the feature setting to hide routes/panel while retaining artifacts.
Handoff API/MCP schemas, UI states, and focused test results to P05.
