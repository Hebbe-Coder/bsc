# BSC v5.0 — SSE Streaming Pipeline + SaaS MVP

**Created**: 2026-07-03
**Status**: Draft
**Depends on**: v4.6.0 (full pipeline working)

---

## Phase 1: SSE Streaming Pipeline Visualization

### Files to create
| File | Responsibility |
|---|---|
| pp/engines/stream_emitter.py | SSE event emitter with stage_start/stage_progress/stage_complete/error_event |
| pp/api/stream_api.py | POST /pipeline/run-stream SSE endpoint |
| static/stream.html | Live pipeline visualization (progress bars, stage cards, logs) |

### Files to modify
| File | Change |
|---|---|
| pp/engines/pipeline_orchestrator.py | Add streaming callbacks to PipelineOrchestrator.run() |
| pp/main.py | Register stream_router, bump to v5.0.0 |

### API
`
POST /pipeline/run-stream  (SSE)
  events: stage_start, stage_progress, stage_complete, error_event, pipeline_complete
`

---

## Phase 2: Cross-Project Knowledge Graph

### Files to create
| File | Responsibility |
|---|---|
| pp/engines/cross_project_learner.py | Extract patterns across projects, merge into industry knowledge |
| pp/api/industry_api.py | GET /industry/{domain}/patterns, POST /industry/learn |

### Files to modify
| File | Change |
|---|---|
| pp/engines/knowledge_center.py | Add cross-project query methods |

---

## Phase 3: SaaS Deployment

### Files to create
| File | Responsibility |
|---|---|
| Dockerfile | Container build |
| docker-compose.yml | App + PostgreSQL + Redis |
| pp/auth/jwt.py | JWT token auth |
| pp/middleware/tenant.py | Multi-tenant isolation |
| rontend/ | Next.js SaaS UI (login, project list, pipeline view) |

### DB Migration
- SQLite → PostgreSQL
- Add: users, tenants, api_keys tables

---

## Task Breakdown (Phase 1 Only)

### Task 1.1: Stream Emitter
- Create StreamEmitter class with emit(stream_id, event_type, data)
- Support: stage_start, stage_progress(%), stage_complete, error_event
- Use asyncio.Queue for backpressure-safe emission

### Task 1.2: Pipeline Orchestrator Streaming
- Add on_stage_start, on_stage_complete, on_error callbacks to PipelineOrchestrator.run()
- Wrap each stage with callback invocations
- Emit percentage progress across stages

### Task 1.3: SSE API Endpoint
- POST /pipeline/run-stream accepts same input as /pipeline/run-inline
- Returns 	ext/event-stream with SSE formatted events
- Handles client disconnect gracefully

### Task 1.4: Frontend Visualization
- Single HTML file with animated stage pipeline
- Progress bars per stage with timing
- Color-coded status (green=done, blue=running, red=failed)
- Auto-scroll log panel

### Verification
- Run pipeline with 3 materials → all 6 stages show live progress
- Client disconnect → pipeline continues but stops emitting
- All 4 event types fire correctly
