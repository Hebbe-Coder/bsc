# Studio Runtime And Chinese Routing Recovery

## Scope

Recover the usable local Studio after an observed frontend runtime failure and
verify that Chinese requests are routed to their intended BSC workspaces. This
record covers the change made in `UnifiedWorkspace` only. It does not claim
completion of owner feedback, Copilot delivery review, personal learning, or
external connector authorization.

## Actual Repair

- A fresh reload of `http://127.0.0.1:5174/` showed a blank page. Browser
  console logs identified an `Invalid hook call` and a null `useState`
  dispatcher in `UnifiedWorkspace`. `npm ls` showed one deduplicated React
  18.3.1 tree. Restarting the stale Vite process with `--force` restored the
  Studio; a fresh tab had no Studio console errors.
- The Chinese input terms in `detectMode` had become literal question marks.
  Replaced them with bounded board-review, PRD/SOP compiler, and
  analysis/diagnosis terms. The classifier still only selects a run profile;
  it neither starts a Mission nor authorizes an external action.
- Added regression coverage for Chinese multi-agent review, PRD-to-dynamic-SOP,
  and risk/coverage analysis requests.

## Verification

- `npm run test:frontend`: `24 files, 230 tests` passed.
- `npm run check` and `npm run build` passed.
- `docker compose up -d --build bsc-backend` rebuilt only the API/frontend
  container. `/ready` returned database and Redis `ok`; PostgreSQL, Redis,
  Worker, Beat, n8n, and persisted volumes stayed running.
- A real request in both `5174` and deployed `8002` selected `Compiler` at
  `85% match`: `请把这份产品需求文档编译为项目专属的动态 SOP 与执行流水线，并明确验收指标。`
  No workflow was submitted as part of this read-only route check.
- At `390x844`, the project PBOS Cockpit loaded its connected Vault context and
  registered Copilot review drafts with no horizontal overflow.
- Focused backend regression passed `99` tests across Artifact Graph
  durability, Copilot transcript import, Obsidian output sync, PBOS services,
  contextual compiler, and PBOS API. The only warning was Starlette's existing
  TestClient deprecation.

## Remaining Boundary

The current project uses Copilot rather than Claudian. Its imported archive is
a registered D-layer draft until the owner supplies a genuine observed result,
attribution, quality score, and next-iteration direction. Damaged historical
text remains quarantined rather than reconstructed or promoted as evidence.
