# BSC Studio — Frontend Design Upgrade

**Audit Date:** 2026-07-05  
**Scope:** `bsc-backend/static/index.html` (BSC Copilot — the AI Q&A dashboard)  
**Audience:** Business consultants and managers  
**Constraints:** Dark theme, single-page, no heavy frameworks, Inter + JetBrains Mono fonts

---

## 1. Current State Assessment

### What Works

| Strength | Detail |
|----------|--------|
| **Zero-framework architecture** | Pure HTML/CSS/JS — loads instantly, no build step, no dependency rot |
| **Fade-up stagger animation** | `fadeUp` keyframes with staggered delays create a polished reveal |
| **Keyboard-first UX** | Enter to submit, Ctrl+K to focus — power-user friendly |
| **Example prompts as chips** | Quick-start affordance lowers the barrier to first use |
| **Semantic result sections** | Modules, KPIs, Risks, Recommendations — clear business taxonomy |
| **Multi-format downloads** | PPT, HTML, JSON export links in a tidy bar |

### What Needs Change

| Problem | Impact |
|---------|--------|
| **Theme is actually light, not dark** | `--bg: #FAFBFC` reads as a white-gray page — contradicts the stated dark-theme preference and feels unpolished for a "business intelligence" tool |
| **Flat visual hierarchy** | All result sections share identical card styling — Summary, Risks, and KPIs carry equal visual weight, making the dashboard unscannable |
| **Health Score is hidden in a badge** | The single most important metric is a tiny `<span class="badge mod">` — no gauge, no color coding, buried among module counts |
| **KPIs are plain text tiles** | `kpi-cell` is just name + value in a 2-column grid — no sparklines, no thresholds, no red/green indicators |
| **Risk levels are undersized** | `tag-hi` / `tag-md` / `tag-lo` are 4-character abbreviations in tiny tags — a missed opportunity for visual urgency |
| **Empty state is too tall** | `min-height: 90vh` pushes the input box to center — after first use, the large whitespace feels wasteful |
| **No sidebar / navigation context** | The page has no branding, no nav, no context about BSC Studio — it floats in isolation |

---

## 2. Prioritized Improvements

### #1 — True Dark Theme with Professional Palette

**Rationale:** The current `--bg: #FAFBFC` is light gray on white. Business intelligence tools (Grafana, Tableau, Datadog) default to dark. The `studio.html` and `dashboard.html` pages already use proper dark themes (`#12161A`, `#141413`). `index.html` should align.

**Specific changes:**
- Switch root to a dark surface: `--bg: #0D1117` (GitHub-dark inspired), `--card: #161B22`, `--border: #30363D`
- Keep the blue accent (`#2563EB`) but warm it slightly for dark backgrounds: `#58A6FF`
- Add a subtle grid dot background pattern for depth (like `workspace.html` uses)
- Ensure contrast ratios meet WCAG AA for body text on dark backgrounds

### #2 — Executive Summary "Hero" Card with Health Gauge

**Rationale:** The summary section currently shows a title + paragraph + badge row. This is the *first thing* a consultant sees — it should communicate business health at a glance.

**Specific changes:**
- Upgrade Summary to a "hero" card: wider, with a left-aligned health gauge (CSS-only radial gauge, 0–100) and key stat clusters beside it
- Health score gets color coding: Red (0–40), Orange (40–65), Green (65–100)
- Pull the top 3 KPIs into the hero as mini stat cards with delta indicators (↑/↓)
- Badge row moves below as a secondary detail strip

### #3 — Risk Severity Heatmap Strip

**Rationale:** Risks in a flat list with abbreviated tags don't convey urgency to a manager scanning the page.

**Specific changes:**
- Replace the `.item` list for risks with a horizontal severity strip
- Each risk becomes a colored bar segment: width = probability, color = impact (red = critical, orange = high, yellow = medium, gray = low)
- Hover reveals the full risk name and mitigation
- This mirrors how `dashboard.html` renders a risk heatmap with ECharts — but CSS-only, no library dependency

### #4 — KPI Cards with Threshold Indicators

**Rationale:** `kpi-grid` currently shows name + value as plain text. A manager skimming the page can't tell if a KPI is healthy without reading numbers.

**Specific changes:**
- Redesign `kpi-cell` into a proper mini card: icon slot, value (large), label (small), and a horizontal progress bar showing current vs. target
- Color the progress bar: green (on track), orange (warning zone), red (below threshold)
- Use CSS custom properties to drive colors from the data (e.g., `style="--pct: 0.72; --status: green"`)
- Maintain the 2-column grid on desktop, stack to 1-column on mobile

### #5 — Compact Empty State + Contextual Branding

**Rationale:** After generating a result, the user still sees the input box at the top — but it's floating above 90vh of nothing. The page also lacks any BSC Studio branding or navigation crumbs.

