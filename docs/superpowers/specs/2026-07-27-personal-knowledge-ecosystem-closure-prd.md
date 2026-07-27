# BSC Personal Knowledge Ecosystem And Growth Closure PRD

**Status:** Proposed implementation authority
**Date:** 2026-07-27
**Owner:** BSC product, knowledge platform, and Dynamic Business OS
**Audience:** Individual knowledge worker, project lead, business owner, and authorized AI agent
**Extends:**

- `docs/superpowers/specs/2026-07-21-karpathy-llm-wiki-knowledge-growth-prd.md`
- `docs/superpowers/specs/2026-07-27-knowledge-operations-visualization-prd.md`
- Project-level `AGENTS.md` in the mapped Obsidian Vault

## 1. Executive Decision

This PRD closes the gap between a technically available knowledge platform and a genuinely self-improving personal knowledge operating system.

The target is not a larger document repository, a recurring summary generator, or a generic content-template machine. The target is a governed learning system in which:

```text
trusted information -> immutable evidence -> useful synthesis -> reusable method
-> project-specific output -> observed outcome -> corrected future judgment
```

The product adopts the Karpathy-style A/B/C/D loop as its knowledge lifecycle:

| Layer | Meaning | Product obligation |
| --- | --- | --- |
| A | Unprocessed and immutable source material | Preserve origin, capture time, hash, rights, trust context, and project boundary. Never silently rewrite it. |
| B | Reviewed, generalized, readable knowledge | Convert evidence into citation-backed concepts, decisions, constraints, cases, and research notes that a human can read in Obsidian. |
| C | Reusable skills and methods | Extract only patterns with an applicability boundary, inputs, steps, exclusions, evidence, and an evaluation record. |
| D | Real output and observed work | Register deliverables, their context, use of methods, acceptance or correction, and the feedback route to A/B/C. |

Two loops operate together:

1. **Knowledge loop:** A -> B -> C -> D -> review -> A/B/C.
2. **Business loop:** business problem -> AI reasoning -> Artifact Graph -> execution -> evidence and outcome -> BSC memory and knowledge loop.

Neither loop is complete because a screen renders, an LLM response exists, or a scheduled job ran. Completion requires durable, project-scoped evidence that the output of one loop changed the next loop under a reviewable policy.

## 2. Product Vision And Success Definition

### 2.1 Vision

Obsidian is the human-facing knowledge IDE. BSC is the governed intelligence and operating layer. Horizon is an optional external-information radar. The LLM is a bounded maintainer, analyst, and proposal author, never an unreviewed source of truth.

The user should be able to move from a web clip, meeting note, Horizon signal, paper, screenshot, project PRD, or completed deliverable to an explainable chain of:

```text
source -> claim -> knowledge page -> method decision -> output -> feedback -> next action
```

The same chain must be visible to a project lead, usable by a permitted agent through MCP, and safe across projects and tenants.

### 2.2 Product Outcomes

The product is successful when it demonstrably produces all of the following:

- A researcher can tell which recent information is worth reading, what it changes, and what it contradicts.
- A project lead can create a PRD-to-SOP package grounded in the active project's constraints, decisions, evidence, and proven methods rather than a generic outline.
- A content creator can produce distinct angles and drafts with source lineage, audience intent, and an explicit feedback route.
- A business owner can see whether knowledge is becoming more verified, more reused, fresher, less duplicated, and less risky.
- An authorized agent can retrieve a minimal project context and explain the sources, method boundary, and uncertainty behind its recommendation.
- A poor outcome, user correction, failed method, or contradicted source makes a later proposal or SOP more conservative or more accurate.

### 2.3 Explicit Non-Successes

The following do not qualify as success:

- A folder scaffold with no real source material.
- A large number of generated summaries, weekly files, or vector chunks.
- A Skill file with no applicability, evaluation, or real reuse.
- A dashboard with invented value, confidence, accuracy, trend, or completion figures.
- A plugin shown as connected before it has actually exported a captured file.
- An LLM response presented as verified knowledge without evidence and a governed proposal path.

## 3. Users, Jobs, And Permissions

| User | Primary decision job | Required view | Authority boundary |
| --- | --- | --- | --- |
| Knowledge owner | Decide what to capture, keep, reject, and study | Inbox, source inspector, Wiki review, weekly distillation | Own project sources and approve governed proposals according to role |
| Project lead | Decide what work should change next | Project cockpit, Artifact Graph projection, risks, action queue | Only authorized project data and project outputs |
| Business owner / tenant admin | Decide where knowledge investment is producing value | Portfolio health, project comparison, risk debt, reuse | Tenant-scoped aggregate metadata; no raw source bodies by default |
| Content creator | Turn evidence into differentiated output | Context pack, verified pages, method boundary, output feedback | May create output drafts; cannot self-verify unsupported claims |
| Reviewer | Approve, reject, correct, or supersede knowledge | Proposal diff, citations, evaluation, contradiction queue | Cannot alter immutable raw evidence |
| AI agent | Answer, plan, retrieve, and propose under policy | Scoped MCP/API read model and explicit context package | No cross-project read; no direct raw mutation or silent publication |

Roles are tenant and project-scoped. A project key resolves to the tenant that owns the bound project. A tenant administrator may see authorized project aggregates; a project member or project key may never enumerate another project merely because its identifier is guessable.

## 4. Architecture And Authority Model

### 4.1 Four Complementary Planes

| Plane | Authority | Responsibilities | Must not become |
| --- | --- | --- | --- |
| Obsidian Vault | Human-readable working surface | Read, link, edit, import, inspect, and review Markdown assets | A hidden database substitute or an uncontrolled automation target |
| BSC knowledge database | Operational authority | Source metadata, immutable bodies, lifecycle, proposals, permissions, runs, evaluations, schedules, feedback, audit | A second hand-authored Wiki or a source-body leak through list APIs |
| Retrieval and graph projections | Rebuildable acceleration and navigation | Search, ranking, citation graph, lifecycle graph, dashboard projections | Independent truth that can diverge from records and pages |
| Dynamic Business OS / Artifact Graph | Business-runtime authority | Problems, reasoning, decisions, execution, risks, validations, memory | A replacement for the Wiki or a raw-source store |

