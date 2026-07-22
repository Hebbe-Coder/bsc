# P4 - Method Evolution And Governed Skill Promotion Implementation Plan

**Goal:** Turn repeated, high-quality project workflows into reproducible C-layer methods with proposal, evaluation, approval, publication, execution selection, deprecation and rollback.

**Architecture:** Keep the current global Skill Registry and execution store intact. Add a project-scoped method domain that can reference a Skill manifest or prompt-only method. Method proposals are evaluated against actual P3 outputs and regression cases. Publication writes a versioned `methods/<slug>/SKILL.md` plus immutable database revision; privileged capability changes require administrator approval.

**Depends on:** P3.
**Blocks:** P5.
**PRD coverage:** FR-6; AC 7, 8, 12 and 17.

## Owned Files

**Create:** `app/knowledge/method_registry.py`, `app/knowledge/method_detector.py`, `app/knowledge/method_evaluator.py`, `app/knowledge/method_gate.py`, `tests/knowledge/test_method_registry.py`, `tests/knowledge/test_method_detector.py`, `tests/knowledge/test_method_evaluator.py`, and `tests/knowledge/test_method_gate.py`.

**Modify:** `app/skills/manifest.py`, `app/skills/registry.py`, `app/skills/execution_store.py`, and Skill execution selection only through documented project-method resolution hooks.

**Forbidden:** Installing arbitrary code, executing proposal shell commands, granting filesystem/network/MCP capability from content, changing global Skill discovery semantics, or publishing privileged methods under project-admin/automatic policy.

## Frozen Public Contracts

- A method proposal contains applicability, exclusions, inputs, outputs, ordered steps, evidence rules, failure handling, eval cases, supporting output/revision IDs, operation and rationale.
- Default promotion requires at least three comparable successful uses, average quality >= 85, groundedness >= 0.90, at least one accepted/reused output, and zero security/permission failures.
- Comparable use is determined by project, task family, input/output contract and method lineage; repeated retries of one run count once.
- Prompt-only method auto-publication requires project and global policy plus all gates.
- Code/hook/agent/filesystem-command/new-MCP-permission methods always require explicit system-admin approval.
- Published revision selection is explicit and reproducible; mutable draft files are never the execution authority.

## Task 1: Method Registry And Versioned Vault Files

- [x] Write failing tests for slug/path safety, candidate creation, revision immutability, optimistic publication, duplicate proposal, deprecation, supersession, rollback and project isolation.
- [x] Implement registry/repository operations over P1 contracts and atomically materialize published prompt-only methods to `methods/<slug>/SKILL.md` with `evals.md`.
- [x] Preserve previous revisions and create `method_supersedes_method` lineage rather than overwriting history.
- [x] Reject unmarked user file overwrite and binary/untrusted manifest payloads.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_method_registry.py tests/knowledge/test_growth_vault.py -q`.

## Task 2: Repeated Workflow Detection

- [x] Write failing tests for two-use/no-candidate, three comparable uses/candidate, retry collapse, mixed task families, rejected/corrected outputs and security-failure exclusion.
- [x] Implement a deterministic detector over P3 output, execution, feedback and evaluation records; persist supporting IDs and the detector revision.
- [x] Build proposals from observed steps and corrections while marking inferred content for review; never infer new capabilities from output text.
- [x] Allow user-created proposals without threshold but require the same validation/publication gates.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_method_detector.py -q`.

## Task 3: Method Evaluation And Regression Gate

- [x] Write failing tests for threshold calculations, groundedness, baseline comparison, negative cases, evaluator unavailable, schema mismatch and deterministic eval case replay.
- [x] Evaluate applicability, contract validity, evidence behavior, output quality, failure handling, permissions and regression cases by immutable revision.
- [x] Block a revision that lowers the published baseline or fails a previously passing security/correction case.
- [x] Persist evaluation cases/results/model revision/latency and make unavailable evaluation non-passing.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_method_evaluator.py -q`.

## Task 4: Approval, Publication And Execution Resolution

- [x] Write failing role/policy tests for project-admin proposal, gated prompt-only publish, global auto-policy, privileged method system-admin approval and denied capability escalation.
- [x] Implement `MethodGate` with durable actor, policy revisions, findings, approval and rollback target.
- [x] Add a resolver that returns the exact published method revision and manifest to generation/execution; it may not fall back to a mutable draft.
- [x] Keep current global Skill Registry responses compatible and expose project methods through an additive namespace/adapter.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_method_gate.py tests/test_skill_registry.py tests/test_skill_execution_store.py -q`.

## Task 5: Regression And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_method_registry.py tests/knowledge/test_method_detector.py tests/knowledge/test_method_evaluator.py tests/knowledge/test_method_gate.py tests/knowledge/test_feedback_router.py tests/test_skill_registry.py tests/test_skill_execution_store.py -q`.
- [x] Run `git diff --check` and `git status --short`.
- [x] Record one threshold-qualified fixture, one regression-blocked revision and one denied privileged proposal in the worklog.

## Acceptance Criteria

- Fewer than three comparable successful uses cannot trigger default automatic promotion; retry deliveries do not inflate use count.
- A qualifying prompt-only proposal still passes validation, evaluation, project policy and global policy before publication.
- Privileged capability proposals require explicit system-admin approval regardless of score or project setting.
- Published revisions are reproducible, immutable and rollback-capable, and execution records the exact revision used.
- Existing global Skill registration/execution contracts continue to pass.

## Rollback Strategy

Disable method detection and project-method resolution, leaving the global Skill Registry active. Deprecate or roll back a published method through a compensating revision; never delete prior revisions, evaluations, outputs or approvals.

## Required Handoff

Provide P5/P7/P8 with method list/read/resolve contracts, proposal/evaluation/gate schemas, policy/approval rules, exact revision provenance and method performance query shape. Record compatibility and rollback evidence in the shared worklog.
