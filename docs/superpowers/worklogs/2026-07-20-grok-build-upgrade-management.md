# Grok Build Upgrade Management

**Started:** 2026-07-20

**Reference archive:** `C:\Users\34216\Downloads\grok-build-main.zip`

**Extracted source:** `C:\Users\34216\AppData\Local\Temp\grok-build-main-analysis\grok-build-main`

**Objective:** Transfer proven engineering practices from Grok Build into BSC
where they improve the actual BusinessRuntime, orchestrator, and MCP execution
paths. Rust implementation details and product-specific interfaces are not
copied into BSC without a Python-native operational use case.

## Transfer Matrix

| Grok Build source | Transferable practice | BSC gap at start | Decision | Evidence |
| --- | --- | --- | --- | --- |
| `xai-grok-agent/src/config.rs` | Explicit tool timeout, bounded retry, retry classification, and backoff policy | Capability backends exposed only a final result; direct compatibility capabilities bypassed a common retry contract | Implemented | `CapabilityExecutionPolicy`, `tests/test_capability_execution_policy.py`, runtime/event/dashboard projection tests |
| `xai-chat-state/src/usage.rs` | Durable, explicit usage completeness semantics | BSC discarded provider-reported token usage and had no way to distinguish complete, partial, and missing reports | Implemented for canonical model/capability execution; monetary cost remains deferred because pricing is not provider-normalized | `app/core/llm_usage.py`, `tests/test_llm_usage.py`, runtime/dashboard/generated contract projection |
| `xai-chat-state` persistence/events | Immutable snapshots, event replay, and terminal semantics | Already covered by BSC durable task projection, SQLite event store, SSE replay/fan-out, and recovery work | No duplicate subsystem | `tests/orchestrator/test_event_store.py`, `tests/orchestrator/test_sse.py`, `tests/orchestrator/test_recovery.py` |
| `xai-grok-mcp/src/liveness.rs` | Owner-bound one-shot liveness watcher that emits once and clears stale state | BSC MCP runs one request per isolated subprocess, so there is no persistent client transport to watch | Adapted to transport model | Hardened isolated-runner lifecycle: no invalid Windows suspended-process resume, stable timeout/child/JSON error codes, and resource-handle release tests |
| `xai-grok-config/src/signed_policy.rs` | Signed, fail-closed policy sidecar | BSC has environment-backed deployment policy and request signing, but no distributed policy delivery requirement | Defer: unsigned local policy file would create a false security boundary | Re-evaluate only with a central policy control plane and key rotation owner |
| `xai-codebase-graph` | Incremental language-aware repository graph | BSC is a business analysis service, not a coding workspace; repository graph would not be consumed by a production workflow | Not applicable | No user-facing code-editing workflow exists in BSC |
| `xai-grok-memory` | Durable memory with query expansion | BSC's knowledge subsystem already owns durable document/chunk/vector retrieval; a second agent memory store would fragment truth | No duplicate subsystem | Existing `app/knowledge/*` persistence and retrieval tests |
| `xai-grok-hooks` | Trusted lifecycle contributor hooks that do not own the agent loop | BSC runtime transitions are explicit but have no extension boundary | Defer until a concrete, authorized extension use case exists | Avoid an untrusted callback surface without product need |
| `xai-fast-worktree` | Isolated workspace/checkpoints | BSC already scopes artifacts by tenant/project/session | No duplicate subsystem | `tests/orchestrator/test_isolation.py`, `tests/test_artifact_scope.py` |
| `xai-chat-state` auto compaction | Actual conversation replacement before context exhaustion | `ContextManager` is not called by a production execution; its legacy wrapper only adds post-run summary statistics | Defer and do not count as delivered | Requires a provider-normalized context window and a prompt-path integration; current helper is intentionally not represented as active protection |

## Completed: Execution Policy and MCP Reliability

