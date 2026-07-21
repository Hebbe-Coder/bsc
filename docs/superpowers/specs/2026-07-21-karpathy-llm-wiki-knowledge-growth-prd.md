# BSC Karpathy LLM Wiki Knowledge Growth PRD

**Status:** Approved for implementation planning
**Date:** 2026-07-21
**Owner:** BSC product and platform
**Related:** `docs/superpowers/specs/2026-07-19-bsc-platform-convergence-design.md`, `docs/superpowers/specs/2026-07-21-grok-build-secondary-development-phase2.md`
**Reference pattern:** Andrej Karpathy's LLM Wiki concept and the Apache-2.0 `lucasastorian/llmwiki` implementation. This PRD adopts the pattern; it does not vendor or fork that project.

## 1. Product Definition

### 1.1 Vision

Turn scattered project evidence, Obsidian notes, Horizon intelligence, prior business outputs, and user corrections into a persistent, readable, project-specific knowledge system that improves over time.

The product follows the LLM Wiki model:

1. **Obsidian is the knowledge IDE.** People read, edit, link, import, and inspect the vault there.
2. **The LLM is the wiki maintainer.** It compiles sources into structured Markdown, maintains links and citations, identifies contradictions, and proposes useful new pages.
3. **BSC is the execution and verification platform.** It provides project isolation, source ingestion, scheduling, evidence checks, evaluation, MCP tools, business/SOP context construction, audit history, and visual operations.

This is not a conventional RAG upload feature. Raw documents remain available, but durable synthesis lives in an evolving Wiki so the model does not need to rediscover the same cross-document conclusions for every question.

### 1.2 Problem

The current BSC knowledge layer can ingest, hash, chunk, search, rerank, and retrieve project documents. It does not produce a human-readable, maintained synthesis. Important knowledge is therefore repeatedly re-derived at query time; output quality depends too heavily on generic prompts and templates; feedback is process-local; and users cannot inspect a durable causal trail from source to conclusion to SOP.

Horizon can broaden information capture, but it is an intelligence pipeline, not a project memory system. Its outputs need source policy, durable provenance, semantic synthesis, and quality gates before they affect BSC decision making.

### 1.3 Goals

- Build a project-scoped, Obsidian-compatible Markdown Wiki that compounds with each trusted source, useful question, accepted business outcome, and weekly distillation.
- Keep raw evidence immutable and attributable while allowing the generated Wiki layer to evolve, be versioned, and be reverted.
- Make PRD-to-SOP output depend on project evidence, constraints, decisions, and tested playbooks rather than generic content templates.
- Support trusted Horizon and user-curated inputs without allowing an LLM or feed to silently become a source of truth.
- Give users an operational knowledge workspace: vault navigation, rendered page, source/citation inspection, patch review, job timeline, health metrics, and a filterable relationship graph.
- Expose the same governed capability to compatible agents through MCP and HTTP/SSE APIs.

### 1.4 Non-goals

- Do not replace Obsidian, implement a generic cloud drive, or create a second hidden file format.
- Do not modify raw source content, fabricate citations, or auto-promote LLM prose merely because it was generated.
- Do not merge the Knowledge Graph into the existing Artifact Graph. Artifact Graph remains the business runtime's source of truth.
- Do not vendor LLM Wiki, Horizon, or an arbitrary shell/agent runtime into BSC.
- Do not claim scheduled cloud execution when Celery/Redis/Beat is disabled or unavailable.

## 2. Users And Core Outcomes

| User | Need | Outcome |
|---|---|---|
| Researcher / founder | Turn reading, clipping, and research into retained insight | Searchable, linked concepts and entities with source citations |
| Project lead | Maintain a living project memory | Decisions, constraints, SOPs, and changes survive chat sessions |
| Business consultant | Produce client-specific delivery material | SOP and reports grounded in the active project's evidence and decisions |
| Content creator | Distill an information stream into useful output | Weekly evidence-backed themes, claims, angles, and content briefs |
| Team reviewer | Verify why a recommendation changed | Page history, citations, source provenance, proposal diff, and run audit |
| MCP agent | Read and maintain knowledge under policy | Typed, project-scoped tools with deterministic failure modes |

## 3. Product Principles

