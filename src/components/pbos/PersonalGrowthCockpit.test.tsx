// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { capturePbosWorkspaceExecution, fetchPbosCockpit, fetchPbosProfile, recordPbosExecution, recordPbosOutcome } from '../../api/pbosApi';
import { PersonalGrowthCockpit } from './PersonalGrowthCockpit';

vi.mock('../../api/pbosApi', () => ({
  capturePbosWorkspaceExecution: vi.fn(),
  fetchPbosCockpit: vi.fn(),
  fetchPbosProfile: vi.fn(),
  recordPbosExecution: vi.fn(),
  recordPbosFeedback: vi.fn(),
  recordPbosOutcome: vi.fn(),
  savePbosProfile: vi.fn(),
}));

vi.mock('../charts/RegisteredECharts', () => ({ default: () => <div data-testid="outcome-chart" /> }));

vi.mock('reactflow', () => ({
  default: ({ children, nodes }: { children: ReactNode; nodes: Array<{ data: { label: string } }> }) => <div data-testid="workflow-lineage" data-node-labels={nodes.map((node) => node.data.label).join('|')}>{children}</div>,
  Background: () => null,
  Controls: () => null,
}));

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe('PersonalGrowthCockpit', () => {
  it('does not issue a PBOS request without a Studio access session and provides a recovery action', async () => {
    const openAccess = vi.fn();

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="" onConfigureAccess={openAccess} />);

    expect(await screen.findByText(/Studio access is required/i)).toBeVisible();
    expect(fetchPbosCockpit).not.toHaveBeenCalled();
    expect(fetchPbosProfile).not.toHaveBeenCalled();

    screen.getByRole('button', { name: /open runtime access/i }).click();
    expect(openAccess).toHaveBeenCalledTimes(1);
  });

  it('turns a rejected Studio session into an actionable access state instead of exposing a raw HTTP error', async () => {
    vi.mocked(fetchPbosCockpit).mockRejectedValue(new Error('HTTP error! status: 401, message: authentication required'));
    vi.mocked(fetchPbosProfile).mockRejectedValue(new Error('HTTP error! status: 401, message: authentication required'));

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="rejected-key" />);

    expect(await screen.findByText(/Studio access was rejected/i)).toBeVisible();
    expect(screen.queryByText(/HTTP error!/i)).not.toBeInTheDocument();
  });

  it('does not present governed Vault context as a verified personal capability', async () => {
    vi.mocked(fetchPbosCockpit).mockResolvedValue({
      profile: { focus: ['AI systems'], goals: [], preferences: {}, resources: ['Obsidian'], constraints: [] },
      today: {
        title: 'Validate the artifact contract',
        compilation_state: 'context_grounded',
        compiler_metadata: { mode: 'llm_contextual', provider: 'deepseek', model: 'deepseek-v4-pro' },
        knowledge_context_refs: [
          'vault:distillations/每周蒸馏/2026-W31/03-下周上下文包.md',
          'vault:wiki/concepts/evidence.md',
        ],
        feedback_refs: ['feedback-1'],
        phases: [{
          title: 'Freeze the evidence boundary',
          why_now: 'The current project needs a reviewable scope before implementation.',
          inputs: ['Mission objective', 'Governed Vault boundary'],
          actions: ['Define the acceptance card'],
          outputs: ['Reviewable acceptance card'],
          decision_point: { question: 'Is the boundary explicit?', proceed_when: 'Owner and metric are named.', adapt_when: 'Capture the missing constraint.' },
        }],
        execution_contract: { reflection_entry: 'Record what changed after the first observable receipt.' },
      },
      today_action: {
        state: 'recommended',
        title: 'Define the acceptance card',
        success_check: 'Owner and metric are named.',
      },
      capabilities: [], outcomes: [], feedback: [],
      strategies: [], failure_patterns: [], project_health: {},
      connectors: { github: 'awaiting_authorization', feishu: 'awaiting_authorization' },
    });
    vi.mocked(fetchPbosProfile).mockResolvedValue({
      profile: { focus: ['AI systems'], goals: [], preferences: {}, resources: ['Obsidian'], constraints: [] },
    });

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="session-key" />);

    expect(await screen.findByText(/governed Vault evidence/i)).toBeVisible();
    expect(screen.getAllByText('Define the acceptance card')[0]).toBeVisible();
    expect(screen.getByText(/Success check: Owner and metric are named/i)).toBeVisible();
    expect(screen.getByText(/Capability claims still await verified execution evidence/i)).toBeVisible();
    expect(screen.getByText('PLAN GROUNDING')).toBeVisible();
    expect(screen.getByText('LLM contextual')).toBeVisible();
    expect(screen.getByText('deepseek / deepseek-v4-pro')).toBeVisible();
    expect(screen.getByText(/1 weekly handoff/i)).toBeVisible();
    expect(screen.getByText(/03-下周上下文包\.md/i)).toBeVisible();
    expect(screen.getByText(/1 feedback input/i)).toBeVisible();
    expect(screen.getByText("TODAY'S EXECUTION PATH")).toBeVisible();
    expect(screen.getByText('Freeze the evidence boundary')).toBeVisible();
    expect(screen.getByText(/Is the boundary explicit/i)).toBeVisible();
    expect(screen.getByTestId('workflow-lineage')).toHaveAttribute('data-node-labels', expect.stringContaining('1 weekly handoff'));
    expect(screen.getByTestId('workflow-lineage')).toHaveAttribute('data-node-labels', expect.stringContaining('2 Vault refs'));
    expect(screen.getByTestId('workflow-lineage')).toHaveAttribute('data-node-labels', expect.stringContaining('1 feedback input'));
    expect(screen.queryByText(/current personal assets/i)).not.toBeInTheDocument();
  });

  it('records an accepted outcome only when the same reflection includes a safe workspace receipt and score', async () => {
    vi.mocked(fetchPbosCockpit).mockResolvedValue({
      profile: null,
      today: {
        artifact_id: 'plan-1', mission_id: 'mission-1', title: 'Verify the evidence loop', compilation_state: 'context_grounded',
        knowledge_context_refs: [], feedback_refs: [], phases: [], execution_contract: {}, compiler_metadata: { mode: 'contextual_deterministic' },
      },
      today_action: { state: 'recommended', title: 'Verify the evidence loop' },
      capabilities: [], outcomes: [], feedback: [], strategies: [], failure_patterns: [], project_health: {}, connectors: {},
    });
    vi.mocked(fetchPbosProfile).mockResolvedValue({ profile: null });
    vi.mocked(capturePbosWorkspaceExecution).mockResolvedValue({ execution: { artifact_id: 'execution-1' } });
    vi.mocked(recordPbosOutcome).mockResolvedValue({ outcome: { artifact_id: 'outcome-1' } });

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="session-key" />);

    await screen.findByText('THREE-MINUTE REFLECTION');
    fireEvent.change(screen.getByLabelText('What changed?'), { target: { value: 'Closed the audited local evidence path.' } });
    fireEvent.change(screen.getByLabelText('Evidence files in this BSC workspace'), { target: { value: 'app/pbos/service.py, tests/pbos/test_pbos_service.py' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Quality score (0-100)'), { target: { value: '86' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record reflection' }));

    await waitFor(() => expect(capturePbosWorkspaceExecution).toHaveBeenCalledWith('default', 'mission-1', expect.objectContaining({
      plan_id: 'plan-1',
      paths: ['app/pbos/service.py', 'tests/pbos/test_pbos_service.py'],
      reflection: expect.objectContaining({ completed: 'Closed the audited local evidence path.' }),
    })));
    expect(recordPbosExecution).not.toHaveBeenCalled();
    expect(recordPbosOutcome).toHaveBeenCalledWith('default', 'execution-1', expect.objectContaining({ acceptance_status: 'accepted', quality_score: 86 }));
  });

  it('renders strategy, health, and failure state only from the cockpit payload', async () => {
    vi.mocked(fetchPbosCockpit).mockResolvedValue({
      profile: null,
      today: null,
      today_action: { state: 'no_plan' },
      capabilities: [],
      outcomes: [],
      feedback: [],
      strategies: [{ artifact_id: 'strategy-2', strategy_name: 'Personal AI project delivery', version: 2, status: 'active', genome: { comparison_context: 'solo AI runtime', median_quality: 84 } }],
      failure_patterns: [{ kind: 'severe_failure', count: 1 }],
      project_health: { accepted_outcomes: 3, unverified_outcomes: 1, active_strategies: 1, evidence_ready: true },
      connectors: { github: 'awaiting_authorization', feishu: 'awaiting_authorization' },
    });
    vi.mocked(fetchPbosProfile).mockResolvedValue({ profile: null });

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="session-key" />);

    expect(await screen.findByText('PROJECT HEALTH')).toBeVisible();
    expect(screen.getByText('STRATEGY ASSETS')).toBeVisible();
    expect(screen.getByText(/Personal AI project delivery v2/i)).toBeVisible();
    expect(screen.getByText(/SEVERE FAILURE/i)).toBeVisible();
  });

  it('shows a safe model fallback category instead of presenting it as an LLM plan', async () => {
    vi.mocked(fetchPbosCockpit).mockResolvedValue({
      profile: null,
      today: {
        title: 'Capture stronger evidence',
        compilation_state: 'context_grounded',
        compiler_metadata: { mode: 'contextual_deterministic', llm_failure: 'transport_timeout' },
        knowledge_context_refs: [],
        feedback_refs: [],
      },
      today_action: { state: 'recommended', title: 'Capture stronger evidence' },
      capabilities: [], outcomes: [], feedback: [], strategies: [], failure_patterns: [], project_health: {},
      connectors: {},
    });
    vi.mocked(fetchPbosProfile).mockResolvedValue({ profile: null });

    render(<PersonalGrowthCockpit projectId="default" onClose={vi.fn()} runtimeAccessKey="session-key" />);

    expect(await screen.findByText('LLM fallback')).toBeVisible();
    expect(screen.getByText('transport timeout')).toBeVisible();
    expect(screen.queryByText('LLM contextual')).not.toBeInTheDocument();
  });
});
