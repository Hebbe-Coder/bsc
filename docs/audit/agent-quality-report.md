# BSC Studio Agent Quality Report

**Audit Date:** 2026-07-05  
**Evaluated Files:** 9 (4 agents + protocol + composer + orchestrator + 2 engines)  
**Scoring Scale:** 1–10 (1 = deficient, 10 = exemplary)

---

## Per-File Scorecard

| File | Input Validation | Output Consistency | Error Resilience | Code Clarity | Documentation | Testability | Performance | Coupling | Idempotency | Completeness | **Avg** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `protocol.py` | 6 | 8 | 7 | 9 | 7 | 9 | 10 | 9 | 10 | 7 | **8.2** |
| `sop_agent.py` | 5 | 7 | 6 | 7 | 4 | 7 | 8 | 8 | 9 | 6 | **6.7** |
| `risk_agent.py` | 5 | 7 | 6 | 7 | 4 | 7 | 4 | 8 | 9 | 5 | **6.2** |
| `strategy_agent.py` | 6 | 8 | 7 | 9 | 4 | 8 | 9 | 8 | 9 | 4 | **7.2** |
| `optimization_agent.py` | 5 | 8 | 6 | 6 | 4 | 7 | 8 | 8 | 9 | 6 | **6.7** |
| `business_composer.py` | 7 | 8 | 7 | 8 | 6 | 8 | 8 | 5 | 9 | 7 | **7.3** |
| `studio_orchestrator.py` | 5 | 8 | 9 | 7 | 5 | 5 | 7 | 3 | 7 | 8 | **6.4** |
| `business_understanding.py` | 7 | 8 | 6 | 7 | 6 | 8 | 6 | 9 | 9 | 7 | **7.3** |
| `template_router.py` | 5 | 8 | 5 | 9 | 4 | 9 | 9 | 9 | 9 | 5 | **7.2** |

### Dimension Averages

| Dimension | Avg Score |
|---|---|
| Input Validation | 5.7 |
| Output Consistency | 7.8 |
| Error Resilience | 6.6 |
| Code Clarity | 7.7 |
| Documentation | 4.9 |
| Testability | 7.6 |
| Performance | 7.7 |
| Coupling | 7.4 |
| Idempotency | 8.9 |
| Completeness | 6.1 |

---

## Overall Score: **7.0 / 10**

---

## Top 3 Issues

### 1. Hardcoded Agent Logic — "Template Fillers, Not Analysts"

The 4 specialist agents contain predominantly hardcoded output:

- **StrategyAgent** (`strategy_agent.py:26-55`): SWOT strengths, weaknesses, opportunities, and threats are entirely static strings. The only dynamic element is the `domain` name interpolated into one bullet. Market analysis is completely hardcoded.
- **OptimizationAgent** (`optimization_agent.py:38-42`): All 3 efficiency recommendations are static strings with no connection to actual input data. The automation rate calculation is the only genuinely derived metric.
- **SOPAgent** (`sop_agent.py:28-29`): SLA values are hardcoded to `"15 min"` and `"5 min"`. Role assignment uses modulo round-robin regardless of actual role definitions.
- **RiskAgent** (`risk_agent.py:34`): Severity is determined by category name (`"operational"` → `"high"`) rather than any quantitative risk assessment.

**Impact:** The agents degrade to glorified JSON templates. They do not perform meaningful analysis — they only reshape input data into a predefined output shell.

### 2. Missing Input Validation & None Guards

None of the 4 specialist agents validate their inputs. Specific vulnerabilities:

- `template_router.py:56` — `classify_template(text: str)` calls `text.lower()` with no `None` check; passing `None` or a non-string will crash with `AttributeError`.
- `sop_agent.py:21` — `roles[i % len(roles)]` on a list of non-dict items will produce a string, then `.get("name", ...)` will fail with `AttributeError`.
- `risk_agent.py:24-27` — The triple-nested generator `for p in processes for m in metrics for r in risks_input` silently produces an empty string when any list is empty, but non-dict items will crash on `.get("name", "")`.
- `optimization_agent.py:51` — The nested `any(kw in str(p.get("name","") if isinstance(p,dict) else str(p)).lower() ...)` has a logic precedence edge: if `p` is a dict and `isinstance(p, dict)` is True, it calls `p.get("name","")` which is fine, but the expression is fragile and hard to audit.

Only `studio_orchestrator.py` has systematic try/except blocks at each pipeline stage.

### 3. Near-Zero Documentation

Every file scored 4–7 on documentation, averaging **4.9/10** — the lowest dimension:

- All 9 files have module-level docstrings (baseline).
- Only `protocol.py` includes a class-level docstring (`BaseAgent`).
- Zero files have method-level docstrings describing parameters, return values, or exceptions.
- Zero files have type annotations on function return values beyond the basic `-> dict`.
- No file explains the reasoning or algorithm behind its core logic (e.g., why bottleneck detection picks the last 2 steps; why risk severity defaults to "high" for operational risks).

