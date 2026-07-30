# N2 - Project Source Registry And RSS

## Goal

Implement the project-local source policy and first-release RSS/YouTube Channel
RSS normalization without enabling paid, restricted, or credential-dependent
connectors.

**Dependencies:** N1 contract accepted.
**May run in parallel with:** N3 after N1.
**Blocks:** N4.

## File Boundary

**Create:** source registry domain types, additive persistence/migration,
project-authorized source-policy service, RSS normalization service, adapter
capability states, focused fixtures, and focused tests.

**Modify:** existing project profile/configuration reads and source-triage
integration only to consume a declared source registry.

**Do not modify:** SignalBatch schema/status definitions, ingress authorization,
SourceRecord admission transitions, Wiki publication, n8n credentials, Feishu
delivery, Horizon semantics, or user-authored Vault files.

## Inputs, Outputs, Authorization, And Redaction

- **Inputs:** project profile, authorized project actor, declared feed/channel
  URLs, topic/language/freshness policy, and existing triage vocabulary.
- **Outputs:** revisioned Source Registry records; normalized RSS candidate
  fields; adapter capability states; safe source-fetch errors; and a projected
  configuration read model.
- **Authorization:** project members may only manage sources for authorized
  projects. Tenant administrators retain aggregate operational visibility
  without raw source bodies.
- **Redaction:** list/API/test responses return source configuration and safe
  status only. They exclude full feed bodies, secrets, request headers,
  provider payloads, filesystem paths, and personal account data.

## Test-First Tasks

1. Add failing tests for project isolation, malformed/non-HTTP feed URLs,
   unapproved source registration, duplicate canonical feed registration,
   disabled source scheduling, and a source that is fresh but policy-excluded.
2. Define the registry record: stable ID, project/tenant ownership, source and
   adapter class, canonical feed URL, topic/language tags, freshness window,
   priority, allow/deny state, rights/retention policy, schedule eligibility,
   capability state, revision, actor, and timestamps.
3. Implement additive persistence, project-authorized CRUD/revision history,
   and a safe read model. No registry mutation starts n8n or captures content.
4. Implement RSS and Channel RSS normalization preserving feed GUID/channel
   identity, original URL, title, excerpt, source date, UTC publication time,
   observed time, source registry ID, and source limitation.
5. Add deterministic URL normalization and candidate deduplication. Preserve
   duplicate provenance without producing duplicate candidate rows.
6. Model X, Reddit, YouTube Data API, and TikTok as unavailable capability
   records with a safe prerequisite reason; do not add provider API calls.
7. Hand N4 fixtures and contract examples for enabled RSS, disabled source,
   malformed feed, stale item, duplicate item, and unavailable connector.

## Acceptance

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/knowledge/test_n8n_source_registry.py tests/knowledge/test_source_triage.py -q
./.venv/Scripts/python.exe -m pytest tests/api/test_n8n_source_registry_api.py -q
git diff --check
~~~

A green suite must prove that no RSS item is a published Wiki page, Skill,
output, or verified claim merely because it was normalized.

## Rollback, Worklog, And Handoff

Disable the source registry feature flag and leave additive records/audit
history intact. Roll back only the additive migration/application release when
necessary; never delete user source material to reset tests. The handoff carries
schema revision, migrations, policy examples, fixture/real classification,
tests, known feed limitations, and rollback action.