1. **Evidence before synthesis.** Sources are immutable, identified by content hash, and remain independently readable.
2. **Readable state over opaque memory.** The durable synthesis is ordinary Markdown plus frontmatter, not an undocumented vector-store state.
3. **Project-specific rules over template repetition.** Each project owns an `AGENTS.md` that describes its taxonomy, required evidence, decision standards, SOP constraints, and content voice.
4. **Patch, validate, then publish.** The LLM proposes structured page operations. BSC validates and evaluates them before they become published Wiki state.
5. **Compaction beats accumulation.** Weekly distillation creates short, high-signal context artifacts. It does not append unlimited history to model context.
6. **Automate maintenance, not authority.** Trusted sources can enter the candidate flow automatically; publication still requires deterministic policy and quality gates.
7. **A graph is evidence navigation, not decoration.** Every rendered link must trace to pages, citations, sources, or proposal relationships.

## 4. Authority And Storage Model

### 4.1 Authority Matrix

| Layer | Authority | Mutation policy | Storage |
|---|---|---|---|
| Raw sources | Original evidence, user imports, feed captures | LLM/MCP read-only; user may replace through a new version | Obsidian project folder and source registry |
| Wiki | Compiled, human-readable project synthesis | User edits allowed; LLM writes only through governed proposals | Obsidian Markdown files |
| Project rules | Taxonomy and maintenance behavior | Versioned `AGENTS.md`; privileged user or approved proposal changes | Obsidian Markdown files |
| BSC knowledge database | Metadata, provenance, permissions, runs, proposals, evals, schedules | BSC services only | Existing knowledge repository database |
| Retrieval index | Search acceleration only | Fully rebuildable from source and Wiki | Existing keyword/TF-IDF/vector stores |
| Artifact Graph | Business runtime state | Existing runtime only | Existing ArtifactGraphStore |

### 4.2 Vault Layout

`OBSIDIAN_VAULT_ROOT` is configured by deployment. BSC stores a validated, canonical project-relative vault mapping; it never assumes a user's vault location or creates a separate global vault.

```text
<OBSIDIAN_VAULT_ROOT>/<configured-project-path>/
  AGENTS.md
  raw/                         # immutable source snapshots and imported files
  inbox/
    horizon/                   # accepted Horizon payloads awaiting processing
  wiki/
    overview.md                # project hub and current synthesis
    index.md                   # content-oriented page catalog
    log.md                     # append-only maintenance ledger
    concepts/
    entities/
    decisions/
    playbooks/
    content/
  distillations/
    2026-W30/
      knowledge-action.md
      content-creation.md
      context-pack.md
  .bsc/                        # generated metadata/cache; not a knowledge authority
```

The path resolver must reject traversal, symlink escapes, missing roots, and mappings outside `OBSIDIAN_VAULT_ROOT`. BSC-created files use atomic write/replace semantics. User-owned raw files are never moved or overwritten.

## 5. Domain Model

All records are project-scoped. IDs are opaque strings; timestamps use ISO-8601 UTC; payload snapshots are JSON objects; actor describes `user`, `system`, `mcp`, or named service.

| Entity | Responsibility | Required fields | Lifecycle |
|---|---|---|---|
| `SourceRecord` | Immutable source registry and ingestion state | `id`, `project_id`, `source_type`, `origin`, `vault_path`, `content_hash`, `trust_level`, `status`, `captured_at` | `captured -> validated -> eligible -> processed`; terminal `rejected` or `superseded` |
| `WikiPage` | Published Markdown page metadata | `id`, `project_id`, `path`, `title`, `page_kind`, `content_hash`, `version`, `published_at` | `published`, `archived`; new body is a new version |
| `WikiProposal` | Governed set of Wiki operations | `id`, `project_id`, `base_revision`, `operations`, `source_ids`, `rationale`, `status`, `eval_summary` | `draft -> validating -> approved -> published`; terminal `rejected`, `failed`, `superseded` |
| `CitationLink` | Source/page claim relationship | `id`, `project_id`, `wiki_page_id`, `source_id`, `anchor`, `claim_text`, `status` | active or stale after source/page change |
| `KnowledgeRun` | Auditable maintenance or query execution | `id`, `project_id`, `run_type`, `trigger`, `status`, `input_refs`, `output_refs`, `started_at` | queued/running/terminal, with retry metadata |
| `KnowledgeSchedule` | Persisted intended cadence and policy | `id`, `project_id`, `job_type`, `cron`, `enabled`, `last_run_at`, `next_run_at` | enabled, paused, disabled |
| `WeeklyDistillation` | Versioned weekly compacted output | `id`, `project_id`, `week`, `knowledge_path`, `content_path`, `context_path`, `source_cutoff` | generated, superseded, archived |

`WikiProposal.operations` is a typed list of `create`, `replace`, `append`, `archive`, or `move` operations. Each operation carries a normalized vault-relative target, expected base hash where applicable, body or patch content, and source references. Arbitrary filesystem commands are never a proposal operation.

## 6. Functional Requirements

### FR-1 Project Vault Configuration And Isolation

