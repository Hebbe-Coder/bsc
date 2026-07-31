# Personal Knowledge Ecosystem Closure Worklog

**PRD:** `docs/superpowers/specs/2026-07-27-personal-knowledge-ecosystem-closure-prd.md`
**Plan:** `docs/superpowers/plans/2026-07-27-obsidian-multimodal-ecosystem-configuration.md`

## Status

The initiative has implemented O1-O5 capability and live browser evidence; O6
and E1 remain operational-proof gates. An installed Obsidian plugin or an
empty directory is never recorded as captured knowledge. Runtime evidence,
source provenance, feedback closure and project isolation remain the release
criteria.

## Progress

| Date | Plan item | State | Evidence / deviation |
| --- | --- | --- | --- |
| 2026-07-27 | O1 configuration backup | Complete | Created a timestamped private backup of the Vault `.obsidian` JSON configuration outside the Vault and Git worktree. The backup report contains no source content or credential values. |
| 2026-07-27 | O1 plugin inventory | Complete | Verified enabled Clipper, Importer, Docxer, Xiaohongshu Importer, Claudian, Dataview, Metadata Menu, Excalidraw, Zotero Integration, Zotero Notes Sync, and Local REST API, plus enabled Properties, Bases, Canvas, Backlinks, Graph, Templates, and Daily Notes core plugins. |
| 2026-07-27 | O1 Local REST hardening | Complete with restart verification pending | Disabled the insecure HTTP server in the user-owned Local REST API configuration after backup. Unauthenticated `/vault/` and `/openapi.json` requests return `401`; the old HTTP listener remains active until Obsidian reloads the plugin or restarts, so it is not claimed closed at runtime yet. The API token was neither read nor written. |
| 2026-07-27 | O2 canonical metadata and views | Complete | Added the 20-field Metadata Menu contract, private config backup, atomic managed-index writer and explicit sync exclusion. Applied it to the real `default` Vault: all 20 fields and 9 Dataview index notes are present; a second run was unchanged with no conflicts. Focused tests passed. |
| 2026-07-27 | PRD implementation-plan split | Complete | Replaced the monolithic O1-O6 plan with an implementation index, six exclusive leaf plans and E1 `ensolidation`. E1 is the only release-readiness owner; no production code changed by this documentation split. |
| 2026-07-27 | Leaf-plan contract audit | Complete | Audited O1-O6 and E1 against the reusable execution template. The index now requires explicit inputs/outputs, project authorization, redaction, exact evidence and scoped rollback; O3-O6/E1 state these boundaries directly. This is documentation governance only and is not operational proof. |
| 2026-07-27 | PRD sub-plan split finalization | Complete | Rechecked the implementation index, O1-O6 leaf plans and E1 `ensolidation` against the fixed execution template. Added explicit shared-worklog rules to every plan, strengthened O1/O2 authorization/redaction and handoff requirements, and retained E1 as the sole `release_ready` authority. Actual verification command: `git diff --check` returned exit code 0 (line-ending warnings only). Documentation-only change; no external plugin export, restart, capture, extraction, feedback, or release status was claimed. |
| 2026-07-27 | PRD execution-index verification | Documentation complete | Revalidated the converted implementation index, six exclusive O-plans and E1 against the required dependency order, contract, authorization, redaction, rollback and handoff rules. Exact command: `git diff --check -- docs/superpowers/plans/... docs/superpowers/worklogs/2026-07-27-personal-knowledge-ecosystem-closure.md`; exit code `0` with only an existing LF-to-CRLF warning. No runtime, export or release claim was made. |
| 2026-07-27 | O3 Zotero and Excalidraw bridges | Complete with real exports pending | Added a bounded Zotero frontmatter provenance adapter and a `filesystem_context` adapter restricted to dedicated `03_Projects/` routes. The real `default` Vault now declares and trusts `01_Sources/zotero/` plus `03_Projects/active/maps/`; both were empty when configured and remain `awaiting_export`, not captured. `pytest tests/knowledge/test_wiki_sync.py tests/knowledge/test_obsidian_output_sync.py tests/knowledge/test_obsidian_source_projection.py -q` passed: 25 passed, 1 skipped. `git diff --check` passed. |
| 2026-07-27 | O3 trust-ledger preservation repair | Complete | Runtime verification found that a replacement manifest followed by a new-route approval could drop unchanged on-disk approvals. `set_trust` now merges still-matching persisted trust entries; a regression test proves that adding Zotero does not revoke Clipper or Docxer. Restored all seven configuration-bound approvals in the real `default` Vault, then re-synced: `blocked` changed from 1 to 0. |
| 2026-07-27 | O4 multimodal evidence core and real bootstrap | Implemented; full local tool stack pending | Added project-scoped `MediaAsset`, `ExtractionArtifact`, `TableArtifact`, and `ReferenceLink` records, additive SQLite/PostgreSQL schema/indexes, redacted list reads, hash checks, CSV/XLSX/Canvas/Excalidraw/PDF/image metadata extraction, and auditable `multimodal_extract` runs. A real Vault re-sync registered 6 immutable asset descriptors. Six persisted extraction runs produced 3 `complete` UTF-8 derivatives and 3 `partial` Canvas derivatives; no table was detected. Local OCR (`tesseract`) and media probe (`ffprobe`) remain unavailable and are reported as such. `pytest tests/knowledge/test_multimodal_evidence.py tests/knowledge/test_wiki_sync.py tests/knowledge/test_obsidian_output_sync.py tests/knowledge/test_obsidian_source_projection.py -q` passed: 30 passed, 1 skipped. |
| 2026-07-27 | n8n information-aggregator architecture review | Documentation complete; external integration not enabled | Parsed the supplied `n8n信息聚合器.json`: 87 nodes, inactive workflow, intended 08:00 schedule, public RSS/Reddit/YouTube/X/TikTok discovery, DeepSeek derivatives, Feishu delivery and credential references only. Added the signal-discovery boundary, batch contract, trust separation, idempotency, BSC receipt ledger, and notification limits to the PRD. No n8n instance, provider credential, Feishu credential, user source, or external workflow was changed; no capture or runtime success is claimed. |

