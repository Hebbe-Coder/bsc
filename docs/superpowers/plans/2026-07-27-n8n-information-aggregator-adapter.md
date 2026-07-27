# N8N Information Aggregator Adapter

## Goal

Connect the supplied n8n information-aggregator workflow to BSC as a bounded,
project-scoped **discovery producer**, without allowing social/news summaries,
Feishu tables, or engagement metrics to bypass the A/B/C/D knowledge lifecycle.

**Depends on:** O1 integration boundary and the frozen source/triage contracts.
**Optional:** this plan is not a prerequisite for the O1-O6 closure while the
adapter feature flag is disabled. If enabled, its real-cycle handoff is required
by O6 and E1.

## Owned Surfaces

**Create:** the versioned SignalBatch ingress contract, adapter configuration,
receipt/read model, focused tests, redacted operator runbook, and configuration
matrix entry.

**Modify:** BSC knowledge ingress/triage and scheduled-run surfaces only where
the frozen source contracts need an additive adapter implementation. The n8n
workflow is modified only in its own n8n instance after the BSC contract is
accepted.

**Do not modify:** third-party provider terms, Obsidian plugin code, user Vault
content, raw source bodies outside BSC policy, existing Horizon semantics,
Artifact Graph semantics, existing A/B/C/D lifecycle meaning, or any credential
value/store.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** the supplied workflow as a design baseline, a BSC project profile,
  approved providers/topics, and credentials configured only by their owners in
  n8n or ignored BSC runtime configuration.
- **Outputs:** per-execution BSC run ID, SignalBatch receipt ledger, one
  project-scoped adapter configuration revision, safe error categories, and an
  optional redacted daily-notification payload.
- **Authorization:** n8n has a least-privilege BSC project key limited to signal
  ingress for one project. Provider keys remain in n8n. BSC rejects a claimed
  project ID that does not match the credential's bound project.
- **Redaction:** tests, responses, worklogs, screenshots, notification payloads,
  and audit summaries may include safe IDs/counts/reason codes only. They must
  exclude secrets, provider response bodies, raw source content, Vault paths,
  prompts, and external-account identifiers.

## Test-First Tasks

1. Add focused failing API/domain tests proving that unknown schema versions,
   cross-project requests, duplicate execution IDs, malformed canonical URLs,
   and oversized batches are rejected without creating any source record.
2. Implement an additive versioned SignalBatch endpoint and receipt model. Use
   project-scoped authorization, deterministic per-item idempotency, and the
   exact status set `captured`, `duplicate`, `lead_only`, `rejected`, `partial`,
   and `failed`.
3. Route accepted candidates through the existing immutable capture and source
   triage paths. Preserve original provider fields and distinguish
   discovery/engagement metrics from trust assessment and citation eligibility.
4. Add a feature-flagged n8n adapter configuration with topic policy, provider
   allow/deny list, timezone, rate/batch limits, retention/right policy,
   retry policy, and rollback state. Do not start a schedule merely because its
   configuration exists.
5. Configure a copy of the n8n workflow only after tests pass: replace direct
   authoritative Feishu/Bitable writes with the BSC SignalBatch ingress and
   send notifications only from a completed BSC receipt. Keep DeepSeek-derived
   translations/classifications as labelled derivatives.
6. Add contract tests for a replay, a partial provider failure, a lead requiring
   primary-source confirmation, an unavailable credential, and a daily brief
   that does not claim zero/new information when a provider failed.
7. Execute one explicitly approved real, bounded project run. Verify BSC receipt
   IDs, source decisions, review queue state, redaction, and the disable path.
   This step remains pending until an n8n instance and provider credentials are
   actually configured by their owner.

## Acceptance

```powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge tests/api tests/integration -q
./.venv/Scripts/python.exe -m pytest tests/mcp -q
npm run test:frontend
npm run check
git diff --check
```

For an enabled adapter, the owner also supplies a redacted n8n execution ID and
the BSC receipt/run IDs. The acceptance gate fails if a direct Feishu row is
reported as a captured source, an LLM derivative replaces the original evidence,
a duplicate replay changes counts, a cross-project request is accepted, or a
provider failure is presented as an empty successful run.

## Rollback, Worklog, And Handoff

Disable the adapter feature flag and its n8n schedule first; revoke or rotate
only the scoped BSC ingress key if required. Retain immutable sources, receipts,
and audits. Do not delete n8n executions, user content, or provider credentials
as a rollback shortcut.

The handoff contains the contract version, changed files, feature flag,
configuration revision, test output, safe BSC run/receipt IDs, provider status,
real-versus-fixture classification, pending owner actions, and rollback result.
Append every activation, retry, failure, and disable action to
`docs/superpowers/worklogs/2026-07-27-personal-knowledge-ecosystem-closure.md`.
