# P02 Interview State And Mission Bridge

## Objective

Persist bounded questions and immutable answer revisions, then convert a
reviewed Intake session into the existing DBOS Mission lifecycle.

## Scope

- Generate one domain-aware question at a time from declared context.
- Persist answer, skip, and revert records; derive only known Mission context
  fields from active revisions.
- Select Lite, Standard, or Full tier as a durable Intake decision.
- Convert idempotently to an existing business/career Mission with session
  lineage and run diagnose_and_compile.

## Prohibited

- Do not make an inferred field into evidence or auto-confirm a Mission.
- Do not reimplement Diagnosis, capability selection, or Dynamic SOP logic.

## Tests First

Cover question order, 2+3+1 limits, targeted revert, direct/skip gaps,
idempotent conversion, and confirmation still blocking execution.

Acceptance command:

    .venv\Scripts\python.exe -m pytest tests/dbos/test_blindspot_intake_mission_bridge.py -q

## Rollback And Handoff

Disable the feature. Converted Missions remain ordinary DBOS records; the
original session remains inspectable. Handoff Mission-context mapping,
conversion idempotency, and control-center projection to P03.
