// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GrowthFunnel } from './GrowthFunnel';
import { GrowthTrends } from './GrowthTrends';

const counts = { sources: 10, eligible_sources: 8, pages: 5, methods: 2, published_methods: 1, outputs: 4, accepted_outputs: 3, rejected_outputs: 1, feedback: 2 };
const health = { status: 'available', citation_coverage: 0.8, orphan_page_ids: ['page-a'], stale_page_ids: [], uncited_eligible_source_ids: ['source-a'], pending_proposal_ids: [], dangling_citation_count: 0, stale_citation_count: 1, contradiction_count: 0, contradiction_pairs: [], evaluation: { status: 'available', latest_score: 88, runs: 2, reason: '' } };
const trend = {
  source_throughput: [{ date: '2026-07-01', count: 2 }, { date: '2026-07-20', count: 4 }],
  proposal_outcomes: [{ date: '2026-07-20', statuses: { published: 2, rejected: 1 } }],
  evaluations: [{ at: '2026-07-20T10:00:00Z', score: 88, baseline_score: 84, score_delta: 4, latency_ms: 32, status: 'completed' }],
  current: health,
};

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })) });
});
afterEach(() => cleanup());

describe('GrowthFunnel', () => {
  it('exposes API-derived counts and conversion summaries accessibly', () => {
    render(<GrowthFunnel counts={counts} state="success" />);
    expect(screen.getByRole('table', { name: 'Persisted growth funnel values' })).toHaveTextContent('A Evidence10');
    expect(screen.getByText('50%', { selector: 'dd' })).toBeVisible();
    expect(screen.getByText('200%', { selector: 'dd' })).toBeVisible();
  });

  it('does not draw fake activity for all-zero values', () => {
    render(<GrowthFunnel counts={{ ...counts, sources: 0, pages: 0, methods: 0, outputs: 0 }} state="success" />);
    expect(screen.getByText(/No persisted A\/B\/C\/D records/)).toBeVisible();
    expect(document.querySelector('[data-chart="growth-funnel"]')).not.toBeInTheDocument();
  });

  it('shows the error rather than retaining a chart', () => {
    render(<GrowthFunnel counts={counts} state="error" error="Server error (500). metrics failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Server error (500)');
    expect(document.querySelector('[data-chart="growth-funnel"]')).not.toBeInTheDocument();
  });
});

describe('GrowthTrends', () => {
  it('renders persisted quality summaries, date filters and missing metric disclosure', () => {
    render(<GrowthTrends trend={trend} health={health} counts={counts} state="success" onRetry={vi.fn()} />);
    expect(screen.getByText('80%')).toBeVisible();
    expect(screen.getByText('75%')).toBeVisible();
    expect(screen.getByText('not exposed by P7')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '7d' }));
    expect(screen.getByRole('button', { name: '7d' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders explicit empty series without manufacturing points', () => {
    render(<GrowthTrends trend={{ ...trend, source_throughput: [], proposal_outcomes: [], evaluations: [] }} health={{ ...health, orphan_page_ids: [], uncited_eligible_source_ids: [], stale_citation_count: 0 }} counts={counts} state="success" onRetry={vi.fn()} />);
    expect(screen.getByText(/No source throughput observations/)).toBeVisible();
    expect(screen.getByText(/No evaluation observations/)).toBeVisible();
    expect(screen.getByText(/No proposal outcomes/)).toBeVisible();
    expect(screen.getByText(/No persisted quality debt/)).toBeVisible();
  });

  it('renders a retryable unavailable state', () => {
    const retry = vi.fn();
    render(<GrowthTrends trend={null} health={null} counts={counts} state="unavailable" error="health endpoint disabled" onRetry={retry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('health endpoint disabled');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