- [x] Analyze Grok's agent configuration and retry/liveness contracts.
- [x] Verify BSC's execution, task projection, event, and dashboard paths.
- [x] Add one capability execution policy for backend and direct-callable paths.
- [x] Project attempt metadata through `BusinessRuntime`, orchestrator events, dashboard payloads, and generated Agent OS TypeScript contracts.
- [x] Harden MCP isolated subprocess lifecycle and structured failures.
- [x] Run focused policy, runtime, orchestrator, projection, and MCP tests.
- [x] Run complete regression, TypeScript checks, lint, build, and diff audit.
- [x] Record complete verification and reassess deferred Grok practices against real product requirements.

## Delivered Detail

- `CapabilityExecutionPolicy` limits each capability to a configured attempt
  count and per-attempt timeout, classifies stable failures, and uses capped
  exponential backoff only for transient failures. `CancelledError` is always
  propagated and never retried.
- `ExecutionResult` now contains attempt-by-attempt telemetry. A successful
  backend response with required outputs but no artifacts becomes an explicit
  `empty_output` failure rather than a silent success.
- Direct compatibility callables use the same policy as Nanobot and local
  backends. This includes the Legacy BSC Runtime adapter.
- The telemetry is carried in the canonical runtime response, durable
  orchestrator terminal event, task projection, dashboard API, and generated
  frontend contract.
- MCP child errors now preserve `error_code`; the parent emits a stable
  `MCPExecutionError` for child, timeout, process-termination, and invalid
  output failures. Windows no longer uses `CREATE_SUSPENDED` with an invalid
  process-handle `ResumeThread` call, and its Job Object CPU/memory bounds now
  use the Windows API's correct named structure fields.

## Focused Verification

- `tests/test_capability_execution_policy.py`: 4 passed.
- `tests/test_agent_runtime_convergence.py`: 12 passed.
- `tests/orchestrator/test_runtime_engine.py`: 2 passed.
- `tests/test_agent_execution_projection.py`: 1 passed.
- `tests/test_mcp_engine_runner.py`: 4 passed.

## Complete Local Verification

- Python full suite: `602 passed, 3 skipped, 3 warnings`.
- `npm run check`: passed.
- `npm run lint`: passed with 0 errors and 196 existing warnings.
- `npm run build`: passed.
- Agent OS backend/frontend generated-contract check: passed.
- `git diff --check`: passed (Git emitted only repository-wide existing CRLF
  conversion notices).

## Remaining External Evidence

- The existing convergence workflow still requires an authorized commit and
  push before GitHub Actions can validate PostgreSQL persistence and Docker
  container smoke. This work did not change that gate.
- The Windows Job Object test runs on Windows and is skipped on non-Windows
  CI runners because those runners do not expose Windows process APIs.

## Guardrails

- Do not copy Grok's Rust code or create a parallel orchestration system.
- Do not treat a mock, fallback, or empty artifact response as a successful real execution.
- Preserve cancellation semantics: cancellation is never retried.
- Keep retries bounded by both attempt count and per-attempt timeout.
- Do not commit, push, or include generated runtime data without explicit approval.

## 2026-07-20 Follow-up: Real Prompt Context Budgeting

The earlier compaction assessment is now partially delivered through the only
production path that needed it: real `NanobotAgentBackend` prompt construction.
This is deliberately not a claim that the unused legacy `ContextManager` has
become a production compaction engine.

- Added `app/core/prompt_context.py` with a deterministic, UTF-8-aware
  conservative estimator, head-and-tail truncation, bounded per-artifact
  selection, and final rendered-prompt enforcement.
- Added configurable limits: `CAPABILITY_PROMPT_MAX_TOKENS`,
  `CAPABILITY_PROMPT_INPUT_MAX_TOKENS`, and
  `CAPABILITY_PROMPT_ARTIFACT_MAX_TOKENS`.
- `NanobotAgentBackend` now ranks capability input Artifact types first,
  prioritizes critical/high-severity evidence within each type, and submits a
  bounded prompt to real LLM adapters. The old unconditional `input_text[:4000]`
  truncation and unbounded Artifact Graph interpolation are removed.
- `evidence_validation` now receives a concrete latest assumption plus actual
  ranked graph evidence. It no longer receives only the former placeholder
  `"(see artifacts above)"`.
