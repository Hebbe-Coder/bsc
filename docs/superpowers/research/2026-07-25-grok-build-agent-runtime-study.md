# Grok Build Agent Runtime Study and BSC Adoption Record

## Scope

Reference reviewed: `C:/Users/34216/Downloads/grok-build-main.zip`.

This is a source-level architecture study, not a claim that BSC embeds or
redistributes Grok Build. The reference is a Rust workspace centered on a local
coding-agent product. BSC remains a project-scoped business, knowledge, and
content operating system.

## What The Reference Gets Right

### Agent Definition Is A Governed Object

`crates/codegen/xai-grok-agent/src/config.rs` composes an agent from a toolset,
model/prompt behavior, scheduler, task delegation, and lifecycle constraints.
The important idea is not its local shell tools. It is that an agent's permitted
surface is explicit and inspectable rather than implied by one long prompt.

### Context Is A First-Class, Inspectable Snapshot

`crates/codegen/xai-grok-agent/src/prompt/context.rs` serializes prompt mode,
audience, project rules, role instructions, memory availability, environment,
and timestamp. Primary and sub-agent contexts differ intentionally. This
prevents a child task from receiving accidental authority or irrelevant history.

### Plugins Must Be Discoverable Before They Are Executable

`plugins/manifest.rs` resolves component paths only under the plugin root and
is forward-compatible with unknown manifest fields. `plugins/trust.rs` keeps a
separate canonical-path trust store: untrusted plugins may be listed, while
hooks, MCP servers, and scripts remain blocked. This distinction is essential
for any Obsidian/Skill/MCP ecosystem.

### Durable Runtime State Beats Prompt History

`xai-chat-state` and `xai-grok-compaction` keep state, usage, compaction, and
recovery independent from the visible terminal transcript. A resumed session
therefore starts from an explicit summary and ledger instead of pretending that
the full old conversation is still available.

### Compaction Is a Guarded State Transition

`xai-grok-compaction` does not treat summarization as a cosmetic prompt edit.
Its trigger records the actual token/window ratio and step; successful results
record before/after tokens and replaced turns; malformed or empty summaries are
rejected before persistence. `xai-chat-state` repairs dangling tool calls when
hydrating a crashed conversation. The reusable principle is: an interrupted
model/tool turn has an explicit, reviewable outcome rather than being silently
continued or re-run.

## BSC Changes Implemented

### One DBOS Ledger Across UI, REST, And MCP

`app/dbos/` remains the sole policy layer for Mission -> diagnosis ->
capability selection -> Dynamic SOP -> confirmation -> execution. The REST
facade in `app/api/dbos_api.py` and the MCP facade in `app/mcp/dbos_tools.py`
delegate into that same project-scoped Artifact Graph. Capability execution is
still rejected until a user has confirmed a selected capability.

The MCP HTTP/SSE catalog now publishes five DBOS tools with schemas and feature
gating. Project keys can read only their own project; readers cannot mutate;
project admins and system credentials must match the requested project.

### PromptOps: Context Policy Before Provider Calls

`app/promptops/` is the BSC counterpart to an inspectable prompt context:

- Task profiles route SOP, Wiki, RAG, distillation, and quality work to
  `deepseek-v4-pro` by default; small extraction/sufficiency work routes to
  `deepseek-v4-flash`.
- A configured project model revision may override the default route. The
  override is explicitly recorded rather than silently changing behavior.
- `public` and `internal` inputs are secret-redacted and fenced as untrusted
  data. Raw `private` and `confidential` data fail closed. Only an explicit
  sanitized derivative may leave the process.
- The append-only audit records project, task, revision, model, status, and
  cryptographic fingerprints. It never stores prompts, source bodies, outputs,
  or credentials.

The weekly/daily semantic distillation provider now uses PromptOps. Existing
citation validation, quality checks, fallback documents, and no-false-success
semantics remain outside the model call and are unchanged.

Wiki proposal compilation, non-mock RAG answer generation, and the default
project-scoped `SopBuilderAgent` composition path now use the same boundary.
RAG's two-phase citation plan uses the bounded `RETRIEVAL_SUFFICIENCY` profile
before its `RAG_ANSWER` profile, and rejects plan IDs absent from the retrieved
evidence. SOP composition uses the `SOP_COMPOSITION` profile with a versioned
revision and preserves injected LLM clients solely as deterministic test and
offline seams. Provider keys, when a caller supports rotation, remain
runtime-only and are excluded from audit serialization.

### Runtime Context and Manual Recovery

