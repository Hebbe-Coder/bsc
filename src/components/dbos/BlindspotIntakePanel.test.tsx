// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  fetchDbosIntakeAvailability: vi.fn(),
  fetchDbosIntake: vi.fn(),
  createDbosIntake: vi.fn(),
  nextDbosIntakeQuestion: vi.fn(),
  answerDbosIntake: vi.fn(),
  listDbosIntakeRevisions: vi.fn(),
  revertDbosIntakeAnswer: vi.fn(),
  directReviewDbosIntake: vi.fn(),
  selectDbosIntakeTier: vi.fn(),
  convertDbosIntake: vi.fn(),
}));

vi.mock('../../api/dbosApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/dbosApi')>()),
  ...api,
}));

import { BlindspotIntakePanel } from './BlindspotIntakePanel';

const base = {
  artifact_id: 'intake-a', project_id: 'project-a', original_request: 'Build a research workflow',
  classification: 'build', classification_confidence: 0.9, classification_rationale: ['build signal'],
  domain: 'automation', unresolved_fields: [], recommendations: [],
};

describe('BlindspotIntakePanel', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('removes the governed Intake entry point when the server disables the feature', async () => {
    api.fetchDbosIntakeAvailability.mockResolvedValue({ enabled: false });

    render(<BlindspotIntakePanel projectId="project-a" onMissionConverted={vi.fn()} />);

    await waitFor(() => expect(screen.queryByLabelText('Governed intake')).not.toBeInTheDocument());
    expect(api.createDbosIntake).not.toHaveBeenCalled();
  });

  it('clears a restored Intake when its project scope changes', async () => {
    api.fetchDbosIntakeAvailability.mockResolvedValue({ enabled: true });
    api.fetchDbosIntake.mockResolvedValue({ ...base, phase: 'converted' });
    api.listDbosIntakeRevisions.mockResolvedValue({ revisions: [] });
    const { rerender } = render(<BlindspotIntakePanel projectId="project-a" sessionId="intake-a" onMissionConverted={vi.fn()} />);

    expect(await screen.findByText('Build a research workflow')).toBeVisible();
    rerender(<BlindspotIntakePanel projectId="project-b" onMissionConverted={vi.fn()} />);

    await waitFor(() => expect(screen.queryByText('Build a research workflow')).not.toBeInTheDocument());
    expect(screen.getByText('Frame the work before a Mission exists')).toBeVisible();
  });

  it('starts a non-executable clarification from a carried business request', async () => {
    api.fetchDbosIntakeAvailability.mockResolvedValue({ enabled: true });
    api.createDbosIntake.mockResolvedValue({ ...base, phase: 'clarifying' });
    api.nextDbosIntakeQuestion.mockResolvedValue({
      intake: { ...base, phase: 'clarifying' },
      question: { question_id: 'qualify-role', phase: 'qualify', field: 'role', prompt: 'Who owns the outcome?', options: [] },
    });
    api.listDbosIntakeRevisions.mockResolvedValue({ revisions: [] });

    render(<BlindspotIntakePanel projectId="project-a" initialRequestText="Recover store traffic in 30 days" autoStart onMissionConverted={vi.fn()} />);

    await waitFor(() => expect(api.createDbosIntake).toHaveBeenCalledWith('project-a', 'Recover store traffic in 30 days'));
    expect(await screen.findByText('Who owns the outcome?')).toBeVisible();
    expect(api.convertDbosIntake).not.toHaveBeenCalled();
  });

  it('uses one bounded question, preserves skip, selects a tier, and converts to a gated Mission', async () => {
    api.fetchDbosIntakeAvailability.mockResolvedValue({ enabled: true });
    api.createDbosIntake.mockResolvedValue({ ...base, phase: 'clarifying' });
    api.nextDbosIntakeQuestion.mockResolvedValue({
      intake: { ...base, phase: 'clarifying' },
      question: { question_id: 'qualify-role', phase: 'qualify', field: 'role', prompt: 'Who owns the outcome?', options: [{ label: 'Founder or owner', value: 'Founder or owner' }] },
    });
    api.answerDbosIntake.mockResolvedValue({ ...base, phase: 'ready_for_review', unresolved_fields: ['role'] });
    api.listDbosIntakeRevisions.mockResolvedValue({ revisions: [] });
    api.selectDbosIntakeTier.mockResolvedValue({ ...base, phase: 'ready_for_review', tier: 'standard' });
    api.convertDbosIntake.mockResolvedValue({ intake: { ...base, phase: 'converted', tier: 'standard', linked_mission_id: 'mission-a' }, mission: { artifact_id: 'mission-a', title: 'Research workflow', mission_status: 'ready_for_confirmation' } });
    const onMissionConverted = vi.fn();

    render(<BlindspotIntakePanel projectId="project-a" onMissionConverted={onMissionConverted} />);
    fireEvent.change(await screen.findByLabelText('Request'), { target: { value: 'Build a research workflow' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start intake' }));

    expect(await screen.findByText('Who owns the outcome?')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await waitFor(() => expect(screen.getByText('OPERATING DEPTH')).toBeVisible());

    fireEvent.click(screen.getByRole('button', { name: 'standard' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create Mission' })).toBeVisible());
    fireEvent.click(screen.getByRole('button', { name: 'Create Mission' }));

    await waitFor(() => expect(onMissionConverted).toHaveBeenCalledWith('mission-a'));
    expect(api.answerDbosIntake).toHaveBeenCalledWith('project-a', 'intake-a', 'qualify-role', '', true);
    expect(api.selectDbosIntakeTier).toHaveBeenCalledWith('project-a', 'intake-a', 'standard');
  });

  it('lets a user bypass questions, undo an answer, and inspect governed source metadata', async () => {
    api.fetchDbosIntakeAvailability.mockResolvedValue({ enabled: true });
    api.createDbosIntake.mockResolvedValue({ ...base, phase: 'clarifying' });
    api.nextDbosIntakeQuestion.mockResolvedValue({
      intake: { ...base, phase: 'clarifying' },
      question: { question_id: 'qualify-role', phase: 'qualify', field: 'role', prompt: 'Who owns the outcome?', options: [] },
    });
    api.listDbosIntakeRevisions.mockResolvedValue({ revisions: [{ artifact_id: 'revision-a', status: 'active', question_field: 'role', answer: 'Owner' }] });
    api.directReviewDbosIntake.mockResolvedValue({
      ...base,
      phase: 'ready_for_review',
      unresolved_fields: ['goal'],
      recommendations: [{ source_id: 'horizon-1', source_url: 'https://example.test/source', captured_at: '2026-07-26T12:00:00Z', trust_level: 'reviewed', status: 'eligible', applicability: 'automation intake at standard tier', summary: 'A governed signal.' }],
    });
    api.revertDbosIntakeAnswer.mockResolvedValue({ ...base, phase: 'clarifying' });

    render(<BlindspotIntakePanel projectId="project-a" onMissionConverted={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText('Request'), { target: { value: 'Build a research workflow' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start intake' }));
    expect(await screen.findByRole('button', { name: 'Undo last answer' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Undo last answer' }));
    await waitFor(() => expect(api.revertDbosIntakeAnswer).toHaveBeenCalledWith('project-a', 'intake-a', 'revision-a'));
    expect(await screen.findByRole('button', { name: 'Skip to review' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Skip to review' }));

    expect(await screen.findByText('Known gaps: goal')).toBeVisible();
    expect(screen.getByText('reviewed | eligible')).toBeVisible();
    expect(screen.getByText(/automation intake at standard tier/)).toBeVisible();
    expect(api.directReviewDbosIntake).toHaveBeenCalledWith('project-a', 'intake-a');
  });
});