Horizon is an external intelligence adapter. It may discover and enrich candidates, but BSC remains responsible for project isolation, source admission, evidence preservation, citation validation, publication, and outcome feedback.

### 4.2 Logical Layer Contract And Compatible Physical Paths

The product has exactly one **logical authority** for every layer. Existing folders remain compatible during migration, but a compatibility alias must never create a second writable truth.

| Logical layer | Canonical intent | Current compatible physical authority | Compatibility rule |
| --- | --- | --- | --- |
| A0 Intake | Unprocessed user or adapter arrivals | `00_Inbox/` and declared plugin drop folders | Files remain user-owned until captured; BSC only reads approved declared roots. |
| A1 Immutable sources | Admitted original evidence and provenance | Database `SourceRecord`; read-only Obsidian projection at `01_Sources/bsc-evidence/` | The database body/hash is authoritative. A projection is never recaptured as a new source. |
| B Knowledge | Reviewed human-readable synthesis | `wiki/` | `02_Assets/curated/` may contain links or views only until an explicit no-loss migration is approved. |
| C Methods / Skills | Reusable, evaluated operational knowledge | `methods/` | `06_Skills/` is an intake/candidate or navigation view, not a duplicate published store. |
| D Outputs | BSC-registered deliverables and their evidence | `outputs/` | `04_Outputs/` is an external producer drop zone. A registered managed copy belongs in `outputs/`. |
| Review | Corrections, failures, evaluations, and supersession | `reviews/`, audit records, evaluation records | `05_Archive/reviewed/` may retain historical user material but does not replace active review state. |
| Distillation | Time-bounded operating briefs | `distillations/每周蒸馏/` | A revision is a revision of a period, not a new knowledge asset count. |
| Attachments | Large binaries and imported media references | `attachments/` and declared attachment roots | Index metadata and links; do not embed or duplicate unbounded binaries in model context. |

All BSC-managed writes occur beneath the mapped project directory only. The system must reject traversal, symlink escape, project-root substitution, and any write to `.obsidian/` or user-owned source files.

### 4.3 Required Project Bootstrap

Creating or connecting a project must produce a reviewable project profile, not only folders. The profile includes:

- Project purpose, primary users, business domain, preferred output channels, confidentiality class, and active goals.
- Evidence hierarchy, trusted source classes, prohibited sources, freshness expectations, and citation standard.
- Taxonomy and page kinds declared in `AGENTS.md`.
- The directories and plugin bridge routes that BSC may read, plus their status: `unconfigured`, `verified_route`, `awaiting_export`, `captured`, `conflict`, or `disabled`.
- Method evaluation criteria, definition of successful output, and feedback vocabulary for the project.
- A context budget for automation and agent calls, with recency, relevance, trust, and diversity requirements.

## 5. Domain Model And Lifecycle Contracts

### 5.1 Core Records

| Record | Immutable / mutable responsibility | Minimum fields | Lifecycle |
| --- | --- | --- | --- |
| `SourceRecord` | Raw body and hash never change; lifecycle metadata is additive | `id`, `tenant_id`, `project_id`, `source_type`, `origin`, `captured_at`, `content_hash`, `raw_content`, `rights`, `trust_level`, `freshness`, `status` | `captured -> triaged -> admitted -> processed`; terminal `rejected`, `superseded`, `blocked` |
| `MediaAsset` | Immutable original binary or external media reference | `id`, `project_id`, `source_id`, `mime_type`, `byte_hash`, `byte_size`, `storage_ref`, `rights`, `access_state` | `registered -> available/missing/restricted -> archived` |
| `ExtractionArtifact` | Versioned, reviewable derivative of a source or media asset | `id`, `project_id`, `source_id`, `extractor`, `extractor_revision`, `kind`, `content_hash`, `status`, `error` | `queued -> running -> complete/partial/failed/unsupported` |
| `ReferenceLink` | Typed pointer from a claim/page/output to an exact evidence anchor | `id`, `project_id`, `target_type`, `target_id`, `source_id`, `anchor_type`, `anchor`, `relation`, `resolution_state` | `resolved`, `stale`, `broken`, `restricted` |
| `TableArtifact` | Structured table extracted from source or authored in a controlled view | `id`, `project_id`, `source_id`, `extraction_id`, `schema`, `row_count`, `unit_metadata`, `content_hash`, `status` | `detected -> reviewed -> published/retired` |
| `SourceAssessment` | A reviewer or policy assessment of a source; never overwrites raw source | provenance, authority, corroboration, freshness, extraction quality, rationale, actor | `draft -> accepted/rejected -> superseded` |
| `WikiPage` | Published B knowledge, revisioned and readable | path, title, kind, version, citations, assumptions, applicability, status | `draft -> proposed -> published -> archived` |
| `WikiProposal` | A typed patch set against a specific base revision | operations, source IDs, rationale, policy result, evaluation summary, actor | `draft -> validating -> review_required -> approved -> published`; terminal `rejected`, `failed`, `superseded` |
| `KnowledgeClaim` | A normalized statement linked to sources and pages | claim text, claim type, supporting and conflicting source IDs, confidence state | `proposed -> supported/disputed -> retired` |
| `MethodProposal` | Candidate C-layer method before publication | source/page/output links, trigger, inputs, steps, exclusions, expected result, evaluation plan | `candidate -> review_required -> eligible -> published`; terminal `rejected`, `retired` |
| `MethodRevision` | Versioned reusable method | semantic version, boundary, evidence, test cases, outcomes, deprecation reason | `active`, `paused`, `deprecated`, `superseded` |
| `OutputAsset` | A D-layer deliverable with immutable managed snapshot | type, channel, audience, prompt/context refs, method refs, source/page refs, content hash, status | `registered -> evaluated -> accepted/revised/rejected -> archived` |
| `OutputFeedback` | Outcome signal for an output; does not rewrite it | feedback type, evidence, actor, affected claims/methods, action | `pending -> processed -> failed` |
| `KnowledgeRun` | Auditable automation or agent execution | type, inputs, idempotency key, schedule ID, status, events, outputs, provider provenance | `queued -> running -> completed/failed/unavailable/cancelled` |
| `KnowledgeSchedule` | Persisted intent to run a bounded job | cron, timezone, job type, enabled flag, next run, retry policy | `enabled`, `paused`, `disabled` |
| `WeeklyDistillation` | Period summary and context artifact | period, input hash, source cutoff, paths, generation provenance, revision relation | `generated`, `reviewed`, `superseded` |