**Specific changes:**
- Shrink empty state to `min-height: auto` once a result exists (already partially done via `.has-result` but the transition is jarring)
- Add a minimal top bar with: BSC Studio logo mark, page title ("Copilot"), and a "New Analysis" button
- Move input into a sticky footer bar (like ChatGPT/Claude) so it's always accessible but doesn't dominate the viewport
- Add a thin sidebar or breadcrumb showing the current project context (if any)

---

## 3. Visual System Proposal

### Colors

```
┌─────────────────────────────────────────────────────────┐
│  Role          Light (current)     Dark (proposed)      │
├─────────────────────────────────────────────────────────┤
│  Background    #FAFBFC             #0D1117               │
│  Card surface  #FFFFFF             #161B22               │
│  Card hover    —                   #1C2128               │
│  Border        #E5E7EB             #30363D               │
│  Text primary  #1A1A2E             #E6EDF3               │
│  Text secondary #4A4A6A            #8B949E               │
│  Text muted    #8A8AA0             #484F58               │
│  Accent blue   #2563EB             #58A6FF               │
│  Accent green  #10B981             #3FB950               │
│  Accent red    #EF4444             #F85149               │
│  Accent orange #F59E0B             #D29922               │
│  Gold accent   —                   #C9A84C (from studio)│
└─────────────────────────────────────────────────────────┘
```

**Rationale:** The proposed palette aligns with GitHub's dark dimmed theme — a familiar, proven scheme for developer-adjacent tools. The gold accent (`#C9A84C`) ties `index.html` into the broader BSC Studio brand (`studio.html` uses it for the logo mark and primary buttons).

### Typography

```
┌─────────────────────────────────────────────────────────┐
│  Token          Size    Weight   Use                    │
├─────────────────────────────────────────────────────────┤
│  --text-2xl     1.5rem  700      Page title / hero      │
│  --text-xl      1.25rem 600      Section headers         │
│  --text-lg      1rem    600      Card titles             │
│  --text-base    0.875rem 400     Body text               │
│  --text-sm      0.75rem 400     Secondary labels         │
│  --text-xs      0.688rem 500    Badges, meta, captions   │
│  --text-mono    0.75rem 400     Code, data values        │
└─────────────────────────────────────────────────────────┘
```

**Fonts:** Keep `Inter` (sans) + `JetBrains Mono` (mono) — consistent across BSC Studio. Add `Noto Sans SC` for Chinese glyphs as currently done.

### Spacing Scale

```
--space-xs:  4px    (inline gaps, icon-to-text)
--space-sm:  8px    (card padding internal)
--space-md:  16px   (section gaps, grid gutters)
--space-lg:  24px   (major section separation)
--space-xl:  40px   (page-level padding)
```

### Motion

| Element | Duration | Easing | Notes |
|---------|----------|--------|-------|
| Section fade-up | 350ms | `ease` | Keep existing, works well |
| Stagger delay | 50ms per section | — | Keep existing |
| Card hover lift | 150ms | `ease-out` | `translateY(-2px)` + shadow increase |
| Health gauge fill | 800ms | `ease-out` | CSS transition on `stroke-dashoffset` |
| Toast enter/exit | 200ms | `ease` | Slide down + fade |
| Input focus ring | 200ms | `ease` | Border color + box-shadow transition |

---

## 4. Wireframe — Dashboard Result View

