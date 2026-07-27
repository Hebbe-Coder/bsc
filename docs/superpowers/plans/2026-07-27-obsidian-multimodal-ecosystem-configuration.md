# Obsidian Multimodal Knowledge Ecosystem Configuration Plan

**Design authority:** `docs/superpowers/specs/2026-07-27-personal-knowledge-ecosystem-closure-prd.md`
**Status:** Ready for staged implementation
**Execution model:** `O1 -> O2 -> O3 -> O4 -> O5 -> O6`; O4 backend extraction and O5 visualization may run in parallel after O2 data contracts freeze.

## Current Verified Baseline

- Vault root is `D:\bsc\bsc`; BSC's managed project root is `projects/default`.
- Existing source synchronization imports Markdown, text, JSON, and Canvas as immutable evidence. PDF, image, spreadsheet, audio, and video files are retained only as unsupported provenance today.
- Installed and enabled plugins are Dataview `0.5.68`, Metadata Menu `0.8.12`, Excalidraw `2.25.3`, Zotero Integration `3.2.1`, Zotero Notes Sync `0.1.2`, Local REST API `5.0.2`, Clipper, Importer, Docxer, Xiaohongshu Importer, and Claudian.
- React Flow is already a BSC frontend dependency and must not be installed in Obsidian.
- Local REST API already uses port `27124` with its insecure server disabled. Its existing token was not read or changed; operation scope and loopback access still require verification.
- Excalidraw still uses its default `Excalidraw/` folder and must be moved through its settings UI to the declared project map route before BSC indexes drawings.

## Cross-Plan Contracts

- BSC database records are authoritative for lifecycle, permissions, immutable content hashes, evaluation, and audit. Dataview, Bases, Canvas, and generated index notes are read-only views of that authority.
- Obsidian plugin installation does not prove source capture. A bridge changes from `verified_route` to `captured` only after an actual user-created export becomes an immutable project `SourceRecord`.
- BSC may read declared project paths and generate managed index/projection files. It must not edit `.obsidian` executable plugin code, overwrite user source notes, or expose plugin tokens in a note, API, log, or prompt.
- `Local REST API` remains optional. Filesystem projection remains the supported integration baseline until localhost-only access, token storage, scope, and redaction tests pass.
- Raw source files, PDFs, images, spreadsheets, media, and their extraction artifacts remain separate records. No re-extraction overwrites user content or immutable evidence.

## O1 - Inventory, Backup, And Local REST API Boundary

**Depends on:** None
**Owned files:** `.obsidian` configuration only after backup; BSC configuration documentation and focused integration tests.
**Do not modify:** Plugin JavaScript/CSS, user notes, raw source files, or BSC database rows.

1. Export a timestamped backup of the Vault's `.obsidian` JSON configuration before changing plugin settings. Do not include source content or credentials in the backup report.
2. Confirm the active plugin list and versions, enabled core plugins (`Properties`, `Bases`, `Canvas`, `Backlinks`, `Graph`, `Templates`, `Daily Notes`), and project-level BSC route manifest.
3. Configure Local REST API through its Obsidian settings UI for loopback-only access. Disable LAN exposure, CORS wildcards, write/delete operations, directory traversal, and unauthenticated access.
4. Generate or enter the Local REST API token only in the plugin setting or an ignored runtime secret store. Never place it in a Markdown note, `bsc-plugins.json`, Git, browser state, or a generated index.
5. Do not connect BSC to Local REST API in this task. First verify that a loopback unauthenticated request is rejected and that an authorized read exposes only the configured project path.

**Acceptance commands / checks:**

```powershell
Get-Content 'D:\bsc\bsc\.obsidian\community-plugins.json' -Raw
Get-ChildItem 'D:\bsc\bsc\.obsidian\plugins' -Directory
```

**Acceptance evidence:** redacted plugin/config inventory, Local REST API configured as loopback/token-only, no token printed.

**Rollback:** restore only the backed-up plugin JSON settings. Do not delete the plugin or its user data unless explicitly requested.

## O2 - Canonical Metadata And Obsidian View Contract

**Depends on:** O1
**Owned files:** Project `AGENTS.md`, managed project view/index notes, Metadata Menu field configuration, optional Bases definitions.
**Do not modify:** Immutable source projection bodies, published Wiki pages outside a governed proposal, `.obsidian` plugin code.