### 5.2 Lineage Requirements

Every transition must emit a durable project-scoped lineage relation. Required relations include:

```text
source_supports_claim
source_conflicts_claim
source_guides_page
page_guides_method
method_applied_to_output
output_receives_feedback
feedback_updates_claim
feedback_updates_method
artifact_informs_knowledge
knowledge_informs_artifact
```

The existing Artifact Graph and the knowledge graph stay physically separate. The lifecycle graph is a read-only projection that references stable IDs from both systems. Deleting or filtering a graph projection must never delete source, page, Artifact Graph, or feedback records.

## 6. End-To-End Operating Loops

### 6.1 A: Capture, Preserve, And Decide What Enters

Every intake route must identify its producer before it becomes a source:

| Route | Expected producer | Intake destination | Admission rule |
| --- | --- | --- | --- |
| Web clip | Obsidian Clipper or explicit importer | `00_Inbox/web-clipper/` | Capture the actual file, original URL, capture time, and content hash. |
| Social import | Declared social/Xiaohongshu adapter | `00_Inbox/social/` | Preserve post URL, author/source metadata, capture limitations, and media references. |
| Paper, report, Word, exported note | Docxer, Importer, manual import | `01_Sources/docxer/` or `01_Sources/importer/` | Preserve original file reference and extraction provenance. |
| Meeting material | User-approved meeting export | declared project source directory | Record meeting date, participants only when authorized, source rights, and unresolved claims. |
| Horizon | Horizon run-store or bounded sidecar export | BSC capture then `01_Sources/bsc-evidence/` projection | Treat as a lead until its original source and claim are admitted. |
| Manual note | User-authored Markdown or API capture | declared input root | Capture only after explicit project route validation. |
| Output return | Registered D output or external output bridge | `04_Outputs/` then managed `outputs/` | Never present an output as source evidence until its status and feedback are explicit. |

Capture must provide idempotent, project-local SHA-256 deduplication. Duplicate content increments provenance and arrival history; it does not multiply knowledge assets. A source can be rejected without deleting its immutable body, because rejection is evidence of a future policy decision.

### 6.2 Source Reliability And Information Intelligence

The source policy must distinguish **truth**, **lead**, **opinion**, **inference**, and **generated output**. It must never use a previous LLM summary as evidence for the same factual claim.

Each admitted source receives a reviewable assessment with these dimensions:

| Dimension | Meaning | Required behavior |
| --- | --- | --- |
| Provenance | Is the original origin identifiable and preserved? | Missing origin limits source use to discovery or explicitly marked uncertainty. |
| Authority | Does the source have domain authority for the claim type? | Official primary material outranks commentary for factual and policy claims. |
| Corroboration | Do independent sources agree or conflict? | Conflict creates a review item, never silent averaging. |
| Freshness | Is the source appropriate for the decision window? | Stale sources remain searchable but are flagged in current decisions. |
| Extraction quality | Did an importer preserve enough content and structure? | Truncated, unreadable, or malformed captures cannot support strong claims. |
| Rights and sensitivity | Is use, retention, and model processing permitted? | Restricted content is redacted, excluded, or routed to approved local processing. |

Horizon must provide source diversity, filtering, enrichment provenance, item scores, and a run identifier. BSC imports only bounded `filtered` or `enriched` outputs, keeps original URL and run provenance, and applies the same admission policy as any other route. A successful Horizon HTTP request alone is not a successful knowledge capture.

### 6.3 B: Compile Evidence Into Living Knowledge

The Wiki maintainer may propose, but not directly publish, changes. A proposal must:

- Name the question, decision, or change that caused the synthesis.
- Cite one or more immutable source IDs next to supported claims.
- State whether each statement is fact, synthesis, recommendation, assumption, or open question.
- Include applicability, exclusions, freshness limitation, and a next validation task when material.
- Surface disagreement rather than remove conflicting evidence.
- Change only the paths and page kinds allowed by the project `AGENTS.md`.
- Be evaluated against the active page revision, citations, graph integrity, project permissions, and project quality baseline before publication.

Publishing a Wiki page creates a page revision, citation records, graph edges, retrieval-index invalidation, and audit events. A user edit or stale proposal cannot be overwritten. Rollback is a new auditable proposal to a prior revision, never a hidden file replacement.

### 6.4 C: Evolve Methods And Skills From Evidence And Work

A method is not a note with imperative language. It is eligible for C only when it has all of:

- A named trigger and a bounded problem type.
- Known inputs, required evidence, expected output, and decision points.
- A step sequence, exception path, and explicit "do not use when" exclusions.
- Source or page evidence plus at least one example, counterexample, or failure mode.
- A measurable evaluation criterion appropriate to the method's purpose.
- A versioned owner and a route for future correction or deprecation.

The system may create method candidates from B pages, repeated D outcomes, reviews, and source extraction. It must not bulk-publish generic templates. A candidate reaches `published` only after evaluation and review policy pass. A method used in a PRD-to-SOP or content job records `method_applied_to_output`; later feedback updates its reuse, acceptance, correction, and retirement metrics.

### 6.5 D: Register Outputs And Return Reality To Knowledge

An output is a real deliverable, such as a decision brief, PRD, SOP, report, article, script, deck, research memo, workflow, or content asset. It is useful to the loop only after BSC records:

- The project, audience, intended decision or outcome, channel, and owner/agent boundary.
- The immutable managed snapshot or a verified external-file reference.
- The context pack revision, source/page citations, applied methods, assumptions, and unresolved risks.
- Evaluation results, user feedback, observed acceptance, correction, rejection, reuse, or business outcome.
- The return action: update a claim, page, method, source policy, or open a review item.

An accepted output can inform voice, method, and business context. It cannot become factual evidence by itself. A rejected or corrected output is high-value negative evidence and must remain inspectable in the review history.

### 6.6 PRD-To-Custom SOP And Content Creation

Every generation request must first construct a **project context package** containing:

```text
requested outcome + audience + operating context + project constraints
+ active decisions + relevant verified pages + appropriate methods
+ recent sources + risk/contradiction state + prior output feedback
+ required validation + open questions
```

The generator may reuse a method only after matching its applicability and exclusions to the current context. It must return a structured output contract:

- Why this evidence and method were selected.
- Which assumptions remain unverified.
- Which requirements could not be grounded and therefore require user input or research.
- The task-specific validation route and feedback capture point.

When the context package is insufficient, the correct product outcome is a bounded research or clarification action, not a confident generic SOP.

### 6.7 Review And Learning

The review queue is the intelligence engine of the system. It contains:

- Untriaged or low-confidence sources.
- Contradictory claims and stale high-impact pages.
- Pending Wiki and method proposals.
- Outputs without feedback, outputs with corrections, and failed methods.
- Horizon signals needing primary-source confirmation.
- Overdue validations, duplicate clusters, and orphaned pages/methods/outputs.

Every review action must identify the affected record, rationale, actor, timestamp, and next state. Review completion is not a checkbox: it must result in an accepted/rejected/superseded record or a deferred action with a due condition.

## 7. Functional Requirements

### FR-1 Project Profiles, Vault Mapping, And Lifecycle Compatibility

- BSC must maintain one validated Vault mapping per project and reject paths outside the configured Vault root.
- The workspace must display both logical A/B/C/D layers and their authoritative physical locations, including temporary compatibility aliases.
- A migration may add indexes, projections, or aliases first; it may not move, overwrite, or recapture user files without an explicit reviewed migration record.
- The product must expose a "path divergence" health item while logical and physical folder contracts remain split.

### FR-2 Multi-Route Intake And Plugin Bridges

- Each bridge declares adapter type, project-relative read roots, producer role, allowed extensions, provenance metadata, and output classification.
- BSC may inspect declared exported files but must not execute, inspect, or modify third-party Obsidian plugin code in `.obsidian/`.
- A bridge reports `verified_route` only after path/trust validation and `captured` only after a real immutable source is persisted.
- External output bridges similarly report `awaiting_output` until a real output is registered and evaluated.

### FR-3 Source Triage, Trust, And Retention

- Triage determines relevance, evidence class, source rights, sensitivity, freshness, deduplication, and an explicit admission decision.
- High-impact factual claims require primary material or independently corroborated sources according to project rules.
- Low-trust or incomplete signals may create research tasks but cannot directly create verified Wiki claims, methods, or SOP requirements.
- Retention and deletion requests must preserve an audit-safe tombstone or policy record without exposing removed raw content.

### FR-4 Horizon Intelligence Integration

- Horizon runs are visible as bounded source batches with run ID, query/topic configuration reference, stages, item counts, failure state, and last successful capture time.
- Every imported item retains URL, source metadata, Horizon score, stage, and run lineage.
- The system displays source diversity and source-type mix; it does not equate a high Horizon score with factual correctness.
- Horizon failures retry under a declared policy and remain visible as failed/unavailable runs. No blank success state is permitted.

### FR-5 Wiki Compiler, Claims, And Contradictions

- The compiler produces typed patch proposals, never direct unrestricted Markdown writes.
- Claim-level citation validation and contradiction detection run before a proposal can publish.
- Pages declare a status such as `draft`, `supported`, `needs_review`, `disputed`, or `archived`; a status is not inferred from text sentiment.
- A page becomes stale when its high-impact supporting sources exceed policy freshness, an output correction conflicts with it, or a related Artifact Graph validation fails.

### FR-6 Method And Skill Ecosystem

- The Skill library supports discover, inspect, compare revisions, simulate applicability, propose, evaluate, publish, pause, and retire operations.
- Every method exposes trigger, required inputs, expected outcome, exclusions, dependencies, evidence, tests, and known failure patterns.
- The routing layer returns an explanation when it recommends or rejects a method for a task.
- Skill marketplace-style discovery, if introduced, remains project-scoped by default and imports only signed/approved packages with declared trust and license metadata.

### FR-7 Output Registry And Feedback

- Outputs can originate from BSC, approved external Obsidian drops, MCP clients, or user registration.
- The registry deduplicates immutable snapshots, preserves origin, and links output to methods/context/artifacts without exposing prompt secrets.
- Feedback accepts at minimum `accepted`, `rejected`, `corrected`, `reused`, `measured_success`, and `measured_failure`.
- Feedback processing opens deterministic updates or review actions; it never silently changes a page or method.

### FR-8 Automation And Scheduled Distillation

The persistent schedule model supports these project jobs, each with idempotency, retry state, run event ledger, and truthful unavailable behavior:

| Job | Default cadence | Purpose | Required output |
| --- | --- | --- | --- |
| Source sync | Every five minutes | Capture declared local exports and register eligible external outputs | Source/output counts, duplicate/conflict report, no fabricated import |
| Horizon capture | Daily 08:00 Asia/Shanghai | Import new filtered/enriched runs when configured | Run provenance, selected items, failures, and triage queue |
| Daily growth | Daily 17:00 Asia/Shanghai | Identify meaningful source/page/output changes | One bounded change brief or an explicit no-material-delta result |
| Wiki maintenance | Daily 17:15 Asia/Shanghai | Build reviewable, citation-backed Wiki proposals | Proposal IDs or a cited insufficiency report |
| Weekly distillation | Friday 17:30 Asia/Shanghai | Produce an operating summary, action queue, content briefs, next context, and method iteration review | Versioned five-document bundle with input hash and source cutoff |

Distillation must be semantic-delta aware. It may create a new revision only when the source/page/output/feedback set materially changes or an approved review decision requires it. Repeated scheduler execution with the same input hash returns a no-op. Dashboard counts show periods and revisions separately.

### FR-9 API, SSE, And MCP Ecosystem

- REST and SSE expose project-scoped source, page, proposal, method, output, feedback, schedule, run, graph, and operations read models.
- MCP tools expose the same policy-bounded capabilities for agents, including context-pack retrieval and proposal creation when authorized.
- APIs return `unavailable`, `no_sample`, `forbidden`, `not_found`, `stale`, and `partial` states explicitly. They do not replace an empty dataset with demo metrics.
- Raw source bodies, provider credentials, prompts, and provider payloads are excluded from broad list, dashboard, and portfolio responses.

