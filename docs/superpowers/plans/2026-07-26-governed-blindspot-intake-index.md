# Governed Blindspot Intake Implementation Index

**PRD:** docs/superpowers/specs/2026-07-26-governed-blindspot-intake-prd.md
**Research:** docs/superpowers/research/2026-07-26-blindspot-finder-methodology-review.md
**Worklog:** docs/superpowers/worklogs/2026-07-26-governed-blindspot-intake.md

## Dependency Order

01 contracts/classification -> 02 interview/Mission bridge -> 03 evidence/Vault
-> 04 API/MCP/UI -> 05 evaluations/release.

Plan 05 is the sole owner of final cross-surface validation and creates the
consolidation document only after actual first-round implementation.

| ID | Plan | Dependency | Owned surfaces |
| --- | --- | --- | --- |
| 01 | governed-blindspot-intake-01-contracts-classification | none | app/artifacts, app/dbos/intake.py, settings |
| 02 | governed-blindspot-intake-02-interview-mission-bridge | 01 | app/dbos/intake.py, app/dbos/service.py |
| 03 | governed-blindspot-intake-03-evidence-vault-handoff | 02 | intake service, knowledge source/Vault adapter |
| 04 | governed-blindspot-intake-04-api-mcp-workspace | 01-03 | REST, MCP, TypeScript API, Control Center |
| 05 | governed-blindspot-intake-05-evals-release | 04 | tests, worklog, consolidation |

## Cross-plan Contract

- The Artifact Graph is the only source of Intake state. No frontend, MCP, or
  route may keep an authoritative in-memory session.
- REST and MCP only validate/authorize then delegate to DBOSService.
- Session conversion creates a normal Mission and calls existing diagnosis.
  It cannot bypass confirmation, decision, or execution gates.
- Vault exports use configured project-relative paths and explicit approval.
  Generated handoffs never enter raw-source capture.
- Child plans may edit only their owned surfaces. Shared-contract changes
  require a PRD and index update.

## Gates

- Write tests before production behavior.
- Record commands, deviations, rollback points, and environment limitations in
  the worklog.
- Run git diff --check, focused pytest/Vitest tests, npm run check, and npm run
  build before consolidation.
- Do not include unrelated worktree changes in this feature branch.
