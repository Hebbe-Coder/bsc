# P1 - A/B/C/D Contracts, Project Profile And Vault Implementation Plan

**Goal:** Establish the additive, project-scoped persistence and filesystem contracts required by the A/B/C/D growth loop without changing the completed Wiki, orchestration, MCP, Skill, or Artifact Graph semantics.

**Architecture:** Extend the existing `WikiRepository`/schema and safe `VaultResolver` patterns. The database owns profile revisions, C/D lifecycle, feedback, evaluation and authoritative lineage; the Vault stores readable/project files. New tables are additive and idempotent. Existing projects resolve compatible profile defaults without rewriting `AGENTS.md`.

**Depends on:** Completed 2026-07-21 P1-P8 baseline.
**Blocks:** P2-P9.
**PRD coverage:** FR-1 foundations, FR-8 foundations, permissions/safety, AC 6, 17 and 20.

## Owned Files

**Create:** `app/knowledge/growth_contracts.py`, `app/knowledge/growth_repository.py`, `app/knowledge/project_profile.py`, `tests/knowledge/test_growth_contracts.py`, `tests/knowledge/test_growth_repository.py`, `tests/knowledge/test_project_profile.py`, and `tests/knowledge/test_growth_vault.py`.

**Modify:** `app/knowledge/schema.py`, `app/knowledge/vault.py`, `app/knowledge/wiki_repository.py`, `app/knowledge/wiki_rules.py`, `app/knowledge/wiki_bootstrap.py`, and migration/startup registration only where needed for additive initialization.

**Forbidden:** `app/artifacts/**` semantics, orchestrator lifecycle/state transitions, MCP transport, existing Wiki proposal/publication behavior, user files below `D:\bsc`, destructive migrations, and automatic legacy output backfill.

## Frozen Public Contracts

- `ProjectKnowledgeProfile`: project ID, revision, research domains, user role, primary output types, target audiences, preferred channels, language, content voice, evidence threshold, automatic publication policy, method promotion policy, timestamps and actor.
- `SourceTriage`: source ID, project/profile revision, five component scores, priority, reliability result, disposition, reasons, evaluator revision and timestamps.
- `MethodAsset`, `MethodRevision`, `MethodProposal`, `OutputAsset`, `OutputFeedback`, `OutputEvaluation`, and `KnowledgeLineageEdge` use the states and relations frozen in the execution index.
- Every repository method requires an explicit `project_id`; an ID lookup also includes project scope.
- Optimistic publication uses expected revision/version and deterministic idempotency keys.
- Vault paths are canonical project-relative paths. Binary content is never passed through text decoding.

## Task 1: Contract Tests And Typed Models

- [x] Write failing tests for required fields, enum/state validation, immutable revision identity, normalized IDs, forbidden relation names, bounded metadata and secret-bearing fields.
- [x] Implement Pydantic/dataclass contracts with JSON-safe serialization and UTC timestamps consistent with existing Wiki contracts.
- [x] Define typed transition maps for method, output, feedback processing and proposal status; reject skips and terminal reopening.
- [x] Define deterministic keys for triage, output registration, evaluation, feedback, proposal and lineage edges.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_contracts.py -q`.

## Task 2: Additive Schema And Repository Isolation

- [x] Write failing SQLite migration/reopen tests for all new entities, foreign keys/indexes, unique idempotency keys, pagination ordering and project-scoped lookup.
- [x] Add idempotent tables and indexes without altering or dropping existing Wiki, Skill, orchestration or Artifact Graph tables.
- [x] Implement repository create/get/list/transition operations with bounded pages and transaction boundaries.
- [x] Reject cross-project endpoint relations, missing endpoints, duplicate edges and direct/indirect synthetic ancestry cycles.
- [x] Add PostgreSQL-compatible SQL/schema coverage using the repository's current backend abstraction; defer live container proof to P9.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_repository.py tests/knowledge/test_schema_migration.py tests/knowledge/test_schema_production.py -q`.

## Task 3: Project Profile And Rules Compatibility

- [x] Write failing tests for defaults, explicit profile revisions, concurrent update conflict, actor/audit metadata, missing optional `AGENTS.md` fields and project isolation.
- [x] Implement profile read/update as immutable revisions; persist the active revision pointer transactionally.
- [x] Extend project-rule parsing additively so absent fields use documented defaults and existing `AGENTS.md` content is not rewritten.
- [x] Expose a service-level configuration status for profile, Vault, scheduler, Horizon, model and automation without inferring availability from desired configuration.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_project_profile.py tests/knowledge/test_wiki_rules.py -q`.

## Task 4: Vault Layout And Binary-Safe Publication

- [x] Write failing filesystem tests for the PRD layout, no-overwrite bootstrap, binary preservation, atomic managed text replacement, path traversal, absolute path, symlink escape and interrupted write cleanup.
- [x] Extend safe bootstrap for `methods/`, `outputs/`, `reviews/` and `distillations/每周蒸馏/` while preserving all existing files.
- [x] Add byte-oriented copy/hash/materialization helpers for binary output and source descriptors; do not decode unknown MIME types.
- [x] Mark managed files with ownership metadata or manifest entries so later automation can distinguish generated from user-authored files.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_vault.py tests/knowledge/test_vault.py tests/knowledge/test_wiki_bootstrap.py -q`.

## Task 5: Security And Regression Handoff

- [x] Test project authorization at every new repository/file operation, secret redaction, bounded metadata, invalid transition and untrusted-content handling.
- [x] Run the full existing Wiki contract/schema/Vault regression set and confirm no Artifact Graph schema or lifecycle changed.
- [x] Append exact schema names, public symbols, migration results and rollback evidence to the worklog.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_contracts.py tests/knowledge/test_growth_repository.py tests/knowledge/test_project_profile.py tests/knowledge/test_growth_vault.py tests/knowledge/test_wiki_contracts.py tests/knowledge/test_wiki_schema.py tests/knowledge/test_vault.py -q`.
- [x] Run `git diff --check` and `git status --short`.

## Acceptance Criteria

- Existing databases reopen after additive migration; existing projects behave unchanged with profile defaults.
- C/D/feedback/evaluation/lineage records are durable, revisioned, paginated and project-isolated on SQLite.
- Cross-project and cyclic lineage cannot be persisted even through direct repository use.
- Bootstrap and managed publication preserve unrelated text and binary files and refuse path escape.
- No user Vault data or runtime database is modified by test setup; tests use temporary fixtures.

## Rollback Strategy

Disable the growth feature flag and stop writing new records. Revert service/model code while retaining additive tables and Vault directories. Do not delete records or user content. A later cleanup migration requires separate approval and backup/restore proof.

## Required Handoff

Provide P2-P8 with import paths, entity JSON examples, transition maps, repository transaction/idempotency semantics, profile default/revision behavior, Vault managed-file rules, migration test results and the exact list of forbidden cross-project operations. Record all commands and results in the shared worklog.
