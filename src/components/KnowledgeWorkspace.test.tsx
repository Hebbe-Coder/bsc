// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { KnowledgePage, KnowledgeProposal, KnowledgeSource, WeeklyDistillation, WeeklyDistillationDetail } from '../api/knowledgeWorkspaceApi';
import {
  DistillationReader,
  EvidenceRecord,
  KNOWLEDGE_JOB_OPTIONS,
  OBSIDIAN_PLUGIN_PRESETS,
  ProposalReview,
  SourceInspector,
  WikiReader,
} from './KnowledgeWorkspace';
import { describeKnowledgeSource, selectDefaultKnowledgePage } from './knowledgePresentation';

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

const growthDistillation: WeeklyDistillation = {
  id: 'growth-weekly-1', project_id: 'project-a', week: '2026-W30', period: '2026-W30', kind: 'weekly', record_type: 'growth',
  knowledge_path: 'distillations/weekly/2026-W30/summary.md', content_path: 'distillations/weekly/2026-W30/actions.md', context_path: '',
  paths: ['distillations/weekly/2026-W30/summary.md', 'distillations/weekly/2026-W30/actions.md'],
  source_cutoff: '2026-07-24T09:00:00Z', status: 'generated', created_at: '2026-07-24T09:01:00Z',
  generation: { mode: 'llm' }, manifest: {},
};

const growthDistillationDetail: WeeklyDistillationDetail = {
  distillation: growthDistillation,
  documents: {
    'distillations/weekly/2026-W30/summary.md': '# Project-specific summary\n\n[source:source-a] changed the release decision.',
    'distillations/weekly/2026-W30/actions.md': '# Verify\n\nReview [source:source-a] before publication.',
  },
};

describe('KnowledgeWorkspace focused components', () => {
  it('offers the actual daily and weekly growth jobs to the knowledge scheduler', () => {
    expect(KNOWLEDGE_JOB_OPTIONS).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'growth_daily', defaultCron: '0 17 * * *' }),
      expect.objectContaining({ id: 'growth_weekly_distillation', defaultCron: '30 17 * * 5' }),
    ]));
  });

  it('uses installed plugin IDs for filesystem bridges and keeps native Horizon out of the export presets', () => {
    expect(OBSIDIAN_PLUGIN_PRESETS).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'obsidian-clipper', input_paths: ['00_Inbox/web-clipper'] }),
      expect.objectContaining({ id: 'xiaohongshu-importer', input_paths: ['00_Inbox/social'] }),
      expect.objectContaining({ id: 'docxer', input_paths: ['01_Sources/docxer'] }),
      expect.objectContaining({ id: 'obsidian-importer', input_paths: ['01_Sources/importer'] }),
    ]));
    expect(OBSIDIAN_PLUGIN_PRESETS).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'horizon' }),
    ]));
  });

  it('shows an explicit empty reader state', () => {
    render(<WikiReader page={null} pages={[]} busy={false} canWrite={false} onCitation={vi.fn()} onWikiLink={vi.fn()} onRestore={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Choose a published page' })).toBeVisible();
  });

  it('opens a project overview before secondary Wiki pages', () => {
    const pages: KnowledgePage[] = [
      { id: 'index', path: 'wiki/index.md', title: 'Index', page_kind: 'index', version: 1, status: 'published', metadata: {} },
      { id: 'concept', path: 'wiki/concepts/loop.md', title: 'Loop', page_kind: 'concept', version: 1, status: 'published', metadata: {} },
      { id: 'overview', path: 'wiki/overview.md', title: 'Overview', page_kind: 'overview', version: 1, status: 'published', metadata: {} },
    ];

    expect(selectDefaultKnowledgePage(pages)?.id).toBe('overview');
  });

  it('renders a persisted growth bundle with its governed documents', () => {
    render(<DistillationReader records={[growthDistillation]} selected={growthDistillationDetail} onSelect={vi.fn()} />);

    expect(screen.getByRole('heading', { name: '2026-W30' })).toBeVisible();
    expect(screen.getByText('Project-specific summary', { exact: false })).toBeVisible();
    expect(screen.getByText('weekly / generated')).toBeVisible();
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

  it('makes long Horizon evidence scannable while retaining its original origin only for inspection', () => {
    const horizonSource: KnowledgeSource = {
      ...source,
      source_type: 'horizon_signal',
      origin: 'https://news.example.com/rss/articles/a-very-long-opaque-article-reference-that-is-not-a-useful-working-title',
      metadata: {
        ai_summary: 'A concise research signal about a multimodal robotics model and its operational implications.',
        ai_score: 0.92,
        horizon_metadata: { source_name: 'Example News' },
      },
    };
    const presentation = describeKnowledgeSource(horizonSource);

    expect(presentation.headline).toContain('multimodal robotics model');
    expect(presentation.provenance).toContain('Example News / Horizon radar');
    expect(presentation.score).toBe('92/100');
    expect(describeKnowledgeSource({ ...horizonSource, metadata: { ...horizonSource.metadata, ai_score: 7 } }).score).toBe('7/10');

    render(<EvidenceRecord source={horizonSource} selected={false} onSelect={vi.fn()} />);
    expect(screen.getByText('92/100')).toBeVisible();
    expect(screen.getByText('Example News / Horizon radar', { exact: false })).toBeVisible();
    expect(screen.queryByText(horizonSource.origin)).toBeNull();
  });
});
