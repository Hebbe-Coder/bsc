# awesome-llm-apps Source-Verified Architecture Analysis

**Audit date:** 2026-07-26
**Archive:** `C:\Users\34216\Downloads\awesome-llm-apps-main.zip`
**SHA-256:** `8D6504BB9D5DB7CCB7DA670669D7261077A1313F71BA706F918672B9B656A008`
**Extraction (audit-only):** `C:\Users\34216\AppData\Local\Temp\awesome-llm-apps-audit\awesome-llm-apps-main`
**Purpose:** determine what BSC can adopt as a product rule without importing a second runtime, state store, authentication system, or MCP control plane.

## 1. Executive conclusion

`awesome-llm-apps` is a curated learning repository, not a deployable platform.
It contains many independent applications with incompatible runtimes, provider
assumptions, state models, and security boundaries. It should never be merged
into BSC as a package or used as the source of truth for a production workflow.

Its strongest value is architectural, not code reuse:

1. Use deterministic code for collection, normalization, deduplication, and
   policy enforcement. Use an LLM only where judgment, interpretation, or
   synthesis is actually required.
2. Split roles by authority: planning/review, execution, verification, and
   publication are different responsibilities and must have separate durable
   records.
3. Treat a task as complete only after its promised artifact can be read and
   verified, not after a model call or HTTP request returns successfully.
4. Treat knowledge as evidence with provenance, reviewable proposals, citations,
   evaluation, and rollback, rather than a one-shot RAG index or a generated
   Markdown file.
5. Make a live workspace show the plan, sources, tool calls, files, failures,
   and publication decision together, while keeping all displayed states backed
   by the server rather than browser memory.

BSC already has source-level counterparts for most high-value patterns in the
current working tree: `ArtifactGraphStore`, task verification, DBOS routing
evaluations, immutable knowledge-source contracts, method-evolution gates,
scoped MCP tools, and the Knowledge/Growth/DBOS workspaces. Those files are
currently uncommitted, so their presence is not a release claim. Any adoption
work must be verified and committed as a coherent BSC change rather than copied
from the examples.

## 2. Scope, coverage, and limits

The archive was extracted and inventoried recursively. It contains **1,757
files**, not the 2,253 files stated in the earlier 2026-07-25 research note.
The earlier count must not be used as an audit fact.

| Area | Files | Python/JS/TS/TSX lines | Primary content |
| --- | ---: | ---: | --- |
| `advanced_ai_agents` | 536 | 62,415 | single and multi-agent demonstrations |
| `generative_ui_agents` | 517 | 25,937 | Next.js/CopilotKit and generated UI demos |
| `ai_agent_framework_crash_course` | 250 | 9,363 | framework tutorials |
| `advanced_llm_apps` | 193 | 4,174 | memory, RAG, and optimization demos |
| `rag_tutorials` | 98 | 7,581 | retrieval and graph-RAG examples |
| `agent_skills` | 39 | 3,608 | skill definitions and local evaluation tools |
| `voice_ai_agents` | 25 | 3,657 | voice interactions and voice RAG |
| `mcp_ai_agents` | 20 | 1,155 | MCP client and router demonstrations |
| `always_on_agents` | 11 | 734 | scheduled briefing examples |

The archive has 508 Python, 204 TSX, 93 TypeScript, 55 JavaScript, 256 Markdown,
and 83 JSON files. The repository-wide inventory, dependency manifests, and
all relevant high-value implementations below were inspected from source.

This is a source-verified architecture audit, not a formal proof of the
behavior of every line in roughly 120,000 lines of example code. No analysis
should claim that every example is production-safe. The detailed review covers
the examples that materially overlap BSC: information collection, multi-agent
orchestration, RAG, knowledge graph/citations, skill governance, MCP, scheduled
automation, and the research workspace UI.

## 3. Repository architecture: what it is and is not

