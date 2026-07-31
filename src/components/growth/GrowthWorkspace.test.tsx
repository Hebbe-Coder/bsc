// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  addGrowthOutputFeedback,
  distillGrowthSourceMethods,
  evaluateGrowthOutput,
  GrowthRequestError,
  fetchGrowthAccess,
  fetchGrowthAssetDetail,
  fetchGrowthCaptureAttempts,
  fetchGrowthFailures,
  fetchGrowthHealth,
  fetchLatestGrowthDistillation,
  fetchGrowthLineage,
  fetchGrowthOverview,
  fetchGrowthRuns,
  fetchGrowthRunEvents,
  fetchGrowthStage,
  fetchGrowthTrend,
  fileGrowthOutput,
  generateProjectSop,
  linkGrowthOutputEvidence,
  runGrowthWorkspaceJob,
  resolveGrowthFailure,
  setGrowthAccessKey,
  startGrowthRun,
  updateGrowthProfile,
} from '../../api/growthApi';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore } from '../../store/knowledgeWorkspaceStore';
import { GrowthWorkspace } from './GrowthWorkspace';

vi.mock('../../api/growthApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/growthApi')>();
  return {
    ...actual,
    fetchGrowthAccess: vi.fn(),
    fetchGrowthAssetDetail: vi.fn(),
    fetchGrowthCaptureAttempts: vi.fn(),
    fetchGrowthFailures: vi.fn(),
    fetchGrowthHealth: vi.fn(),
    fetchLatestGrowthDistillation: vi.fn(),
    fetchGrowthLineage: vi.fn(),
    fetchGrowthOverview: vi.fn(),
    fetchGrowthRuns: vi.fn(),
    fetchGrowthRunEvents: vi.fn(),
    fetchGrowthStage: vi.fn(),
    fetchGrowthTrend: vi.fn(),
    addGrowthOutputFeedback: vi.fn(),
    distillGrowthSourceMethods: vi.fn(),
    evaluateGrowthOutput: vi.fn(),
    fileGrowthOutput: vi.fn(),
    generateProjectSop: vi.fn(),
    linkGrowthOutputEvidence: vi.fn(),
    processGrowthFeedback: vi.fn(),
    runGrowthWorkspaceJob: vi.fn(),
    resolveGrowthFailure: vi.fn(),
    setGrowthAccessKey: vi.fn(),
    startGrowthRun: vi.fn(),
    triageGrowthSource: vi.fn(),
    updateGrowthProfile: vi.fn(),
  };
});

const mockedOverview = vi.mocked(fetchGrowthOverview);
const mockedAccess = vi.mocked(fetchGrowthAccess);
const mockedStage = vi.mocked(fetchGrowthStage);
const mockedDetail = vi.mocked(fetchGrowthAssetDetail);
const mockedCaptureAttempts = vi.mocked(fetchGrowthCaptureAttempts);
const mockedHealth = vi.mocked(fetchGrowthHealth);
const mockedLatestDistillation = vi.mocked(fetchLatestGrowthDistillation);
const mockedTrend = vi.mocked(fetchGrowthTrend);
const mockedLineage = vi.mocked(fetchGrowthLineage);
const mockedRuns = vi.mocked(fetchGrowthRuns);
const mockedRunEvents = vi.mocked(fetchGrowthRunEvents);
const mockedFailures = vi.mocked(fetchGrowthFailures);
const mockedAddFeedback = vi.mocked(addGrowthOutputFeedback);
const mockedDistillSourceMethods = vi.mocked(distillGrowthSourceMethods);
const mockedEvaluateOutput = vi.mocked(evaluateGrowthOutput);
const mockedFileOutput = vi.mocked(fileGrowthOutput);
const mockedGenerateProjectSop = vi.mocked(generateProjectSop);
const mockedLinkEvidence = vi.mocked(linkGrowthOutputEvidence);
const mockedWorkspaceJob = vi.mocked(runGrowthWorkspaceJob);
const mockedResolveFailure = vi.mocked(resolveGrowthFailure);
const mockedSetGrowthAccessKey = vi.mocked(setGrowthAccessKey);
const mockedStartGrowthRun = vi.mocked(startGrowthRun);
const mockedUpdateGrowthProfile = vi.mocked(updateGrowthProfile);

