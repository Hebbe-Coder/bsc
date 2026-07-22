// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  addGrowthOutputFeedback,
  GrowthRequestError,
  fetchGrowthAccess,
  fetchGrowthAssetDetail,
  fetchGrowthHealth,
  fetchGrowthLineage,
  fetchGrowthOverview,
  fetchGrowthStage,
  fetchGrowthTrend,
  fileGrowthOutput,
} from '../../api/growthApi';
import { useGrowthWorkspaceStore } from '../../store/knowledgeWorkspaceStore';
import { GrowthWorkspace } from './GrowthWorkspace';

vi.mock('../../api/growthApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/growthApi')>();
  return {
    ...actual,
    fetchGrowthAccess: vi.fn(),
    fetchGrowthAssetDetail: vi.fn(),
    fetchGrowthHealth: vi.fn(),
    fetchGrowthLineage: vi.fn(),
    fetchGrowthOverview: vi.fn(),
    fetchGrowthStage: vi.fn(),
    fetchGrowthTrend: vi.fn(),
    addGrowthOutputFeedback: vi.fn(),
    fileGrowthOutput: vi.fn(),
    processGrowthFeedback: vi.fn(),
    setGrowthAccessKey: vi.fn(),
    triageGrowthSource: vi.fn(),
  };
});

const mockedOverview = vi.mocked(fetchGrowthOverview);
const mockedAccess = vi.mocked(fetchGrowthAccess);
const mockedStage = vi.mocked(fetchGrowthStage);
const mockedDetail = vi.mocked(fetchGrowthAssetDetail);
const mockedHealth = vi.mocked(fetchGrowthHealth);
const mockedTrend = vi.mocked(fetchGrowthTrend);
const mockedLineage = vi.mocked(fetchGrowthLineage);
const mockedAddFeedback = vi.mocked(addGrowthOutputFeedback);
const mockedFileOutput = vi.mocked(fileGrowthOutput);

const overview = {
  profile: { project_id: 'default', user_role: 'researcher', revision: 3 },
  summary: { project_id: 'default', counts: { sources: 25, eligible_sources: 20, pages: 1, methods: 1, published_methods: 1, outputs: 1, accepted_outputs: 1, rejected_outputs: 0, feedback: 1, wiki_proposals: 1, review_records: 2 } },
};
const source = { id: 'source-a', origin: 'Source brief', status: 'eligible', created_at: '2026-07-20T09:00:00Z', content_hash: 'a'.repeat(64) };
const page = { id: 'page-a', title: 'Wiki page', path: 'wiki/page.md', status: 'published', updated_at: '2026-07-21T09:00:00Z' };

function installSuccessfulProject() {
  mockedOverview.mockResolvedValue(overview);
  mockedAccess.mockResolvedValue({ role: 'project_admin', can_write: true, features: { wiki: true } });
  mockedStage.mockImplementation(async (_projectId, stage, limit) => {
    const records = stage === 'A' ? [source] : stage === 'B' ? [page] : [];
    return { project_id: 'default', stage, records, limit, truncated: false };
  });
  mockedDetail.mockImplementation(async (_projectId, stage, assetId) => stage === 'B'
    ? { kind: 'page', record: page, content: '# Persisted wiki\nEvidence-backed paragraph.', citations: [{ id: 'citation-a', source_id: 'source-a' }], revisions: [], backlinks: [], detailAvailability: 'complete' }
    : { kind: 'source', record: { ...source, id: assetId }, detailAvailability: 'metadata_only', detailMessage: 'Raw evidence bodies are intentionally excluded from this API.' });
  mockedHealth.mockResolvedValue({ status: 'available', citation_coverage: 1, orphan_page_ids: [], stale_page_ids: [], uncited_eligible_source_ids: [], pending_proposal_ids: [], dangling_citation_count: 0, stale_citation_count: 0, contradiction_count: 0, contradiction_pairs: [], evaluation: { status: 'available', latest_score: 92, runs: 1, reason: '' } });
  mockedTrend.mockResolvedValue({ source_throughput: [{ date: '2026-07-20', count: 2 }], proposal_outcomes: [], evaluations: [], current: {} as never });
  mockedLineage.mockResolvedValue({ project_id: 'default', edges: [], limit: 200, truncated: false });
  mockedAddFeedback.mockResolvedValue({ id: 'feedback-new', status: 'pending' });
  mockedFileOutput.mockResolvedValue({ id: 'output-a', status: 'filed' });
}

