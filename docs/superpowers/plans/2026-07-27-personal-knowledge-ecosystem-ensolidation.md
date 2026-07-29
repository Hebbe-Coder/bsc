# E1 - Personal Knowledge Ecosystem Ensolidation

## Goal

Integrate the first independently developed O1-O6 slices into one release
candidate, verify their contracts together, and make the only authoritative
release status decision for this PRD.

**Depends on:** O1, O2, O3, O4, O5 and O6 each passing its declared acceptance
gate.
**Exclusive authority:** cross-plan integration order, compatibility decisions,
release status and final worklog reconciliation.

## Owned Surfaces

**Create:** integration acceptance harness, release matrix and consolidated
handoff evidence.
**Modify:** cross-plan index, shared worklog, feature-flag/release
documentation, and only the documented compatibility seams required to join
accepted leaf plans.
**Do not modify:** third-party plugin code, user sources, raw evidence bodies,
credential stores, or an accepted leaf plan's domain semantics without first
reopening its contract and updating the PRD.

## Entry Gate

- Each leaf plan supplies its first-round handoff: changed files, migration
  IDs, JSON examples, feature flags, test output, rollback point and actual
  external evidence status.
- No leaf may be accepted merely because its API, UI or folder exists.
- E1 stops immediately on an undocumented contract change, pending migration,
  source-body leak, cross-project access defect, or fabricated capture/value
  claim.

## Input, Output, Permissions, And Redaction

- **Inputs:** only the documented O1-O6 first-round handoff packets and the
  integrated build. E1 rejects undocumented files, migration revisions,
  fixture-to-production substitutions and status claims unsupported by the
  shared worklog.
- **Outputs:** the cross-plan release matrix, compatibility decisions,
  integration test results, rollback matrix and exactly one final status:
  `release_ready`, `implemented_with_operational_proof_pending` or
  `not_release_ready`.
- **Access:** consolidation retains the original tenant/project authorization
  checks at every seam. It cannot use administrator access to mask a failed
  project-key or project-user isolation probe.
- **Redaction:** reports and release evidence contain only bounded metadata,
  identifiers, commands and safe result summaries. They may not aggregate raw
  source/derivative bodies, credentials, prompts, provider payloads, local
  paths or third-party plugin configuration.

## Test-First Integration Gate

Before changing a compatibility seam, add or amend a focused failing test that
reproduces the integrated defect against the frozen O1-O6 contracts. The test
must exercise the actual seam rather than a substituted mock: migration order,
feature-flag isolation, route-to-evidence lineage, project authorization,
REST/MCP redaction, or browser drill-down. Record the initial failure and its
scope in the shared worklog. A green leaf-plan test suite does not waive this
gate when the integrated build fails or exposes a contract mismatch.

## Consolidation Tasks

1. Freeze the metadata, route, extraction, reference and evidence-read API
   contracts. Resolve overlaps by updating the PRD, index, affected leaf plan
   and worklog before changing code.
2. Apply migrations in dependency order on isolated SQLite and PostgreSQL
   databases; verify legacy knowledge projects, existing A/B/C/D records,
   scheduled distillations and project keys remain compatible.
3. Assemble a single feature-flag matrix. Disable paths independently without
   deleting source, media, extraction, proposal, output, feedback or audit
   records.
4. Run end-to-end scenarios: trusted plugin route -> immutable source ->
   extraction/anchor -> reviewable Wiki/method/output -> feedback -> changed
   later action; include unauthorized tenant/project probes and unavailable
   tool/provider behavior.
5. Rebuild Compose services and verify API, PostgreSQL, Redis, Worker and Beat.
   Exercise REST and MCP read paths with redacted responses, then perform
   desktop and `390x844` browser journeys with nonblank chart/graph checks.
6. Consolidate leaf handoffs into the worklog and configuration matrix. Record
   exact commands, screenshots, runtime versions, deviations, unresolved
   external conditions and rollback procedures.

## Release Status Rules

Set `release_ready` only when all of the following are true:

- O1-O6 acceptance results are current and pass against the integrated build.
- Real project-scoped source, extraction/reference, B/C/D lineage and feedback
  evidence exists; project/tenant isolation is verified.
- Obsidian secure-boundary restart verification and at least the declared real
  plugin exports have occurred.
- Compose, Celery recovery, REST/MCP redaction, desktop/mobile accessibility
  and no-secret checks pass.

Otherwise set `implemented_with_operational_proof_pending`, list every missing
proof item, and leave the affected feature state visible as awaiting, disabled
or unavailable. Never infer release readiness from fixtures, generated files,
an empty Vault route or a successful UI render.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest
npm run test:frontend
npm run check
npm run lint
npm run build
docker compose --profile full config
git diff --check
```

E1 additionally requires the O6 real-cycle matrix and fresh browser evidence.
It records the final status in the shared worklog and does not commit, publish
or change user knowledge unless separately requested.

## Worklog Reconciliation

For every E1 execution, reconcile O1-O6 handoffs against the integrated build
and append the exact test/browser/Compose commands, exit results, migration
order, feature-flag matrix, durable IDs, deviations, external conditions, and
rollback decision to the shared worklog. E1 rejects missing evidence rather
than rewriting it as success. Only this reconciliation can set
`release_ready`; otherwise it records
`implemented_with_operational_proof_pending` or `not_release_ready`.

## Failure, Rollback, Worklog, And Handoff

Use the feature-flag matrix to disable the failing surface, roll back only the
additive migration/application release where needed, and retain all immutable
source and audit records. A rollback result is `not_release_ready`, never a
deleted history.

The E1 handoff is the reconciled release matrix: all O1-O6 packets, the frozen
contract revision, applied migration order, feature-flag matrix, exact command
and browser results, real-versus-fixture evidence classification, unresolved
external conditions, and the final status. It is delivered to the release
owner only after the worklog reconciliation below; it does not authorize a
commit, publish, or change to user knowledge by itself.
