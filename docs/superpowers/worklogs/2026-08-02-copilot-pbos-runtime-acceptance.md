# Copilot And PBOS Runtime Acceptance

## Scope

Verify the live personal knowledge loop with Obsidian Copilot as the active
authoring bridge. This is an evidence record, not an assertion that a model
chat, native plugin export, personal outcome, or strategy promotion happened
when its required evidence is absent.

## 2026-08-02 Runtime State

- The active project is `proj_b8a285642094`. Its managed Vault connection is
  ready and the authenticated Obsidian Local REST probe reports `connected`.
- The project plugin map registers only the Copilot output bridge alongside
  Clipper, Xiaohongshu, and Zotero imports. Claudian is not a project bridge
  and has no bearing on the project workflow.
- Copilot's automatic conversation archive and reviewed-output path are
  intentionally separate. The archive is configured; the output bridge is
  trusted and `ready_for_first_output`. There is no file in
  `04_Outputs/copilot`, so the bridge truthfully remains `awaiting_output`.
- During this acceptance run, a persisted setting that temporarily pointed
  automatic chat saving at `04_Outputs/copilot` was corrected back to the
  project archive route. The live workspace API now reports
  `conversation_archive_separated_from_reviewed_output`; the explicit
  `writeFile` custom command remains the only path to the reviewed-output
  directory.
- A completed Copilot response has been imported by the explicit archive
  transition as output `e8bfac705bad32e5a5e1458c`. It is a registered review
  draft only, with the normal evidence, quality, owner-outcome, and learning
  gates still active.

## Verification

- Backend PBOS/API/MCP/end-to-end suite: `92 passed, 1 warning`.
- Artifact, runtime convergence, Wiki sync, growth distillation, Copilot
  transcript import, and output-sync suite: `121 passed, 1 skipped, 1
  warning`. Both warnings are the existing Starlette TestClient deprecation.
- The live API readiness endpoint returned HTTP 200 with PostgreSQL and Redis
  reported as `ok`. API, Worker, Beat, n8n, PostgreSQL, and Redis were running.
- The configured local Studio proxy at `http://127.0.0.1:5174/` enumerated the
  selected project without placing an API credential in the browser. Selecting
  the project enabled the Knowledge, Growth, PBOS, and Mission controls.
- The live Personal Growth Cockpit rendered the actual selected-project data:
  connected Vault context, one pending Copilot review draft, declared personal
  context, zero accepted outcomes, zero verified capabilities, zero active
  strategies, two read-only connectors awaiting authorization, and the current
  evidence-gated execution plan.
- Desktop inspection at `1280x720` found client width `1274`, scroll width
  `1274`, and no horizontal overflow. Mobile inspection at `390x844` found
  client width `384`, scroll width `384`, zero offscreen interactive controls,
  and the PBOS cockpit still visible. The Studio console had zero error-level
  entries during the inspection.

## Boundaries And Next Real Inputs

- A native Copilot D-layer delivery must originate in the Copilot desktop UI:
  use one of the project commands, review the response, and approve its visible
  `writeFile` action to `04_Outputs/copilot/`. BSC cannot create that file and
  attribute it to Copilot.
- The release evidence gate still needs a real user-owned PDF, image,
  spreadsheet, Canvas, audio, or video source to prove the multimodal
  extraction/reference path. No temporary clipboard image or Vault attachment
  was available during this run, so no surrogate was generated.
- Outcome acceptance and strategy evolution continue to require a real
  observed delivery result, owner or mixed attribution, receipts, an explicit
  quality decision, and comparable cases. Agent test results remain technical
  verification only.
