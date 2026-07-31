// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { captureKnowledgePrimaryWebSource, createKnowledgeInformationSource, fetchKnowledgeInformationOverview, runKnowledgeInformationManualIngress, type KnowledgeInformationOverview } from '../../api/knowledgeWorkspaceApi';
import { InformationOperationsPanel } from './InformationOperationsPanel';

vi.mock('../../api/knowledgeWorkspaceApi', () => ({
  captureKnowledgePrimaryWebSource: vi.fn(),
  createKnowledgeInformationSource: vi.fn(),
  fetchKnowledgeInformationOverview: vi.fn(),
  runKnowledgeInformationManualIngress: vi.fn(),
}));

const overview = {
  state: 'ready' as const,
  source_registry: [],
  receipts: [],
  runs: [{
    id: 'run-1', run_type: 'information_signal_ingress', trigger: 'n8n', status: 'completed', error: '', retry_of: null,
    input_refs: { batch_id: 'rss-execution-source-0', item_count: 1 },
    output_refs: { receipt_count: 1, failure_count: 0 },
    created_at: '2026-07-29T00:00:00Z', updated_at: '2026-07-29T00:00:01Z',
  }],
  counts: { sources: 2, available_sources: 1, unavailable_sources: 0, captured: 6, new_sources: 2, duplicate_sources: 4, lead_only: 0, rejected: 0 },
};

const overviewWithBrief: KnowledgeInformationOverview = {
  ...overview,
  horizon_review_queue: {
    project_id: 'project-a', state: 'available', count: 1,
    items: [{ source_id: 'horizon-pending', title: 'Needs primary review', origin: 'https://example.com/radar', status: 'eligible', trust_level: 'reviewed', ai_score: 8.7, task_families: ['research'], next_action: 'capture_primary_source' }],
  },
  daily_brief: {
    project_id: 'project-a', state: 'available', coverage: 'complete', denominator: 2,
    window: { date: '2026-07-31', timezone: 'Asia/Shanghai', start_at: '2026-07-30T16:00:00Z', end_at: '2026-07-31T16:00:00Z' },
    summary: { captured: 1, repeat_discoveries: 0, confirmation_required: 1, rejected: 0, failures: 0 },
    sections: {
      captured: { count: 1, items: [{ receipt_id: 'receipt-1', batch_id: 'batch-1', registry_id: 'source-1', source_id: 'source-1', disposition: 'captured', reason: '', canonical_url: 'https://example.com/captured', title: 'Captured evidence', published_at: '', source_created: true, created_at: '' }] },
      repeat_discoveries: { count: 0, items: [] },
      confirmation_required: { count: 1, items: [{ receipt_id: 'receipt-2', batch_id: 'batch-2', registry_id: 'source-1', source_id: 'source-lead', disposition: 'lead_only', reason: '', canonical_url: 'https://example.com/lead', title: 'Needs original source', published_at: '', source_created: true, created_at: '' }] },
      rejected: { count: 0, items: [] },
      failures: { count: 0, items: [] },
    },
    confirmation_queue: [{ receipt_id: 'receipt-2', batch_id: 'batch-2', registry_id: 'source-1', source_id: 'source-lead', disposition: 'lead_only', reason: '', canonical_url: 'https://example.com/lead', title: 'Needs original source', published_at: '', source_created: true, created_at: '', next_action: 'capture_original_source' }],
    lineage: { batch_ids: ['batch-1', 'batch-2'], run_ids: ['run-1', 'run-2'], receipt_ids: ['receipt-1', 'receipt-2'], source_ids: ['source-1', 'source-lead'], revision: 'abc123456789abcd' },
    delivery: { provider: 'feishu', state: 'unavailable', reason: 'delivery_not_configured', attempts: [] },
  },
};

