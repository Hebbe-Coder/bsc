# P01 DBOS Contracts and Artifact Mapping

## Goal
Add typed DBOS artifacts: mission, diagnosis, capability selection, Dynamic SOP,
execution result and memory. Preserve existing Artifact Graph serialization,
scope, snapshots and legacy exports.

## Modify
`app/artifacts/types.py`, `app/artifacts/store.py`, new `app/dbos/contracts.py`,
and `tests/dbos/test_contracts.py`.

## Do Not Modify
Existing artifact field meanings, legacy ArtifactGraphStore keys, orchestrator
or MCP transports.

## Test-first Tasks
1. Assert DBOS artifacts serialize/deserialize, preserve parent lineage, and
   appear in additive `_artifact_graph["dbos"]` output.
2. Add types/models and export mapping.
3. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_contracts.py tests/test_artifact_scope.py -q`.

## Rollback / Handoff
Revert only the additive enum/models/map/export keys. Handoff artifact ids and
parent rules to P02-P08.
