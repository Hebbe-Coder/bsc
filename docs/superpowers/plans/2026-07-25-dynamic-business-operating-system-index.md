# Dynamic Business OS Implementation Index

**PRD:** `docs/superpowers/specs/2026-07-25-dynamic-business-operating-system-prd.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-25-dynamic-business-operating-system.md`

## Dependency Order

`01 contracts -> 02 diagnosis -> 03 capability selection -> 04 compiler -> 05 execution -> 07 API/MCP -> 08 control center -> 09 release`.

`06 knowledge/memory` starts after `01` and may proceed alongside `03-05`.
`09` is the sole release/integration owner.

## Plans

| ID | Plan | Dependency | Owned surfaces |
| --- | --- | --- | --- |
| 01 | `2026-07-25-dbos-contracts-artifacts.md` | none | `app/artifacts/*`, `app/dbos/contracts.py` |
| 02 | `2026-07-25-dbos-diagnosis-intake.md` | 01 | `app/dbos/diagnosis.py` |
| 03 | `2026-07-25-dbos-capability-selection.md` | 02 | `app/dbos/capabilities.py` |
| 04 | `2026-07-25-dbos-dynamic-sop-compiler.md` | 03 | `app/dbos/compiler.py` |
| 05 | `2026-07-25-dbos-execution-autonomy.md` | 04 | `app/dbos/execution.py` |
| 06 | `2026-07-25-dbos-knowledge-memory.md` | 01 | `app/dbos/memory.py` |
| 07 | `2026-07-25-dbos-api-mcp.md` | 05,06 | `app/api/dbos_api.py`, `app/mcp/*` |
| 08 | `2026-07-25-dbos-control-center.md` | 07 | `src/components/dbos/*`, `src/api/dbosApi.ts` |
| 09 | `2026-07-25-dbos-evals-release.md` | 08 | tests, release documentation |

## Cross-plan Contract

- All plans import models only from `app.dbos.contracts` and `app.artifacts`.
- `artifact_id`, `project_id`, `parent_ids`, and normal Artifact Graph scope
  checks are mandatory. A plan cannot create an ad hoc in-memory mission state
  as the product source of truth.
- API/MCP accepts only Pydantic-bound JSON and delegates to one DBOS service;
  transport handlers cannot implement business policy independently.
- No plan modifies legacy runtime/MCP transport or Artifact Graph semantics
  beyond additive types/exports. Contract changes require PRD and index update.

## Gates

- Tests are written or updated before production implementation per plan.
- No execution call before a persisted confirmed Mission with explicit grants.
- Each plan writes exact command/results, deviations, rollback point, and
  unimplemented external dependencies into the worklog.
- `consolidation.md` is created only after first-round implementation/tests;
  it consolidates observed state rather than copying these plans.
