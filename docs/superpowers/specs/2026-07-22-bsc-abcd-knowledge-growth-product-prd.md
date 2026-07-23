# BSC A/B/C/D Self-Growing Knowledge Product PRD

**Status:** P1-P9 implementation complete and verified in isolated fixtures and Docker runtime on 2026-07-22; live third-party account calls are intentionally not claimed.
**Date:** 2026-07-22
**Owner:** BSC product and platform
**Supersedes:** None
**Extends:** `docs/superpowers/specs/2026-07-21-karpathy-llm-wiki-knowledge-growth-prd.md`
**References:** Andrej Karpathy, "LLM Knowledge Bases"; Xuanjiang, "Codex + Obsidian self-growing knowledge base" tutorial; existing BSC Horizon, Wiki, Skill, orchestration, MCP, Artifact Graph, and Knowledge Workspace capabilities.
**Execution index:** `docs/superpowers/plans/2026-07-22-abcd-growth-execution-index.md`

## 1. Product Definition

### 1.1 Product thesis

BSC will turn personal research, project evidence, external intelligence, repeated work, and actual outputs into a governed knowledge growth loop:

```text
Capture -> A Evidence -> B Knowledge -> C Method -> D Output -> Review -> B/C/Eval
```

The system is not a folder template and is not a generic RAG upload page. The four stages are governed asset classes with explicit authority, state, lineage, quality gates, and project isolation.

- **A / Evidence:** immutable external or user-provided material.
- **B / Knowledge:** readable, linked, evidence-backed Wiki synthesis.
- **C / Method:** reusable prompts, SOPs, playbooks, and Skills proven through actual work.
- **D / Output:** articles, reports, scripts, presentations, dashboards, images, videos, and retrospectives produced for a real task.
- **Review:** the routing layer that decides whether an output becomes a Wiki proposal, a method proposal, a correction case, or a failure example.

Obsidian remains the knowledge IDE. LLMs act as maintainers and researchers. BSC owns orchestration, persistence, permissions, validation, evaluation, scheduling, MCP compatibility, and visualization.

### 1.2 Interpretation of the reference material

Karpathy's core loop is:

1. collect raw documents into a `raw/` directory;
2. incrementally compile and maintain a Markdown Wiki;
3. use the Wiki through agents and CLI tools for research and generation;
4. file valuable outputs back into the Wiki;
5. run health checks to find contradictions, missing information, useful connections, and new research questions.

The tutorial adds a practical product layer:

- Horizon and browser/Obsidian import tools broaden capture;
- Codex automations turn maintenance into recurring jobs;
- repeated prompts and workflows become Skills;
- outputs can be Markdown, HTML dashboards, illustrations, presentations, or videos.

BSC adopts both ideas with one correction: D outputs never flow unconditionally into A or B. Every feedback path is typed and gated to prevent synthetic evidence loops.

### 1.3 Current baseline

BSC already provides:

- immutable project-scoped `SourceRecord` capture and source lifecycle;
- Obsidian project mappings, safe Wiki bootstrap, and non-destructive source sync;
- Horizon staged-run ingestion with provenance and durable scheduling;
- Wiki pages, revisions, proposals, citations, lint, evaluation, publication, and rollback;
- persistent knowledge runs, ordered events, schedules, retries, and weekly distillation;
- project context packs for PRD-to-SOP generation;
- MCP HTTP/SSE tools and a Knowledge Workspace with sources, Wiki, Diff, runs, health, trends, and graph;
- a Skill Registry and persistent Skill execution history;
- a separate business Artifact Graph that must retain its existing semantics.

The product gap is the absence of first-class C/D lifecycle, output feedback, cross-stage lineage, method evolution, and a unified growth view.

## 2. Problem And Outcomes

### 2.1 Problems

1. Imported information accumulates faster than users can judge or connect it.
2. Existing knowledge is repeatedly rediscovered because useful conclusions are not consistently filed.
3. Generic prompts and templates produce outputs that are insufficiently tailored to project context.
4. Skill execution history does not prove where a method came from or whether it works.
5. Generated outputs are not consistently registered, evaluated, or reused.
6. Negative feedback is not yet a durable input to Wiki, method, and output evaluation.
7. Users cannot see the real conversion from source to knowledge to method to outcome.

