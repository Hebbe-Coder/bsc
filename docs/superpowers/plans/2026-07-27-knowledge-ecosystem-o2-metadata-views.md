# O2 - Canonical Metadata And Knowledge Views

## Goal

Create one project-safe metadata vocabulary and managed Obsidian views without
creating a second writable source of lifecycle truth.

**Depends on:** O1.
**Blocks:** O3-O6.

## Owned Surfaces

**Create:** metadata registry/renderer, managed-index tests and managed index
notes.
**Modify:** project `AGENTS.md`, Metadata Menu settings, source-sync exclusion
logic and the ecosystem worklog.
**Do not modify:** plugin executable code, immutable source bodies, published
Wiki content, Artifact Graph semantics, or user-authored notes.

## Frozen Metadata Contract

- Identity: `bsc_id`, `project_id`, `asset_kind`, `managed_by_bsc`.
- Provenance: `source_url`, `canonical_url`, `citation_key`, `source_date`,
  `captured_at`.
- Quality: `trust_level`, `review_status`, `freshness`, `extraction_status`,
  `feedback_status`.
- Relations: `related_sources`, `related_pages`, `table_refs`, `image_refs`,
  `method_refs`, `output_refs`.

The BSC-controlled identity, hash, capture and managed fields are projection
metadata. Editing a visible note property never changes a persisted BSC
lifecycle or authorization state.

## Input, Output, Permissions, And Redaction

- **Inputs:** O1's redacted boundary handoff, the declared project root, and
  BSC-owned lifecycle metadata. User-authored note bodies and plugin code are
  outside this plan's input boundary.
- **Outputs:** a typed field registry, deterministic frontmatter projection,
  managed index revision, and source-capture exclusion result. Each generated
  row links only to an authorized BSC or Obsidian target.
- **Access:** generation and reads are scoped to one authorized project. A
  visible property cannot grant access, alter BSC lifecycle, or make a
  cross-project record discoverable.
- **Redaction:** registry fixtures, Dataview/Bases queries, logs, and handoff
  may contain field names, IDs, state and safe counts only; never source body,
  local secret, credential, or hidden plugin configuration.

## Test-First Tasks

1. First write focused failing tests for allowed field names/types, secret rejection,
   deterministic frontmatter rendering, project ownership, and exclusion of
   generated indexes from source capture.

## Implementation Tasks

2. Add the typed registry and renderer. It emits only the frozen vocabulary and
   records managed index ownership/revision without raw source bodies.
3. Update `AGENTS.md` with the A/B/C/D path map, field ownership, citation
   anchor rules, and the rule that generated indexes are navigation only.
4. Configure Metadata Menu with Input, Select, Date, MultiFile and Boolean
   fields. Select options cover only documented states; no field auto-inserts
   into user notes.
5. Generate a managed `Knowledge Index` folder with Dataview views for Inbox,
   review queue, published Wiki, method candidates, registered outputs,
   feedback debt, stale references and extraction failures. Provide an empty
   state and BSC/Obsidian record link for every row.
6. Configure optional Bases views with the same frontmatter filters. Bases may
   not encode permissions, lifecycle transitions, or hidden aggregation logic.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_obsidian_metadata.py tests/knowledge/test_obsidian_index_views.py tests/knowledge/test_wiki_sync.py -q
git diff --check
```

Open the managed views with both an empty fixture and a populated fixture. A
source sync must report generated index files as skipped, never captured.

## Failure, Rollback, Worklog, And Handoff

Remove only files carrying the managed-index marker and restore the Metadata
Menu setting backup. Hand O3 the registry revision, field JSON example,
generated-root exclusion rule, test fixtures, exact acceptance output, and
known empty/unavailable states. Append actual commands, exit results, managed
index revision, conflicts, skipped paths, deviations, and rollback action to
the shared worklog. A generated view or fixture never counts as a real export.