`RuntimeContextArtifact` now records the composition contract for a DBOS
diagnosis/execution: policy revision, mission/diagnosis/selection lineage,
knowledge IDs, context field names, token budget and cryptographic
fingerprints. It is intentionally redacted: no mission body, raw source,
provider response or credential is copied into the ledger.

Every capability attempt now appends `RunCheckpointArtifact` events for
dispatch, completion, failure, or restart interruption. On FastAPI startup,
BSC scans project DBOS ledgers and changes persisted `executing` attempts to
`interrupted`; it returns the Mission to `confirmed` and requires an explicit
new idempotency key for a manual retry. This follows Grok's durable-state
discipline while preserving BSC's side-effect safety: a restart never implies
permission to replay an action.

### Bounded Context Compaction With Recovery Pointers

The source's `xai-chat-state` compaction mode makes an important distinction:
a summary is lossy, while the session transcript or segment store remains an
authoritative recovery source. BSC's prior `ContextManager` only produced a
bounded inline summary. A caller could not determine which inherited segments
were retained, summarized, or dropped after its token budget was applied.

`app/core/context_policy.py` now emits a `bsc-context-v2` manifest on every
`fresh`, `fork`, and `resume` request. It records only role, priority, token
estimate, content fingerprint, disposition and source session id. It never
copies prompt/source text or provider credentials. `fresh` intentionally
contains no parent entries. `fork` and `resume` mark inherited entries as
`included`, `summarized`, or `omitted` and preserve their source-session
references so the API layer can rebuild another bounded packet from the
authoritative persisted session rather than treating a summary as canonical.

The capability runtime carries this redacted manifest alongside the existing
usage object. This makes model context composition inspectable in
the Studio/runtime response without turning the event ledger into a prompt
archive. Studio's control rail renders the manifest id and the actual
included/summarized/omitted counts after a run. The summary itself is now
bounded before rendering; an overflow can no longer silently truncate an
unknown number of inherited lines.

### Studio Control Plane

`BusinessControlCenter` is reachable from BSC Studio's `Operate` action. It
shows persisted diagnosis, capability authorization, Dynamic SOP tasks, actual
execution attempts, feedback memory, and the Artifact Graph through React Flow.
It starts from a diagnosis form rather than an SOP template selector. The view
does not show invented execution activity when a mission has not run.

## Deliberately Not Adopted

- No arbitrary local file editing, PTY terminal management, worktree handling,
  or shell execution has been introduced into the business/knowledge runtime.
- No Obsidian plugin, Skill package, or MCP command is auto-trusted merely by
  appearing in a directory. Existing connectors stay metadata/manifest based
  until their concrete execution and scope are validated.
- No third-party system prompt has been copied. PromptOps uses BSC's own
  structured contracts, project isolation, provenance, and audit rules.
- BSC does not expose a terminal transcript reader or automatically invoke an
  LLM to rewrite conversation history. The adopted summary mode is deterministic
  and recoverable through source-session references; semantic compaction would
  require its own evidence and evaluation contract before adoption.

## Acceptance Evidence

The implementation is verified by DBOS REST/domain/MCP tests, PromptOps policy
tests, project-scoped Wiki/RAG/SOP composition tests, DBOS control-center tests,
TypeScript checking, and the existing knowledge distillation/model-client tests.
Docker-dependent Redis/PostgreSQL/Celery execution remains outside this evidence
until containers are available.

## Follow-up: Explicit Prompt Agent Manifests

The source goes further than choosing a model and rendering a prompt. Its
`xai-grok-agent` `AgentDefinition` binds a role to a deliberately bounded
toolset, prompt audience, compaction policy, and delegation behavior. The
useful BSC analogue is not a shell-enabled worker. It is an exact, inspectable
definition for every external model invocation.

`app/promptops/contracts.py` now defines a versioned BSC profile for each
PromptOps task: SOP composition, Wiki compilation, knowledge distillation,
retrieval planning, RAG answering, extraction, and quality review. Each
profile fixes its role identity, primary/subagent audience, governed-context
memory policy, no-delegation rule, structured-model-only tool policy, and
prohibition on external side effects. A caller may provide a stricter profile,
but it cannot cross task families or enable side effects.

Before the provider boundary, `PromptOps` creates a redacted
`PromptAgentManifest`. It binds the profile, selected model, override state,
prompt/input fingerprints, and a hash of explicit project-context references.
The append-only audit ledger stores this manifest fingerprint and policy facts,
not prompt text, source text, output text, reference IDs, or provider keys.
The returned `PromptRun` carries the same manifest so a caller can attach it to
its own governed execution evidence.

