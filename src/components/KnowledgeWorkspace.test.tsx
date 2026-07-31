// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { KnowledgeGraphEdge, KnowledgeGraphNode, KnowledgePage, KnowledgeProposal, KnowledgeSource, WeeklyDistillation, WeeklyDistillationDetail } from '../api/knowledgeWorkspaceApi';
import {
  DistillationReader,
  EvidenceRecord,
  KNOWLEDGE_JOB_OPTIONS,
  OBSIDIAN_PLUGIN_PRESETS,
  describeLocalRestConnection,
  projectOptions,
  ProposalReview,
  selectKnowledgeGraphFocus,
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
  it('keeps the current project selectable until authorized project discovery returns', () => {
    expect(projectOptions('default', [])).toEqual([{ id: 'default', name: 'default', created_at: '' }]);
    expect(projectOptions('default', [{ id: 'intel', name: 'RSS intelligence', created_at: '2026-07-29T00:00:00Z' }])).toEqual([
      { id: 'intel', name: 'RSS intelligence', created_at: '2026-07-29T00:00:00Z' },
      { id: 'default', name: 'default', created_at: '' },
    ]);
  });

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
      expect.objectContaining({ id: 'codex-agent', adapter: 'filesystem_output', input_paths: ['04_Outputs/codex'] }),
      expect.objectContaining({ id: 'copilot-agent', adapter: 'filesystem_output', input_paths: ['04_Outputs/copilot'] }),
    ]));
    expect(OBSIDIAN_PLUGIN_PRESETS).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'horizon' }),
      expect.objectContaining({ id: 'realclaudian' }),
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
    const setHistory = vi.fn();
    render(<DistillationReader records={[growthDistillation]} selected={growthDistillationDetail} onSelect={vi.fn()} includeHistory onIncludeHistoryChange={setHistory} />);

    expect(screen.getByRole('heading', { name: '2026-W30' })).toBeVisible();
    expect(screen.getByText('Project-specific summary', { exact: false })).toBeVisible();
    expect(screen.getByText('weekly / generated')).toBeVisible();
    expect(screen.getByRole('checkbox', { name: 'Revision history' })).toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Revision history' }));
    expect(setHistory).toHaveBeenCalledWith(false);
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

  it('explains the optional Local REST connector without treating it as a source bridge', () => {
    expect(describeLocalRestConnection(undefined)).toMatch(/not configured/i);
    expect(describeLocalRestConnection({
      state: 'connected', detail_code: 'authenticated_manifest_verified', transport: 'loopback_tls', plugin_id: 'obsidian-local-rest-api', plugin_version: '5.0.2',
    })).toBe('Authenticated obsidian-local-rest-api 5.0.2 via loopback_tls');
    expect(describeLocalRestConnection({
      state: 'authentication_failed', detail_code: 'authorization_rejected', transport: 'loopback_tls', plugin_id: 'obsidian-local-rest-api', plugin_version: '',
    })).toMatch(/rejected/i);
  });

  it('keeps a compact graph focused on the most connected reviewable records', () => {
    const nodes: KnowledgeGraphNode[] = [
      { id: 'source-high', node_type: 'source', label: 'High-signal source', status: 'validated', created_at: '' },
      { id: 'page-linked', node_type: 'page', label: 'Linked Wiki page', status: 'published', created_at: '' },
      { id: 'source-support', node_type: 'source', label: 'Supporting source', status: 'validated', created_at: '' },
      { id: 'proposal-linked', node_type: 'proposal', label: 'Review proposal', status: 'draft', created_at: '' },
      { id: 'isolated', node_type: 'source', label: 'Isolated record', status: 'captured', created_at: '' },
    ];
    const edges: KnowledgeGraphEdge[] = [
      { id: 'edge-page', from_id: 'source-high', to_id: 'page-linked', edge_type: 'supports', created_at: '' },
      { id: 'edge-support', from_id: 'source-high', to_id: 'source-support', edge_type: 'corroborates', created_at: '' },
      { id: 'edge-proposal', from_id: 'source-high', to_id: 'proposal-linked', edge_type: 'informs', created_at: '' },
    ];

    const focus = selectKnowledgeGraphFocus(nodes, edges, 2);

    expect(focus.nodes.map((node) => node.id)).toEqual(['source-high', 'page-linked']);
    expect(focus.edges.map((edge) => edge.id)).toEqual(['edge-page']);
    expect(focus.nodes.map((node) => node.id)).not.toContain('isolated');
  });

  it('shows a semantic project-fit recommendation without replacing explicit approval', () => {
    const analyze = vi.fn();
    const approve = vi.fn();
    const { container } = render(<SourceInspector source={source} busy={false} canWrite triage={{
      id: 'triage-a', project_id: 'project-a', source_id: source.id, profile_revision: 1,
      relevance: 92, value: 86, freshness: 75, outputability: 88, connectedness: 84,
      priority: 86, reliability_pass: true, disposition: 'knowledge_candidate',
      reasons: ['The source addresses this project\'s AI-agent workflow scope.', 'prompt_run=prompt_semantic_triage'],
      evaluator_revision: 'semantic-source-triage-v1', evaluator_status: 'completed', latency_ms: 123,
      created_at: '2026-07-27T00:00:00Z',
    }} onApprove={approve} onAnalyze={analyze} />);
    const inspector = within(container.querySelector('.source-inspector') as HTMLElement);

    expect(inspector.getByText('Project fit review')).toBeVisible();
    expect(inspector.getByText('knowledge_candidate / priority 86')).toBeVisible();
    fireEvent.click(inspector.getByRole('button', { name: /analyze semantic fit/i }));
    expect(analyze).toHaveBeenCalledWith(source);
    fireEvent.click(inspector.getByRole('button', { name: /approve for synthesis/i }));
    expect(approve).toHaveBeenCalledWith(source);
  });

  it('gives a Horizon signal an explicit primary-capture action without treating the signal as primary evidence', () => {
    const capture = vi.fn();
    const horizonSource: KnowledgeSource = {
      ...source,
      id: 'horizon-signal-1',
      source_type: 'horizon_signal',
      origin: 'https://publisher.example/article',
      metadata: { evidence_role: 'discovery_signal', ai_summary: 'A discovery that needs an independent source capture.' },
    };
    render(<SourceInspector source={horizonSource} busy={false} canWrite onApprove={vi.fn()} onCapturePrimary={capture} />);

    const button = screen.getByRole('button', { name: /capture primary source/i });
    expect(button).toBeVisible();
    fireEvent.click(button);
    expect(capture).toHaveBeenCalledWith(horizonSource);
    expect(screen.getByText(/does not promote the radar signal/i)).toBeVisible();
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
