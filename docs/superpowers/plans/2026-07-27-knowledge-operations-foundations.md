# P1 - Knowledge Operations Foundations

## Goal

Create the tenant-safe project registry and frozen operations read-model
contracts required by every later visualization plan.

**Depends on:** Existing DBOS and A/B/C/D contracts.
**Blocks:** P2-P6.

## Owned Files

**Create:** `app/knowledge/operations_contracts.py`, focused contract and
migration tests.

**Modify:** `app/knowledge/schema.py`, project repository access methods,
auth-scoped project resolution, and only necessary type exports.

**Do not modify:** Artifact Graph meanings, Mission lifecycle, Growth entity
states, MCP transport framing, existing project-key behavior, or user Vault
content.

## Frozen Contracts

- `OperationsScope`: `tenant_id`, permitted project IDs, role, selected
  project/portfolio scope and UTC query interval.
- `OperationsMetricState`: `available`, `insufficient_sample`, `unavailable`.
- `OperationalAction`: stable ID, project ID, kind, severity, source refs,
  recommendation, created timestamp and permitted drill-down target.
- `ProjectOperationsCockpit`, `OperationsPortfolio`, and
  `LifecycleGraphProjection` contain metadata only; raw content is excluded.
- `knowledge_projects.tenant_id` is non-null after migration. Legacy data is
  backfilled once to `DEFAULT_TENANT_ID`; project IDs remain stable.

## Tasks

1. Write failing tests for tenant migration/reopen, legacy backfill,
   idempotency, tenant-filtered project listing and global/project role access.
2. Add an additive, SQLite/PostgreSQL-compatible migration and indexes; reject
   tenantless project reads after compatibility migration completes.
3. Implement contracts, serialization bounds and shared authorization helpers.
4. Test that project keys cannot enumerate portfolio projects and no metadata
   leak occurs through counts or errors.
5. Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_contracts.py tests/knowledge/test_operations_schema.py tests/knowledge/test_auth_resolve.py tests/api/test_knowledge_operations_api.py -q` and `git diff --check`.

## Acceptance Criteria

- Existing project data remains usable after one idempotent backfill.
- Admin scope is tenant-only; project scope remains exact.
- Operations contracts cannot carry source bodies, prompts, credentials or
  cross-project references.

## Rollback And Handoff

Disable the operations feature/router while retaining the additive column and
index. Hand P2/P3 the frozen Python/TypeScript JSON examples, migration result,
role matrix and forbidden cross-scope operations.
