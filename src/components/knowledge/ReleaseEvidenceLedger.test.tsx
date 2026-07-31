// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  fetchKnowledgeReleaseEvidence: vi.fn(),
  submitKnowledgeReleaseEvidence: vi.fn(),
  verifyKnowledgeReleaseEvidence: vi.fn(),
}));

vi.mock('../../api/knowledgeWorkspaceApi', () => api);

import { ReleaseEvidenceLedger } from './ReleaseEvidenceLedger';

const pendingEvidence = {
  evidence_id: 'o1_secure_boundary_restart',
  state: 'pending' as const,
  proof_class: 'none' as const,
  observed_at: '',
  durable_ids: [],
  detail_code: 'awaiting_observation',
  revision: 1,
  recorded_by: 'project_admin',
};

describe('ReleaseEvidenceLedger', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    api.fetchKnowledgeReleaseEvidence.mockResolvedValue({ evidence: [pendingEvidence], count: 1 });
    api.submitKnowledgeReleaseEvidence.mockResolvedValue({ evidence: { ...pendingEvidence, revision: 2 } });
    api.verifyKnowledgeReleaseEvidence.mockResolvedValue({
      evidence: {
        ...pendingEvidence,
        state: 'verified',
        proof_class: 'real',
        observed_at: '2026-08-01T00:00:00+00:00',
        durable_ids: ['run:restart-1'],
        revision: 2,
        recorded_by: 'admin',
      },
    });
  });

  it('keeps evidence metadata-only and read-only for project readers', async () => {
    render(<ReleaseEvidenceLedger projectId="project-a" role="project_reader" canWrite={false} onChanged={vi.fn()} />);

    expect(await screen.findByText('o1_secure_boundary_restart')).toBeVisible();
    expect(screen.getByText('awaiting_observation')).toBeVisible();
    expect(screen.queryByRole('button', { name: /record observation/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /verify real proof/i })).toBeNull();
    expect(document.body.textContent).not.toContain('raw_content');
    expect(document.body.textContent).not.toContain('source_url');
  });

  it('allows a project admin to record a non-verified observation without an approval control', async () => {
    const onChanged = vi.fn();
    render(<ReleaseEvidenceLedger projectId="project-a" role="project_admin" canWrite onChanged={onChanged} />);

    await screen.findByText('o1_secure_boundary_restart');
    fireEvent.change(screen.getByLabelText('Evidence category'), { target: { value: 'o2_metadata_views' } });
    fireEvent.change(screen.getByLabelText('Observation status'), { target: { value: 'unavailable' } });
    fireEvent.change(screen.getByLabelText('Detail code'), { target: { value: 'plugin_not_running' } });
    fireEvent.click(screen.getByRole('button', { name: /record observation/i }));

    await waitFor(() => expect(api.submitKnowledgeReleaseEvidence).toHaveBeenCalledWith('project-a', {
      evidence_id: 'o2_metadata_views',
      state: 'unavailable',
      proof_class: 'none',
      observed_at: '',
      durable_ids: [],
      detail_code: 'plugin_not_running',
    }));
    expect(screen.queryByRole('button', { name: /verify real proof/i })).toBeNull();
  });

  it('requires explicit durable metadata before an administrator can submit a review', async () => {
    render(<ReleaseEvidenceLedger projectId="project-a" role="admin" canWrite onChanged={vi.fn()} />);

    await screen.findByText('o1_secure_boundary_restart');
    const verify = screen.getByRole('button', { name: /verify real proof/i });
    expect(verify).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Observed at'), { target: { value: '2026-08-01T00:00:00+00:00' } });
    fireEvent.change(screen.getByLabelText('Durable evidence IDs'), { target: { value: 'run:restart-1' } });
    fireEvent.change(screen.getByLabelText('Review detail code'), { target: { value: 'restart_verified' } });
    expect(verify).toBeEnabled();
    fireEvent.click(verify);

    await waitFor(() => expect(api.verifyKnowledgeReleaseEvidence).toHaveBeenCalledWith('project-a', 'o1_secure_boundary_restart', {
      evidence_id: 'o1_secure_boundary_restart',
      state: 'verified',
      proof_class: 'real',
      observed_at: '2026-08-01T00:00:00+00:00',
      durable_ids: ['run:restart-1'],
      detail_code: 'restart_verified',
    }));
  });
});
