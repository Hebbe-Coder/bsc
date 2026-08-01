# PBOS Plan 05: Personal Growth Cockpit

## Goal And Dependencies

Depends on Plans 02 and 04. Build the daily control center inside the existing
workspace: next action, project health, personalization readiness, review
work, strategy assets, capability evidence, failure patterns, and lineage.

## Ownership And Prohibitions

- May change `src/components/pbos/`, `src/api/pbosApi.ts`, PBOS styles, and
  focused frontend tests.
- May read `/api/pbos` and growth APIs; a button may call only its existing
  authorized mutation.
- Must not render imported Copilot drafts, profile fields, or unverified
  outcomes as verified capabilities or personal methods.

## Test-First Tasks

1. Render loading, unavailable, empty, and populated states from real API
   contracts, including `awaiting_authorization` connector state.
2. Keep D-layer review separate from BSC-generated outputs and label transcript
   imports as review material, not native plugin delivery.
3. Provide constrained reflection, attribution/outcome review, Strategy Genome
   diff, capability evidence, and React Flow lineage interactions.
4. Verify desktop and 390px layouts have no horizontal overflow and every
   chart/metric traces to a bounded API field.

## Acceptance

```powershell
npm run test:frontend -- src/components/pbos/PersonalGrowthCockpit.test.tsx
npm run check
npm run build
```

Acceptance uses the selected real project at desktop and 390px, never a static
fixture. Rollback is frontend-only and cannot alter the ledger. Handoff
contains route names, state assertions, mobile proof, and unavailable states.
