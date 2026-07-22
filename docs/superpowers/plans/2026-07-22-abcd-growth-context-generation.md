# P5 - Growth Context And Project-Specific Generation Implementation Plan

**Goal:** Build bounded, cited context packs that use the active project's profile, rules, B knowledge, A evidence, approved C methods, D learnings, evaluations and distillation without falling back to generic templates as business truth.

**Architecture:** Extend the existing context-pack and Wiki compiler services with a typed `GrowthContextPack`. Selection starts with B summaries and maintained indexes, returns to A for exact evidence, adds only approved method revisions and uses D outputs as style/method examples or typed failure cases. Every pack records included, omitted and assumption references.

**Depends on:** P2, P3 and P4.
**Blocks:** P6 and P7.
**PRD coverage:** FR-4, FR-7 and FR-14; AC 5, 9 and 12.

## Owned Files

**Create:** `app/knowledge/growth_context.py`, `app/knowledge/generation_provenance.py`, `tests/knowledge/test_growth_context.py`, `tests/knowledge/test_generation_provenance.py`, and `tests/integration/test_growth_sop_context.py`.

**Modify:** `app/knowledge/context_pack.py`, `app/knowledge/wiki_compiler.py`, `app/knowledge/wiki_service.py`, `app/knowledge/prompts.py`, `app/knowledge/agent_router.py`, and the existing PRD/SOP generation bridge only where it accepts the additive context contract.

**Forbidden:** Unbounded retrieval, direct file writes from generation, generic template claims presented as facts, D-only evidence, cross-project fallback, changing Wiki proposal gates, or changing the existing orchestrator lifecycle.

## Frozen Public Contracts

- `GrowthContextPack` contains project/profile/rules revisions, selected source/page/method/output/eval/feedback IDs, rendered sections, assumptions, omissions, source cutoff, context hash, character/token budget and creation run.
- Default rendered context limit is 12,000 characters unless a task policy overrides it with a bounded value.
- Retrieval order is B summary/index -> hybrid search -> A exact evidence; index records are never authority.
- Output examples may influence style/method but never replace factual evidence. Rejected output prose is a failure pattern only.
- Every generated artifact references context revision, method revision (if any), evidence/page refs, assumptions and generator/model revision.

## Task 1: Context Selection And Budgeting

- [x] Write failing tests for profile/rules inclusion, 12,000-character budget, deterministic ordering, source/page deduplication, project isolation, omissions and unavailable index fallback.
- [x] Implement candidate selection from maintained B pages and summaries, then hydrate exact A citations and contradictions within a bounded budget.
- [x] Include active profile and `AGENTS.md` revision, approved methods, relevant accepted outputs, correction/failure cases and latest eligible distillation without ingesting the distillation folder recursively.
- [x] Record every omitted candidate with a reason such as budget, permission, stale, failed reliability or unsupported type.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_context.py tests/knowledge/test_context_pack.py tests/knowledge/test_rerank_project.py -q`.

## Task 2: Provenance And Assumption Accounting

- [x] Write failing tests for cited fact, uncited assumption, contradiction, missing evidence, method revision, D example and evaluator finding serialization.
- [x] Implement a provenance manifest with typed refs and exact source/page revisions; never infer citation from filename or text similarity alone.
- [x] Require generated factual claims to resolve to an eligible source or published B page; render unresolved items under explicit `Assumption`/`Research gap` sections.
- [x] Redact secrets and untrusted instructions before prompt construction, and mark document content as data rather than executable instruction.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_generation_provenance.py tests/knowledge/test_prompts.py tests/knowledge/test_context_pack.py -q`.

## Task 3: PRD-to-SOP And Content Wiring

- [x] Write failing integration tests for a project-specific PRD-to-SOP and content task with distinct profiles, sources, methods and outputs; verify no cross-project context.
- [x] Extend generation request/response metadata to carry context ID/hash, selected refs, method revision, assumptions and `knowledge_context_used` without breaking legacy callers.
- [x] Replace template-only business sections with profile/method/evidence-driven sections. Templates may provide structure only.
- [x] Include accepted D outputs as style examples only, rejected outputs as regression constraints, and external research gaps as follow-up tasks.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/integration/test_growth_sop_context.py tests/orchestrator/test_wiki_methodology_bridge.py -q`.

## Task 4: Query And Research Feedback

- [x] Test that an unanswered context request creates a research candidate rather than a fabricated paragraph.
- [x] Expose selected/omitted/evidence coverage in the generation trace and preserve retrieval/index rebuild compatibility.
- [x] Ensure newly discovered links/attachments are sent to P2 capture before their content can be selected as factual context.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_service.py tests/knowledge/test_answer_generator.py tests/knowledge/test_api_ask_eval.py -q`.

## Task 5: Verification And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_context.py tests/knowledge/test_generation_provenance.py tests/integration/test_growth_sop_context.py tests/knowledge/test_context_pack.py tests/knowledge/test_prompts.py -q`.
- [x] Run `git diff --check` and `git status --short`.
- [x] Record context IDs, source cutoffs, omissions, model availability and one no-Vault/legacy compatibility result in the worklog.

## Acceptance Criteria

- Two projects with similarly named material generate distinct, profile-specific context packs and SOPs.
- Every generated factual section has resolvable A/B ancestry or is explicitly an assumption/research gap.
- D examples improve style/method selection without becoming evidence; rejected outputs produce constraints/regression cases.
- Context is bounded, reproducible, redacted, project-authorized and fully traceable.
- Legacy no-Vault generation remains functional and clearly reports that knowledge context was not used.

## Rollback Strategy

Disable growth-context selection and return to the existing context builder while retaining generated provenance records. Do not delete generated outputs, source/page refs or method revisions. Re-enable only after context hash/provenance compatibility is restored.

## Required Handoff

Provide P6/P7 with context-pack request/response JSON, selection order, cutoff/hash/idempotency rules, assumption/omission shapes, legacy behavior and generation provenance events. Include a real fixture result and exact verification commands.