| 2026-07-27 | PRD split contract revalidation | Documentation complete | A static contract check validated the implementation index plus the six O-plans and E1 for their required ownership, input/output, test-first, acceptance, rollback and worklog sections. The scoped `git diff --check` exited `0`; only the existing LF-to-CRLF warning was emitted. This verifies planning governance only and does not advance O5/O6/E1 runtime status. |
| 2026-07-27 | Test-first gate clarification | Documentation complete | Revalidated the requested O1 -> O2 -> O3 -> (O4/O5) -> O6 -> E1 sequence. Standardized every O-plan's first task as a focused failing-test requirement and added E1's explicit integration-level failing-test gate for migration order, feature flags, lineage, authorization, REST/MCP redaction, and browser drill-down. This documentation change does not claim an integrated runtime result. |
| 2026-07-27 | O1-O6/E1 split-contract audit | Documentation complete | Actual command: PowerShell structural audit of the implementation index's six O-plans and E1 for `Goal`, `Owned Surfaces`, `Acceptance`, and `Failure, Rollback, Worklog, And Handoff`; exit code `0` (`subplan-contract-audit: PASS`). `git diff --check` over the index, O1-O6, E1 and this worklog also exited `0`; Git emitted only an LF-to-CRLF warning for the pre-existing tracked index file. E1's failure/rollback heading was normalized and its release handoff was made explicit. This validates planning governance only: O5/O6/E1 retain their existing operational-proof status. |
| 2026-07-27 | O1-O6 execution-template normalization | Documentation complete | A stricter structure audit found that all six leaf plans carried test-first requirements but used a combined `Tasks` heading. Split each into explicit `Test-First Tasks` and `Implementation Tasks` sections without changing ownership, scope, dependencies, acceptance commands, release status, or production code. The E1 integration gate already had its own test-first section. This makes the requested fixed sub-agent template mechanically auditable; it is not runtime or operational proof. |
| 2026-07-27 | Horizon-to-primary capture contract | Implemented and tested | Replaced the one-way legacy discovery field with the explicit `supports_horizon_signal_ids` contract in `POST /knowledge/sources/capture-web`, retained `discovered_from_source_id` for existing records, and made the admission gate accept either only after same-project, eligible/processed, distinct-hash, primary-role and canonical-origin checks pass. Idempotent re-capture links an existing governed `primary_web` capture without turning an unrelated duplicate into primary evidence. Exact failing tests were added first, then `pytest tests/api/test_knowledge_workspace_api.py::test_workspace_capture_web_creates_reviewable_primary_evidence_linked_to_a_horizon_signal tests/knowledge/test_source_triage.py::test_horizon_candidate_can_be_used_only_after_an_explicit_independent_primary_capture tests/knowledge/test_source_triage.py::test_horizon_candidate_accepts_the_legacy_discovery_link_on_existing_primary_capture -q` passed: 3 passed. |
| 2026-07-27 | Studio explicit primary capture action | Implemented and tested | Added the typed Studio API client and a selected-Horizon-source `Capture primary source` action. The click performs the existing bounded public HTTPS capture only for the selected signal, refreshes the project state, and keeps the signal and captured primary evidence distinct. UI copy states that the radar signal is not promoted; normal approval remains a separate governed step. `npm run test:frontend -- --run src/api/knowledgeWorkspaceApi.test.ts src/components/KnowledgeWorkspace.test.tsx` passed: 18 passed. |
| 2026-07-27 | Integrated knowledge regression | Passed | `pytest tests/knowledge/test_source_triage.py tests/api/test_knowledge_workspace_api.py tests/integration/test_knowledge_wiki_e2e.py -q` passed: 49 passed. `npm run check` and `npm run build` passed. The production build emitted only the existing large-chunk advisory; no test or type failure occurred. |
| 2026-07-27 | Docker deployment and runtime proof | Passed with external capture pending | Rebuilt and restarted `bsc-backend`, `celery-worker` and `celery-beat` with `docker compose --profile celery up -d --build bsc-backend celery-worker celery-beat`. `http://127.0.0.1:8002/health` reported PostgreSQL, Redis, Celery, DeepSeek provider and document parser healthy. Worker inspection returned `pong`; the deployed Horizon-link contract assertion passed. The rebuilt worker has `tesseract 5.5.0` and `ffprobe 7.1.5` on `PATH`. |
| 2026-07-27 | Browser acceptance after image rebuild | Passed for authentication boundary and layout | The rebuilt Studio at `http://127.0.0.1:8002/` rendered the Knowledge workspace. At desktop width `1274`, `scrollWidth` equalled `clientWidth`; at the explicit mobile check (`390x844`, rendered width `384`), `scrollWidth` also equalled `clientWidth`. With no access key entered, Studio visibly showed `Studio access required` and disabled Sync, Horizon import, growth and maintenance actions. No browser capture was invoked and no user source or credential was read; authenticated real-project capture therefore remains external operational proof, not a completed claim. |
| 2026-07-27 | Authenticated Studio evidence and capture-control proof | Passed without source mutation | A local authorized Studio read verified the actual `default` project state: Vault connected and Wiki ready, 125 evidence records, 59 Horizon records, 9 published Wiki pages, configured plugin routes, persistent schedules and a live Evidence Atlas. A real Horizon source was selected; the new `Capture primary source` control was visible and enabled with explicit non-promotion guidance. At the mobile `390x844` viewport, the existing `Inspect` pane displayed the same enabled control with no horizontal overflow. The control was deliberately not clicked, so no external HTTP capture or database source mutation is claimed. |
| 2026-07-28 | Live Horizon-to-primary evidence capture | Passed | Used the running container's already-configured authorization only in process, without reading, printing, persisting, or exposing its credential. Captured one existing Horizon signal's public HTTPS primary page through `POST /knowledge/sources/capture-web`. Durable record `51b0d908cb93` is a distinct `primary_web` source in `validated` state, retains `evidence_role=primary_capture` and the explicit Horizon support link; capture run `265a76fadbfd` is `completed`. No approval, publication, source-body disclosure, or automatic signal promotion occurred. |
| 2026-07-28 | Knowledge capture and multimodal regression | Passed | `pytest tests/knowledge/test_source_triage.py::test_horizon_candidate_can_be_used_only_after_an_explicit_independent_primary_capture tests/knowledge/test_source_triage.py::test_horizon_candidate_accepts_the_legacy_discovery_link_on_existing_primary_capture tests/api/test_knowledge_workspace_api.py::test_workspace_capture_web_creates_reviewable_primary_evidence_linked_to_a_horizon_signal -q` passed: 3 passed. `pytest tests/knowledge/test_multimodal_evidence.py tests/integration/test_knowledge_wiki_e2e.py -q` passed: 9 passed. A broader six-file aggregation was stopped after its 15-minute command timeout and is not counted as a passing result. |
| 2026-07-28 | Studio and container integration verification | Passed with optional n8n runtime unconfigured | `npm run test:frontend -- --run src/api/knowledgeWorkspaceApi.test.ts src/components/KnowledgeWorkspace.test.tsx src/components/growth/GrowthWorkspace.test.tsx` passed: 50 passed. `npm run check` and `npm run build` passed. `docker compose --profile full config` passed only with a one-process validation value for the required n8n encryption key; no n8n key was generated or saved, so n8n itself remains intentionally unconfigured. API health reported PostgreSQL, Redis, Celery, LLM and parser `ok`; worker `celery -A app.core.celery_app:celery inspect ping --timeout=10` returned `pong`; worker has `tesseract 5.5.0` and `ffprobe 7.1.5`. |
| 2026-07-28 | Celery integration isolation check | Passed | `pytest tests/integration/test_growth_celery.py -q` passed: 12 passed. `pytest tests/integration/test_knowledge_celery.py -q` passed: 2 passed. These isolated results prove the scheduled growth and knowledge task contracts; they do not convert the earlier broad aggregation timeout into a passing aggregate run. |
| 2026-07-28 | Persisted schedule verification | Passed | A protected local `GET /knowledge/schedules?project_id=default` check found five enabled schedules in `Asia/Shanghai`: `growth_daily` at `0 17 * * *`, `growth_weekly_distillation` at `30 17 * * 5`, `horizon_capture` at `0 8 * * *`, `source_sync` every five minutes, and `wiki_maintenance` at `15 17 * * *`. This proves persisted schedule configuration, not future task execution or external plugin capture. |
| 2026-07-28 | Complete workspace and operations projection verification | Passed with evidence-gap disclosure | `pytest tests/api/test_knowledge_workspace_api.py -q` passed: 19 passed. `pytest tests/knowledge/test_source_triage.py -q` passed: 29 passed. `pytest tests/knowledge/test_operations_service.py tests/knowledge/test_operations_graph.py tests/api/test_knowledge_operations_api.py -q` passed: 10 passed. Operations cockpit and growth-visualization UI tests passed: 14 passed. The protected live project projection returned 175 graph nodes, 346 edges, 7 lanes, 27 derived actions and no pagination truncation. Its lifecycle audit truthfully reports missing `validation` and `memory_feedback` lanes; this is the expected current evidence gap until a real evaluated output and feedback closure exist. |
| 2026-07-28 | Live scheduled-source synchronization | Passed without synthetic capture | Submitted a governed `source_sync` run through the running protected API and waited for its Celery terminal state. Run `ef5380500b2c` completed with 6 persisted events. Its safe report recorded 7 duplicates, 0 new sources, 9 Wiki pages and output-feedback synchronization metadata. This validates the real scheduler/worker/Vault path and shows that already-managed files are not re-captured as novel evidence; it does not claim a new third-party plugin export. |
| 2026-07-28 | MCP read-boundary verification | Passed | `pytest tests/mcp/test_knowledge_operations_tools.py tests/mcp/test_knowledge_evidence_tools.py tests/mcp/test_wiki_http_contract.py -q` passed: 5 passed. This covers authorized Agent access to operational projection, bounded evidence reads and Wiki HTTP compatibility without granting publication or source-body disclosure authority. |
| 2026-07-28 | External operational-proof recheck | Pending user-origin activity | Re-probed the live boundaries: plaintext Local REST port `27123` remains reachable; configured `01_Sources/zotero/` and `03_Projects/active/maps/` contain no export file; protected project feedback list returns 0 records. These are not implementation failures that can be repaired with generated fixtures: secure listener reload, plugin-origin exports and a real D-layer business judgement must occur outside BSC before O6/E1 can proceed. |
| 2026-07-28 | Obsidian secure-boundary restart proof | Passed | After the user restarted Obsidian, `Test-NetConnection 127.0.0.1 -Port 27123` returned `False` while the Obsidian process was running. The disabled plaintext Local REST listener is no longer reachable at runtime. No Local REST token, plugin configuration value, source content, or credential was read. |
| 2026-07-28 | Excalidraw route and command verification | Implemented; visual-content export pending | Confirmed that the active Vault is `D:/bsc/bsc`, Excalidraw `2.25.3` is compatible with Obsidian `1.12.7`, and the plugin configuration is valid UTF-8 JSON. This plugin version exposes `Create new drawing - IN AN ADJACENT WINDOW` (and equivalent tab/current-pane commands), not the older `Excalidraw: Create new drawing` name. Changed only Excalidraw's configured output folder to `projects/default/03_Projects/active/maps`; its existence and JSON validity were verified. A user-created `knowledge-flow.excalidraw.md.md` has only the empty `%%excalidraw%%` marker and a doubled extension, so it was preserved but is not counted as a visual export, extraction, or capture event. |
| 2026-07-29 | Excalidraw extension repair | Implemented; visual-content export pending | A user screenshot and filesystem check confirmed that the empty marker file was opened as ordinary Markdown because its actual name ended in `.excalidraw.md.md`. Renamed only that user-created file to `knowledge-flow.excalidraw.md`; byte length remains 14 and content remains exactly `%%excalidraw%%`. This repairs the supported filename contract without adding or altering visual content. The user must reopen the tab so Obsidian can choose the Excalidraw view. It remains ineligible as a visual-evidence, extraction, or capture proof until it contains genuine user-created elements. |
| 2026-07-29 | Excalidraw producer startup proof | Passed; knowledge-flow content pending | User screenshot showed the genuine Excalidraw canvas and drawing toolbar. Filesystem inspection then confirmed that plugin-created `Drawing 2026-07-29 19.01.22.excalidraw.md` landed directly in `projects/default/03_Projects/active/maps/`, with valid Excalidraw frontmatter, a Drawing section and compressed scene data (574 bytes). This is real plugin-output routing proof. Its visible content is the plugin's default welcome screen, not a user-authored knowledge-flow diagram, so no source synchronization, extraction, graph claim, or release gate was advanced from it. |
| 2026-07-29 | Official compressed Excalidraw extraction | Implemented, deployed, and runtime-verified | Real plugin output exposed a production gap: the original extractor only scanned fenced `json`, while Excalidraw `2.25.3` writes LZString Base64 `compressed-json`. Added a bounded in-process decoder, explicit scene encoding metadata, an auditable `excalidraw_no_elements` partial state, and a decode-failure state. Added a formal pytest regression covering official compressed scenes and empty scenes. In a newly built isolated image, equivalent assertions passed for plaintext compatibility, official compressed extraction, empty compressed scenes, and malformed compressed scenes. Formal local tests then passed: `tests/knowledge/test_multimodal_evidence.py` `9 passed`; affected Obsidian sync and Celery regression `32 passed, 1 skipped`. Rebuilt and recreated API, Worker and Beat; health reports PostgreSQL, Redis, Celery, LLM and parser `ok`, Worker ping returned `pong`, and the running API image decoder passed. Production images intentionally omit pytest; the repository `.venv` is the authoritative local test runner for this change. |
| 2026-07-29 | Controlled extractor revision re-execution | Implemented, deployed, and runtime-verified | Centralized the active extractor revision as `local-v2`, including automatic source sync and default manual extraction. A new regression proves a persisted `local-v1` derivative does not block governed `local-v2` re-extraction. Local verification: `pytest tests/knowledge/test_multimodal_evidence.py tests/knowledge/test_wiki_sync.py tests/integration/test_knowledge_celery.py -q` returned `33 passed, 1 skipped`; `git diff --check` passed with only the existing line-ending warning. Rebuilt API, Worker and Beat; health remained `ok`, Worker ping returned `pong`, and the deployed Worker reported `local-v2`. A real scheduled `source_sync` run `60f4c7f38563` reprocessed 12 persisted default-project assets at `local-v2` (`3 complete`, `7 partial`, `2 unavailable`); the prior `local-v1` records remain immutable audit history. Two compressed Excalidraw scenes are now explicitly `partial` with `excalidraw_no_elements`, rather than silently appearing as zero-element generic results. A subsequent manual source sync `facefb17c503` skipped all 12 current-revision derivatives, proving idempotency. This does not claim a business knowledge diagram: the current drawing remains the plugin welcome scene until the user adds and saves real nodes. |
| 2026-07-29 | O6 regression, read-performance repair, and redeployment | Implemented and runtime-verified; external proof remains pending | Fixed a real read-path defect: advisory scheduler availability in every growth response could synchronously block on an unreachable Celery broker for about 4.1 seconds and its former two-second cache expired before the next read. The advisory cache is now 30 seconds; task submission retains a fresh broker check and cannot be authorized by cached status. Focused regression passed: 5 passed. Full knowledge/integration suite passed: `651 passed, 8 skipped`. Frontend suite passed: `149 passed`; `npm run check` and `npm run build` passed; lint completed with the repository's pre-existing `208` warnings and no errors. `docker compose --profile full config` passed with a process-only validation value. API, Worker and Beat were rebuilt and recreated; protected dependencies reported `ok` for PostgreSQL, Redis, Celery, DeepSeek routing and document parsing, and Worker inspection returned `pong`. This verifies implementation, performance and deployment, but does not replace the required real Zotero/table-or-image/business-diagram exports or D-layer user feedback. |
| 2026-07-29 | O5 authorized table and image inspection | Implemented, tested, and deployed | Closed two real visualization-contract gaps instead of treating a metadata list as an inspector. `GET /knowledge/evidence/projects/{project_id}/tables/{table_id}/preview` now returns a bounded, project-authorized page of extracted table rows, declared versus available row counts, truncation, units, extractor revision and source linkage. Overview, graph, MCP and generic record reads still exclude derivative bodies. `GET /knowledge/evidence/projects/{project_id}/assets/{asset_id}/thumbnail` now returns only an explicit, authorized, max-edge 1280 WebP thumbnail; it strips original image metadata, rejects non-image, missing, oversized, escaped or cross-project storage references, and sends `Cache-Control: private, no-store`. The Studio now opens these inspection surfaces only after the user selects the matching table or visual record. Focused regression: `pytest tests/api/test_knowledge_evidence_api.py tests/knowledge/test_multimodal_evidence.py tests/mcp/test_knowledge_evidence_tools.py -q` passed: 14 passed. Focused frontend Evidence Atlas regression passed: 7 passed. |
| 2026-07-29 | O5 container Vault-path repair and release verification | Implemented and runtime-verified; real asset proof pending | The thumbnail service initially used the persisted project-relative Vault mapping as if it were a container root. Corrected it to resolve through configured container `OBSIDIAN_VAULT_ROOT` and require the asset to remain inside the mapped project directory. Added a content-hash guard so a `TableArtifact` can never display rows from a non-matching extraction revision; it reports `table_derivative_content_hash_mismatch` instead. Runtime check confirmed the container Vault root and mapped project root exist. Rebuilt and recreated API, Worker and Beat with `docker compose --profile celery up -d --build bsc-backend celery-worker celery-beat`; API health reported database, Redis, Celery, DeepSeek and parser `ok`, Worker inspection returned `pong`, and a temporary in-container repository assertion returned the expected hash-mismatch reason. Final commands all exited `0`: `pytest -q` (1447 collected), `npm run test:frontend`, `npm run check`, `npm run lint`, `npm run build`, `docker compose --profile full config`, and `git diff --check`. Current protected aggregation remains truthful: 134 sources, 12 assets, 24 extraction records, 0 table artifacts, 0 references, and 0 image assets. Therefore this proves the feature and deployment path, not a real table/image user-value claim. |

