# Horizon Intelligence Adapter Architecture

## What Horizon Contributes

Horizon is an intelligence sidecar, not the BSC knowledge authority. Its useful architecture is a staged, observable pipeline:

1. Concurrent source adapters collect RSS, GitHub, Hacker News, Reddit, Telegram, X, OpenBB, OSS Insight, GDELT, and Google News into one `ContentItem` shape.
2. Cross-source URL canonicalization strips tracking parameters and merges the same story before model cost is spent.
3. AI scoring yields a 0-10 score, reason, summary, and tags; low-value items are removed before enrichment.
4. Topic de-duplication and optional category quotas preserve information diversity rather than optimizing only for the highest repeated score.
5. A second pass enriches selected items with concepts, background, caveats, and source context.
6. MCP persists `raw`, `scored`, `filtered`, and `enriched` stage artifacts per run, so each later operation is reproducible.

## BSC Boundary

Horizon output enters BSC only through `HorizonImportService` and only from `filtered` or `enriched` stages. The adapter retains the Horizon run ID, stage, item ID, URL, score, rationale, tags, and raw article text in immutable `SourceRecord` evidence.

- Horizon score is a selection signal, not truth and not an automatic publishing permission.
- Imported signals remain `validated`; BSC project rules, citation checks, evaluation baselines, and proposal gates still decide publication.
- BSC never imports Horizon's generated daily summary as a primary source when the underlying item text is available.
- Horizon remains independently deployable, so its scraper credentials, cookies, and network failures do not enter BSC's database or MCP transport.

## Integration Sequence

```text
Horizon filtered/enriched stage
  -> BSC HorizonImportService
  -> immutable validated SourceRecord
  -> project review / eligibility policy
  -> WikiCompiler draft
  -> lint + eval + proposal gate
  -> Obsidian projects/<project_id>/wiki
  -> graph, SOP context, weekly distillation
```

## Reusable Design Decisions

- Use Horizon's run-stage artifacts as an auditable adapter input, not opaque HTTP summaries.
- Preserve cross-source URL provenance even when BSC content hashing deduplicates the evidence body.
- Carry Horizon's score and category into BSC UI later as filterable metadata, never as an unchallengeable ranking.
- Reuse staged run diagnostics: partial source failure must be visible beside successful signals.
- Keep full-text extractors opt-in and fall back to feed excerpts, matching Horizon's graceful degradation approach.
