# N5 - Information Operations And Delivery

## Goal

Expose BSC-owned source, run, receipt, confirmation, and daily-brief state in
the Knowledge Workspace and managed projections without manufacturing value or
turning Feishu/Obsidian into writable lifecycle authorities.

**Dependencies:** N3 and N4 accepted handoffs.
**Blocks:** C1.

## File Boundary

**Create:** authorized information-operations read service/API, typed frontend
client, Knowledge Workspace panels, daily-brief projection, receipt drill-down,
safe Feishu delivery adapter contract, browser tests, and managed Obsidian
navigation/projection templates.

**Modify:** existing Knowledge Workspace, daily-growth/weekly-distillation
read inputs, and read-only MCP operations tools only through additive,
feature-gated extensions.

**Do not modify:** source admission/receipt mutation, n8n workflow/runtimes,
Feishu credential values, user-authored Vault notes, Artifact Graph storage,
provider credentials, or portfolio metrics definitions.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** N3 receipt/read model, N4 derivative/delivery fixtures, existing
  project authorization, Obsidian managed projection contract, and operations
  visualization standards.
- **Outputs:** project-scoped source registry health, run/receipt state,
  confirmation queue, provider failure state, daily brief, exact drill-downs,
  and optional redacted delivery payload.
- **Authorization:** server-side tenant/project authorization gates every REST,
  MCP, and browser read. The UI cannot select a foreign project/record ID to
  bypass scope.
- **Redaction:** lists/charts/cards show metadata, counts, safe reason codes,
  and authorized links only. Raw source/derivative text, prompt, provider
  payload, credential, Vault path, and local n8n configuration are excluded.

## Test-First Tasks

1. Add focused failing tests for project/tenant isolation, no-sample state,
   partial/unavailable provider state, receipt-to-source drill-down, payload
   redaction, disabled-feature behavior, and mobile layout.
2. Implement one authorized read service aggregating source registry state,
   batch runs, receipt statuses, confirmation-required leads, configured versus
   unavailable adapters, and daily-brief revision/lineage.
3. Add Information Operations to the existing Knowledge Workspace: source
   health table, run timeline, receipt status distribution, confirmation queue,
   daily brief, and a direct transition into the existing evidence inspector.
4. Use ECharts only for bounded distributions/trends and accessible HTML tables
   as an equivalent information path. Every panel displays project, window,
   denominator, filter, and no_sample/partial/unavailable state.
5. Build daily brief projections only from completed BSC receipts. Surface
   duplicate and failure counts explicitly; do not count them as new knowledge.
6. Add an optional Feishu delivery adapter that receives a redacted completed
   brief payload, records delivery attempt/result, and does not affect capture
   success. Add managed Obsidian navigation/projection links without arbitrary
   n8n filesystem writes.
7. Connect only admitted source/receipt deltas to existing daily growth and
   weekly distillation reads. Do not alter their semantic-delta or revision
   rules. Hand C1 browser evidence and integration fixtures.

## Acceptance

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/api/test_n8n_information_operations_api.py tests/mcp/test_n8n_information_operations.py -q
npm run test:frontend -- --run src/api/n8nInformationApi.test.ts src/components/knowledge/InformationOperations.test.tsx
npm run check
npm run build
git diff --check
~~~

Browser acceptance covers desktop and 390x844: nonblank but truthful states,
keyboard-accessible filters and drill-down, no document-level horizontal
overflow, authorized record selection, and no raw-content leakage.

## Rollback, Worklog, And Handoff

Disable information-operations and delivery feature flags while retaining BSC
records and managed projection history. Do not delete sources, receipts, n8n
executions, or Feishu data to hide a failure. The handoff includes APIs/types,
screenshots/test output, viewport evidence, redaction assertions,
fixture-versus-real classification, delivery state, known gaps, and rollback
action.
