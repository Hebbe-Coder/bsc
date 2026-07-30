# O3 - Plugin Route, Trust, And Capture Proof

## Goal

Turn enabled Obsidian plugins into explicitly declared, trusted and observable
project routes while keeping capture status truthful.

**Depends on:** O2.
**Blocks:** O4-O6.

## Owned Surfaces

**Create:** plugin route validation/status tests and route configuration matrix.
**Modify:** `bsc-plugins.json`, its trust store, plugin-setting adapters and
managed index links.
**Do not modify:** third-party plugin source code, user source content after
export, BSC source bodies, output evaluation rules, or Local REST credentials.

## Route Contract

| Producer | Project route | Adapter | Initial state |
| --- | --- | --- | --- |
| Clipper | `00_Inbox/web-clipper/` | filesystem drop | verified route |
| Xiaohongshu Importer | `00_Inbox/social/` | filesystem drop | verified route |
| Docxer | `01_Sources/docxer/` | filesystem drop | awaiting operator export |
| Obsidian Importer | `01_Sources/importer/` | filesystem drop | awaiting operator export |
| Zotero Integration | `01_Sources/zotero/` | filesystem drop | awaiting export |
| Excalidraw | `03_Projects/active/maps/` | filesystem context | awaiting export |
| Claudian | `04_Outputs/claudian/` | filesystem output | awaiting registered output |

## Input, Output, Permissions, And Redaction

- **Inputs:** the O2 field-registry revision, a user-visible plugin export
  destination, a project-scoped manifest/trust record, and optionally an
  exported file. Plugin source code and unrelated plugin settings are never
  inputs.
- **Outputs:** route status, immutable source/output provenance and bounded
  metadata only. The route output must name its project, producer, adapter,
  captured file hash or registered-output ID, and its honest state.
- **Access:** a route resolves only beneath its declared project root. A
  project key or project user cannot enumerate, read or register files for a
  different project; filesystem traversal, symlinks outside the route and
  managed-index paths are rejected.
- **Redaction:** tests, API payloads and handoffs contain no file body,
  credential, Local REST token, browser session, third-party account ID or
  plugin configuration secret. A missing export remains `awaiting_export`.

## Test-First Tasks

1. First write focused failing tests for duplicate plugin IDs, path escape, undeclared root,
   trust invalidation after route change, forbidden managed-index capture,
   Zotero metadata mapping, Excalidraw project association and output/source
   separation.

## Implementation Tasks

2. Extend the manifest and runtime-setting probes to support Zotero and
   Excalidraw without reading plugin code or unrelated configuration values.
3. Configure declared output folders through supported plugin settings. For
   interactive Importer and Docxer destinations, retain the user-visible
   destination selection and report `awaiting_export` until a file exists.
   Claudian is an agent workspace, not a chat-transcript exporter: it must
   write a durable file to its declared `04_Outputs/claudian/` path under the
   project `AGENTS.md` output contract. Its attachment `mediaFolder` is never
   evidence that a result was written.
4. Require a source record with immutable hash and plugin provenance before
   changing a source bridge to `captured`; require OutputRegistry registration
   before a Claudian bridge becomes `registered`.
5. Preserve original URL, canonical URL, platform/item key, attachment
   reference and capture limitations. Social and Horizon material remain leads
   until separately assessed.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_sync.py tests/knowledge/test_obsidian_output_sync.py tests/knowledge/test_obsidian_source_projection.py -q
./.venv/Scripts/python.exe -m pytest tests/api/test_knowledge_workspace_api.py -q
```

Each route must show its actual state. Only a genuine export can upgrade a
route; tests and manually created folders do not qualify as user evidence.

## Failure, Rollback, Worklog, And Handoff

Disable the affected bridge in the manifest and retain existing captured
records. Hand O4 the route metadata schema, stable plugin IDs, safe paths and
fixture exports; hand O5 the workspace status schema and state vocabulary.
The handoff must include changed-file paths, trust/migration revision, exact
acceptance output, rollback action, route-state matrix and whether a real
user-origin export was observed. Append the exact commands, observed route
states, source/output IDs where present, rejection reason where absent,
deviations and rollback action to the shared worklog; never substitute a
declared route, directory, fixture, or manually created file for an export.
