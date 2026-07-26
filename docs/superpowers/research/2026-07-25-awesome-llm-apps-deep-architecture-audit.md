# awesome-llm-apps Deep Architecture Audit

**Audited:** 2026-07-25
**Archive:** `C:\Users\34216\Downloads\awesome-llm-apps-main.zip`
**SHA-256:** `8D6504BB9D5DB7CCB7DA670669D7261077A1313F71BA706F918672B9B656A008`

## Executive Decision

`awesome-llm-apps` is a curated collection of independent reference
applications and three Agent Skills. It is not a coherent platform runtime.
It is valuable as a library of sharply scoped engineering patterns, but adding
its frameworks wholesale would create a second agent runtime, second state
store, second authorization model, and second UI inside BSC.

The correct BSC strategy is selective adoption:

1. Keep BSC's Artifact Graph, project scope, authorization, MCP transport,
   PromptOps, Wiki lifecycle, and Dynamic SOP as system-of-record boundaries.
2. Reuse the collection's strongest ideas: deterministic non-LLM stages,
   per-result verification, explicit negative routing tests, visible tool
   traces, source-level status, bounded experiments, and failure taxonomy.
3. Do not embed Google ADK, AG2/AutoGen, Agno, LangGraph, CopilotKit,
   Streamlit, or demo MCP subprocess launchers into the BSC request path.

This audit is evidence-based. No provider API, external Agent CLI, MCP
subprocess, browser automation, or third-party write operation was run.

## Scope And Method

The archive has 2,253 entries. Its top-level file distribution confirms that
it is a catalogue, rather than a deployable monolith:

| Directory | Entries | Primary purpose |
| --- | ---: | --- |
| `advanced_ai_agents` | 683 | Single-agent and multi-agent demonstrations |
| `generative_ui_agents` | 654 | Independent Next.js, MCP UI, and CopilotKit applications |
| `ai_agent_framework_crash_course` | 326 | Google ADK and OpenAI SDK tutorials |
| `advanced_llm_apps` | 234 | Memory, chat-with-X, optimization, fine-tuning samples |
| `rag_tutorials` | 133 | Retrieval, corrective RAG, graph RAG, and diagnostics |
| `starter_ai_agents` | 68 | Small API-key examples |
| `agent_skills` | 55 | Three Skill-related packages and their evaluator tooling |
| `voice_ai_agents` | 32 | Voice demonstrations |
| `mcp_ai_agents` | 27 | MCP client and router demonstrations |
| `always_on_agents` | 17 | Scheduled-agent example |

Representative source was read from each relevant area, along with both GitHub
Actions workflows. The deterministic Skill CI was extracted to an isolated
temporary directory and run locally. It did not run networked product examples.

## Architectural Map

### 1. Catalogue Strategy

The root README advertises more than 100 applications across incompatible
frameworks. Dependencies found in manifests include repeated `agno`,
`streamlit`, `google-adk`, `FastAPI`, `Next.js`, `React`, `LangGraph`,
`CrewAI`, and MCP client packages. This is intentional pedagogical breadth,
not a versioned shared runtime.

Implication for BSC: a sample can establish a pattern, but its imports, global
state, provider assumptions, and UI conventions must not be treated as BSC
contracts. BSC should expose a provider-neutral capability contract rather than
adopt each sample's framework.

### 2. Agent Skill Governance

The strongest engineering in the archive is under `agent_skills`:

* `skill-evals.yml` runs strict lint, security scan, deterministic behavior
  tests, and lexical trigger-routing tests on every Skill change.
* `skill_lint.py` validates frontmatter, declared files, references, and
  packaging rules.
* `skill_scanner.py` scans for install lures, remote pipe-to-shell patterns,
  obfuscated payloads, network plus credential co-location, metadata mismatch,
  and unpinned dependencies. It deliberately does not claim to solve natural
  language prompt injection.
* `run_trigger_evals.py` compares positive prompts with near-miss negatives,
  ensures the owning Skill ranks first, and rejects overly similar Skill
  descriptions.

