# P3 - Wiki Compiler And Project Context Implementation Plan

**Goal:** Compile eligible evidence into project-specific, citation-backed Wiki proposals and construct bounded context packs that ground BSC SOP and content output in the active project's knowledge.

**Architecture:** The compiler reads immutable sources plus current Markdown state and returns typed `WikiProposal` operations. It does not directly write filesystem or database published state. `AGENTS.md` is an evolving per-project schema/instruction asset. A context pack is a bounded, traceable selection of project rules, pages, evidence, decisions, constraints, and weekly distillation.

**Depends on:** P1, P2
**Blocks:** P4-P8
**Do not modify:** raw source content, P4 publication logic, current compiler lifecycle contracts, or generic output-template compatibility.

## Owned Files

**Create:** `app/knowledge/wiki_rules.py`, `app/knowledge/wiki_compiler.py`, `app/knowledge/context_pack.py`, `app/knowledge/wiki_prompting.py`, `tests/knowledge/test_wiki_rules.py`, `tests/knowledge/test_wiki_compiler.py`, `tests/knowledge/test_context_pack.py`, and `tests/orchestrator/test_wiki_methodology_bridge.py`.

**Modify:** `app/orchestrator/methodology.py`, the active SOP composition seam discovered during implementation, `app/knowledge/wiki_service.py`, and existing provider abstractions only through dependency injection.

## Compiler Contract

- `compile_maintenance(project_id, source_ids, trigger, actor)` returns a persisted proposal in `draft` state and a structured compiler report.
- Input records rule revision, source hashes, page revisions, and context-pack ID. Output records operations, citations, links, conflicts, assumptions, rationale, and source IDs.
- Compiler operations may target allowed `wiki/` pages only. `raw/`, `inbox/`, `.bsc/`, and arbitrary paths are forbidden.
- A malformed LLM response creates a failed `KnowledgeRun`; it cannot create a partially inferred operation list.

## Task 1: Project Rules (`AGENTS.md`)

- [ ] Add failing tests for default generation, valid parse, missing required sections, invalid page-kind policy, forbidden path rule, and stable rule revision hash.
- [ ] Define required sections: project scope, evidence hierarchy, allowed page kinds, frontmatter schema, citation convention, contradiction policy, SOP requirements, content voice, and maintenance workflow.
- [ ] Generate a concise, domain-neutral default. Preserve user-provided rules as authoritative and report validation findings rather than rewriting them.
- [ ] Parse YAML frontmatter plus Markdown body into typed settings while retaining unrecognized user text for context inclusion.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_rules.py -q
```

## Task 2: Deterministic Bounded Context Packs

- [ ] Define `ContextPack` with project/rule revisions, selected page/source references, character/token budget, decision/constraint summaries, weekly-distillation reference, omission list, and generated sections.
- [ ] Assemble sections in fixed priority: project rules, explicit task/PRD constraints, decisions, relevant Wiki pages, cited raw evidence, then recent distillation.
- [ ] Use existing hybrid retrieval only to find candidates; retain page/source IDs in every included section and enforce project isolation.
- [ ] Trim by dropping low-priority complete sections. Never split a citation/claim pair or silently lose the omission record.
- [ ] Attach context-pack hash and references to SOP/content metadata so later review can reconstruct the inputs.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_context_pack.py -q
```

## Task 3: Compile Proposals Without Direct Writes

- [ ] Add fake-provider tests for valid multi-page proposal, malformed structured output, unsupported operation, unreferenced claim, contradiction result, and unchanged source set.
- [ ] Build prompts from rules, context pack, selected sources, and page snapshots. Require machine-readable proposal JSON validated by P1 models; keep human rationale separate.
- [ ] Select only eligible/unprocessed sources and persist all input revisions before an LLM call.
- [ ] Add overview/index/log operations when substantive pages change. `wiki/log.md` is append-only and no response claims a file is written until P4 publishes it.
- [ ] Detect likely contradiction candidates from shared entities/concepts and source recency. Expose findings rather than inventing a resolution.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_compiler.py -q
```

## Task 4: Ground SOP And Content Output

- [ ] Add an opt-in Wiki context provider at the current methodology/SOP seam. Without an enabled vault, preserve current behavior and emit `knowledge_context_used=false`.
- [ ] Add context-pack ID, page/source references, and explicit assumption markers without removing any existing response field.
- [ ] Require SOP sections to distinguish project evidence/rules from general recommendations. Existing templates may supply layout only.
- [ ] Add focused fake-context tests proving project constraints alter the output and project A references never enter project B.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\orchestrator\test_wiki_methodology_bridge.py tests\orchestrator\test_methodology_e2e.py tests\orchestrator\test_sop_methodology.py -q
```

## Task 5: Verification And Handoff

- [ ] Run all P1-P3 tests and preserve current methodology/SOP regressions.
- [ ] Record provider format assumptions, context budget defaults, and actual SOP integration file in the worklog.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\knowledge\test_wiki_rules.py tests\knowledge\test_context_pack.py tests\knowledge\test_wiki_compiler.py tests\orchestrator\test_wiki_methodology_bridge.py -q
git diff --check
```

## Acceptance, Rollback, Handoff

- Compilation produces reviewable proposals only; it cannot publish pages or mutate raw evidence.
- Every operation has scope, expected revision when needed, and sources or explicit user-authored exception.
- SOP behavior remains compatible without a Wiki and traceable with a configured Wiki.
- Rollback disables compiler/context flags without changing existing SOP or Wiki files.
- Handoff P4 with proposal snapshots, contradiction shape, and fake-provider fixtures; hand P6/P7 read-only proposal/context response contracts.
