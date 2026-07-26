# Governed Blindspot Intake First-Round Consolidation

**Date:** 2026-07-26
**Branch:** `codex/governed-blindspot-intake`
**PRD:** `docs/superpowers/specs/2026-07-26-governed-blindspot-intake-prd.md`
**Worklog:** `docs/superpowers/worklogs/2026-07-26-governed-blindspot-intake.md`

This document records only verified first-round behavior. It is not a claim
that external information collection, Obsidian plugin execution, or a Vault
handoff has occurred in this environment.

## Integrated Behavior

| Plan | Verified delivery | Code and test evidence | Rollback |
| --- | --- | --- | --- |
| P01 | Additive, project-scoped Intake session and immutable answer revision artifacts; deterministic four-way classification; phase and question-budget validation. | `app/artifacts/types.py`, `app/artifacts/store.py`, `app/dbos/intake.py`; `tests/dbos/test_blindspot_intake_contracts.py` and `tests/dbos/test_blindspot_intake_evals.py`. | Set `DBOS_BLINDSPOT_INTAKE_ENABLED=false`; preserve audit artifacts. |
| P02 | One-at-a-time interview, skip/revert lineage, explicit assumptions and gaps, tier choice, and idempotent bridge to the existing Mission diagnosis/confirmation gates. | `app/dbos/intake.py`, `app/dbos/service.py`; `tests/dbos/test_blindspot_intake_mission_bridge.py`. | Disable feature; existing converted Missions remain ordinary audited Mission records. |
| P03 | Recommendations only from eligible, project-scoped SourceRecords; explicit unavailable state; approved confined Vault handoff with recorded SHA-256 Deliverable. | `app/dbos/intake_evidence.py`, `app/dbos/service.py`; `tests/dbos/test_blindspot_intake_evidence.py`. | Disable feature; do not delete reviewed output or the hash record. |
| P04 | Authorized REST lifecycle, single `dbos_intake` MCP facade, existing MCP HTTP catalog wiring, TypeScript client contract, persisted-state Control Center panel, and project-scope race protection. | `app/api/dbos_api.py`, `app/api/mcp_http.py`, `app/mcp/dbos_tools.py`, `app/mcp/server.py`, `src/api/dbosApi.ts`, `src/components/dbos/BlindspotIntakePanel.tsx`, `src/components/dbos/BusinessControlCenter.tsx`; REST/MCP and frontend tests below. | Disable feature; existing API/MCP transports and permissions retain their prior behavior. |
| P05 | Focused behavior coverage, production type/build checks, post-hardening desktop/mobile browser interaction evidence, and regression coverage for stale project requests. | 59 backend/API/MCP tests plus 18 frontend component tests, recorded below. | No schema rollback or destructive cleanup is needed; use the feature flag. |

## Commands And Results

```powershell
& 'C:\Users\34216\Documents\New project 3\bsc-backend\.venv\Scripts\python.exe' -m pytest tests\dbos\test_blindspot_intake_contracts.py tests\dbos\test_blindspot_intake_mission_bridge.py tests\dbos\test_blindspot_intake_evidence.py tests\dbos\test_blindspot_intake_evals.py tests\api\test_blindspot_intake_api.py tests\mcp\test_dbos_tools.py tests\mcp\test_dbos_http_contract.py -q
# 59 passed, 1 Starlette/httpx deprecation warning

npm run test:frontend -- src/components/dbos/BlindspotIntakePanel.test.tsx src/components/dbos/BusinessControlCenter.test.tsx
# 2 files, 18 passed

npm run check
# passed

npm run build
# passed; existing Vite large-chunk warning remains
```

Desktop browser verification created an Intake, skipped each bounded question,
selected a tier, observed the no-source fallback, converted to a Mission, and
confirmed that the approval/export controls remained visible after conversion.
A second `390x844` mobile check opened the Control Center and measured
`scrollWidth == clientWidth` (384), so the primary Intake view did not
horizontally scroll. In the final hardening pass, live browser exploration
found stale project refresh and retained child-panel state; both now have
component regressions. The post-fix browser rerun changed to a fresh project,
proved the old Mission option and content were both absent, then completed a
build Intake, answer revision/revert, direct review, standard tier, unavailable
source fallback, Mission conversion, and approval-gated unavailable-Vault
handoff. The `390x844` viewport measured `scrollWidth == clientWidth == 384`.

## External Boundaries And Remaining Risk

- The isolated worktree does not contain a virtual environment, so tests used
  the original workspace's interpreter in read-only mode. Recreate the local
  environment before running these commands on another machine.
- A managed Vault was not configured for this verification. The UI/API returned
  `managed Obsidian Vault is unavailable` when export was attempted, which is
  the expected refusal; no file was falsely claimed as exported.
- No Horizon network fetch, Obsidian plugin execution, external installation,
  account action, or command execution is part of this release proof.
- Output chunks above 500 kB are a pre-existing build optimization concern.
- The legacy collapsed Manual Mission compatibility control was not included in
  mobile browser evidence after the local browser runtime timed out while
  capturing it. The new Intake landing screen was verified at 390px.
- The compatibility Manual Mission control was not part of the governed Intake
  mobile path. The relevant post-fix Intake flow has desktop and 390px browser
  evidence.

## Scope Preservation

The feature is additive. It does not replace existing DBOS Mission lifecycle,
MCP transport, Artifact Graph authority, Horizon ingestion, knowledge-growth
workflow, or Vault source-of-truth rules. The source of truth for a managed
Vault remains BSC artifacts; handoffs are approved outputs, not raw evidence.
