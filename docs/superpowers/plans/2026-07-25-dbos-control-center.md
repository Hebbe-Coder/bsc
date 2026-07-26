# P08 Business Control Center

## Goal
Build a real-data control center for diagnosis health, reasoning lineage,
decisions, capability/agent status, Dynamic SOP execution and memory feedback.

## Modify
`src/api/dbosApi.ts`, new `src/components/dbos/*`, `UnifiedWorkspace` routing,
and frontend tests.

## Do Not Modify
Existing knowledge workspace behavior or hard-coded mock API paths.

## Test-first Tasks
1. Test API client rejects malformed payloads and renders empty/error/loading
   states truthfully.
2. Test task inspection shows lineage and execution status from server data.
3. Implement responsive control center using current visual primitives.
4. Run `npm run test -- --run src/components/dbos` and `npm run build`.

## Rollback / Handoff
Remove DBOS workspace entry only. Handoff screenshots and build result to P09.
