// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { KnowledgeProposal, KnowledgeSource } from '../api/knowledgeWorkspaceApi';
import { KNOWLEDGE_JOB_OPTIONS, ProposalReview, SourceInspector, WikiReader } from './KnowledgeWorkspace';

const proposal: KnowledgeProposal = {
  id: 'proposal-a',
  status: 'draft',
  rationale: 'Review a governed change',
  source_ids: ['source-a'],
  operations: [{
    id: 'operation-a', operation: 'create', path: 'wiki/concepts/a.md', content: '# A', source_ids: ['source-a'],
  }],
  eval_summary: {},
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T00:00:00Z',
};

const source: KnowledgeSource = {
  id: 'source-a',
  project_id: 'project-a',
  source_type: 'obsidian_markdown',
  origin: 'brief.md',
  vault_path: 'inbox/brief.md',
  content_hash: 'a'.repeat(64),
  trust_level: 'reviewed',
  status: 'validated',
  metadata: { obsidian_plugin: 'readwise', plugin_name: 'Readwise Export' },
  supersedes_id: null,
  captured_at: '2026-07-22T00:00:00Z',
};

describe('KnowledgeWorkspace focused components', () => {
  it('offers the actual daily and weekly growth jobs to the knowledge scheduler', () => {
    expect(KNOWLEDGE_JOB_OPTIONS).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'growth_daily', defaultCron: '0 17 * * *' }),
      expect.objectContaining({ id: 'growth_weekly_distillation', defaultCron: '30 17 * * 5' }),
    ]));
  });

  it('shows an explicit empty reader state', () => {
    render(<WikiReader page={null} pages={[]} busy={false} canWrite={false} onCitation={vi.fn()} onWikiLink={vi.fn()} onRestore={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Choose a published page' })).toBeVisible();
  });

  it('keeps proposal controls visible but disabled for a reader', () => {
    const publish = vi.fn();
    const { rerender } = render(<ProposalReview proposal={proposal} baselines={{}} busy={false} canWrite={false} onLint={vi.fn()} onPublish={publish} onReject={vi.fn()} />);

    expect(screen.getByRole('button', { name: /publish/i })).toBeDisabled();
    rerender(<ProposalReview proposal={proposal} baselines={{}} busy={false} canWrite onLint={vi.fn()} onPublish={publish} onReject={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));
    expect(publish).toHaveBeenCalledWith(proposal);
  });

  it('saves a project-specific evaluation baseline instead of assuming a template', () => {
    const saveBaseline = vi.fn();
    render(<ProposalReview proposal={proposal} baselines={{}} busy={false} canWrite onLint={vi.fn()} onPublish={vi.fn()} onReject={vi.fn()} onSaveEvaluationCase={saveBaseline} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'Required project constraints' }), { target: { value: 'named owner\nreview window' } });
    fireEvent.click(screen.getByRole('button', { name: /save evaluation baseline/i }));

    expect(saveBaseline).toHaveBeenCalledWith(proposal, expect.objectContaining({
      case_type: 'content', expected: { constraints: ['named owner', 'review window'], require_citations: true },
    }));
  });

  it('never renders an evidence editor and disables curation for a reader', () => {
    const { container } = render(<SourceInspector source={source} busy={false} canWrite={false} onApprove={vi.fn()} />);

    expect(container.querySelector('input, textarea')).toBeNull();
    expect(screen.getByRole('button', { name: /approve for synthesis/i })).toBeDisabled();
    expect(screen.getByText(source.content_hash)).toBeVisible();
    expect(screen.getByText('Readwise Export')).toBeVisible();
  });
});