### 2.2 Goals

- Make every trusted source, published claim, approved method, and accepted output traceable.
- Let the knowledge base improve through routine use without requiring manual folder maintenance.
- Generate project-specific SOPs and content from evidence, profile, rules, validated methods, and prior outcomes.
- Turn successful repeated workflows into reusable methods under measurable quality gates.
- Turn low-quality outputs and corrections into regression tests instead of repeated mistakes.
- Produce daily incremental and Friday weekly distillation files in the user's Obsidian Vault.
- Give users a real operational view of growth, quality debt, and pending decisions.

### 2.3 Non-goals

- Do not replace Obsidian or move user data into a proprietary document format.
- Do not treat an LLM answer, generated output, or social post as authoritative solely because it exists.
- Do not auto-install or trust arbitrary Obsidian plugins, Skill packages, hooks, or executable code.
- Do not merge the Knowledge Graph with the business Artifact Graph.
- Do not require fine-tuning for the first release.
- Do not claim that an automation ran when its model, scheduler, integration, or filesystem was unavailable.

## 3. Users And Jobs

| User | Primary job | Required outcome |
|---|---|---|
| Personal researcher | Convert reading into durable understanding | Linked concepts, research questions, and evidence-backed summaries |
| Content creator | Convert signals into original content | Weekly angles, reusable context, accepted drafts, and style methods |
| Founder / project lead | Preserve project memory and decisions | Current constraints, decisions, rationale, and action-ready context |
| Consultant | Turn a PRD into a client-specific SOP or report | Evidence-backed steps, controls, metrics, and explicit assumptions |
| Team reviewer | Understand and approve knowledge changes | Diff, provenance, evaluation, feedback, and rollback |
| Agent / MCP client | Read and maintain knowledge programmatically | Typed project-scoped tools and deterministic failure modes |

## 4. Product Principles

1. **Evidence before synthesis.** Factual publication requires an A-layer source.
2. **Compilation, not accumulation.** B evolves concepts and relationships instead of producing one summary per file.
3. **Methods require proof.** A prompt is not a Skill until repeated outcomes validate it.
4. **Outputs are experiments.** D records what was attempted, with which context and method, and whether it worked.
5. **Feedback is routed, not dumped.** Acceptance, correction, rejection, reuse, and new evidence have different destinations.
6. **Automation maintains work, not authority.** Jobs may create candidates; publication still passes deterministic and evaluation gates.
7. **Readable state wins.** Durable knowledge and distillation remain inspectable Markdown.
8. **Indexes are replaceable.** Search indexes and graph projections are rebuildable from authoritative records.
9. **No synthetic echo.** Derived output cannot become factual evidence without an external evidence ancestor.
10. **No fake operations.** Every visible state comes from a persisted record or a truthful unavailable result.

## 5. Authority And Information Architecture

### 5.1 Authority matrix

| Layer | Authority | Mutation policy | Storage |
|---|---|---|---|
| Project profile and rules | User-approved project intent and policy | User edit or governed proposal | `AGENTS.md` plus project metadata |
| A Evidence | Original material and immutable extraction snapshot | New version only | Vault `raw/` / `inbox/` plus BSC source registry |
| B Knowledge | Published project synthesis | Governed Wiki proposal and rollback | Vault `wiki/` plus page revisions |
| C Method | Approved reusable method definition | Method proposal and version publication | Vault `methods/` plus method registry |
| D Output | Immutable generated or adopted task result | New output version or disposition | Vault `outputs/` plus output registry |
| Feedback | User or evaluator observation | Append-only, then processed | BSC database |
| Runs and schedules | What actually executed | BSC services only | BSC database |
| Retrieval index | Search acceleration | Rebuildable | Existing keyword/TF-IDF/vector backends |
| Knowledge graph projection | Navigation and visualization | Rebuildable from lineage and content | BSC database |

### 5.2 Vault layout