const overview = {
  profile: { project_id: 'default', user_role: 'researcher', revision: 3 },
  summary: { project_id: 'default', counts: { sources: 25, eligible_sources: 20, pages: 1, methods: 1, published_methods: 1, outputs: 1, accepted_outputs: 1, rejected_outputs: 0, feedback: 1, wiki_proposals: 1, review_records: 2 } },
};
const source = { id: 'source-a', origin: 'Source brief', status: 'eligible', created_at: '2026-07-20T09:00:00Z', content_hash: 'a'.repeat(64), metadata: { evidence_role: 'project_prd' } };
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
  mockedLatestDistillation.mockResolvedValue(null);
  mockedTrend.mockResolvedValue({ source_throughput: [{ date: '2026-07-20', count: 2 }], proposal_outcomes: [], evaluations: [], current: {} as never });
  mockedLineage.mockResolvedValue({ project_id: 'default', edges: [], limit: 200, truncated: false });
  mockedRuns.mockResolvedValue([]);
  mockedRunEvents.mockResolvedValue({ run: { id: 'growth-run-a', status: 'completed' }, events: [] });
  mockedCaptureAttempts.mockResolvedValue([]);
  mockedFailures.mockResolvedValue([]);
  mockedAddFeedback.mockResolvedValue({ id: 'feedback-new', status: 'pending' });
  mockedDistillSourceMethods.mockResolvedValue({ run: { id: 'method-distillation-run', run_type: 'source_method_distillation', status: 'queued' }, proposals: [], publication_status: 'proposal_only', execution: { execution: 'in_process', task_id: 'in-process:method-distillation-run' } });
  mockedEvaluateOutput.mockResolvedValue({ id: 'evaluation-new', quality: 90, status: 'completed' });
  mockedFileOutput.mockResolvedValue({ id: 'output-a', status: 'filed' });
  mockedGenerateProjectSop.mockResolvedValue({ run: { id: 'sop-run-a', run_type: 'prd_to_sop', status: 'completed' }, output: { id: 'sop-output-a', status: 'registered', asset_type: 'output' }, idempotent: false });
  mockedLinkEvidence.mockResolvedValue({ output: { id: 'output-a', status: 'registered', source_refs: [] }, evidence: { source_ids: ['source-a'], page_ids: [] } });
  mockedWorkspaceJob.mockResolvedValue({ run_id: 'workspace-run-a', status: 'queued' });
  mockedResolveFailure.mockResolvedValue({ id: 'failure-a', code: 'routing_mismatch', severity: 'error', summary: 'routing failed', status: 'resolved' });
  mockedStartGrowthRun.mockResolvedValue({ id: 'growth-run-a', run_id: 'growth-run-a', run_type: 'growth_daily', status: 'queued' });
  mockedUpdateGrowthProfile.mockResolvedValue({ ...overview.profile, revision: 4, research_domains: ['agent systems'] });
}

beforeEach(() => {
  vi.clearAllMocks();
  useGrowthWorkspaceStore.getState().reset();
  useKnowledgeWorkspaceStore.getState().setProjectId('default');
  installSuccessfulProject();
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })) });
});

afterEach(() => cleanup());