### FR-10 Knowledge Workspace And Obsidian Interoperability

The knowledge workspace provides:

- A layer-aware Vault tree that labels user-owned, BSC-managed, pending, conflict, and compatibility paths.
- Source inspector with origin, hash, trust, lifecycle, capture path, related claims, and redacted content access according to permissions.
- Rendered Wiki reader, page history, citation side panel, proposal Diff, lint/evaluation result, and publish/rollback actions.
- Method library with applicability test, evidence and evaluation detail, revision comparison, reuse history, and retirement reasons.
- Output registry with context/source/method lineage, acceptance state, feedback entry, and route back to review.
- Run console with scheduler, retry, timing, provider provenance, event timeline, and truthful unavailable/failed states.

### FR-11 Knowledge Operations Cockpit

The existing `UnifiedWorkspace` must expose a role-appropriate operations surface without conflating it with an engineering console.

Portfolio view for an authorized tenant administrator:

- Project health comparison, freshness, verified/unverified asset mix, risk debt, pending review, and method reuse.
- No project enumeration outside tenant authorization.
- Clear no-sample and insufficient-data states.

Project view for an authorized project user:

- Today's operating changes, highest-priority action, source reliability, Wiki health, method health, output feedback, and runtime status.
- One-click drill-down from a metric or action to the exact persisted source, page, proposal, method, output, review, run, or Artifact Graph record.
- Read-only lifecycle projection that joins the knowledge and Artifact Graph identifiers without merging their storage.

### FR-12 Data Visualization And Decision Experience

Visualizations serve a decision. They must not use decorative charts, synthetic trends, or unreadable force-directed graphs.

| View | Decision answered | Required real measures | Interaction |
| --- | --- | --- | --- |
| Knowledge health | Is the asset base trustworthy and usable? | admitted sources, supported/disputed pages, stale pages, pending proposals, orphaned nodes | Filter by project, time, source type, confidence/status; drill to exact record |
| Growth funnel | Is information becoming reusable operating knowledge? | A admitted -> B published -> C evaluated -> D accepted/reviewed counts and conversion denominators | Show zero/no-sample when denominator is absent; select a stage to list records |
| Source reliability matrix | Which sources need attention? | provenance, authority, freshness, corroboration, use count, conflict count | Sort by decision impact and freshness debt; open source/citation inspector |
| Method effectiveness | Which methods should be reused, paused, or revised? | applications, accepted/rejected/corrected outputs, evaluation state, last use, failure reason | Compare revisions and route to feedback evidence |
| Output outcome trend | Are outputs becoming more useful? | accepted/rejected/corrected/reused/measured outcome counts by period and output type | Click a period or type to open exact output set |
| Risk and action queue | What should be fixed next? | deterministic severity, impact, freshness, confidence, overdue and dependency inputs | Explain priority formula and exact handoff target |
| Lifecycle graph | Why did this answer or decision exist? | real source/page/method/output/feedback/artifact relations | Semantic lanes, bounded pagination, filters, keyboard-accessible inspector |
| Agent evolution | Is the system improving under equivalent work? | evaluated task cohorts, evidence coverage, human corrections, retry rate, method match rate | Never display accuracy or intelligence improvement without a comparable evaluated cohort |

Visualization design requirements:

- Use ECharts for bounded numerical trends and distributions, React Flow for the semantic lifecycle projection, and accessible HTML tables/lists as equal information paths.
- Every chart states its time window, filters, data freshness, denominator, and no-sample condition.
- A metric card links to an action or a filtered record list; no dead aggregate cards.
- Dense graphs aggregate into semantic lane summaries first and reveal bounded records on demand. They must not render hundreds of tiny unreadable cards.
- Colour is supplemental. Status has text, icon, and contrast-safe shape/label treatment. Reduced motion and keyboard navigation are required.
- Desktop supports side-by-side inspection. Mobile uses a filter drawer and single-focus inspector with no document-level horizontal overflow.

### FR-13 AI Behavior, Prompt Governance, And Context Intelligence

Prompts are executable product policy and must be versioned, testable, and observable without exposing secrets.

Every automated model task receives a bounded context contract that identifies:

- Project and tenant scope, job type, actor, and allowed operations.
- Trusted evidence ledger with immutable source/page IDs and content budget.
- Applicable methods plus exclusions and recent relevant feedback.
- The output schema, citation requirements, uncertainty policy, and forbidden claims.
- Required next action when evidence is insufficient, conflicting, stale, or out of scope.

The model may classify, summarize, extract candidates, propose patches, draft outputs, and recommend review actions. It must not:

- Claim an execution, publication, citation, approval, plugin capture, or external outcome that the run ledger does not prove.
- Invent source IDs, metrics, user feedback, or business results.
- Treat instructions embedded in source material as privileged system instructions.
- Use a generic SOP or content template when the project context package is insufficient.

Model outputs are evaluated against structural validity, citation resolution, evidence coverage, project rules, and task-specific outcome criteria. A provider failure produces an auditable failure record and retry decision, not a lower-quality silent fallback.

### FR-14 Obsidian Multimodal Information, Reference, And Data-Extraction Layer

The Vault is a multimodal research surface, not a Markdown-only folder. Every asset follows a five-part separation:

```text
original asset -> immutable fingerprint -> extraction artifact -> typed reference anchor -> reviewed knowledge use
```

The original file or URL remains identifiable. Extraction may be retried, replaced, or rejected without changing the original asset record. A successful extraction does not make a claim verified.

