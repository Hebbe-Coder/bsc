# ECC Agent Architecture Audit

**Date:** 2026-07-21
**Scope:** BSC FastAPI/React BusinessRuntime, orchestrator, context policy,
Skill registry, MCP HTTP/SSE, LLM adapter, and feedback projection.
**Method:** ECC 12-layer agent architecture audit with source inspection,
focused regression tests, and live browser evidence from the runtime workspace.

## Executive Verdict

```json
{
  "schema_version": "ecc.agent-architecture-audit.report.v1",
  "executive_verdict": {
    "overall_health": "controlled_with_residual_persistence_limit",
    "primary_failure_mode": "dashboard reads could mutate feedback state",
    "most_urgent_fix": "make compiler-evaluation feedback idempotent per session"
  },
  "scope": {
    "target_name": "BSC BusinessRuntime",
    "model_stack": ["LLMService", "LLMAdapter", "BusinessRuntime"],
    "layers_to_audit": ["system prompt", "session history", "tool selection", "tool execution", "transport", "fallback", "persistence"]
  }
}
```

## Findings

### High - Fixed: dashboard reads polluted feedback statistics

- **Layer:** 12, persistence; 5, active recall.
- **Mechanism:** `GET /api/orchestrate/dashboard/{session_id}` calculated an
  evaluation and called `CompilerFeedbackBridge.record` on every read. Browser
  refreshes, retries, and dashboards could write duplicate synthetic negative
  feedback for the same completed run.
- **Evidence:** `app/api/orchestrate.py` dashboard projection; the bridge
  previously appended unconditionally in `app/evolution/feedback_bridge.py`.
- **Fix:** the bridge now returns the existing `compiler_evaluator` record for
  the same session before writing. A repeated dashboard request remains read
  stable.
- **Confidence:** 0.99.

### Medium - Fixed: MCP tool schema was descriptive instead of enforced

- **Layer:** 6, tool selection; 7, tool execution.
- **Mechanism:** JSON-RPC advertised `required`, type, and range metadata, but
  `tools/call` forwarded malformed arguments to handlers. Invalid input could
  become an internal error rather than a protocol error at the trust boundary.
- **Evidence:** `app/api/mcp_http.py` tool registry and call dispatcher.
- **Fix:** the MCP boundary now rejects missing, unexpected, mistyped, and
  out-of-range arguments with JSON-RPC `-32602` before executing a handler.
- **Confidence:** 0.98.

### Medium - Fixed: orchestration SSE could be buffered by a reverse proxy

- **Layer:** 10, platform rendering/transport.
- **Mechanism:** the orchestrator stream used the right media type but omitted
  anti-buffering response headers. A reverse proxy could delay capability
  events, making the terminal look stalled while the runtime was active.
- **Evidence:** `app/api/orchestrate.py` event response.
- **Fix:** the stream now sends `Cache-Control: no-cache`, `Connection:
  keep-alive`, and `X-Accel-Buffering: no`.
- **Confidence:** 0.93.

### Medium - Residual: evolution feedback is process-local

- **Layer:** 12, persistence.
- **Mechanism:** `FeedbackStore` is an in-memory list. The now-idempotent
  compiler evaluation record survives repeated dashboard reads but resets after
  an API process restart. Core project drafts, events, and Skill executions are
  durable; only the optional evolution summary is not.
- **Evidence:** `app/knowledge/feedback.py` stores records in `_records`; the
  default bridge holds one process-local store.
- **Impact:** the dashboard's evolution count is advisory rather than durable
  learning history. It does not affect the completed runtime result, context
  inheritance, tool permissions, or MCP execution.
- **Confidence:** 1.0.
- **Recommendation:** move evolution records to a dedicated database table
  only when persistent feedback-driven tuning is promoted from advisory UI to a
  product requirement. This is intentionally not coupled into the completed
  runtime-convergence scope.

### Low - Residual: legacy JSON extraction remains permissive

- **Layer:** 9, answer shaping.
- **Mechanism:** the capability parser accepts fenced JSON and falls back to a
  broad object extraction pattern for legacy providers.
- **Impact:** a response that mixes prose with a valid but unintended JSON
  object can be interpreted as an artifact payload. Current providers request
  JSON output and typed artifact mapping limits the blast radius.
- **Confidence:** 0.72.
- **Recommendation:** migrate each remaining legacy capability to a strict
  typed response envelope before removing the compatibility parser.

## Verification

- `tests/api/test_dashboard_evolution.py`: repeated dashboard reads create one
  evaluator record per session.
- `tests/test_mcp_http.py`: malformed MCP arguments are rejected before any
  handler executes.
- `tests/orchestrator/test_api.py`: orchestrator SSE advertises anti-buffering
  headers.
- Full regression and browser runtime evidence remain the release gate after
  these focused checks.
