// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('reactflow', () => ({
  default: ({ nodes }: { nodes: Array<{ id: string; data: { label: string } }> }) => <div data-testid="dbos-graph">{nodes.map((node) => <span key={node.id}>{node.data.label}</span>)}</div>,
  Background: () => null,
  Controls: () => null,
}));

import { BusinessControlCenter } from './BusinessControlCenter';
import type { DBOSControlCenter } from '../../api/dbosApi';

const dbosApi = vi.hoisted(() => ({
  createDBOSMission: vi.fn(),
  diagnoseDBOSMission: vi.fn(),
  getDBOSControlCenter: vi.fn(),
  listDbosMissions: vi.fn(),
}));

vi.mock('../../api/dbosApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/dbosApi')>()),
  ...dbosApi,
}));

const center: DBOSControlCenter = {
  mission: { artifact_id: 'mission-a', title: 'Conversion recovery', mission_status: 'ready_for_confirmation', status: 'ready_for_confirmation' },
  diagnosis: { role: 'operations lead', industry: 'ecommerce', organization_stage: 'growth', goal: 'restore conversion', constraints: ['limited budget'], stakeholders: ['merchandising lead'], decision_rights: ['operations director'], success_metrics: ['cart conversion'], operating_hypotheses: ['cart loss is the controllable bottleneck'], missing_fields: [] },
  selection: { selected: [
    { capability_name: 'business_understanding', task_family: 'context_mapping', score: 0.8, reasons: ['shared context'], executable: true },
    { capability_name: 'optimization_recommendations', task_family: 'conversion_experiment', score: 0.9, reasons: ['ecommerce'], executable: true },
  ], rejected: [] },
  dynamic_sop: { title: '30-day Conversion Recovery Operating System', objective: 'Restore conversion', diagnostic_summary: 'Use the funnel baseline before acquisition spend.', quality_gates: ['A source-backed baseline exists.'], phases: [{ phase_id: 'operate', title: 'Operate', objective: 'Measure', tasks: [{ task_id: 'task-1', title: 'Run conversion recovery experiments', task_family: 'conversion_experiment', capability_name: 'optimization_recommendations', owner: 'operations lead', deliverable: 'Experiment portfolio', metric: 'conversion', trigger: 'confirmation', decision_point: 'decide', risk: 'budget', check: 'measure', retrospect: 'record', parent_refs: ['diagnosis-a', 'selection-a'] }] }] },
  execution_results: [],
  decisions: [{ artifact_id: 'decision-a', decision_statement: 'Prioritize conversion experiments', rationale: 'Budget is constrained.', metadata: { task_id: 'task-1' } }],
  memories: [],
  assumptions: [],
  gaps: [{ artifact_id: 'gap-a', gap_statement: 'Missing source-backed baseline' }],
  risks: [{ artifact_id: 'risk-a', risk_statement: 'Budget can limit the intervention.' }],
  evidence: [{ artifact_id: 'evidence-a', source: 'Trading dashboard', finding: 'Cart conversion fell 12%' }],
  verifications: [],
  runtime_context: null,
  health: { executions_total: 0, executions_completed: 0, executions_failed: 0, executions_rejected: 0, unresolved_gaps: 0 },
  reasoning_graph: { nodes: [{ id: 'mission-a', type: 'mission', label: 'Conversion recovery', status: 'ready_for_confirmation' }], edges: [], root_id: 'mission-a' },
};

