# PBOS Plan 08: Integration And Release

## Goal And Dependencies

Depends on Plans 01-07. Verify the complete personal AI-project delivery loop
in the running system, not only fixtures: context-grounded plan, receipt
capture, review boundaries, automation, Studio rendering, recovery, and
honest external states.

## Ownership And Prohibitions

- May change release documentation, integration tests, Docker verification
  scripts, and non-secret release evidence records.
- Must not alter user content, connector credentials/accounts, Outcome
  acceptance, or Strategy Genome state merely to turn a gate green.

## Test-First Tasks

1. Run two contrasting contexts and assert different plans, no pre-confirmation
   side effect, and lineage from Mission to reviewable Outcome.
2. Test promotion/rollback in controlled fixtures while the live project keeps
   missing owner evidence honest.
3. Rebuild API, worker, and beat; verify readiness, schedule recovery, Docker
   configuration, and authorization isolation.
4. Inspect the selected Studio project at desktop and `390x844`, recording only
   bounded run/browser IDs and state counts.
5. Update consolidation only from current code, test output, runtime, and
   browser evidence; mark unprovided authorization or user feedback pending.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_store_durability.py tests/test_agent_runtime_convergence.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_growth_distillation.py -q
npm run test:frontend
npm run check
npm run build
docker compose config
```

Rollback uses the last verified image/commit and preserves audit history and
Vault content. Handoff updates consolidation with implementation evidence,
deviations, open risks, rollback points, and next priorities ordered by
diagnosis quality, capability selection, execution reliability, knowledge
learning, and experience quality.
