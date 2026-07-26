# awesome-llm-apps Source-Verified Analysis Worklog

**Started:** 2026-07-26
**Scope:** audit `C:\Users\34216\Downloads\awesome-llm-apps-main.zip` for
architecture and product patterns relevant to BSC. This is analysis work only;
it does not import or execute a new product runtime.

## Progress

| Item | Status | Evidence |
| --- | --- | --- |
| Archive identity | complete | SHA-256 `8D6504BB9D5DB7CCB7DA670669D7261077A1313F71BA706F918672B9B656A008` |
| Isolated extraction | complete | extracted to temporary audit directory, outside BSC source tree |
| Full inventory | complete | 1,757 files; earlier 2,253-file count superseded |
| Architecture and source study | complete | DevPulse, Advisor/Worker, AG2 research, RAG, graph/citations, diagnostics, skill evals, MCP, always-on, and deep-research UI read from source |
| Runtime truthfulness check | complete | DevPulse mock verifier fails under default GBK output and then fails for missing `agno` under UTF-8 |
| Skill package check | complete | Advisor/Worker strict lint passes; self-improving application is not an AgentSkills package |
| BSC adoption comparison | complete | source-level mapping to Artifact Graph, DBOS, knowledge contracts, MCP, and Studio recorded in research report |
| Product-code import | intentionally not performed | archive demos would introduce duplicate state, credential, and authorization models |

## Findings

- The primary adoption value is the deterministic-data-plane versus LLM-judgment
  split, verified delivery, evidence-first UI, single-mutation evaluation, and
  task-scoped tools.
- The archive is a learning catalogue, not a coherent platform. Its examples
  rely on browser/request credentials, process or UI state, dynamic MCP
  executable launch, fragile JSON parsing, and often unauthenticated endpoints.
- The current BSC working tree has uncommitted changes across the mapped
  components. No new feature branch or commit was created during this audit;
  preserving that state must precede any additional implementation work.

## Verification

- Archive hash and file counts were calculated from the supplied zip.
- No archive dependencies were installed.
- No provider key, Vault content, third-party service, or user data was sent to
  the archive code.
- No BSC application source was changed by this audit.

## Next Work

1. Establish an atomic BSC baseline for the existing dirty working tree.
2. Turn the four concrete gaps in the research report into separately owned
   implementation plans with backend, frontend, and end-to-end acceptance tests.
3. Keep any reference-derived behavior behind BSC contracts; do not copy the
   example frameworks or their UI state as runtime truth.

## Implementation Follow-Through (2026-07-26)

The owner requested that the report's concrete effects be implemented rather
than left as recommendations. This continuation changed only the BSC evidence
boundary; no reference runtime or archive dependency was imported.

### Completed

1. **Canonical web-source identity:** `CapturedSourceInput` now canonicalizes
   HTTP(S) origins before source policy, duplicate detection, source
   supersession and capture-attempt recording. It lowercases scheme/host,
   removes fragments/default ports/common tracking parameters, sorts retained
   query parameters, and leaves non-web paths or malformed URLs unchanged.
   Immutable source bodies and their SHA-256 hashes are not rewritten.
2. **Versioned citation graph evidence:** Wiki publication now writes
   source-backed graph edges with only bounded provenance metadata: citation
   ID, source ID/status/content hash, page content hash/version, and the
   `explicit_source_marker_v1` extraction method. The graph-rebuild path uses
   the same metadata contract. Raw source text, prompts and credentials are
   excluded.
3. **Truthful Obsidian sync result:** the integration contract now includes
   `blocked=0` when no untrusted plugin export was encountered. This preserves
   the distinction between no source found and a declared but untrusted bridge
   that BSC deliberately did not read.

### Verification