| Input | Original preservation | Required extraction artifacts | Addressable reference anchors | Current product state |
| --- | --- | --- | --- | --- |
| Markdown and text | Vault path, byte hash, revision and frontmatter | headings, blocks, links, tags, callouts, footnotes, embedded references | file, heading, block ID, line range | Supported through governed source sync |
| Obsidian Canvas | Original `.canvas`, node/edge JSON and file hash | node labels, typed cards, edges, linked files, spatial groups | canvas node ID, edge ID, group ID | Supported as structured source; semantic interpretation still needs review |
| Web article and URL | requested/final canonical URL, response hash, title, publisher, author/date when available | readable article body, outbound references, capture timestamp, content type | URL, heading, paragraph/block, quote | Primary web capture is supported; URL health and richer article parsing remain required |
| PDF and document | Original file reference, byte hash, page count, rights and access state | page text, blocks, tables, figures, annotations, extraction quality | page, block, table cell, figure region | Current Vault sync retains/rejects unsupported binary provenance; full extraction is required |
| Image and screenshot | Original image file, byte hash, MIME type, dimensions, rights | OCR text, caption, visual entities, diagram regions, OCR confidence | image, named region, bounding box, caption | Attachment metadata exists; OCR/vision pipeline is required |
| Spreadsheet and CSV | Original workbook/file hash and sheet identity | sheet schema, typed columns, units, formulas/values where permitted, sampled rows | sheet, table, row, column, cell | Structured table extraction and reviewed publishing are required |
| Audio and video | Original media reference, byte hash, duration, rights | transcript, timestamped segments, speaker labels only with permission, key frames | media timestamp, transcript segment, key frame | Not yet implemented; must remain unavailable rather than be represented as text knowledge |
| Zotero item | Citation key, library/item identity, DOI/URL, attachment references | bibliographic metadata, abstract, notes, tags, PDF extraction references | citekey, item key, DOI, page/annotation | Plugin configuration and controlled import are required |
| Excalidraw | Original `.excalidraw.md`/drawing data and embedded asset refs | element IDs, text, links, frame/group boundaries, export revision | element ID, frame, linked asset | Plugin is installed; BSC adapter and review rules are required |

#### 14.1 Extraction Contract

Each extraction artifact records the extractor name and revision, source/media hash, start/finish time, status, confidence when meaningful, and a bounded error category. Extraction statuses are `queued`, `running`, `complete`, `partial`, `failed`, `unsupported`, `restricted`, and `needs_review`.

- `unsupported` means the original is retained but contributes no textual or factual content.
- `partial` means the UI identifies the missing pages, regions, sheets, timestamps, or fields. It must not silently appear as complete.
- OCR and vision outputs are hypotheses. They cannot support a factual claim unless a reviewer accepts them or a corroborated source supports the claim.
- Table extraction preserves headers, units, data types, empty cells, formulas or formula-redaction state, sheet/page origin, and row/column coordinates. It never rounds, aggregates, or converts units without an explicit derived artifact.
- PDF and image extraction must preserve page/region anchors so a reader can inspect the source rather than trust a detached summary.
- Binary parsing, OCR, media decoding, and web capture run in bounded workers with file-size, MIME, time, and anti-malware policy limits. Untrusted attachments never execute embedded macros, scripts, or source instructions.

#### 14.2 Reference And Citation Contract

Every page, method, output, chart, table, or agent answer uses typed references instead of bare URLs. The following display forms map to durable `ReferenceLink` records:

```text
[source:<source-id>]                         source-level provenance
[source:<source-id>#heading=<slug>]          Markdown or HTML section
[source:<source-id>#page=<n>]                PDF/document page
[table:<table-id>#row=<n>&column=<field>]    structured table cell or range
[asset:<asset-id>#region=<region-id>]        image, figure, or diagram region
[media:<asset-id>#t=<seconds>]                audio/video timestamp
[zotero:<citekey>]                           bibliography item
[url:<reference-id>]                         captured external URL
```

The renderer resolves each reference according to permission. It shows title, origin, capture/published time, trust/review state, preview, and an exact Open-in-Obsidian or inspect action. Broken URLs, missing files, expired access, and superseded source revisions are visible as `stale`, `broken`, `restricted`, or `superseded`; they do not silently remain green citations.

Reference articles, papers, websites, DOI links, social posts, and web captures form a source network. The system must retain the original URL and its canonical/final URL separately, reject credentials in URLs, store capture time, and make tracking-parameter normalization reversible through provenance. URL recrawl is opt-in, rate-limited, project-scoped, and never follows private-network targets or attempts to bypass paywalls, login walls, or robots policy.

#### 14.3 Obsidian-Native Views Without a Second Source of Truth

Obsidian remains immediately useful even when BSC is offline. BSC may create governed, read-only index or view notes under the mapped project root; it must not edit `.obsidian/` plugin code or user-authored source notes.

- **Dataview:** Generated project index notes use frontmatter compatible with Dataview queries for Inbox, source review, Wiki status, methods, outputs, and review debt. Queries are read-only Markdown views; BSC database records remain authoritative for lifecycle and permissions.
- **Metadata Menu:** The project schema defines controlled fields such as `bsc_id`, `project_id`, `asset_kind`, `source_url`, `citation_key`, `trust_level`, `review_status`, `freshness`, `related_sources`, `related_pages`, `method_refs`, `output_refs`, `table_refs`, and `image_refs`. Fields are validated before BSC capture; free text never overwrites immutable provenance.
- **Obsidian Bases:** Native Bases may present local filtered lists and simple tables from the same frontmatter. It is a local view, not a security boundary or aggregation engine.
- **Excalidraw and Canvas:** Visual maps link to stable source/page/method/output IDs. BSC may generate a projection or index, but it never treats an unreviewed drawing label as verified factual evidence.
- **Zotero Integration and Zotero Notes Sync:** Bibliography keys, DOI, author, publication date, abstract, note links, and attachment identifiers are captured as provenance. PDF body extraction stays subject to the same rights, page-anchor, and review policy.
- **Local REST API:** It is optional and disabled as an authority path until configured for loopback-only access, an explicit token, narrow operations, and BSC-side redaction tests. Filesystem capture remains the compatibility baseline.

#### 14.4 Multimodal Visual Exploration

The BSC workspace and Obsidian view notes must give different users equal access to evidence:

