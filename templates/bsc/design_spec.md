---
template_id: bsc-business-system
kind: deck
summary: "Business System Compiler - PRD to SOP/KPI/Risk executive report"
canvas_format: ppt169
page_count: 7
primary_color: "#1B3A5C"
---

# BSC Business System - Design Specification

## I. Template Overview

| Property | Description |
| --- | --- |
| **Template Name** | BSC Business System |
| **Use Cases** | PRD compilation, SOP design, KPI dashboards, risk analysis, executive reporting |
| **Design Tone** | Professional navy/teal, data-dense but clean, consulting-grade |
| **Theme Mode** | Hybrid (dark navy cover/ending + light content pages) |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| **Format** | Standard 16:9 |
| **Dimensions** | 1280 x 720 px |
| **viewBox** | `0 0 1280 720` |
| **Safe Margins** | 60px all sides |

## III. Color Scheme

| Role | Color Value | Usage |
| --- | --- | --- |
| **Navy** | `#1B3A5C` | Cover bg, header bars, table headers |
| **Teal** | `#2E86AB` | Accent lines, KPI bars, workflow nodes |
| **Red** | `#E83151` | Risk indicators, end nodes, critical alerts |
| **Green** | `#2CA02C` | Start nodes, positive KPI, low risk |
| **Orange** | `#F4A261` | Decision nodes, warnings, medium risk |
| **Purple** | `#9467BD` | Wait nodes, secondary metrics |
| **Light BG** | `#F0F4F8` | Content page backgrounds |
| **White** | `#FFFFFF` | Card backgrounds, clean areas |
| **Dark Text** | `#2D3436` | Primary copy |
| **Gray** | `#636E72` | Secondary copy, metadata |

## IV. Typography System

| Level | Usage | Size | Weight |
| --- | --- | --- | --- |
| **H1** | Cover title | 42px | Bold |
| **H2** | Slide title | 26px | Bold |
| **H3** | Section label | 12px | Bold |
| **Body** | Content | 12px | Regular |
| **Caption** | Footer / notes | 9px | Regular |
| **Metric Value** | KPI cards | 28px | Bold |

Font Stack: `"Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif`

## V. Page Types

1. **Cover** (`01_cover.svg`) - Navy background, title, accent line, domain badge
2. **TOC** (`02_toc.svg`) - Light page, numbered agenda items
3. **KPI Dashboard** (`03_kpi.svg`) - Metric cards with branch colors, catalog table
4. **Workflow** (`04_workflow.svg`) - Swimlane process with color-coded nodes
5. **Risk Matrix** (`05_risk.svg`) - Heatmap table, mitigations, optimizations
6. **Summary** (`06_summary.svg`) - Two-column executive view
7. **Ending** (`07_ending.svg`) - Navy background, closing message

## VI. Placeholder Specification

| Placeholder | Description |
| --- | --- |
| `{{TITLE}}` | Cover main title |
| `{{SUBTITLE}}` | Cover subtitle / objective |
| `{{DOMAIN}}` | Domain badge text |
| `{{DATE}}` | Report date |
| `{{PAGE_TITLE}}` | Content page title |
| `{{CHAPTER_NUM}}` | Chapter/slide number |
| `{{CONTENT_ROWS}}` | Dynamic content rows (KPI cards, risk items, etc.) |
