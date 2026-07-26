# awesome-llm-apps Adoption Audit

**Date:** 2026-07-25

## Scope and Conclusion

`awesome-llm-apps-main` is a collection of independent demonstrations, not a
single production runtime. Its useful contribution to BSC is a set of operating
rules: explicitly split work, test outputs rather than narratives, keep failed
experiments, and make model-provider fallback visible. Its example applications
are not directly importable without creating duplicate state, authorization,
and MCP systems.

This adoption therefore strengthens the existing DBOS and knowledge-growth
runtime rather than adding Agno, AG2, Google ADK, Streamlit, or a second
frontend.

## Inspected Sources

| Source | Valuable pattern | Adoption decision |
| --- | --- | --- |
| `agent_skills/advisor-orchestrator-worker/SKILL.md` | Advisor plan review, isolated workers, per-result verification, explicit retry and fallback ledger | Adopt verification and truthful degraded-mode rules; do not execute its shell dispatcher. |
| `agent_skills/self-improving-agent-skills/backend/adk_optimizer.py` | Baseline -> diagnose one failure -> mutate once -> re-evaluate -> keep only an improvement | Existing method proposals, revisions, gates, and rollback already provide the governed persistence layer. Use as a later optimizer contract, not an ADK dependency. |
| `advanced_ai_agents/.../ag2_adaptive_research_team` | Role handoff and tracing | BSC already has Dynamic SOP tasks, capability selection, run checkpoints, and Artifact Graph lineage. No framework import. |
| `mcp_ai_agents/*` | Tool routing by declared capability | Already represented by BSC's scoped REST/MCP tools and `CapabilityRegistry`; retain BSC's authorization boundary. |

## Runtime Availability

The original Advisor/Worker Skill requires `agy`, `claude`, `jq`, plus Gemini
or Anthropic credentials. This machine has none of those executable paths or
environment variables. No simulated external worker, shell command, provider
fallback, or success claim was produced. BSC's configured provider path remains
separate and is not silently repurposed as an Advisor/Worker team.

## Adopted Improvement: Verified DBOS Completion

Before this change, an authorized DBOS capability could be marked `completed`
once its transport returned without an exception. That does not establish that
the Dynamic SOP task's promised work product exists.

The DBOS execution path now applies an artifact-contract verifier to real
capability results:

```text
approved Dynamic SOP task
  -> registered capability executes
  -> provider reports output artifact IDs
  -> BSC reads the project Artifact Graph
  -> TaskVerificationArtifact: passed or failed
  -> completed only when the output contract passes
```

The verifier records the expected output types, observed artifact IDs, findings,
and the DBOS execution identity. Missing IDs or a missing declared output type
turn the execution into `failed` with stop reason
`task_verification_failed`. The failure remains in the Artifact Graph and adds
an explicit `verification_failed` checkpoint.

An injected callback returning a plain dictionary is not converted into a
verified delivery. It is useful for controlled tests and adapters, but Studio
shows its verification as pending because there is no independently inspectable
artifact ledger. This prevents a test fixture or integration adapter from
claiming the same evidentiary status as a real registered capability.

The control center now returns verification artifacts and separates
`COMPLETED / VERIFIED` in its health strip. Its execution ledger displays the
per-attempt verdict rather than treating transport success as business success.

## Why the Example Projects Were Not Imported

The self-improving demo uses in-memory sessions, accepts a provider key through
the browser, mutates an entire `SKILL.md` string, and decides whether to keep a
change through an LLM-driven score. It does not provide project isolation,
immutable source provenance, revision conflicts, publication gates, rollback,
or durable evaluation evidence. Those omissions are unacceptable for BSC's
knowledge and SOP methods.

The advisor-worker demo has good operational advice but dispatches CLI agents
from temporary directories and uses plain files as its status board. BSC already
has stronger durable equivalents: Mission authorization, Dynamic SOP tasks,
Decision artifacts, Execution results, Run checkpoints, API/MCP authorization,
and Artifact Graph lineage. Replacing those with subprocess coordination would
weaken the platform.

## Existing BSC Coverage

