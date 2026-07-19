# BSC Backend — Coding Standards Audit

**Generated**: 2026-07-17 | **ECC Coding-Standards Skill**

---

## 1. Quantitative Metrics

| Metric | Value | Grade |
|--------|-------|-------|
| Total Python files | 173 | — |
| Files with return type hints | 120 / 173 (69%) | ⭐⭐⭐ |
| Files with class docstrings | 119 / 173 (69%) | ⭐⭐⭐ |
| Longest file | `sop_report_engine.py` (2,439 lines) | 🔴 |
| Functions > 80 lines | 56 | 🔴 |
| Longest function | `export_to_html` in `sop_report_engine.py` (564 lines) | 🔴 |

---

## 2. Top 10 Longest Files

| # | File | Lines | Issue |
|---|------|-------|-------|
| 1 | `app/engines/sop_report_engine.py` | 2,439 | 🔴 Monolithic — split into sub-engines |
| 2 | `app/core/dialog_engine.py` | 1,450 | 🔴 Mixed concerns (PRD gen + quality + scoring) |
| 3 | `app/services/langchain_service.py` | 1,176 | 🟡 LangChain integration + mock + fallbacks |
| 4 | `app/core/bsc_pipeline.py` | 759 | 🟢 Core orchestrator — reasonable |
| 5 | `app/engines/pm_report_engine.py` | 647 | 🟡 PM report generation |
| 6 | `app/engines/prd_analyzer.py` | 621 | 🟡 PRD analysis |
| 7 | `app/services/cache_service.py` | 616 | 🟡 Cache service |
| 8 | `app/core/metrics.py` | 607 | 🟢 Metrics + Prometheus |
| 9 | `app/core/async_pipeline.py` | 607 | 🟢 Async pipeline (mirrors bsc_pipeline) |
| 10 | `app/core/langchain_agent.py` | 594 | 🟡 LangChain agent |

---

## 3. Code Quality Analysis

### ✅ Strengths

| Area | Evidence |
|------|----------|
| **Type Hints** | 69% of files use return type annotations |
| **Pydantic Models** | Extensive use of `BaseModel` with `Field()` descriptions |
| **Docstrings** | 69% of files document their classes |
| **Dependency Injection** | Agent constructors accept `llm_service` parameter |
| **Configuration** | Strong `pydantic-settings` with production validation |
| **Error Handling** | Try/except with graceful degradation patterns |
| **Immutable Patterns** | `ConfigDict(extra="allow")` for forward compatibility |

### 🔴 Critical Issues

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `sop_report_engine.py:1784` | `export_to_html()` is **564 lines** | Split into `_export_header()`, `_export_body()`, `_export_sections()` |
| 2 | `dialog_api.py:66` | `get_agent_instance()` is **474 lines** | Extract to factory module with registry pattern |
| 3 | `prd_editor_api.py:152` | `find_path()` is **395 lines** | Extract tree traversal logic |
| 4 | `sop_report_api.py:36` | `validate_format()` is **461 lines** | Decompose per section validator |

### 🟡 Warnings

| # | Issue | Files Affected |
|---|-------|---------------|
| 5 | **Deep nesting**: Some functions have 4-5 levels of indentation | `dialog_engine.py`, `prd_analyzer.py` |
| 6 | **Magic strings**: "business_understanding", "sop", "risk" etc. used as string literals | Pipeline files, orchestrators |
| 7 | **God objects**: `DialogEngine` handles PRD generation, quality scoring, refinement, and section editing | `dialog_engine.py` |
| 8 | **Duplicate code**: `async_pipeline.py` (607 lines) heavily mirrors `bsc_pipeline.py` (759 lines) — ~80% structural similarity |
| 9 | **Naming inconsistency**: `BaseAgent` defined in both `base_agent.py` and `protocol.py` | Agents module |

---

## 4. Language-Specific Patterns

### Python: Good Patterns Found

```python
# ✅ Dependency Injection (base_agent.py)
class BaseAgent(ABC):
    def __init__(self, llm_service=None):
        self._llm_service = llm_service

# ✅ Pydantic with extra="allow" for LLM output flexibility (production_schema.py)
class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="allow")

# ✅ Graceful degradation (bsc_pipeline.py)
try:
    bs = ProductionBusinessSystem(**raw)
except ValidationError:
    logger.warning("Schema validation degraded")

# ✅ Type-safe config (config.py)
class Settings(BaseSettings):
    LLM_PROVIDER: str = "deepseek"
```

### Python: Areas to Improve

```python
# ❌ Magic strings — should be Enum or constants
if stage_key == "business_understanding":  # bsc_pipeline.py
if provider == "deepseek":                  # config.py

# ❌ Missing type hints
def _create_initial_results(self, prd_content, template_id=None):  # async_pipeline.py

# ❌ Long parameter lists
def compile_to_business_system(prd_content, llm_service=None, template_id=None,
                               output_types=None, custom_prompts=None, skip_cache=False,
                               timeout=None):  # bsc_pipeline.py — 7 params!
```

### TypeScript/React: Good Patterns Found

```tsx
// ✅ Functional components with typed props
interface ButtonProps { ... }
export function Button({ children, onClick }: ButtonProps) { ... }

// ✅ Zustand for state management
// ✅ Tailwind utility classes
// ✅ Proper file organization (components/, hooks/, store/, types/, api/)
```

---

## 5. Recommendation Summary

| Priority | Action | Effort |
|----------|--------|--------|
| **P0** | Split `sop_report_engine.py` (2439 lines) into sub-modules | Medium |
| **P1** | Extract `get_agent_instance()` to factory pattern | Low |
| **P1** | Deduplicate `bsc_pipeline.py` ↔ `async_pipeline.py` shared logic | Medium |
| **P1** | Replace magic strings in pipeline stages with Enums | Low |
| **P2** | Add return type hints to remaining 31% of functions | Low |
| **P2** | Break functions > 80 lines into smaller units | Ongoing |
| **P3** | Add mypy/pyright type checking to CI | Low |
