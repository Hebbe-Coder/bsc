# P03 Evidence Recommendations And Vault Handoff

## Objective

Produce advisory recommendations from governed source metadata and export an
approved, non-evidence handoff to the configured project Vault.

## Scope

- Select only project-scoped admitted SourceRecords with usable URL, capture
  timestamp, and acceptable state; record unavailable/no-source explicitly.
- Persist recommendation metadata without copying raw source bodies or claiming
  live verification.
- Render an approved session/Mission handoff to outputs/handoffs through a
  confined Vault adapter and record Deliverable hash/path.

## Prohibited

- Do not fetch a URL, install a Skill, execute an external command, or write
  a Vault file without explicit approval.
- Do not re-ingest generated handoffs as source evidence.

## Tests First

Cover admitted-source filtering, unavailable Horizon/source state, project
isolation, missing Vault mapping, traversal rejection, unapproved export, and
idempotent approved export.

Acceptance command:

    .venv\Scripts\python.exe -m pytest tests/dbos/test_blindspot_intake_evidence.py -q

## Rollback And Handoff

Disable the feature; generated files remain reviewed outputs and artifacts
retain their hash. Handoff source filters, export path contract, and any
environment-gated Vault proof to P04.
