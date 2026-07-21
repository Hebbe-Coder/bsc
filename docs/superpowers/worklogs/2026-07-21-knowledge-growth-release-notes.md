# LLM Wiki Knowledge Growth Release Notes

**Release class:** Local Docker deployment verified; broader P8 release validation remains in progress.

## Delivered

- Immutable Obsidian and Horizon evidence capture, project-scoped Vault mappings, governed proposals, deterministic lint/evaluation, atomic filesystem publication, citations, revision history, and a separate Knowledge Graph.
- A responsive BSC Knowledge workspace with real Vault, evidence, proposal, run, schedule, health, graph, and distillation data. Graph filters cover edges, node type, and status; charts render persisted observations only.
- Durable Celery schedule reconciliation, Redis-backed Worker/Beat execution, durable run events, and shared Vault/database mounts across services.
- Docker Hub connectivity, image build, Redis, API, Worker, Beat, restart recovery, and scheduled reconciler consumption have been verified locally.

## Required Configuration

- Set `KNOWLEDGE_WIKI_ENABLED=true` and `OBSIDIAN_VAULT_ROOT` to the Obsidian Vault root. Store each project mapping as a relative path inside that root.
- Set `API_KEY` for protected local or production API access. Do not commit `.env` or any provider key.
- Set `CELERY_ENABLED=true`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` for durable schedules; run Redis, Worker, and Beat together.
- Configure `HORIZON_ENABLED`, `HORIZON_API_BASE_URL`, and optional `HORIZON_API_KEY` only when a trusted Horizon sidecar is available.
- Configure an explicit real `KNOWLEDGE_WIKI_LLM_PROVIDER` before enabling autonomous Wiki maintenance. The system reports this dependency as unavailable instead of fabricating a proposal.

## Rollout And Alarms

1. Configure the Vault mapping and run bootstrap. This creates only missing managed files and does not overwrite existing `AGENTS.md`.
2. Run source sync, review validated evidence, and promote only trusted items to eligible.
3. Define project evaluation cases before publishing any proposal. Missing or failing baselines block publication.
4. Enable schedules only after Redis, Worker, and Beat are healthy. Monitor terminal knowledge run events, stale citations, uncited eligible sources, failed/unavailable runs, and scheduler reconciliation failures.
5. Pause schedules and disable `KNOWLEDGE_WIKI_ENABLED` to roll back operational behavior. Published pages are corrected with a new compensating proposal; raw evidence and audit history remain intact.

## Known Release Gates

- Live Horizon capture requires the user's endpoint and credentials.
- Autonomous maintenance requires a real configured provider and its project evaluation baseline.
- The complete review/diff/run/weekly browser journey and two-principal MCP transport E2E require dedicated seeded fixtures before a full multi-user production claim.