- A project administrator can configure one vault mapping under `OBSIDIAN_VAULT_ROOT`.
- All source, page, proposal, graph, schedule, MCP, and UI calls require `project_id` and enforce the existing project authorization model.
- Every project begins with a minimal generated `AGENTS.md`, `wiki/overview.md`, `wiki/index.md`, and `wiki/log.md`; user edits remain authoritative for their contents.
- BSC must not list or traverse another project's configured path, even if a caller supplies a valid-looking relative path.

### FR-2 Source Capture And Evidence Lifecycle

- The system detects imports and edits under the configured project path and idempotently records changed source hashes.
- Obsidian files, manual uploads, existing BSC documents, approved business artifacts, and Horizon signals are normalized into `SourceRecord` without deleting their original representation.
- Horizon is consumed through its documented HTTP/MCP stages or a deployable sidecar contract. BSC must not import the external repository's private modules.
- Trust policy combines source allowlist, source type, project relevance, duplicate detection, freshness, and user annotations. Trust makes a source eligible for synthesis; it never directly changes published Wiki pages.
- User highlights and notes are marked as curated opinion, not silently represented as factual source claims.

### FR-3 Project Rule File

`AGENTS.md` defines project-specific Wiki behavior: supported page kinds, naming convention, frontmatter fields, citation requirements, evidence hierarchy, contradiction policy, SOP constraints, content style, and maintenance prompts. It is passed to the compiler as structured context and is versioned like Wiki content.

### FR-4 Wiki Compilation

For a maintenance run, BSC selects unprocessed eligible sources, reads `AGENTS.md`, `overview.md`, `index.md`, affected pages, and bounded retrieved evidence. The LLM returns a `WikiProposal`, not direct database or filesystem mutation.

The compiler must:

- create or update only pages justified by evidence;
- add page frontmatter, links, citations, and log entries;
- identify source contradictions or uncertainty instead of resolving them by invention;
- update overview and index after any published material change;
- make valuable user queries, comparisons, analyses, and accepted business conclusions fileable as durable pages;
- keep prompt context bounded by the project context pack and selected evidence.

### FR-5 Proposal Validation And Publication

Before publication BSC validates path policy, base revision, frontmatter, source references, footnote format, local links, citation resolution, policy constraints, and graph consistency. It then runs project evals for retrieval, SOP groundedness, and content attribution.

Publication is automatic only when source policy permits it and all required gates pass. Failed proposals remain inspectable with errors; they cannot partly mutate published pages. Published revisions are reversible by creating a new proposal based on a previous snapshot.

### FR-6 Knowledge Graph And Health

The Knowledge Graph has typed edges: `wiki_links_to`, `wiki_cites_source`, `proposal_changes_page`, `source_supersedes_source`, and `decision_uses_evidence`. It is separate from Artifact Graph. Health calculations include citation coverage, dangling links, unresolved references, orphan pages, stale pages, uncited eligible sources, pending proposals, contradiction count, and evaluation trend.

### FR-7 PRD-To-SOP And Content Context

When BSC generates an SOP or content output, it assembles a traceable context pack from current project Wiki pages, sources, decisions, constraints, prior evaluations, and weekly distillation. Generic templates may supply layout only; business claims, controls, metrics, and process steps must carry source/page references or be flagged as assumptions.

Accepted high-quality outputs can become candidate Wiki sources. Low-quality outputs and user corrections become evidence for proposals/evals rather than being treated as truth.

### FR-8 Automation And Weekly Distillation

- Persist schedules for source synchronization, Horizon capture, maintenance, lint/eval, and weekly distillation.
- Use Celery Worker plus Celery Beat when real Celery/Redis is enabled. In synchronous/local mode, scheduled endpoints report `unavailable` and support explicit manual execution; they do not claim background completion.
- The weekly job writes `knowledge-action.md`, `content-creation.md`, and `context-pack.md` under a deterministic week folder. It includes source cutoff, linked evidence, changed beliefs, unresolved questions, actions, candidate content angles, and compact reusable context.
- Runs are idempotent per project/job/period/content cutoff and safe to retry.

### FR-9 MCP And HTTP/SSE Interface

BSC extends its existing MCP compatibility layer with project-scoped Wiki operations: `wiki_guide`, `wiki_search`, `wiki_read`, `wiki_propose_update`, `wiki_apply_update`, `wiki_lint`, `wiki_graph`, `wiki_distill`, and `wiki_schedule`. HTTP APIs expose equivalent typed operations for the web client. Existing `knowledge_ask`, transport initialization, and normal MCP content blocks remain backward compatible.

### FR-10 Knowledge Workspace

