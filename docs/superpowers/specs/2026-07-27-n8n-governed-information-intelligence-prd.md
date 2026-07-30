# BSC Governed Information Intelligence PRD

**Status:** Proposed implementation authority
**Date:** 2026-07-27
**Owners:** BSC knowledge platform, Dynamic Business OS, and authorized project owner
**Extends:**

- docs/superpowers/specs/2026-07-27-personal-knowledge-ecosystem-closure-prd.md
- docs/superpowers/specs/2026-07-21-karpathy-llm-wiki-knowledge-growth-prd.md
- docs/superpowers/specs/2026-07-27-knowledge-operations-visualization-prd.md

## 1. Product Decision

This product turns the supplied n8n information aggregator into a governed,
project-scoped information-intelligence surface for BSC. It does not turn n8n,
Feishu Bitable, a social post, an LLM summary, or an engagement score into a
knowledge authority.

~~~text
project information policy
  -> source registry and n8n discovery
  -> normalized SignalBatch
  -> BSC authorization, deduplication, capture, and triage
  -> evidence assessment and review queue
  -> Obsidian A/B/C/D projections and project context
  -> daily brief, weekly distillation, output feedback, and later policy change
~~~

The first release uses an optional Compose-managed n8n service, disabled by
default. It starts with configured RSS and YouTube Channel RSS sources only.
X/Twitter, Reddit, YouTube Data API, and TikTok are future adapters. They stay
disabled and visibly unavailable until a project owner configures valid
credentials, accepts the provider cost and terms, and enables that adapter.

## 2. Input Analysis And Product Boundary

The supplied n8n information aggregator JSON is an 87-node, inactive workflow
intended to run daily at 08:00. It collects public RSS, Reddit, YouTube,
X/Twitter, and TikTok signals; filters by recency and engagement; calls
DeepSeek for Chinese translation/classification; writes rows to Feishu Bitable;
and produces Feishu interactive-card payloads. Its generic HTTP notification
nodes have no target URL. The export references n8n credential records but
contains no usable credential values.

The accompanying tutorial establishes a useful five-stage method:

1. Run n8n continuously through Docker.
2. Discover information with RSS, channel feeds, and optional APIs.
3. Normalize dates and apply source-specific filters.
4. Use an LLM for readability and relevance classification.
5. Archive and notify through a human-facing system.

BSC retains the method while correcting direct Feishu storage, hard-coded
global AI queries, unconfigured notification endpoints, dependence on
paid/unavailable APIs, ambiguous date fields, credential portability, and no
proof that a successful HTTP call produced trustworthy knowledge.

## 3. Users, Jobs, And Authority

| User | Decision job | Required capability | Authority boundary |
| --- | --- | --- | --- |
| Knowledge owner | Decide what sources and discoveries deserve attention | Configure project source policy and review receipts | Cannot treat n8n output as verified knowledge |
| Project lead | Decide what changed in the active project | Inspect fresh signals, risks, and confirmation queue | Cannot read another project by identifier |
| Researcher/content owner | Use verified material in a deliverable | Inspect original, derivative, citation, and feedback | Cannot cite an unverified social summary as fact |
| Tenant administrator | Govern source health, cost, and risk | See authorized aggregate operations state | Cannot read raw source bodies by default |
| n8n worker | Fetch approved external signals | Submit batch and read its project receipt | Cannot publish Wiki, Skills, or outputs |
| AI agent | Retrieve bounded context and propose work | Use authorized BSC API/MCP reads | Cannot read provider/n8n/Feishu credentials |

BSC is authoritative for project authorization, source records, immutable body
or retained reference, triage, assessments, citations, proposals, runs,
schedules, output feedback, and audit. Obsidian is the human-readable working
surface. n8n is an external-information producer. Feishu Bitable and cards are
optional notification/projection sinks. Horizon remains a separate discovery
adapter and follows the same admission policy.

## 4. Source Policy And First-Release Scope

Every source belongs to a project-local Source Registry record with owner,
source class, canonical URL/feed URL, topic tags, language, freshness limit,
allow/deny state, rights/retention policy, schedule eligibility, and failure
state. Global source lists never silently populate every project.