## Current Verified Boundaries

- Vault root: `D:/bsc/bsc`; managed project root: `projects/default`.
- Zotero Integration is configured to import into
  `projects/default/01_Sources/zotero`, but the Zotero library contains no
  imported items yet. The route remains `awaiting_export`.
- Local REST API is not connected to BSC. Filesystem projection remains the
  supported route until the secure listener has been reloaded and a scoped,
  authorized read test can be performed without exposing a token.
- Excalidraw creates new drawings directly in
  `projects/default/03_Projects/active/maps`. Its installed version uses the
  `Create new drawing` command family rather than the older prefixed command.
  The route currently contains two plugin-generated default welcome drawings;
  both are correctly extracted as `partial/excalidraw_no_elements`, not as
  visual knowledge or business evidence. No user-authored knowledge-flow
  diagram has been exported yet.
- The Docker Worker has verified OCR and media-probe executables. Host-local
  capability state remains separate from the deployed worker capability state.
- Table row and image preview are now explicit, project-authorized inspector
  reads. They do not add source or derivative bodies to catalog, graph, MCP or
  generic record responses. The current project has no persisted table or
  image asset, so their empty state is operationally correct until an actual
  user export is captured.
- After the user restarted Obsidian on 2026-07-28, plaintext Local REST port
  `27123` was probed as unreachable while Obsidian remained running. The
  disabled insecure listener is therefore closed at runtime.
- n8n's encryption key is intentionally unset. Compose topology validates with
  an ephemeral process-only value, but no n8n instance or credential store is
  configured or claimed operational.
- No third-party plugin executable code, user source note, raw source body,
  external account, or credential has been modified. The governed
  `primary_web` evidence record documented above is the intentional BSC
  database mutation for the live capture proof.

## Next Gates

1. Run O6 with real project exports and feedback records. The Obsidian restart
   check that confirms port `27123` is closed has already passed.
2. Record one real D-layer output feedback event that changes a later
   knowledge, method, context-pack or action decision; generated summaries and
   rendered charts do not qualify.
3. Produce actual Zotero, Excalidraw and table-or-image exports through their
   configured producer routes. Empty route folders, an empty Excalidraw marker,
   and BSC-managed evidence projections do not satisfy this gate.
4. Start E1 `ensolidation` only after O1-O6 handoffs are current; E1 alone may
   set `release_ready`, otherwise it must record
   `implemented_with_operational_proof_pending`.

## 2026-07-29 Controlled Multimodal Acceptance and Citation Projection

- Created three clearly labelled, non-business operational fixtures in the
  managed `default` project: an Excalidraw scene, a CSV table and a PNG image.
  They exist only to exercise the configured Vault -> source-sync -> derivative
  -> Evidence Atlas path and were not proposed, published or represented as
  user knowledge.
- Submitted protected `source_sync` run `3a6c470f24ce` through the running
  BSC API without reading, logging or persisting its access key. Celery finished
  it as `completed`: three new assets were extracted as `complete`; twelve
  current-revision assets were correctly skipped as idempotent duplicates.
- Found and repaired two live-read defects. Evidence Atlas now projects the
  authoritative `knowledge_citations` rows as redacted, read-only `cites`
  references to Wiki pages, while preserving `ReferenceLink` as its independent
  typed-link domain. It also recognises `excalidraw-elements` from Obsidian
  Markdown drawings as visual evidence. No publication, source status or
  citation claim was modified.
- Rebuilt and recreated `bsc-backend`, `celery-worker` and `celery-beat` with
  `docker compose --profile celery up -d --build bsc-backend celery-worker
  celery-beat`. Health reported PostgreSQL, Redis, Celery, DeepSeek routing and
  document parsing `ok`; Worker inspection returned `pong`.
- Production API acceptance passed against the live `default` project: the
  Excalidraw fixture was `complete` with eight elements; the table inspector
  returned four available rows at `local-v2`; the image endpoint returned an
  authorized `image/webp` thumbnail with `Cache-Control: private, no-store`;
  25 published Wiki citations appeared as redacted Evidence Atlas references;
  a projected citation record returned `200` without a `claim_text` field.
- Regression evidence: `pytest tests/api/test_knowledge_evidence_api.py -q`
  passed (`4 passed`), `npm run test:frontend -- --run
  src/components/knowledge/EvidenceWorkspace.test.tsx` passed (`8 passed`),
  and `npm run check` passed. Full-suite verification follows this entry so it
  covers the final citation-projection changes.
- Status remains `implemented_with_operational_proof_pending` for business
  value: this is a real technical E2E verification using explicit fixtures,
  not a substituted claim that a user-authored Zotero item, business diagram or
  D-layer feedback loop has been validated.

### Final Regression Evidence

- `pytest -q` completed with `1440 passed, 13 skipped` in 209.53 seconds.
- `npm run test:frontend` completed with `21` passing files and `155` passing
  tests; `npm run check` and `npm run build` completed successfully.
- `npm run lint` completed with zero errors and 212 pre-existing warnings.
  The citation projection and Excalidraw visual-detection edits introduced no
  lint error.
- `docker compose --profile full config` passed using a process-only validation
  value for the required n8n encryption setting; no key was generated or
  persisted. `git diff --check` passed; its only output was the workspace-wide
  existing CRLF conversion advisory.

## 2026-07-29 Live Excalidraw Bridge And Idempotent Sync

- Rechecked the running Obsidian process rather than treating installation as
  proof. The secure Local REST listener is active on its configured loopback
  port, and the enabled plugin inventory includes Local REST API, Excalidraw,
  Claudian, and Zotero Integration. No plugin credential or third-party source
  body was copied into BSC or this worklog.
- The `default` project had real Excalidraw maps under
  `03_Projects/active/maps`, but no BSC plugin manifest. Registered exactly
  that existing directory through the governed workspace API as the trusted
  `obsidian-excalidraw-plugin` `filesystem_context` route. This created the
  project-local `bsc-plugins.json` and configuration-bound trust ledger; it
  did not alter any drawing, source, or plugin code.
- Submitted source-sync run `7ac784293ca5` through the local authorized Studio
  proxy. The live Celery worker completed it with six durable events:
  `knowledge.run.queued`, `knowledge.run.execution_assigned`,
  `knowledge.run.running`, `knowledge.source.sync.completed`,
  `knowledge.wiki.snapshot.synced`, and `knowledge.run.completed`.
- The safe result was intentionally idempotent: 11 project files scanned, 0
  new source bodies, 13 existing-hash duplicates reconciled, 3 skipped, and 0
  blocked. The trusted Excalidraw route now reports `captured` with 3 linked
  source records and the Wiki snapshot contains 9 indexed pages. This is a
  provenance connection for existing immutable evidence, not a fabricated
  claim of new knowledge.
- The evidence mirror reported 2 conflicts and preserved them without
  overwriting user content. They remain an operational review item. Status is
  still `implemented_with_operational_proof_pending`: GitHub/Feishu remain
  unauthorized and a real D-layer business feedback loop has not been
  substituted with fixtures.
- Rollback: revoke the single bridge through the workspace plugin-trust API or
  replace the project manifest with an empty approved configuration. Existing
  immutable source records and user-authored Excalidraw files remain intact.

## 2026-07-29 Horizon Recovery And Exact-Projection Reconciliation

- Investigated the live Horizon producer failure instead of treating it as a
  successful update. The configured source set was present; the actual defect
  was that a normal empty fetch window entered the required scoring stage and
  became `HZ_EMPTY_INPUT`. `scripts/run_horizon_pipeline.py` now records a
  completed `no_items` outcome without scoring only when fetch diagnostics are
  not a full source failure. A full source failure remains terminal.
- A 72-hour recovery collection initially proved the information sources were
  reachable (GitHub, RSS, and Hacker News returned 35 merged items) but exposed
  an insufficient 180-second score-stage limit. The Horizon analysis
  concurrency was conservatively changed from 1 to 2. The daily Windows task
  remains single-instance with its 10-minute execution limit and now invokes
  the producer with a 300-second score-stage and 540-second cycle bound, with
  optional enrichment disabled for the evidence path.
- The subsequent real producer run `run-20260729T154353Z-64a6ed6d` completed
  with `fetched=35`, `scored=35`, and `kept=10`. Google News and Reddit
  connectivity faults remained explicit external-source diagnostics; they were
  not replaced with generated content. BSC capture processed all 10 filtered
  signals and the project workspace now reports 74 captured Horizon sources.
- Found that three evidence pages were byte-for-byte identical to their
  current BSC immutable projections but had no mirror metadata, which caused
  false conflict counts after prior concurrent or legacy writes. Added a strict
  `adopted` projection state: BSC records the mirror ledger only when a file
  exactly matches the recomputed projection and never rewrites the file. Any
  non-matching page remains a conflict.
- Live source-sync run `5285279554d0` verified the repair: 3 pages adopted, 79
  unchanged, 0 evidence-mirror conflicts, and no evidence body write. Focused
  regression command `python -m pytest
  tests/knowledge/test_obsidian_source_projection.py
  tests/test_horizon_producer_script.py tests/knowledge/test_horizon_run_store.py -q`
  passed with 20 tests.
- The correct overall release state remains
  `implemented_with_operational_proof_pending`: this closes the Horizon and
  Excalidraw input proof plus projection integrity, but does not claim a
  user-authored Zotero/Claudian export or a real D-layer business feedback loop
  that changes a later decision.

## 2026-07-30 Obsidian Session And PBOS Feedback-Lineage Check

- Inspected the live Obsidian session after the user restart. The enabled
  community-plugin inventory contains Local REST API, Excalidraw, Claudian,
  Zotero Integration, Dataview, Metadata Menu, Clipper, Importer, Docxer and
  the configured social route. This confirms plugin activation, not an
  assertion that every connector has emitted user material.
- The opened Excalidraw note is a plugin welcome/default drawing in the trusted
  project maps route. It remains eligible as technical route evidence but is
  not labelled as a business diagram or knowledge asset. The visible Claudian
  panel contained a test conversation; the configured
  `04_Outputs/claudian` directory still had no plugin-written file, so no
  Claudian output was fabricated or captured.
- Queried the protected PBOS cockpit from inside the running API container
  without reading, logging or exposing its `API_KEY`. The latest active plan
  `art_ffc8b3b7085b` has both feedback artifacts in `feedback_refs` and in
  its parent lineage. The two feedback records each point back to their
  respective outcome records, proving the feedback-to-next-plan reference
  chain is live.
