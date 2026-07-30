# C1 - n8n Information Intelligence Consolidation

## Goal

Integrate N1-N5 into one release candidate and make the only authoritative
decision about operational readiness for governed n8n information intelligence.

**Dependencies:** N1, N2, N3, N4, and N5 accepted handoffs.
**Exclusive authority:** cross-plan compatibility, real-cycle evidence,
release conclusion, and final worklog reconciliation.

## File Boundary

**Create:** integration matrix, real-cycle evidence packet, release checklist,
cross-plan regression harness, and final n8n information-intelligence status.

**Modify:** only documented compatibility seams, feature-flag/release
documentation, index/worklog, and scoped tests needed to join accepted leaves.

**Do not modify:** a leaf plan's source/authorization/lifecycle semantics,
third-party plugin code, provider/n8n/Feishu credential stores, user Vault
content, raw evidence body, or existing Artifact Graph/Horizon semantics.

## Entry Gate

- N1-N5 provide changed-file lists, contract/migration revisions, feature-flag
  states, acceptance outputs, rollback points, and fixture-versus-real evidence.
- N2/N3 SignalBatch and authorization contracts are frozen and match N4/N5
  consumers.
- All unavailable external dependencies are listed explicitly. Empty folders,
  imported workflow files, fixtures, generated cards, and container starts do
  not satisfy a real-cycle requirement.

## Test-First Integration Tasks

1. Add a focused failing integration test for one cross-plan defect before
   changing any compatibility seam. The test must exercise actual configuration,
   authorization, schema, lifecycle, or read-model behavior.
2. Apply additive migrations in dependency order on SQLite and PostgreSQL.
   Verify existing knowledge projects, source records, schedules, project keys,
   A/B/C/D flows, Horizon data, and disabled n8n behavior remain compatible.
3. Assemble a feature-flag matrix for n8n runtime, source registry, ingress,
   workflow/derivatives, operations read model, and optional delivery. Verify
   each can be disabled without deleting records or creating a false success.
4. Run a bounded, authorized RSS cycle:
   source registry -> n8n RSS discovery -> SignalBatch -> BSC receipt ->
   capture/lead decision -> triage/confirmation queue -> Knowledge Workspace ->
   managed Obsidian projection -> daily brief -> weekly-distillation input.
5. Run failure probes: duplicate execution replay, cross-project request,
   malformed batch, unavailable provider/credential, partial provider failure,
   LLM unavailable, Feishu delivery failure, disabled n8n, restart/recovery,
   and redacted REST/MCP reads.
6. Rebuild/verify Compose services and execute desktop/mobile browser journeys.
   Confirm ECharts/table parity, exact drill-down, no horizontal overflow,
   keyboard access, no raw data leakage, and truthful no-sample states.
7. Reconcile every handoff in the shared worklog with exact commands, status
   transitions, safe run/receipt IDs, browser evidence, deviations, external
   conditions, feature-flag matrix, and rollback result.

## Acceptance

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge tests/api tests/mcp tests/integration -q
npm run test:frontend
npm run check
npm run lint
npm run build
docker compose config
docker compose --profile n8n config
docker compose --profile full config
git diff --check
~~~

When a real n8n run is possible, also verify the scoped profile with its health
probe and a redacted BSC run/receipt record. Never print or store credentials.

## Release Decision

C1 records exactly one state:

- **release_ready:** all acceptance commands pass and the authorized real RSS
  cycle plus isolation, replay, failure, redaction, disabled-feature, browser,
  and rollback evidence are current.
- **implemented_with_operational_proof_pending:** code and focused tests pass,
  but a real external prerequisite such as Docker availability, n8n owner
  initialization, scoped credential, or authorized RSS run remains unproven.
- **not_release_ready:** a contract, authorization, persistence, redaction,
  lifecycle, or compatibility test fails.

## Rollback, Worklog, And Handoff

Use the feature-flag matrix to stop the affected surface, then roll back only
the additive migration/application release when required. Retain source,
receipt, run, audit, and output-feedback history. The final handoff is the
reconciled release matrix and a single release decision; it does not delete
history or conceal external failures.
