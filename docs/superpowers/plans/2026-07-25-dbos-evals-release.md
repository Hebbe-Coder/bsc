# P09 DBOS Evals and Release

## Goal
Run cross-role/industry scenario evaluation, authorization/isolation/recovery
tests, browser/build checks, documentation and rollback review.

## Modify
DBOS tests, release evidence, worklog, and consolidation document only.

## Do Not Modify
Business policy to make a test pass or unrelated existing tests.

## Test-first Tasks
1. Add end-to-end scenario and failure/authorization tests.
2. Run focused DBOS suite, Artifact Graph regression, frontend test/build.
3. Record exact outputs and unresolved external boundaries.
4. Produce the consolidation document from actual code/results.

## Rollback / Handoff
Set `DYNAMIC_BUSINESS_OS_ENABLED=false` or unregister DBOS router. Preserve
artifacts for audit and report final risk status honestly.
