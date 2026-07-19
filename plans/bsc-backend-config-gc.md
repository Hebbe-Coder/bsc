# BSC Backend — Config & Code GC (Garbage Collection Audit)

**Generated**: 2026-07-17 | **ECC Config-GC Skill (adapted for project)**

---

## Scan Results

### Channel 1: Dead Compatibility Shims

| File | Status | Size | Action |
|------|--------|------|--------|
| `app/core/llm_service.py` | **ORPHANED** — 0 consumers | ~100B | 🗑️ Delete |
| `app/core/async_llm_service.py` | **ORPHANED** — 0 consumers | ~100B | 🗑️ Delete |
| `app/core/langchain_service.py` | **ORPHANED** — 0 consumers | ~100B | 🗑️ Delete |
| `app/core/cache_service.py` | **ORPHANED** — 0 consumers | ~100B | 🗑️ Delete |
| `app/core/user_preference_service.py` | **ORPHANED** — 0 consumers | ~100B | 🗑️ Delete |

> **Evidence**: All 37 consumers have been migrated to `from app.services.*`. The shims re-export `from app.services.*` but nothing imports through them.

### Channel 2: Previously Deleted Dead Code (Confirmed)

| File | Status |
|------|--------|
| `app/core/pipeline.py` | ✅ Already deleted |
| `app/core/compiler.py` | ✅ Already deleted |
| `app/core/orchestrator.py` | ✅ Already deleted |
| `app/services/mock_compiler.py` | ✅ Already deleted |

### Channel 3: Deprecated Schema — Zero Import Consumers

| File | Status |
|------|--------|
| `app/schemas/business_schema.py` (DEPRECATED) | ⚠️ Zero `from app.schemas.business_schema` imports found |

> The deprecated `BusinessSystemSchema` has no import consumers. It exists purely as reference material.

### Channel 4: Duplicate Virtual Environments

| Path | Size |
|------|------|
| `.venv/` | ~18,749 files |
| `venv/` | ~9,839 files |

> ⚠️ Two Python virtual environments. Keep `.venv/` (larger, probably active), delete `venv/`.

### Channel 5: Large Cache/Artifact Directories

| Directory | Size | Recommendation |
|-----------|------|---------------|
| `node_modules/` | 329 MB | ⚠️ Keep (required by frontend build) |
| `output/` | 6.7 MB | ⚠️ Review — generated export artifacts |
| `dist/` | 5.1 MB | ⚠️ Keep (React production build) |
| `__pycache__/` | <1 MB | 🗑️ Safe to clean |
| `.pytest_cache/` | <1 MB | 🗑️ Safe to clean |
| `.ruff_cache/` | <1 MB | 🗑️ Safe to clean |

### Channel 6: README Mismatch

| File | Issue |
|------|-------|
| `README.md` | Still contains Vite React template boilerplate — does not describe BSC project |

---

## GC Action Plan

| # | Action | Risk | Reversible? |
|---|--------|------|-------------|
| 1 | Delete 5 dead shims from `app/core/` | Zero | ✅ Git revert |
| 2 | Delete `venv/` (keep `.venv/`) | Low | ✅ Re-create with pip |
| 3 | Delete caches: `.pytest_cache`, `.ruff_cache`, `__pycache__` | Zero | ✅ Auto-regenerated |
| 4 | Review `output/` — archive or clean old exports | Zero | ✅ Just files |
| 5 | Update `README.md` with actual project description | Zero | ✅ Git revert |
| 6 | Keep `business_schema.py` as reference (docs-only, zero runtime impact) | N/A | N/A |

**Estimated reclaimable**: ~10,000+ files (venv + caches + shims)