describe('BusinessControlCenter', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('renders persisted health, graph, Dynamic SOP tasks, and a confirmation gate', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={center} />);

    expect(screen.getByRole('heading', { name: 'Business Control Center' })).toBeVisible();
    expect(screen.getByText('30-day Conversion Recovery Operating System')).toBeVisible();
    expect(screen.getByText('Prioritize conversion experiments')).toBeVisible();
    expect(screen.getByTestId('dbos-graph')).toHaveTextContent('Conversion recovery');
    expect(screen.getByRole('button', { name: /confirm 2 capabilities/i })).toBeVisible();
  });

  it('keeps an operations action focused on its exact durable DBOS record', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialArtifactId="risk-a" initialData={{
      ...center,
      reasoning_graph: {
        ...center.reasoning_graph,
        nodes: [...center.reasoning_graph.nodes, { id: 'risk-a', type: 'risk', label: 'Budget risk', status: 'open' }],
        edges: [{ source: 'mission-a', target: 'risk-a' }],
      },
    }} />);

    const inspector = screen.getByLabelText('Focused artifact inspector');
    expect(inspector).toHaveTextContent('Budget risk');
    expect(inspector).toHaveTextContent('risk-a');
    expect(inspector).toHaveTextContent('Persisted connections');
  });

  it('renders persisted adaptive-model evidence instead of inferring model activity', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      dynamic_sop: {
        ...center.dynamic_sop,
        metadata: {
          adaptive_compilation: {
            status: 'completed',
            context_available: true,
            specificity: { anchor_count: 18, matched_anchor_count: 14 },
            model_run: {
              provider: 'deepseek', model: 'deepseek-v4-pro', provider_calls: 1, reported_calls: 1,
              usage_complete: true, total_tokens: 3292, latency_ms: 19736, attempt_count: 1, retry_count: 0,
            },
          },
        },
      },
    }} />);

    expect(screen.getByText('PROJECT CONTEXT REFINED')).toBeVisible();
    expect(screen.getByLabelText('Model run evidence')).toHaveTextContent('deepseek / deepseek-v4-pro');
    expect(screen.getByLabelText('Model run evidence')).toHaveTextContent('1 provider / 1 reported');
    expect(screen.getByLabelText('Model run evidence')).toHaveTextContent('14 / 18 anchors');
    expect(screen.getByLabelText('Model run evidence')).toHaveTextContent('3292 tokens');
  });

  it('lets the reviewer narrow the authorization set before confirmation', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={center} />);

    fireEvent.click(screen.getByLabelText('Authorize optimization_recommendations'));
    expect(screen.getByRole('button', { name: /confirm 1 capability/i })).toBeVisible();
  });

  it('clears Mission and Intake state immediately when the project scope changes', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={center} />);

    fireEvent.change(screen.getByLabelText('DBOS project ID'), { target: { value: 'project-b' } });

    expect(screen.queryByText('30-day Conversion Recovery Operating System')).not.toBeInTheDocument();
    expect(screen.queryByText('Conversion recovery')).not.toBeInTheDocument();
  });

  it('clears cached Mission choices when the project scope changes', async () => {
    dbosApi.listDbosMissions.mockResolvedValue({ missions: [{ artifact_id: 'mission-a', title: 'Conversion recovery' }] });
    dbosApi.getDBOSControlCenter.mockResolvedValue(center);
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" />);

    expect(await screen.findByRole('option', { name: 'Conversion recovery' })).toBeVisible();
    fireEvent.change(screen.getByLabelText('DBOS project ID'), { target: { value: 'project-b' } });

    expect(screen.queryByRole('option', { name: 'Conversion recovery' })).not.toBeInTheDocument();
  });

  it('does not restore a prior project after its in-flight refresh resolves', async () => {
    let resolveList: ((value: { missions: Array<{ artifact_id: string; title: string }> }) => void) | undefined;
    dbosApi.listDbosMissions.mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve; }));

    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" />);
    await waitFor(() => expect(dbosApi.listDbosMissions).toHaveBeenCalledWith('project-a'));

    fireEvent.change(screen.getByLabelText('DBOS project ID'), { target: { value: 'project-b' } });
    resolveList?.({ missions: [{ artifact_id: 'mission-a', title: 'Conversion recovery' }] });

    await waitFor(() => expect(dbosApi.getDBOSControlCenter).not.toHaveBeenCalled());
    expect(screen.queryByText('Conversion recovery')).not.toBeInTheDocument();
  });

  it('requires the matching persisted decision before enabling execution', () => {
    const confirmedWithoutDecision: DBOSControlCenter = {
      ...center,
      mission: { ...center.mission, mission_status: 'confirmed', status: 'confirmed' },
      decisions: [],
    };
    const { unmount } = render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={confirmedWithoutDecision} />);

    expect(screen.getByRole('button', { name: 'Execute optimization_recommendations' })).toBeDisabled();

    unmount();
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{ ...center, mission: { ...center.mission, mission_status: 'confirmed', status: 'confirmed' } }} />);
    expect(screen.getByRole('button', { name: 'Execute optimization_recommendations' })).toBeEnabled();
  });

  it('shows the redacted persisted runtime context rather than a prompt body', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      runtime_context: {
        artifact_id: 'context-a',
        context_revision: 'dbos-context-v1',
        purpose: 'dynamic_sop_and_execution',
        estimated_tokens: 384,
        context_window_tokens: 32000,
        compaction_required: false,
        source_ids: ['source-a', 'source-b'],
        method_ids: ['method-a'],
        redacted: true,
      },
    }} />);

    expect(screen.getByText('CONTEXT SNAPSHOT')).toBeVisible();
    expect(screen.getByText('dbos-context-v1')).toBeVisible();
    expect(screen.getByText('2 sources, 1 methods')).toBeVisible();
    expect(screen.getByText('Redacted composition manifest recorded.')).toBeVisible();
  });

  it('exposes evidence, capability rationale, and task-level lineage for review', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={center} />);

    expect(screen.getByText('DIAGNOSIS AND EVIDENCE')).toBeVisible();
    expect(screen.getByText('Trading dashboard')).toBeVisible();
    expect(screen.getByText('CAPABILITY RATIONALE')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Run conversion recovery experiments' }));
    expect(screen.getByText('TASK INSPECTOR')).toBeVisible();
    expect(screen.getByText('diagnosis-a, selection-a')).toBeVisible();
  });

  it('distinguishes a verified capability result from an unverified execution claim', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      execution_results: [{
        artifact_id: 'execution-a', execution_id: 'exec-a', mission_id: 'mission-a', capability_name: 'optimization_recommendations',
        execution_status: 'completed', status: 'completed', effects: [],
      }],
      verifications: [{
        artifact_id: 'verification-a', execution_id: 'exec-a', capability_name: 'optimization_recommendations',
        verification_status: 'passed', produced_artifact_ids: ['deliverable-a'],
      }],
      health: { ...center.health, executions_total: 1, executions_completed: 1, executions_verified: 1 },
    }} />);

    expect(screen.getByText('COMPLETED / VERIFIED')).toBeVisible();
    expect(screen.getByText('1 / 1')).toBeVisible();
  });

  it('offers historic proof reconciliation only when an execution is still unverified', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      execution_results: [{
        artifact_id: 'execution-a', execution_id: 'exec-a', mission_id: 'mission-a', capability_name: 'optimization_recommendations',
        execution_status: 'completed', status: 'completed', effects: [],
      }],
      health: { ...center.health, executions_total: 1, executions_completed: 1, executions_unverified: 1 },
    }} />);

    expect(screen.getByRole('button', { name: 'Reconcile historic execution proof' })).toBeEnabled();
  });

  it('shows the persisted routing evaluation instead of implying SOP quality from its title', () => {
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      sop_routing_evaluation: {
        artifact_id: 'routing-evaluation-a', evaluator_revision: 'dbos-sop-routing-evaluator-v1', selector_fingerprint: 'fingerprint',
        evaluation_status: 'passed', positive_case_count: 3, near_negative_case_count: 2, holdout_case_count: 2, holdout_passed: true,
      },
    }} />);

    expect(screen.getByText('ROUTING EVALUATION')).toBeVisible();
    expect(screen.getByText('3 positive, 2 near-negative, 2 isolated holdout cases.')).toBeVisible();
    expect(screen.getByText('Holdouts: passed.')).toBeVisible();
  });

  it('makes persisted stop and rollback controls available only for eligible states', () => {
    const { unmount } = render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      mission: { ...center.mission, mission_status: 'confirmed', status: 'confirmed' },
    }} />);

    expect(screen.getByRole('button', { name: 'Stop mission' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Rollback optimization_recommendations' })).not.toBeInTheDocument();

    unmount();
    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" initialData={{
      ...center,
      mission: { ...center.mission, mission_status: 'completed', status: 'completed' },
      execution_results: [{
        artifact_id: 'execution-a', execution_id: 'exec-a', mission_id: 'mission-a', capability_name: 'optimization_recommendations',
        execution_status: 'completed', status: 'completed', effects: [],
      }],
    }} />);

    expect(screen.queryByRole('button', { name: 'Stop mission' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rollback optimization_recommendations' })).toBeEnabled();
  });

  it('keeps the compilation state visible while diagnosis is being assembled', async () => {
    let resolveDiagnosis: (() => void) | undefined;
    dbosApi.listDbosMissions.mockResolvedValue({ missions: [] });
    dbosApi.createDBOSMission.mockResolvedValue({ mission: { artifact_id: 'new-mission', title: 'New mission' } });
    dbosApi.diagnoseDBOSMission.mockImplementation(() => new Promise<void>((resolve) => { resolveDiagnosis = resolve; }));

    render(<BusinessControlCenter onClose={vi.fn()} initialProjectId="project-a" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create diagnosis' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Mission title'), { target: { value: 'AI product launch recovery' } });
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'Recover activation with evidence.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create diagnosis' }));

    expect(dbosApi.createDBOSMission).toHaveBeenCalledWith(expect.objectContaining({
      context: expect.objectContaining({ sop_generation_mode: 'adaptive' }),
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Compiling a dynamic operating system from declared evidence and project context...');
    expect(screen.getByRole('button', { name: /compiling a dynamic operating system/i })).toBeDisabled();

    resolveDiagnosis?.();
  });
});