- The same read-only cockpit check reported one accepted and one unverified
  outcome, zero verified capabilities, zero active strategies and
  `evidence_ready=false`. These values are intentionally not upgraded into a
  business-success claim: the evolution gate still requires comparable,
  complete evidence before it may promote a reusable capability or strategy.
- Docker runtime recheck: API, PostgreSQL, Redis and n8n were healthy; Celery
  Worker and Beat were running. Overall status remains
  `implemented_with_operational_proof_pending` until a real user-created
  output is exported by a configured plugin and a real outcome changes a later
  decision under the declared evidence rules.

## 2026-07-30 Real Horizon Weekly Distillation Into PBOS Planning Context

- Ran the protected, real weekly distillation for `default` period `2026-W31`
  against the configured DeepSeek provider. The completed distillation
  `6eabfd13be47b5a844e00e53` used input hash
  `1b5c24fb41c76948977b9556827d6e620271c6c443417d8388a26d8b05d73251`
  and `424` bounded input records. It materialized the governed five-document
  bundle under `distillations/每周蒸馏/2026-W31/`: summary, knowledge actions,
  content briefs, next-context package and method iteration.
- Performed an independent read-only validation without logging generated
  prose or source bodies. Every document exists, has three Markdown sections,
  at least one resolvable source/page citation, and an explicit uncertainty
  marker. The five documents contained respectively 2, 11, 4, 2 and 1
  resolvable citations; all labels resolved to the same project's governed
  sources or pages. The generation metadata identifies `deepseek-v4-pro`;
  no credential or prompt payload was written to this worklog.
- Found and fixed a real handoff defect: PBOS allowed `distillations/` but
  selected roots in an order that could fill its eight-document budget with
  Wiki pages before the latest weekly next-context package was reached.
  `PBOSVaultContextBuilder` now selects the latest `03-下周上下文包.md` before
  other roots and excludes superseded next-context packages from fallback
  context. A new regression first failed under the former order, then the
  PBOS context/API/integration suite passed with `25 passed`.
- Rebuilt and recreated `bsc-backend`, `celery-worker` and `celery-beat`.
  The protected live PBOS compiler then created plan `art_9f8e70e999ed` for
  its current Mission. Its `knowledge_context_refs` begins with
  `vault:distillations/每周蒸馏/2026-W31/03-下周上下文包.md` and retains two
  feedback references from prior outcomes. This is a real source ->
  distillation -> next-plan context and feedback lineage, not a fixture.
- The new plan remains `context_grounded`, correctly exposing that verified
  personal capabilities and sufficient comparable business outcomes have not
  yet been established. Plugin configuration and the self-growing knowledge
  loop are operational; release status remains
  `implemented_with_operational_proof_pending` only for the still-unproven
  user-origin Claudian/Zotero output and business-value feedback gates.

### Regression And Runtime Gate

- `pytest tests/knowledge/test_growth_distillation.py
  tests/integration/test_abcd_growth_e2e.py tests/integration/test_pbos_e2e.py
  -q` passed with `57 passed`. This covers weekly distillation constraints,
  A/B/C/D persistence and the PBOS end-to-end contract in addition to the
  focused `25 passed` PBOS context/API/integration run.
- `docker compose --profile full config` and `git diff --check` both passed.
  The latter emitted only existing workspace-wide LF-to-CRLF advisories.
  Runtime health reported PostgreSQL, Redis, Celery, DeepSeek and document
  parsing as `ok`; a live worker `inspect ping` returned `pong`.
- Studio browser readback rendered the runtime-access boundary and kept
  execution disabled until an authorized local key is supplied. The protected
  API and Vault checks above are the authoritative runtime proof; no secret
  was copied into browser state or this worklog merely to turn an unauthenticated
  screen into a screenshot.

## 2026-07-30 PBOS Grounding Readback

- Replaced the remaining static personal-lineage diagram with a read-only
  projection of the actual plan inputs and outcome loop: weekly handoff and
  Vault references feed the current plan; outcomes feed feedback, the next
  plan, and capability promotion gates. The new Plan Grounding panel lists
  the selected governed references without reading Vault content in the
  browser.
- Browser acceptance against the protected local Studio displayed the real
  W31 handoff, eight governed Vault references, and two feedback inputs for
  the active default-project plan. The panel still explicitly states that
  these inputs do not establish a personal capability without verified
  execution evidence.
- Targeted cockpit tests, TypeScript checking, and the production frontend
  build passed. Desktop and 390px mobile rendering had no document, cockpit,
  or graph horizontal overflow; all seven React Flow nodes had non-overlapping
  bounds. Compose configuration also passed and the existing Docker services
  remained healthy.
- This is presentation and traceability proof only. The release state remains
  `implemented_with_operational_proof_pending` for user-origin Claudian/Zotero
  outputs and for enough comparable real outcomes to validate business value
  or capability promotion.

## 2026-07-30 Claudian Destination And Operational Recheck

- Re-checked the user-visible Claudian configuration without inspecting plugin
  code, private note content, or provider credentials. Its configured media
  destination is `projects/default/04_Outputs/claudian`, matching the trusted
  BSC output bridge. The configured directory exists and remained empty at the
  time of inspection.
- The visible Claudian sidebar conversation therefore proves that the plugin
  is active, but it is not a filesystem export and cannot truthfully be
  represented as a captured D-layer output. BSC requires a user-authored
  Markdown file to be created or exported into that configured destination;
  the existing five-minute `source_sync` schedule will then capture its
  metadata, evidence link, output feedback, and downstream growth context.
- Revalidated the surrounding runtime: Docker API, Worker, Beat, PostgreSQL,
  Redis, and n8n were healthy; `docker compose --profile full config --quiet`
  passed; the related scheduler, growth, A/B/C/D, and PBOS regression command
  passed with `106 passed`. The overall state remains
  `implemented_with_operational_proof_pending`, not `release_ready`, until a
  real user-origin output and a later decision-changing feedback result exist.

## 2026-07-30 Claudian Agent-Workspace Output Contract

- Corrected an operationally misleading bridge assumption. Claudian's public
  plugin contract gives its agent the Vault as a read/write workspace;
  `mediaFolder` is an attachment location, not evidence that a sidebar chat
  was exported. The runtime bridge therefore reports
  `agent_workspace / agent_writes_declared_output_path` and remains
  `ready_for_first_output` until a real file exists beneath
  `04_Outputs/claudian/`.
- Added the `bsc_output_contract: v1` parser for declared plugin outputs. It
  accepts only bounded scalar metadata plus comma-separated project-local
  source/page IDs, normalizes Windows CRLF, validates output kind and contract
  revision, and rejects a declared project mismatch. Existing source/page
  authorization remains enforced by `OutputRegistry`; output bodies and chat
  sessions are not exposed in route status or work logs.
- Added the durable-deliverable rule to the project `AGENTS.md` and configured
  Claudian's system prompt to direct report, PRD, plan, SOP, article, research
  brief, decision memo, and retrospective requests into the governed output
  folder. Ordinary conversation remains chat-only. No user output was created
  by BSC to satisfy this proof.
- Verification: focused output/plugin route tests, source sync, knowledge and
  growth Celery integration, and workspace/growth API tests passed with
  `112 passed, 1 skipped`; focused frontend workspace tests passed with
  `44 passed`; TypeScript check and production build passed. Rebuilt API,
  Worker, and Beat; all Compose services are healthy and Celery returned
  `pong`.
- A post-deployment scheduled run `298cea42ee58` completed through the real
  Worker. It scanned 11 existing managed-project files, had no mirror
  conflicts, and reported `output_feedback.scanned=0` and `registered=0`.
  This is the correct empty-route result, not a Claudian completion claim.
  Status remains `implemented_with_operational_proof_pending` until the
  plugin itself writes a user-origin output and a later evaluation/feedback
  record changes a subsequent decision.

## 2026-07-30 Published Wiki Metadata Reconciliation

- A full quality-gate audit exposed eight older BSC-published Wiki pages whose
  durable database status was `published` but whose Vault frontmatter lacked
  `status: published`. The new contract does not weaken lint to accept this
  mismatch. Instead, it provides an idempotent compatibility reconciliation
  that changes only the missing generated metadata.
- Before any write, the reconciler compares each page requiring repair against
  its exact durable BSC revision. A missing page, changed file, or cross-version
  mismatch raises a conflict and leaves the Vault untouched. Pages that already
  satisfy the contract perform no filesystem or database write. The quality
  run records the reconciliation result alongside its lint and evaluation
  output, so a metadata repair cannot be mistaken for an evidence or knowledge
  claim.
- Verification: focused reconciliation/quality tests, the affected Obsidian,
  triage, API, and PBOS suites passed; the complete backend suite passed
  `838 passed, 9 skipped`, the full frontend suite passed `163` tests, and
  TypeScript, production build, and Compose parsing passed. The current Docker
  image predates this reconciliation code; a live repair is deliberately not
  claimed until the rebuilt API and Worker are healthy.

## 2026-07-30 Bridge Runtime And Cross-Service Acceptance

- Re-read the BSC-owned plugin manifest and trust ledger without inspecting
  third-party plugin code, note bodies, credentials, or private settings.
  All seven declared routes are trusted and their configured project paths
  exist. The public runtime status is intentionally mixed: Obsidian Clipper
  has one captured export with a matching destination; Excalidraw has three
  captured project-map exports; Xiaohongshu, Docxer, Obsidian Importer, Zotero
  and Claudian have empty but ready paths. Docxer and Importer explicitly
  report `interactive_destination`; Claudian reports
  `agent_workspace / agent_writes_declared_output_path`. Empty folders were
  not promoted to sources, outputs, or business value.
- Executed a fresh protected `source_sync` through the Studio API. Durable run
  `c28c5e22107b` progressed `queued -> execution_assigned -> running ->
  completed` through Celery. Its persisted receipt reports `11` files scanned,
  `13` source duplicates, `0` created, `0` rejected, `0` blocked, `15`
  existing multimodal derivatives retained, `88` eligible evidence-mirror
  records unchanged, `10` Wiki pages indexed, and output feedback
  `scanned=0/registered=0`. This is real idempotent processing of the current
  Vault and an honest empty D-layer result.
- Regression: `pytest tests/knowledge/test_obsidian_output_sync.py
  tests/knowledge/test_wiki_sync.py tests/knowledge/test_knowledge_tasks.py
  tests/api/test_knowledge_workspace_api.py -q` passed with `76 passed, 1
  skipped`. It covers declared output registration, empty-output behavior,
  plugin route/trust state, task execution, and workspace authorization.
- Cross-service acceptance: `docker compose --profile full config --quiet`
  passed. Compose reported healthy/running API, Worker, Beat, PostgreSQL,
  Redis and n8n; `docker compose exec -T celery-worker celery -A
  app.core.celery_app inspect ping` returned `pong`. `/ready` returned `200`,
  while an unauthenticated direct request to
  `/knowledge/workspaces/default` returned `401`.
- MCP acceptance used the configured local proxy, which keeps the credential
  server-side. The compatibility profile reports JSON-RPC `2.0`,
  `stdio/streamable_http/sse` support and API-key/bearer authorization.
  `tools/list` returned `55` tools, including the knowledge/growth/operations
  set, and a bounded `wiki_evidence` call for `default` succeeded with a
  redacted structured response. `pytest tests/test_mcp_http.py
  tests/integration/test_knowledge_mcp_e2e.py
  tests/api/test_knowledge_operations_api.py -q` passed with `7 passed`,
  including tenant and project-key escape rejection.
