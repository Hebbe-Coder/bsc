# P02 DBOS Diagnosis Intake

## Goal
Compile career/business intake into a traceable diagnosis, assumptions, gaps,
and risks before any capability selection.

## Modify
New `app/dbos/diagnosis.py`, tests under `tests/dbos/`.

## Do Not Modify
Runtime execution, existing knowledge source lifecycle, or API transport.

## Test-first Tasks
1. Test career and business intake produce distinct diagnosis material.
2. Test unprovided critical fields become gaps/assumptions, never facts.
3. Implement deterministic normalization and Artifact Graph writes.
4. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_diagnosis.py -q`.

## Rollback / Handoff
Delete only DBOS diagnosis service; stored artifacts remain inspectable. Handoff
diagnosis ids and fields to P03.
