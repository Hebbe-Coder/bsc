# Runtime Convergence Subproject B Implementation Plan

**Goal:** Make the HTTP Agent OS and `/api/orchestrate` execute the shared `BusinessRuntime` instead of maintaining separate planner/reflection-only or legacy pipeline paths.

**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

---

## Scope

This subproject continues the platform convergence roadmap after Orchestrator Lifecycle Phase 1.

### In This Slice

- Add a shared runtime runner that constructs `ArtifactGraphStore`, `CapabilityRegistry`, `MissionPlanner` and `BusinessRuntime` in one place.
- Route `POST /agent/analyze` through `BusinessRuntime`.
- Add request-scoped artifact isolation so one execution cannot observe another execution's artifacts.
- Stop hardcoding Agent OS artifacts under project ID `api`.
- Preserve the existing response shape while adding runtime metadata.
- Add a `BSC_RUNTIME_MODE=legacy|business_runtime` switch for `POST /api/orchestrate`.
- Project BusinessRuntime output back into the existing orchestrator/dashboard state contract.
- Register legacy `/bsc/*` through an explicit `legacy_bsc_compatibility` capability adapter.
- Make mock execution deterministic for every registered capability, or fail registry validation.
- Define the Agent OS request/response contract once in Pydantic and generate the frontend TypeScript contract from it.
- Add focused tests proving the Agent OS and orchestrator runtime paths execute and persist terminal lifecycle correctly.

### Deferred

- Durable tenant/project/session Artifact Graph storage and repository-backed isolation.

---

## Exit Criteria For This Slice

- `POST /agent/analyze` calls the shared runtime runner.
- `POST /api/orchestrate` can run behind `BSC_RUNTIME_MODE=business_runtime` without breaking the Phase 1 lifecycle contract.
- The response includes `runtime` metadata with iterations, elapsed time and errors.
- A request-scoped `project_id` is used instead of literal `api`, and repeated runs do not share artifact state.
- The default capability registry includes a reversible legacy BSC compatibility capability.
- Registered capabilities have deterministic mock coverage or fail fast during registry construction.
- The Agent OS HTTP response and frontend API client consume one generated contract.
- Focused regression tests pass.