1. Freeze the logical A/B/C/D-to-path mapping from the PRD and display compatibility aliases instead of creating duplicate writable locations.
2. Configure Metadata Menu fields for these project-scoped properties:

```text
bsc_id, project_id, asset_kind, source_url, canonical_url, citation_key,
source_date, captured_at, trust_level, review_status, freshness,
extraction_status, related_sources, related_pages, table_refs, image_refs,
method_refs, output_refs, feedback_status, managed_by_bsc
```

3. Use select, date, link, multi-link, and read-only field controls where supported. `bsc_id`, hashes, capture time, and managed flags are BSC-controlled fields; users may not edit them to change lifecycle authority.
4. Create a managed `Knowledge Index` folder under the mapped project directory containing standard Markdown/Dataview views for Inbox, sources needing review, published Wiki pages, method candidates, registered outputs, feedback debt, stale references, and extraction failures.
5. Enable Obsidian Bases views for local table exploration where available. Base filters must be equivalent to documented frontmatter and must not encode hidden authorization or lifecycle logic.

**Test-first work:** add parser/renderer tests that verify generated frontmatter matches the frozen field vocabulary, contains no secret field, and does not create a second source capture route.

**Acceptance:** open each generated Dataview/Base view in Obsidian with an empty-data state and a populated fixture; each row opens its BSC/Obsidian record; generated views are excluded from source capture.

**Rollback:** remove only BSC-marked managed index notes and restore the Metadata Menu field backup. Existing user notes, sources, pages, and methods remain untouched.

## O3 - Plugin Routing And Real Export Verification

**Depends on:** O2
**Owned files:** `bsc-plugins.json`, plugin trust manifest, route tests, managed index links.
**Do not modify:** Third-party plugin source code, user note contents, raw capture files after they arrive.

1. Keep Clipper exporting to `projects/default/00_Inbox/web-clipper/` and validate one genuine clipped article with original URL, canonical URL, title, capture time, and content hash.
2. Configure Xiaohongshu Importer to `projects/default/00_Inbox/social/`; validate one genuine exported post and retain source URL/platform provenance without treating a social claim as verified fact.
3. Configure Docxer and Obsidian Importer to choose `projects/default/01_Sources/docxer/` and `projects/default/01_Sources/importer/` during their import flow. Their interactive destination selection remains visible as an operator step.
4. Configure Claudian output routing to `projects/default/04_Outputs/claudian/`. Validate that a real output becomes a D-layer candidate and is not re-imported as A-layer source evidence.
5. Configure Excalidraw creation/export under `projects/default/03_Projects/active/maps/` with embedded images under the project's attachments directory. Only drawings explicitly linked to a project are eligible for BSC indexing.
6. Configure Zotero Integration and Zotero Notes Sync to create notes under `projects/default/01_Sources/zotero/` with citation key, DOI/URL, author, publication date, abstract, attachment reference, and item key. Configure Zotero Desktop plus Better BibTeX only after the user chooses the intended library and citation-key pattern.

**Test-first work:** add project-route validation and sync fixtures for every export folder; test capture, duplicate, unsupported media, output registration, and forbidden unlisted paths.

**Acceptance:** each enabled source-producing plugin performs one real export; BSC records immutable provenance and the workspace changes bridge status to `captured`. Claudian output changes to `registered` only after output registration. No plugin status is upgraded by a manual folder creation alone.

**Rollback:** disable the individual bridge in the manifest. Existing captured source/output records remain auditable; no original export file is deleted.

## O4 - Multimodal Asset, Extraction, And Reference Platform

**Depends on:** O2 data contract
**Owned files:** Knowledge schema/repository, capture adapters, extraction workers, source/reference APIs, tests, and managed projections.
**Do not modify:** Raw source body/hash semantics, existing Artifact Graph authority, existing MCP transport semantics.

1. Add `MediaAsset`, `ExtractionArtifact`, `TableArtifact`, and `ReferenceLink` contracts with project/tenant isolation, content hashes, extractor revisions, retention state, and typed anchors.
2. Implement extraction adapters in this order: PDF/document text and page anchors; spreadsheets/CSV and typed tables; image metadata/OCR and reviewable regions; Excalidraw/Canvas elements; audio/video transcripts and timestamped segments.
3. Preserve originals separately from extracted text. Track `complete`, `partial`, `failed`, `unsupported`, `restricted`, and `needs_review` honestly per artifact.
4. Add a bounded primary-web capture/URL normalization pipeline that retains requested and final URL, title/publisher/date when available, capture hash, outbound-reference list, and safe recrawl policy.
5. Add Zotero import adapter mapping citekey, DOI, item key, bibliography data, note references, and attachment provenance into `SourceRecord`/`ReferenceLink` without copying restricted attachment content by default.
6. Extend citation parsing and rendering for page, heading, block, table cell, image region, media timestamp, citekey, and captured URL anchors.