This is the model BSC should use for its knowledge methods and reusable SOP
skills: a method is not publishable merely because its Markdown renders. It
needs a declared trigger surface, positive cases, negative cases, output
contract, scope, and deterministic regression checks.

The catalogue has a real coverage gap: its `self-improving-agent-skills`
directory contains an application but no root `SKILL.md`. Consequently its
strict Skill lint, discovery-based scanner, and trigger routing CI discover
only the two actual Skills: `advisor-orchestrator-worker` and
`project-graveyard`. The source must not be cited as a fully evaluated Skill.

### 3. Advisor / Orchestrator / Worker

`agent_skills/advisor-orchestrator-worker/SKILL.md` separates four duties:

```text
frame success criteria and budget
  -> advisor reviews decomposition
  -> isolated workers execute a wave
  -> verifier exercises each deliverable
  -> synthesizer resolves conflicts
  -> advisor performs a final taste/risk review
```

Its useful controls are concrete:

* Worker briefs and results are separate files; briefs are not interpolated
  into shell commands.
* Workers use individual empty temporary directories and minimal environments
  to reduce accidental context leakage.
* Work is batched, failures are explicit, retries and provider fallbacks are
  recorded, and cost budgets are declared before dispatch.
* Verification must run the real artifact or command. A README check or a
  successful callback is explicitly rejected as proof of delivery.
* Structural disagreement, two failed attempts, or a changing plan escalates
  rather than being silently averaged away.

It remains unsuitable as BSC's execution engine. It relies on an external
`agy` CLI with `--dangerously-skip-permissions`, a Claude CLI, shell files as
the status board, and no durable project authorization or immutable artifact
lineage. The BSC equivalent is already stronger: `MissionArtifact`,
`DynamicSOPArtifact`, task-bound `DecisionArtifact`, `RunCheckpointArtifact`,
capability grants, and project-scoped Artifact Graph persistence.

### 4. Self-Improving Agent Skills

`agent_skills/self-improving-agent-skills/backend/adk_optimizer.py` has a
clear experimental loop:

```text
baseline score
  -> executor generates/runs scenarios and scores them
  -> analyst diagnoses the worst observed failure
  -> mutator makes exactly one targeted Skill change
  -> rescore candidate
  -> keep only a strictly higher score
```

It uses Pydantic output schemas for diagnosis and mutation, keeps a mutation
log, streams experiment events to the UI, and uses one-change-per-round rather
than an opaque full rewrite. Those are useful product behaviors for BSC's
`MethodProposal -> MethodRevision -> MethodGate` lifecycle.

It is not a safe autonomous optimizer:

* The same model family generates test scenarios, simulates the Skill,
  evaluates output, diagnoses failures, and mutates the candidate. This is a
  self-referential score, not independent evidence.
* Sessions and optimizer state use `InMemorySessionService` and a module-level
  FastAPI dictionary. A restart loses history; no project partition,
  idempotency, revision conflict, or audit transaction exists.
* The FastAPI app accepts provider keys in request bodies and enables wildcard
  CORS. This is demonstrative onboarding, not a credential boundary.
* It accepts a change on score increase alone; it has no holdout set,
  non-regression set, citation validation, rollout tier, or durable rollback.

BSC should adopt the experiment record and single-mutation discipline only.
Each BSC mutation must be a proposal linked to baseline, training cases,
holdout cases, negative cases, cost, provider policy, reviewer decision, and
rollback target. Publication remains gated.

### 5. Adaptive Research Team

`ag2_adaptive_research_team` models five roles: triage, local research, web
research, verification, and final synthesis. It routes between local chunks
and SearxNG, then passes a verifier verdict into final synthesis. The role
separation is easy to understand and its `Chunk` model keeps document name and
chunk id visible.

The implementation is still a compact demo. It parses model JSON using a regex,
uses simple token overlap as local retrieval, does not persist evidence, and
allows the final synthesizer to answer even when the verifier reports
`insufficient`. BSC should retain its stronger answer path: immutable source
records, citation links, proposal gates, and missing-evidence outcomes instead
of a forced final answer.

