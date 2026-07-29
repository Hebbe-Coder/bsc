# O4 - Multimodal Evidence And Extraction Platform

## Goal

Add durable, tenant-safe records and local extraction pipelines for documents,
tables, images, Canvas, Excalidraw, media, URLs and Zotero references while
preserving original evidence unchanged.

**Depends on:** O3.
**May run in parallel with:** O5 after O3 route metadata is frozen.
**Blocks:** O6 and E1.

## Owned Surfaces

**Create:** media/extraction/reference domain contracts, migration, repository,
capture adapters, Celery workers, extractor capability registry and focused
fixtures/tests.
**Modify:** knowledge schema/repository, source/reference APIs, Docker and
Python dependency manifests only as required by local extraction.
**Do not modify:** raw source body/hash semantics, Artifact Graph persistence,
MCP transport framing, user attachment paths, or plugin code.

## Frozen Records And States

- `MediaAsset`: immutable original binary or external media reference with
  source ID, hash, MIME type, size, storage reference, rights and access state.
- `ExtractionArtifact`: versioned derivative with extractor/revision, content
  hash, status and safe error summary.
- `TableArtifact`: structured table schema, row count, units, content hash and
  review/publication state.
- `ReferenceLink`: typed project-scoped pointer to page, heading, block, table
  cell, image region, timestamp, citekey or URL anchor.
- Extraction states are `queued`, `running`, `complete`, `partial`, `failed`,
  `unsupported`, `restricted` and `needs_review`; a missing tool/model is
  explicitly unavailable and never reported as extracted.

## Input, Output, Permissions, And Redaction

- **Inputs:** an O3-authorized immutable source/media descriptor, the declared
  project route, extractor capability configuration and a bounded extraction
  request. The worker may read originals only through the governed storage
  reference, never through an arbitrary Vault path.
- **Outputs:** additive `MediaAsset`, `ExtractionArtifact`, `TableArtifact`
  and `ReferenceLink` records with hashes, extractor revision, capability and
  truthful status. Derivatives never overwrite originals or mutate source
  lifecycle records.
- **Access:** every asset, derivative and anchor is project-scoped; a target
  anchor must resolve source, target and authorization in the same project.
  Cross-project media reuse requires an explicit future sharing contract and
  is rejected in this phase.
- **Redaction:** read models, logs, tests and handoffs disclose IDs, hashes,
  MIME type, dimensions, capability state and safe error summaries only. They
  must not expose source bodies, OCR/transcript content, attachment paths,
  provider payloads or secrets.

## Test-First Tasks

1. First write focused failing contract, migration and authorization tests for hashes,
   idempotency, cross-project rejection, unsupported/restricted assets,
   re-extraction versioning, no raw-body API leak and retry classification.

## Implementation Tasks

2. Add SQLite/PostgreSQL-compatible additive tables, indexes and repository
   methods. Existing source records remain usable without a media row.
3. Install and health-check the full local stack in development and Compose:
   Tesseract for OCR, FFmpeg for media decoding, PDF tools, PyMuPDF/PDFPlumber,
   Pillow, OpenPyXL and a local Faster-Whisper adapter. Tool paths, model IDs
   and capabilities are environment configuration, never embedded secrets.
4. Implement extractors in this order: PDF text/page/table; scanned-PDF OCR;
   CSV/XLSX table/cell/unit; image metadata/OCR/regions; Canvas and Excalidraw
   elements; audio/video timestamps and transcription; normalized primary URL.
5. Preserve media originals separately from derivatives. Bounded worker jobs
   write only managed extraction storage and never replace a Vault file.
6. Add a Zotero adapter that maps exported citekey, DOI, item key,
   bibliography data, note reference and attachment provenance. Restricted
   attachment content is not copied by default.
7. Extend citation parsing/rendering and APIs for every typed anchor. A link is
   returned only if source, target and project authorization all resolve.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_media_assets.py tests/knowledge/test_extraction_artifacts.py tests/knowledge/test_reference_links.py tests/knowledge/test_multimodal_extractors.py -q
./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_evidence_api.py tests/integration/test_knowledge_extraction_celery.py -q
./.venv/Scripts/python.exe -m compileall -q app/knowledge
docker compose --profile full config
git diff --check
```

Fixtures cover text and scanned PDFs, OCR uncertainty, CSV/XLSX units, image
regions, Canvas, Excalidraw, local media, URL canonicalization, missing anchor,
restricted asset and cross-project access.

## Failure, Rollback, Worklog, And Handoff

Feature flags disable an extractor without deleting originals or derivatives;
derived records remain auditable and rebuildable. Hand O5 the metadata-only
read models, anchor schema, capability states, fixture IDs and pagination
bounds. Hand O6 installed tool/model versions and actual unavailable states.
Both handoffs include changed-file paths, migration IDs, exact test output,
feature flags, rollback point and an explicit list of real versus fixture-only
records. The shared worklog records each extractor command/job ID, capability
version, immutable record ID, status, safe failure summary, test exit result,
deviation and rollback state. It must preserve `unavailable`, `partial`, and
`restricted` states rather than collapsing them into completion.
