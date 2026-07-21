# P4 - Knowledge Quality, Graph, And Evaluation Gates Implementation Plan

**Goal:** Make Wiki publication evidence-backed, atomic, observable, and measurably non-regressing through deterministic lint, a separate Knowledge Graph, evaluation baselines, and proposal publication gates.

**Architecture:** P4 consumes P1-P3 proposals and files. It validates against immutable snapshots, rebuilds typed graph edges from published Markdown, runs deterministic quality/evaluation suites, then publishes all operations atomically or none. Existing `ArtifactGraphStore` is not imported or changed.

**Depends on:** P1, P2, P3
**Blocks:** P5-P8
**Do not modify:** raw source content, current Artifact Graph, existing PRD evaluator semantics, or MCP/API route surfaces.

## Owned Files

**Create:** `app/knowledge/wiki_lint.py`, `app/knowledge/knowledge_graph.py`, `app/knowledge/proposal_gate.py`, `app/knowledge/wiki_evaluator.py`, `tests/knowledge/test_wiki_lint.py`, `tests/knowledge/test_knowledge_graph.py`, `tests/knowledge/test_proposal_gate.py`, and `tests/knowledge/test_wiki_evaluator.py`.

**Modify:** `app/knowledge/wiki_repository.py`, `app/knowledge/vault.py`, `app/knowledge/wiki_service.py`, and only the optional integration seam in `app/evaluation/compiler_evaluator.py`.

## Publication Gate Contract

A proposal can become `published` only after project/actor/source/status/path/base-revision validation, resolvable citations, valid frontmatter/links/taxonomy, graph consistency, required project baseline evaluation, and successful atomic file/metadata commit. Missing baseline blocks publication. An administrator override requires a reason and audit event; it cannot erase findings.

## Task 1: Deterministic Wiki Lint

- [x] Add failing tests for frontmatter, source footnotes, missing source, dangling page link, missed overview/index/log update, forbidden path/page kind, orphan, stale page, and valid no-finding state.
- [x] Parse Markdown only; do not execute embedded content. Extract normalized frontmatter, links, footnotes, source/page references, and issue codes.
- [x] Implement `lint_project` and `lint_proposal` with severity, code, path, artifact reference, and remediation text.
- [x] Treat `wiki/log.md` as append-only ledger with specialized checks rather than ordinary frontmatter requirements.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_lint.py -q
```

## Task 2: Separate Knowledge Graph

- [x] Add tests for page links, citations, source supersession, proposal/page edges, stale detection, isolated traversal, and idempotent rebuild.
- [x] Persist only PRD edge types: `wiki_links_to`, `wiki_cites_source`, `proposal_changes_page`, `source_supersedes_source`, and `decision_uses_evidence`.
- [x] Rebuild affected edges from successfully published Markdown, not from untrusted model declarations.
- [x] Provide bounded project-scoped queries for nodes/edges, backlinks, uncited sources, stale/orphan pages, and health counts.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_knowledge_graph.py -q
```

## Task 3: Persisted Evaluation Baselines

- [x] Define project evaluation cases for retrieval expected sources, SOP required evidence/constraints, and content required citations/unsupported-claim policy.
- [x] Reuse existing retrieval and compiler-evaluator primitives only where their meanings match; add adapters rather than changing legacy score semantics.
- [x] Implement baseline/candidate comparison with score deltas, coverage, latency, skipped reason, and per-case findings.
- [x] Keep LLM deep review optional and mockable. Deterministic checks are the default publication gate.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_evaluator.py -q
```

## Task 4: Atomic Gate And Recovery

- [x] Add failing tests for successful multi-page publish, first/last operation failure, revision conflict, lint failure, evaluation regression, trusted auto-publication, audited manual override, and retry after transient write failure.
- [x] Implement a persisted state machine with `KnowledgeRun` and a snapshot of affected page hashes.
- [x] Use vault staging/recovery so failure leaves no partial Markdown, false graph revision, or processed-source transition.
- [x] On success persist page versions, citations, graph edges, proposal/run status, source processed status, and ledger update together; on failure keep sources eligible and findings inspectable.
- [x] Support rollback only as a compensating proposal using a prior page version, never as destructive filesystem restore.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_proposal_gate.py -q
```

## Task 5: Verification And Handoff

- [x] Run P1-P4 focused suites, existing knowledge/evaluation tests, Artifact Graph regression tests, and `git diff --check`.
- [x] Record gate thresholds, baseline policy, graph query limits, and override behavior in the worklog.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge -q
.\.venv\Scripts\python.exe -m pytest tests\evaluation tests\test_artifact_scope.py -q
git diff --check
```

## Acceptance, Rollback, Handoff

- Broken citations, links, hashes, or regressing evaluation cannot change published Wiki content.
- A reviewer can traverse page -> citation -> source -> proposal -> run using persisted data.
- Knowledge Graph is isolated by project and remains distinct from Artifact Graph.
- Rollback is feature disable or an audited compensating proposal; it never deletes raw evidence.
- Handoff P5-P7 with public publish/run/health/graph/evaluation contracts, event names, baseline fixtures, and auto-publication policy.
