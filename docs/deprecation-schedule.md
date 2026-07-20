# Legacy API Deprecation Schedule

`/bsc/*` remains available through the A-C compatibility window.

| Endpoint family | Replacement | Deprecation date | Removal date |
|---|---|---|---|
| `/bsc/*` | `/api/orchestrate` and `/agent/analyze` | 2026-07-20 | 2026-12-31 |
| Legacy SSE URLs | `/api/orchestrate/{session_id}/events` | 2026-07-20 | 2026-12-31 |

All `/bsc/*` responses carry `Deprecation: true`, `Sunset`, and a successor link.