```text
<vault>/<project>/
  AGENTS.md
  inbox/
    horizon/
    manual/
  raw/
    web/
    papers/
    meetings/
    media/
    imports/
  wiki/
    overview.md
    index.md
    log.md
    concepts/
    entities/
    decisions/
    research/
    playbooks/
  methods/
    <method-slug>/
      SKILL.md
      evals.md
  outputs/
    <year>/<output-id>/
      index.md
      <generated-files>
  reviews/
    failures/
    corrections/
  distillations/
    每周蒸馏/
      <YYYY-Www>/
        每日增量/<YYYY-MM-DD>.md
        00-本周总结.md
        01-知识行动.md
        02-内容创作.md
        03-下周上下文包.md
        04-方法迭代.md
        manifest.json
        revisions/
  attachments/
  .bsc/
```

Existing `distillations/<week>/` records remain readable and are not moved automatically. New dual-track automation writes under `distillations/每周蒸馏/` after the feature is enabled.

Workspace initialization atomically creates any missing layout directories and a root operational `README.md` alongside the managed Wiki baseline. It never creates synthetic factual knowledge, overwrites a user-authored file, or treats the new layout as a captured source. A Vault with only the former minimal Wiki files is reported as `mapped_incomplete` until this layout exists.

### 5.3 Binary file policy

- PDF, image, office, audio, video, and generated binary files must not be decoded as UTF-8.
- Wiki publication updates managed text atomically while preserving unmodified binary files.
- Binary assets are stored by content hash or immutable output ID.
- Oversized or externally managed media may use a Markdown descriptor with origin, hash, size, MIME type, and extraction state.
- Missing OCR or transcription capability is recorded as `extraction_unavailable`; capture still succeeds.

## 6. Project Profile

Each project has a profile used by triage, Wiki compilation, method selection, SOP generation, and content output.

Required profile fields:

- `research_domains`
- `user_role`
- `primary_output_types`
- `target_audiences`
- `preferred_channels`
- `language`
- `content_voice`
- `evidence_threshold`
- `automatic_publication_policy`
- `method_promotion_policy`

New projects receive compatible defaults. Existing `AGENTS.md` files remain valid when optional profile fields are absent and are never silently rewritten.

## 7. Domain Model And Lifecycle

### 7.1 Existing entities retained

- `SourceRecord`
- `WikiPage`
- `WikiProposal`
- `CitationLink`
- `KnowledgeRun`
- `KnowledgeSchedule`
- `WeeklyDistillation`

### 7.2 New entities

| Entity | Responsibility | Key fields |
|---|---|---|
| `SourceTriage` | Score and route one source relative to a project profile | source, profile revision, five scores, reliability, disposition, reasons, evaluator revision |
| `MethodAsset` | Current published reusable method | project, slug, name, applicability, input/output contract, status, version, Vault path |
| `MethodRevision` | Immutable method version | body, manifest, evidence/output refs, eval summary, proposal, created at |
| `MethodProposal` | Candidate method change | source outputs, rationale, operation, status, validation and evaluation results |
| `OutputAsset` | Registered task result and its generation context | kind, title, MIME, hash, Vault path, run, method revision, context revision, refs, status, quality |
| `OutputFeedback` | User/evaluator observation about an output | type, rating, correction, comment, actor, processed state |
| `KnowledgeLineageEdge` | Authoritative cross-stage relationship | from type/id, to type/id, relation, metadata, revision |

### 7.3 States

- Source processing: `captured -> validated -> eligible -> processed`; terminal `rejected` or `superseded`.
- Triage disposition: `research_topic`, `knowledge_candidate`, `reference`, `archive`, or `ignore`.
- Method: `candidate -> validating -> approved -> published`; terminal `rejected`, `deprecated`, or `superseded`.
- Output: `registered -> evaluating -> accepted/rejected -> filed/archived`; optional `superseded`.
- Feedback type: `accepted`, `rejected`, `corrected`, `rated`, or `reused`.

### 7.4 Lineage relations

The minimum supported relations are:

- `source_supports_page`
- `source_contradicts_source`
- `page_informs_method`
- `output_used_source`
- `output_used_page`
- `output_used_method_revision`
- `output_produced_by_run`
- `feedback_evaluates_output`
- `output_proposes_page`
- `output_proposes_method`
- `method_supersedes_method`

Lineage creation rejects project mismatches, missing endpoints, duplicate deterministic edges, and direct or indirect cycles that would make a generated output its own evidence ancestor.