The repository has no shared domain model, service boundary, database migration
lineage, cross-application authorization, or common deployment contract. Each
folder normally owns its own framework, state, API key flow, and UI.

```text
many standalone demonstrations
  -> provider/framework-specific process state
  -> local Streamlit or Next.js UI
  -> direct model/tool calls
  -> transient output
```

That is appropriate for teaching a narrow pattern. It is the opposite of the
BSC target:

```text
project + role + mission authorization
  -> durable artifact/evidence/decision lineage
  -> scoped deterministic or LLM capability
  -> explicit verification, evaluation, retry, publication, or rollback
  -> API/MCP/Studio projections of the same persisted state
```

Consequently, BSC must adopt a pattern only if it can be expressed through its
existing project boundary and Artifact Graph. Importing `Agno`, Google ADK,
AG2/AutoGen, Streamlit, CopilotKit, or a demo MCP subprocess launcher would
create duplicate state and weaken the existing authorization model.

## 4. High-value source studies

### 4.1 DevPulseAI: the correct information-collection split

**Source:** `advanced_ai_agents/multi_agent_apps/devpulse_ai/`

DevPulse is the best reference for the Horizon side of BSC because it makes one
correct design decision explicit:

```text
source adapters
  -> SignalCollector (normalize + deterministic deduplicate)
  -> RelevanceAgent (judgment)
  -> RiskAgent (judgment)
  -> SynthesisAgent (cross-source interpretation)
```

`SignalCollector.collect()` uses a `source:id` composite key, fills a common
signal shape, and adds a collection timestamp. GitHub, arXiv, Hacker News,
Medium, and Hugging Face are independent HTTP/RSS adapters. Relevance and risk
are delegated to cheaper models; synthesis is delegated to a stronger model.
This separation is sound because fetching, normalizing, and filtering malformed
records are mechanical operations, while relevance and implications are not.

What BSC should retain:

- a narrow adapter interface returning raw records and capture facts;
- deterministic canonicalization and deduplication before any LLM call;
- inexpensive classification before expensive cross-source synthesis;
- a clear distinction between model output and heuristic fallback;
- a source-specific failure record rather than silently calling a partial run a
  successful collection.

What BSC must strengthen:

| DevPulse behavior | Why it is insufficient | BSC rule |
| --- | --- | --- |
| `source:id` only | URL changes and cross-source reposts remain duplicates | retain external ID, canonical URL, raw-body hash, and merge candidates |
| HTTP exceptions print and return `[]` | the user cannot distinguish no news from failed collection | persist `SourceCaptureAttempt` with outcome, retry policy, and error class |
| heuristic and model scores share a shape | a fallback score can look like model judgment | record `assessment_provenance=deterministic|heuristic|model` |
| ranking uses relevance times risk multiplier | a list order is not evidence for publication | publish only through citation and evaluation gates |
| short summaries are the stored result | primary evidence cannot be reviewed or rebuilt | preserve immutable source body/attachment hash and retention policy |

The DevPulse README claims `python verify.py` has no API keys, no network calls,
and no external dependencies. This was tested. On the Windows GBK terminal it
first fails while printing an emoji. With `PYTHONIOENCODING=utf-8`, it then
fails at import time with `ModuleNotFoundError: No module named 'agno'` because
`agents/__init__.py` imports the three Agno-backed agents. Its mock verifier is
therefore not dependency-free as claimed. BSC must not model its verification
standard on this demonstration.

### 4.2 Advisor-Orchestrator-Worker: verification is a role, not a prompt

**Source:** `agent_skills/advisor-orchestrator-worker/SKILL.md`

This is a well-written operational skill. It defines three authority levels:

- **Advisor:** critiques decomposition, risks, and final quality; it does not
  execute tasks.
- **Orchestrator:** writes checkable acceptance criteria, assigns independent
  briefs, resolves conflicts, and manages budget/retry state.
- **Worker:** produces one isolated deliverable.

