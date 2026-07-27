# P3 - Operations Lifecycle Graph Projection

## Goal

Provide a bounded, semantic and explainable read projection across Mission,
reasoning, knowledge, verification and feedback without merging underlying
graph stores.

**Depends on:** P1.
**Blocks:** P4-P6.

## Owned Files

**Create:** `app/knowledge/operations_graph.py` and graph projection tests.

**Modify:** only scoped read helpers needed to obtain Artifact Graph subgraphs,
Growth lineage and redacted runtime references.

**Do not modify:** `ArtifactGraphStore` semantics, graph persistence schema,
Growth edge semantics, raw runtime context storage, or React UI.

## Frozen Graph Contract

- Lanes: `mission`, `assumption`, `risk_constraint`, `method_sop`,
  `validation`, `memory_feedback`, with `evidence_source` as support rail.
- A projected edge must identify its persisted domain and source reference.
  Links are admitted only when both endpoints are authorized and project scoped.
- Filters: mission, node type, status, relation, time interval and bounded
  limit/cursor. The response declares truncation and omitted endpoint count.
- Nodes expose ID, domain, lane, label, status, timestamp, supplied confidence
  and safe drill-down descriptor, never raw source or prompt text.

## Tasks

1. Write failing tests for graph lane classification, cross-domain valid links,
   missing endpoint, cross-project rejection, redaction, filtering, cursor
   bounds and deterministic ordering.
2. Implement project-scoped projection from durable parent IDs, growth lineage
   and runtime source/method references; do not infer edges from names.
3. Calculate lane layout descriptors independent of visual coordinates so the
   frontend can render a stable semantic layout.
4. Run `./.venv/Scripts/python.exe -m pytest tests/knowledge/test_operations_graph.py tests/test_artifact_scope.py -q`.

## Acceptance Criteria

A risk can be traced to durable evidence/assumption, method/SOP, verification
and memory when such links exist; absent lineage remains absent. Returned graph
slices always declare bounds and do not disclose raw source content.

## Rollback And Handoff

Disable graph projection only. Hand P4 node/edge schema, filters, bounds,
graph fixtures and redaction proof.