## 8. Functional Requirements

### FR-1 Project onboarding and profile

- A user can configure Vault mapping, research domains, role, audiences, primary outputs, and content voice.
- The workspace must show whether the profile, Vault, scheduler, Horizon, model, and automation are configured.
- Project rules remain the policy authority and are included by revision in every governed run.

### FR-2 Multi-channel evidence capture

- Capture Obsidian imports, uploads, Horizon signals, Feishu documents and meeting summaries, browser clips, and explicitly adopted BSC artifacts.
- Preserve original bytes or source URI, content hash, extraction text, MIME type, source time, capture time, and extractor state.
- Secrets, access tokens, and API keys must never be persisted in Vault content, prompts, run events, or output files.
- User notes and annotations are marked as curated opinion, not external fact.

### FR-3 Five-dimensional triage

Every newly validated source is evaluated relative to the current project profile:

```text
priority = relevance * 0.30
         + value * 0.25
         + freshness * 0.15
         + outputability * 0.15
         + connectedness * 0.15
```

Routing defaults:

- score `>= 80` and reliability pass: `knowledge_candidate`;
- score `60-79`: `reference`;
- score `40-59`: `archive`;
- score `< 40`: `ignore`;
- a high-value unanswered question with insufficient evidence: `research_topic`.

Source reliability is a hard gate independent of priority. The decision, reasons, profile revision, and evaluator revision are persisted and reviewable.

### FR-4 B-layer Wiki compilation

- Select only eligible, unprocessed evidence within the active project.
- Read the project profile, `AGENTS.md`, overview, index, affected pages, relevant evidence, and bounded prior distillation.
- Produce a `WikiProposal`; never write published pages directly.
- Maintain concepts, links, citations, overview, index, research questions, and append-only log.
- Preserve contradictions and uncertainty instead of inventing resolution.
- Mark sources processed only after successful publication.

### FR-5 Research and health loop

- Health checks identify stale pages, orphan pages, dangling citations, uncited eligible evidence, unresolved contradictions, repeated failed queries, and candidate research questions.
- Web research results re-enter A as new external sources before they affect B.
- Health recommendations create proposals or research tasks, not silent page changes.

### FR-6 C-layer method evolution

- Detect repeated successful workflows from method executions, orchestration runs, accepted outputs, and user corrections.
- Generate a method proposal containing applicability, exclusions, inputs, outputs, steps, evidence rules, failure handling, and evaluation cases.
- Default promotion threshold: at least three comparable successful uses, average quality `>= 85`, groundedness `>= 0.90`, at least one accepted or reused output, and no security or permission failure.
- Prompt-only methods may auto-publish only when project and global policy allow it and all gates pass.
- Code, hooks, agents, filesystem commands, or new MCP permissions always require administrator approval.
- Published method revisions remain reproducible and rollback-capable.

### FR-7 Project-specific generation

- PRD-to-SOP and content generation assemble a context pack from profile, project rules, relevant Wiki pages, external evidence, decisions, constraints, approved methods, evaluations, and weekly distillation.
- Generic templates may define layout only. Business claims, metrics, controls, and process steps must be sourced or explicitly marked as assumptions.
- Prior D outputs may be style or method examples but may not replace factual evidence.
- Negative cases contribute failure patterns and eval cases without injecting erroneous prose as truth.

### FR-8 D-layer output registration

- Register every BSC Skill result, orchestration result, export, report, presentation, dashboard, image, and adopted external deliverable with a project ID.
- Record task goal, audience, channel, generator, model, prompt/method revision, context revision, run/session ID, evidence/page refs, file hash, MIME type, and Vault path.
- Existing global files with unknown project ownership are not backfilled automatically.
- Binary and text outputs are materialized under a deterministic output ID without moving or deleting the original file.

### FR-9 Output evaluation

Default output quality score:

```text
quality = groundedness * 0.30
        + task_fit * 0.25
        + usefulness * 0.20
        + coherence * 0.15
        + format_quality * 0.10
```

- `>= 85`: eligible for acceptance or filing review.
- `60-84`: improvement required.
- `< 60`: rejected and added to failure analysis.
- Type-specific eval cases override generic presentation requirements where defined.
- Evaluator availability, model revision, findings, and latency are persisted.