| Requirement | BSC implementation |
| --- | --- |
| Project-scoped state | `ArtifactGraphStore`, knowledge repositories, API/MCP project checks |
| Explicit plan and task ownership | `DiagnosisArtifact`, `CapabilitySelectionArtifact`, `DynamicSOPArtifact` |
| Human gate before work | task-bound `DecisionArtifact` plus capability authorization |
| Retry and restart honesty | idempotency key, `RunCheckpointArtifact`, manual retry after interruption |
| Evidence-aware knowledge production | immutable `SourceRecord`, Wiki proposals, method revisions, evaluation gates |
| Result verification | `TaskVerificationArtifact` for real DBOS capability outputs |

## Current Boundaries

1. Provider-neutral Advisor review is implemented as an explicit metered DBOS
   action through PromptOps. It produces structured findings and has no
   authority to authorize a capability, execution, publication or decision.
2. Method self-improvement is implemented through the immutable
   `MethodProposal -> MethodRevision -> MethodGate` path. The later experiment
   closure records the baseline, one mutation, positive/near-negative/holdout
   evidence, non-regression result, rollback anchor and reviewer-only release
   boundary.
3. A real external worker call remains a deployment configuration task. It
   requires an allowlisted non-production HTTPS endpoint, server-side
   credential reference, per-project egress policy, rate/cost budgets and
   integration evidence before BSC may claim a provider executed work. None is
   implied by the local contract tests or by this audit.

## Verification

- `python -m pytest tests/dbos/test_dbos_flow.py -q`: 9 passed.
- `npm run test:frontend -- --run src/components/dbos/BusinessControlCenter.test.tsx src/api/dbosApi.test.ts`: 7 passed.
- `python -m pytest tests/dbos tests/api/test_dbos_api.py tests/mcp/test_dbos_tools.py tests/mcp/test_dbos_http_contract.py tests/test_artifact_scope.py -q`: 26 passed.
- `npm run check` and `npm run build`: passed.

The tests include both critical paths: a real-mode result that reports a
nonexistent artifact is failed, while a real-mode result whose persisted
artifact matches its registered output type is verified and shown in Studio.

## Follow-Up Implementation: Governed SOP Routing (2026-07-25)

The previously deferred Method/SOP routing requirement is now implemented on
both paths. Method updates retain their immutable revision, single-mutation,
positive/near-negative/holdout, non-regression, reviewer-gate and rollback
requirements. Dynamic SOP routing now has an independent Artifact Graph
record, `SOPRoutingEvaluationArtifact`, rather than a frontend-only test
claim.

Each newly compiled Mission persists the versioned selector fingerprint and a
deterministic suite of three positive, two near-negative and two isolated
holdout cases. The suite replays diagnosis, capability selection and SOP
compilation without a model, provider, browser or external write. Its result
is parent-linked to the Mission, Diagnosis, CapabilitySelection and
DynamicSOP artifacts; REST, MCP, Artifact Graph export and the Business
Control Center all project the same persisted record. Confirmation and
execution fail closed unless the evaluation and its holdouts pass.

The first replay exposed and fixed a real issue: short token `ai` was matched
as a substring, so words such as `constraints` could misclassify a general
mission as a product route. Short ASCII routing identifiers now require word
boundaries in both selector and compiler. This is covered by a regression
case, not only documented as an observation.

Focused verification after this implementation:

- `./.venv/Scripts/python.exe -m pytest tests/dbos/test_sop_routing_evaluation.py tests/dbos/test_contracts.py tests/dbos/test_dbos_flow.py tests/api/test_dbos_api.py tests/mcp/test_dbos_tools.py -q`: 21 passed.
- `npm run test:frontend -- --run src/components/dbos/BusinessControlCenter.test.tsx src/api/dbosApi.test.ts`: 11 passed.
- `npm run check`: passed.

The external Worker tier remains deferred. It still requires explicit egress
policy, server-side secret storage, rate/cost budgets, sandbox and cancellation
controls, and non-production integration evidence before BSC can claim that an
external multi-agent run occurred.

## Follow-Up Implementation: Cancellable External Worker Boundary (2026-07-26)

The deferred runtime boundary is now implemented as a governed control plane;
this does **not** claim that any configured third-party provider has run. A
`POST` from REST or MCP first writes a redacted `ExternalWorkerRunArtifact` in
`queued` state and schedules the HTTPS call on a dedicated asynchronous worker
loop. The request caller never owns the connection and no credential, request
body, model output, or ambient proxy configuration is retained in the ledger.

