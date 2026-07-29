# O6 - Operational Proof And Release Evidence

## Goal

Demonstrate that the configured ecosystem changes later knowledge, methods or
actions through real project-scoped work, and prepare the evidence required by
E1 without manufacturing business value.

**Depends on:** O4 and O5.
**Blocks:** E1.

## Owned Surfaces

**Create:** operational runbook, configuration matrix, acceptance fixtures and
release evidence in the shared worklog.
**Modify:** schedule/runbook documentation and feature-flag configuration only
when a verified operational need requires it.
**Do not modify:** raw user material, third-party plugin code, external
accounts, credentials, or published knowledge without the governed approval
path.

## Proof Scenarios

1. Complete three distinct project cycles. Each contains an admitted or
   rejected source, a reviewable B-layer change, a stated next action and an
   outcome recorded without claiming unsupported causal value.
2. Demonstrate one real export for every enabled producer route, including a
   Zotero item, one map or Canvas/Excalidraw asset, and at least one table or
   image anchor. A disabled or unavailable route is documented, not omitted.
3. Demonstrate an evaluated method applied to a real output, then typed output
   feedback that changes a later claim, proposal, method boundary, context pack
   or action priority.
4. Verify daily `17:00` and Friday `17:30` `Asia/Shanghai` schedules preserve
   their established idempotency, source cutoff and weekly revision semantics.
5. Restart Obsidian and complete O1's runtime proof: plaintext `27123` is
   closed and unauthenticated secure Local REST reads are rejected.

## Input, Output, Permissions, And Redaction

- **Inputs:** passing O4/O5 handoffs, immutable project records, route and
  capability matrices, schedule configuration and user-approved real exports.
  Test fixtures, empty folders and generated summaries are labelled as such
  and cannot satisfy a proof scenario.
- **Outputs:** a project-scoped configuration matrix, durable run/audit IDs,
  status transitions, exact command results, browser evidence paths and a
  release-evidence packet for E1. A failed or unavailable external boundary
  is an output state, not omitted evidence.
- **Access:** operational probes use only the authorized project, tenant or
  local service account required for the test. Isolation tests must prove
  denial rather than using elevated credentials to bypass the boundary.
- **Redaction:** the worklog stores identifiers, timestamps, result codes and
  safe error summaries. It never stores source bodies, Local REST tokens,
  API keys, provider payloads, private plugin settings, screenshots of
  sensitive material or third-party account data.

## Test-First Tasks

1. First write a focused failing release-evidence test or harness assertion
   for each required proof field, then create a fixture checklist that
   distinguishes real records from test fixtures, empty folders, generated
   summaries and repeat revisions.

## Implementation Tasks

2. Run the defined cycles with user-origin or explicitly approved external
   material. Preserve sources and audit IDs; do not paste bodies or secrets
   into the worklog.
3. Produce a configuration matrix: plugin/version, route, adapter, trust,
   security posture, current status, last real export, BSC source/output ID,
   feature flag and rollback procedure.
4. Execute project/tenant isolation, source-to-feedback lineage, retry/recovery,
   Compose API/Worker/Beat and desktop/mobile browser proof.
5. Record actual commands, results, runtime versions, deviations, residual
   user-owned actions and rollback points. Do not label the project release
   ready; E1 owns that decision.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge tests/integration -q
npm run test:frontend
npm run check
npm run build
docker compose --profile full config
git diff --check
```

The worklog must contain durable IDs and status transitions for all real
cycles, or explicitly state `operational_proof_pending` for each missing
external action.

## Failure, Rollback, Worklog, And Handoff

Pause the affected schedule or feature flag and retain records for audit. Hand
E1 the configuration matrix, test output, browser proof, real-cycle evidence,
unavailable states and no unreported credentials. The packet must distinguish
real user-origin records from fixtures, record each pending external action,
list all feature flags and include the scoped rollback command or procedure.
The shared worklog records only exact commands, run/audit IDs, status
transitions, timestamps, safe result summaries, runtime versions, deviations,
pending owner actions, and rollback results. It cannot infer an operational
proof from preparation, a scheduled task, a fixture, or a rendered page.