### 6. DevPulse Signal Intelligence

`advanced_ai_agents/multi_agent_apps/devpulse_ai` is the most relevant pattern
for BSC's Horizon-backed information intake. Its architecture is sound:

```text
source adapters
  -> deterministic normalization and source:id deduplication
  -> inexpensive relevance classification
  -> risk assessment
  -> stronger-model synthesis and priority digest
```

The important design decision is explicit in `SignalCollector`: fetching,
normalizing, and deduplicating are utilities, not Agents. LLM calls are
reserved for judgment. The relevance and risk stages use a low-cost model; the
synthesis stage uses a stronger model. That produces a sensible cost/quality
allocation.

Its limitations define BSC's integration requirements:

* GitHub and arXiv adapters fetch public data with timeouts, but failure is
  printed and converted to an empty list; source failures are not durable.
* The canonical record has no fetched-body snapshot, content hash, provenance
  chain, source reputation, rate limit ledger, or retry schedule.
* Risk and relevance JSON are parsed with fallbacks. A heuristic score cannot
  be represented as equivalent to a model-reviewed score.
* The synthesized priority is `relevance * risk_multiplier`, useful as a view
  ordering, but insufficient as a publication decision.

For BSC, retain the adapter pattern but persist every capture as immutable
`SourceRecord`, record fetch status and failure, hash raw material, preserve
the source URL and capture time, and distinguish deterministic, heuristic, and
model-derived attributes. Horizon becomes a governed source adapter, not an
untracked second intelligence database.

### 7. Trust-Gated Multi-Agent Team

The trust-gated example contributes two concepts: agent eligibility can be
checked before a role executes, and each step can emit auditable evidence. Its
demo UI exposes a configurable numeric trust threshold and intentionally
includes a low-trust writer that is blocked by default.

Do not adopt numeric trust scores as an authorization substitute. BSC already
has a stronger model: project scope, user role, capability registry, explicit
Mission confirmation, and task-matched decision. A reputation score may become
an advisory input, but it can never grant tool access or release a knowledge
proposal by itself.

### 8. MCP Examples

`multi_mcp_agent_router/agent_forge.py` provides a readable UX pattern: route a
query to a specialist, attach only that specialist's listed MCP tools, render
the routing choice, then show the tool loop. It demonstrates schema conversion
and parallel MCP session setup clearly.

It is not a secure MCP server boundary. It dynamically starts `npx -y`
packages, forwards inherited process environment, uses keyword routing, keeps
conversation state in Streamlit, and has no per-project authorization,
outbound-data policy, artifact persistence, or server allowlist. BSC must keep
its existing scoped HTTP/SSE and stdio MCP transport plus CapabilityRegistry.
The reusable idea is a declared tool subset per task, not local subprocess
launching.

### 9. Always-On Agents

`always_on_hn_briefing_agent` separates observation, rendered brief, and
delivery. Its scheduler endpoint defaults to `dry_run=true`; the Agent prompt
also says it must not claim it sent a message or scheduled a job. This is a
good honesty rule for BSC automation.

It is intentionally light: an HTTP trigger has no authentication in the demo,
there is no persistence, idempotency key, retry ledger, or source provenance.
BSC's Celery/Redis scheduler, `KnowledgeSchedule`, `KnowledgeRun`, output
artifacts, and failure events remain the production implementation. Adopt the
default-dry-run and honest delivery status behavior.

### 10. RAG And Knowledge Graph Samples

Three ideas are relevant:

* Corrective RAG grades retrieved documents, rewrites a query, and performs a
  web fallback when the local context is judged inadequate.
* Knowledge Graph RAG attaches entity and relationship extraction to source
  documents and renders reasoning paths and citations.
* RAG Failure Diagnostics defines reusable labels for grounding drift, chunk
  segmentation, index staleness, routing mismatch, evaluation blind spots,
  configuration drift, and tenant interference.