describe('InformationOperationsPanel', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('registers a YouTube channel as its canonical Channel RSS feed and shows durable run details', async () => {
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overview);
    vi.mocked(createKnowledgeInformationSource).mockResolvedValue({ source: {} as never });
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} />);

    expect(await screen.findByText('INGRESS RUN HISTORY')).toBeVisible();
    expect(screen.getByText('rss-execution-source-0')).toBeVisible();
    expect(screen.getByText('1 signal / 1 receipt')).toBeVisible();
    fireEvent.change(screen.getByLabelText('Connector'), { target: { value: 'youtube_channel_rss' } });
    fireEvent.change(screen.getByLabelText('Source name'), { target: { value: 'BSC video channel' } });
    fireEvent.change(screen.getByLabelText('YouTube Channel ID or feed URL'), { target: { value: 'UC123' } });
    fireEvent.click(screen.getByRole('button', { name: /register source/i }));

    await waitFor(() => expect(createKnowledgeInformationSource).toHaveBeenCalledWith('project-a', expect.objectContaining({
      project_id: 'project-a', connector_type: 'youtube_channel_rss', channel_id: 'UC123',
      feed_url: 'https://www.youtube.com/feeds/videos.xml?channel_id=UC123',
    })));
  });

  it('separates repeat discovery receipts from new evidence assets', async () => {
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overview);
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} />);

    const metrics = await screen.findByLabelText('Information intake metrics');
    expect(within(metrics).getByText('New sources')).toBeVisible();
    expect(within(metrics).getByText('Repeat discoveries')).toBeVisible();
    expect(within(metrics).getByText('2 new evidence asset(s)')).toBeVisible();
    expect(within(metrics).getByText('4 repeat receipt(s), no source growth')).toBeVisible();
  });

  it('renders the completed-receipt daily brief and drills a confirmation lead into the source inspector', async () => {
    const inspect = vi.fn();
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overviewWithBrief);
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} onInspectSource={inspect} />);

    expect(await screen.findByText('DAILY INTELLIGENCE BRIEF')).toBeVisible();
    expect(screen.getByText('2 completed receipts')).toBeVisible();
    expect(screen.getAllByText('Needs original source').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect source source-lead' }));
    expect(inspect).toHaveBeenCalledWith('source-lead');
    expect(screen.queryByText(/Original body must stay outside/i)).toBeNull();
  });

  it('renders unpromoted Horizon signals as a primary-source review queue', async () => {
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overviewWithBrief);
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} />);

    expect(await screen.findByText('HORIZON PRIMARY-SOURCE REVIEW')).toBeVisible();
    expect(screen.getByText('Needs primary review')).toBeVisible();
    expect(screen.getByText('capture_primary_source')).toBeVisible();
    expect(screen.queryByText(/verified conclusion/i)).toBeNull();
  });

  it('captures a chosen Horizon origin as reviewable primary evidence without publishing a claim', async () => {
    const inspect = vi.fn();
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overviewWithBrief);
    vi.mocked(captureKnowledgePrimaryWebSource).mockResolvedValue({ source: { id: 'primary-evidence' } } as never);
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} onInspectSource={inspect} />);

    await screen.findByText('HORIZON PRIMARY-SOURCE REVIEW');
    fireEvent.click(screen.getByRole('button', { name: 'Capture primary source' }));

    await waitFor(() => expect(captureKnowledgePrimaryWebSource).toHaveBeenCalledWith(
      'project-a',
      'https://example.com/radar',
      'horizon-pending',
    ));
    await waitFor(() => expect(inspect).toHaveBeenCalledWith('primary-evidence'));
  });

  it('moves a Horizon signal with a linked capture to primary-evidence review instead of recapturing it', async () => {
    const inspect = vi.fn();
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue({
      ...overviewWithBrief,
      horizon_review_queue: {
        ...overviewWithBrief.horizon_review_queue!,
        items: [{
          ...overviewWithBrief.horizon_review_queue!.items[0],
          next_action: 'review_primary_capture',
          primary_capture: {
            source_id: 'primary-evidence', status: 'eligible', origin: 'https://example.com/radar', trust_level: 'reviewed',
          },
        }],
      },
    });
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} onInspectSource={inspect} />);

    await screen.findByText('review_primary_capture');
    expect(screen.getByRole('button', { name: 'Review primary evidence' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Capture primary source' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Review primary evidence' }));
    expect(inspect).toHaveBeenCalledWith('primary-evidence');
  });

  it('runs the configured source check only through the governed BSC and n8n receipt path', async () => {
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overviewWithBrief);
    vi.mocked(runKnowledgeInformationManualIngress).mockResolvedValue({
      project_id: 'project-a', trigger: 'n8n_signed_manual_webhook', run_id: 'run-1', request_id: 'request-1', requested_at: '2026-07-31T00:00:00Z',
      state: 'completed', batch_count: 2, receipt_count: 3, batches: [],
      verification: { state: 'verified', claimed_batch_count: 2, verified_batch_count: 2, pending_batch_ids: [] },
    });
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} />);

    await screen.findByText('GOVERNED INFORMATION');
    fireEvent.click(screen.getByRole('button', { name: 'Run source check' }));

    await waitFor(() => expect(runKnowledgeInformationManualIngress).toHaveBeenCalledWith('project-a'));
    expect(await screen.findByText('Source check completed with 3 BSC receipts across 2 batches.')).toBeVisible();
  });

  it('does not present an unpersisted n8n batch claim as a completed source check', async () => {
    vi.mocked(fetchKnowledgeInformationOverview).mockResolvedValue(overviewWithBrief);
    vi.mocked(runKnowledgeInformationManualIngress).mockResolvedValue({
      project_id: 'project-a', trigger: 'n8n_signed_manual_webhook', run_id: 'run-2', request_id: 'request-2', requested_at: '2026-07-31T00:00:00Z',
      state: 'receipt_verification_pending', batch_count: 0, receipt_count: 0, batches: [],
      verification: { state: 'pending', claimed_batch_count: 1, verified_batch_count: 0, pending_batch_ids: ['unverified-batch'] },
    } as never);
    render(<InformationOperationsPanel projectId="project-a" canWrite refreshToken={0} />);

    await screen.findByText('GOVERNED INFORMATION');
    fireEvent.click(screen.getByRole('button', { name: 'Run source check' }));

    expect(await screen.findByText('Source check is awaiting BSC receipt verification. No new receipt is counted yet.')).toBeVisible();
    expect(screen.queryByText(/Source check completed with 0 BSC receipt/i)).toBeNull();
  });
});
