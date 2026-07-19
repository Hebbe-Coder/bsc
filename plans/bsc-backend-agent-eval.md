# BSC Backend — Agent System Evaluation

**Generated**: 2026-07-17 | **ECC Agent-Eval Skill (adapted)**

---

## 1. Agent Inventory & Architecture Audit

### Agent Class Hierarchy

```
ABC (Python stdlib)
├── BaseAgent (app/agents/base_agent.py)         ← Primary LLM agent base
│   ├── BusinessUnderstandingAgent               ← LLM-driven, has schema
│   ├── SOPAgent                                 ← LLM-driven
│   ├── RiskAgent                                ← LLM-driven
│   ├── StrategyAgent                            ← LLM-driven
│   ├── OptimizationAgent                        ← LLM-driven
│   ├── RootCauseAgent                           ← LLM-driven
│   ├── AssetAgent                               ← LLM-driven
│   └── ReportComposer                          ← LLM-driven
│
├── UnifiedBaseAgent (app/agents/unified_agent.py) ← Alternative base
│   ├── BaseAgent (app/agents/protocol.py)       ← ⚠️ NAME CONFLICT with above!
│   ├── LLMAgentAdapter                          ← Wraps LLM agents
│   └── LocalAgentAdapter                        ← Wraps local engines
│
└── (No base class)
    ├── Composer (app/agents/composer.py)        ← Standalone, no inheritance
    └── BusinessComposer                         ← Standalone wrapper
```

### ⚠️ Critical: Double BaseAgent Name Collision

Two different files define `BaseAgent`:
- `app/agents/base_agent.py::BaseAgent(ABC)` — primary, has LLM run(), output_schema
- `app/agents/protocol.py::BaseAgent(UnifiedBaseAgent)` — legacy protocol, different API

This causes confusion and import shadowing risk.

---

## 2. Agent Architecture Scorecard

| Dimension | Rating | Evidence |
|-----------|--------|----------|
| **Separation of Concerns** | ⭐⭐⭐ | Each agent has single responsibility (BU, SOP, Risk, etc.) |
| **Interface Consistency** | ⭐⭐ | 3 base classes + 2 standalone classes with no base |
| **LLM Decoupling** | ⭐⭐⭐ | Dependency injection via constructor, thread-safe |
| **Error Handling** | ⭐⭐ | JSON parse errors caught, but no retry/fallback in agents |
| **Testability** | ⭐⭐ | Mock agents exist but inline in base_agent.py |
| **Observability** | ⭐ | No per-agent metrics, no tracing, no latency tracking |
| **Documentation** | ⭐⭐⭐ | Good docstrings on BaseAgent design principles |

---

## 3. Findings

### 🔴 Critical Issues

| # | Issue | Impact |
|---|-------|--------|
| 1 | **Dual BaseAgent class** (`base_agent.py` vs `protocol.py`) | Import ambiguity, maintenance burden |
| 2 | **`Composer`/`BusinessComposer`** don't inherit from any base | No schema validation, no standardized run() interface |
| 3 | **Mock agents inline** in `base_agent.py` lines 151-311 | Test code mixed with production code |

### 🟡 Warnings

| # | Issue |
|---|-------|
| 4 | No per-agent metrics (latency, token usage, success rate) |
| 5 | No retry logic in agent `run()` methods |
| 6 | `UnifiedBaseAgent`/`protocol.py` v3 legacy coexists with v4 orchestrator |
| 7 | 6 agents don't define `output_schema` explicitly (rely on inherited) |

### ✅ Strengths

| # | Strength |
|---|----------|
| 1 | Clean dependency injection: `BaseAgent(llm_service=None)` |
| 2 | Thread-safe design for parallel agent execution |
| 3 | Clear prompt templates with JSON output enforcement |
| 4 | `StudioOrchestrator` v4 unified to main pipeline |
| 5 | `AssetAgent` properly handles chart/PPT generation as separate concern |

---

## 4. Agent Performance Assessment (Qualitative)

Based on code analysis of execution paths:

| Agent | Est. LLM Calls | Output Complexity | Risk of Hallucination |
|-------|---------------|-------------------|----------------------|
| BusinessUnderstanding | 1 | Medium (domain + objectives + flow) | Low (structured extraction) |
| SOP | 1 | High (workflow + roles + SLA + KPI) | Medium (creative generation) |
| Risk | 1 | High (4 risk categories) | Medium (speculative) |
| Strategy | 1 | Medium | High (strategic analysis) |
| Optimization | 1 | Medium | Medium |
| Composer | 1 | Low (assembly) | Low |

**Total LLM calls per compile: 6** (4 in parallel, 2 serial)

---

## 5. Recommendations

| Priority | Action |
|----------|--------|
| **P0** | Remove `protocol.py::BaseAgent` name conflict — rename to `StudioBaseAgent` |
| **P0** | Extract mock agents from `base_agent.py` to `tests/mocks/` |
| **P1** | Make `Composer`/`BusinessComposer` inherit from `BaseAgent` |
| **P1** | Add per-agent metrics: `duration_ms`, `tokens_used`, `success` to pipeline stages |
| **P2** | Add retry with exponential backoff to `BaseAgent.run()` |
| **P2** | Deprecate `UnifiedBaseAgent`/`protocol.py` now that v4 orchestrator is unified |
| **P3** | Add agent-level tracing/logging for debugging LLM outputs |