The existing `UnifiedWorkspace` gains a Knowledge view with:

- project/vault selector and expandable page tree;
- rendered Markdown with citation and backlink navigation;
- source inspector with immutable provenance and annotations;
- proposal diff, validation findings, publish/reject/retry status;
- live maintenance run timeline and scheduled job state;
- health trend charts and a filterable graph with real page/source/proposal nodes;
- weekly distillation browser and context-pack preview.

Desktop supports a stable three-pane workflow. Mobile uses a compact tab or drawer flow; no panel may overlap or hide the active action. Empty, loading, permission-denied, offline, failed, and no-vault states are first-class UI states.

## 7. Interfaces And Events

The implementation keeps existing `/knowledge` APIs stable and adds a dedicated workspace namespace. Exact routes and Pydantic/TypeScript shapes are frozen by the contracts plan.

| Interface group | Required operations |
|---|---|
| `/knowledge/workspaces` | configure/read project vault, initialize project Wiki, inspect sync state |
| `/knowledge/sources` | list, inspect, ingest, validate, reject, reprocess, source status |
| `/knowledge/wiki` | tree, page read, page history, proposal create/read/apply, lint, graph |
| `/knowledge/runs` | start, list, inspect, retry, stream events |
| `/knowledge/schedules` | create/update/pause/run-now and report scheduler availability |
| `/knowledge/distillations` | list, read, generate and retrieve context packs |

Event names are append-only, sequence-ordered within a run: `knowledge.source.captured`, `knowledge.source.eligible`, `knowledge.proposal.created`, `knowledge.validation.completed`, `knowledge.proposal.published`, `knowledge.proposal.failed`, `knowledge.lint.completed`, `knowledge.distillation.completed`, and `knowledge.run.failed`.

## 8. Quality, Security, And Observability

- All file access is canonicalized and constrained to the configured project root.
- Raw source bytes/text are never changed by LLM, lint, MCP, or scheduler code.
- Writes use expected hash/version checks and atomic replacement. A failed operation leaves the prior published Wiki intact.
- Each published statement is traceable to one or more `SourceRecord` entries or explicitly marked as an assumption.
- Automated evaluation must prove no regression against the affected project's baseline. Missing baseline is reported, not interpreted as a pass.
- Job records include trigger, actor, input source/page revisions, policy decision, task ID, output revisions, errors, and retry lineage.
- Logs and MCP outputs redact configured secrets and never expose raw credentials.
- Metrics include source throughput, proposal success rate, lint error count, citation coverage, stale/orphan count, evaluation deltas, job latency, retry count, and weekly distillation completion.

## 9. Acceptance Scenarios

1. A user maps a valid Obsidian project directory. BSC creates only the minimal Wiki scaffolding and cannot escape that directory.
2. A user imports a Markdown note and a Horizon signal arrives. Both become traceable sources; neither changes `wiki/` until the compiler proposal passes validation.
3. A maintenance run updates an entity and a concept, records citations, updates overview/index/log, and exposes all affected nodes in the Knowledge Graph.
4. A proposal with a broken citation, unresolved link, stale base hash, or failed eval is not published and surfaces an actionable failure state.
5. An approved change in project A cannot be retrieved, rendered, or modified through project B credentials or MCP calls.
6. A PRD submitted after knowledge growth produces an SOP whose core steps and controls cite project Wiki/evidence; unsupported statements are visible as assumptions.
7. A scheduled weekly run produces the three required files once per project/week/cutoff, survives a retry, and provides a verifiable source list.
8. The Knowledge view lets a user move from a graph edge to the page, claim citation, source, proposal diff, and run record without a fabricated UI-only data state.
9. With Celery disabled, the UI/API states that background scheduling is unavailable and a manual run completes through the normal auditable pipeline.
10. Existing compiler, Artifact Graph, `knowledge_ask`, MCP HTTP/SSE initialization, and live terminal regressions continue to pass.

## 10. Rollout And Feature Flags

The feature is project opt-in and defaults to disabled until a vault mapping and source policy exist. Feature flags independently gate vault sync, Horizon ingestion, automatic publication, Celery schedules, MCP write operations, and the web workspace. Rollout progresses from manual source/import and proposal review, to trusted-source automatic publication, then to scheduled maintenance after end-to-end verification.

## 11. Delivery Breakdown

Implementation is divided into eight dependency-aware plans under `docs/superpowers/plans/2026-07-21-knowledge-*.md`. Contracts, source capture, compiler, and quality gates are sequential foundations. Automation and API/MCP proceed in parallel after the gate contracts are frozen; visualization follows the API contract. Integration/release is the final gate. The companion index defines ownership boundaries and handoff requirements.
