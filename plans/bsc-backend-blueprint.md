# BSC Backend — Architecture Blueprint

**Generated**: 2026-07-17 | **ECC Blueprint Skill** | **Version**: v5.0.0

---

## Executive Summary

BSC (Business System Compiler) is an AI-driven enterprise platform that transforms unstructured PRD documents into comprehensive business system designs. The platform follows a **6-stage LLM Agent Pipeline** architecture with dual entry paths (main pipeline + Studio orchestrator), supporting 7 LLM providers, 7 output formats, a built-in RAG knowledge base, and a React+TypeScript frontend.

---

## 1. System Context

```
┌──────────────┐     ┌─────────────────────────────────────────┐     ┌──────────────┐
│   Browser    │────▶│         FastAPI (app/main.py)            │────▶│  SQLite/     │
│  (React SPA) │     │  Port 8000 | CORS | Auth | Rate Limit   │     │  PostgreSQL  │
└──────────────┘     └────────────────┬────────────────────────┘     └──────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│  BSC Pipeline   │    │  Studio Orchestrator │    │  Knowledge / RAG     │
│  (Agent Chain)  │    │  (Unified Entry v4)  │    │  (Vector Search)     │
└────────┬────────┘    └──────────┬───────────┘    └──────────┬───────────┘
         │                        │                           │
         ▼                        ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        LLM Adapter Layer                                 │
│  DeepSeek | Doubao | Qwen | Kimi | Yuanbao | Ollama | vLLM | LocalAI    │
│  LangChain Integration | L1/L2 Cache | Mock Fallback                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Export Layer                                      │
│  JSON | HTML | PPT (v1+v2) | Word | PDF | XLSX | Markdown              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Map

### 2.1 Core Pipeline (`app/core/` — 27 files)

| Module | Status | Responsibility |
|--------|--------|---------------|
| `bsc_pipeline.py` | **Active** | Synchronous 6-stage agent pipeline |
| `async_pipeline.py` | **Active** | Async variant, Celery-compatible |
| `llm_service.py` | **SHIM** → `app/services/` | LLM provider abstraction |
| `async_llm_service.py` | **SHIM** → `app/services/` | Async LLM provider |
| `langchain_service.py` | **SHIM** → `app/services/` | LangChain integration |
| `cache_service.py` | **SHIM** → `app/services/` | L1/L2 caching |
| `user_preference_service.py` | **SHIM** → `app/services/` | User preferences |
| `config.py` | **Active** | Pydantic Settings (160+ config keys) |
| `document_parser.py` | **Active** | PDF/Word/PPT/XLSX parsing |
| `prd_refiner.py` | **Active** | Multi-round PRD refinement |
| `prd_quality_scorer.py` | **Active** | PRD quality scoring |
| `prompt_manager.py` | **Active** | Dynamic prompt loading |
| `prompt_loader.py` | **Active** | File-based prompt templates |
| `celery_app.py` | **Active** | Celery task queue |
| `database.py` | **Active** | SQLite/PostgreSQL backend |
| `event_bus.py` | **Active** | In-process pub/sub |
| `metrics.py` | **Active** | Prometheus + JSON metrics |
| `template_customizer.py` | **Active** | Industry template customization |
| `planner.py` | **Active** | Agent execution planning |

> **SHIM** = Compatibility shims pointing to `app/services/`. 5 shims exist because services were migrated but old `from app.core.*` imports remain.

### 2.2 Agent Layer (`app/agents/` — 14 files)

| Agent | Type | Mode |
|-------|------|------|
| `base_agent.py` | Abstract | LLM-driven base class |
| `protocol.py` | Protocol | Local callback agent interface |
| `business_understanding_agent.py` | LLM Agent | PRD semantic analysis |
| `sop_agent.py` | LLM Agent | SOP/workflow generation |
| `risk_agent.py` | LLM Agent | Risk identification |
| `strategy_agent.py` | LLM Agent | Strategic analysis |
| `optimization_agent.py` | LLM Agent | Improvement recommendations |
| `composer.py` | LLM Agent | Result assembly |
| `business_composer.py` | LLM Agent | Business blueprint assembly |
| `report_composer.py` | LLM Agent | Formatted report generation |
| `asset_agent.py` | LLM Agent | Chart/PPT asset generation |
| `unified_agent.py` | LLM Agent | Unified agent interface |
| `studio_orchestrator.py` | Orchestrator | v4: wraps main pipeline |

### 2.3 Dual Architecture: Main Pipeline vs Studio

| Dimension | Main Pipeline | Studio Orchestrator |
|-----------|--------------|---------------------|
| Entry | `POST /bsc/compile` | `POST /studio/ask` |
| Implementation | `BSCPipeline` class | `StudioOrchestrator` v4 |
| Agent Type | LLM-driven (`BaseAgent`) | Same (unified since v4) |
| Execution | Serial + Parallel phases | Wraps main pipeline + adapters |
| Output | `business_system` dict | Studio workspace dict |

### 2.4 Skill Chains (`app/chains/` — 8 files)

Independent LangChain-based skill execution path: `POST /api/skill/execute` → Chain selection → LLM call → structured output.

### 2.5 Knowledge/RAG (`app/knowledge/` — 19 files)

Full RAG pipeline: chunker → embeddings → hybrid search → reranker → self-RAG → answer generation.

---

## 3. Data Flow

```
PRD Input (text/file)
    │
    ▼