- Release status remains `implemented_with_operational_proof_pending`.
  The only remaining bridge proof is an actual Claudian-written Markdown file
  in `04_Outputs/claudian`, followed by BSC registration and reviewed feedback
  that demonstrably changes a later PBOS plan or decision. No file was
  generated to imitate that user-origin action.

## 2026-07-30 Full Regression And Studio Final Check

- Full current backend regression, run against the dirty integrated worktree,
  passed with `1517 passed, 14 skipped` in `3m55s`. The skipped cases are
  declared external/PostgreSQL-environment boundaries; no test failed. This
  extends the focused knowledge, growth, PBOS, MCP and isolation checks above
  to the complete backend.
- `npm run lint` exposed one real error in the knowledge workspace's triage
  approval guard: `!Boolean(triage.reliability_pass)` violated
  `no-extra-boolean-cast`. Replaced it with the equivalent
  `!triage.reliability_pass`, preserving the `boolean | number` gate semantics.
  No warning-only unrelated legacy cleanup was mixed into this fix.
- Verification after the repair: focused `KnowledgeWorkspace` tests passed
  (`13 passed`); `npm run check`, `npm run lint`, `npm run build`, and
  `git diff --check` all passed. Lint retains the existing `214` warnings but
  reports zero errors; build retains only the existing ECharts chunk-size
  advisory. `git diff --check` emitted only existing LF-to-CRLF advisories.
- Fresh post-build Studio browser acceptance loaded the protected Knowledge
  workspace, reachable Vault, Horizon state and Evidence Atlas without a new
  console error. This validates the actual Vite path after the lint repair,
  rather than relying solely on the production bundle.

## 2026-07-30 Real Weekly Distillation Citation-Repair Closure

- A real `growth_weekly_distillation` run reached its model calls but preserved
  the prior weekly bundle because three documents failed the strict citation
  ledger gate. The existing no-overwrite behavior was correct, but the retry
  policy stopped after one batch repair when more than one document remained.
- Added one final bounded strict batch repair for production providers only.
  Its correction prompt includes the exact source/page labels retained in the
  context, requires output only for the still-rejected document slots, and
  prohibits non-citation square-bracket text. Citation validation, project
  scope, and incomplete-bundle preservation are unchanged. Bumped the
  distillation contract to revision `26` so the corrected behavior receives a
  new auditable input hash.
- Regression: `pytest tests/knowledge/test_growth_distillation.py -q` passed
  `54` tests. The added scenario proves that multiple invalid references after
  the first batch repair use the last bounded repair and publish only after all
  five documents meet the existing gate.
- Runtime proof: rebuilt the Compose `bsc-backend` and `celery-worker` images;
  API became healthy and Worker returned `pong`. Protected HTTP run
  `d18df90b398c` completed through Celery with three successful DeepSeek
  provider calls, `generation_mode=llm`, `quality_retry_count=2`, no fallback
  documents, and five generated paths under
  `distillations/每周蒸馏/2026-W31/`. A separate non-content inspection verified
  all five Markdown files plus `manifest.json` exist and pass the same
  citation/length/section/uncertainty/state-claim validator.
- The Claudian D-layer bridge remains honestly pending: its declared directory
  still has no user-origin Markdown. This successful weekly model run proves
  the governed A/B/C growth and real-provider path; it does not substitute for
  an external Claudian output, its evaluation, or feedback-driven PBOS change.
- Latest runtime recheck: scheduled `source_sync` run `3df46df2ad21` completed
  with `output_feedback.scanned=0`, `registered=0`, `rejected=0`, and
  `blocked=0`; the mounted `04_Outputs/claudian/` directory likewise contains
  zero Markdown files. This is an externally pending user-agent action, not a
  BSC failure or a result that may be synthesized by the platform.

## 2026-07-30 Copilot Replacement Bridge And Idempotent Output Sync

- Claudian was disabled in the user-facing Obsidian plugin list because its
  required Claude Code CLI is not installed. Obsidian Copilot was configured
  by the user with a local model-provider key and returned a real chat response
  in the sidebar. This verifies the interactive Copilot entry point only; it
  does not claim that Copilot has authored a governed output.
- Added the dedicated `copilot-agent` `filesystem_output` declaration at
  `04_Outputs/copilot/`, created that directory, and added its bounded durable
  output rule to the project `AGENTS.md`. A protected workspace API call wrote
  a separate trusted configuration record for that exact route. Copilot,
  Codex, and Claudian remain distinct provenance identities; chat transcripts,
  silent note edits, and unreviewed suggestions are excluded from D-layer
  capture.
- A live `source_sync` initially exposed a real idempotency defect: a later
  scan of the same external file used its new scan run ID and was rejected as
  an immutable-output conflict. The output sync service now retains the
  original registered run ID on a repeat observation, so it neither rejects a
  harmless retry nor creates false `output_produced_by_run` lineage for each
  later scan. The regression suite now covers two distinct scan runs.
- Verification: `pytest tests/knowledge/test_obsidian_output_sync.py
  tests/knowledge/test_knowledge_tasks.py -q` passed with `30 passed`.
  Rebuilt and restarted Compose API, Worker, and Beat. Live protected run
  `7b5166d31ba5` completed with
  `output_feedback.scanned=1/registered=0/duplicates=1/rejected=0/blocked=0`;
  Worker inspection returned `pong`. The one scanned file was the existing
  Codex operational receipt. The Copilot route was empty and did not create a
  fictional output.
- Current status: `implemented_with_operational_proof_pending`. The remaining
  external proof is a user-reviewed Copilot Markdown deliverable intentionally
  saved under `04_Outputs/copilot/`, followed by capture, evaluation, and typed
  feedback. No system-generated file may substitute for this Copilot-authored
  action.

## 2026-07-30 Evidence Atlas Scope-Exclusion Projection Closure

- A protected source sync had already quarantined 19 historical records that
  were captured before the mapped-Vault boundary was enforced. Their durable
  audit state is intentionally retained as `rejected`, `source_present=false`,
  with `scope_exclusion.reason=outside_mapped_project_root`; no Vault file,
  source body, or audit record was deleted.
- The read model was then corrected so those records cannot still inflate the
  Evidence Atlas. Overview totals, source lists, media assets, extraction
  artifacts, tables, explicit references, Wiki-citation projections, timeline,
  and graph now share one active-source eligibility filter. Direct Evidence
  Atlas record, table-preview, and image-thumbnail paths return unavailable for
  derivatives of an excluded source, preventing an ID-based inspector bypass.
- Regression: `pytest tests/knowledge/test_wiki_sync.py
  tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_obsidian_output_sync.py
  tests/knowledge/test_multimodal_evidence.py tests/api/test_knowledge_evidence_api.py -q`
  passed with `69 passed, 1 skipped`; `npm run test:frontend -- --run
  src/components/knowledge/EvidenceWorkspace.test.tsx` passed with `10 passed`;
  `npm run check` passed. The new multimodal evidence regression proves that a
  quarantined source and every listed derivative/reference/citation are absent
  from active projections while a mapped source remains visible.
- Deployment and runtime proof: rebuilt and restarted the Compose API image;
  its health check passed. A protected request to the live Evidence Atlas
  returned `151` active sources, `9` assets, `15` extraction records, `1`
  table, `39` references, and `denominator=215`. The response contained zero
  active Copilot records. The three remaining active-projection `rejected`
  sources are separate in-scope quality decisions, not scope-excluded records.
- Status remains `implemented_with_operational_proof_pending`: this removes a
  visualization/data-boundary defect, but does not substitute for a genuine
  reviewed Copilot output and feedback loop.

## 2026-07-30 Active Knowledge Projection Consistency Closure

- Browser acceptance exposed a second-order aggregation defect after the Atlas
  repair: the Evidence Atlas correctly showed `151` active sources, while the
  Knowledge workspace header and source list still displayed the historical
  stored total of `170`. This was an active-view inconsistency, not a missing
  audit record.
- Introduced one shared active-evidence predicate and applied it to the
  workspace status/source list, plugin bridge status inputs, Wiki graph
  visualization, Knowledge Health snapshot/trend, and the tenant-scoped
  operations projection. Source records carrying the mapped-root exclusion
  are therefore excluded before counts, trend points, graph nodes, graph
  edges, citations, health debt, and operations actions are calculated. The
  durable rows and graph edges remain unchanged for audit and repair history.
- The default sources endpoint is now an active operational view. An explicit
  `include_scope_excluded=true` audit query remains available only to an
  administrator or project administrator, returning the existing redacted
  source projection rather than a source body.
- Runtime proof after rebuilding the Compose API: protected workspace,
  sources, graph, and health requests all reported `151` sources. The graph
  reported `85` active relations, and Health reported `38` active citations.
  Browser refresh at `http://127.0.0.1:5174/` confirmed the header's Evidence
  metric is `151` and the Evidence Atlas reports `151 source records`; no
  stale `170 source records` string remained in the rendered active workspace.
- Regression: focused workspace/evidence/graph/health tests passed with `50`
  tests, operations projection tests passed with `5`, and the complete backend
  suite passed with `1539 passed, 14 skipped`. Full frontend regression passed
  with `23 files, 170 tests`; `npm run check`, `npm run lint` (zero errors,
  211 pre-existing warnings), and production build passed. Compose API,
  PostgreSQL, Redis, n8n and Worker were healthy; Worker inspection returned
  `pong`.
- During full frontend validation, one new PBOS strategy-grounding test used a
  unique-text query despite the intended UI showing the same verified strategy
  in both the plan-input and strategy-asset views. The test now asserts both
  instances, preserving the UI behavior and restoring the full suite. No PBOS
  runtime behavior changed in this closure.

## 2026-07-30 Obsidian Copilot Bridge Operational Verification

- Verified the actual Obsidian Vault host rather than the project subfolder:
  `D:\\bsc\\bsc\\.obsidian` has Copilot, Local REST API, Clipper, Importer,
  Docxer, Dataview, Metadata Menu, Zotero, Excalidraw and social-import
  plugins enabled. Claudian remains installed for local history but is not in
  Obsidian's enabled-plugin list.
- Local REST API is listening only on `127.0.0.1:27124`. Authenticated root and
  Vault requests both returned HTTP 200 without logging its credential. Copilot
  saved an actual successful chat receipt using its configured DeepSeek model.
  Copilot API secrets are intentionally stored through Obsidian Keychain and
  were neither read nor copied into BSC.
- Removed the inactive `realclaudian` route from the active project plugin
  manifest. Its historical trust record remains intact for audit; it is no
  longer presented as an executable output bridge. Copilot and Codex retain
  their governed `04_Outputs/` routes.
- Added the native Copilot slash command `BSC 知识审查与沉淀` under
  `D:\\bsc\\bsc\\copilot\\copilot-custom-prompts`. It requires evidence/
  inference separation, project-specific decisions and validation before a
  reusable method or SOP is proposed, and emits the BSC D-layer contract only
  when the user explicitly elects to save a reviewed durable deliverable.
- Ran a real BSC `source_sync` after the bridge verification. Run
  `33d6a8e9ee69` completed through Celery: it scanned one declared Codex D-layer
  file and reported it as one idempotent duplicate, with zero registrations,
  rejections, blocks or skipped files. No Copilot content was fabricated:
  `04_Outputs/copilot/` is still empty and accurately remains
  `awaiting_output`.
