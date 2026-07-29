# n8n Information Intelligence Worklog

**PRD:** docs/superpowers/specs/2026-07-27-n8n-governed-information-intelligence-prd.md
**Execution index:** docs/superpowers/plans/2026-07-27-n8n-information-intelligence-index.md

## Status

`not_release_ready` for the repository release gate; the governed public-RSS
capability itself has current runtime proof.

The operational chain has been proven with n8n as a constrained producer and
BSC as the only evidence, receipt, review, and audit authority. A real public
RSS item has passed n8n collection, exact-body HMAC validation, project-scoped
ingress, immutable evidence capture, receipt persistence, managed Obsidian
projection, REST/MCP read models, and the Studio Intel panel. The verified
daily runtime workflow is active at 08:00 `Asia/Shanghai`; the versioned
repository export remains disabled by default so importing it cannot silently
start collection. The C1 release conclusion was corrected on 2026-07-29 after
the required full regression suite exposed two non-n8n failures. This worklog
does not treat scoped proof as a substitute for the repository release gate.

## Progress

| Date | Item | State | Evidence / deviation |
| --- | --- | --- | --- |
| 2026-07-27 | Tutorial and workflow analysis | Complete | Read the Xuan tutorial and parsed the supplied 87-node inactive workflow. Confirmed intended RSS/API collection, date/filter preprocessing, DeepSeek derivatives, Feishu archiving/push, daily schedule, unconfigured generic HTTP notification targets, and credential references without secret values. |
| 2026-07-27 | PRD and plan split | Complete | Created the dedicated PRD, execution index, N1-N5 boundaries, and C1 consolidation contract. This is documentation governance only; no runtime or external integration was executed. |
| 2026-07-27 to 2026-07-29 | N1 optional n8n runtime | Complete with Compose proof | Added a disabled-by-default Compose `n8n` profile with loopback-only administration, a dedicated durable volume, mandatory runtime encryption key, health check, and no imported credentials. Docker Hub remained unavailable, so the image was switched to the pinned official `ghcr.io/n8n-io/n8n:1.106.3` image and its OCI source label was verified. `docker compose --profile n8n up -d n8n`, `/healthz`, `docker compose config --quiet`, and a restart after activation all passed. Rollback is `docker compose --profile n8n down`; removing the profile leaves existing BSC services unchanged. |
| 2026-07-27 | N2 project RSS source registry | Complete | Added project-scoped RSS and YouTube Channel RSS registry contracts, source policy fields, retention controls, canonical URL handling, and explicit `unavailable` states for X, Reddit, YouTube Data, and TikTok. Focused registry/deduplication tests passed. |
| 2026-07-27 | N3 signed SignalBatch ingress | Complete with real evidence | Added v1 SignalBatch validation, HMAC verification over the exact request body, `project_ingress` authorization, batch and execution replay protection, immutable source capture, `lead_only` disposition, BSC receipt ledger, and rejection receipt paths. A real public GitHub Blog RSS item was admitted into a configured project: the first submission created one `captured` receipt; exact replay returned `replayed: true`; a fresh batch for the same item produced `duplicate_source` without duplicating the source. A cross-project submission was rejected. No feed body or credential is recorded here. |
| 2026-07-28 to 2026-07-29 | N4 governed derivatives workflow | Complete with n8n-owned proof | The sanitized 9-node export has a manual trigger, disabled 08:00 trigger, exact-body HMAC, BSC receipt validation, and disabled notification placeholder. A stale Crypto-node field mapping was caught by a structural test and corrected to explicit `action=hmac`, SHA-256, hex encoding, and the `signature` field. n8n imported the export and a producer-owned manual run completed with a BSC receipt. A separate persisted runtime copy enables the already-proven 08:00 `Asia/Shanghai` trigger; it is the single active workflow after a health-checked restart. No credentials, Feishu delivery, Reddit, TikTok, or automatic knowledge publication were imported. |
| 2026-07-28 to 2026-07-29 | N5 operations delivery and projection | Complete with real browser proof | Added read-only REST/MCP operations views and the Knowledge Workspace `Intel` panel. The HTTP MCP compatibility layer now advertises and invokes the information overview and receipt tools only when the feature flag is enabled. In an authenticated Studio session, the actual configured project displayed one ready RSS source, persisted BSC receipts, and ingress runs. A 390px browser check showed the Intel panel visible with its source/receipt data and no horizontal overflow. The default project correctly displayed its honest no-source/no-receipt state instead of inheriting another project's data. |
| 2026-07-28 to 2026-07-29 | Obsidian authority boundary | Complete with filesystem proof | The captured source's configured-project mapping, `completed` projection state, managed Markdown evidence file, source ID frontmatter, and immutable read-only marker were verified from the running BSC container. The projection exists only after BSC capture; n8n does not write to the Vault directly. |
| 2026-07-28 to 2026-07-29 | Focused verification | Passed | `& .\\.venv\\Scripts\\python.exe -m pytest tests/knowledge/test_information_intelligence.py tests/api/test_knowledge_intelligence_api.py tests/mcp/test_information_intelligence_tools.py tests/test_n8n_information_intelligence_compose.py -q` exited 0 with 12 passed. `npm run check` exited 0. `npm run test:frontend -- src/components/KnowledgeWorkspace.test.tsx src/api/knowledgeWorkspaceApi.test.ts` exited 0 with 18 passed. `docker compose config --quiet`, n8n health checks, BSC `/ready`, REST reads, and HTTP MCP calls all passed. |
| 2026-07-29 | Initial consolidation decision | Superseded | The active daily workflow was manually executed after its final scheduling configuration and returned a completed BSC receipt. The evidence remains valid for actual n8n-to-BSC connectivity, scoped authorization, HMAC integrity, source capture, receipt-ledger readback, Vault projection, MCP access, Studio display, and responsive layout. The original `release_ready` label was superseded by the C1 revalidation below because the complete repository gate did not pass. |
| 2026-07-29 | C1 revalidation | `not_release_ready` | Scoped evidence remains green: 12 n8n Python tests, 18 Intel frontend tests, TypeScript check, production build, and all three Compose configs passed; BSC and n8n health probes are current. The required full suite exited 1 after 769 passed and 8 skipped: `test_wiki_maintenance_without_eligible_evidence_completes_as_auditable_noop` returned `unavailable` because no real Wiki LLM provider was configured, and `test_metadata_list_p95_is_below_300ms_for_10000_project_records` measured about 4.17s under the running local container workload. Neither failure is in the n8n contract, but both block the plan's all-command release gate. The current embedded browser session could not connect to `127.0.0.1:5180` although host HTTP returned 200, so a new browser run was not claimed. Rollback remains disabling the n8n profile/workflow without deleting BSC records. |