| Adapter | First-release state | Evidence rule | State before configuration |
| --- | --- | --- | --- |
| Publisher/official RSS | Enabled when declared by project | Preserve feed ID, URL, date, title, excerpt, and fetch provenance | unconfigured |
| YouTube Channel RSS | Enabled when declared by project | Preserve channel ID, video URL, time, title, and limitation | unconfigured |
| X/Twitter | Deferred | Social post is a lead; factual claims need primary confirmation | unavailable |
| Reddit | Deferred | Community post is a lead with lawful provenance | unavailable |
| YouTube Data API | Deferred | API metrics are discovery metrics, not verification | unavailable |
| TikTok/RapidAPI | Deferred | Third-party retention limits remain visible | unavailable |
| Horizon | Existing optional adapter | Score and stage remain discovery provenance | current configured/unavailable state |

The project policy may prioritize official sources, named publishers, a bounded
industry set, or user-declared channels. It may not use views, likes, shares,
comments, or viral-score thresholds as a proxy for source trust.

## 5. Architecture And Lifecycle

The Compose profile exposes n8n on a local-only management port and persists its
own encrypted runtime data in a named volume. It is disabled unless the n8n
profile and feature flag are both enabled. n8n provider credentials stay in its
credential store. BSC holds a distinct least-privilege project key for signal
ingress. Neither service reads, writes, logs, exports, or derives the other's
credential.

~~~text
RSS / Channel RSS
  -> n8n source adapter
  -> source-specific normalization and bounded relevance prefilter
  -> BSC SignalBatch ingress using a project-bound credential
  -> receipt ledger and source admission
  -> immutable SourceRecord or lead_only/rejected record
  -> trust assessment, corroboration task, and review action
  -> BSC/Obsidian projection and optional daily notification
~~~

The lifecycle is additive:

~~~text
discovered -> received -> duplicate | lead_only | rejected | captured
captured -> triaged -> admitted | confirmation_required | blocked
admitted -> may support a Wiki proposal -> reviewed/published under existing policy
~~~

No n8n execution, dashboard render, Feishu write, or scheduled run can skip a
state or be reported as a published knowledge asset.

## 6. SignalBatch And Receipt Contract

n8n submits a versioned batch to a project-scoped BSC ingress. BSC rejects
unknown versions, missing/incorrect project authorization, oversized batches,
malformed or provider-mismatched URLs, invalid dates, and duplicate execution
IDs that do not match the original payload hash.

~~~json
{
  "adapter": "n8n-information-aggregator",
  "schema_version": "1",
  "adapter_revision": "<workflow-revision>",
  "execution_id": "<n8n-execution-id>",
  "project_id": "<BSC-project-id>",
  "collected_at": "2026-07-27T00:00:00Z",
  "items": [
    {
      "external_id": "<provider-stable-id>",
      "provider": "rss|youtube_channel_rss|x|reddit|youtube_api|tiktok|horizon",
      "source_class": "official|publisher|community|social|video|aggregator",
      "canonical_url": "https://example.invalid/item",
      "published_at": "2026-07-27T00:00:00Z",
      "observed_at": "2026-07-27T00:00:00Z",
      "title": "<provider title without LLM rewrite>",
      "excerpt": "<bounded provider excerpt>",
      "author_or_channel": "<optional>",
      "source_registry_id": "<project source registration>",
      "discovery_metrics": { "views": 0, "likes": 0, "comments": 0 },
      "selection_reasons": ["fresh", "topic_match"],
      "source_limitations": ["requires_primary_confirmation"],
      "raw_payload_hash": "<optional retained-payload hash>"
    }
  ]
}
~~~

Receipt entries are deterministic and return captured, duplicate, lead_only,
rejected, partial, or failed, a safe reason code, and the durable BSC ID when
one exists. The idempotency key includes project, adapter, execution identity,
external identity or canonical URL, and content hash. A replay returns the
original decision and never increments asset or dashboard counts.

Discovery metrics and selection reasons are immutable discovery provenance.
They are never copied into trust assessment, citation confidence, or method
effectiveness. BSC captures a lawful original body, a restricted external
reference, or a precise lead_only explanation. An LLM derivative can never be
the only retained source body for a claim.

## 7. Functional Requirements

### FR-1 Runtime And Configuration

- Compose defines an optional n8n service, named data volume, local-only admin
  binding, health check, runtime encryption secret, feature flag, and
  non-destructive disable path.
- Startup does not import a workflow, enable a schedule, or create provider
  credentials automatically.
- The BSC project profile declares source policy, schedule/timezone, batch
  ceiling, retry policy, retention rules, and enabled adapter state.
- When the first-release RSS workflow is explicitly activated, its default
  collection cadence is daily at `08:00 Asia/Shanghai`. A project owner may
  pause it or set a project-local cadence through the governed schedule
  configuration; neither configuration change may start an unavailable adapter.

