# PBOS Plan 06: Read-Only Connectors

## Goal And Dependencies

Depends on Plan 02 and may run with Plans 03-05. Add GitHub and Feishu as
project-scoped, explicitly authorized, read-only evidence sources. Missing
credentials must remain an honest state, not a hidden error.

## Ownership And Prohibitions

- May change PBOS connector services/contracts, `/api/pbos` state projection,
  and connector tests.
- Must never persist tokens in Artifact Graph, Vault, logs, browser state, or
  public API responses; remote writes are forbidden.
- Must not enable a connector from a provider key, model configuration, or
  unauthenticated public request.

## Test-First Tasks

1. Test project isolation, redaction, `awaiting_authorization`, authorized read
   receipts, degradation, rate limiting, and revocation.
2. Permit connector material to influence context only after scoped
   authorization and a durable read receipt exist.
3. Render status in Cockpit and retain degraded results as diagnostics instead
   of fabricating knowledge.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos tests/api/test_pbos_api.py tests/knowledge/test_wiki_sync.py -q
npm run test:frontend -- src/components/pbos/PersonalGrowthCockpit.test.tsx
```

Without credentials, acceptance is `awaiting_authorization`; with a user-owned
authorization, it additionally requires a real read receipt. Rollback revokes
the binding and removes only cached non-secret metadata. Handoff lists scope,
receipt IDs, degradation behavior, and any user credential requirement.