Cancellation is a transport operation, not a label transition. The worker loop
races the HTTP task with a loop-local cancellation signal. It writes
`cancelled` only after the HTTP task acknowledges `CancelledError`; a response
that finishes first is recorded as `completed`, including a note that a later
cancellation could not undo the provider effect. The durable record includes
outbound start, cancellation request, cancellation completion and recovery
timestamps. Concurrent REST/MCP and background-loop transitions are guarded so
the file-backed Artifact Graph cannot lose a terminal state through a local
write race.

Startup recovery marks `queued`, `executing`, and
`cancellation_requested` calls `interrupted`. It never replays a possible
outbound request. A new human-approved idempotency key is required for another
attempt. REST, stdio MCP, HTTP MCP and the Business Control Center project
queued, active, cancellation-requested, cancelled, interrupted, rejected,
failed and completed worker ledger states from the same artifact data.

Verification covers the full governed boundary: disabled-policy rejection,
server-only credential resolution, HTTP request/response contract, project
output ownership, idempotency, cost exhaustion, two-failure escalation,
actual transport cancellation, restart recovery, REST cancellation projection,
and MCP tool discovery. The non-production HTTP test uses `httpx`'s transport
layer to inspect the outgoing HTTPS request without sending a real provider
credential over a network.

An actual provider run remains intentionally unclaimed until an operator
enables a non-production project policy, sets the server-side credential
reference, and supplies an allowlisted HTTPS endpoint that returns BSC-owned
artifact IDs. That is deployment configuration, not a fabricated test result.

## Follow-Up Implementation: Governed Method Evolution Experiments (2026-07-26)

The `self-improving-agent-skills` observation is now a concrete BSC product
boundary, not a future recommendation. `MethodEvolutionService` implements a
durable experiment cycle:

```text
published active revision
  -> three or more verified, immutable outputs produced by that revision
  -> one declared production mutation
  -> immutable update proposal
  -> existing MethodEvaluator positive/near-negative/holdout replay
  -> retain for MethodGate review, discard, or unavailable
```

Each experiment records the baseline revision, declared mutation dimension and
rationale, supporting output IDs, candidate proposal ID, complete evaluation
summary, retain/discard/unavailable decision, rollback anchor, actor and
project-scoped idempotency key. Reusing a key with different candidate input
is rejected. A passing experiment is `eligible_for_review`; it does not write
a published revision or change the method's active revision. The existing
`MethodGate` remains the only publication path.

The service rejects a non-published baseline, outputs from another method
revision, unverified outputs, missing immutable output evaluations, and any
candidate that changes more than its declared production dimension. Evaluation
unavailability is persisted as `unavailable`, not converted to a discard or a
passing result. Baseline, supporting outputs, run and candidate proposal are
linked in the project-scoped knowledge graph and a `method_evolution`
KnowledgeRun exposes an event timeline and bounded evaluation projection.

REST provides start/list/read endpoints under `/knowledge/projects/{project}/methods`.
The existing scoped MCP `knowledge_growth_method` tool adds `evolve`,
`experiments` and `experiment` actions with the same authorization boundary.
Growth Studio's existing durable Run Ledger now includes method-evolution runs;
the inspected published method renders its real experiment summaries and opens
the review-only candidate proposal.

Verification performed for this implementation:

- `pytest -q tests/knowledge/test_method_evolution.py tests/knowledge/test_method_evaluator.py tests/knowledge/test_method_registry.py tests/knowledge/test_method_evolution_service.py tests/api/test_growth_api.py tests/api/test_method_evolution_api.py tests/mcp/test_growth_tools.py tests/mcp/test_growth_http_contract.py`: 64 passed.
- `npm run test:frontend -- --run src/api/growthApi.test.ts src/components/growth/GrowthWorkspace.test.tsx`: 53 passed.
- `npm run check`, targeted `py_compile`, and `git diff --check`: passed. Line-ending notices only.
- Broad regression after the integration: 528 relevant knowledge/API/MCP tests passed with 3 expected skips; the full frontend suite passed 105 tests.

This deliberately does not reuse the demo's model-created test cases or
automatic full-SKILL rewrite. Candidate creation remains explicit and all
publication requires the pre-existing reviewer gate, evaluation and rollback
contract.
