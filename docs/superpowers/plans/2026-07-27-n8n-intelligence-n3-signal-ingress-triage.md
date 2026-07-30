# N3 - Signal Ingress, Receipt Ledger, And Triage

## Goal

Implement the versioned, project-scoped SignalBatch ingress that converts a
bounded n8n discovery batch into auditable receipt decisions and existing BSC
source-triage inputs.

**Dependencies:** N1 contract accepted.
**May run in parallel with:** N2 after N1.
**Blocks:** N4 and N5.

## File Boundary

**Create:** SignalBatch request/receipt types, additive receipt/run persistence,
project-bound ingress authorization, canonicalization/idempotency service, REST
endpoint, read-only MCP/API receipt reads, and focused authorization/contract
tests.

**Modify:** existing SourceRecord capture and source-triage orchestration only
through an additive adapter boundary.

**Do not modify:** source registry policy semantics, n8n Compose deployment,
provider fetch implementation, LLM derivative generation, Feishu delivery,
Wiki/Skill publication policy, Artifact Graph semantics, or raw body retention
rules beyond their existing capture interface.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** versioned SignalBatch, project-bound ingress credential, existing
  project profile and capture/triage policies.
- **Outputs:** one KnowledgeRun-compatible batch run, per-item receipt status,
  safe reason code, durable BSC source/lead ID when applicable, and traceable
  audit relations.
- **Authorization:** the credential resolves to one tenant/project and the
  signal-ingress capability only. Claimed project ID must match the credential.
- **Redaction:** batch list/receipt endpoints and MCP tools expose metadata,
  counts, status, and safe reason codes. They never expose provider secrets,
  raw payload, source body, prompt, or unrelated project identifiers.

## Test-First Tasks

1. Add failing tests for unknown schema version, missing/invalid key,
   cross-project request, malformed URL, provider/origin mismatch, invalid
   timestamp, oversized batch, duplicate execution with changed hash, and replay.
2. Freeze the SignalBatch schema from the PRD and define receipt statuses:
   captured, duplicate, lead_only, rejected, partial, and failed. N3 is the
   only plan allowed to change this vocabulary.
3. Implement project-bound authorization, request-size limits, URL
   canonicalization, provider validation, per-execution hash, and deterministic
   item idempotency.
4. Persist batch run and receipt ledger records with tenant/project scopes,
   configuration/schema revision, safe failure category, timestamps, and links
   to existing capture/triage/audit records.
5. Route acceptable items to the existing immutable capture surface or a
   lead-only/rejected decision. Separate discovery metrics from trust
   assessment and primary-source confirmation requirements.
6. Expose authorized REST and read-only MCP receipt/run inspection. Preserve
   existing transport behavior when n8n is disabled or no batch exists.
7. Hand N4 stable request/response fixtures and N5 bounded read models for
   successful, duplicate, lead-only, partial, rejected, and unavailable runs.

## Acceptance

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_n8n_signal_ingress.py tests/knowledge/test_source_triage.py -q
./.venv/Scripts/python.exe -m pytest tests/api/test_n8n_signal_ingress_api.py tests/mcp/test_n8n_signal_receipts.py -q
git diff --check
~~~

The acceptance result must prove replay stability, cross-project denial,
redaction, source/receipt lineage, and that a high-engagement discovery signal
does not become a trust or citation score.

## Rollback, Worklog, And Handoff

Disable the ingress feature flag and revoke only the scoped ingress credential
if necessary. Retain receipts, admitted immutable sources, triage decisions,
and audit records. The handoff includes API/schema revision, migrations,
authorization matrix, tests, fixture-versus-real status, safe run/receipt IDs,
known compatibility gaps, and rollback result.
