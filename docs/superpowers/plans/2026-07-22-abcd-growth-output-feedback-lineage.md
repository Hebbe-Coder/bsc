# P3 - Output Registration, Evaluation, Feedback And Lineage Implementation Plan

**Goal:** Make every project-owned result a first-class D-layer asset with immutable materialization, generation provenance, quality evaluation and safe feedback routing into B/C proposals or failure knowledge.

**Architecture:** Add one `OutputRegistry` behind terminal Skill, orchestration and export bridges. Registration is idempotent and never changes existing lifecycle semantics. Evaluation and feedback are separate append-only records. `FeedbackRouter` may create governed proposals/cases, but it cannot publish Wiki pages, methods, or synthetic evidence.

**Depends on:** P1 and P2.
**Blocks:** P4 and P5.
**PRD coverage:** FR-8, FR-9, FR-10; AC 10-12 and 17.

## Owned Files

**Create:** `app/knowledge/output_registry.py`, `app/knowledge/output_evaluator.py`, `app/knowledge/feedback_router.py`, `app/knowledge/output_bridges.py`, `tests/knowledge/test_output_registry.py`, `tests/knowledge/test_output_evaluator.py`, `tests/knowledge/test_feedback_router.py`, and `tests/integration/test_growth_output_bridges.py`.

**Modify:** `app/skills/execution_store.py`, `app/api/skill_routes.py`, `app/orchestrator/runtime_engine.py`, `app/api/orchestrate.py`, `app/api/bsc_api.py`, `app/tasks/export_tasks.py`, and exporter completion wiring only through the shared bridge. Changes must remain optional when no project ID is present.

**Forbidden:** Reopening terminal Skill/orchestrator runs, changing export response contracts, mutating business Artifact Graph, moving/deleting original output files, global legacy output backfill, or treating generated prose as external evidence.

## Frozen Public Contracts

- Output identity is project plus producer/run/result identity plus content hash. Retry returns the same logical registration.
- Required provenance: goal, audience, channel, generator, provider/model, prompt/method revision, context revision, run/session, source/page refs, hash, MIME, Vault path and status.
- Text and binary files materialize below `outputs/<year>/<output-id>/` without modifying the original; `index.md` is managed metadata.
- Quality components are groundedness 30%, task fit 25%, usefulness 20%, coherence 15% and format quality 10%; type-specific evaluators may override presentation cases but not evidence rules.
- Feedback is append-only and links to output, actor, rating/correction/comment and processing state.

## Task 1: Output Registry And Materialization

- [x] Write failing tests for text/binary registration, deterministic ID, duplicate retry, hash mismatch, missing project, path escape, unknown legacy ownership, materialization collision and original-file preservation.
- [x] Implement `OutputRegistry.register` as one transaction around metadata/lineage and an atomic managed Vault write with cleanup on failure.
- [x] Create `index.md` with provenance and references; preserve binary bytes and use descriptors for externally managed/oversized assets.
- [x] Support adopted external deliverables only through explicit project-admin action and mark their generator/origin accurately.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_output_registry.py tests/knowledge/test_growth_vault.py -q`.

## Task 2: Production Completion Bridges

- [x] Write failing integration tests proving a completed Skill, orchestration session and export register once while failed/cancelled/incomplete work does not register accepted output.
- [x] Implement a shared best-effort/audited bridge after existing terminal commit points; bridge failure must be visible but must not reopen or falsify the producer lifecycle.
- [x] Carry explicit `project_id`; preserve legacy behavior when ownership is absent and report `not_registered_unscoped` rather than assigning a default project.
- [x] Add lineage to run, source/page context and method revision when present without writing business Artifact Graph edges.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_growth_output_bridges.py tests/test_skill_execution_store.py tests/orchestrator/test_lifecycle.py -q`.

## Task 3: Output Quality Evaluation

- [x] Write failing tests for formula/boundaries 59/60/84/85, evaluator unavailable, type-specific cases, evidence hallucination, model revision/latency persistence and repeat idempotency.
- [x] Implement deterministic structural/evidence checks plus optional model scoring; persist component scores and findings rather than only the aggregate.
- [x] Transition output through `evaluating` to accepted/rejected only under the frozen state map. A 60-84 result remains improvement-required and is not auto-filed.
- [x] Enforce groundedness against registered source/page ancestry; D-only circular references cannot satisfy evidence requirements.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_output_evaluator.py -q`.

## Task 4: Feedback Routing

- [x] Write failing tests for accepted, rejected, corrected, rated and reused feedback; duplicate processing; actor permissions; unsupported route; and cross-project output access.
- [x] Route evidence-backed accepted output to a `WikiProposal` draft, repeatable accepted workflow to a `MethodProposal` candidate, correction to a regression case, and rejection to a failure pattern.
- [x] Require external A ancestry for factual Wiki proposal claims. A newly discovered attachment is separately captured through P2 before it can support B.
- [x] Make feedback processing idempotent and transactional; a failed route leaves feedback pending/failed with an actionable reason.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_feedback_router.py tests/knowledge/test_proposal_gate.py -q`.

## Task 5: Lineage Integrity And Handoff

- [x] Prove output-to-run/source/page/method/evaluation/feedback edges are rebuildable for graph projection but authoritative in P1 lineage storage.
- [x] Test direct and multi-hop attempts to make an output its own evidence ancestor, including through a Wiki proposal.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_output_registry.py tests/knowledge/test_output_evaluator.py tests/knowledge/test_feedback_router.py tests/integration/test_growth_output_bridges.py tests/knowledge/test_knowledge_graph.py -q`.
- [x] Run `git diff --check` and `git status --short` and append real bridge/evaluation evidence to the worklog.

## Acceptance Criteria

- Real project-owned Skill, orchestration and export completions register one immutable output with complete context, method and evidence provenance.
- Registration failure never corrupts original output or producer lifecycle, and is never hidden as success.
- Evaluation is component-level, revisioned and threshold-correct; unavailable evaluators do not invent scores.
- Accepted/rejected/corrected feedback creates only the allowed governed route and cannot create source authority.
- Existing Skill, orchestrator, export and Artifact Graph regressions remain compatible.

## Rollback Strategy

Disable completion bridges and feedback processing, leaving producer behavior and all audit records intact. New output files remain user-visible. Revert registry/evaluator code but retain additive schema; do not remove originals or registered materializations.

## Required Handoff

Provide P4/P5 with accepted-output queries, evaluation summary schema, feedback/failure-case schema, bridge registration events, lineage traversal API and explicit `not_registered_unscoped` behavior. Record test counts and producer compatibility in the worklog.