| View | User question | Required presentation and drill-down |
| --- | --- | --- |
| Evidence atlas | What source material exists and what has not been understood? | Filterable cards/list by type, origin, project, trust, freshness, extraction state, and review state; thumbnail only when authorized; open original and extraction side by side. |
| Reference browser | Why should I trust this statement? | Citation chain from page/claim/output to exact URL, paper, page, table cell, image region, or timestamp; show conflicting and superseded evidence. |
| Table explorer | What does the source data actually show? | Virtualized sortable table preview, schema, units, missing values, source sheet/page anchors, derived-versus-original label, and export-safe filtered view. |
| Image and figure inspector | What does this screenshot, chart, or diagram support? | Original media preview, OCR/caption/regions, reviewer state, linked claims, and explicit warning that visual extraction is not fact approval. |
| Research timeline | What changed and when was it known? | Published date, capture date, source revision, review date, page/method/output use, and freshness debt. |
| Reference network | Which articles, websites, concepts, methods, and outputs depend on each other? | Typed graph lanes, relation filters, node aggregation, source diversity counts, and one-record inspector. |
| Obsidian workspace map | Where does a project asset live? | Logical A/B/C/D layer, physical path, ownership, managed/user status, compatibility alias, and capture/write policy. |

Charts that use extracted tables must cite the table artifact and exact applied transformation. Charts must show source period, units, row count, filters, missing-data treatment, and whether a value is original or derived. A dashboard cannot turn OCR text, raw spreadsheet values, or an unreviewed visual label into a business conclusion.

## 8. Metrics And Data Semantics

### 8.1 Primary Measures

| Metric | Formula / source | Interpretation guard |
| --- | --- | --- |
| Admitted source growth | New `SourceRecord` records admitted in period, deduplicated by content hash | Do not count captures, duplicates, or projections as new knowledge. |
| Knowledge coverage | Supported pages / pages requiring evidence | Display `no_sample` where no relevant pages exist. |
| Evidence coverage | Claims with resolvable support / claims that require support | Do not call a citation link support if the source is missing or cross-project. |
| Freshness debt | Weighted stale high-impact pages, methods, and sources | Freshness policy is project-specific; old research is not automatically bad. |
| Method reuse | Distinct accepted/reviewed outputs linked to a published method | A method file without an application has zero reuse. |
| Method effectiveness | Evaluated accepted outcomes divided by evaluated outcomes for comparable method applications | Do not infer effectiveness from generation count or raw thumbs-up. |
| Output feedback coverage | Outputs with typed feedback / eligible outputs | A missing review is missing data, not acceptance. |
| Review debt | Pending, disputed, stale, or failed items weighted by impact and age | The action queue must expose individual contributors. |
| Distillation novelty | New admitted evidence, changed supported claims, feedback, or decisions in period | Revisions alone do not increase novelty. |
| Agent evolution | Cohort-based change in evaluated evidence coverage, correction rate, route selection, or cycle time | No "accuracy" trend without a stable comparable evaluation cohort. |
| Extraction coverage | Assets with complete or accepted partial extraction / eligible supported asset types | Unsupported/restricted assets remain visible and are excluded from the denominator only with a stated reason. |
| Reference resolution | Resolved typed references / references that must resolve | A bare URL, missing file, or page-less PDF citation is not a resolved reference. |
| Multimodal review coverage | Image/table/media extraction artifacts reviewed or corroborated / artifacts used in claims | High OCR confidence alone is not a review. |
| Source diversity | Distinct authoritative domains/source classes supporting a decision | Duplicate mirrors and reposts do not increase diversity. |

### 8.2 Anti-Metrics

The dashboard must not use the following as evidence of value without a linked outcome:

- Number of tokens, chunks, embeddings, generated pages, or prompts.
- Number of scheduled jobs that merely ran.
- Number of Skill files or output files.
- LLM self-reported confidence.
- Generic "knowledge score" with no decomposable formula and action path.

## 9. Quality, Security, And Operational Requirements

### 9.1 Correctness And Safety

- Raw source content is immutable after capture. Re-import or update creates a new source or supersession relation.
- Every database query, file mapping, graph edge, run, API, SSE event, and MCP tool is tenant and project scoped.
- All automated writes use staged, atomic writes and preserve user edits through hash/conflict detection.
- Publishing requires a valid base revision, project authorization, path policy, citation check, evaluation gate, and durable audit event.
- Output feedback and method evaluation are additive. They cannot erase a bad result to improve a metric.
- Secrets are accepted through runtime configuration only, redacted from logs and APIs, and never copied into Vault files, prompts, or generated reports.

### 9.2 Reliability And Recovery

- Every recurring job has an idempotency key based on project, job, schedule/due time, and input cutoff when applicable.
- Worker duplicate delivery permits one active executor per run; later deliveries return the durable state.
- Transient provider, Horizon, broker, filesystem, and database failures record category, retryability, and recovery instructions.
- Scheduler status reflects actual broker/worker availability at the documented freshness, while execution submission performs its own readiness check.
- The API must retain compatible read behavior when optional Horizon, provider, Vault, or scheduler dependencies are unavailable.

### 9.3 Performance Budgets

| Surface | Target |
| --- | --- |
| Project operations summary after warm cache | p95 under 300 ms for bounded authorized data |
| Workspace list/graph queries | Server-side bounded pagination; never transfer raw bodies for visual rendering |
| Source sync | Hash and deduplicate incrementally; no full Vault rewrite |
| Distillation | Deterministic no-op for unchanged input hash; preserve prior revision when changed |
| Lifecycle graph | Render semantic lanes first; load detailed nodes only under explicit bounded filters |
| Mobile workspace | No document-level horizontal overflow at 390 px width; functional filters and inspector |

## 10. Acceptance Criteria And Proof Obligations

The feature is not complete until all applicable proof obligations below are met using real runtime records or isolated deterministic tests. A fixture proves software behavior; it does not prove that the user's knowledge operation is producing value.

### 10.1 Engineering Closure

- Docker Compose API, PostgreSQL, Redis, Worker, and Beat are healthy and execute a persisted knowledge run through the event ledger.
- A project-key request for a non-default tenant resolves to its durable tenant and cannot access other projects.
- Source capture, proposal lint/evaluation/publication, method evaluation, output registration, feedback routing, retry, and rollback paths have focused regression coverage.
- HTTP, SSE, and MCP tools expose identical scope and redaction semantics.
- TypeScript check, frontend tests, production build, targeted lint, and `git diff --check` pass for changed work.

### 10.2 Real A/B/C/D Closure

