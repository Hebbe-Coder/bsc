# PBOS Workspace Evidence Capture Verification

## Scope

Verify that the deployed PBOS API can capture bounded, reviewable evidence
from the local BSC AI-project workspace without copying file contents or
reading credentials.

## Commands And Results

| Command | Result |
| --- | --- |
| `python -m pytest tests/pbos/test_pbos_service.py tests/pbos/test_pbos_contextual_compiler.py tests/api/test_pbos_api.py tests/mcp/test_pbos_http_contract.py tests/integration/test_pbos_e2e.py -q` | `50 passed` |
| `npm run test:frontend` | `170 passed` |
| `npm run check` | passed |
| `docker compose config --quiet` | passed |
| `docker compose up -d --build bsc-backend` | passed |

## Receipt Contract

- The Compose API container receives the local BSC workspace at `/workspace`
  as a read-only mount.
- PBOS uses `PBOS_WORKSPACE_ROOT=/workspace` only for local Git revision and
  hashes of explicit allowlisted paths under `app/`, `src/`, `tests/`,
  `docs/`, or a small fixed root-file list.
- `.env`, credentials, arbitrary absolute paths, traversal paths, symlink
  escapes, source bodies, and test-output bodies are excluded.
- A resulting `WorkExecutionRecord` is reviewable evidence, not an accepted
  business result. User acceptance and a quality score remain required before
  PBOS can learn from the delivery.
