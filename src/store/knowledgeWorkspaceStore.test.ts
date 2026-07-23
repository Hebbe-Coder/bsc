import { beforeEach, describe, expect, it } from 'vitest';

import type { KnowledgeRun, KnowledgeRunEvent } from '../api/knowledgeWorkspaceApi';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore, type KnowledgeSnapshot } from './knowledgeWorkspaceStore';

const run = (overrides: Partial<KnowledgeRun> = {}): KnowledgeRun => ({
  id: 'run-a',
  run_type: 'source_sync',
  trigger: 'manual',
  status: 'running',
  error: '',
  retry_of: null,
  input_refs: {},
  output_refs: {},
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T00:00:00Z',
  ...overrides,
});

const snapshot = (projectId: string): KnowledgeSnapshot => ({
  workspace: {
    project_id: projectId,
    vault: { configured: true, status: 'configured' },
    plugins: { configured: false, supported_adapters: ['filesystem_drop', 'filesystem_output'], plugins: [], errors: [] },
    sources: 0,
    runs: 1,
    schedules: 0,
    access: { role: 'project_admin', can_write: true },
    features: {
      wiki: true,
      obsidian_sync: true,
      schedules: true,
      mcp_write: true,
      horizon: false,
      automatic_publication: false,
    },
    sync: { status: 'not_run', last_run: null },
    scheduler: { available: true, mode: 'celery' },
  },
  sources: [],
  runs: [run()],
  schedules: [],
  graph: { nodes: [], edges: [], count: 0, total: 0, limit: 500, offset: 0, truncated: false },
  proposals: [],
  pages: [],
  distillations: [],
  health: {
    status: 'available',
    citation_coverage: null,
    orphan_page_ids: [],
    stale_page_ids: [],
    uncited_eligible_source_ids: [],
    pending_proposal_ids: [],
    dangling_citation_count: 0,
    stale_citation_count: 0,
    contradiction_count: 0,
    contradiction_pairs: [],
    evaluation: { status: 'unavailable', latest_score: null, runs: 0, reason: 'no baseline' },
  },
  trend: { source_throughput: [], proposal_outcomes: [], evaluations: [], current: {} as never },
});

const event = (sequence: number, overrides: Partial<KnowledgeRunEvent> = {}): KnowledgeRunEvent => ({
  id: `event-${sequence}`,
  project_id: 'project-a',
  run_id: 'run-a',
  sequence,
  event_type: 'knowledge.source.captured',
  payload: {},
  created_at: '2026-07-22T00:00:00Z',
  ...overrides,
});

beforeEach(() => {
  useKnowledgeWorkspaceStore.setState({
    projectId: 'default',
    workspace: null,
    sources: [],
    runs: [],
    schedules: [],
    selectedRun: null,
    runEvents: [],
    requestEpoch: 0,
    loading: false,
    error: '',
  });
});

describe('knowledge workspace state', () => {
  it('rejects a completed response after the selected project changes', () => {
    const state = useKnowledgeWorkspaceStore.getState();
    state.setProjectId('project-a');
    const epoch = useKnowledgeWorkspaceStore.getState().beginLoad('project-a');
    useKnowledgeWorkspaceStore.getState().setProjectId('project-b');

    const accepted = useKnowledgeWorkspaceStore.getState().applyLoad(epoch, 'project-a', snapshot('project-a'));

    expect(accepted).toBe(false);
    expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('project-b');
    expect(useKnowledgeWorkspaceStore.getState().workspace).toBeNull();
  });

  it('deduplicates stale events, rejects cross-project events, and applies terminal truth', () => {
    useKnowledgeWorkspaceStore.setState({ projectId: 'project-a', selectedRun: run(), runs: [run()], runEvents: [] });
    const store = useKnowledgeWorkspaceStore.getState();
    store.appendRunEvents('project-a', 'run-a', [event(1)]);
    useKnowledgeWorkspaceStore.getState().appendRunEvents('project-a', 'run-a', [
      event(1),
      event(2, { project_id: 'project-b' }),
      event(2, { event_type: 'knowledge.run.completed', payload: { status: 'completed' } }),
    ]);

    const current = useKnowledgeWorkspaceStore.getState();
    expect(current.runEvents.map((item) => item.sequence)).toEqual([1, 2]);
    expect(current.selectedRun?.status).toBe('completed');
    expect(current.runs[0].status).toBe('completed');
  });

  it('keeps terminal run identity stable while replaying persisted events', () => {
    const completed = run({ status: 'completed' });
    useKnowledgeWorkspaceStore.setState({
      projectId: 'project-a',
      selectedRun: completed,
      runs: [completed],
      runEvents: [],
    });

    useKnowledgeWorkspaceStore.getState().appendRunEvents('project-a', 'run-a', [
      event(1, { event_type: 'knowledge.run.queued', payload: { status: 'queued' } }),
      event(2, { event_type: 'knowledge.run.completed', payload: { status: 'completed' } }),
    ]);

    const current = useKnowledgeWorkspaceStore.getState();
    expect(current.runEvents.map((item) => item.sequence)).toEqual([1, 2]);
    expect(current.selectedRun).toBe(completed);
    expect(current.runs).toEqual([completed]);
  });

  it('preserves selection while switching mobile panes', () => {
    useKnowledgeWorkspaceStore.setState({ projectId: 'project-a', selectedRun: run() });
    useKnowledgeWorkspaceStore.getState().setMobilePane('inspector');

    expect(useKnowledgeWorkspaceStore.getState().mobilePane).toBe('inspector');
    expect(useKnowledgeWorkspaceStore.getState().selectedRun?.id).toBe('run-a');
  });
});

describe('growth workspace state', () => {
  beforeEach(() => useGrowthWorkspaceStore.getState().reset());

  it('keeps global search while resetting stale selection and pagination on stage change', () => {
    const store = useGrowthWorkspaceStore.getState();
    store.setQuery('evidence');
    store.setPage(3);
    store.setSelectedId('source-a');
    useGrowthWorkspaceStore.getState().setStage('B');

    const current = useGrowthWorkspaceStore.getState();
    expect(current.query).toBe('evidence');
    expect(current.page).toBe(1);
    expect(current.selectedId).toBe('');
    expect(current.inspectorOpen).toBe(false);
  });

  it('clears project-bound state when the project changes', () => {
    useGrowthWorkspaceStore.getState().setSelectedId('output-a');
    useGrowthWorkspaceStore.getState().setRequestState('stage', 'success');
    useGrowthWorkspaceStore.getState().setProjectId('project-b');

    const current = useGrowthWorkspaceStore.getState();
    expect(current.projectId).toBe('project-b');
    expect(current.selectedId).toBe('');
    expect(current.requestStates.stage).toBe('idle');
  });

  it('retains selection when the active stage remains available', () => {
    useGrowthWorkspaceStore.getState().setSelectedId('source-a');
    useGrowthWorkspaceStore.getState().setStage('A');

    expect(useGrowthWorkspaceStore.getState().selectedId).toBe('source-a');
    expect(useGrowthWorkspaceStore.getState().inspectorOpen).toBe(true);
  });
});