### FR-10 Feedback routing

- Accepted, evidence-backed output may create a B-layer Wiki proposal.
- A repeatable accepted workflow may create a C-layer method proposal.
- User correction creates a correction record and regression case; it is not a factual source unless accompanied by external evidence.
- Rejected output creates a failure pattern linked to the method, context, and evaluator findings.
- A new external attachment discovered during output work is captured as a new A-layer source.
- No route performs unconditional D-to-A or D-to-B publication.

### FR-11 Dual-track distillation

Two recurring local Codex automations operate in Asia/Shanghai:

- **Daily at 17:00:** create a project-scoped incremental digest.
- **Friday at 17:30:** create the complete weekly bundle after the daily job has finished.

Daily output includes A/B/C/D changes, contradictions, candidates, actions, and an evidence index.

Friday output includes:

1. `00-本周总结.md`
2. `01-知识行动.md`
3. `02-内容创作.md`
4. `03-下周上下文包.md`
5. `04-方法迭代.md`
6. `manifest.json`

Automation rules:

- exclude `distillations/` from inputs to prevent recursive ingestion;
- compute a deterministic input manifest and `input_hash`;
- no-op when the same input hash already completed;
- preserve a prior generated revision before replacing changed weekly output;
- never modify A/B/C/D content;
- write atomically and never overwrite an unmarked user-authored file;
- report processed projects, input count, output paths, and failures truthfully.

### FR-12 Horizon and external intelligence

- Horizon remains an external capture and enrichment pipeline, not a knowledge authority.
- BSC imports only documented run artifacts or sidecar responses and preserves Horizon run/stage provenance.
- Horizon scores inform triage but do not replace BSC source policy.
- Network, authentication, rate-limit, and missing-configuration failures remain durable and retryable where appropriate.

### FR-13 Feishu and Obsidian integration

- Feishu CLI may import documents, meeting summaries, and explicitly selected content under user authorization.
- Imported Feishu content becomes A-layer evidence with source URL, document revision, capture time, and attachment references.
- Studio provides an explicit-export handoff for one user-selected Feishu document or meeting-summary JSON. It creates a project-scoped import run and redacts/rejects credentials; it never scrapes Feishu or performs background account access.
- Obsidian plugins are optional capture tools; BSC works without Claudian, Clipper, Importer, Docxer, HyperFrames, or third-party Skill packages.
- Plugin-generated files pass the same project, path, source, and trust controls as any other input.

### FR-14 Retrieval and context

- Query B first through maintained index and page summaries, then use hybrid retrieval to return to A for exact evidence.
- Retrieval indexes remain rebuildable and never become authority.
- Default generation context is bounded to 12,000 characters unless a task-specific policy provides another limit.
- Context output records included, omitted, and retrieved references.

### FR-15 API and MCP

Add project-scoped REST and MCP capabilities for:

- profile read/update;
- unified A/B/C/D asset listing;
- source upload and triage inspection;
- method listing, proposal review, revision reading, execution, and deprecation;
- output registration, reading, evaluation, feedback, and filing;
- lineage graph and growth summary;
- daily/weekly distillation and growth review runs.

Existing Wiki, knowledge query, Skill, MCP transport, SSE, and error contracts remain backward compatible.

### FR-16 Knowledge Growth Workspace

The existing Knowledge Workspace becomes a growth operations surface:

- left stage rail: A Evidence, B Knowledge, C Methods, D Outputs, Review;
- center reader: asset list, Markdown/output preview, proposal Diff, run timeline, or graph;
- right inspector: provenance, quality, lineage, feedback, and permitted actions;
- persistent project/profile selector and global search;
- real conversion funnel, throughput, citation coverage, method success, output acceptance, and quality debt trends;
- filterable `source/page/method/output/feedback` relationship graph;
- explicit empty, loading, offline, unavailable, permission-denied, failed, and no-Vault states.

Desktop uses a stable three-pane workflow. Mobile uses stage tabs and an inspector drawer without horizontal overflow or action overlap. The product follows the existing BSC operational visual language rather than copying the tutorial's promotional infographic styling.

## 9. Permissions And Safety