### FR-2 Source Registry And RSS Acquisition

- Source Registry changes are project-authorized, revisioned, auditable, and
  validated before a source is scheduled.
- RSS and Channel RSS normalization preserves provider IDs and original URLs;
  timestamps are normalized to UTC while preserving the displayed source date.
- Fetch failure, unreadable feed, redirect violation, malformed item, or policy
  exclusion creates a visible source/run state, never a zero-item success.

### FR-3 Triage And Evidence Admission

- BSC performs authorization, schema checks, canonicalization, deduplication,
  retention checks, source classification, and lifecycle decision before a
  source is available to Wiki, Skill, SOP, or content generation.
- High-impact claims from social/community/video material create a
  primary-source-confirmation task unless project policy accepts corroboration.
- Rejection and lead_only retain a safe audit reason and do not erase the
  discovery event.

### FR-4 LLM Derivatives

- Translation, summary, relevance classification, and category labels are
  versioned derivatives with provider/model/revision, source IDs, input hash,
  output hash, and failure state.
- Derivatives are review aids, label uncertainty, and never overwrite provider
  title/body or an approved Wiki page.
- A missing provider key or failed LLM call produces unavailable/failed;
  source admission continues when raw-source policy permits it.

### FR-5 Daily Brief And Delivery

- The daily brief is generated from completed BSC receipts only. It separates
  captured evidence, confirmation-required leads, duplicates, and failures.
- Feishu delivery is optional and consumes a redacted BSC projection. Delivery
  failure cannot roll back BSC capture or make the run unrecorded.
- Obsidian receives managed projections through the existing Vault mapping;
  n8n never writes arbitrary Markdown into the Vault.

### FR-6 Operations And Visualization

- The Knowledge Workspace exposes source registry state, adapter state,
  run/receipt outcomes, source limitations, confirmation queue, daily brief,
  and links to exact authorized records.
- Aggregates display project, time window, denominator, filter, and no_sample,
  partial, or unavailable state. No chart invents quality, growth, accuracy, or
  business value.
- Daily growth and weekly distillation consume admitted evidence and feedback
  through existing semantic-delta rules. Unchanged input creates a no-op.

## 8. Security, Reliability, And Compliance

- n8n management access is local by default. It may not expose an unauthenticated
  public admin port or accept BSC data through a broad webhook.
- Provider credentials, BSC keys, Feishu credentials, raw payloads, source
  bodies, Vault paths, prompts, and model payloads are excluded from list APIs,
  worklogs, notifications, browser captures, and metrics.
- All adapters have timeout, rate-limit, retry, rights, and deletion behavior.
  A retry retains execution identity and cannot overwrite an admitted source.
- Schedules record queued, running, completed, partial, failed, unavailable, or
  cancelled with durable timestamps and safe errors.
- Provider use honors declared terms, robots/rate policies, copyright, privacy,
  sensitivity, and project exclusions before retention or model use.

## 9. Non-Goals

- Rebuilding Horizon, a general RSS reader, a social crawler, or a BI platform.
- Treating public attention as factual truth, model relevance as source trust,
  or a summary as original evidence.
- Auto-publishing Wiki pages, Skills, SOPs, or content from n8n discoveries.
- Migrating n8n credentials from the supplied export or storing credentials in
  Git, a Vault note, or the BSC database.
- Enabling paid/restricted connectors merely because their nodes exist.

## 10. Acceptance And Definition Of Done

The system is only release_ready when all conditions are proven:

1. Disabled n8n leaves existing BSC, Celery, Horizon, Obsidian, and A/B/C/D
   behavior unchanged; enable, disable, and rollback are verified.
2. One authorized RSS source completes n8n discovery, project-bound batch
   ingestion, receipt, capture or honest lead decision, triage, and authorized
   BSC/Obsidian read path.
3. Replaying the same execution creates no duplicate source, graph edge, daily
   brief revision, or metric increment.
4. Cross-project ingress, malformed input, missing key, unavailable provider,
   partial batch, and notification failure produce safe durable truthful states.
5. Daily brief and weekly distillation show exact source/receipt lineage and a
   review action, without claiming a lead is verified knowledge.
6. Docker/Compose, API/MCP authorization and redaction, focused backend tests,
   desktop/mobile browser flows, accessibility, and rollback checks pass.

Until a real authorized source run proves these conditions, the correct state is
**implemented capability with operational proof pending**, never a completed
self-growing knowledge system.