Its most transferable rule is precise: verification must exercise the actual
deliverable, not an adjacent signal such as a command exiting zero, a README
mentioning the feature, or a callback that did not throw. Per-subtask verdicts
are `PASS`, `FIX`, or `ESCALATE`; two failures or a structural plan conflict
triggers a higher-authority review.

The BSC translation is:

```text
Mission/Decision -> Dynamic SOP task -> authorized capability
  -> output artifacts -> TaskVerificationArtifact
  -> verified | failed | pending evidence
```

The skill itself passes the bundled strict `skill_lint.py` check, which confirms
that it is a coherent AgentSkills package. That only validates its metadata and
local references. It does not make its runtime safe to embed.

Do not import its dispatcher. It launches `agy` with
`--dangerously-skip-permissions`, runs workers in temporary directories,
uses plain files as a status board, falls back to environment credentials, and
has no BSC project authorization, egress budget, durable audit record, or
artifact ownership check. An empty temporary directory is not a sandbox.

### 4.3 AG2 adaptive research: useful role topology, unsafe evidence contract

**Source:** `advanced_ai_agents/multi_agent_apps/agent_teams/ag2_adaptive_research_team/`

The topology is useful:

```text
triage -> local or web researcher -> verifier -> synthesizer
```

The model prompts correctly distinguish local evidence from web evidence and
reserve a verifier role. However, `router.py` extracts JSON with a greedy regex,
uses an in-memory lexical overlap index, sends a final synthesis request even
when the verifier returns `insufficient`, and leaves evidence in request-local
lists. The syntheses therefore have no durable, independently inspectable
source fragments or citation positions.

Use the topology only. In BSC, an `insufficient` evidence verdict must be a
first-class result that blocks a supported-answer or Wiki publication path;
the source evidence must be persisted as `SourceRecord` and `CitationLink`
before a model can synthesize it.

### 4.4 Corrective RAG and graph RAG: preserve branching semantics, reject storage

**Sources:**

- `rag_tutorials/corrective_rag/corrective_rag.py`
- `rag_tutorials/knowledge_graph_rag_citations/knowledge_graph_rag.py`
- `rag_tutorials/rag_failure_diagnostics_clinic/rag_failure_diagnostics_clinic.py`

The Corrective RAG state graph contains an important semantic branch:

```text
retrieve -> grade documents -> generate
                         -> rewrite question -> web search -> generate
```

This is worth preserving: external search is an escalation because local
evidence is insufficient, not a hidden substitute for retrieval. BSC should
also retain the reason for escalation and return an evidence gap when public
collection or search fails.

The example implementation is not reusable. It collects browser-entered API
keys in Streamlit session state, parses model JSON with a regular expression,
and deletes/recreates the global `rag-qdrant` collection whenever a document is
loaded. It has no project scope, retention boundary, provenance contract, or
rebuild-safe index management.

The graph-RAG example correctly names `Entity`, `Relationship`, `Citation`, and
`AnswerWithCitations`. Its `clear_graph()` executes global Neo4j
`MATCH (n) DETACH DELETE n`, and relationships do not carry enough project,
fragment, proposal revision, confidence-status, or rollback facts. BSC graph
edges need at least `project_id`, source record and fragment IDs, extraction
method, timestamp, confidence, `proposed|published|retracted` lifecycle, and
the revision that owns the extraction.

The diagnostics clinic provides the most reusable operational taxonomy:

| Pattern | BSC interpretation |
| --- | --- |
| P01 grounding drift | answer/SOP claim conflicts with cited evidence |
| P02 chunk boundary | a fact is lost or distorted during segmentation |
| P03 embedding mismatch | vector similarity is not semantic relevance |
| P04 index staleness | derived index diverges from an authority source |
| P05 router misalignment | wrong project, method, tool, or corpus selected |
| P06 long-chain drift | later SOP stages lose an early constraint |
| P07 tool misuse | invalid parameters or ungrounded tool call |
| P08 memory defect | missing or leaked conversation/project context |
| P09 evaluation blind spot | offline checks pass while real work fails |
| P10 dependency readiness | worker, broker, index, or service is unavailable |
| P11 configuration drift | environment, model, or secret configuration differs |
| P12 tenant interference | project records, runs, or context cross boundaries |