describe('GrowthWorkspace', () => {
  it('submits an admitted source to a detached review-only method run and opens its ledger', async () => {
    mockedRuns.mockResolvedValue([{ id: 'method-distillation-run', run_type: 'source_method_distillation', status: 'queued' }]);
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));
    const distill = await screen.findByRole('button', { name: 'Distill source into methods' });
    expect(distill).toBeEnabled();
    fireEvent.click(distill);

    await waitFor(() => expect(mockedDistillSourceMethods).toHaveBeenCalledWith('default', 'source-a'));
    expect(await screen.findByText('RUN LEDGER')).toBeVisible();
    await waitFor(() => expect(mockedRunEvents).toHaveBeenCalledWith('default', 'method-distillation-run', expect.anything()));
  });

  it('does not allow a read-only project role to distill a source', async () => {
    mockedAccess.mockResolvedValue({ role: 'project_reader', can_write: false, features: { wiki: true } });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));
    expect(await screen.findByRole('button', { name: 'Distill source into methods' })).toBeDisabled();
    expect(mockedDistillSourceMethods).not.toHaveBeenCalled();
  });

  it('uses an accepted Cangjie candidate as the audited selection for a method draft', async () => {
    const candidate = {
      id: 'candidate-a', asset_type: 'candidate', status: 'accepted', source_id: 'source-a',
      candidate_type: 'framework', title: 'Evidence comparison selection', claim: 'Compare independent evidence before changing a decision path.',
    };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'review' ? [candidate] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'review'
      ? { kind: 'candidate', record: { ...candidate, evidence: [{ source_id: 'source-a', anchor: 'paragraph-1', quote: 'Compare independent evidence before changing a decision path.' }] }, detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Review/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Evidence comparison selection/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Draft method from accepted candidate' }));

    await waitFor(() => expect(mockedDistillSourceMethods).toHaveBeenCalledWith('default', 'source-a', ['candidate-a']));
    expect(await screen.findByText('RUN LEDGER')).toBeVisible();
  });

  it('shows persisted semantic distillation provenance instead of inferring it from run status', async () => {
    mockedLatestDistillation.mockResolvedValue({
      id: 'weekly-a',
      project_id: 'default',
      kind: 'weekly',
      period: '2026-W30',
      status: 'generated',
      paths: ['distillations/weekly/summary.md'],
      generation: {
        mode: 'llm',
        provider: 'deepseek',
        model: 'deepseek-v4-pro',
        llm_documents: ['summary.md', 'actions.md'],
        fallback_documents: [],
      },
    });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    expect(await screen.findByText('LATEST DISTILLATION')).toBeVisible();
    expect(screen.getByText('LLM / deepseek-v4-pro')).toBeVisible();
    expect(screen.getByText('weekly 2026-W30 / 2 LLM documents')).toBeVisible();
  });

  it('renders the persisted model execution tied to the selected growth run', async () => {
    useGrowthWorkspaceStore.getState().setCenterView('runs');
    mockedRuns.mockResolvedValue([{ id: 'growth-run-a', run_type: 'growth_daily', status: 'completed' }]);
    mockedRunEvents.mockResolvedValue({
      run: { id: 'growth-run-a', status: 'completed' },
      events: [{
        id: 'event-model-a',
        run_id: 'growth-run-a',
        sequence: 2,
        event_type: 'knowledge.growth.model.completed',
        payload: {
          prompt_run_id: 'prompt-run-a',
          agent_manifest_fingerprint: 'a'.repeat(64),
          task: 'knowledge_distillation',
          revision: 'growth-distillation-v9',
          provider: 'deepseek',
          model: 'deepseek-v4-pro',
          usage: { provider_calls: 2, reported_calls: 2, complete: true, total_tokens: 123, reasoning_tokens: 40, latency_ms: 900 },
          attempt_count: 2,
          retry_count: 1,
          retry_categories: ['server_error'],
        },
      }],
    });

    render(<GrowthWorkspace onClose={vi.fn()} />);

    expect(await screen.findByText('Model execution')).toBeVisible();
    expect(screen.getByText('deepseek / deepseek-v4-pro')).toBeVisible();
    expect(screen.getByText('123 total tokens')).toBeVisible();
    expect(screen.getByText(/1 retry attempt: server error/)).toBeVisible();
    expect(screen.getByText('run prompt-run-a')).toBeVisible();
  });

  it('shows the connected Vault, plugin, Horizon and scheduler contract and can run a declared sync', async () => {
    mockedAccess.mockResolvedValue({
      role: 'project_admin',
      can_write: true,
      features: { wiki: true, obsidian_sync: true, horizon: true },
      vault: { configured: true, status: 'ready', connection: { state: 'ready' } },
      plugins: { plugins: [{ id: 'obsidian-clipper', status: 'captured', path_status: 'ready', captured_sources: 1, registered_outputs: 0 }] },
      horizon: { enabled: true, captured_sources: 2, artifact_store: { configured: true, available: true, mode: 'host_fallback' } },
      scheduler: { available: false, mode: 'manual' },
      growth: { status: 'completed' },
    });
    render(<GrowthWorkspace onClose={vi.fn()} runtimeAccessKey="session-key" />);

    expect(await screen.findByText('VAULT')).toBeInTheDocument();
    expect(screen.getByText('ready / host_fallback')).toBeInTheDocument();
    expect(screen.getByText('manual only')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Sync Obsidian evidence'));
    await waitFor(() => expect(mockedWorkspaceJob).toHaveBeenCalledWith('default', 'source_sync'));
  });

  it('shows a retryable Horizon channel failure instead of treating it as an empty result', async () => {
    mockedAccess.mockResolvedValue({
      role: 'project_admin',
      can_write: true,
      features: { wiki: true, obsidian_sync: true, horizon: true },
      horizon: {
        enabled: true,
        captured_sources: 2,
        artifact_store: { configured: true, available: true, mode: 'host_fallback' },
        last_run: {
          status: 'failed',
          accepted: 0,
          created: 0,
          duplicates: 0,
          skipped: false,
          outcome: 'channel_error',
          items_observed: 0,
          failure: { category: 'transient_dependency', code: 'horizon_unavailable', retryable: true },
        },
      },
    });
    render(<GrowthWorkspace onClose={vi.fn()} runtimeAccessKey="session-key" />);

    expect(await screen.findByText('channel unavailable')).toBeVisible();
    expect(screen.getByText('horizon_unavailable / retryable')).toBeVisible();
    expect(screen.getByLabelText('Import Horizon evidence')).toBeEnabled();
  });

  it('uses the shared Studio session and project boundary', async () => {
    useKnowledgeWorkspaceStore.getState().setProjectId('project-shared');
    render(<GrowthWorkspace onClose={vi.fn()} runtimeAccessKey="session-key" />);

    await waitFor(() => expect(mockedSetGrowthAccessKey).toHaveBeenCalledWith('session-key'));
    await waitFor(() => expect(mockedOverview).toHaveBeenCalledWith('project-shared', expect.any(AbortSignal)));
    expect(screen.queryByRole('textbox', { name: 'Growth access key' })).not.toBeInTheDocument();
    expect(screen.getByText('Studio session applied')).toBeVisible();

    fireEvent.change(screen.getByRole('textbox', { name: 'Growth project ID' }), { target: { value: 'project-next' } });
    fireEvent.click(screen.getByRole('button', { name: /Load/i }));
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('project-next'));
  });

  it('labels accepted and filed totals as verified D-layer outputs', async () => {
    mockedOverview.mockResolvedValue({
      ...overview,
      summary: { ...overview.summary, counts: { ...overview.summary.counts, outputs: 2, accepted_outputs: 2 } },
    });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    expect(await screen.findByText('VERIFIED D')).toBeVisible();
    expect(screen.queryByText('ACCEPTED D')).not.toBeInTheDocument();
  });

  it('persists a revisioned project profile and reloads the governed workspace state', async () => {
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByLabelText('Configure project profile'));
    fireEvent.change(screen.getByLabelText('Research domains'), { target: { value: 'agent systems\nknowledge operations' } });
    fireEvent.change(screen.getByLabelText('Primary outputs'), { target: { value: 'research brief\noperational decision' } });
    fireEvent.change(screen.getByLabelText('Primary source origins'), { target: { value: 'https://research.example/\nhttps://papers.example/' } });
    fireEvent.change(screen.getByLabelText('Community retention days'), { target: { value: '45' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    await waitFor(() => expect(mockedUpdateGrowthProfile).toHaveBeenCalledWith('default', expect.objectContaining({
      expected_revision: 3,
      research_domains: ['agent systems', 'knowledge operations'],
      primary_output_types: ['research brief', 'operational decision'],
      source_policy: expect.objectContaining({
        primary_origin_prefixes: ['https://research.example/', 'https://papers.example/'],
        community_retention_days: 45,
      }),
    })));
    expect(await screen.findByText(/Saved revision 4/)).toBeVisible();
    await waitFor(() => expect(mockedOverview.mock.calls.length).toBeGreaterThan(1));
  });

  it('starts a real daily growth run and reflects its durable status in the workspace', async () => {
    mockedRuns.mockResolvedValue([{ id: 'growth-run-a', run_type: 'growth_daily', status: 'queued' }]);
    render(<GrowthWorkspace onClose={vi.fn()} />);

    const runButton = await screen.findByRole('button', { name: 'Run daily growth cycle' });
    await waitFor(() => expect(runButton).toBeEnabled());
    fireEvent.click(runButton);

    await waitFor(() => expect(mockedStartGrowthRun).toHaveBeenCalledWith('default', 'growth_daily'));
    expect(await screen.findByText(/growth_daily: queued/i)).toBeVisible();
  });

  it('generates a reviewable SOP only from an admitted project PRD and opens the registered output', async () => {
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Outputs/i }));
    const prd = await screen.findByRole('combobox', { name: 'Admitted project PRD' });
    expect(prd).toHaveValue('source-a');
    fireEvent.change(screen.getByRole('textbox', { name: 'SOP delivery goal' }), { target: { value: 'Create the governed delivery SOP for the active project.' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'SOP audience' }), { target: { value: 'Project operators' } });
    fireEvent.click(screen.getByRole('button', { name: 'Generate reviewable SOP' }));

    await waitFor(() => expect(mockedGenerateProjectSop).toHaveBeenCalledWith('default', expect.objectContaining({
      prd_source_id: 'source-a',
      goal: 'Create the governed delivery SOP for the active project.',
      audience: 'Project operators',
      channel: 'knowledge_workspace',
      idempotency_key: expect.stringMatching(/^browser-prd-to-sop-/),
    })));
    expect(await screen.findByText(/New registered SOP is open/i)).toBeVisible();
    expect(useGrowthWorkspaceStore.getState().selectedId).toBe('sop-output-a');
  });

  it('audits persisted run inputs, events, output references and linked failures in one workspace view', async () => {
    mockedRuns.mockResolvedValue([{
      id: 'growth-run-a', run_type: 'growth_daily', status: 'failed', created_at: '2026-07-25T08:00:00Z',
      input_refs: { source_ids: ['source-a'], task: 'Build the weekly research brief' },
      output_refs: { proposal_ids: ['proposal-a'], output_ids: ['output-a'] },
    }]);
    mockedRunEvents.mockResolvedValue({
      run: { id: 'growth-run-a', status: 'failed' },
      events: [{ id: 'event-a', run_id: 'growth-run-a', sequence: 1, event_type: 'knowledge.capture.failed', created_at: '2026-07-25T08:01:00Z', payload: { code: 'timeout' } }],
    });
    mockedFailures.mockResolvedValue([{
      id: 'failure-a', code: 'source_capture_failure', severity: 'error', summary: 'Horizon timed out before capture.', run_id: 'growth-run-a', event_sequence: 1, retryable: true, status: 'open',
    }]);
    vi.stubGlobal('prompt', vi.fn(() => 'Source channel was restored and the retry is recorded.'));
    render(<GrowthWorkspace onClose={vi.fn()} />);

    expect(await screen.findByText(/growth_daily: failed/i)).toBeVisible();
    fireEvent.click(await screen.findByRole('button', { name: 'Runs' }));

    expect(await screen.findByText('Inputs, sources, events, outputs and failure diagnostics')).toBeVisible();
    await waitFor(() => expect(mockedCaptureAttempts).toHaveBeenCalledWith('default', { runId: 'growth-run-a' }, expect.any(AbortSignal)));
    expect(await screen.findByText(/Build the weekly research brief/)).toBeVisible();
    expect(screen.getByText('knowledge.capture.failed')).toBeVisible();
    expect(screen.getByText('Horizon timed out before capture.')).toBeVisible();
    expect(mockedRunEvents).toHaveBeenCalledWith('default', 'growth-run-a', expect.any(AbortSignal));
    expect(mockedCaptureAttempts).toHaveBeenCalledWith('default', { runId: 'growth-run-a' }, expect.any(AbortSignal));
    expect(mockedFailures).toHaveBeenCalledWith('default', { runId: 'growth-run-a' }, expect.any(AbortSignal));

    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));
    await waitFor(() => expect(mockedResolveFailure).toHaveBeenCalledWith('default', 'failure-a', {
      resolution_note: 'Source channel was restored and the retry is recorded.',
    }));
  });

  it('renders the capture outcome and policy projection without exposing raw evidence', async () => {
    mockedRuns.mockResolvedValue([{ id: 'capture-run-a', run_type: 'horizon_capture', status: 'completed' }]);
    mockedRunEvents.mockResolvedValue({ run: { id: 'capture-run-a', status: 'completed' }, events: [] });
    mockedCaptureAttempts.mockResolvedValue([{
      id: 'capture-a', run_id: 'capture-run-a', source_id: 'source-a', source_type: 'horizon_signal',
      origin: 'https://news.example.test/agent-systems', content_hash: 'a'.repeat(64), outcome: 'projection_failed',
      policy: { authority: 'primary', extraction_quality: 'complete' }, projection: { status: 'failed', code: 'index_backend_error' },
      created_at: '2026-07-25T08:01:00Z',
    }]);
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Runs' }));

    expect(await screen.findByText('Source capture ledger')).toBeVisible();
    expect(screen.getByText('projection failed')).toBeVisible();
    expect(screen.getByText(/index_backend_error/)).toBeVisible();
    expect(screen.queryByText(/raw evidence body/i)).not.toBeInTheDocument();
  });

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

  it('uses the lineage projection for readable upstream and downstream inspector links', async () => {
    mockedLineage.mockResolvedValue({
      project_id: 'default',
      edges: [{ id: 'edge-a', from_id: 'source-a', to_id: 'page-a', from_type: 'source', to_type: 'page', edge_type: 'source_supports_page' }],
      nodes: [
        { id: 'source-a', type: 'source', label: 'Robotics research signal', status: 'processed' },
        { id: 'page-a', type: 'page', label: 'Embodied AI overview', status: 'published' },
      ],
      limit: 200,
      truncated: false,
    });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('option', { name: /Source brief/i }));

    expect(await screen.findByText('Embodied AI overview')).toBeVisible();
    expect(screen.getByText('page-a')).toBeVisible();
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

  it('makes a persisted weekly distillation readable from Review without classifying it as a D-layer output', async () => {
    const distillation = { id: 'weekly-a', asset_type: 'distillation', kind: 'weekly', period: '2026-W30', status: 'generated' };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'review' ? [distillation] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'review'
      ? { kind: 'distillation', record: distillation, content: '# summary.md\n\nEvidence-backed weekly decision summary.', detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Review/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Weekly distillation 2026-W30/i }));

    expect(await screen.findByText('Evidence-backed weekly decision summary.')).toBeVisible();
    expect(screen.getAllByText('Feedback, proposals and distillations')).not.toHaveLength(0);
  });

  it('opens an automatically detected method candidate from the review queue', async () => {
    const candidate = { id: 'method-proposal-a', asset_type: 'method_proposal', status: 'candidate', task_family: 'evidence-brief', rationale: 'Three comparable accepted outputs' };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'review' ? [candidate] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'review'
      ? { kind: 'method_proposal', record: { ...candidate, body: '# Evidence brief\nUse verified project evidence.' }, content: '# Evidence brief\nUse verified project evidence.', detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Review/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Three comparable accepted outputs/i }));

    expect(await screen.findByText('Use verified project evidence.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Evaluate method candidate' })).toBeVisible();
  });

  it('shows durable method-evolution experiments in the inspected published method', async () => {
    const method = { id: 'weekly-report-method', asset_type: 'method', status: 'published', name: 'Weekly report', active_revision_id: 'baseline-a' };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'C' ? [method] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'C'
      ? { kind: 'method', record: { ...method, evolution_experiments: [{ id: 'experiment-a', decision: 'retain', mutation_dimension: 'body', baseline_revision_id: 'baseline-a', candidate_proposal_id: 'proposal-a' }] }, content: '# Weekly report', detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Methods/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Weekly report/i }));

    expect(await screen.findByText('Method evolution experiments')).toBeVisible();
    expect(screen.getByText('retain')).toBeVisible();
    expect(screen.getByText('body')).toBeVisible();
  });

  it('shows persisted update holdout evidence and blocks a regressing method from publication', async () => {
    const candidate = {
      id: 'method-update-a', asset_type: 'method_proposal', status: 'approved', operation: 'update',
      task_family: 'weekly-report', rationale: 'Observed method update',
      eval_summary: {
        eligible: true,
        evolution: {
          status: 'failed', protocol_revision: 'method-evolution-v1', passed: false,
          positive_case_count: 3, near_negative_case_count: 2,
          findings: ['candidate regresses one or more baseline holdout cases'],
          holdout: { case_count: 2, candidate_passed: false, baseline_passed: true, regressed_case_ids: ['holdout-1'] },
          mutation: { observed_dimensions: ['trigger_contract'] },
          cost: { status: 'not_metered' },
        },
      },
    };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'review' ? [candidate] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'review'
      ? { kind: 'method_proposal', record: { ...candidate, body: '# Weekly report update' }, content: '# Weekly report update', detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('tab', { name: /Review/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Observed method update/i }));

    expect(await screen.findByText('UPDATE EVALUATION')).toBeVisible();
    expect(screen.getByText('method-evolution-v1')).toBeVisible();
    expect(screen.getByText('holdout-1')).toBeVisible();
    expect(screen.getByText('trigger_contract')).toBeVisible();
    expect(screen.getByText('not_metered')).toBeVisible();
    expect(screen.getByText('candidate regresses one or more baseline holdout cases')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Publish approved method' })).toBeDisabled();
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

  it('links a captured source before allowing a standalone plugin output through quality review', async () => {
    const output = { id: 'plugin-output', title: 'Web Clipper synthesis', status: 'registered', asset_type: 'output', vault_path: 'outputs/2026/plugin-output.md', metadata: { origin: 'external' } };
    mockedStage.mockImplementation(async (_projectId, currentStage, limit) => ({ project_id: 'default', stage: currentStage, records: currentStage === 'D' ? [output] : currentStage === 'A' ? [source] : [], limit, truncated: false }));
    mockedDetail.mockImplementation(async (_projectId, currentStage) => currentStage === 'D'
      ? { kind: 'output', record: output, content: '# Plugin synthesis\nNeeds evidence linkage.', evaluations: [], feedback: [], detailAvailability: 'complete' }
      : { kind: 'source', record: source, detailAvailability: 'metadata_only' });
    render(<GrowthWorkspace onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('tab', { name: /Outputs/i }));
    fireEvent.click(await screen.findByRole('option', { name: /Web Clipper synthesis/i }));

    const evidenceSelect = await screen.findByRole('listbox', { name: 'Registered evidence sources' });
    fireEvent.change(evidenceSelect, { target: { value: 'source-a' } });
    fireEvent.click(screen.getByRole('button', { name: 'Link selected evidence' }));
    await waitFor(() => expect(mockedLinkEvidence).toHaveBeenCalledWith('default', 'plugin-output', { source_ids: ['source-a'], page_ids: [] }));

    mockedDetail.mockResolvedValue({ kind: 'output', record: output, evidence: { source_ids: ['source-a'], page_ids: [] }, content: '# Plugin synthesis\nLinked evidence.', evaluations: [], feedback: [], detailAvailability: 'complete' });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh growth workspace' }));
    await screen.findByRole('slider', { name: 'Groundedness score' });
    for (const label of ['Groundedness', 'Task fit', 'Usefulness', 'Coherence', 'Format quality']) {
      fireEvent.change(screen.getByRole('slider', { name: `${label} score` }), { target: { value: '90' } });
    }
    fireEvent.change(screen.getByRole('textbox', { name: 'Output evaluation findings' }), { target: { value: 'Cites captured source.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate output' }));

    await waitFor(() => expect(mockedEvaluateOutput).toHaveBeenCalledWith('default', 'plugin-output', {
      groundedness: 0.9, task_fit: 0.9, usefulness: 0.9, coherence: 0.9, format_quality: 0.9, findings: ['Cites captured source.'],
    }));
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
