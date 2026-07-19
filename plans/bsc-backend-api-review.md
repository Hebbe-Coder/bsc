# BSC Backend — API Design Review

**Generated**: 2026-07-17 | **ECC API-Design Skill**

---

## 1. Endpoint Inventory (~154 endpoints, 22 routers)

### Router Prefix Overview

| Router | Prefix | Endpoints | Pattern |
|--------|--------|-----------|---------|
| bsc_api | `/bsc` | 8 | Root-level |
| chat_api | `/chat` | 4 | Root-level |
| studio_api | `/studio` | 1 | Root-level |
| prd_api | `/prd` | 7 | Root-level |
| prd_editor_api | `/prd/editor` | ~15 | Root-level |
| brainstorm_api | `/brainstorm` | 7 | Root-level |
| knowledge_api | `/knowledge` | ~18 | Root-level |
| dashboard | `/dashboard` | 8 | Root-level |
| template_api | `/templates` | 8 | Root-level |
| tasks_api | `/tasks` | 6 | Root-level |
| stream_api | `/stream` | 7 | Root-level |
| visual_api | `/visual` | 9 | Root-level |
| sop_report_api | `/sop-report` | ~16 | Root-level |
| pm_report_api | `/pm-report` | ~10 | Root-level |
| dialog_api | `/dialog` | ~12 | Root-level |
| recommendation_api | `/recommendation` | 8 | Root-level |
| **files_api** | `/api` | 1 | `/api/` prefix |
| **skill_routes** | `/api/skill` | 6 | `/api/` prefix |
| **orchestrate** | `/api/orchestrate` | 3 | `/api/` prefix |

---

## 2. Findings

### ✅ Strengths

| Area | Assessment |
|------|-----------|
| **Response Envelope** | `ApiResponse` class provides consistent `{success, data, message, errors, code}` format |
| **HTTP Methods** | Correct use of GET/POST/PUT/DELETE semantics |
| **Status Codes** | Proper use of 200, 201, 207, 400, 401, 404, 500 via `ApiResponse` helpers |
| **Resource Naming** | Most paths use nouns: `/templates`, `/documents`, `/projects` |
| **SSE Streaming** | Dedicated `/stream` router with proper streaming support |
| **Task Abstraction** | `/tasks` router for async job management |
| **Health/Metrics** | Well-designed `/health` and `/metrics` endpoints |

### ⚠️ Issues

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| 1 | **No API versioning** | High | No `/api/v1/` prefix. Breaking changes will be painful. |
| 2 | **Inconsistent prefix pattern** | Medium | 3 routers use `/api/` prefix (files, skill, orchestrate); 19 use root-level prefixes |
| 3 | **Response format inconsistency** | Medium | `studio_api.py` uses custom `_ok()/_err()` format instead of `ApiResponse` |
| 4 | **Mixed path styles** | Low | Some use kebab-case (`/sop-report`, `/pm-report`), some flat (`/bsc`, `/chat`) |
| 5 | **Verb-in-URL anti-pattern** | Low | `/bsc/compile` uses verb; consider `POST /bsc` instead |
| 6 | **No pagination** | Low | Collection endpoints (`/documents`, `/tasks`) lack pagination metadata |
| 7 | **Tags inconsistency** | Low | Tags use mixed casing: `"BSC Pipeline"`, `"chat"`, `"studio"`, `"Knowledge"` |

### 🔴 Critical: No API Versioning

All endpoints are unversioned. Example:

```
POST /bsc/compile          # NO version
POST /studio/ask           # NO version
GET  /knowledge/documents  # NO version
```

Should be:

```
POST /api/v1/bsc/compile
POST /api/v1/studio/ask
GET  /api/v1/knowledge/documents
```

---

## 3. Response Format Audit

### `app/api/response.py` — Canonical Format ✅

```python
ApiResponse.ok(data, message)        → {"success": true, "data": ..., "message": "...", "code": 200}
ApiResponse.error(message, errors)   → {"success": false, "message": "...", "errors": [...], "code": 400}
ApiResponse.unauthorized(message)    → {"success": false, "message": "...", "code": 401}
ApiResponse.not_found(message)       → {"success": false, "message": "...", "code": 404}
ApiResponse.server_error(message)    → {"success": false, "message": "...", "code": 500}
ApiResponse.partial(data, message)   → {"success": false, "data": ..., "message": "...", "code": 207}
```

### `app/api/studio_api.py` — Custom Format ⚠️

```python
_ok(d)   → {"success": True, "data": d}        # No message, no code field
_err(m,c) → HTTPException(c, detail={"success": False, "error": m})  # Different error key!
```

**Gap**: `studio_api` uses `"error"` key while `ApiResponse` uses `"message"` + `"errors"` keys. Inconsistent error format.

---

## 4. Recommendations

| Priority | Action |
|----------|--------|
| **P0** | Add `/api/v1/` version prefix to all routers |
| **P1** | Unify `studio_api.py` to use `ApiResponse` class |
| **P1** | Normalize 3 `/api/`-prefixed routers to root-level or all to `/api/` |
| **P2** | Add pagination metadata (`meta.total`, `meta.page`, `links.next`) to list endpoints |
| **P2** | Standardize tag casing (all `"Title Case"` or all `"lowercase"`) |
| **P3** | Add OpenAPI operation IDs for better client generation |
