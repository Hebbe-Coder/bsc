# PBOS v1.0 Execution Index

## Execution Order

`01 -> 02 -> 03 -> 04`; after Plan 04, Plans `05`, `06`, and `07` may run in
parallel. Plan `08` is the integration/release gate. Each plan is test-first,
records implementation/verification/deviation/rollback evidence, and changes
only its declared ownership boundary.

| Plan | Depends on | Owns | Handoff contract |
| --- | --- | --- | --- |
| 01 Personal Model | none | PBOS artifacts, graph relations, migration | Typed artifact schemas and immutable genome relation names. |
| 02 Evidence + Obsidian | 01 | capture, receipts, managed L3 projection | Receipt and projection ownership contract; plugin bridge truth states. |
| 03 Compiler | 01, 02 | context selection and PersonalExecutionPlan | Plan schema, context priority, fallback/locale behavior. |
| 04 Evolution | 01-03 | outcome review, experience, promotion/rollback | Eligibility, comparison key, strategy diff, rollback criteria. |
| 05 Cockpit | 02, 04 | UI and REST client state rendering | API field/state contract and desktop/mobile proof. |
| 06 Connectors | 02 | authorization/receipt state only | Scope, redaction, status, receipt and revocation contract. |
| 07 Automation/API/MCP | 01-04 | routes, schedules, reports, MCP tools | Route/tool table, schedule IDs, authorization behavior. |
| 08 Integration/Release | 01-07 | E2E, Docker, browser, consolidation | Evidence matrix, deviations, rollback image/commit, remaining risks. |

## Parallel Boundaries

- Plans 05-07 may consume the contracts published by 01-04 but cannot redefine
  PBOS artifact relations, outcome eligibility, or compiler context priority.
- Connector code cannot write external systems or cause Plan 04 promotion.
- Cockpit code cannot create accepted outcomes/Capabilities/Strategies from
  display state.
- Cross-plan changes require an explicit PRD/index update first; do not edit a
  sibling plan's owned source files to resolve a local conflict.

## Invariants

- `ArtifactGraphStore` is the PBOS lifecycle/audit authority; Vault/indexes are
  projections and rebuildable derivatives.
- Existing DBOS artifacts are never reinterpreted as personal success/failure.
- `/api/pbos` and MCP share project authorization; readers cannot mutate.
- Unconfirmed Missions have no external side effects.
- Credentials, source bodies, and raw private notes never enter public
  PBOS/release evidence.
- Imported Copilot transcript drafts remain registered review material; native
  output, external authorization, and user outcome review have distinct gates.

## Verification Matrix

Run the relevant sub-plan commands first, then release verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_growth_distillation.py -q
npm run test:frontend
npm run check
npm run build
docker compose config
```

The final runtime audit also requires API readiness, a selected-project Studio
inspection at desktop and `390x844`, scheduler state, and a release gate whose
pending evidence is reported rather than silently passed.

## Rollback And Handoff

Every plan identifies an independently reversible code/projection/schedule
boundary. Rollback preserves BSC audit records and user Vault content. Each
handoff includes changed files, exact tests/results, API/data contracts,
runtime IDs, rollback point, deviations, and open evidence gaps. The final
consolidation is a factual release record, not a restatement of this index.