**Test-first work:** fixtures for a text PDF, scanned PDF/OCR failure, image with OCR uncertainty, CSV/XLSX with units/missing data, Canvas, Excalidraw, URL canonicalization, missing reference, restricted asset, and cross-project reference rejection.

**Acceptance commands:** focused Python contract/repository/API tests, worker retry tests, a full knowledge regression, `python -m compileall -q app/knowledge`, and `git diff --check`.

**Rollback:** feature flags disable individual extractors; raw source and media records remain intact. Derived artifacts can be regenerated from immutable assets and are never deleted as a hidden rollback step.

## O5 - Evidence Visualization And Obsidian/BSC Dual Views

**Depends on:** O2; may proceed in parallel with O4 using fixtures
**Owned files:** Workspace APIs, knowledge frontend/store/components, generated Obsidian view templates, browser tests.
**Do not modify:** Existing DBOS graph semantics, portfolio authorization, or user-authored Vault layout.

1. Add Evidence Atlas, Reference Browser, Table Explorer, Image/Figure Inspector, Research Timeline, Reference Network, and Workspace Map to the Knowledge workspace.
2. Use ECharts for bounded trends/distributions and React Flow for typed lifecycle/reference projection. Provide an accessible table/list alternative for every chart/graph.
3. Add source type, extraction state, review state, trust, freshness, project, period, relation, and derived/original filters. Every interaction opens an exact persisted record.
4. Generate lightweight Dataview and Bases views that mirror the same concepts locally without carrying raw source bodies or overriding BSC state.
5. Show data window, filters, denominator, units, source/table artifact, freshness, and no-sample state on every visualization. Charts using tables link to transformation provenance.

**Test-first work:** API redaction/scope tests, chart no-sample tests, typed anchor drill-down tests, large-table pagination tests, graph aggregation tests, desktop/mobile Playwright acceptance, keyboard and reduced-motion checks.

**Acceptance:** desktop and 390x844 mobile render nonblank visualizations with no horizontal overflow; a selected chart value, image region, table cell, URL, and graph edge each open the same authorized evidence target.

**Rollback:** hide the new views behind feature flags and retain APIs/contracts. No source, extraction, or index data is removed.

## O6 - Operational Proof, Governance, And Handoff

**Depends on:** O3, O4, O5
**Owned files:** Release worklog, runbook, acceptance fixtures, PRD/plan status updates.
**Do not modify:** User raw material, third-party plugin code, credentials, or external accounts without an explicit action request.

1. Execute three real review cycles using user-origin or approved external material. Each cycle must contain source admission/rejection, a reviewable B change, and an action outcome.
2. Demonstrate one source reference from each enabled route, one table or image anchor, one Zotero item, and one visual map through BSC-to-Obsidian-and-back inspection.
3. Demonstrate a method applied to a real output and typed feedback updating a later review/action.
4. Document all unavailable provider/plugin/extractor states and do not count fixtures, repeated distillation revisions, or empty folders as value proof.
5. Record changed files, commands/results, deviations, runtime versions, rollback procedure, and remaining user-owned configuration in a new worklog entry.

**Release gates:** full backend/frontend regression, Compose API/Worker/Beat proof, tenant/project isolation, browser desktop/mobile verification, no secret in diff/logs, and `git diff --check`.

**Handoff output:** a configuration matrix that lists each plugin, its enabled version, route, security posture, current status, last real export, BSC source/output IDs, and rollback procedure.

## User Actions Reserved For Last

- Choose the Zotero Desktop library and whether Better BibTeX should own citation keys. This affects existing personal bibliography data and cannot be guessed safely.
- Enter Local REST API token only in Obsidian's plugin settings or an ignored secret store after loopback-only configuration is visible.
- Perform one genuine clip/import/Zotero sync/Claudian output action per configured route. BSC will not manufacture these external artifacts.