- Verified the protected API's active projection: workspace sources `151`,
  Wiki graph total `85`, output registry `11`, Evidence Atlas and Operations
  project views both available. This is a configuration and transport proof,
  not content-quality or feedback-loop proof.
- Remaining real-world proof: a user-reviewed Copilot deliverable must be
  intentionally saved to `projects/default/04_Outputs/copilot/`, captured,
  evaluated, and given feedback before it can support a claim that the Copilot
  D-layer loop is operationally closed.

### Copilot Index Submission

- Discovered the Local REST API command contract from the installed plugin and
  submitted `copilot:index-vault-to-copilot-index` through its authenticated,
  loopback-only endpoint at `2026-07-30T15:38:50Z`. Obsidian returned HTTP 204
  and the listener remained healthy after observation.
- This proves the official index refresh command was accepted; it does not
  expose the asynchronous embedding completion state. Semantic-index coverage
  must therefore remain unverified until Copilot's own indexed-file or search
  UI reports a completed index. No embedding credential, source body, or
  private note content was read during the verification.

## 2026-07-30 Current Project Plugin Capture Bridge And Provider Probe

- Confirmed the deployed provider route with a minimal real request. The
  configured DeepSeek `deepseek-v4-pro` route returned a valid structured
  response; the probe recorded only provider/model and token counts, never
  response content or credentials. This is connectivity proof, not a claim
  that a content-generation workflow has completed.
- Audited the actual Vault host at `D:\\bsc\\bsc`. The managed personal
  project is `projects/proj_b8a285642094`, while the enabled Clipper,
  Xiaohongshu Importer, and Zotero Integration settings still targeted
  `projects/default/...`. Their settings were changed only at the documented
  export-directory fields to the matching current-project A-layer routes:
  `00_Inbox/web-clipper`, `00_Inbox/social`, and `01_Sources/zotero`.
  No plugin source, executable code, unrelated setting, Local REST secret, or
  Copilot credential was read or changed.
- Registered those exact three `filesystem_drop` bridges through the protected
  BSC Workspace API. The durable manifest and trust ledger now report each
  bridge as `trusted`, `path_status=ready`, and
  `runtime_configuration=destination_matches_bridge`. Empty managed target
  folders were created so the plugins have valid destinations; they contain no
  fabricated imports. All bridges therefore honestly remain
  `awaiting_export` / `ready_for_first_export` with zero captured sources.
- Submitted two protected Celery `source_sync` runs after bridge registration
  (`737680c7d635` and `e943c072db62`). Both completed. Each scanned zero new
  bridge files, created/deleted/rejected/blocked zero sources, retained 27
  eligible active records in the evidence mirror, and indexed five Wiki pages.
  This proves the configured bridge scan is idempotent and does not invent a
  user-origin source when no plugin has exported one.
- Post-sync consistency readback: the Vault is ready; active knowledge health
  reports 27 sources, five pages, five citations, no dangling or stale
  citations, no pending proposal, and a passed evaluation baseline of `1.0`.
  The graph visualization contains nine visible nodes and eight active edges.
  A PowerShell absent-property count initially looked like a graph mismatch;
  the authoritative in-container API schema has no dangling/stale fields on
  the graph endpoint, while the Health endpoint is the citation-validity
  authority.
- Browser visual re-acceptance remains unverified in this execution context.
  The controlled in-app browser can only navigate its original `5180` local
  address, but the active authorized Studio is on `5174`; the environment
  rejected background process startup needed to mirror the Vite server to
  `5180`. This is not recorded as a rendering pass or failure. Earlier
  authorized Studio acceptance remains historical evidence only; a future
  browser run must verify the current page at the active authorized port.
- Rollback: set the three documented plugin destination fields back to their
  recorded `projects/default/...` values and replace the project plugin
  manifest with an empty protected Workspace API declaration. This revokes the
  active bridge routes without deleting captured sources, audit records, Wiki
  pages, distillations, or external plugin content.

### Verification

- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_wiki_sync.py
  tests/knowledge/test_obsidian_output_sync.py
  tests/knowledge/test_knowledge_tasks.py tests/knowledge/test_knowledge_graph.py
  tests/api/test_knowledge_workspace_api.py -q` completed with `84 passed,
  1 skipped`. The skip is the existing declared environment boundary.
- `npm run test:frontend -- --run src/components/KnowledgeWorkspace.test.tsx`
  completed with `13 passed`.
- `git diff --check` reported no patch errors. Its only output was the
  existing repository LF-to-CRLF advisory for modified files.

## 2026-07-30 Knowledge Operations Metric Integrity And Runtime Readback

- Confirmed the user-disabled Claudian state against the actual Vault host:
  `realclaudian` is absent from `.obsidian/community-plugins.json` and from
  the active default-project `bsc-plugins.json` bridge declaration. Its prior
  trust record remains historical audit data only; the workspace no longer
  presents it as an available bridge.
- Corrected the operations projection so a governed asset means a persisted
  status-qualified record, not merely a row in a registry. Counts now include
  only `eligible`/`processed` evidence, published Wiki pages and methods,
  accepted/filed outputs, and explicitly reusable memory. `validated`
  evidence, candidate methods, registered/evaluating outputs, rejected,
  retired, and candidate-memory records remain in the authorized audit
  coverage and never inflate the asset or reusable-reference totals.
- Added deterministic output governance actions. Registered/evaluating outputs
  emit `pending_output_evaluation`; rejected, superseded, or archived outputs
  emit `rejected_output`. These actions route to the existing governed Growth
  review surface rather than asserting automatic remediation.
- Updated the Operations Cockpit language to distinguish authorized audit
  coverage from governed assets, label the asset movement series by its status
  gates, and surface pending/attention states explicitly. The qualification
  chart is therefore not a visual claim that generation equals verification.
- Rebuilt and restarted Compose API, Celery Worker, and Celery Beat after
  Docker Desktop's Linux engine recovered. API, PostgreSQL, Redis, n8n, Worker
  and Beat were healthy; Celery inspection returned `pong`.
- Live protected portfolio readback after deployment: 206 authorized audit
  records across two projects, 63 governed assets, 116 records pending a
  validation gate, 64 requiring attention, and 41 deterministic actions.
  The actions included nine pending output evaluations and one rejected-output
  review. These are live operational counts, not fixture values.
- Verified the prior Codex bridge smoke output `fb729180904522df8cf6bfb9` is
  `rejected`, has one persisted evaluation, and has processed feedback
  `a6e7ffca0ec849ea912eaed2`. It remains visible only as negative evidence and
  a governance action, never as a reusable asset.

### Verification

- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_service.py
  tests/knowledge/test_operations_contracts.py -q` completed with `10 passed`.
  The new mixed-status regression proves qualified assets, audit coverage,
  pending validation, attention debt, and output actions remain distinct.
- `npm run test:frontend -- --run
  src/components/operations/KnowledgeOperationsCockpit.test.tsx
  src/components/KnowledgeWorkspace.test.tsx` completed with `21 passed`.
- `docker compose up -d --build bsc-backend celery-worker celery-beat`
  completed successfully, and `docker compose ps` showed a healthy API plus
  live Worker and Beat. `git diff --check` reports no patch errors; its
  line-ending advisories are pre-existing workspace behavior.
- A fresh Studio browser-automation session loaded the deployed Operations
  Cockpit but did not inherit the user's loopback-proxy authorization state;
  its unauthenticated request returned no JSON. The session was closed without
  writing a key to browser storage. This is not recorded as a visual pass or
  a runtime failure: the same deployed Cockpit API completed the protected
  readback above. Visual re-acceptance must use the user's authenticated Studio
  session or an explicitly authorized local login state.
- The overall ecosystem state remains
  `implemented_with_operational_proof_pending`: a real user-reviewed Copilot
  output still has to be saved through the declared `04_Outputs/copilot/`
  route, captured, evaluated, and fed back before the Copilot D-layer can be
  called operationally closed.

## 2026-07-30 Runtime Distillation Contract v28 Proof

- Deployed `GrowthDistillationService.DISTILLATION_CONTRACT_REVISION=28` to
  the Compose API, Worker, and Beat. The revision rejects a daily narrative
  whose `open_question` section has a citation but does not explicitly state
  an uncertainty, evidence gap, or verification need. It neither promotes a
  claim nor changes any source or publication lifecycle state.
- Submitted one protected manual `growth_daily` run for the default project
  with a unique idempotency key. Celery run `e8786b6a0553` reached
  `completed` through the dedicated `knowledge.growth.execute` task. Its
  redacted run metadata reports `generation.mode=llm`, contract revision
  `28`, and one managed output path. No Vault source body, model response,
  prompt, or credential is recorded here.
- Runtime checks after deployment: BSC API readiness was `200`; Worker
  inspection returned `pong`; PostgreSQL, Redis, n8n, and the API/Worker/Beat
  Compose services were healthy. A protected readback confirmed that the
  operations portfolio keeps status-qualified governed assets separate from
  the broader authorized audit count.
- Visual verification supersedes the earlier unauthenticated browser attempt:
  the current local-proxy Studio session loaded both Portfolio and default
  Project Operations views. It showed the lifecycle graph and three charts,
  and at a `390x844` viewport the document/client widths were both `384` with
  no console errors. The default project honestly reports `0/32` risks with a
  complete lifecycle, so unresolved validation and feedback remain action
  work rather than a fabricated success.
- Remaining boundary: a user-reviewed Copilot output still must be explicitly
  saved to its declared D-layer route, then captured, evaluated, and fed back
  before the Copilot output loop can be called closed.

## 2026-07-31 Daily Distillation Evidence-Scope Repair And Live Proof

- Reworked the daily distillation evidence boundary after a live run exposed a
  semantic quality failure: a multi-topic AINews roundup allowed the model to
  cite the unrelated sentence "Slack is the home for great culture" and infer
  agent-policy implications. The source was admissible, but that sentence was
  not project-relevant evidence.
- `GrowthDistillationService` now derives one compact, sentence-aligned
  project-relevant source scope from the active research domains. The complete
  source remains immutable and searchable; an unmatched source is excluded
  only from daily factual synthesis, never deleted or relabeled. The runtime
  manifest records selected and excluded source IDs, while exact source text
  remains out of the D-layer manifest.
- Contract revision `30` requires a daily signal to quote an exact scoped
  source passage and cite that source. Its project implication must cite the
  same source and reuse a concrete quoted term. Invalid model text receives at
  most one corrective render; it otherwise becomes an explicitly marked
  deterministic fallback instead of a fabricated LLM success.
- Real attempts `69bf4271ec56` and `5eb9a54230e6` each reached completed run
  state but their model documents were rejected as `missing_scoped_evidence_quote`.
  Their managed daily revisions were archived rather than discarded. The root
  cause was a second context-budget truncation that supplied sentence fragments
  to the model; it was corrected by emitting one 460-character scope before
  the final attempt.
- Live run `36a4c2e2566e` completed through `knowledge.growth.execute` with
  DeepSeek `deepseek-v4-pro`, contract revision `30`, two bounded provider
  calls, and one quality repair. The accepted distillation is
  `b3adbb5a70df85662245672c` at
  `distillations/每周蒸馏/2026-W31/每日增量/2026-07-31.md`.
  Its direct evidence quote covers asynchronous coding/knowledge-work agents
  supervised from mobile or voice, not the unrelated Slack sentence.
- Verified the final file SHA-256 matches its persisted manifest:
  `a0cbe0ef770b2d5f6a5cca774cc478e8843f5fba041d01eb5c733dc2963a3820`.
  The four prior input-hash revisions remain under the managed `revisions/`
  directory. Rollback is selecting a prior retained revision for review or
  rerunning under a new evidence/input hash; no user-authored file is
  overwritten.