The samples cannot be taken as BSC storage code. The graph example includes a
global `clear_graph()` and no project boundary; the corrective RAG sample
recreates/deletes a shared Qdrant collection; both depend on browser-entered
provider keys and hand-parsed output. BSC should map the concepts to
project-scoped `CitationLink`, evidence artifacts, retrieval indexes that can
be rebuilt from source records, and a controlled failure taxonomy.

### 11. Generative Research UI

`generative_ui_agents/ai-deep-research-agent` is the best UI reference in the
archive. Its Next.js/CopilotKit interface renders a live tool trace and a
parallel workspace with:

* a mutable research plan with pending, active, and completed states;
* source cards that reveal fetched, failed, and pending status;
* produced files with preview and download actions; and
* specialized tool cards rather than raw JSON for known actions.

This is a good interaction direction for BSC's `UnifiedWorkspace`: a user
needs to inspect source, plan, task evidence, diff/proposal, and deliverable in
one task workspace. BSC should preserve its current React application and
Artifact Graph projection, then add these audit-friendly views with real
backend state.

The sample keeps client state in React memory, deduplicates events with a
hand-built result hash, uses an in-memory LangGraph checkpoint, and writes to a
demo filesystem. It must not be treated as a durable execution console.

## Deterministic Verification

Only offline checks were run against an isolated extraction:

| Check | Result | Interpretation |
| --- | --- | --- |
| Strict lint: `advisor-orchestrator-worker` | Pass, 0 errors/warnings | Valid packaged Skill |
| Strict lint: `project-graveyard` | Pass, 0 errors/warnings | Valid packaged Skill |
| Skill security scanner | Pass, 0 critical/warn/info for 2 discovered Skills | Useful static signal, not proof against prompt injection |
| Trigger routing with UTF-8 enabled | Pass, 2 Skills | Positives clear their near-miss negatives |
| Project Graveyard offline unit test | Pass, 16/16 | Classification, redaction, relapse and JSON report behavior |
| Trigger routing in default Windows locale | Fails before evaluation | `open()` uses the GBK default and cannot decode UTF-8 punctuation |
| Self-improving directory as a Skill | Fails strict lint | No root `SKILL.md`; not a discoverable Skill |

The route evaluation succeeds under its Linux GitHub Actions environment or
when Python UTF-8 mode is enabled. A portable implementation must open files
with `encoding="utf-8"`; BSC should not reuse the current default-locale code.

A filename-only secret heuristic found three `sk-...`-shaped matches, all in
README or `env.example` tutorial material. No candidate value was printed,
used, copied, or committed. This is not a full secret audit of all 2,253 files.

## BSC Adoption Status

### Already Implemented

The highest-value Advisor/Worker rule has already been implemented in BSC.
`app/dbos/execution.py` now creates `TaskVerificationArtifact` only for a
provider-reported real/API execution. It reads the persisted Artifact Graph and
fails the execution with `task_verification_failed` when reported artifact IDs
are absent or registered output types are missing. Plain test callbacks remain
unverified rather than being promoted to a delivery claim.

The UI and API expose that verdict through:

* `app/dbos/service.py`
* `app/artifacts/types.py`
* `src/api/dbosApi.ts`
* `src/components/dbos/BusinessControlCenter.tsx`

Focused verification already passed:

```text
pytest tests/dbos tests/api/test_dbos_api.py tests/mcp/test_dbos_tools.py \
  tests/mcp/test_dbos_http_contract.py tests/test_artifact_scope.py -q
26 passed

npm run test:frontend -- --run \
  src/components/dbos/BusinessControlCenter.test.tsx src/api/dbosApi.test.ts
7 passed

npm run check
npm run build
passed
```

### Concrete Follow-On Work

