# P05 DBOS Execution and Authorization

## Goal
Provide Mission confirmation, explicit grants, idempotent execution audit,
failure/retry/stop/rollback records and registered BSC capability dispatch.

## Modify
New `app/dbos/execution.py`, tests under `tests/dbos/`.

## Do Not Modify
Existing BusinessRuntime lifecycle semantics; third-party/system side effects.

## Test-first Tasks
1. Test unconfirmed Mission returns an error before executor invocation.
2. Test confirmed Mission rejects ungranted capabilities and records attempts.
3. Implement confirmation and controlled dispatcher.
4. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_execution.py -q`.

## Rollback / Handoff
Disable DBOS router/dispatcher; persisted artifacts have no untracked effect.
Handoff service operations to P07.
