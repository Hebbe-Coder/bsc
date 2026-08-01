# 2026-08-02 Copilot Runtime Verification

## Scope

Verify the active Obsidian AI integration after the project owner selected
Copilot instead of Claudian. This record contains only bounded configuration
states, deployment checks, and local test evidence. It contains no provider
credential, conversation body, source body, or private Vault content.

## Runtime Evidence

- Protected workspace read for `proj_b8a285642094` returned exactly one
  relevant plugin bridge: `copilot`, with status `awaiting_output`. No
  `realclaudian` bridge was returned. Copilot's automatic conversation archive
  remains distinct from a reviewed D-layer output and is not treated as an
  accepted knowledge or personal-learning record.
- API, Worker, Beat, PostgreSQL, Redis, and n8n were healthy. `/ready`
  reported healthy database and Redis dependencies.
- SHA-256 comparison confirmed that the running API container matches the
  workspace for `wiki_compiler.py`, `wiki_llm_provider.py`,
  `extraction_reference_projection.py`, `multimodal_extraction.py`, and
  `knowledge_tasks.py`.

## Verification

- `npm run check` passed.
- Focused knowledge regression passed: `64 passed, 1 warning` across
  multimodal evidence, governed Celery source sync, Wiki compiler, Wiki LLM
  provider, and Knowledge Workspace API coverage. The sole warning is the
  pre-existing Starlette TestClient/httpx deprecation.

## Release Boundary

The workspace release status remains
`implemented_with_operational_proof_pending`. Copilot configuration is real
and governed, but it does not replace the remaining evidence gates: a real
project-owned multimodal import with an extraction/reference chain and a
reviewed delivery feedback cycle that demonstrably changes a later action.

## Related Commits

- `0c46757 feat(knowledge): harden governed evidence lineage`
- `b8e4620 docs(pbos): complete implementation contracts`
- `57824c8 docs(pbos): define evidence-driven personal loop`
