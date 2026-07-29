# PBOS v1.0 Execution Index

## Order

`01 -> 02 -> 03 -> 04`; after that `05`, `06`, and `07` may proceed in parallel; `08` closes the release. Each plan is test-first, writes evidence to the PBOS worklog, and may change only its declared ownership boundary.

| Plan | Ownership | Depends on |
| --- | --- | --- |
| 01 personal model and Strategy Genome | Artifact Graph contracts and PBOS service foundation | none |
| 02 execution evidence and Obsidian | local capture, reflection, managed projections | 01 |
| 03 personal compiler | execution-plan composition | 01, 02 |
| 04 reflection and evolution | outcome evaluation, capability updates, promotion/rollback | 01-03 |
| 05 growth cockpit | PBOS REST client and workspace UI | 02, 04 |
| 06 read-only connectors | GitHub/Feishu authorization states and receipts | 02 |
| 07 automation/API/MCP | schedules, report projection, REST/MCP contracts | 01-04 |
| 08 integration/release | end-to-end evidence and release gates | 01-07 |

## Invariants

- `ArtifactGraphStore` remains the audited PBOS lifecycle authority; Vault files are projections.
- Existing DBOS artifacts are never reinterpreted as a user's real-world success or failure.
- New API is isolated below `/api/pbos`; connector writes are forbidden.
- Worktree changes outside explicit PBOS files are neither reverted nor staged.

## Verification

Run focused PBOS tests, existing Artifact Graph/DBOS/knowledge regression tests, `npm run test:frontend`, `npm run check`, `npm run build`, and `docker compose config`. The final consolidation records actual output, deviations, and rollback points.
