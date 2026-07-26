// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  createDbosIntake: vi.fn(),
  nextDbosIntakeQuestion: vi.fn(),
  answerDbosIntake: vi.fn(),
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

  it('uses one bounded question, preserves skip, selects a tier, and converts to a gated Mission', async () => {
    api.createDbosIntake.mockResolvedValue({ ...base, phase: 'clarifying' });
    api.nextDbosIntakeQuestion.mockResolvedValue({
      intake: { ...base, phase: 'clarifying' },
      question: { question_id: 'qualify-role', phase: 'qualify', field: 'role', prompt: 'Who owns the outcome?', options: [{ label: 'Founder or owner', value: 'Founder or owner' }] },
    });
    api.answerDbosIntake.mockResolvedValue({ ...base, phase: 'ready_for_review', unresolved_fields: ['role'] });
    api.selectDbosIntakeTier.mockResolvedValue({ ...base, phase: 'ready_for_review', tier: 'standard' });
    api.convertDbosIntake.mockResolvedValue({ intake: { ...base, phase: 'converted', tier: 'standard', linked_mission_id: 'mission-a' }, mission: { artifact_id: 'mission-a', title: 'Research workflow', mission_status: 'ready_for_confirmation' } });
    const onMissionConverted = vi.fn();

    render(<BlindspotIntakePanel projectId="project-a" onMissionConverted={onMissionConverted} />);
    fireEvent.change(screen.getByLabelText('Request'), { target: { value: 'Build a research workflow' } });
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
});