This taxonomy should be a structured `FailureRecord` linked to the affected
run, task, source, method revision, retry decision, and resolution. It is not
enough to write a Markdown diagnosis to a local file.

### 4.5 Self-improving skills: single-variable experiments, not automatic rewrite

**Source:** `agent_skills/self-improving-agent-skills/`

The useful loop is:

```text
baseline -> execute scenarios -> identify one failure pattern
  -> one declared mutation -> re-run evaluation -> retain or revert
```

The Executor, Analyst, and Mutator roles distinguish scoring, diagnosis, and
mutation. `FailureAnalysis` and `SkillMutation` Pydantic models are a good
example of structured boundaries. Keeping a change only after a measured
improvement is the right experiment discipline.

The implementation cannot govern BSC methods. It accepts a Gemini key in the
browser request and writes it into process-global `GOOGLE_API_KEY`, retains
sessions in `InMemorySessionService`, asks the same model family to generate
tests, simulate the skill, score it, diagnose it, and mutate it, and replaces
the full `SKILL.md` text. It has no project isolation, independent holdout set,
negative samples, revision conflict handling, reviewer gate, or rollback.

The BSC equivalent must remain:

```text
published baseline revision
  -> verified production outputs + positive/near-negative/holdout evaluation
  -> exactly one declared mutation dimension
  -> immutable proposal and evaluation evidence
  -> eligible for reviewer gate | discarded | unavailable
  -> reviewer-only publication or rollback
```

The folder is an application, not an AgentSkills package; running the bundled
skill linter against it correctly fails because no root `SKILL.md` exists. This
is further evidence that it should not be treated as a plug-in ready for BSC.

### 4.6 AgentSkills eval tooling: directly reusable as a quality-gate concept

**Source:** `agent_skills/evals/tools/skill_lint.py` and `skill_scanner.py`

This is the most mature part of the archive. The linter validates structured
metadata, name-to-directory identity, explicit trigger language, bounded
instruction length, missing relative references, unresolved placeholders, and
whether a skill bundles tools/references rather than being unbounded prose. The
security scanner statically checks common remote-execution, obfuscation,
network, secret, and prompt-injection patterns without executing the skill.

For BSC, these should become capability/method packaging gates, not another
runtime:

- lint and scan a candidate method or MCP capability before it may be proposed;
- attach findings to the proposal and Artifact Graph;
- fail closed on critical scanner findings;
- allow suppressions only as explicit, reviewed policy decisions;
- keep execution permissions separate from documentation quality.

### 4.7 MCP router: smallest task-specific tool set is the correct rule

**Source:** `mcp_ai_agents/multi_mcp_agent_router/agent_forge.py`

The beneficial pattern is a task-specific tool subset: a code-review request
gets repository tools, a research request gets fetch tools, and an agent should
not receive every tool simply because the process can start them. This directly
supports BSC capability selection.

The implementation is unsafe as an integration: it chooses agents by keyword
substrings, runs `npx -y` MCP servers dynamically, inherits `os.environ`,
accepts an Anthropic key in the Streamlit sidebar, maps tool names globally,
and keeps conversation history only in browser memory. There is no server
allowlist, project/mission/task authorization, egress policy, budget, output
artifact requirement, or recovery story.

BSC must keep its existing HTTP/SSE/stdio transports and construct an
allowlisted minimal capability set from `project + mission + task + decision`.
Every tool call must create durable input, output/evidence, error, and
authorization lineage.

### 4.8 Always-on agent: dry-run honesty is valuable; scheduler persistence is absent