| Priority | BSC work item | Source lesson | Acceptance evidence |
| --- | --- | --- | --- |
| P1 | Add positive/negative trigger cases to Method and SOP routing | Skill lexical routing | Wrong-method and sibling-method cases must fail deterministically |
| P1 | Add a reusable knowledge/agent failure taxonomy | RAG diagnostics clinic | A failure is stored with a code, evidence, cause, retry decision, and resolution |
| P1 | Persist source adapter status and raw evidence snapshots | DevPulse | A failed source is visible; every published claim reaches immutable source evidence |
| P1 | Surface real task plans, source states, and artifacts together | Generative research UI | UI values come from project-scoped run/artifact records, never simulated local state |
| P2 | Add gated method-improvement experiments | Self-improving Skill | Baseline, holdout, negative cases, cost, proposal, reviewer gate, and rollback are all persisted |
| P2 | Add advisory risk/relevance models as non-authoritative signals | DevPulse | Model/heuristic provenance and confidence are shown; no score can auto-publish |
| P3 | Add a provider-neutral external worker adapter | Advisor/Worker | Requires explicit outbound data policy, cost quota, credential configuration, sandbox, and integration test project |

### Explicit Non-Adoption

* No embedded second Agent framework or duplicate web application.
* No API keys supplied through browser request bodies or checked into runtime
  configuration.
* No `npx -y` MCP launcher, inherited environment forwarding, or automatically
  trusted local filesystem server.
* No autonomous mutation that writes a Method, Wiki page, or Skill directly to
  the published knowledge base.
* No global Neo4j/Qdrant clearing or shared collection replacement.
* No claim that an external multi-agent team executed without its actual
  provider, tools, audit record, and outputs.

## Completion Standard

The archive has been analyzed down to its repository structure, core CI,
representative orchestration, information intake, RAG, MCP, UI, and security
boundaries. It should not be described as a drop-in BSC dependency. BSC has
already adopted its most critical delivery-verification rule; the remaining
adoptions above are separate, testable BSC product work and cannot honestly be
marked complete until their source, proposal, evaluation, authorization, and UI
contracts are implemented and verified.

## Follow-Up Implementation (2026-07-25)

The previously identified P0 source-trust gap is now implemented without
adding a second agent runtime or a second configuration database. BSC stores a
typed `ProjectSourcePolicy` inside the existing revisioned project profile.
It governs primary, trusted, community and blocked origin prefixes, trusted
and mandatory-triage source types, and authority-specific retention periods.

`SourceCaptureService` resolves the persisted project policy for every normal
capture. The immutable `SourceRecord` and privacy-bounded
`SourceCaptureAttempt` store the policy source, profile revision, full
non-secret policy snapshot, authority result, retention days and expiry. A
blocked origin is retained as rejected audit evidence and is never projected
to the search index. Horizon uses the same capture service, so its signals
inherit the project policy but continue to require project triage.

The Profile REST surface and Growth Workspace editor expose this configuration
through the existing compare-and-swap revision contract. Focused verification
passed for profile history, API validation, capture outcomes, Horizon import,
workspace API, TypeScript and the profile UI. The remaining material adoption
work is method self-improvement with positive/near-negative/holdout gates; an
external worker tier remains intentionally unavailable until explicit egress,
credential, cost, sandbox and integration-test requirements are met.

## Follow-Up: Routing Evaluation Evidence

The deferred governed-improvement work is no longer only a recommendation.
Method evolution now enforces revision lineage, one declared mutation,
positive/near-negative/isolated-holdout routes, non-regression and a reviewer
gate. Dynamic SOP routing has the analogous durable boundary:
`SOPRoutingEvaluationArtifact` stores a versioned selector fingerprint, three
positive cases, two near-negative cases and two holdout cases for every newly
compiled Mission.

The deterministic suite exercises diagnosis, capability selection and
compilation without an LLM or an external system. Its record is linked to the
Mission, Diagnosis, Selection and SOP in the Artifact Graph, returned through
REST/MCP/control-center/export projections, and is required before Mission
confirmation or execution. The suite also discovered a genuine substring
routing defect (`ai` matching within `constraints`); both selector and
compiler now require word-boundary matching for short ASCII identifiers.

Current focused verification: 21 DBOS/API/MCP tests, 11 frontend/API-client
tests and TypeScript checking pass. This does not promote the external worker
tier: egress, secret storage, budgets, sandboxing and integration evidence are
still explicit prerequisites.
