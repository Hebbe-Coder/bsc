# P04 Dynamic SOP Compiler

## Goal
Compile diagnosis plus selected capabilities into a specific staged operating
system with owners, artifacts, metrics, decisions, risks, checks and retro.

## Modify
New `app/dbos/compiler.py`, tests under `tests/dbos/`.

## Do Not Modify
Legacy `sop_design` capability and export schemas.

## Test-first Tasks
1. Test compiler output lineages and stable task schema.
2. Test different contexts produce different task-family compositions.
3. Implement deterministic compiler and DynamicSOP artifact creation.
4. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_compiler.py -q`.

## Rollback / Handoff
Delete compiler service only. Handoff Dynamic SOP task capability names and
lineage identifiers to P05/P07.