SOP composition passes the source/page/method/output identifiers actually
admitted by its selected knowledge context into this contract. This creates an
auditable link from a custom SOP back to its knowledge context without turning
the audit log into a copy of the Vault.

### Follow-up Acceptance Evidence

- `48` focused PromptOps, distillation, Wiki, RAG, SOP, and knowledge
  end-to-end tests passed after the manifest integration.
- `npm run check` passed.
- The focused tests prove policy-blocked and provider-success paths use the
  same redacted manifest contract, and prove references remain absent from the
  audit record body.

## Follow-up: Provider Usage Is Not A Prompt Estimate

The reference's `xai-chat-state/src/usage.rs` treats usage as a separate,
incomplete-aware ledger. This matters when an agent makes an internal repair
call: a final valid result does not erase the earlier provider spend. It also
refuses to claim a complete bill when any provider response omits usage.

BSC now applies that rule at `app/promptops/`. `PromptUsage` folds only
provider-reported `ModelUsage` values from the structured client, preserving
provider call count, reported-call count, latency, cached/reasoning tokens and
a completeness flag. Any missing aggregate stays absent. `SOPLLMClient` tracks
all successful low-temperature/JSON-mode repair responses for one structured
request, so PromptOps can record both calls without retaining prompt or output
content.

The redacted PromptOps audit record contains the usage projection next to the
existing agent manifest facts. It contains no provider key, prompt, source,
output, or cost estimate. A real public-only DeepSeek smoke call verified that
provider usage reaches this ledger. This is adopted for model quality and cost
diagnosis, not copied from the reference's terminal-agent product.

## Follow-up: Governed Retry Lifecycle

`xai-grok-sampler/src/retry.rs` separates pure error classification from the
actor that sleeps and resubmits. Its useful rule is precise: transport, service
and bounded rate-limit failures can be retried; authentication, configuration,
request-shape, serialization and maximum-context failures are terminal. A
successful later sample must not erase the cost or evidence of earlier calls.

BSC now applies that rule at the existing PromptOps model boundary. A request
has a small explicit outer budget (two attempts by default, three maximum), a
bounded exponential backoff, and an independent rate-limit cap. The structured
client still owns key rotation and JSON repair inside an attempt. PromptOps
only retries stable transient categories after that client returns a failure.
It reuses one prompt run ID, emits a redacted `retrying` audit entry before
sleeping, and folds every provider-reported attempt into the terminal usage
record. Missing usage remains missing; no retry cost is estimated.

The smaller budget is deliberate. Grok Build is an interactive coding sampler
that can tolerate minutes of retry time. BSC's scheduled knowledge and business
work must not silently amplify provider spend, delay a workflow indefinitely,
or retry an invalid instruction. Provider configuration, credentials, payment,
policy rejection, oversized context and malformed structured output therefore
remain terminal and visible for review.

Growth distillation projects the resulting attempt count, retry count and a
fixed set of safe categories into its durable run event. The Studio model card
shows total attempts and retries beside total provider usage. The public event
projection is strictly allowlisted, so a raw exception, prompt, output or key
cannot reach the browser along with the new telemetry.

## Follow-up: Grounded Adaptive Outputs Instead Of Fluent Template Rewrites

`xai-grok-sampler/src/doom_loop.rs` is a useful reminder that a model turn is
not accepted merely because the transport returned valid text. Grok receives
provider-side streaming signals and records them per request attempt. BSC uses
bounded structured responses rather than that streaming protocol, so it does
not pretend to receive Grok's server signal or copy the terminal behavior.

The directly applicable gap was in BSC's adaptive Dynamic SOP compiler. It
previously rejected invalid structure and exact copies of the deterministic
task skeleton, but could accept fluent generic rewrites that mentioned no
Mission evidence. That outcome still looked "completed" despite being a
template with different prose.

`app/dbos/adaptive_compiler.py` now adds a deterministic specificity gate
after JSON/graph validation and before persistence. It derives compact terms
from the declared goal, constraints, success metrics, and evidence findings.
Every generated phase and every task's title/deliverable/metric must contain a
distinctive Mission term; at least two distinct anchors must appear across the
result. System-provided capability and task-family labels are removed before
matching, so repeating `conversion_experiment` cannot masquerade as a tailored
business fact. Generic language is rejected as `model_output_not_grounded` and
the deterministic SOP is retained.

The persisted `adaptive_compilation.specificity` result contains only counts
and task/phase IDs, never source bodies or anchor terms. This makes a fallback
reviewable without expanding the DBOS audit surface. It is deliberately a
literal grounding check, not a claim to solve semantic similarity; a future
semantic checker needs its own held-out evaluation set before it can gate
publication.
