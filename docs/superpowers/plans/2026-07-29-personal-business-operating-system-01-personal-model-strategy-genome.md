# PBOS Plan 01: Personal Model And Strategy Genome

## Goal And Dependencies

Define the project-scoped personal model that makes PBOS a personal loop
system rather than a SOP-template library. This plan has no dependency and
unblocks Plans 02-08. It extends the Artifact Graph without changing existing
DBOS Mission, authorization, or Artifact Graph meanings.

## Ownership And Prohibitions

- May change: `app/artifacts/`, `app/pbos/service.py`, `app/pbos/migration.py`,
  `tests/pbos/test_pbos_service.py`, and `tests/pbos/test_pbos_migration.py`.
- May add BSC-owned projections only below `pbos/` in the mapped project Vault.
- Must not change DBOS artifacts, cross-project visibility, user-authored
  Vault notes, or create a Capability from a declared profile or agent-only run.

## Test-First Tasks

1. Add failing isolation and serialization tests for Profile, Capability,
   Experience, Plan, Execution, Outcome, Feedback, SOPVersion, and Promotion.
2. Implement parent links for `Mission -> Plan -> Execution -> Outcome ->
   Feedback -> Experience -> Capability` and the immutable Strategy Genome.
3. Require every genome revision to retain its prior version, evidence chain,
   applicable scope, decision rules, path, boundaries, metrics, and diff.
4. Add tamper-resistant export/import tests for project bundles.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_service.py tests/pbos/test_pbos_migration.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py -q
```

Rollback changes only PBOS readers/writers and managed projections; ledger and
user content remain auditable. Handoff supplies schemas, relation names,
migration version, test output, and compatibility constraints for Plans 02-04.
