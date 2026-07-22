# P2 - Evidence Capture, Triage And Integrations Implementation Plan

**Goal:** Turn multi-channel material into immutable, project-scoped A-layer evidence and produce reviewable five-dimensional routing decisions without allowing Horizon, Feishu, plugins, or model output to become knowledge authority.

**Architecture:** Reuse `WikiSourceCapture`, Obsidian sync, Horizon run-store/client/import and source lifecycle. Add thin capture adapters that normalize into `SourceRecord`, then run a profile-revision-bound `SourceTriageService`. Reliability remains a hard eligibility gate independent of the weighted priority score.

**Depends on:** P1.
**Blocks:** P3 and P5.
**PRD coverage:** FR-2, FR-3, FR-5, FR-12, FR-13; AC 1-4, 16 and 19.

## Owned Files

**Create:** `app/knowledge/source_triage.py`, `app/knowledge/capture_adapters.py`, `app/knowledge/feishu_import.py`, `tests/knowledge/test_source_triage.py`, `tests/knowledge/test_capture_adapters.py`, and `tests/knowledge/test_feishu_import.py`.

**Modify:** `app/knowledge/wiki_source_capture.py`, `app/knowledge/wiki_sync.py`, `app/knowledge/horizon_client.py`, `app/knowledge/horizon_import.py`, `app/knowledge/horizon_run_store.py`, and source-capture configuration only for frozen adapter contracts.

**Forbidden:** Direct B Wiki publication, direct C/D creation, rewriting source bytes, storing credentials in source/run content, scraping undocumented Feishu internals, changing Horizon's repository/archive, or requiring optional Obsidian plugins.

## Frozen Public Contracts

- All adapters return a normalized capture request containing project, source kind, original URI/path, source revision/time, capture time, MIME, byte hash, extraction text/state, attachment descriptors, annotations and external provenance.
- Deduplication is by project plus immutable content identity; same bytes in another project remain independently authorized records.
- User notes are marked `curated_opinion`; they are never represented as external fact.
- Priority is `relevance * .30 + value * .25 + freshness * .15 + outputability * .15 + connectedness * .15` on a 0-100 scale.
- Reliability is a separate pass/fail result. A failed source cannot become `eligible` regardless of priority.
- Horizon run and stage, and Feishu document/revision/source URL, remain queryable provenance.

## Task 1: Unified Capture Adapter Contract

- [x] Write failing tests for upload, browser clip, Obsidian import, Feishu document/minutes, Horizon staged artifact and adopted BSC artifact normalization.
- [x] Test original bytes/URI, hash, MIME, source/capture times, extractor state, attachment metadata, opinion marking and secret redaction.
- [x] Implement allowlisted adapter kinds and route every result through the existing immutable source capture service.
- [x] Refuse missing project ownership for adopted BSC artifacts and do not auto-backfill global legacy files.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_capture_adapters.py tests/knowledge/test_wiki_source_capture.py -q`.

## Task 2: Five-Dimensional Triage

- [x] Write failing tests for exact weighting, boundary scores 39/40/59/60/79/80, reliability failure, research-topic routing, profile/evaluator revisions and deterministic rerun.
- [x] Implement `SourceTriageService` using explicit component scores and persisted reasons; do not store only a single opaque model score.
- [x] Permit deterministic policy/rule evaluators and an optional model evaluator behind one typed interface; persist unavailable/model revision/latency truthfully.
- [x] Transition validated sources to eligible only for allowed dispositions plus reliability pass. Preserve rejected/superseded lifecycle rules.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_source_triage.py tests/knowledge/test_growth_repository.py -q`.

## Task 3: Horizon Incremental Import

- [x] Extend failing tests for newest-unimported staged artifact, `enriched` preference, `filtered` fallback, imported-run exclusion, malformed artifact, network/auth/rate-limit/config errors and retryability.
- [x] Map Horizon scoring/provenance into adapter metadata but compute BSC triage independently under the active project profile.
- [x] Keep source capture idempotent across producer retry, Celery retry and manual re-import.
- [x] Confirm Horizon can create only A records and cannot call Wiki publication or mark a source processed.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_horizon_client.py tests/knowledge/test_horizon_import.py tests/knowledge/test_horizon_run_store.py -q`.

## Task 4: Feishu And Obsidian Provenance

- [x] Write failing tests for Feishu document/minutes revision provenance, attachment descriptors, expired authorization, missing attachment access, redacted token/error and duplicate revision.
- [x] Implement an explicit-import adapter around authorized `lark-cli`/exported payloads; no background access is claimed when credentials are absent.
- [x] Extend Obsidian import detection to ignore all managed project roots, `distillations/`, `.bsc/`, methods and outputs unless the user explicitly adopts a file through the appropriate asset flow.
- [x] Verify optional plugin-created files pass canonical path, project, MIME, source trust and immutable capture controls.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_feishu_import.py tests/knowledge/test_wiki_sync.py -q`.

## Task 5: Research And Health Routing

- [x] Test that high-value unanswered questions become `research_topic` records/tasks and that external research results return through normal A capture.
- [x] Extend health reporting for uncited eligible evidence, unresolved source contradictions and research candidates without silently changing Wiki pages.
- [x] Create typed proposal/research-task recommendations only; preserve the existing Wiki proposal gate.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_knowledge_health.py tests/knowledge/test_knowledge_graph.py -q`.

## Task 6: Regression And Handoff

- [x] Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_capture_adapters.py tests/knowledge/test_source_triage.py tests/knowledge/test_feishu_import.py tests/knowledge/test_horizon_client.py tests/knowledge/test_horizon_import.py tests/knowledge/test_horizon_run_store.py tests/knowledge/test_wiki_source_capture.py tests/knowledge/test_wiki_sync.py -q`.
- [x] Run `git diff --check` and `git status --short`.
- [x] Record live integration as unavailable unless a real authorized Feishu/Horizon call was executed and captured in the worklog.

## Acceptance Criteria

- Each supported channel creates one immutable, deduplicated, project-scoped source with complete provenance and no stored secret.
- Triage component scores, reasons, reliability, profile revision and evaluator revision are reproducible and reviewable.
- An unreliable score-100 source remains ineligible; contradictory sources remain explicit rather than synthesized away.
- Missing OCR, transcription, Horizon or Feishu capability preserves capture and reports `extraction_unavailable` or integration unavailability truthfully.
- Existing Obsidian and Horizon capture regressions pass unchanged.

## Rollback Strategy

Disable individual adapters and the triage worker while retaining source and triage records. Resume existing manual/Obsidian/Horizon capture paths under their prior behavior. Never delete imported source versions; supersede an incorrect record through the lifecycle contract.

## Required Handoff

Provide P3/P5 with normalized source examples, eligibility query API, disposition/reliability semantics, active profile/evaluator revision handling, research-topic records, integration availability contract, and focused test results. Append exact live-versus-fixture evidence to the worklog.
