# A/B/C/D Growth Browser Acceptance

**Date:** 2026-07-22
**Product:** `http://127.0.0.1:8002/`
**Runtime:** Docker production build with authenticated local Growth REST data

## Preconditions

- `bsc-backend`, `redis`, `celery-worker`, and `celery-beat` are running.
- The API container reports healthy and `/health` returns HTTP 200.
- `KNOWLEDGE_GROWTH_ENABLED=true`; credentials are entered interactively and are not persisted in this file.

## Results

| Journey | Viewport | Result | Evidence |
|---|---:|---|---|
| Open Growth and load persisted project state | 390x844 | Pass | Workspace loaded without unavailable/authentication alert |
| Whole-page overflow | 390x844 | Pass | Root `clientWidth=390`, `scrollWidth=390` |
| Mobile controls and stages | 390x844 | Pass | Project/key/load/refresh/close controls and A/B/C/D/Review rail render without overlap |
| Empty persisted state | 390x844 | Pass | Explicit no-record funnel, stage, lineage and Inspector states; no fabricated chart series |
| Desktop three-column workspace | 1280x720 | Pass | Root `clientWidth=1280`, `scrollWidth=1280`; stage rail, canvas and Inspector remain visible |
| Authenticated refresh | 1280x720 | Pass | Growth data loads from the Docker API and no unavailable alert remains |

## Visual Observations

- Mobile uses an intentionally scrollable stage rail while the document root remains fixed to the viewport.
- Long labels wrap inside their controls and no button, metric, heading or panel visibly overlaps another element.
- The zero-data funnel uses an explicit empty state rather than synthetic values.
- The underlying Studio cannot introduce whole-page horizontal overflow while the Growth workspace is open.

## Open Release Gates

- A populated 10,000-record browser/performance fixture was not run.
- PostgreSQL parity was not run.
- Live Horizon, Feishu and LLM provider journeys were not run.
- Keyboard focus order and reduced-motion behavior remain part of the final populated-fixture P9 pass.

## 2026-07-22 Final Populated-Fixture Follow-Up

- The former release gates in this section were completed in the final P9 run and are retained above as historical context.
- Authenticated Docker fixture data covered A/B/C/D/Review with five B pages, one published C method, four accepted D outputs and a processed review feedback record. Output-to-method-revision-to-Wiki-page-to-source traversal was verified.
- At `1280x720` and `390x844`, the document root had no horizontal overflow. Charts and lineage graph had nonblank rendered pixels. Mobile Inspector focus moved to its heading and `Escape` closed it; stage navigation responded to ArrowRight.
- Failure states for permission denial, offline API, disabled Growth and PostgreSQL outage/recovery were exercised. Browser console recorded no errors or warnings.
- PostgreSQL parity, the 10,000-record p95 guard and restart/recovery were completed by the full Python regression and dedicated P9 tests. Live Horizon, Feishu and model-provider account calls are not claimed.
