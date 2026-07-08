# BSC Studio Security & Architecture Audit

**Date:** 2026-07-05
**Version:** 5.0.0
**Scope:** `bsc-backend/` — all `.py`, `.html`, `.env`, `requirements.txt`

---

## Security Findings

| Severity | File | Issue | Fix |
|---|---|---|---|
| **HIGH** | `app/main.py:40` | CORS set to `allow_origins=["*"]` — any origin can call the API. In production, this exposes the backend to cross-origin attacks (CSRF, data exfiltration). | Restrict to specific origins via env var: `allow_origins=os.environ.get("CORS_ORIGINS","").split(",")` |
| **MEDIUM** | `app/middleware/rate_limiter.py` (global) | `RateLimitMiddleware` is implemented but **never registered** in `app/main.py`. Zero rate-limit protection in practice. | Add `app.add_middleware(RateLimitMiddleware, rate=10, burst=20)` to `main.py` |
| **MEDIUM** | `app/api/bsc_api.py:120` | `compile_files` exposes raw file uploads with no size limit, no MIME-type validation, and no extension whitelist. An attacker can upload arbitrary large files or malicious documents. | Add `File(..., max_size=10*1024*1024)` and whitelist extensions `[".txt",".docx",".pdf"]` |
| **MEDIUM** | `app/api/chat_api.py:14-15` | `_conversations` dict grows unbounded — no TTL, no max size, no eviction. Over time this leaks memory (OOM risk under sustained use). | Add LRU eviction with `maxsize=1000` and TTL-based cleanup (e.g., 1 hour idle timeout) |
| **MEDIUM** | `app/core/llm_service.py:12-27` | Docstring contains fake API key patterns (`sk-xxx`, `xxx`) that could trigger false positives in secret scanners. Not a real leak, but noise in CI/CD pipelines. | Replace with `your-api-key-here` or `$PROVIDER_API_KEY` placeholders |
| **LOW** | `requirements.txt` | All dependencies use `>=` (lower-bound) pinning. A supply-chain attack on any package could inject malicious code on the next `pip install`. | Pin exact versions or use `requirements.lock` / `pip freeze` |
| **LOW** | `app/api/bsc_api.py:138` | `HTTPException(400, str(e))` passes raw Python exception strings to the client, potentially leaking internal paths or logic. | Return generic error messages; log the full exception server-side |
| **LOW** | `app/api/bsc_api.py:223-298` | `_generate_html_report()` builds HTML by direct string interpolation of `business_system` dict values (e.g., `business_system.get("report", {}).get("executive_summary", "")`). If LLM output contains `<script>`, `&`, or unescaped HTML, it produces malformed/injectable HTML. | Apply `html.escape()` to all interpolated values |
| **LOW** | `static/*.html` | Uses `innerHTML` for rendering server data. The `esc()` function handles `<` and `&`, but no Content-Security-Policy header is set. | Add CSP header: `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' fonts.googleapis.com` |
| **LOW** | `app/main.py:50` | `__import__(m, fromlist=["router"])` dynamically imports router modules. Currently uses hardcoded module names, but the pattern is fragile — a typo silently skips an API route instead of failing loudly. | Validate that all expected routers loaded successfully; raise on missing critical routes |

---

## Architecture Findings

| Severity | Component | Issue | Fix |
|---|---|---|---|
| **HIGH** | `app/core/compiler.py:779-869` | **Hidden repair loop / silent mock fallback.** The `_compile_llm_full` pipeline has 7 stages: compile → parse → repair → validate → fallback → local repair → mock. If LLM returns invalid JSON, the system silently repairs it (via LLM repair prompt + local heuristic repair). If all repair fails, `_mock_fallback_result` returns **fake/mock data** with no indication to the user that the output is fabricated. The user sees `"success": true` and mock data indistinguishable from real results. | Surface `"backend": "mock_fallback"` and `"repairs_applied": N` in the response so the caller knows the data is synthetic. Consider refusing to return data (HTTP 503) when all real backends fail. |
| **HIGH** | `app/agents/studio_orchestrator.py:56-65` | **Wrapper regression — failures produce empty dicts.** When a specialist agent (SOP, Risk, Strategy, Optimization) throws, the orchestrator catches and sets `results[name] = {}`. The composer then receives `{}` and builds a workspace from partial/no data. The user gets a "complete" looking result without knowing 3 of 4 agents failed. | Propagate errors to the caller. Mark the overall result `"success": false` if any mandatory agent fails. |
| **MEDIUM** | `app/agents/studio_orchestrator.py:42-47` | **Error silently swallowed.** When `bind_visuals(bs)` fails in `bsc_api.py:41`, the `except: pass` drops the error entirely. No log, no user notification, no fallback visual. The response just omits visuals. | Log the error and include `"visuals_error"` in the response so the frontend can show a warning. |
| **MEDIUM** | `app/core/llm_service.py:316-368` | **Mock responses are hardcoded to specific system prompts (Chinese text).** The `_call_mock` method pattern-matches on exact Chinese prompt prefixes like `"你是SOP Agent"`. If the prompt text changes even slightly, the mock silently returns `{"content": "mock response", "note": "未匹配到Agent类型"}` — a valid-looking but useless dict. | Use a generic mock that returns structurally valid but clearly marked synthetic data, regardless of prompt text. Tag mock data with `"_mock": true`. |
| **MEDIUM** | `validators/repair_engine.py` (via `compiler.py:762`) | **Local repair mutates data silently.** The `_repair_locally` function runs a `RepairEngine` on broken JSON without logging what was changed. Repaired data is returned as if it were the original LLM output, masking quality issues. | Log repair actions (what fields were fixed) and include a `"repairs"` list in the response metadata. |
| **LOW** | `app/agents/studio_orchestrator.py:100-102` | **AgentContext reused across runs.** `get_studio_orchestrator()` is a singleton. While `StudioOrchestrator` itself is stateless, the `AgentContext` created at line 100 is fresh per-request. However, if future code adds state to the orchestrator, it would be shared across all requests. | Document the singleton pattern clearly and enforce that no request-scoped state is stored on the instance. |
| **LOW** | `app/engines/business_understanding.py:87-95` | **Regex-based extraction is fragile.** Domain detection, objective extraction, risk identification all use regex/keyword matching on raw text. If input is in English but keywords are Chinese (e.g., `审核`), the engine returns empty/default results. No LLM fallback for extraction failures. | Add bilingual keyword support or fall back to an LLM-based extraction when regex yields empty results. |
| **LOW** | `app/middleware/rate_limiter.py:16-31` | **TokenBucket implementation is not thread-safe for async.** The `consume` method modifies `self.tokens` and `self.last_refill` without synchronization. Under concurrent access from the same IP, token counts may be incorrect (race condition on token decrement). | Use `asyncio.Lock` or make `consume` an async method that acquires the per-bucket lock. |

---

## Summary

- **Critical:** 0
- **High:** 3
- **Medium:** 6
- **Low:** 9

### Top 3 Actions Required

1. **Restrict CORS** (`app/main.py:40`) — currently `*` allows any origin.
2. **Register rate limiter** — middleware exists but is not wired into the app.
3. **Surface fallback/mock data** — the compiler silently returns fake data on LLM failure; callers have no way to detect this.
