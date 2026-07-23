# Feishu A/B/C/D Knowledge Growth Operating Standard

**Status:** Implemented as an additive product standard; live user-Vault adoption remains separately auditable.
**Date:** 2026-07-23
**Source studied:** authenticated Feishu document `XBXYdZDrXoWb6hxtITqc6PQSn8m`, revision `644`.
**Product authority:** `docs/superpowers/specs/2026-07-22-bsc-abcd-knowledge-growth-product-prd.md`.
**Worklog:** `docs/superpowers/worklogs/2026-07-22-abcd-knowledge-growth.md`.

## 1. Extracted Operating Model

The reference workflow is a compounding loop, not a collection of folders:

```text
External and work material -> A raw evidence -> B distilled knowledge
  -> C reusable Skill/method -> D real output -> reviewed feedback -> A/B/C
```

Its operational ingredients are multi-channel capture (Horizon, Web Clipper, social import, Feishu CLI, Importer and Docxer), regular daily/weekly distillation, reusable topic/style methods, and outputs such as articles, dashboards, illustrations, presentations and video. Each output is useful input for the next review, but it is not factual evidence by default.

## 2. BSC Enforcement Matrix

| Reference operation | BSC product enforcement | Completion evidence |
|---|---|---|
| Put original material in A | Immutable `SourceRecord`, SHA-256 identity, project ownership, original URI/path, capture/source time, extraction state and attachments | Source API omits raw content from list views and retains provenance in the record |
| Capture from many tools | Declared Obsidian `filesystem_drop` bridges accept only `00_Inbox/`, `01_Sources/`, `raw/` or `inbox/`; Horizon has an explicit staged-artifact adapter | Bridge capture count is persisted only after a source is created or matched |
| Bring Feishu documents and meeting review into A | User selects an explicit Feishu CLI/export JSON in Studio; `POST /knowledge/sources/feishu/import` validates document/revision/source URL, rejects credentials, creates a `feishu_import` run and captures `feishu_document` or `feishu_minutes` evidence | Source metadata and ordered run events retain source ID/type/revision, never token content |
| Distil A into B | Triage applies reliability as a hard gate; Wiki maintenance emits a reviewable proposal with citations, lint/evaluation and rollback | Published pages have source references, revisions and graph edges |
| Turn repeated work into C | Method detection evaluates comparable real outcomes, evidence grounding, quality and failure patterns before a method proposal can publish | Method revision, evaluation cases and approval state are persisted |
| File every real output into D | BSC/Obsidian output bridges register immutable outputs with context, method, run, evidence/page lineage and evaluation state | D registration never changes the external original and remains pending until evidence review |
| Let outputs improve future work | Accepted, grounded output may create a B or C proposal; correction and rejection become regression/failure records; generated output never directly becomes factual A evidence | Feedback route and lineage are visible in the growth workspace |
| Review on a stable cadence | `growth_daily` runs at 17:00 and `growth_weekly_distillation` runs at Friday 17:30, `Asia/Shanghai`; both write managed, revision-preserving distillation artifacts | Schedules, runs, retries and source cutoffs are durable records |

## 3. Non-Negotiable Rules

1. A-layer source bytes are not rewritten. A changed external document becomes a new version and supersedes the prior record.
2. No integration stores an API key, access token, authorization header or secret-bearing error in a source, run, event, prompt or workspace response.
3. A file existing in an Obsidian folder is not proof of connection. A bridge is active only after persisted source capture or output registration.
4. Daily/weekly jobs may collect, triage, distil and propose. They do not silently publish Wiki claims or approve methods.
5. D-layer artifacts may guide style and method learning only after evaluation. They may not substitute for external factual evidence.
6. Every cross-stage relationship is project-scoped. Project permission checks apply to source, run, proposal, output, graph and MCP access.

## 4. Studio Operating Path

1. Map the project-relative Vault and initialize the managed Wiki baseline.
2. Register only the actual export paths of installed capture/output tools. Never execute or introspect arbitrary `.obsidian` plugin code.
3. For Feishu, use **Import Feishu** in the Knowledge Workspace to select one user-authorized CLI/export JSON. The product validates and imports the document or meeting summary as A evidence.
4. Inspect the resulting Evidence item and `feishu_import` run. Promote only after the normal triage/review path.
5. Run or schedule **Growth cycle**. Inspect daily and weekly run counts before treating a source bridge or output bridge as adopted.
6. Review B proposals, C method proposals and D evaluation feedback through their existing publication gates.

## 5. Acceptance Standard

- A Feishu document or meeting summary imported twice under one project yields one immutable source identity and two auditable runs; the first creates and the second reports a duplicate.
- The visible source retains document type and revision, while list responses omit raw evidence.
- A supplied credential field is rejected before capture and never appears in persisted source/run records.
- A captured Feishu source remains `validated` until the same reliability/triage rules as other A-layer material allow its use in B.
- Daily and Friday distillation consume only governed project material and produce reviewable records, not fabricated completion states.
- Any assertion that the user's real Vault or plugin is connected requires an authenticated Studio action and a persisted captured/registered count. Fixture success is not substituted for that evidence.

## 6. Current Boundary And Rollback

The direct Feishu import path is intentionally an explicit export handoff. It does not scrape Feishu, call undocumented internals, reuse browser credentials, or fetch content in the background. This preserves user control and keeps the third-party authentication boundary outside BSC.

Rollback is additive: disable or remove the Studio action/endpoint while retaining immutable source and run history. Existing sources can be superseded or rejected through the lifecycle; they are never silently deleted to hide a previous import.
