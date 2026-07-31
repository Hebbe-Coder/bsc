# PBOS Obsidian Plugin Planning Verification

Date: 2026-07-31
Current project: `proj_b8a285642094`

## Purpose

Verify that PBOS consumes only a bounded, project-scoped operational projection
of Obsidian bridge readiness. A Personal Execution Plan must advance the active
Mission rather than ask the user to configure an already declared route again.

## Scope And Historical Record

Earlier PBOS records contain historical observations made while `default` was
the active project. They remain audit history, but do not describe current
plugin destinations. An installed plugin can target only one active project
route at a time; its current scope is `proj_b8a285642094`.

This verification never reads or records plugin settings, plugin credentials,
raw Vault text, observed filenames, source bodies, or provider credentials.
Managed paths are represented only as project-relative routes.

## Current Active-Project Evidence

- Clipper, Xiaohongshu Importer, and Zotero are trusted, their declared
  destinations are ready, and each remains `awaiting_export` until the
  user-operated plugin produces a real file.
- Copilot is trusted with a declared output route and remains
  `awaiting_output`. No installed-plugin behavior has been inferred from that
  declaration.
- Real Claudian is trusted as an `agent_workspace` route and remains
  `awaiting_output` until its first registered output.
- The active project has a contextual PBOS plan under the managed
  project-relative `pbos/plans/` route. Its context contains governed
  references and route state, not Vault body content or plugin settings.

## Compiler Behavior

- `PBOSGovernedContextProvider` projects only
  `configured_awaiting_export`, `configured_awaiting_output`,
  `registered_output`, `captured`, or `not_ready`.
- D-layer `OutputAsset` registrations participate in the projection. A
  registered agent output is not misrepresented as an empty route.
- Declared, interactive, and agent-workspace routes qualify as planning-ready
  only when the existing trust and project-relative path checks succeed.
- A configured route is not evidence. It cannot become a captured source,
  completed output, accepted outcome, Capability, or Strategy Genome without
  its own lifecycle record.

## Citation Graph Behavior

- Compatible source metadata can create idempotent, source-scoped
  `ReferenceLink` edges for a normalized HTTP(S) URL, DOI, or citekey.
- Link projection reads metadata-only candidate fields. It has no Vault path,
  body reader, network client, or source mutation API.
- URL query tracking parameters are removed before identity calculation;
  malformed URLs, local paths, invalid DOIs, and invalid citekeys are rejected.
- Each link carries only a bounded identifier, relation, and provenance class.
  Repeated sync/backfill does not create duplicate graph edges.

## Verification Commands

Run from the BSC workspace after rebuilding the affected API, Worker, and Beat
images:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_contextual_compiler.py tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q
.\.venv\Scripts\python.exe -m pytest tests/knowledge/test_reference_projection.py tests/knowledge/test_wiki_sync.py tests/api/test_knowledge_evidence_api.py -q
npm run typecheck
npm run build
docker compose config --quiet
```

Protected runtime verification is limited to API readiness and a Celery `pong`.
It must not read raw source text, plugin settings, or secret values.

## Deployment Result

- The complete Python suite passed with `1564 passed, 14 skipped`; the complete
  frontend suite passed with `176 passed`.
- Production build, TypeScript check, Compose configuration, and `git diff
  --check` passed. ESLint completed with zero errors and existing repository
  warnings only.
- API, Worker, and Beat were rebuilt and restarted. API `/ready` returned
  `status=ok` with database and Redis dependencies healthy; Celery inspection
  returned one `pong`.
- Host and API-container SHA-256 values matched for `app/pbos/context.py`,
  `app/knowledge/reference_projection.py`, and `app/knowledge/prd_to_sop.py`.
  The deployed OpenAPI contract includes the authenticated,
  project-scoped `/outputs/generate-sop` route.

## Boundaries And Remaining Gates

- A real user plugin export or reviewed D-layer output is still required before
  the corresponding bridge can claim captured/registered delivery evidence.
- Explicit outcome acceptance and repeated comparable delivery evidence remain
  user-owned gates for personal-learning promotion.
- This work does not execute a Capability, publish externally, or claim a
  business result from a page render, container start, or configured route.

## Rollback

Revert the PBOS output-bridge projection and its regression test to restore the
previous compiler projection. Revert the metadata projector and its tests to
remove generated citation edges. Neither rollback deletes immutable source
records, prior plans, registered outputs, or user-authored Vault files.
