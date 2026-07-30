# N4 - Governed n8n Derivatives Workflow

## Goal

Transform the supplied information-aggregator workflow into a sanitized,
BSC-governed n8n workflow for first-release RSS/Channel RSS collection,
normalization, optional LLM derivatives, and receipt-aware completion.

**Dependencies:** N2 and N3 accepted handoffs.
**Blocks:** N5 and C1.

## File Boundary

**Create:** sanitized n8n workflow export, workflow README/import procedure,
source-to-SignalBatch mapping, derivative provenance mapping, test fixtures, and
optional feature-flagged LLM configuration contract.

**Modify:** n8n workflow assets and the narrow BSC adapter client required to
submit batches and read receipts.

**Do not modify:** n8n runtime/Compose topology, Source Registry persistence,
SignalBatch semantics, source admission policy, Feishu app configuration,
Obsidian plugin code, user/provider credentials, or existing DeepSeek
credential configuration.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** N2 source registry/normalization examples, N3 frozen batch and
  receipt contracts, user-owned n8n runtime after N1, and optional LLM
  credentials configured inside n8n only.
- **Outputs:** an importable workflow with no credentials, no hard-coded user
  sources, no direct authoritative Feishu writes, and no enabled schedule until
  the owner explicitly activates it.
- **Authorization:** the workflow uses the scoped BSC ingress credential only
  for its bound project. An optional BSC receipt read is scoped to the execution
  just submitted.
- **Redaction:** workflow export includes placeholder credentials and
  environment variable names, never values. Logs and notifications contain safe
  receipt counts/statuses, not raw provider body, secrets, or local Vault data.

## Test-First Tasks

1. Add a structural failing test that rejects workflow exports containing n8n
   credential values, direct Feishu Bitable authority writes, unbounded broad
   HTTP notification nodes, active schedules by default, or non-RSS first-round
   connectors.
2. Define a first-release workflow path: manual/scheduled trigger ->
   configured RSS/Channel RSS fetch -> source-registry normalization -> bounded
   relevance prefilter -> SignalBatch submission -> receipt polling ->
   completed/partial/unavailable operator result.
3. Preserve original title, URL, identifiers, publication time, source registry
   ID, and limitations. Date conversion distinguishes source publication time,
   n8n observation time, and BSC capture time.
4. Add optional translation, summary, and classification nodes after raw
   normalization. Attach model/provider/revision and source linkage; label their
   output as a derivative and allow a provider-unavailable path.
5. Replace direct Feishu storage/card paths with BSC receipt-aware delivery
   inputs. A notification may be emitted only after a completed BSC receipt
   ledger and may describe partial/provider failures.
6. Disable X, Reddit, YouTube Data API, and TikTok branches in the exported
   workflow. Document their future prerequisites without carrying their
   credential IDs, account names, static queries, or paid API assumptions.
7. Simulate success, duplicate, lead-only, partial provider failure, malformed
   item, and LLM unavailable paths with N3 fixtures. Hand N5 the receipt-backed
   daily brief payload contract.

## Acceptance

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_n8n_workflow_contract.py tests/knowledge/test_n8n_signal_ingress.py -q
docker compose --profile n8n config
git diff --check
~~~

An optional n8n import/run is successful only if the imported workflow shows no
secret values, starts disabled, submits a project-scoped batch, and records a
BSC receipt. A workflow that only renders or sends a Feishu card is not accepted.

## Rollback, Worklog, And Handoff

Disable the workflow schedule and BSC adapter feature flag; retain the sanitized
export and BSC receipts. Do not delete user n8n credentials, executions, or
provider accounts. The handoff includes workflow revision/hash, import steps,
node-to-contract map, structural test result, fixture simulation output,
provider-unavailable behavior, changed files, and rollback action.