**Source:** `always_on_agents/always_on_hn_briefing_agent/`

`scheduler_api.py` defaults every scheduled trigger to `dry_run=true` and
returns a delivery status rather than claiming a notification was sent. This is
the correct user contract. `agent.py` also explicitly separates rendering a
brief from delivery.

It is still a demo scheduler: trigger endpoints have no authorization, no
durable schedule/run/idempotency records, no retry ledger, and no project
ownership. The BSC translation is a persisted `KnowledgeSchedule` and
`KnowledgeRun` backed by Celery/Redis, with checkpoints, idempotency, outcome
truthfulness, retry policy, and an Obsidian output artifact only after the
write actually succeeds.

### 4.9 Deep Research UI: adopt evidence-first interaction, not its decorative shell

**Source:** `generative_ui_agents/ai-deep-research-agent/`

This example is a good interaction reference. Its workspace has three
inspectable objects beside chat:

1. a visible research plan with pending/in-progress/completed states;
2. generated files that can be previewed/downloaded;
3. source cards with `found`, `scraped`, and `failed` states.

`ToolCard.tsx` renders known tool calls as domain-specific cards and falls back
to expandable JSON only for unknown tools. This is a useful principle for BSC:
task verification, source capture, Wiki diffs, method evaluations, and external
worker cancellation must have purpose-built views, while unrecognized artifacts
can use a compact technical inspector.

Do not copy its implementation or visual shell. `page.tsx` keeps research
state in React memory and deduplicates with a manually assembled
length-and-prefix hash; its Python agent uses LangGraph `MemorySaver`; it uses
an animated glass/blob background and fixed 38%/62% desktop split. Those are
poor fits for BSC's dense operational workspace, responsive requirements, and
server-authoritative runs. BSC should use its own durable API projections,
three-pane responsive layout, real ECharts trends, and React Flow graph.

## 5. Cross-cutting risks found in the reference archive

These are normal shortcuts for teaching examples, but they are unacceptable as
BSC production defaults:

1. **Browser-provided credentials:** Corrective RAG, Multi-MCP Agent Forge, and
   the self-improving app accept provider secrets in UI/request state.
2. **Transient state:** Streamlit session state, React state, process globals,
   and `InMemorySessionService` are used as runtime truth.
3. **Dynamic executable acquisition:** MCP examples launch `npx -y` servers and
   may inherit the full host environment.
4. **Destructive global data operations:** Corrective RAG deletes a shared
   collection; graph RAG deletes every Neo4j node and edge.
5. **Fragile structured output:** several examples recover JSON with regular
   expressions instead of a validated typed response protocol.
6. **Truthfulness gaps:** HTTP failures often become empty results, fallback
   heuristics can look like LLM assessments, and UI completion can be driven by
   local state rather than verified output.
7. **Missing multi-tenant controls:** examples do not consistently associate
   sources, graph edges, tool calls, sessions, files, or schedules with a
   project boundary.

## 6. BSC adoption matrix

| Pattern | Decision | BSC destination | Required acceptance evidence |
| --- | --- | --- | --- |
| deterministic signal collection | adopt and harden | Horizon adapters -> capture attempts -> immutable sources | retry/timeout/duplicate/provenance tests |
| role separation and real verification | adopt | DBOS tasks + `TaskVerificationArtifact` | missing/wrong artifact must fail task |
| local-vs-web evidence routing | adopt semantics | answer/Wiki context builder | insufficient evidence must block grounded answer/publication |
| citation graph | adopt with provenance | `CitationLink` + project-scoped graph projection | every graph edge links to a source fragment/revision |
| RAG failure taxonomy | adopt as records | run/task/source/method failure ledger | P01-P12 routing and retry tests |
| one-mutation method improvement | adopt with reviewer gate | method evolution -> proposal -> evaluation -> gate | holdout non-regression and rollback tests |
| Skill lint/security scanning | adopt as policy gate | method/capability packaging workflow | critical findings block proposal/execution |
| minimal MCP tool set | adopt | existing scoped MCP capability selection | no unapproved tool reaches a task |
| dry-run automation | adopt | Celery schedules and delivery adapters | dry run cannot claim delivery; retry is durable |
| research workspace information architecture | adopt selectively | Knowledge/Growth/DBOS Studio | server-backed source/run/diff/failure states, desktop/mobile tests |
| Agno/ADK/AG2/Streamlit/CopilotKit runtimes | reject | none | no duplicate state/auth/runtime introduced |
| dynamic `npx` MCP server launch | reject | none | only preconfigured, allowlisted server contracts |