| Action | Reader | Project admin | Admin/System under policy |
|---|---:|---:|---:|
| Read project assets and lineage | Yes | Yes | Yes |
| Capture and annotate source | No | Yes | Yes |
| Create Wiki/method proposal | No | Yes | Yes |
| Publish Wiki proposal | No | Yes, gated | Yes, gated and audited |
| Publish prompt-only method | No | Yes, gated | Optional automatic policy |
| Enable code/hook/MCP method | No | No | Yes, explicit approval |
| Register output feedback | Own/allowed project | Yes | Yes |
| Configure schedules/profile | No | Yes | Yes |

Security requirements:

- canonical project-relative paths and symlink escape protection;
- project authorization on every repository, API, MCP, graph, and file operation;
- secret redaction before persistence and event emission;
- no arbitrary shell operation in a knowledge proposal;
- bounded file size, response size, graph size, and model context;
- content from documents, web pages, and Vault files is treated as untrusted input, never as execution instruction;
- automatic publication retains a durable actor, reason, policy revision, findings, and rollback target.

## 10. Reliability And Performance

- Every scheduled run has a persistent idempotency key and ordered event ledger.
- Abandoned runs are recovered and marked failed before retry.
- Daily processing is bounded by project-configured batch size and resumes from a durable cursor.
- List APIs are paginated; graph responses remain bounded to 500 nodes/edges per slice by default.
- Metadata list requests target p95 below 300 ms for 10,000 project records on the supported local deployment profile.
- Atomic file publication must preserve unrelated user content and binary files after process interruption.
- SQLite and PostgreSQL produce equivalent lifecycle behavior.
- Celery/Redis-disabled mode exposes manual execution and `unavailable` scheduling instead of simulating background work.

## 11. Product Metrics

### 11.1 Growth

- A-to-B candidate and publication conversion rate
- median eligible-source age before processing
- published Wiki pages with current citations
- accepted outputs filed into B or C
- approved method count and method reuse rate

### 11.2 Quality

- citation coverage and dangling citation count
- contradiction resolution age
- output acceptance, correction, and rejection rates
- method success rate by revision and task type
- evaluation regression count
- synthetic-only claim rejection count

### 11.3 Operations

- daily and weekly automation success rate
- duplicate/no-op rate
- queue delay, runtime, retry count, and abandoned run count
- extraction unavailable rate by media type
- scheduler, Horizon, model, and Vault availability

Metrics must be computed from persisted records. The UI must not infer success from file existence alone.

## 12. Acceptance Scenarios

1. A clipped article is captured once, hashed, triaged with reasons, and remains unchanged after Wiki publication.
2. A new Horizon run imports only new staged artifacts and cannot directly publish Wiki content.
3. A high-scoring but unreliable source remains ineligible for factual synthesis.
4. Two contradictory sources produce an explicit contradiction and research candidate rather than a fabricated resolution.
5. A Wiki proposal updates related pages, index, citations, and graph atomically or changes nothing.
6. A PDF or presentation stored in the project survives a Wiki publication without decode failure or deletion.
7. Three successful comparable outputs create a method candidate; fewer than three do not auto-promote it.
8. A method revision that reduces the evaluation baseline cannot replace the published revision.
9. A PRD-to-SOP run identifies the profile, rules, sources, pages, method revision, and assumptions used.
10. Every generated output is registered with project, run, context, method, hash, and quality information.
11. An accepted output creates a proposal with external evidence ancestry; it never becomes an A source by itself.
12. A rejected output creates a failure case and reduces future method evaluation without becoming factual context.
13. The daily automation runs twice against identical input and produces one logical result.
14. The Friday automation archives a prior managed revision when source input changes during the same week.
15. A user-authored file inside the distillation path is not overwritten.
16. A Feishu meeting summary is imported under the correct project and preserves document revision provenance.
16a. A Studio explicit-export import creates a `feishu_import` audit run, redacts raw evidence from source list responses, and rejects credentials before persistence.
17. Cross-project method, output, source, graph, API, and MCP access is rejected.
18. Desktop and mobile users can move from an output to its method, Wiki context, and original evidence.
19. Missing Redis, Horizon, model, OCR, transcription, or Vault configuration produces a truthful unavailable state.
20. Existing Wiki, Artifact Graph, Skill, orchestration, and MCP compatibility tests continue to pass.