### Verification

- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_growth_distillation.py -q`
  completed with `57 passed`. The added regression creates a multi-topic
  source containing both an irrelevant Slack claim and a relevant agentic
  context-management claim, then proves the former is absent from the scoped
  evidence and cannot pass validation.
- `docker compose up -d --build bsc-backend celery-worker celery-beat` rebuilt
  and deployed the API, Worker, and Beat. PostgreSQL, Redis, API, Worker and
  Beat are healthy; live Celery inspection returned `pong`.
- Runtime readback of run `36a4c2e2566e` confirmed
  `generation.mode=llm`, `provider=deepseek`, `model=deepseek-v4-pro`, a
  resolved PromptOps manifest, one scoped source ID, and no fallback document.

## 2026-07-31 Live Weekly Distillation Proof

- Submitted the manual weekly run only after the successful same-week daily
  growth run. `knowledge.growth.execute` run `d4d428891850` completed with
  DeepSeek `deepseek-v4-pro`, contract revision `30`, and one bounded provider
  call. It did not use a deterministic or hybrid fallback.
- Generated and hash-verified all five distinct weekly outputs under
  `distillations/每周蒸馏/2026-W31/`:
  `00-本周总结.md`, `01-知识行动.md`, `02-内容创作.md`,
  `03-下周上下文包.md`, and `04-方法迭代.md`. Persisted distillation record:
  `c8edc880898b513f8e1d3029`.
- Manual review confirmed that the bundle separates evidence/decision
  boundaries, a bounded verification queue, two content angles, a carry-forward
  packet, and a controlled citation-consistency experiment. All factual
  evidence remains cited to the retained policy-failure Wiki page; proposed
  project actions are labeled as suggestions or verification work.
- Runtime readback proved all five mounted Vault files exist and their SHA-256
  values exactly match the persisted weekly manifest. Both durable schedules
  remain enabled: daily at `0 17 * * *` and weekly at `30 17 * * 5`, timezone
  `Asia/Shanghai`.

## 2026-07-31 Weekly Distillation And Recovery Re-acceptance

- Confirmed the previously abandoned default-project `source_sync` run
  `10f86b2325af` is no longer stuck in `running`. Its protected API readback
  is terminal `failed` with a `knowledge.run.failed` terminal event, while
  the later source-sync runs remain completed. No duplicate source or
  publication was created by recovery.
- Read the protected metadata for weekly distillation
  `1d228616091f09dc796adc1e` without exposing source bodies. It is a generated
  `2026-W31` record with five managed paths, 598 bounded inputs, contract
  revision `28`, an LLM generation, and one quality retry.
- Re-checked the real Vault files under the default project against the local
  manifest. All five files exist, each has at least two `##` sections, at
  least 260 non-whitespace characters, an allowed source/page citation, an
  explicit uncertainty marker recognized by the application validator, and a
  SHA-256 hash matching `manifest.json`. This is a file/manifest proof, not a
  claim that the generated conclusions are independently true.
- The first ad-hoc PowerShell check reported four missing uncertainty markers
  because its inline Chinese regular expression was decoded incorrectly by
  the Windows shell. It was discarded as an invalid check; the authoritative
  application matcher and a UTF-8 Python verification both returned all five
  files valid.

### Verification

- `./.venv/Scripts/python.exe -m pytest
  tests/knowledge/test_growth_distillation.py
  tests/knowledge/test_knowledge_tasks.py -q` completed with `83 passed`.
- `npm run test:frontend -- --run
  src/components/KnowledgeWorkspace.test.tsx
  src/components/operations/KnowledgeOperationsCockpit.test.tsx` completed
  with `21 passed`.
- `npm run check` completed successfully with no TypeScript diagnostics.
- The overall ecosystem state remains
  `implemented_with_operational_proof_pending`: the user-reviewed Copilot
  D-layer output still needs to be saved through the declared
  `04_Outputs/copilot/` route, captured, evaluated, and fed back before that
  loop can be called operationally closed.

## 2026-07-31 PBOS Review Gate And Live Workspace Proof

- Rechecked the live Obsidian host rather than treating configuration files as
  runtime proof. Obsidian was running; its Local REST API was secure
  loopback-only HTTPS on port `27124`, had an owner-configured token, and an
  authenticated read-only root request returned `200`. No plaintext listener,
  token, certificate, plugin credential, source body, or Copilot history was
  copied into BSC or this log.
- The active enabled-plugin inventory contains Clipper, Importer, Docxer,
  Xiaohongshu Importer, Dataview, Metadata Menu, Zotero connectors, Local
  REST API, Excalidraw and Copilot. The actual default project has one older
  Codex D-layer smoke file but zero files in `04_Outputs/copilot/`; this is
  reported as `awaiting_output`, not a completed Copilot delivery.
- Browser acceptance of the running Studio at `127.0.0.1:5174` loaded the
  Personal Growth Cockpit against protected live data. It displayed 22
  governed Vault references, one weekly handoff, three unverified outcomes,
  two reviewable outcomes with verified receipts, and one outcome whose
  missing verified receipt disables acceptance. The rendered lineage and
  outcome-quality views were present. This is a live UI readback, not a
  user-review decision.
- Closed an API/UX integrity gap: the review queue already disabled acceptance
  when evidence was incomplete, but direct callers could previously submit an
  accepted review with only a numeric score. `PBOSService.review_outcome` now
  enforces the same reviewable-execution requirements before it mutates the
  outcome. Rejection remains possible for an unverified result; acceptance
  requires actions, a verified receipt, reflection, and an explicit score.
- Rebuilt Compose API, Celery Worker and Beat with the gate. All dependent
  services were healthy and Worker inspection returned `pong`. A protected
  live acceptance request against a real outcome missing a verified receipt
  returned `422`; the pending count remained `3` and that outcome remained
  `unverified`. The rejection probe made no user-review, source, Wiki,
  method, or output mutation.

### Verification

- `./.venv/Scripts/python.exe -m pytest tests/integration/test_pbos_e2e.py
  tests/pbos/test_pbos_service.py tests/api/test_pbos_api.py -q` completed
  with `38 passed`. The integration case uses the guarded BSC workspace
  capture path rather than a caller-asserted tool receipt.
- `npm run test:frontend -- --run
  src/components/pbos/PersonalGrowthCockpit.test.tsx
  src/components/KnowledgeWorkspace.test.tsx
  src/components/operations/KnowledgeOperationsCockpit.test.tsx` completed
  with `31 passed`.
- `npm run check` completed successfully with no TypeScript diagnostics.
- `docker compose up -d --build bsc-backend celery-worker celery-beat`
  completed successfully after Docker Desktop recovered; `docker compose ps`
  showed a healthy API and live Worker/Beat.
- Remaining external evidence is intentionally explicit: an owner must either
  accept or reject the two evidence-complete PBOS outcomes with their real
  quality scores, and a user-reviewed Copilot output still must be saved to
  `04_Outputs/copilot/`, captured, evaluated and fed back before either loop
  can claim personal learning or Copilot D-layer operational closure.

## 2026-07-31 Live Candidate Extraction And Obsidian D-Layer Route

- Verified the live candidate-extraction admission gate before incurring a
  model call. The Horizon-only signal `65a7de85ced2` was rejected by the
  application with `project_triage_reference_requires_corroboration`; no run,
  candidate, method, Wiki page, or output was created from that uncorroborated
  derivative.
- Selected the admitted primary-web source `6d535597e335` and ran the
  five-way Cangjie extraction against the live PostgreSQL ledger. Run
  `243d9d655c65` completed with ten `pending_review` candidates: one
  framework, three principles, one case, three counterexamples, and two
  glossary entries. Each candidate has one or more evidence anchors whose
  quote is an exact substring of the immutable source. The persisted provider
  ledger records five real DeepSeek calls using `deepseek-v4-flash`; no mock
  or fallback candidate was stored.
- The ten items remain review-only. A single source, even after exact-quote
  validation, is not a published method or a custom SOP. The next promotion
  gate requires real, verified comparable D-layer outputs rather than a
  system-generated claim of repeated success.
- Added governed output bridges for the installed `copilot` and
  `realclaudian` Obsidian agents. The mapped Vault routes
  `04_Outputs/copilot/` and `04_Outputs/claudian/` now exist and are trusted
  for the `filesystem_output` adapter. A live sync scanned zero files and
  registered zero outputs, so both states are correctly
  `ready_for_first_output`, not `registered_output`. No conversation, plugin
  code, prompt history, or synthetic D-layer file was read or copied.
- Re-read all bridge statuses from the running API container. Clipper,
  Xiaohongshu Importer, and Zotero are `trusted`, have ready paths, and their
  read-only destination probes match the declared routes. Copilot and Real
  Claudian are both `trusted` and path-ready; future reviewed files under
  either declared D-layer route are eligible for governed registration.
- Corrected a live Real Claudian configuration defect: its media folder and
  durable-deliverable system prompt had both targeted historical
  `projects/default` paths. They now target this project's
  `04_Outputs/claudian/` route. Added the live Copilot slash command
  `BSC Project Delivery`, which writes only explicit, user-reviewable durable
  deliverables to this project's `04_Outputs/copilot/` route using the BSC
  output-contract frontmatter.

### Verification

- Runtime candidate audit confirmed run `243d9d655c65` is `completed`, lists
  exactly ten candidate IDs, has no failed candidate type, and retains the
  individual provider run IDs without exposing credentials.
- For all ten persisted candidates, the audit recomputed every evidence quote
  check against its referenced immutable source and returned `exact_quotes=True`.
- `ObsidianOutputSyncService.sync` against the live Vault returned
  `scanned=0`, `registered=0`, `duplicates=0`, `rejected=0`, and `blocked=0`.
- `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_candidate_extraction.py
  tests/knowledge/test_obsidian_output_sync.py
  tests/integration/test_growth_output_bridges.py -q` completed with
  `19 passed`.
- After the Compose runtime refreshed, the protected API `/live` endpoint
  returned `{"status":"ok"}` and `celery inspect ping --timeout=15` returned
  one `pong`. The live candidate run remained terminal `completed` after the
  refresh.

## 2026-07-31 Project Context And Live Workspace Re-Acceptance

- Fixed a Studio routing defect where opening Growth from the global header
  could mount the Growth store with its historical `default` project before
  the selected Knowledge project was applied. The header now synchronizes the
  selected project into the Growth store before it mounts the workspace.
- Browser readback at `http://127.0.0.1:5174` selected
  `proj_b8a285642094`, opened Growth, and confirmed the Growth project field,
  project stage rail, API profile, source inventory, and Stage A records all
  use that same project. The workspace showed 30 captured sources, 3 eligible
  sources, 5 Wiki pages, 0 methods, 0 outputs, 5 of 5 configured plugin
  bridges, 9 immutable Horizon signals, and the persisted DeepSeek weekly
  distillation. No `default` project inventory was displayed.
- The first browser request occurred while the Docker API was restarting and
  returned a Vite proxy 500. It was retried only after `/live` returned 200,
  the protected profile and summary endpoints returned 200 through the Vite
  proxy, and Celery reported `pong`. The subsequent UI readback rendered the
  persisted project data successfully.
- Mobile acceptance at 390 by 844 rendered the project selector, command
  controls, health cells, stage rail, and Stage A asset list without overlap.
  The responsive stage rail intentionally uses compact labels while retaining
  their accessible names.
