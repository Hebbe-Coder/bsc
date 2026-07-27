# n8n Information Intelligence Execution Index

## Authority And Scope

This index executes
docs/superpowers/specs/2026-07-27-n8n-governed-information-intelligence-prd.md.
It supersedes the implementation role of
docs/superpowers/plans/2026-07-27-n8n-information-aggregator-adapter.md, which
remains historical architecture context. Existing A/B/C/D, Horizon, Artifact
Graph, MCP transport, and Obsidian contracts remain unchanged.

The initiative is a governed source-discovery capability, not an automatic
knowledge-publication feature. The consolidation plan owns the release decision.

## Dependency Order

~~~text
N1 Runtime Compose
  -> N2 Source Registry RSS -----------+
  -> N3 Signal Ingress Triage ---------+-> N4 Derivatives Workflow
                                             -> N5 Operations Delivery
                                                  -> C1 Consolidation
~~~

N2 and N3 may proceed in parallel after N1 passes its contract gate. N4 starts
only after their contract revisions are frozen. N5 starts only after N3/N4
handoffs pass. C1 starts only after N1-N5 each deliver a current handoff packet.

## Leaf Plans

| ID | Plan | Exclusive responsibility | Depends on |
| --- | --- | --- | --- |
| N1 | 2026-07-27-n8n-intelligence-n1-runtime-compose.md | Optional n8n runtime, local exposure, encryption, feature flag, health, rollback | None |
| N2 | 2026-07-27-n8n-intelligence-n2-source-registry-rss.md | Project source policy, RSS/Channel RSS normalization, first-release source state | N1 |
| N3 | 2026-07-27-n8n-intelligence-n3-signal-ingress-triage.md | SignalBatch API, authorization, receipts, capture, triage, idempotency | N1 |
| N4 | 2026-07-27-n8n-intelligence-n4-derivatives-workflow.md | Sanitized workflow, derivative provenance, BSC receipt readback | N2, N3 |
| N5 | 2026-07-27-n8n-intelligence-n5-operations-delivery.md | Operations read model, workspace, daily brief, managed delivery/projections | N3, N4 |
| C1 | 2026-07-27-n8n-information-intelligence-consolidation.md | Integration, real-cycle evidence, release decision | N1-N5 |

## Frozen Cross-Plan Contracts

- **Authority:** BSC owns source lifecycle, project authorization, receipts,
  evidence, triage, schedules, audit, and delivery state. n8n owns only
  provider acquisition and its local credentials.
- **SignalBatch:** N3 owns the schema and status vocabulary. N2/N4/N5 consume
  it and may not add fields or reinterpret statuses without a PRD/index change.
- **Source trust:** discovery metrics and LLM derivatives never become source
  trust or citation confidence. N3 owns the admission transition.
- **Credentials:** no plan reads, moves, logs, tests, or commits user/provider/
  Feishu/n8n secret values. N1 defines n8n runtime injection; N3 defines the
  separate BSC ingress capability.
- **First-release source scope:** only RSS and YouTube Channel RSS may become
  enabled. Other connectors remain feature-gated unavailable integrations.
- **Delivery:** N5 may notify only from BSC receipt-backed projections. It
  cannot make Feishu or Obsidian a second writable lifecycle authority.

## Shared Engineering Rules

Every plan begins with a focused failing test for its owned contract. Each
handoff includes changed files, contract/migration revisions, feature-flag
state, exact test output, fixture-versus-real evidence classification, safe
durable IDs, outstanding external actions, and a scoped rollback procedure.

Plans may not modify third-party Obsidian plugin code, user source files,
provider terms, existing Artifact Graph storage/semantics, raw evidence bodies,
or credential stores. Cross-plan changes require a PRD and index revision before
implementation.

All actual work, verification, deviations, external dependencies, rollbacks,
and commits are appended to
docs/superpowers/worklogs/2026-07-27-n8n-information-intelligence.md.
An API, container, or chart alone is not evidence of a completed
information-to-knowledge cycle.
