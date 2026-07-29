# Personal Knowledge Ecosystem Implementation Index

**PRD:** `docs/superpowers/specs/2026-07-27-personal-knowledge-ecosystem-closure-prd.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-27-personal-knowledge-ecosystem-closure.md`
**Status:** Split into independently owned implementation plans.

## Delivery Order

```text
O1 Integration boundary
  -> O2 Metadata and views
  -> O3 Plugin routes
  -> O4 Multimodal extraction --+
  -> O5 Evidence visualization -+-> O6 Operational proof -> Ensolidation
```

O4 and O5 may begin after O3 freezes route metadata and O2 freezes the field
vocabulary. O5 uses O4's fixture contract until real extraction APIs are
available. No implementation plan may begin the release gate; only
`2026-07-27-personal-knowledge-ecosystem-ensolidation.md` owns integration
status and release readiness.

## Plan Registry

| ID | Plan | Depends on | Exclusive ownership |
| --- | --- | --- | --- |
| O1 | `2026-07-27-knowledge-ecosystem-o1-integration-boundary.md` | none | Obsidian configuration backup and Local REST boundary evidence |
| O2 | `2026-07-27-knowledge-ecosystem-o2-metadata-views.md` | O1 | metadata registry, managed indexes, source-sync exclusion |
| O3 | `2026-07-27-knowledge-ecosystem-o3-plugin-routes.md` | O2 | plugin manifest, trust, route status and export capture proof |
| O4 | `2026-07-27-knowledge-ecosystem-o4-multimodal-extraction.md` | O3 | asset/extraction/reference records and local extractors |
| O5 | `2026-07-27-knowledge-ecosystem-o5-evidence-visualization.md` | O3 | evidence read APIs, workspace UI, charts and evidence graph |
| O6 | `2026-07-27-knowledge-ecosystem-o6-operational-proof.md` | O4, O5 | real-cycle proof, runbook and release evidence |
| E1 | `2026-07-27-personal-knowledge-ecosystem-ensolidation.md` | O1-O6 | migration sequencing, end-to-end gates and final status |

## Frozen Cross-Plan Contracts

- BSC records remain authoritative for permissions, immutable source hashes,
  lifecycle, evaluation, audit and project isolation. Obsidian, Dataview,
  Bases, Canvas and generated index notes are read-only projections.
- Artifact Graph, knowledge lineage and DBOS remain separate durable stores.
  Project-scoped references can be projected but neither graph changes the
  other graph's persistence semantics.
- A plugin installation, a route declaration, an empty directory, a queued
  task, or a rendered chart never proves capture, extraction, approval,
  verification, value, or reuse.
- No plan may expose raw source bodies, prompts, provider payloads, Local REST
  API credentials, or third-party plugin secrets through Markdown, API, MCP,
  browser state, logs, tests, or worklogs.
- Existing A/B/C/D, weekly distillation, MCP transport, Artifact Graph,
  project-key behavior, and Knowledge Operations dashboard semantics are
  compatibility boundaries, not refactor targets.

## Global Engineering Rules

- Write or amend focused failing tests before production changes. Each plan
  runs its acceptance command and appends actual results, deviations, rollback
  point and open dependencies to the shared worklog.
- A project key and project user can access only their authorized project.
  Tenant portfolio behavior remains server-authorized; no client enumeration
  of project IDs is permitted.
- Generated views, BSC evidence projections, output snapshots, temporary
  extractor files and distillation products must be excluded from broad source
  capture unless a dedicated governed import path says otherwise.
- Every external boundary has explicit `unconfigured`, `verified_route`,
  `awaiting_export`, `captured`, `conflict`, `disabled`, or `unavailable`
  behavior. Missing data is never converted to a favorable metric or status.
- Each plan may change only its owned surfaces. Any shared contract change
  requires an update to this index, the PRD, affected leaf plans and the
  worklog before implementation proceeds.

## Required Leaf-Plan Template

Every O-plan must state its goal, dependencies, owned files/surfaces and
explicit non-goals; begin with a focused failing test before implementation;
and publish exact acceptance commands, observable failure states and a scoped
rollback procedure. Each plan must also define its input/output contract,
project authorization and redaction rules, plus the evidence that its owner
hands to the next plan. A task that has only an API, folder, mock, rendered
view or fixture is `implemented` at most; it cannot claim real operational
proof.

Every plan appends a dated shared-worklog entry after each implementation or
verification attempt. The entry names the exact command, exit result, fixture
or durable record ID, observed deviation, external dependency, and rollback
point. A proposed command, an inferred result, or a future user action is not
an execution record.

## First-Round Handoff

Each leaf plan hands E1: changed-file list, migration identifiers, public
JSON examples, fixture identifiers, exact test/build output, feature flags,
known unavailable dependencies, and an explicit claim of whether any real
user-origin export was observed. E1 rejects undocumented or fabricated
completion claims.
