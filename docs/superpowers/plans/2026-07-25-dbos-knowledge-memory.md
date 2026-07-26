# P06 DBOS Knowledge and Memory

## Goal
Adapt governed A/B/C/D metadata as pattern/rule/method/output evidence for
DBOS selection, compilation and memory, preserving project isolation,
approval gates and raw-body exclusion.

## Modify
New `app/dbos/memory.py`, tests under `tests/dbos/`.

## Do Not Modify
Knowledge method promotion, source immutability, existing schema migrations.

## Test-first Tasks
1. Test only same-project, approved/published methods are read as patterns.
2. Test feedback creates a traceable advisory memory artifact.
3. Test trusted/reviewed eligible/processed sources, published Wiki pages and
   accepted/filed outputs affect only an exact declared task family, add
   traceable Dynamic SOP lineage, and never copy raw source bodies.
4. Implement a read-only bounded signal adapter and advisory memory writer.
5. Run `./.venv/Scripts/python.exe -m pytest tests/dbos/test_memory.py tests/knowledge/test_method_registry.py -q`.

## Rollback / Handoff
Remove adapter; no knowledge record is mutated. Handoff serialized bounded
signals to P03/P04/P07/P08. Raw Vault/source/output bodies are outside this
contract and require a separate audited retrieval design.
