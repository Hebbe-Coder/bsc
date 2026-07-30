// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createKnowledgeInformationSource, fetchKnowledgeInformationOverview } from '../../api/knowledgeWorkspaceApi';
import { InformationOperationsPanel } from './InformationOperationsPanel';

vi.mock('../../api/knowledgeWorkspaceApi', () => ({
  createKnowledgeInformationSource: vi.fn(),
  fetchKnowledgeInformationOverview: vi.fn(),
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
});