- `ExecutionResult.prompt_context` carries non-sensitive usage telemetry
  (estimated budget, selected/omitted/truncated artifact counts) through the
  runtime, API schema, dashboard type, and generated Agent OS TypeScript
  contract.

### Verification

- New `tests/test_capability_prompt_context.py`: 4 passed. It proves bounded
  final prompts, critical Artifact priority, head/tail input retention, actual
  evidence injection, and real-execution telemetry.
- Capability policy, runtime convergence, execution projection, and runtime
  engine regression set: 23 passed.
- Full Python suite: `606 passed, 3 skipped, 3 warnings`.
- `npm run check`: passed.
- `npm run lint`: 0 errors; 196 existing warnings.
- `npm run build`: passed.

## 2026-07-20 Docker Deployment Evidence

- Docker Desktop 4.82.0 and CLI 29.6.1 were present but the Linux engine could
  not start because WSL was not installed. `wsl --install --no-distribution`
  completed successfully; WSL 2.7.10.0 with kernel 6.18.33.2-2 is now active.
- A controlled Docker Desktop/WSL restart recovered the Docker API. The engine
  now reports server version 29.6.1.
- Compose initially rejected the local `.env` because its first line had a
  UTF-8 BOM. The BOM alone was removed without changing any variable name or
  value; `docker compose config --quiet` then passed.
- `docker compose up --build -d --quiet-pull` correctly reached the image pull
  stage but could not connect to `registry-1.docker.io:443` for
  `ollama/ollama:latest`. The Windows host independently timed out against the
  same endpoint, and neither process nor WinHTTP proxy settings are configured.
- Therefore the production Compose stack has **not** been declared deployed and
  its container smoke remains pending an available Docker Hub route or a
  configured registry proxy/mirror. The remaining blocker is external network
  reachability, not Docker installation or BSC Compose validation.

## 2026-07-20 Follow-up: Provider-Reported Model Usage

- Added one `ModelUsage` contract for prompt, completion, total, cached, and
  reasoning token counts. `reported` distinguishes a provider usage object from
  no usage object; `complete` is true only when prompt, completion, and total
  tokens were all supplied.
- The normalizer accepts OpenAI-compatible object or mapping responses and
  never calculates missing fields from prompt length. Mock, fallback, and
  providers without usage return explicit `reported=false` records.
- `LLMService`, the OpenAI-compatible/Ollama/vLLM/LocalAI adapters, and the SOP
  client preserve provider usage. `LLMAdapter` exposes the last normalized
  value, and real `NanobotAgentBackend` executions project it as
  `model_usage` alongside prompt-context telemetry.
- The Agent OS schema, generated TypeScript contract, and compiler dashboard
  contract now expose the same typed model. No prompts, completions, API keys,
  or pricing guesses are stored in the usage record.
- New usage tests: 4 passed. Full Python regression after the change:
  `612 passed, 3 skipped, 3 warnings`; TypeScript check and production build
  passed; ESLint remained at 0 errors and 196 existing warnings.

## 2026-07-20 Follow-up: Optional Local-LLM Deployment

- Default Compose deployment now starts only `bsc-backend` for configured
  remote providers. Ollama is enabled explicitly through the `ollama`,
  `celery`, or `full` profile; the `full` profile resolves to backend, Ollama,
  Redis, and Celery worker.
- This removed an incorrect hard dependency on the unused Ollama image. The
  default build then reached the actual backend Dockerfile and failed while
  resolving the trusted Docker Hub base images `python:3.11-slim` and
  `node:22-bookworm-slim`, confirming the remaining blocker is registry
  network access. No untrusted mirror was introduced.

## 2026-07-20 Follow-up: Board Fail-Closed Policy

- `MultiAgentBoard` no longer silently substitutes fixed rule-generated role
  opinions after an LLM failure in production. Its deterministic Artifact-based
  fallback is now controlled by the shared `ALLOW_LLM_FALLBACK` policy.
- Production without explicit fallback authorization raises the model failure;
  development or explicitly authorized fallback can still use the rule path.
- Two policy tests cover both states and are included in the current full-suite
  result: `612 passed, 3 skipped, 3 warnings`.
