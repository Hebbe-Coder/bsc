// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore } from '../store/knowledgeWorkspaceStore';
import { detectMode, formatRuntimeError, isLocalProxySession, syncGrowthProjectContext, syncKnowledgeProjectContext, UnifiedWorkspace } from './UnifiedWorkspace';

vi.mock('./KnowledgeWorkspace', () => ({
  KnowledgeWorkspace: ({ onProjectChange }: { onProjectChange: (projectId: string) => void }) => createElement(
    'section',
    { role: 'dialog', 'aria-label': 'Knowledge workspace' },
    createElement('button', { type: 'button', onClick: () => onProjectChange('proj_b8a285642094') }, 'Select knowledge project'),
  ),
}));

vi.mock('./GrowthWorkspace', () => ({
  GrowthWorkspace: () => createElement('section', { role: 'dialog', 'aria-label': 'Knowledge growth workspace' }, 'Growth workspace'),
}));

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  useGrowthWorkspaceStore.getState().reset();
  useKnowledgeWorkspaceStore.getState().setProjectId('');
  delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
});

describe('formatRuntimeError', () => {
  it('turns unreachable backend failures into a Vite proxy recovery action', () => {
    expect(formatRuntimeError(new TypeError('Failed to fetch'))).toMatch(/VITE_API_PROXY_TARGET/);
  });

  it('turns API authentication failures into an actionable access-key request', () => {
    expect(formatRuntimeError(new Error('HTTP error! status: 401, message: authentication required'))).toMatch(/runtime access key/i);
  });

  it('explains when a long-running request exceeds the UI wait budget', () => {
    expect(formatRuntimeError(new Error('signal is aborted without reason'))).toMatch(/may still be completing/i);
  });

  it('routes an ordinary business outcome through Business OS instead of the coverage dashboard', () => {
    const result = detectMode('I lead regional retail operations and need a 30-day recovery system for falling store traffic.');

    expect(result.mode).toBe('business');
    expect(result.reason).toMatch(/diagnosis/i);
  });
});

describe('isLocalProxySession', () => {
  it('requires both an enabled local proxy marker and the sentinel session value', () => {
    expect(isLocalProxySession('local-proxy', 'local-proxy')).toBe(true);
    expect(isLocalProxySession('', '')).toBe(false);
    expect(isLocalProxySession('local-proxy', '')).toBe(false);
    expect(isLocalProxySession('manual-key', 'local-proxy')).toBe(false);
  });
});

describe('syncGrowthProjectContext', () => {
  it('sets the Growth workspace project before it mounts instead of retaining default', () => {
    useGrowthWorkspaceStore.getState().reset();

    syncGrowthProjectContext('proj_b8a285642094');

    expect(useGrowthWorkspaceStore.getState().projectId).toBe('proj_b8a285642094');
  });

  it('clears the Growth project when no Knowledge project is selected', () => {
    useGrowthWorkspaceStore.getState().setProjectId('stale-project');

    syncGrowthProjectContext('   ');

    expect(useGrowthWorkspaceStore.getState().projectId).toBe('');
  });
});

describe('syncKnowledgeProjectContext', () => {
  it('sets the shared Knowledge project before the lazy workspace mounts', () => {
    useKnowledgeWorkspaceStore.getState().setProjectId('default');

    syncKnowledgeProjectContext(' proj_b8a285642094 ');

    expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('proj_b8a285642094');
  });

  it('propagates a project switch and explicit clear without falling back to default', () => {
    syncKnowledgeProjectContext('project-next');
    expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('project-next');

    syncKnowledgeProjectContext('   ');
    expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('');
  });
});

describe('workspace navigation', () => {
  it('moves the selected Knowledge project into a visible Growth workspace without leaving Knowledge over it', async () => {
    render(createElement(UnifiedWorkspace));

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Select knowledge project' }));
    await waitFor(() => expect(screen.getByLabelText('Project knowledge context ID')).toHaveValue('proj_b8a285642094'));

    fireEvent.click(screen.getByRole('button', { name: 'Growth' }));

    expect(await screen.findByRole('dialog', { name: 'Knowledge growth workspace' })).toBeVisible();
    expect(screen.queryByRole('dialog', { name: 'Knowledge workspace' })).not.toBeInTheDocument();
    expect(useGrowthWorkspaceStore.getState().projectId).toBe('proj_b8a285642094');
  });
});
