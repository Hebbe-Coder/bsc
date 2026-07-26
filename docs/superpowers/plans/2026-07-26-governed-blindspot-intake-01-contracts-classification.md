# P01 Governed Intake Contracts And Classification

## Objective

Add additive Artifact Graph contracts and a deterministic, side-effect-free
classifier for the four supported Intake outcomes.

## Scope

- Add intake_session and intake_answer_revision Artifact types, classes,
  exports, and deserialization registry entries.
- Add DBOS_BLINDSPOT_INTAKE_ENABLED.
- Implement classification, phase validation, question-budget counters, and
  scoped session lookup in app/dbos/intake.py.

## Prohibited

- Do not alter existing Mission status values or execution behavior.
- Do not call Horizon, a model provider, a Vault, or an external command.

## Tests First

Create contract tests for serialization, scoped storage, each classification,
weak-signal uncertainty, budget exhaustion, and disabled feature handling.

Acceptance command:

    .venv\Scripts\python.exe -m pytest tests/dbos/test_blindspot_intake_contracts.py -q

## Rollback And Handoff

Disable the feature setting and remove only additive Intake routes/service;
stored artifacts remain readable. Handoff type names, session phases,
classification signal rules, and passing test results to P02.
