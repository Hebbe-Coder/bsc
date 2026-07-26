# P03 DBOS Capability Selection

## Goal
Select a composable capability set using diagnosis context and explanation,
rather than an SOP title/template.

## Modify
New `app/dbos/capabilities.py`, tests under `tests/dbos/`.

## Do Not Modify
Existing `MissionPlanner` fallback templates or registry capability behavior.

## Test-first Tasks
1. Test scenario divergence across role/industry/stage/constraints.
2. Test rejected/unregistered capabilities cannot be selected for execution.
3. Implement scored pool and Selection artifact persistence.
4. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_capability_selection.py -q`.

## Rollback / Handoff
Remove DBOS selector only. Handoff selected/rejected record schema to P04/P05.
