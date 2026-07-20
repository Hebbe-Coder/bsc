# Runtime Convergence Subproject B Work Log

**Started:** 2026-07-19
**Plan:** `docs/superpowers/plans/2026-07-19-runtime-convergence-subproject-b.md`
**Design Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`
**Execution mode:** Incremental implementation with focused regression gates

## Scope Snapshot

- Route `POST /agent/analyze` through the shared `BusinessRuntime`.
- Introduce a shared runtime runner and response mapper.
- Isolate runtime artifacts per execution instead of writing into a shared project bucket.
- Add `BSC_RUNTIME_MODE=legacy|business_runtime` switching for `POST /api/orchestrate`.
- Preserve the Phase 1 orchestrator lifecycle contract while projecting runtime output into the existing dashboard state shape.
- Register legacy `/bsc/*` as an explicit compatibility capability inside the shared registry.
- Make mock execution deterministic for every registered capability used by the Nanobot-style runtime path.
- Define Agent OS HTTP contracts in one backend schema and generate the frontend TypeScript contract from that source.

## Task Board

| Task | Status | Evidence | Notes |
|---|---|---|---|
| Shared runtime runner | Completed | `tests/test_agent_runtime_convergence.py` | Shared runner builds store, registry, planner and runtime in one place |
| Agent OS runtime path | Completed | `tests/test_agent_runtime_convergence.py` | `/agent/analyze` now executes BusinessRuntime |
| Request-scoped project and execution ids | Completed | `tests/test_agent_runtime_convergence.py` | No more literal `api`; response now includes runtime execution metadata |
| Per-execution artifact isolation | Completed | `tests/test_agent_runtime_convergence.py` | Repeated runs with the same `project_id` no longer see prior artifacts |
| Orchestrator runtime mode switch | Completed | `tests/orchestrator/test_api.py` | `/api/orchestrate` can switch to BusinessRuntime via `BSC_RUNTIME_MODE=business_runtime` |
| Runtime-backed orchestrator lifecycle | Completed | `tests/orchestrator/test_runtime_engine.py` | Runtime branch persists `completed` and `failed` terminal states and emits terminal events |
| Legacy BSC compatibility capability | Completed | `tests/test_agent_runtime_convergence.py` | Legacy compiler path is now registered and executable inside BusinessRuntime |
| Registry mock coverage validation | Completed | `tests/test_agent_runtime_convergence.py` | Registry construction now fails fast if a capability lacks deterministic mock coverage |
| Shared Agent OS contract | Completed | `tests/test_agent_runtime_convergence.py`, `npm run check` | Pydantic is the source of truth; TypeScript contract is generated and consumed by the frontend API client |
| Focused regression gate | Completed | 22 focused tests + `npm run check` | Runtime convergence and orchestrator suites all passed after the compatibility slice |

## Progress Notes

### 2026-07-19 - Shared Runtime Extraction

- Added `app/capabilities/runner.py` to centralize BusinessRuntime construction and Agent OS response mapping.
- Updated `POST /agent/analyze` to call the shared runner instead of keeping a planner/reflection-only HTTP path.
- Extended the runtime response to include mission metadata, runtime status, elapsed time and errors.

### 2026-07-19 - Isolation Hardening

- Added request-scoped `execution_id` support and isolated artifact writes under per-execution directories.
- Removed the old shared-project artifact behavior where repeated runs could observe prior artifacts from the same `project_id`.
- Added regression coverage proving two runs against the same `project_id` stay isolated.

### 2026-07-19 - Orchestrator Runtime Convergence

- Added `app/orchestrator/runtime_engine.py` to wrap BusinessRuntime inside the existing Phase 1 control-plane lifecycle.
- Preserved `queued -> running -> completed|failed|cancelled`, SSE terminal events and the existing dashboard projection contract.
- Added `BSC_RUNTIME_MODE=legacy|business_runtime` switching in `app/api/orchestrate.py` so the runtime path is reversible.
- Added projection helpers that map runtime artifacts back into `project`, `business_model`, `sop`, `risk`, `review` and `presentation`.

### 2026-07-19 - Legacy Compatibility And Mock Coverage

- Added `app/capabilities/legacy_bsc.py` and registered `legacy_bsc_compatibility` in the default capability registry.
- Projected legacy `/bsc/*` business-system outputs into typed Artifact Graph records so the shared runtime can consume them as compatibility output rather than a parallel product path.
- Updated direct capability execution inside `BusinessRuntime` to pass request context, await async callables and persist returned artifact lists.
- Extended `ArtifactGraphStore.export()` to surface workflow, role, KPI and SLA metadata carried by compatibility artifacts.
- Added deterministic capability-level mock payloads for the Nanobot-style executor path and fail-fast registry validation when a registered capability lacks mock coverage.

### 2026-07-19 - Shared Agent OS Contract

- Added `app/schemas/agent_os.py` as the Pydantic contract for `POST /agent/analyze` requests and responses.
- Added `scripts/generate_agent_os_contracts.py`, which renders the checked-in `src/api/generated/agentOsContracts.ts` file from that schema.
- Switched `src/api/agentOsApi.ts` to consume the generated TypeScript contract and preserved the existing board convenience fields for UI compatibility.
- Normalized runtime gap and board payloads so FastAPI response validation and frontend consumption use stable fields.

## Verification

- `.\.venv\Scripts\python.exe -m pytest tests\test_agent_runtime_convergence.py tests\orchestrator\test_runtime_engine.py tests\orchestrator\test_api.py -q`
  - Result: `22 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\test_agent_runtime_convergence.py tests\test_agent_pool.py tests\test_compaction_pipeline.py tests\test_grok_pipeline_integration.py tests\orchestrator\test_api.py tests\orchestrator\test_engine.py tests\orchestrator\test_lifecycle.py tests\orchestrator\test_runtime_engine.py tests\api\test_compiler_dashboard.py tests\api\test_dashboard_evaluation.py tests\api\test_dashboard_evolution.py tests\api\test_dashboard_trusted_audit.py -q`
  - Result: `46 passed`
- `npm run check`
  - Result: passed
- `python -m compileall -q app scripts`
  - Result: passed
- `git diff --check`
  - Result: passed; only existing line-ending warnings were reported

## Known Baseline / Remaining Scope

- The known unrelated orchestrator mock-agent failures remain outside this slice:
  - `tests/orchestrator/test_agents.py::test_mock_planner_produces_project_and_requirements`
  - `tests/orchestrator/test_agents.py::test_mock_architect_produces_renderable_business_model`
  - `tests/orchestrator/test_agents.py::test_mock_reviewer_returns_explicit_approval`
- Still deferred in Subproject B:
  - Replace file-path isolation with durable tenant/project/session repository boundaries in Subproject C.
