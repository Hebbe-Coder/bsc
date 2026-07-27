# Knowledge Operations Visualization Execution Index

**PRD:** `docs/superpowers/specs/2026-07-27-knowledge-operations-visualization-prd.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-27-knowledge-operations-visualization.md`

## Dependency Order

```text
P1 Foundations
  -> P2 Aggregation and actions ----+
  -> P3 Lifecycle graph -----------+-> P4 REST and MCP -> P5 Cockpit UI -> P6 Release
```

P2 and P3 may proceed in parallel only after P1 freezes tenancy, scope,
projection types and metric vocabulary. P6 is the only integration/release
owner.

## Plans

| ID | Plan | Depends on | Owned surfaces |
| --- | --- | --- | --- |
| P1 | `2026-07-27-knowledge-operations-foundations.md` | none | tenant migration, contracts, authorization |
| P2 | `2026-07-27-knowledge-operations-aggregation-actions.md` | P1 | aggregation service, metric/action projection |
| P3 | `2026-07-27-knowledge-operations-lifecycle-graph.md` | P1 | bounded semantic lifecycle projection |
| P4 | `2026-07-27-knowledge-operations-api-mcp.md` | P2, P3 | REST, client contracts, MCP read tools |
| P5 | `2026-07-27-knowledge-operations-cockpit-ui.md` | P4 | UnifiedWorkspace cockpit, charts, graph and drill-down |
| P6 | `2026-07-27-knowledge-operations-validation-release.md` | P5 | integration, browser, accessibility and release proof |

## Cross-plan Contracts

- P1 is the sole owner of tenant project registry, `OperationsScope`, response
  type names, role semantics and migration compatibility. Other plans must not
  change these contracts without updating P1, this index and the PRD.
- All metrics are derived from persisted Artifact Graph, Wiki/Growth, run,
  evaluation and feedback records. No plan may add mock dashboard records,
  inferred cross-project links or a fabricated quality score.
- Knowledge lineage and Artifact Graph retain separate stores and IDs. P3 may
  project links only through durable scoped references.
- REST/MCP handlers delegate to one service and preserve existing transport
  framing, authentication and proposal/execution mutation semantics.
- Each plan owns only its listed surfaces. Shared files require a small,
  documented interface edit and handoff note before parallel work begins.

## Global Gates

- Tests are written or amended before production changes in every plan.
- Every endpoint reports explicit empty, unavailable and permission states;
  stale success values may not survive a failed refresh.
- Raw source bodies, prompts, keys and provider payloads remain absent from
  operation projections and MCP responses.
- Each sub-agent appends commands, results, deviations, rollback point and
  unimplemented dependencies to the shared worklog.
- Only P6 may mark the initiative release-ready after cross-plan regression,
  browser and responsive proof.