```
┌──────────────────────────────────────────────────────────────────┐
│  [BSC]  BSC Copilot                           [+ New Analysis]   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  BUSINESS HEALTH ANALYSIS                                   │ │
│  │                                                             │ │
│  │     ╭──────╮     ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │    ╱        ╲    │ Revenue  │  │ Margin   │  │ Cust Sat │ │ │
│  │   │   72/100 │   │  $4.2M ↑ │  │  34%  ↑  │  │   88%  → │ │ │
│  │    ╲        ╱    └──────────┘  └──────────┘  └──────────┘ │ │
│  │     ╰──────╯                                               │ │
│  │                                                             │ │
│  │  The business system shows strong operational health with   │ │
│  │  improving revenue trajectory. Customer satisfaction remains │ │
│  │  stable at 88%. Three areas require attention...            │ │
│  │                                                             │ │
│  │  [8 Modules]  [12 Processes]  [3 Risks]  [Health 72/100]   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  BUSINESS MODULES                                [view all] │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │ │
│  │  │ 01       │ │ 02       │ │ 03       │ │ 04       │      │ │
│  │  │ Sales    │ │ Marketing│ │ Finance  │ │ HR       │      │ │
│  │  │ B2B/Retail│ │ Digital  │ │ AR/AP    │ │ Talent   │      │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  KPI DASHBOARD                                              │ │
│  │  ┌──────────────────┐  ┌──────────────────┐                │ │
│  │  │ 💰 Revenue       │  │ 📊 Gross Margin  │                │ │
│  │  │  $4.2M           │  │       34%        │                │ │
│  │  │ ████████████░░ 85%│  │ ██████████░░░ 72%│                │ │
│  │  │ Target: $5M       │  │ Target: 40%      │                │ │
│  │  └──────────────────┘  └──────────────────┘                │ │
│  │  ┌──────────────────┐  ┌──────────────────┐                │ │
│  │  │ 😊 Cust. Sat     │  │ 🔻 Churn Rate    │                │ │
│  │  │       88%        │  │       5.2%       │                │ │
│  │  │ ██████████████ 88%│  │ ████░░░░░░░░░ 28%│                │ │
│  │  │ Target: 90%       │  │ Target: <3%      │                │ │
│  │  └──────────────────┘  └──────────────────┘                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  RISK HEATMAP                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │ HIGH   ████████  Supply chain disruption             │  │ │
│  │  │ MED    ██████    Talent retention risk               │  │ │
│  │  │ LOW    ████      Currency fluctuation                │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  RECOMMENDATIONS                                           │ │
│  │  01  Diversify supplier base across 3+ regions             │ │
│  │  02  Implement employee stock option program               │ │
│  │  03  Hedge 40% of forex exposure through forward contracts │ │
│  │  04  Launch customer loyalty tier program                  │ │
│  │  05  Automate AR reconciliation to reduce DSO by 5 days    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  📥 Download  [📊 PPT Report]  [🌐 HTML Dashboard]  [📋 JSON]│ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Ask about this business system...                  [→]  │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**Key wireframe decisions:**
- Hero card at top with CSS radial health gauge (left) + 3 highlight KPIs (right) — no library needed
- Modules shown as a horizontal card row instead of a vertical numbered list — easier to scan
- KPI cards have progress bars with color coding — immediate visual feedback
- Risks shown as a severity bar chart — width encodes probability, color encodes impact
- Recommendations stay as a numbered list (works well — scannable actions)
- Sticky input footer replaces the centered empty-state input

---

## 5. Implementation Plan

### Phase 1: Theme & Foundation (1 file)
**File:** `bsc-backend/static/index.html`

1. Replace `:root` CSS variables with dark theme palette
2. Add `body::before` dot-grid background pattern
3. Adjust all existing component colors (badges, tags, borders) to dark equivalents
4. Add CSS custom properties for the new spacing scale

### Phase 2: Hero Card + Health Gauge (1 file)
**File:** `bsc-backend/static/index.html`

5. Redesign `.summary-card` → `.hero-card` with CSS grid layout
6. Build CSS-only radial health gauge using `conic-gradient` + `border-radius`
7. Pull top 3 metrics into hero as `.hero-stat` mini cards
8. Wire health score color coding (red/orange/green) via CSS custom properties

### Phase 3: KPI Cards + Risk Heatmap (1 file)
**File:** `bsc-backend/static/index.html`

9. Redesign `.kpi-cell` → `.kpi-card` with progress bar and threshold colors
10. Replace risk `.item` list with `.risk-bar` horizontal severity bars
11. Update `render()` JS function to emit new HTML structures
12. Add hover tooltips for risk details (CSS-only `:hover` + `::after`)

### Phase 4: Layout & Navigation (1 file)
**File:** `bsc-backend/static/index.html`

13. Add minimal top bar with BSC logo mark and "New Analysis" action
14. Convert input area to sticky footer bar
15. Shrink empty-state height transition
16. Add module cards as horizontal grid instead of vertical list

### Phase 5: Polish (1 file)
**File:** `bsc-backend/static/index.html`

17. Verify all contrast ratios meet WCAG AA
18. Add `prefers-reduced-motion` media query to disable animations
19. Test on 1280px, 1440px, and mobile (375px) viewports
20. Ensure keyboard navigation works end-to-end

**Total files changed: 1** (`index.html`). No new dependencies. No build step. All CSS-only solutions for charts and gauges.

---

## Appendix: CSS-Only Health Gauge Implementation Sketch

```css
.health-gauge {
  --score: 72;           /* driven by JS via style attribute */
  --color: #3FB950;      /* green by default */
  --size: 100px;
  --stroke: 8px;
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  background: conic-gradient(
    var(--color) calc(var(--score) * 1%),
    #21262D calc(var(--score) * 1%)
  );
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.health-gauge::after {
  content: "";
  width: calc(var(--size) - var(--stroke) * 2);
  height: calc(var(--size) - var(--stroke) * 2);
  border-radius: 50%;
  background: #161B22;
  position: absolute;
}
.health-gauge .score {
  position: relative;
  z-index: 1;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color);
}
```

---

*Generated for BSC Studio frontend audit — ECC design direction methodology.*