| Check | Result |
| --- | --- |
| Capture canonicalization and source supersession | `tests/knowledge/test_wiki_source_capture.py`: 11 passed |
| Citation/version graph lineage and Wiki publication | `tests/knowledge/test_knowledge_graph.py tests/knowledge/test_wiki_repository.py tests/knowledge/test_wiki_evaluator.py`: 11 passed |
| Horizon, failure ledger, method package audit/gate/evolution | 20 passed |
| Obsidian sync and filesystem Wiki lifecycle | 14 passed, 1 skipped because the current Windows principal cannot create a symlink |
| DBOS, MCP, knowledge, scheduler, source, graph, and end-to-end subset | 142 passed, 1 skipped |
| Workspace/API frontend suite | 88 passed |
| Type check and production build | `npm run check` and `npm run build` passed; Vite emitted only its large-chunk advisory |

### Boundaries Retained

- Canonicalization is deliberately conservative and does not fetch URLs,
  resolve redirects, inspect third-party pages or deduplicate by model output.
- Graph metadata identifies an immutable source revision by hash; it does not
  expose raw evidence text in graph APIs or the browser.
- A real external Horizon collection and a real Obsidian plugin export remain
  external user actions. The system reports their absence or blocked state
  honestly and does not manufacture a completed capture.

## Completion Audit (2026-07-26)

The source-verified report has now been checked against the current working
tree rather than against the earlier implementation notes alone.

| Report effect | Current implementation evidence | Result |
| --- | --- | --- |
| Verified delivery rather than transport-only success | `TaskVerificationArtifact`, DBOS execution verification, REST/MCP/control-center projections, and DBOS governance tests | Complete |
| Explicit deterministic SOP routing gate | `SOPRoutingEvaluationArtifact` plus positive, negative, edge and holdout replay tests | Complete |
| Governed external-worker boundary | Project policy, server-side credential reference, allowlisted endpoint, idempotency, cancellation, recovery and durable `ExternalWorkerRunArtifact` ledger | Complete as a configurable boundary; no provider run is claimed without operator configuration |
| Single-mutation method evolution | Immutable baseline, supporting outputs, positive/near-negative/holdout replay, non-regression, reviewer-only promotion and rollback anchor | Complete |
| Evidence-first information intake | Project source policy, immutable source/capture-attempt ledger, canonical web origin identity, failure records, URL/version supersession and source-hash citation lineage | Complete |
| Evidence-first workspace projection | Knowledge/Growth/DBOS APIs and workspace components consume persisted project-scoped records; browser smoke check loads all three surfaces without console errors | Complete |
| Obsidian bridge honesty | Explicit manifest and trust store; plugin output reports `declared_only`, `unavailable`, or an aligned configuration state instead of inferring a successful plugin sync | Complete |

### Regression Repair During Closure

The release-level suite found two current-state contract gaps and they were
fixed before closure:

1. `MethodEvaluator` previously audited the persisted proposal body alongside
   a caller-supplied manifest. It now always evaluates the repository's exact
   persisted manifest. A caller cannot substitute an incomplete package, while
   a malformed persisted package is recorded as a blocking static-audit result
   rather than being treated as an unlogged request-validation exception.
2. The growth-daily integration contract now requires the bounded Obsidian
   `runtime_configuration` state. A plugin with no safe read-only settings
   probe reports `declared_only/no_readonly_settings_probe`; this information is
   retained rather than hidden to satisfy an outdated response snapshot.

### Final Verification

| Check | Result |
| --- | --- |
| DBOS, API, MCP, evidence, routing, method-evolution, source, graph, scheduler and E2E subset | `145 passed` |
| Intake, source triage, Horizon, Obsidian output bridge, growth distillation, method routing/distillation, provenance and failure-ledger regressions | `90 passed` |
| Frontend suite | `108 passed` across 13 files |
| TypeScript | `npm run check` passed |
| Production frontend build | `npm run build` passed; only the existing chunk-size advisory remains |
| Local runtime smoke | `http://127.0.0.1:5180/` loaded BSC Studio; Knowledge, Growth and Operate entry points appeared; no console errors and SSE reported ready |

No commit was made during this closure because the repository contains extensive
pre-existing, unrelated uncommitted changes. No user-authored change was
reverted or staged.