- The durable ledger continues to show completed real runs for daily growth
  (`36a4c2e2566e`), weekly distillation (`d4d428891850`), and candidate
  extraction (`243d9d655c65`). The candidate run remains review-only with 10
  `pending_review` items. C-layer publication and D-layer acceptance were not
  fabricated: no user business output is currently present in the declared
  output bridges, so the correct persisted D count remains zero.

### Verification

- `npm run test:frontend -- src/components/UnifiedWorkspace.test.ts
  src/components/growth/GrowthWorkspace.test.tsx
  src/components/growth/GrowthVisualizations.test.tsx` completed with
  `45 passed`.
- `npm run check` and `npm run build` completed successfully.
- `docker compose ps` showed healthy API, PostgreSQL, Redis, Celery worker,
  Celery beat, and n8n services. Direct and proxied protected reads for
  `proj_b8a285642094` returned the same persisted project summary.

## 2026-07-31 Metadata-Only Bibliographic Reference Projection

- Added a source-reference projector that reads only the persisted source ID,
  project ID, origin and bounded metadata fields. It has no Vault reader,
  HTTP client or original-file write path. It creates idempotent `url`, `doi`
  and `citekey` relationships with hashed target IDs and display anchors.
- Obsidian Zotero provenance now uses the same projection contract after its
  trusted metadata reconciliation. Historical-source repair uses the narrow
  database query rather than rescanning the Vault or selecting source bodies.
- Evidence Atlas target nodes now retain the safe reference anchor and render
  readable URL, DOI and citekey labels. The reference browser and inspector
  remain metadata-only; source and derivative bodies are still excluded from
  the read API and MCP tools.
- Runtime verification rebuilt and restarted only the API service. The
  metadata-only backfill examined 177 default-project source candidates,
  created 93 URL relationships, and a second execution created zero duplicate
  rows while recognizing 93 existing relationships. Aggregate database
  verification reported only `url / declares_url`; no Zotero DOI or citekey
  relationship was claimed because no real Zotero export is present.
- Verification passed: `pytest tests/knowledge/test_reference_projection.py
  tests/knowledge/test_wiki_sync.py tests/knowledge/test_multimodal_evidence.py
  tests/api/test_knowledge_evidence_api.py tests/mcp/test_knowledge_evidence_tools.py -q`
  (`43 passed, 1 skipped`); focused frontend tests (`18 passed`); `npm run
  check`; `npm run build`; and `git diff --check`.
- Celery Worker and Beat were deliberately not restarted for this operation,
  so the verification did not trigger or authorize a Vault synchronization.
  Their normal rolling deployment remains a separate operational action; no
  user Vault file, plugin export, URL, credential or source body was read or
  written by the backfill.

### Execution-Path Deployment Follow-Up

- Performed a controlled Worker/Beat rolling deployment after their active,
  reserved and scheduled queues each reported empty. The rebuilt API, Worker
  and Beat all loaded `SourceReferenceProjector`; Celery inspection returned
  one `pong`.
- The Worker task ledger recorded zero `source_sync` runs at or after its new
  container start time. No synchronization, external capture or Vault-body
  read was triggered as part of deployment. Future API and Celery capture
  paths now share the deployed idempotent metadata-reference behavior.

## 2026-07-31 Local Studio Proxy Recovery And Metadata-Only Acceptance

- Added a regression test for `scripts/provision_local_api_access.ps1` using
  a temporary project with intentionally duplicated, stale Studio proxy keys.
  The test verifies that provisioning retains only one backend `API_KEY`,
  synchronizes exactly one `BSC_LOCAL_API_KEY`, preserves unrelated settings,
  and never emits the credential in its JSON result.
- Corrected `Set-EnvValue` so provisioning replaces the first matching key
  and removes subsequent duplicates. This makes the backend and Vite proxy
  configuration deterministic instead of reporting a successful write while
  leaving multiple candidate values in place.
- Ran the provisioner without `-Rotate`. The local backend and Studio values
  are now single-entry and equal, as verified by a non-secret equality check,
  lengths and a truncated one-way fingerprint. No credential was logged.
- Restarted only the Vite Studio process on `127.0.0.1:5174` through
  `start_authorized_studio.ps1`. An unauthenticated browser-side request to
  `/knowledge/workspaces` returned `200`; the protected direct API request
  also returned `200`, and the proxy response contained no credential echo.
- Browser acceptance reopened `Personal Knowledge Intelligence` under its
  authorized project scope. The project showed a connected Vault, five
  verified plugin routes, persisted Horizon run state, five published Wiki
  pages, 28 evidence records, 32 relations and 100% citation coverage. A
  persisted URL source was selected in Evidence Atlas and its metadata-only
  inspector displayed origin, provenance, hash, trust and status without
  exposing a source body.
- At `390x844`, Evidence Atlas, its source filter and selected metadata
  inspector remained accessible with no document-level horizontal overflow.
  The in-app browser host did not honor its attempted desktop viewport
  override, so that host cannot be cited as a desktop-width visual proof in
  this run. Existing desktop component tests remain the current desktop
  coverage; the live mobile result is not misrepresented as desktop evidence.

### Verification

- `./.venv/Scripts/pytest.exe tests/test_local_api_provision.py
  tests/test_authorized_studio_launcher.py -q` completed with `2 passed`.
- Local proxy verification returned `proxy_status=200`, `direct_status=200`,
  one visible authorized project response and `proxy_has_credential_echo=false`.
- The provisioning flow did not rotate a secret, read a Vault or source body,
  write any original knowledge file, call an external service, or trigger a
  source synchronization task.

## 2026-07-31 Evidence Atlas Composition And Truthful Zero-State Repair

- Replaced the misleading derivative-first Evidence Atlas summary. The first
  view now leads with persisted Sources and References, retains Assets and
  Derived records as distinct lifecycle layers, and does not imply that a
  project with zero assets/extractions/tables has zero usable evidence.
- Replaced the empty-only `Extraction states` chart with an ECharts evidence
  composition view for sources, assets, extractions, tables and references.
  Each category is a persisted-record count with an explicit type color,
  accessible chart description and keyboard-operable filter control. Selecting
  a category filters the existing metadata inventory; it does not create or
  alter evidence.
- The live authorized project read returned `state=available`, `28` sources,
  `0` assets, `0` extractions, `0` tables and `32` references. The response
  envelope was checked only for countable arrays and top-level field names;
  no source body, raw content, prompt or provider response field was present
  or read.
- The compact composition control switches to two columns below 520px, so five
  evidence categories do not compress into an unreadable single row on mobile.
- A first runtime probe used the obsolete evidence URL and returned `404`.
  Its empty PowerShell object was discarded and not recorded as evidence. The
  follow-up used the client contract route and returned `200`.

### Verification

- Added and passed focused regression coverage for a source/reference-only
  project and for accessible composition filtering. `npm run test:frontend --
  --run src/components/knowledge/EvidenceWorkspace.test.tsx
  src/components/KnowledgeWorkspace.test.tsx` completed with `25 passed`.
- Full frontend regression completed with `180 passed`; `npm run check` and
  `npm run build` completed successfully. The build retains the existing
  ECharts bundle-size warning; it is not hidden or treated as a pass/fail
  result.
- `./.venv/Scripts/pytest.exe tests/api/test_knowledge_evidence_api.py
  tests/mcp/test_knowledge_evidence_tools.py -q` completed with `5 passed`.
- This increment has real API and automated UI proof. A new browser screenshot
  is intentionally still pending because the previous controlled browser
  session had already been finalized before this source change.

## 2026-07-31 Evidence Atlas Metadata-Only Regression Boundary

- Replaced the Evidence Atlas source and Wiki citation reads with dedicated
  metadata projections. These queries select source identity, provenance,
  status, hashes and citation lineage only; they do not select source
  `raw_content` or citation `claim_text`. The regular full-record repository
  methods remain available to governed compiler and publication paths and were
  not changed.
- Added recursive response assertions for `raw_content`, `content`,
  `claim_text`, `prompt` and `provider_response` to the Evidence Atlas API
  regression. Added a stronger route-level test that rejects the old full
  source/citation readers, rejects non-`SELECT` SQL, rejects body-column SQL,
  and blocks outbound `socket.create_connection` calls while exercising the
  overview and citation-record routes.
- No Vault path was opened, no source or derivative body was read, no network
  service was contacted, and no original file or database record was written
  by this read-only verification.

### Verification

- `./.venv/Scripts/pytest.exe tests/api/test_knowledge_evidence_api.py
  tests/mcp/test_knowledge_evidence_tools.py -q`: `6 passed`.
- `./.venv/Scripts/pytest.exe tests/knowledge/test_multimodal_evidence.py
  tests/knowledge/test_reference_projection.py
  tests/api/test_knowledge_evidence_api.py
  tests/mcp/test_knowledge_evidence_tools.py -q`: `20 passed`.
- `git diff --check`: passed. The remaining warning is the repository's
  existing CRLF normalization notice, not a whitespace error.

## 2026-07-31 Governed Information Brief And Horizon Review Queue

- Added a deterministic daily intelligence brief over completed BSC ingress
  batches. It returns receipt lineage, capture/duplicate/confirmation/reject
  counts and bounded failure metadata, never an evidence body or derivative
  body. Empty windows explicitly return `no_sample`; Feishu delivery remains
  `unavailable` until a real delivery integration is configured.
- Corrected legacy, offset-free information-ingress timestamps to use the
  product's Asia/Shanghai operating timezone. This prevents an early-day
  completed batch from disappearing from its local daily brief.
- Added a Horizon review queue to daily and weekly growth distillations. A
  radar signal remains a review item until primary-source verification and
  Wiki review; a source already cited by a Wiki page is excluded by both the
  citation ledger and the persisted `wiki_cites_source` lineage edge. The
  queue renders only title, URL, score and lifecycle metadata, not its source
  body.
- Added the project-scoped REST and MCP read contracts plus the Studio
  information-operations panel. It distinguishes BSC receipt state from feed
  configuration and exposes a confirmation queue instead of presenting
  discovery as knowledge.
- Runtime readback of `proj_b8a285642094` after API rebuild reported a
  `ready` Vault boundary and a `no_sample` daily brief with zero source IDs;
  the response contained no `raw_content` field. This is a truthful absence
  of a completed signed ingress batch in the current window, not a claim that
  Horizon, n8n or Feishu delivery has run.
- Rebuilt only the API and Worker from the verified working tree. Before the
  Worker replacement its dedicated queue had length zero; after startup it
  connected to Redis and reported ready. Beat was intentionally not restarted
  because this project has enabled daily and weekly schedules. No source sync,
  ingestion, distillation or original-file write was triggered.

### Verification

- Focused backend boundary suites: `141 passed`.
- Full backend suite: `1587 passed, 14 skipped`.
- Full frontend suite: `186 passed`; `npm run check` and `npm run build`
  passed. `npm run lint` returned zero errors and 214 existing warnings.
- PostgreSQL contract suites: `5 passed`; Evidence Atlas/MCP offline boundary:
  `6 passed`. The temporary PostgreSQL project-row audit returned zero after
  cleanup.
- Compose configuration and `git diff --check` passed. The rebuilt API health
  endpoint returned `200`; PostgreSQL, Redis, n8n, Worker and Beat remained
  healthy. At `390x844`, Studio had no document-level horizontal overflow.

### Operational Status

- This increment is `implemented_with_operational_proof_pending`, not
  `release_ready`: a real signed n8n ingress batch, real primary-source
  confirmation, real Feishu delivery and user-reviewed D-layer feedback remain
  external/user-owned evidence gates. They were not fabricated or bypassed.
