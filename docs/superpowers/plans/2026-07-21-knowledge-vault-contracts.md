# P1 - Knowledge Vault Contracts Implementation Plan

**Goal:** Establish the project-isolated Obsidian vault boundary, durable knowledge domain contracts, additive schema, and repository services on which every later LLM Wiki plan depends.

**Architecture:** The configured Obsidian project directory is the source-of-truth filesystem for raw sources and published Markdown. The existing knowledge database stores only metadata, proposals, authorization scope, and audit data. All later services use a canonical vault service and typed contracts; none construct paths or issue raw knowledge SQL directly.

**Depends on:** none
**Blocks:** P2-P8
**Do not modify:** `app/artifacts/**`, existing Artifact Graph contracts, existing `/knowledge` routes, or raw user Vault content.

## Owned Files

**Create:** `app/knowledge/wiki_contracts.py`, `app/knowledge/vault.py`, `app/knowledge/wiki_repository.py`, `app/knowledge/wiki_service.py`, `tests/knowledge/test_wiki_contracts.py`, `tests/knowledge/test_vault_service.py`, `tests/knowledge/test_wiki_repository.py`, and `tests/knowledge/test_wiki_schema.py`.

**Modify:** `app/knowledge/schema.py`, `app/core/config.py`, `app/config_types.py`, and only shared repository helpers required by `WikiRepository`.

## Frozen Public Contract

- `SourceStatus`: `captured`, `validated`, `eligible`, `processed`, `rejected`, `superseded`.
- `ProposalStatus`: `draft`, `validating`, `approved`, `published`, `rejected`, `failed`, `superseded`.
- `RunStatus`: `queued`, `running`, `completed`, `failed`, `cancelled`, `unavailable`.
- `WikiOperation`: `create`, `replace`, `append`, `archive`, or `move`; it contains a normalized relative path and never accepts a shell command or absolute path.
- Pydantic v2 models: `VaultMapping`, `SourceRecord`, `WikiPage`, `WikiProposal`, `CitationLink`, `KnowledgeRun`, `KnowledgeSchedule`, `WeeklyDistillation`, `KnowledgeGraphEdge`, and API-safe result models.
- `VaultService.resolve(project_id, relative_path)` validates mapping, canonical path, and root containment. `write_published_page` requires expected hash/version when replacing an existing page.

## Task 1: Contracts First

- [ ] Add failing tests for enum values, required project IDs, ISO timestamps, non-empty IDs, relative-path normalization, duplicate operation IDs, terminal status behavior, and proposal source requirements.
- [ ] Implement immutable Pydantic contracts in `wiki_contracts.py`; serialize through `model_dump` and preserve internal-only fields separately from public responses.
- [ ] Reject empty paths, `..` traversal, absolute paths, NUL bytes, unsupported page operations, and proposals without source references unless explicitly marked user-authored/manual.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_contracts.py -q
```

## Task 2: Vault Boundary

- [ ] Add optional `OBSIDIAN_VAULT_ROOT` configuration. A mapping cannot be created without it; existing BSC knowledge operations still work while it is unset.
- [ ] Implement canonical resolver behavior using `Path.resolve(strict=False)`, root containment validation, and symlink escape rejection.
- [ ] Implement idempotent bootstrap of only `AGENTS.md`, `wiki/overview.md`, `wiki/index.md`, `wiki/log.md`, and required directories. Never overwrite a user-created file.
- [ ] Implement UTF-8 read/list operations and atomic temp-file-plus-replace writes for generated Wiki pages. Automated writes to `raw/` and `inbox/` must fail.
- [ ] Return typed errors for unconfigured/missing roots, missing mapping, path traversal, version conflict, and encoding failures; never hide them as empty state.

Tests cover nested mapping, traversal, absolute path, escaping symlink, project isolation, failed write recovery, repeat bootstrap, and rejection of raw-source writes.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_vault_service.py -q
```

## Task 3: Additive Schema And Repository

- [ ] Add portable idempotent DDL and indexes for `knowledge_vaults`, `knowledge_sources`, `knowledge_wiki_pages`, `knowledge_proposals`, `knowledge_proposal_operations`, `knowledge_citations`, `knowledge_runs`, `knowledge_schedules`, `knowledge_distillations`, `knowledge_graph_edges`, and `knowledge_eval_runs`.
- [ ] Persist JSON with existing repository helpers and preserve hash/version columns across SQLite and PostgreSQL.
- [ ] Implement parameterized, project-scoped repository methods for mappings, source/page records, proposal/runs, schedules, graph edges, and history reads.
- [ ] Enforce expected hash/version inside a transaction; return a conflict result rather than overwriting a newer user edit.

Tests prove idempotent initialization, required SQLite objects, project isolation, revision conflict, and immutable source rows.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_schema.py tests\knowledge\test_wiki_repository.py -q
```

## Task 4: Narrow Bootstrap Facade

- [ ] Implement `WikiService.initialize_project(project_id, actor)` to validate mapping, create only missing starter files, register page metadata, and record an auditable run.
- [ ] Expose read-only `get_workspace_status`, `list_pages`, `read_page`, and `list_runs` for later API/MCP/UI plans.
- [ ] Index generated Wiki Markdown through the existing `KnowledgeService.ingest_text` with explicit Wiki `doc_format`; content remains authoritative on disk and the index stays rebuildable.
- [ ] Do not add routes, MCP tools, filesystem watcher, LLM invocation, or scheduler behavior in P1.

## Task 5: Verify And Handoff

- [ ] Run focused tests, existing knowledge tests, and `git diff --check`.
- [ ] Record configuration names, exported contracts, table/index names, and any dialect limitation in the worklog.
- [ ] Commit only P1-owned files.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge -q
.\.venv\Scripts\python.exe -m pytest tests\test_repositories.py -q
git diff --check
```

## Acceptance, Rollback, Handoff

- Invalid mappings cannot reach the filesystem; valid projects cannot read each other.
- Existing retrieval works without vault configuration and all new schema is additive.
- Rollback is a feature disable/code revert and never deletes Obsidian files or existing knowledge tables.
- Handoff P2-P4 with public contracts, repository signatures, starter contents, config behavior, and test results.