## 7. Current BSC alignment and outstanding work

The current working tree contains source-level evidence of the following BSC
counterparts:

| Reference lesson | Current BSC source location |
| --- | --- |
| durable artifact and project scope | `app/artifacts/store.py`, `app/artifacts/types.py` |
| verified output before DBOS completion | `app/dbos/execution.py`, `TaskVerificationArtifact` |
| deterministic SOP selector replay | `app/dbos/evaluation.py`, `SOPRoutingEvaluationArtifact` |
| source/capture/citation/run contracts | `app/knowledge/wiki_contracts.py` |
| immutable method-evolution experiments | `app/knowledge/method_evolution.py` |
| knowledge capture and Horizon boundary | `app/knowledge/horizon_import.py`, `app/knowledge/wiki_source_capture.py` |
| scoped REST/MCP projections | `app/api/dbos_api.py`, `app/mcp/dbos_tools.py`, `app/mcp/growth_tools.py` |
| durable Studio clients/workspaces | `src/components/KnowledgeWorkspace.tsx`, `src/components/growth/GrowthWorkspace.tsx`, `src/components/dbos/BusinessControlCenter.tsx` |

This review did not modify those modules and did not re-run the entire BSC
regression suite. The repository is already heavily dirty, including these
modules. Before further product work, the owner should first preserve the
current known-good BSC changes in an atomic commit or otherwise establish a
clean baseline. New `awesome-llm-apps` work must then be split into reviewable
commits, with no archive code copied into BSC.

The concrete gaps worth pursuing after baseline preservation are:

1. make the P01-P12 diagnostics taxonomy a uniform, queryable failure ledger
   if it is not yet wired to every answer, source capture, SOP, worker, and
   method path;
2. add the AgentSkills lint/scanner concept as a BSC method/capability proposal
   gate, with scoped findings and reviewed suppressions;
3. audit every Horizon adapter for canonical URL/body-hash deduplication,
   explicit capture attempts, source policy, and heuristic/model provenance;
4. complete the Studio evidence-first UX with source capture failures, citation
   fragments, verification verdicts, proposal diffs, schedule outcomes, and
   mobile interaction tests all projected from durable records.

## 8. Verification ledger

| Check | Result |
| --- | --- |
| archive SHA-256 | matched the value recorded above |
| recursive archive inventory | 1,757 extracted files; source extension counts recorded in section 2 |
| Advisor-Orchestrator-Worker strict lint | passed with zero errors and warnings |
| Self-improving application lint as a skill | correctly failed: no root `SKILL.md`; it is an application, not a ready skill plug-in |
| DevPulse mock verification on default Windows terminal | failed before imports because GBK cannot print its emoji output |
| DevPulse mock verification with UTF-8 output | failed with `ModuleNotFoundError: agno`, disproving its no-external-dependency claim |
| product code modified by this audit | none |

## 9. Final decision

Do not import the repository or any of its application runtimes into BSC. Use
the verified patterns above as acceptance criteria for BSC's own governed
information, knowledge-growth, orchestration, MCP, and workspace capabilities.
The testable implementation target is not "look like an agent demo". It is a
single BSC system where every source, judgment, tool call, output, failure,
evaluation, publication, and rollback remains project-scoped, inspectable, and
truthful.
