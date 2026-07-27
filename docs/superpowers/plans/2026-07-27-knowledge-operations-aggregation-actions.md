# P2 - Operations Aggregation And Action Queue

## Goal

Compute trustworthy project/portfolio knowledge operations metrics and a
deterministic next-action queue from existing durable records.

**Depends on:** P1.
**Blocks:** P4-P6.

## Owned Files

**Create:** `app/knowledge/operations_service.py` and focused service tests.

**Modify:** read-only repository query helpers only where existing scoped list
methods cannot provide bounded aggregate inputs.

**Do not modify:** source bodies, growth state transitions, Artifact Graph
storage, proposal publication logic, execution/verification logic, or frontend.

## Metric Contract

- Asset buckets use existing source/page/method/output/feedback/memory records
  and their durable timestamps.
- Quality states are derived from existing publication, verification, accepted
  output, evaluation, citation, stale/orphan, contradiction and failure
  records; no aggregate confidence score is invented.
- Reuse counts use persisted method/memory references from outputs, runtime
  context and missions only.
- Agent evolution uses passed/failed verification, persisted attempt numbers,
  routing holdout and knowledge-evaluation values. Every displayed rate or
  median requires at least three persisted observations, including per rendered
  time bucket; smaller samples return `insufficient_sample` or a `null` trend
  value with the real sample count.
- Actions use the PRD priority order and include immutable source references.

## Tasks

1. Write fixtures and failing tests for mixed successful/failed projects,
   verified/unverified work, empty periods, missing dependencies and action
   priority ties.
2. Implement bounded project aggregation, tenant portfolio rollup and period
   bucketing without N+1 frontend-driven requests.
3. Implement deterministic action ranking and action-to-existing-detail target
   mapping; never perform a mutation from the service.
4. Return coverage/sample metadata and explicit unavailable reasons for every
   derived group.
5. Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_service.py tests/knowledge/test_operations_actions.py -q`.

## Acceptance Criteria

Given fixtures spanning A/B/C/D and DBOS, counts and actions match durable
records exactly and stay tenant/project scoped. Missing data is declared rather
than converted to a favorable zero or green status.

## Rollback And Handoff

Disable the projection service without deleting records. Hand P4 metric
definitions, action IDs, period bounds, fixtures and unavailable-state behavior.
