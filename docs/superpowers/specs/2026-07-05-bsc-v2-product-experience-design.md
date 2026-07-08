# BSC Studio v2 — One-Surface Product Experience

**Status:** Approved  
**Date:** 2026-07-05  
**Author:** BSC Studio Team  

---

## 1. Problem Statement

BSC Studio v1 is functionally complete (85% maturity) but suffers from product experience gaps:

- Users land on Swagger docs, not product
- Results show pipeline debug info (agent names, ms timings)  
- PPT export requires explicit `output_types: ["ppt"]` in API
- No clear "happy path" for non-technical users
- Feature surface is fragmented across 14 API routes

**Core insight:** Users want one thing — paste business text, get a polished deliverable. Everything else is friction.

---

## 2. Target Persona

**Primary:** Business consultant / manager who needs to turn a PRD into a client-ready deck in 30 seconds.  
**Secondary:** Bid team member who needs to extract structure from an RFP and auto-generate a proposal.

Both personas share the same need: **input → insight → export**, with zero learning curve.

---

## 3. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Homepage style | Minimal input (textarea + button) | Zero cognitive load; one surface |
| Result format | Visual dashboard (health score, KPIs, risks) | Immediate comprehension; "wow" moment |
| Primary action | One-click PPT export | Consultants live in PowerPoint |
| Export strategy | Smart template router | Context-aware without user choosing |

---

## 4. User Flow

```
User lands on /
    │
    ├─ Sees: Title + one textarea + "Analyze" button + 5 example chips
    │
    ├─ Types/pastes text, presses Enter
    │
    ├─ <500ms: Dashboard appears
    │   ├─ System health score (0-100)
    │   ├─ KPI cards (modules count, processes, risks)
    │   ├─ Risk badges (high/medium/low)
    │   └─ Recommendations list
    │
    ├─ System auto-detects template context
    │   ├─ bid_proposal (RFP/bidding keywords)
    │   ├─ operations_report (metrics/KPI keywords)
    │   ├─ sop_design (workflow/process keywords)
    │   └─ strategy_deck (strategy/transformation keywords)
    │
    └─ One-click download → polished PPTX
```

---

## 5. Smart Template Router

### Detection Rules

| Template | Trigger Keywords | Slide Structure |
|----------|-----------------|-----------------|
| `bid_proposal` | bid, RFP, proposal, bidding, tender | Cover → Exec Summary → Solution → Team → Pricing → Cases |
| `operations_report` | report, metrics, KPI, operations, ops | Cover → Health → KPI Dashboard → Bottlenecks → Risk Matrix → Recommendations |
| `sop_design` | SOP, workflow, process, standard, procedure | Cover → Process Overview → Swimlane Flow → Roles → SLA → Escalation |
| `strategy_deck` | strategy, transformation, roadmap, vision | Cover → Current State → Target State → Gap Analysis → Execution Plan |

### Fallback
If no keyword match, default to `operations_report`.

---

## 6. Single-Page UI Architecture

```
┌────────────────────────────────────────────┐
│  BSC Studio                    [Settings?] │
├────────────────────────────────────────────┤
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │  Paste your business requirements... │  │
│  │                                      │  │
│  │                              [Send]  │  │
│  └──────────────────────────────────────┘  │
│  [Content] [Customer] [Risk] [Bid] [Ops]  │
│                                            │
│  ──── Results appear below ────            │
│                                            │
│  ┌─────────┬─────────┬─────────┐          │
│  │ Health  │ Modules │ Risks   │          │
│  │  87/100 │    5    │  2 High │          │
│  └─────────┴─────────┴─────────┘          │
│                                            │
│  Detected: Bid Proposal ▼                  │
│                                            │
│  [Download PPTX]  [Download HTML]          │
│                                            │
└────────────────────────────────────────────┘
```

---

## 7. Technical Changes Required

### Frontend (`static/index.html`)
1. Replace pipeline debug bar with clean dashboard cards
2. Add template detection indicator ("Detected: Bid Proposal")
3. Single download button (auto-detected format)
4. Remove `output_types` from user-facing flow

### Backend
1. `POST /studio/ask` — already exists, works ✓
2. Add `template_type` to response from `studio_api.py`
3. Add keyword-based template detection in `goal_router.py` or new module
4. Route detected template to `asset_agent.py` PPT generation

### New Module
- `app/engines/template_router.py` — keyword-based template classification (lightweight, no LLM needed)

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Time from page load to first dashboard | <500ms |
| Time from click to PPT download | <5s |
| Template detection accuracy | >90% |
| User steps to complete task | 2 (type + click) |
| UI elements visible at rest | <10 |

---

## 9. Scope Boundaries

### In scope
- Single-page UI redesign (input → dashboard → export)
- Smart template router (4 templates)
- One-click PPT download
- Visual dashboard polish

### Out of scope
- Multi-tenancy / user accounts
- Collaborative editing
- Custom template builder
- PDF/Word export (keep existing but don't surface)
- Simulation/sandbox UI (keep API but don't surface in v2)

---

## 10. Risks

| Risk | Mitigation |
|------|-----------|
| Template misdetection | Strong default (operations_report) + user can override via keyword |
| Dashboard too sparse for power users | Keep "Advanced" tab linking to full `/docs` API |
| PPT quality not consulting-grade enough | Iterate on CATARC template; add more visual templates |
