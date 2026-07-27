// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as operationsApi from '../../api/knowledgeOperationsApi';
import { KnowledgeOperationsCockpit } from './KnowledgeOperationsCockpit';

vi.mock('../../api/knowledgeOperationsApi', async () => {
  const actual = await vi.importActual<typeof import('../../api/knowledgeOperationsApi')>('../../api/knowledgeOperationsApi');
  return { ...actual, fetchOperationsPortfolio: vi.fn(), fetchOperationsProject: vi.fn(), fetchOperationsGraph: vi.fn() };
});

const overview = {
  generated_at: '2026-07-27T00:00:00+00:00', state: 'available' as const, coverage: { state: 'available' as const, record_count: 4, reason: '' },
  scope: { tenant_id: 'default', role: 'tenant_admin', project_ids: ['project-a'], selected_project_id: '', mode: 'portfolio' as const }, project_count: 1,
  metrics: {
    assets: { sources: { key: 'sources', state: 'available' as const, value: 2, unit: 'count', record_count: 2, reason: '' }, methods: { key: 'methods', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' }, outputs: { key: 'outputs', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' } },
    quality: { verified: { key: 'verified', state: 'available' as const, value: 2, unit: 'count', record_count: 2, reason: '' }, pending_validation: { key: 'pending_validation', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' }, requires_attention: { key: 'requires_attention', state: 'available' as const, value: 0, unit: 'count', record_count: 0, reason: '' } },
    reuse: { durable_references: { key: 'durable_references', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' } }, agent_evolution: {},
  },
  project_summaries: [{
    project_id: 'project-a', project_name: 'Project A',
    coverage: { state: 'available' as const, record_count: 4, reason: '' },
    freshness: { state: 'available' as const, latest_activity_at: '2026-07-27T00:00:00+00:00', record_count: 4, reason: '' },
    metrics: {
      asset_count: { key: 'asset_count', state: 'available' as const, value: 4, unit: 'count', record_count: 4, reason: '' },
      verified: { key: 'verified', state: 'available' as const, value: 2, unit: 'count', record_count: 2, reason: '' },
      pending_validation: { key: 'pending_validation', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' },
      risk_debt: { key: 'risk_debt', state: 'available' as const, value: 0, unit: 'count', record_count: 0, reason: '' },
      durable_references: { key: 'durable_references', state: 'available' as const, value: 1, unit: 'count', record_count: 1, reason: '' },
    },
    highest_priority_action: null,
  }],
  trends: { asset_growth: [], agent_evolution: [] }, actions: [{ id: 'action-a', project_id: 'project-a', kind: 'unresolved_risk', severity: 'high', source_refs: ['artifact:risk-a'], recommendation: 'Review the unresolved risk.', created_at: '2026-07-27T00:00:00+00:00', drilldown: { surface: 'dbos' as const, entity_id: 'risk-a', mission_id: 'mission-a' } }],
};

const projectOverview = {
  ...overview,
  scope: { ...overview.scope, selected_project_id: 'project-a', mode: 'project' as const },
};

const graph = {
  generated_at: '2026-07-27T00:00:00+00:00', state: 'available' as const,
  coverage: { state: 'available' as const, record_count: 3, reason: '' },
  scope: projectOverview.scope, project_id: 'project-a', mission_id: '',
  lanes: [
    { id: 'risk_constraint', label: 'Risks and constraints', order: 3 },
  ],
  nodes: [
    { id: 'mission-a', domain: 'dbos' as const, type: 'mission', lane: 'mission', label: 'Launch', status: 'active', created_at: '2026-07-27T00:00:00+00:00', confidence: null, drilldown: { surface: 'dbos' as const, entity_id: 'mission-a', mission_id: 'mission-a' } },
    { id: 'risk-a', domain: 'dbos' as const, type: 'risk', lane: 'risk_constraint', label: 'Launch risk', status: 'open', created_at: '2026-07-27T00:01:00+00:00', confidence: 0.4, drilldown: { surface: 'dbos' as const, entity_id: 'risk-a', mission_id: 'mission-a' } },
  ],
  edges: [{ id: 'edge-a', source: 'mission-a', target: 'risk-a', relation: 'artifact_parent', domain: 'dbos' as const, source_ref: 'risk-a' }],
  pagination: { limit: 200, next_cursor: null, truncated: false, omitted_node_count: 0, omitted_endpoint_count: 0 },
  lifecycle_audit: {
    scope: 'filtered_graph' as const,
    risk_node_count: 1,
    complete_risk_lineage_count: 0,
    missing_lanes: ['evidence_source', 'method_sop', 'validation', 'memory_feedback'],
    reason: 'No persisted risk node reaches every required lifecycle lane in this graph.',
  },
};

describe('KnowledgeOperationsCockpit', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

  it('renders server-backed metrics and keeps the action as a real drill-down', async () => {
    const openDbos = vi.fn();
    vi.mocked(operationsApi.fetchOperationsPortfolio).mockResolvedValue(overview);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} onOpenDbos={openDbos} />);
    await waitFor(() => expect(screen.getByText('Verified assets')).toBeTruthy());
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    screen.getByRole('button', { name: /unresolved risk/i }).click();
    expect(openDbos).toHaveBeenCalledWith('project-a', 'mission-a', 'risk-a');
    expect(screen.getByText(/Scope: project-a.*tenant_admin/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Open Project A cockpit/i })).toBeTruthy();
  });

  it('keeps the project decision strip grounded in metrics, actions, and durable coverage', async () => {
    vi.mocked(operationsApi.fetchOperationsProject).mockResolvedValue(projectOverview);
    vi.mocked(operationsApi.fetchOperationsGraph).mockResolvedValue(graph);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} initialProjectId="project-a" />);

    fireEvent.click(screen.getByRole('tab', { name: 'Project' }));
    await waitFor(() => expect(screen.getByLabelText('Decision summary')).toBeTruthy());
    const summary = within(screen.getByLabelText('Decision summary'));
    expect(summary.getByText('Verified assets')).toBeTruthy();
    expect(summary.getByText('Pending validation')).toBeTruthy();
    expect(summary.getByText('Risk debt')).toBeTruthy();
    expect(summary.getByText('Reusable references')).toBeTruthy();
    expect(summary.getByText('Open actions')).toBeTruthy();
    expect(screen.getByText('Coverage 4 durable records')).toBeTruthy();
    expect(screen.getByLabelText('Lifecycle closure audit').textContent).toContain('0/1 risks have a complete durable lifecycle');
    expect(screen.getByLabelText('Lifecycle closure audit').textContent).toContain('Missing: evidence, method or SOP, validation, memory or feedback');
  });

  it('passes a pending proposal ID into the governed Growth review target', async () => {
    const openGrowth = vi.fn();
    vi.mocked(operationsApi.fetchOperationsPortfolio).mockResolvedValue({
      ...overview,
      actions: [{
        id: 'action-proposal-a', project_id: 'project-a', kind: 'pending_proposal', severity: 'medium',
        source_refs: ['method_proposal:proposal-a'], recommendation: 'Review proposal.', created_at: '2026-07-27T00:00:00+00:00',
        drilldown: { surface: 'growth' as const, entity_id: 'proposal-a', mission_id: '' },
      }],
    });
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} onOpenGrowth={openGrowth} />);

    await waitFor(() => expect(screen.getByRole('button', { name: /pending proposal/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /pending proposal/i }));
    expect(openGrowth).toHaveBeenCalledWith('project-a', 'proposal-a');
  });

  it('keeps a DBOS action without a mission inside the exact project graph inspector', async () => {
    const openDbos = vi.fn();
    vi.mocked(operationsApi.fetchOperationsPortfolio).mockResolvedValue({
      ...overview,
      actions: [{
        id: 'action-risk-a', project_id: 'project-a', kind: 'unresolved_risk', severity: 'high',
        source_refs: ['artifact:risk-a'], recommendation: 'Review the risk.', created_at: '2026-07-27T00:00:00+00:00',
        drilldown: { surface: 'dbos' as const, entity_id: 'risk-a', mission_id: '' },
      }],
    });
    vi.mocked(operationsApi.fetchOperationsProject).mockResolvedValue(projectOverview);
    vi.mocked(operationsApi.fetchOperationsGraph).mockResolvedValue(graph);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} onOpenDbos={openDbos} />);

    await waitFor(() => expect(screen.getByRole('button', { name: /unresolved risk/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /unresolved risk/i }));
    await waitFor(() => expect(screen.getByLabelText('Selected lifecycle node').textContent).toContain('Launch risk'));
    expect(openDbos).not.toHaveBeenCalled();
  });

  it('does not chart an agent success rate when every available time bucket is under-sampled', async () => {
    vi.mocked(operationsApi.fetchOperationsPortfolio).mockResolvedValue({
      ...overview,
      trends: {
        ...overview.trends,
        agent_evolution: [{
          date: '2026-07-27',
          verification_pass_rate: null,
          verification_sample_count: 1,
          median_execution_attempt: null,
          execution_sample_count: 1,
          routing_holdout_pass_rate: null,
          routing_sample_count: 1,
        }],
      },
    });
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('No sufficiently sampled verification or holdout results exist for this scope.')).toBeTruthy());
    expect(screen.queryByLabelText('Agent verification and holdout trends')).toBeNull();
  });

  it('reloads the exact DBOS record when an unbound action is selected inside an open project', async () => {
    vi.mocked(operationsApi.fetchOperationsProject).mockResolvedValue({
      ...projectOverview,
      actions: [{
        id: 'action-risk-a', project_id: 'project-a', kind: 'unresolved_risk', severity: 'high',
        source_refs: ['artifact:risk-a'], recommendation: 'Review the risk.', created_at: '2026-07-27T00:00:00+00:00',
        drilldown: { surface: 'dbos' as const, entity_id: 'risk-a', mission_id: '' },
      }],
    });
    vi.mocked(operationsApi.fetchOperationsGraph).mockResolvedValue(graph);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} initialProjectId="project-a" />);

    fireEvent.click(screen.getByRole('tab', { name: 'Project' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /unresolved risk/i })).toBeTruthy());
    const graphCallsBeforeAction = vi.mocked(operationsApi.fetchOperationsGraph).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: /unresolved risk/i }));

    await waitFor(() => expect(vi.mocked(operationsApi.fetchOperationsGraph).mock.calls.length).toBeGreaterThan(graphCallsBeforeAction));
    await waitFor(() => expect(screen.getByLabelText('Selected lifecycle node').textContent).toContain('Launch risk'));
  });

  it('keeps the selected unbound DBOS record inside the project lifecycle inspector', async () => {
    vi.mocked(operationsApi.fetchOperationsProject).mockResolvedValue({
      ...projectOverview,
      actions: [{
        id: 'action-risk-a', project_id: 'project-a', kind: 'unresolved_risk', severity: 'high',
        source_refs: ['artifact:risk-a'], recommendation: 'Review the risk.', created_at: '2026-07-27T00:00:00+00:00',
        drilldown: { surface: 'dbos' as const, entity_id: 'risk-a', mission_id: '' },
      }],
    });
    vi.mocked(operationsApi.fetchOperationsGraph).mockResolvedValue(graph);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} initialProjectId="project-a" />);

    fireEvent.click(screen.getByRole('tab', { name: 'Project' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /unresolved risk/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /unresolved risk/i }));

    await waitFor(() => expect(screen.getByLabelText('Selected lifecycle node').textContent).toContain('Launch risk'));
    expect(screen.getByLabelText('Selected lifecycle node').textContent).toContain('Persisted connections');
  });

  it('sends lifecycle filters to the server and lets users traverse persisted adjacent records', async () => {
    vi.mocked(operationsApi.fetchOperationsProject).mockResolvedValue(projectOverview);
    vi.mocked(operationsApi.fetchOperationsGraph).mockResolvedValue(graph);
    render(<KnowledgeOperationsCockpit onClose={vi.fn()} initialProjectId="project-a" />);

    fireEvent.click(screen.getByRole('tab', { name: 'Project' }));
    await waitFor(() => expect(screen.getByLabelText('Operations mission')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Operations mission'), { target: { value: 'mission-a' } });
    await waitFor(() => expect(operationsApi.fetchOperationsGraph).toHaveBeenLastCalledWith('project-a', expect.objectContaining({ missionId: 'mission-a', limit: 200 })));

    fireEvent.click(screen.getByRole('button', { name: /Launch risk/i }));
    expect(screen.getByText('Persisted connections')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /artifact parent.*Launch/i }));
    expect(within(screen.getByLabelText('Selected lifecycle node')).getByText('Launch')).toBeTruthy();
  });
});
