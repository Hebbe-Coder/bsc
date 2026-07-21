# P2 - Knowledge Source Capture And Horizon Implementation Plan

**Goal:** Turn Obsidian imports, user annotations, existing BSC outputs, and Horizon intelligence into immutable, project-scoped `SourceRecord` entries that can safely become eligible for Wiki compilation.

**Architecture:** Use deterministic vault scanning as the baseline sync mechanism, with optional watcher acceleration only after scanning is correct. Normalize every input into P1's source lifecycle, preserve source bytes/text and hash, and project it through the existing `KnowledgeService` only as a derived retrieval document. Treat Horizon as a versioned HTTP/MCP sidecar adapter, never as direct database authority.

**Depends on:** P1
**Blocks:** P3-P8
**Do not modify:** published `wiki/` pages, P1 contracts/schema, existing Horizon archive, Artifact Graph semantics, or scheduler configuration.

## Owned Files

**Create:** `app/knowledge/source_registry.py`, `app/knowledge/obsidian_sync.py`, `app/knowledge/horizon_client.py`, `app/knowledge/source_policy.py`, `tests/knowledge/test_source_registry.py`, `tests/knowledge/test_obsidian_sync.py`, `tests/knowledge/test_horizon_client.py`, and `tests/knowledge/test_source_policy.py`.

**Modify:** `app/knowledge/wiki_service.py`, `app/core/config.py`, `app/config_types.py`, and only the documented `KnowledgeService` metadata projection seam if source formats need it.

## Frozen Source Semantics

- Supported `source_type`: `obsidian_file`, `manual_upload`, `web_clip`, `horizon_signal`, `bsc_artifact`, `user_annotation`.
- `origin` identifies an external URL, original file, Horizon run/stage, or BSC artifact revision and is never rewritten during a source update.
- Changed content creates a new source record/version and a `supersedes` relation. It does not mutate historical content or hash.
- User annotations are stored as curation. They can prioritize synthesis and retrieval but cannot independently satisfy a factual citation requirement.
- Eligibility requires valid project mapping, successful extraction, policy acceptance, and no duplicate active source with the same canonical origin/hash.

## Task 1: Source Registry And Idempotency

- [x] Add failing tests for capture, same-content skip, changed-content supersession, rejected-source retention, project isolation, and retrieval-index projection.
- [x] Implement `SourceRegistry.capture` and lifecycle transition guards. Terminal source states cannot silently return to eligible.
- [x] Persist content hash, source type, vault path/origin, trust level, extraction result, policy decision, and lineage before calling any index backend.
- [x] Project text through `KnowledgeService.ingest_text` with source-specific `doc_format`; keep the registry, not the index, as provenance authority.
- [x] On index failure retain the source and record the projection failure; do not erase extracted evidence.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_source_registry.py -q
```

## Task 2: Deterministic Obsidian Sync

- [x] Implement `scan_project(project_id)` to list allowed source/import paths, calculate hashes, classify new/changed/deleted files, and return a typed report.
- [x] Exclude `.bsc/`, editor lock files, temporary files, and published `wiki/` paths. Wiki page changes are page revisions, not raw evidence imports.
- [x] Preserve vault-relative path and extension; never move, normalize in place, or replace a user file.
- [x] Support Markdown/text/structured data and current BSC document extraction paths; retain unsupported formats with explicit rejection/extraction status.
- [x] Track write-origin/hashes so BSC generated page writes do not return through the external-source scan.

Tests use temporary vaults and cover nested imports, repeated scans, deletion/supersession, cross-project mappings, malformed UTF-8, excluded paths, and a user edit after processing.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_obsidian_sync.py -q
```

## Task 3: Horizon Sidecar Adapter

- [x] Define `HORIZON_API_BASE_URL`, optional `HORIZON_API_KEY`, timeout, enabled flag, and per-project allowed source configuration.
- [x] Implement a client for Horizon public staged/full-pipeline interfaces. Validate response shape and map run IDs, URLs, timestamps, summaries, scores, source names, and raw payload hash into `horizon_signal` records.
- [x] Reuse BSC-safe HTTP principles: reject non-HTTP(S), private/loopback targets, malformed/oversized payload references, and redact credentials from errors.
- [x] Preserve Horizon run/stage references and score/filter outputs as evidence metadata. A Horizon score must not become a BSC factual truth score.
- [x] Make the client injectable for offline tests; importing it must make no network call.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_horizon_client.py -q
```

## Task 4: Trust And Eligibility Policy

- [x] Implement a pure policy evaluator using source allowlist, source type, freshness, explicit user curation, extraction quality, duplicate result, and project relevance.
- [x] Return structured reasons/evidence, not only a Boolean.
- [x] Default unknown external feeds to `validated`, not `eligible`; known trusted sources may become eligible automatically under project policy.
- [x] Add service-level manual reprocess/reject transitions for P6. Do not add routes or scheduling here.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_source_policy.py -q
```

## Task 5: Verification And Handoff

- [x] Run P1 and P2 focused tests plus existing knowledge-ingest tests.
- [x] Record extraction limitations and Horizon contract assumptions in the worklog.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_contracts.py tests\knowledge\test_vault_service.py tests\knowledge\test_source_registry.py tests\knowledge\test_obsidian_sync.py tests\knowledge\test_horizon_client.py tests\knowledge\test_source_policy.py -q
git diff --check
```

## Acceptance, Rollback, Handoff

- Repeated scan or repeated Horizon response cannot create duplicate active sources.
- No capture path writes raw content or publishes a Wiki page.
- Source status, policy reasons, and lineage remain visible after an extraction/index failure.
- Rollback disables Horizon/sync features but retains evidence and never deletes Vault files.
- Handoff P3/P4 with registry API, eligibility policy, normalized Horizon fixture, and trusted/rejected/changed/annotated source test data.
