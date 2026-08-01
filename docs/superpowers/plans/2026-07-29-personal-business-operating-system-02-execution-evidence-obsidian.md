# PBOS Plan 02: Execution Evidence And Obsidian

## Goal And Dependencies

Depends on Plan 01. Capture real local Git, build, test, BSC-runtime, and Vault
receipts into reviewable execution records. Obsidian is the personal memory
projection, not the PBOS lifecycle authority.

## Ownership And Prohibitions

- May change `app/pbos/capture.py`, `app/pbos/obsidian.py`, managed source/output
  sync integration, PBOS tasks, and focused PBOS/knowledge tests.
- May write BSC-owned files below `projects/<id>/pbos/` and
  `distillations/.../pbos/` with ownership markers.
- Must not alter raw sources, user L1/L2 notes, plugin credentials, or treat a
  file's existence as accepted evidence.

## Test-First Tasks

1. Reject traversal, secrets, and client-asserted verification from local/BSC
   capture payloads; retain only approved path metadata and server hashes.
2. Record the three-minute reflection: change, observed result, blocker,
   adjustment, attribution, and optional owner contribution.
3. Project L3 assets with Dataview-compatible frontmatter and preserve user
   edits as conflicts/review candidates rather than overwriting them.
4. Accept native plugin outputs only from trusted declared bridge paths;
   Copilot archives require a distinct, explicit review-draft import.

## Acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py -q
.\.venv\Scripts\python.exe -m pytest tests/knowledge/test_wiki_sync.py tests/knowledge/test_obsidian_output_sync.py tests/knowledge/test_copilot_transcript_import.py -q
```

Acceptance requires a captured receipt and reflection while keeping the result
non-learning-eligible until owner/mixed attribution and explicit review. Roll
back only the projection/task binding. Handoff includes payload contracts,
projection markers, trusted routes, and observed bridge state.