---

## Top 3 Strengths

### 1. Consistent Protocol & Structural Patterns

All agents inherit from the same `BaseAgent` and share `AgentContext` / `AgentResult` types (`protocol.py`). The orchestrator's 4-stage pipeline (Parse → Fan-out → Compose → Deliver) is cleanly structured. Output structures are predictable, well-typed via `@dataclass`, and all expose `to_dict()` for serialization. This makes the system easy to extend with new agents.

### 2. Orchestrator-Level Error Resilience

The `StudioOrchestrator.execute()` method (`studio_orchestrator.py:42-103`) wraps each pipeline stage in try/except with graceful degradation:
- Failed business understanding → falls back to a minimal empty model.
- Failed agent in fan-out → empty dict assigned, stage marked `"error"`.
- Failed composer → partial workspace with `"Composition failed"` summary.
- Each future has a 30-second timeout.

Individual agent failures never crash the entire pipeline. This is the single best-practice pattern in the codebase.

### 3. Low Coupling of Specialist Agents

Each of the 4 agents (`sop_agent.py`, `risk_agent.py`, `strategy_agent.py`, `optimization_agent.py`) depends only on `protocol.py`. They are self-contained, share no state, and can be modified, replaced, or tested independently. The engines (`business_understanding.py`, `template_router.py`) are also zero-dependency (stdlib only) and independently testable.

---

## Per-File Notes

### `protocol.py` — **8.2** (Best)
Clean protocol layer. `BaseAgent.run()` catches all exceptions. Minor gaps: no type validation on `AgentContext` fields, no docstrings on `AgentStatus`/`AgentResult`/`AgentContext`. Consider adding `__post_init__` validation.

### `sop_agent.py` — **6.7**
Handles mixed dict/string process items. Fallback SOP when no processes. Weaknesses: hardcoded SLA, simplistic role assignment, no step dependencies (all steps are linear/independent).

### `risk_agent.py` — **6.2** (Worst)
Triple-nested generator is O(n×m×r) for text building — a performance anti-pattern. Risk detection is pure keyword matching with no semantic analysis. Severity assignment is category-based, not evidence-based.

### `strategy_agent.py` — **7.2**
Cleanest code of the 4 agents, but least useful output. SWOT is 100% static — effectively a placeholder. Only the domain name and first objective title are dynamic. Needs to derive real strategic insights from the business model.

### `optimization_agent.py` — **6.7**
Bottleneck detection heuristic (last 2 steps + keyword match) is simplistic. Hardcoded efficiency recommendations. The automation potential calculation is the only genuinely derived metric. The one-liner `any(...)` comprehension at line 51 is hard to parse and audit.

### `business_composer.py` — **7.3**
Well-structured composition layer. Health score is a simple linear penalty model (base 80, subtract for risks/bottlenecks, bonus for automation). Module-level helper functions (`_build_kpi_cards`, `_build_risk_cards`) are oddly placed outside the class. Coupling: implicitly depends on the output shapes of all 4 agents.

### `studio_orchestrator.py` — **6.4**
Best error resilience in the codebase, but most coupled file — imports 7+ modules via lazy imports inside functions. The `30s` timeout on futures is hardcoded. Duplicate try/except blocks (4 nearly identical patterns). Testing requires extensive mocking.

### `business_understanding.py` — **7.3**
Solid regex-based extraction engine. Good breadth — covers objectives, roles, processes, metrics, risks, constraints, domain detection, and complexity scoring. Multiple regex passes over the same text is somewhat redundant. Fallback defaults for every extraction category when nothing is found.

### `template_router.py` — **7.2**
Clean, simple keyword classifier. 4 hardcoded templates with no extension mechanism. Confidence formula (`matched_keywords / 4.0`) is arbitrary and doesn't account for keyword weight. Crashes on `None` input.

---

## Recommendations

1. **De-template the agents** — Replace hardcoded SWOT/recommendations/SLA with derived logic that actually analyzes the business model. Even simple heuristics (e.g., count processes → scale SLA, detect specific risk keywords → assign real severity) would be a major improvement.
2. **Add input validation** — Every agent should start with `if ctx is None: return {"error": "No context provided"}` or equivalent. Guards on dict/list type assumptions throughout.
3. **Document methods** — Add Google-style or NumPy-style docstrings with Parameters/Returns/Raises sections on all public methods. This will also clarify the expected shape of `business_system` dicts that each agent consumes.
4. **Fix the O(n×m×r) anti-pattern** — In `risk_agent.py`, replace the triple-nested generator with a single pass over concatenated text from all three lists.