beforeEach(() => {
  vi.clearAllMocks();
  useGrowthWorkspaceStore.getState().reset();
  installSuccessfulProject();
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })) });
});

afterEach(() => cleanup());

describe('GrowthWorkspace', () => {
  it('loads stage, list and detail, then supports keyboard stage navigation', async () => {
    render(<GrowthWorkspace onClose={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: 'Knowledge growth workspace' })).toBeVisible();
    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));
    expect((await screen.findAllByText(/Raw evidence bodies are intentionally excluded/i))[0]).toBeVisible();

    const evidenceTab = screen.getByRole('tab', { name: /Evidence/i });
    fireEvent.keyDown(evidenceTab, { key: 'ArrowRight' });

    await waitFor(() => expect(mockedStage).toHaveBeenCalledWith('default', 'B', 20, expect.any(AbortSignal)));
    fireEvent.click(await screen.findByRole('option', { name: /Wiki page/i }));
    expect(await screen.findByRole('heading', { name: 'Persisted wiki' })).toBeVisible();
    expect(screen.getByText('Evidence-backed paragraph.')).toBeVisible();
  });

  it('requests a larger real server slice for the next page', async () => {
    mockedStage.mockImplementation(async (_projectId, stage, limit) => {
      const count = Math.min(limit, 25);
      return { project_id: 'default', stage, records: Array.from({ length: count }, (_, index) => ({ id: `source-${index + 1}`, origin: `Source ${index + 1}`, status: 'eligible' })), limit, truncated: count >= limit };
    });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    const next = await screen.findByRole('button', { name: 'Next asset page' });
    fireEvent.click(next);

    await waitFor(() => expect(mockedStage).toHaveBeenCalledWith('default', 'A', 40, expect.any(AbortSignal)));
    expect(await screen.findByRole('option', { name: /Source 21/i })).toBeVisible();
    expect(screen.getByText('Page 2')).toBeVisible();
  });

  it('loads the complete bounded slice before applying search and status filters', async () => {
    render(<GrowthWorkspace onClose={vi.fn()} />);
    const search = await screen.findByPlaceholderText('Search ID, title, path');
    fireEvent.change(search, { target: { value: 'brief' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'eligible' } });

    await waitFor(() => expect(mockedStage).toHaveBeenCalledWith('default', 'A', 500, expect.any(AbortSignal)));
    expect(screen.getByRole('option', { name: /Source brief/i })).toBeVisible();
  });

  it('renders a persisted proposal as a reviewable current/proposed diff', async () => {
    const proposal = { id: 'proposal-a', status: 'candidate', rationale: 'Improve evidence', operations: [{ id: 'operation-a', operation: 'update', path: 'wiki/page.md', content: '# New content' }] };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'review' ? [proposal] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'review'
      ? { kind: 'proposal', record: proposal, baselines: { 'wiki/page.md': '# Old content' }, detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('tab', { name: /Review/i }));
    fireEvent.click(await screen.findByRole('option', { name: /proposal-a/i }));

    expect(await screen.findByText('Current published content')).toBeVisible();
    expect(screen.getByText('# Old content')).toBeVisible();
    expect(screen.getByText('# New content')).toBeVisible();
  });

  it('shows verified output content, evaluation history and usable feedback actions', async () => {
    const output = { id: 'output-a', title: 'Verified SOP', status: 'accepted', asset_type: 'output', vault_path: 'outputs/2026/output-a/sop.md' };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'D' ? [output] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'D'
      ? { kind: 'output', record: output, content: '# Verified SOP\nGrounded result.', evaluations: [{ id: 'eval-a', quality: 96, groundedness: 0.98, status: 'completed' }], feedback: [], detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('tab', { name: /Outputs/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Verified SOP/i }));

    expect((await screen.findAllByRole('heading', { name: 'Verified SOP' })).length).toBeGreaterThan(0);
    expect(screen.getByText('Grounded result.')).toBeVisible();
    expect(screen.getByText('96')).toBeVisible();

    fireEvent.change(screen.getByRole('combobox', { name: 'Output feedback type' }), { target: { value: 'rated' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Output feedback rating' }), { target: { value: '97' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit feedback' }));
    await waitFor(() => expect(mockedAddFeedback).toHaveBeenCalledWith('default', 'output-a', { feedback_type: 'rated', rating: 97 }));

    fireEvent.click(screen.getByRole('button', { name: 'File accepted output' }));
    await waitFor(() => expect(mockedFileOutput).toHaveBeenCalledWith('default', 'output-a'));
  });

  it('renders method content without duplicating the active revision JSON in metadata', async () => {
    const method = { id: 'method-a', name: 'Evidence synthesis', status: 'published', active_revision_id: 'method-revision-a' };
    const activeRevision = { id: 'method-revision-a', body: '# Evidence synthesis\nApply the verified sequence.', version: 2 };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'C' ? [method] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'C'
      ? { kind: 'method', record: { ...method, active_revision: activeRevision }, content: activeRevision.body, revisions: [activeRevision], detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('tab', { name: /Methods/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Evidence synthesis/i }));

    expect(await screen.findByText('Apply the verified sequence.')).toBeVisible();
    expect(screen.queryByText('active revision')).not.toBeInTheDocument();
    expect(screen.queryByText(JSON.stringify(activeRevision))).not.toBeInTheDocument();
  });

  it('clears prior success data and exposes a 500 boundary', async () => {
    mockedOverview.mockImplementation(async (projectId) => {
      if (projectId === 'broken') throw new GrowthRequestError('database unavailable', 'growth_internal_error', 500);
      return overview;
    });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    expect(await screen.findByText('Source brief')).toBeVisible();

    fireEvent.change(screen.getByRole('textbox', { name: 'Growth project ID' }), { target: { value: 'broken' } });
    fireEvent.click(screen.getByRole('button', { name: /Load/i }));

    expect(await screen.findByText('Server boundary reached')).toBeVisible();
    expect(screen.getByText(/Server error \(500\).*database unavailable/i)).toBeVisible();
    expect(screen.queryByText('Source brief')).not.toBeInTheDocument();
  });

  it.each([
    [new GrowthRequestError('forbidden', 'project_forbidden', 403), 'Project access denied'],
    [new GrowthRequestError('disabled', 'knowledge_growth_disabled', 503), 'Growth workspace unavailable'],
    [new GrowthRequestError('offline', 'knowledge_growth_offline', 0, 'offline'), 'Knowledge service offline'],
  ])('renders an explicit request boundary for %s', async (failure, title) => {
    mockedOverview.mockRejectedValue(failure);
    render(<GrowthWorkspace onClose={vi.fn()} />);
    expect(await screen.findByText(title)).toBeVisible();
    expect(screen.queryByText('Source brief')).not.toBeInTheDocument();
  });

  it('shows a truthful empty state without mock records', async () => {
    mockedOverview.mockResolvedValue({ ...overview, summary: { project_id: 'default', counts: { sources: 0, eligible_sources: 0, pages: 0, methods: 0, published_methods: 0, outputs: 0, accepted_outputs: 0, rejected_outputs: 0, feedback: 0 } } });
    mockedStage.mockResolvedValue({ project_id: 'default', stage: 'A', records: [], limit: 20, truncated: false });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    expect(await screen.findByText('No persisted assets exist in this stage.')).toBeVisible();
    expect(document.querySelector('.growth-record-list')).not.toBeInTheDocument();
  });

  it('gates write actions using the real project permission state', async () => {
    mockedAccess.mockResolvedValue({ role: 'viewer', can_write: false, features: { wiki: true } });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));

    const action = await screen.findByRole('button', { name: 'Run evidence triage' });
    expect(action).toBeDisabled();
    expect(screen.getByText(/Read-only project role/)).toBeVisible();
  });

  it('opens a mobile inspector drawer and closes it with Escape', async () => {
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn((query: string) => ({ matches: query.includes('760px'), media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })) });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));

    expect(await screen.findByRole('dialog', { name: 'Growth inspector' })).toBeVisible();
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Growth inspector' })).not.toBeInTheDocument());
  });
});