## Required Handoff Record

Each N1-N5/C1 entry must state the exact command, exit code, changed files,
feature flag, fixture/real classification, safe IDs/counts, deviation, external
dependency, rollback action, and next owner. It must not contain secret values,
raw source text, provider payloads, Vault paths, prompt bodies, or personal
account identifiers.

## Current External Dependencies

- The scoped BSC signal-ingress capability and signing secret exist only in the
  ignored local runtime environment; they must never be committed or displayed.
- X, Reddit, YouTube Data API, TikTok, optional DeepSeek derivatives, and the
  Feishu notification mirror remain explicitly unavailable until their own
  credentials, cost controls, terms review, and connector tests are supplied.
- Docker Hub remains unreachable in this environment. The running n8n image is
  the pinned official GHCR image, not an unverified registry mirror.
- The current in-app browser session cannot reach the host Vite endpoint even
  though the endpoint returns HTTP 200 from the host. It must be restored before
  treating a fresh desktop/mobile browser run as current C1 evidence.

## Next Handoff

1. Use the authenticated Studio Knowledge workspace with the project that owns
   the registered RSS source. Other projects intentionally remain empty.
2. Inspect the `Intel` panel for receipt-backed intake health and the managed
   `01_Sources/bsc-evidence` pages for human-readable, BSC-owned projections.
3. Add sources only through the BSC registry. Do not add credentials or enable
   unsupported connectors in a workflow export.
4. Keep the daily runtime workflow enabled only while its project-scoped
   ingress key, signing secret, and source policy remain valid. Disable it with
   `n8n update:workflow --id <id> --active=false` and restart n8n to roll back.
5. Re-run C1 after resolving the Wiki provider/no-op expectation, the A/B/C/D
   performance regression under the chosen release load, and the local browser
   reachability issue. Only then may the release conclusion change from
   `not_release_ready`.
