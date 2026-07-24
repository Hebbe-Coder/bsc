// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GrowthProfileEditor } from './GrowthProfileEditor';

const profile = {
  project_id: 'project-a',
  revision: 7,
  user_role: 'research lead',
  research_domains: ['agent systems'],
  primary_output_types: ['research brief'],
  target_audiences: ['product team'],
  preferred_channels: ['Obsidian'],
  language: 'zh-CN',
  content_voice: 'evidence-backed',
  evidence_threshold: 82,
  automatic_publication_policy: 'review',
  method_promotion_policy: 'gated',
};

describe('GrowthProfileEditor', () => {
  afterEach(() => cleanup());

  it('normalizes list fields and saves against the displayed profile revision', () => {
    const onSave = vi.fn();
    render(<GrowthProfileEditor profile={profile} canWrite busy={false} onSave={onSave} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Research domains'), { target: { value: 'agent systems, knowledge graph\nagent systems' } });
    fireEvent.change(screen.getByLabelText('Primary outputs'), { target: { value: 'new output\nresearch brief' } });
    fireEvent.change(screen.getByRole('slider', { name: 'Evidence threshold' }), { target: { value: '91' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      expected_revision: 7,
      research_domains: ['agent systems', 'knowledge graph'],
      primary_output_types: ['new output', 'research brief'],
      evidence_threshold: 91,
      language: 'zh-CN',
    }));
  });

  it('does not permit a reader to submit a profile revision', () => {
    render(<GrowthProfileEditor profile={profile} canWrite={false} busy={false} onSave={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Save profile' })).toBeDisabled();
  });
});
