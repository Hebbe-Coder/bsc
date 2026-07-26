# Governed Blindspot Intake PRD

**Date:** 2026-07-26
**Status:** First-round implementation
**Owner:** BSC Studio / DBOS
**Source review:** docs/superpowers/research/2026-07-26-blindspot-finder-methodology-review.md

## 1. Product Definition

Governed Blindspot Intake converts ambiguous project requests into bounded,
reviewable DBOS intake. It adopts Blindspot Finder's useful interaction rules
without treating a prompt-only Skill as an execution system.

Initial request -> deterministic classification -> direct draft, bounded
clarification, help exit, or one choice for uncertainty -> reviewable answers,
gaps, assumptions, and tier -> source-backed recommendations when available ->
Mission, Diagnosis, and Dynamic SOP through existing DBOS gates -> explicit
Vault handoff export.

The Artifact Graph remains authoritative. Existing DBOS Mission, confirmation,
execution, Horizon, knowledge-growth, MCP transport, and Obsidian Vault
semantics are compatibility boundaries.

## 2. Problem, Goals, And Non-goals

Current free-text DBOS intake can preserve missing fields but does not provide
a low-friction, bounded way to discover the highest-value unknowns before SOP
compilation. The product must improve the user path without reintroducing a
generic, mandatory prompt workflow.

Goals:

1. Classify a new request as build, direct, help, or uncertain without
   external effects.
2. Ask no more than two qualifying questions, three missing-context questions,
   and one blindspot probe; make every answer individually reversible.
3. Persist answer revisions, skips, tier choice, recommendation evidence, and
   Mission conversion under the project boundary.
4. Make confirmed answers affect Mission context and Dynamic SOP compilation.
5. Export a readable handoff only after user approval to the managed Vault.

Non-goals:

- Installing Blindspot Finder or applying it as a global system prompt.
- Automatic installs, account creation, external commands, source fetching, or
  capability execution.
- Replacing existing business/career Mission modes or DBOS authorization.
- Reading arbitrary Vault files, raw source bodies, or private credentials.

## 3. User Flow

| Classification | User-visible path | Side effects |
| --- | --- | --- |
| build | Start bounded clarification. | Creates only an Intake session. |
| direct | Show a Mission draft and direct conversion. | No Mission until conversion. |
| help | Explain that this is not a build workflow and exit. | None. |
| uncertain | Show one choice: clarify, create directly, or exit. | None. |

The deterministic classifier returns rationale and confidence. The user can
select direct conversion at any time; remaining unknowns become visible DBOS
Assumptions or Gaps during diagnosis. Direct conversion never confirms or
executes a Mission.

## 4. Domain Contracts

Two additive Artifact Graph types provide durable intake state:

| Artifact | Responsibility | Parent lineage |
| --- | --- | --- |
| intake_session | Original request, classification, phase, question budget, derived context, tier, recommendation state, linked Mission, and export metadata. | Project only; Mission after conversion. |
| intake_answer_revision | Immutable answer/skip record, question key, ordinal, supersession pointer, and context mapping. | Intake session. |

IntakeSessionArtifact phases are classified, clarifying, ready_for_review,
converted, exited, and cancelled. It stores a domain separate from DBOS
intake_mode: product_build, automation, data_analysis, business, or career.
Conversion maps it to existing Mission mode and carries domain in Mission
context.

Answers can map only to known Mission context fields: role, industry,
organization_stage, goal, time_horizon, constraints, stakeholders,
decision_rights, success_metrics, and declared evidence. A skipped or unknown
value cannot become a fact.

## 5. Functional Requirements

### FR-1 Classification And Interview

- The local classifier uses explicit direct/help signals and build, automation,
  data, business, and career signals. Ties or weak signals become uncertain.
- The server selects one concrete question at a time from domain and declared
  context, enforcing the 2 + 3 + 1 budget before mutation.
- Answer submission creates an immutable revision. Revert supersedes only the
  selected revision and recomputes affected derived context.
- Users can skip, pick Lite/Standard/Full, or exit. Skips stay unresolved.

### FR-2 Mission Bridge

- The review contains normalized intent, declared context, unresolved fields,
  tier, and probe findings.
- Conversion creates one ordinary DBOS Mission with intake_session_id and
  sop_generation_mode=adaptive, then invokes existing diagnosis/compilation.
- Repeated conversion is idempotent and returns the linked Mission.
- Existing confirmation, task-decision, capability-grant, execution, stop, and
  rollback requirements are unchanged.

### FR-3 Recommendations And Handoff

- Recommendations appear only after tier selection. They use admitted,
  project-scoped SourceRecord metadata with a usable URL, capture time, and
  acceptable status.
- Missing Horizon/source governance records an explicit unavailable state. No
  unavailable item is described as freshly or externally verified.
- Recommendations are advisory only and cannot install, invoke, or grant.
- An approved handoff renders persisted session/Mission data to
  outputs/handoffs/<session-id>.md under the configured Vault. Its path and
  SHA-256 are recorded in a Deliverable artifact and not re-ingested as source.

### FR-4 REST, MCP, And UI

REST provides project-scoped create/read session, answer, revert, select tier,
recommend, convert, and approved handoff export operations through strict
Pydantic schemas. MCP exposes the same service as one dbos_intake facade under
current DBOS project authorization.

Business Control Center displays a compact pre-Mission panel: classification,
single-question card, budget, back action, direct path, tier review, source
state, conversion, and approved export. The 390 px view remains one action at
a time and never shows planning as execution success.

## 6. Security And Reliability

- Intake artifacts are project-scoped and cannot link to foreign artifacts.
- Readers can inspect but cannot create, answer, convert, or export.
- A Vault file requires approved=true; missing/escaped Vault paths fail closed.
- Recommendation and export failure states are durable and never reported as
  success.
- DBOS_BLINDSPOT_INTAKE_ENABLED can disable routes and UI without changing
  current DBOS behavior. It defaults on in development.

## 7. Acceptance Criteria

1. Build, direct, help, and uncertain requests follow distinct persisted paths.
2. A third qualifying, fourth completion, or second probe question is rejected.
3. Revert preserves history; skipped required context becomes a DBOS Gap after
   conversion.
4. Only admitted, URL-bearing sources can form recommendations; unavailable
   sources return an explicit unavailable state.
5. Cross-project mutation, reader mutation, and unapproved export fail.
6. Conversion yields a normal Mission, Diagnosis, and Dynamic SOP with session
   lineage; DBOS execution remains blocked before existing confirmation/decision
   gates.
7. At least 30 focused cases pass with DBOS, knowledge, REST, MCP, frontend,
   TypeScript, production-build, desktop, and mobile verification.

## 8. Rollout And Rollback

The feature launches behind its dedicated setting. Rollback disables the
router and panel while preserving sessions, revisions, Mission lineage, and
approved outputs for inspection. Consolidation records commands, browser
results, deviations, and any environment-gated Horizon/Vault boundary.
