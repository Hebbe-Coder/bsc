# Platform Convergence Execution Management

**Objective:** Complete every acceptance criterion in
`docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`.

**Last updated:** 2026-07-20

## Acceptance Tracking

| Criterion | Status | Evidence |
| --- | --- | --- |
| One documented runtime owns product executions | Complete locally | BusinessRuntime plus the Legacy BSC capability own canonical and compatibility paths; `tests/test_runtime_entrypoint_policy.py` prevents direct compiler bypasses. |
| Every execution has a queryable terminal state | Complete locally | Durable task projection, terminal transitions, recovery, and production HTTP smoke. |
| SSE reconnect and multi-subscriber behavior are deterministic | Complete locally | Durable event store plus `tests/orchestrator/test_sse.py` and `tests/orchestrator/test_event_store.py`. |
| Frontend renders backend artifacts after terminal completion | Complete locally | Terminal SSE handling, dashboard projection, and `tests/test_frontend_api_policy.py`. |
| Production rejects silent mock or fallback LLM output | Complete locally | `tests/test_production_llm_policy.py` covers all identified LLM paths. |
| Business data respects tenant/project/session scope | Complete locally | Artifact and orchestrator isolation tests. |
| Every repository follows configured database backend | Complete locally | The repository contract passes against both SQLite and a real PostgreSQL 16 container. |
| Clean checkout passes CI and produces SPA container | Complete locally | The multi-stage image builds from source and the production container passes health, authenticated task, terminal SSE, and dashboard smoke checks. |

## Completed Verification

- [x] Python full suite with PostgreSQL 16: `620 passed, 2 skipped` from `622` collected tests.
- [x] `npm run check`.
- [x] `npm run lint`: 0 errors, 196 pre-existing warnings.
- [x] `npm run build`.
- [x] `python scripts/quality_inventory.py --root .`.
- [x] Production-mode container smoke with explicit mock opt-in: `/live`, `/ready`, Docker health, authenticated orchestration, terminal SSE, and dashboard projection.
- [x] CI YAML parses locally.
- [x] `git diff --check`.
- [x] `python -m pip check`: no broken requirements.
- [x] `npm ci --dry-run`: package lock resolves without mutation.
- [x] `.gitignore` protects local smoke databases and generated legacy/default
  Artifact directories without ignoring tracked Artifact fixtures.
- [x] Docker Desktop/WSL/Compose availability and default/full service graphs.

## Pre-Commit Audit

- CI workflow is valid YAML and pins the intended Python 3.11 and Node 22
  runtimes.
- CI explicitly provides PostgreSQL 16 and runs the durable repository
  contract through `TEST_POSTGRES_URL`.
- CI builds the Docker image, starts an explicitly mock-authorized production
  container, and verifies readiness, task terminal state, persisted SSE and
  dashboard projection.
- Docker Desktop 4.82.0, Docker Engine 29.6.1, Compose 5.3.0 and WSL 2.7.10.0
  are operational. Default and `full` profile service graphs validate.
- Docker Hub access recovered through the VPN. The final multi-stage image
  `bsc-backend:spec` builds successfully from the trusted Python and Node base
  images despite transient Debian/PyPI failures, using bounded retries and
  BuildKit caches.
- PostgreSQL 16 runs locally in `bsc-spec-postgres`; the full repository
  contract and complete Python suite pass against it.
- The first container smoke exposed a structured-logger call that aborted
  startup when orphaned jobs were recovered. The call and its regression test
  were fixed, the image was rebuilt, and the final production smoke passed.
- Runtime-data entries remain excluded by the scope below and must not be
  staged even though the deliverable worktree is intentionally extensive.

## Current Git State

- Current branch: `master`; `HEAD`: `b3bc414` (`merge: Orchestrator Lifecycle
  Phase 1 certification`).
- Remote `origin` is configured as `https://github.com/Hebbe-Coder/bsc.git`.
- The convergence/Grok implementation remains uncommitted at this checkpoint.
  The user authorized commit and push to the current `master` branch; remote
  GitHub Actions evidence will be recorded after the push.

## Commit Scope

Include all convergence implementation, tests, generated Agent OS TypeScript
contracts, documentation, CI workflow and delivery scripts.

Do not include runtime data:

- `app/data/local-production-smoke.db`
- `data/local-production-smoke.db`
- `data/artifacts/**`
- temporary databases and logs outside the repository

## Remaining Release Gate

- [ ] Commit the reviewed convergence implementation.
- [ ] Push to the configured remote branch.
- [ ] Confirm GitHub Actions runs the PostgreSQL persistence contract.
- [ ] Record remote evidence and complete final acceptance audit.

## 2026-07-21 Frontend Runtime Recovery

- Fixed Agent OS error parsing so an HTTP response body is consumed once,
  preserving the backend error detail without triggering the browser's
  `body stream already read` exception.
- Added the missing Vite `/agent` development proxy. Agent OS routes are
  root-level FastAPI endpoints, so requests previously fell through to the SPA
  HTML response instead of reaching the backend.
- Browser verification on `http://127.0.0.1:5173/` completed an Agent OS run
  and rendered the result inspector without console errors, stream-read
  errors, or `/agent` 404 responses.
- Focused regression: `19 passed` across frontend API policy and Agent OS
  runtime convergence tests. Type check, quiet lint, and production build also
  passed locally.
