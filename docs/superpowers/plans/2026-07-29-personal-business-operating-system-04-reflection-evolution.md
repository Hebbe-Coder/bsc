# PBOS Plan 04: Reflection And Evolution

## Goal And Dependencies

Depends on Plans 01-03. Turn only reviewed, attributable, receipt-backed work
outcomes into Experience candidates and evolve Strategy Genome versions under
the v1 thresholds.

## Ownership And Prohibitions

- May change `app/pbos/service.py`, PBOS contracts, and PBOS/API tests for
  outcome review, feedback, promotion, rollback, and lineage.
- Must not reinterpret DBOS artifacts, erase historical audit records, or call
  an agent-only validation run a user's skill.

## Test-First Tasks

1. Require observed delivery result, server receipt, attribution, explicit
   acceptance, and quality score before an Outcome becomes learning-eligible.
2. Derive Experience scope, success/failure factors, boundary conditions, and
   confidence only from eligible outcomes.
3. Promote only after three comparable complete records without severe failure
   and either median quality gain >= 10 or a resolved hard failure.
4. Roll back on one severe failure or two comparable regressions, preserving
   prior version, version diff, evidence, and failure analysis.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py -q
```

The suite must cover missing evidence, agent-only work, promotion, rollback,
and isolation. Rollback changes only the active-strategy pointer. Handoff
reports eligible count, pending gaps, promoted IDs, and rollback criteria.
