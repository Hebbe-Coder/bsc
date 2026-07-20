# Platform Convergence Finalization Worklog

**Date:** 2026-07-20
**Spec:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`

## Delivered

- Routed `/api/orchestrate`, `/agent/analyze`, the Agent CLI, `/prd/compile`, and
  deprecated `/bsc` compile and stage operations through `BusinessRuntime`.
- Kept legacy BSC payload compatibility by projecting the legacy capability's
  scoped Artifact Graph records back to the existing response fields.
- Added durable task projections, event replay/recovery, terminal status
  guarantees, tenant/project/browser-session checks, and scoped artifact paths.
- Added production LLM fallback policy, direct request-signing configuration,
  SPA shell access policy, deprecation headers, health/readiness endpoints,
  Docker/CI contracts, and generated Agent OS frontend types.
- Extended the production LLM guard to SOP, LangChain, LangChain Agent,
  legacy BSC integrity fallback, and legacy LLM adapters. Explicit mock and
  fallback output now fail closed in production unless their corresponding
  configuration flag is enabled.
- Expanded the PostgreSQL CI contract to cover task/event persistence plus
  project, asset, document, knowledge, graph, and preference repositories.
- Updated stale lifecycle/cache tests to assert canonical `completed` state
  and preserve the underlying execution mode on cache hits.
- Extended the CI container smoke script to verify the terminal task state,
  persisted SSE terminal event, and completed dashboard projection.
- Fixed authentication failures raised inside `BaseHTTPMiddleware` so they now
  return their correct 401/403 HTTP responses rather than being wrapped as 500
  errors by Starlette. Added direct middleware contract coverage.
- Isolated the pytest database backend before application imports so test runs
  use a disposable SQLite database rather than mutating the tracked runtime
  database; a clean test run no longer depends on its local state.
- Guarded the Query Rewrite and Self-RAG mock and LLM-fallback paths with the
  same production fail-closed policy used by the primary LLM services.
- Routed every remaining public legacy compilation entry point, including the
  CLI, stream API, task worker, Studio, dialog completion and compatibility
  helper modules, through the Legacy BSC Runtime capability. A regression test
  now rejects direct legacy compiler imports in those entry points.
- Routed the MCP compiler and the legacy Orchestrator's Business Architect
  compiler dependency through the same Runtime capability, leaving the legacy
  compiler implementation reachable only from its explicit adapter.

## Verification

- `TEST_POSTGRES_URL=... python -m pytest -q`: `620 passed, 2 skipped` from
  `622` collected tests, including the real PostgreSQL repository contract.
- `npm run check`: passed.
- `npm run lint`: passed with 0 errors; 196 historical warnings remain.
- `npm run build`: passed.
- `python scripts/quality_inventory.py --root .`: no encoding-risk or
  trivially unreachable statements.
- The multi-stage Docker image built successfully. Its production-mode
  container passed `/live`, `/ready`, Docker HEALTHCHECK, authenticated
  orchestration, terminal state, persisted SSE, and dashboard lifecycle.
- The CI workflow parses successfully and installs `pytest` explicitly before
  collecting and running the Python suite.

## Acceptance Audit

| Spec criterion | Local implementation and evidence |
| --- | --- |
| One documented runtime owns product executions | `BusinessRuntime` is the canonical runtime; all public Legacy BSC entry points are routed through its compatibility capability and guarded by `tests/test_runtime_entrypoint_policy.py`. |
| Every execution has a queryable terminal state | Durable `ProjectDraft` projections, terminal-state tests, recovery tests, and the production smoke cover status inspection and final states. |
| SSE reconnect and fan-out are deterministic | `tests/orchestrator/test_sse.py` and `tests/orchestrator/test_event_store.py` cover sequence ordering, replay, fan-out, and persisted terminal events. |
| Frontend loads artifacts after real completion | `UnifiedWorkspace` consumes terminal SSE events and fetches the dashboard; `tests/test_frontend_api_policy.py` prevents timer-based completion regressions. |
| Production never silently substitutes mock output | `tests/test_production_llm_policy.py` covers primary, SOP, LangChain, Legacy, Query Rewrite, and Self-RAG paths. |
| Business data is tenant/project/session scoped | Artifact and orchestrator isolation tests enforce tenant, project, browser-session, and artifact-store boundaries. |
| Database configuration reaches every repository | Config convergence, non-destructive migration, and PostgreSQL contract tests cover configured backends and repository persistence. |
| Clean checkout passes CI and builds a runnable SPA container | Local tests, type checking, lint, build, real PostgreSQL contract, image build, and production container smoke all pass; the same gates are defined in GitHub Actions. |

## External CI Evidence

- Local Docker 29.6.1 and PostgreSQL 16 now provide complete deployment and
  persistence evidence; neither acceptance item remains simulated or deferred.
- GitHub Actions evidence remains pending the authorized commit and push to
  `master` and will run the same PostgreSQL and container checks.

## 2026-07-20 Deployment Follow-up

- Docker Desktop's Linux engine was restored locally after installing WSL 2
  and restarting Docker Desktop. `docker version` confirms server version
  29.6.1, so the earlier local-Docker-unavailable statement is superseded.
- Compose validation now passes locally. During that validation a UTF-8 BOM on
  the first line of the ignored local `.env` was found and removed without
  changing its configuration values.
- Actual `docker compose up --build -d --quiet-pull` is blocked while pulling
  `ollama/ollama:latest`: both Docker Desktop and the host cannot reach
  `registry-1.docker.io:443`, and no proxy/mirror is configured. The stack was
  not falsely marked deployed; container `/live`, `/ready`, authenticated task,
  terminal SSE, and dashboard smoke remain pending registry access.
- The canonical real Nanobot capability prompt path now has a configurable,
  deterministic context budget. It prioritizes the capability's declared
  inputs and high-severity Artifacts, preserves head and tail of oversized PRD
  input, sends actual evidence to evidence validation, and projects only
  non-sensitive prompt-context telemetry through the runtime and frontend
  contract. Full local regression after this change: `606 passed, 3 skipped`.
- Remote-provider deployments no longer start Ollama unconditionally. Default
  Compose contains only `bsc-backend`; the `ollama`, `celery`, and `full`
  profiles opt into local model and worker dependencies. Both default and full
  profile service graphs pass `docker compose config` validation.
- A default backend-only build still cannot resolve the trusted Docker Hub
  metadata for `python:3.11-slim` and `node:22-bookworm-slim`, proving the
  remaining deployment blocker is general registry access rather than the
  optional Ollama image. No third-party registry mirror was added.
- Provider-native token usage is now normalized without guessing missing
  values or monetary prices and projected per real capability execution. The
  full regression after this addition is `610 passed, 3 skipped`; TypeScript,
  production frontend build, and lint (0 errors) pass.

## 2026-07-20 Continued Execution

- Docker Hub access recovered through the VPN. `python:3.11-slim` and
  `node:22-bookworm-slim` now pull successfully.
- The first real Compose build exposed a portability defect: `requirements.txt`
  contained two UTF-8 BOM prefixes. The file now starts with plain ASCII
  `fastapi>=0.110.0`.
- The next build exposed a slow-network defect rather than an application
  defect: pip timed out while downloading `tqdm` after 903 seconds. The
  production Dockerfile now uses `--default-timeout=180 --retries=8` so the
  build tolerates the current VPN/CI network conditions.
- Local verification after the fixes: `612 passed, 3 skipped, 3 warnings`,
  `npm run check`, `npm run build`, and `npm run lint` all pass. Lint remains
  at 0 errors with 196 existing warnings.
- The retrying BuildKit job `u2qf0pb08xo51zhi9dtks6a9u` reached dependency
  resolution but received a truncated PyPI package-index response and failed
  with `JSONDecodeError`. The Dockerfile now mounts a persistent BuildKit pip
  cache, while keeping that cache outside the final image, so later retries do
  not redownload every successful wheel.
- Compose configuration, `pip check`, and the quality inventory all pass; the
  inventory reports no encoding risks and no trivially unreachable Python.

## Remaining Release Actions

- Commit and push the verified workspace to `master` under the user's explicit
  authorization.
- Confirm GitHub Actions repeats the PostgreSQL and Docker gates successfully,
  then record the remote run as the final release evidence.

## 2026-07-20 Final Local Acceptance

- The final image build completed after bounded retries recovered two transient
  Debian package errors and the persistent pip cache completed all production
  dependencies.
- The first real production start found an incorrect positional-format logging
  call in orphaned-job recovery. It is now rendered before calling the
  structured logger, and `test_lifespan_invokes_orchestrator_recovery` exercises
  the non-empty recovery path.
- The rebuilt container is healthy and `scripts/container_smoke.py` passed the
  complete authenticated orchestration, status, SSE, and dashboard workflow.