1. A user-created external clip, import, meeting record, or Horizon batch appears in a declared route and is captured as immutable project evidence with real provenance.
2. The source passes or fails triage visibly. A duplicate and a low-trust lead produce the expected non-inflated or review-required outcome.
3. A citation-backed Wiki proposal is reviewed and published, while a conflicting source creates a visible review record rather than an overwritten claim.
4. A method candidate with trigger, exclusions, evidence, evaluation plan, and failure boundary is reviewed. At least one method is applied to a real output and its use is recorded.
5. A real output receives acceptance, correction, rejection, reuse, or measured outcome feedback. The feedback creates a specific page/method/review update action and the action is completed or explicitly deferred.
6. A weekly run with material new evidence creates a five-part evidence-backed bundle. Re-running unchanged inputs yields a no-op. A new revision is explainably linked to the changed source, page, output, or feedback.
7. The lifecycle graph traces the exact selected output to its applied method, supporting page, immutable source, feedback, and related Artifact Graph record where applicable.
8. A Markdown note, captured web article, PDF, image, spreadsheet, Canvas/Excalidraw drawing, and Zotero item each retain immutable original provenance. Unsupported formats truthfully show their limitation rather than fabricated extracted text.
9. A PDF page, table cell, image region, external URL, and Zotero item each resolve from a BSC page or output citation to an authorized inspector. A deliberately missing or changed reference visibly becomes stale/broken.
10. An extracted table is rendered with source units, sheet/page/cell anchors, missing-data treatment, and derived-data labels. A visual chart links back to its exact table artifact and transformation record.
11. A Dataview index and Obsidian Base display the project's captured sources, pending review, published knowledge, methods, outputs, and feedback status from declared properties without creating a second writable lifecycle authority.
12. Local REST API access is loopback-scoped and token-protected before any optional BSC integration; unauthorized and cross-project requests fail closed.

### 10.3 Visual And Product Closure

- The portfolio and project cockpit use actual authorized data, show data freshness and no-sample states, and provide exact drill-down for every action.
- ECharts panels and React Flow projection render nonblank at desktop and 390x844 mobile sizes. Keyboard navigation, screen-reader labels, reduced-motion handling, and no-horizontal-overflow are verified.
- A user can identify why a metric changed, what action is recommended, which evidence supports it, and what would change its status without reading raw database JSON.
- The system distinguishes `verified route`, `captured source`, `published knowledge`, `published method`, `registered output`, and `feedback processed`; no UI phrase conflates these states.

### 10.4 User Knowledge-Operation Closure

The personal system is considered operational only after at least three consecutive review cycles with new user-origin or approved external material demonstrate:

- Sources arrive through declared routes without manual database intervention.
- At least one source is rejected, one is retained as a lead, and one becomes citation-backed knowledge.
- At least one method is reused or explicitly found inapplicable with recorded reasoning.
- At least one output's feedback changes a later page, method, context package, or review priority.
- The owner can explain the top current knowledge risk and the next recommended action from the cockpit.

## 11. Rollout, Migration, And Ecosystem Evolution

### 11.1 Rollout Sequence

1. Freeze and document the logical-to-physical directory contract; show compatibility alias health without moving user data.
2. Close source intake truthfulness for each installed plugin and Horizon adapter using actual exported files or unavailable states.
3. Enforce evidence, claims, proposal, and contradiction gates for B knowledge.
4. Make C method proposals depend on evidence and real D output lineage rather than bulk templates.
5. Require D feedback before reporting method value or agent improvement.
6. Enable the operations dashboard only against the authoritative read model and prove browser behavior with real bounded data.
7. After observed stable data semantics, export optional organization analytics to Metabase or Superset. BI is a consumer of the read model, not a substitute for project operations or permission gates.

### 11.2 Migration Rules

- No migration deletes or moves user-owned Vault files automatically.
- Existing `wiki/`, `methods/`, `outputs/`, `reviews/`, and `distillations/` contracts remain authoritative until a versioned migration completes.
- User-facing A/B/C/D folders may use index/link projections during transition. Projection content carries ownership and revision metadata so it cannot be mistaken for a duplicate source.
- Generated source projections remain excluded from source-sync input. External output drop folders remain excluded from broad source import until registered as outputs.
- Media originals, OCR, PDF text, table extraction, image regions, and generated previews are separate versioned records. Re-extraction never overwrites a source body or user attachment.
- Obsidian plugin configuration is treated as a user-owned integration boundary. BSC can validate declared routes and consume exported files, but it never edits plugin executable code or treats installation as captured evidence.
- Each migration ships with idempotent database changes, a dry-run report, compatibility tests, rollback behavior, and a worklog entry.

### 11.3 Ecosystem Boundary

The system may integrate Obsidian plugins, Horizon, Feishu exports, document importers, browser clipper tools, content-publishing tools, external Skills, and BI tools. Each integration is an adapter with:

- Declared data direction, ownership, route, credentials, rate limits, and failure state.
- Provenance and trust mapping into the same source/output contracts.
- A feature flag and non-destructive disable path.
- No privileged execution of untrusted plugin code or embedded source instructions.

## 12. Non-Goals

- Replacing Obsidian, Horizon, a document management system, or a corporate BI platform in the first release.
- Training a foundation model on private Vault content.
- Treating automated summaries as independent evidence.
- Auto-publishing all model-generated Wiki pages, Skills, or outputs.
- Making cross-project knowledge globally visible without explicit tenant policy and authorization.
- Optimizing dashboards for presentation while leaving the review, feedback, and outcome loops unimplemented.

## 13. Definition Of 100 Percent Done

This PRD reaches 100 percent only when the technical, operational, and user-value gates all hold together:

- The current project's source routes, Vault mapping, schedule, provider boundaries, and access policy are real, observable, and truthful.
- A/B/C/D each contain real project-scoped assets with durable lineage, not only scaffolds or test fixtures.
- The personal operating loop has processed real incoming material across multiple cycles and has used feedback to alter subsequent knowledge or method decisions.
- The BSC workspace and Obsidian views expose the same authoritative state without duplicate writable truths.
- The dashboard can justify its metrics and actions from persisted records, including insufficient-data cases.
- Failure, disagreement, correction, and inapplicability remain visible as learning signals rather than being hidden to make the system look successful.

Until those conditions are demonstrated, the correct status is **implemented capability with open operational proof**, not fully self-growing knowledge intelligence.