document_parser.py ─── Multi-format parsing (PDF/Word/PPT/XLSX)
    │
    ▼
┌─ BSCPipeline.compile_to_business_system() ─────────────────────┐
│                                                                 │
│  Stage 1: Business Understanding (LLM) ──▶ domain, objectives   │
│                                                                 │
│  Stage 2-5: Parallel Agents (ThreadPool)                        │
│    ├─ SOP Agent      ──▶ workflow, roles, SLA, KPI             │
│    ├─ Risk Agent     ──▶ risk categories                       │
│    ├─ Strategy Agent ──▶ growth opportunities                   │
│    └─ Optimization   ──▶ recommendations                       │
│                                                                 │
│  Stage 6: Composer ──▶ assembled report                        │
│                                                                 │
│  Post: validate_business_system() → degrade on failure          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Exporters ──▶ JSON / HTML / PPT / Word / PDF / XLSX / MD
```

---

## 4. Technical Debt & Risk Register

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| 1 | **5 Compatibility Shims** in `app/core/` redirect to `app/services/` | Medium | `core/llm_service.py`, `async_llm_service.py`, `langchain_service.py`, `cache_service.py`, `user_preference_service.py` |
| 2 | **Dual data models coexist**: `ProductionBusinessSystem` vs `BusinessSystemSchema` (DEPRECATED) | Medium | `schemas/production_schema.py`, `schemas/business_schema.py` |
| 3 | **Service layer split**: services physically in `app/services/` but 10+ modules still import from `app.core.*service` | Medium | 10+ `from app.core.*service` imports |
| 4 | **`repair_engine.py` still references DEPRECATED schema** | Low | `validators/repair_engine.py` |
| 5 | **README.md** still reads "React + TypeScript + Vite" template default | Low | Root `README.md` |
| 6 | **Double virtual envs**: both `.venv/` and `venv/` exist | Low | Root directory |
| 7 | **Config sprawl**: 160+ config keys in single `Settings` class | Medium | `core/config.py` |

---

## 5. Improvement Blueprint

### Phase 1: Clean (Zero Risk)
1. Remove 5 compatibility shims from `app/core/` — migrate all 10+ consumers
2. Delete duplicate `venv/` (keep `.venv/`)
3. Update `README.md` with real project description

### Phase 2: Harden
4. Migrate remaining `from app.core.*service` to `from app.services.*`
5. Completely deprecate `business_schema.py` — update `repair_engine.py`
6. Split `config.py` Settings into domain-specific config classes

### Phase 3: Optimize
7. Unify agent execution model (remove protocol.py legacy)
8. Add integration test coverage for full pipeline
9. Consider extracting `config.py` into `app/config/` package

---

## 6. Key Metrics

| Metric | Value |
|--------|-------|
| Python files | 173 |
| TypeScript files | 72 |
| Test files | 93 |
| API endpoints | ~60+ |
| LLM providers | 7 |
| Export formats | 7 |
| LangChain chains | 8 |
| Agent classes | 14 |
| Config keys | ~160 |
| Compat shims | 5 |
| Dual models | 2 (1 active, 1 deprecated) |