## 13. Rollout

### Phase 0: Contract lock

- Approve this PRD and create the implementation index and worklog.
- Freeze entity states, lineage relations, automation paths, and compatibility requirements.

### Phase 1: Authority and filesystem hardening

- Add project profile and triage contracts.
- Make Vault publication binary-safe.
- Add method, output, feedback, and authoritative lineage persistence.

### Phase 2: C/D loop

- Register outputs from Skill, orchestration, and export paths.
- Add output evaluation, feedback routing, method proposals, and rollback.
- Extend context construction and weekly distillation.

### Phase 3: Automation and integration

- Create the daily 17:00 and Friday 17:30 Codex automations against `D:\bsc`.
- Add growth review scheduling and Feishu import provenance.
- Verify Horizon, Celery Worker/Beat, restart recovery, and unavailable paths.

### Phase 4: Workspace and release

- Deliver the A/B/C/D/Review workspace, funnel, trends, and lineage graph.
- Complete browser, accessibility, mobile, Docker, PostgreSQL, security, and backward-compatibility acceptance.
- Update user documentation and release notes with verified runtime evidence.

## 14. Default Decisions

- The active Obsidian Vault remains `D:\bsc\bsc`; project directories remain under `projects/`.
- `default` is the personal/general knowledge project; `horizon-radar` is the external intelligence project unless explicitly remapped.
- Daily incremental distillation runs at 17:00; Friday weekly distillation runs at 17:30 in Asia/Shanghai.
- Automatic work always creates reviewable records. Direct authority changes remain controlled by existing global and project policy.
- Prompt-only methods are the only C-layer assets eligible for gated automatic publication.
- Fine-tuning and synthetic training data are deferred until accepted outputs and regression cases form a reliable dataset.
- Existing runtime databases, user Vault content, and historical outputs are not modified or backfilled merely by installing this feature.

## 15. Implementation Plan Mapping

The PRD is implemented through nine bounded plans. The execution index is the authority for dependency order, cross-plan contracts, file ownership, integration gates, handoff evidence, and rollback order.

| Plan | Implementation boundary | PRD coverage | Dependency |
|---|---|---|---|
| P1 `2026-07-22-abcd-growth-contracts-profile-vault.md` | Contracts, project profile, persistence, Vault safety | FR-1 and FR-8 foundations; AC 6, 17, 20 | 2026-07-21 baseline |
| P2 `2026-07-22-abcd-growth-capture-triage-integrations.md` | Capture, five-dimensional triage, Horizon, Feishu, Obsidian | FR-2, FR-3, FR-5, FR-12, FR-13; AC 1-4, 16, 19 | P1 |
| P3 `2026-07-22-abcd-growth-output-feedback-lineage.md` | D output registry, evaluation, feedback, lineage | FR-8, FR-9, FR-10; AC 10-12 | P1, P2 |
| P4 `2026-07-22-abcd-growth-method-evolution.md` | C method evolution, evaluation, approval, rollback | FR-6; AC 7-8 | P3 |
| P5 `2026-07-22-abcd-growth-context-generation.md` | Evidence-grounded context and project-specific generation | FR-4, FR-7, FR-14; AC 5, 9, 12 | P2-P4 |
| P6 `2026-07-22-abcd-growth-automation-distillation.md` | Daily and Friday automation, dual-track distillation, recovery | FR-11; AC 13-15, 19 | P5 |
| P7 `2026-07-22-abcd-growth-api-mcp.md` | Project-scoped REST, SSE, MCP and permissions | FR-15; AC 17, 20 | P5 |
| P8 `2026-07-22-abcd-growth-workspace-visualization.md` | A/B/C/D/Review workspace and real visualizations | FR-16; AC 18-19 | P7 |
| P9 `2026-07-22-abcd-growth-integration-release.md` | E2E, isolation, recovery, Docker, PostgreSQL, browser and release | Reliability, performance and all AC | P1-P8 |

Plan files remain test-first execution contracts. An unchecked item is not complete merely because production code exists; it may be checked only after its exact acceptance evidence is recorded in `docs/superpowers/worklogs/2026-07-22-abcd-knowledge-growth.md`.
