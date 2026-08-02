// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore } from '../store/knowledgeWorkspaceStore';
import { fetchKnowledgeWorkspaceProjects } from '../api/knowledgeWorkspaceApi';
import { detectMode, formatRuntimeError, isLocalProxySession, syncGrowthProjectContext, syncKnowledgeProjectContext, UnifiedWorkspace } from './UnifiedWorkspace';

vi.mock('../api/knowledgeWorkspaceApi', () => ({
  fetchKnowledgeWorkspaceProjects: vi.fn(),
}));

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

vi.mock('./operations/KnowledgeOperationsCockpit', () => ({
  KnowledgeOperationsCockpit: ({ onOpenGrowth }: { onOpenGrowth?: (projectId: string, entityId: string) => void }) => createElement(
    'section',
    { role: 'dialog', 'aria-label': 'Knowledge operations cockpit' },
    'Operations cockpit',
    onOpenGrowth && createElement('button', { type: 'button', onClick: () => onOpenGrowth('project-action', 'proposal-action') }, 'Open governed review'),
  ),
}));

vi.mock('./pbos/PersonalGrowthCockpit', () => ({
  PersonalGrowthCockpit: () => createElement('section', { role: 'dialog', 'aria-label': 'Personal Growth Cockpit' }, 'PBOS cockpit'),
}));

vi.mock('./dbos/BusinessControlCenter', () => ({
  BusinessControlCenter: ({ autoStartIntake, initialRequestText, onClose }: { autoStartIntake?: boolean; initialRequestText?: string; onClose?: () => void }) => createElement(
    'section',
    { role: 'dialog', 'aria-label': 'Business Control Center' },
    autoStartIntake ? `Auto intake: ${initialRequestText}` : 'Blank mission',
    onClose && createElement('button', { type: 'button', onClick: onClose }, 'Close mission'),
  ),
}));

beforeEach(() => {
  vi.mocked(fetchKnowledgeWorkspaceProjects).mockReset();
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

  it('routes Chinese multi-agent, PRD, and analysis requests to their intended workspaces', () => {
    expect(detectMode('请组织 CEO、CFO 和 CTO 进行多智能体董事会评审').mode).toBe('board');
    expect(detectMode('请把这份产品需求文档编译为项目专属的动态 SOP 与执行流水线').mode).toBe('compile');
    expect(detectMode('请诊断当前方案的风险、证据缺口与覆盖范围').mode).toBe('analyze');
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
  it('discovers authorized projects and opens PBOS in the selected project instead of an unscoped workspace', async () => {
    vi.mocked(fetchKnowledgeWorkspaceProjects).mockResolvedValue({
      projects: [
        { id: 'proj_b8a285642094', name: 'Personal Knowledge Intelligence', created_at: '2026-07-27T18:57:22' },
        { id: 'default', name: 'Obsidian Knowledge Vault', created_at: '2026-07-21T21:16:47' },
      ],
      count: 2,
    });
    render(createElement(StrictMode, null, createElement(UnifiedWorkspace)));

    fireEvent.change(screen.getByLabelText('Runtime access key'), { target: { value: 'test-runtime-key' } });
    expect(await screen.findByRole('option', { name: /Personal Knowledge Intelligence/ })).toBeVisible();
    fireEvent.change(screen.getByLabelText('Project knowledge context ID'), { target: { value: 'proj_b8a285642094' } });

    expect(screen.getByLabelText('Project knowledge context ID')).toHaveValue('proj_b8a285642094');
    expect(screen.getByText('mapped')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'PBOS' }));
    expect(await screen.findByRole('dialog', { name: 'Personal Growth Cockpit' })).toBeVisible();
  });

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

  it.each([
    ['Operate', 'Knowledge operations cockpit'],
    ['PBOS', 'Personal Growth Cockpit'],
    ['Mission', 'Business Control Center'],
  ])('closes Knowledge before opening %s for the selected project', async (command, destination) => {
    render(createElement(UnifiedWorkspace));

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Select knowledge project' }));
    await waitFor(() => expect(screen.getByLabelText('Project knowledge context ID')).toHaveValue('proj_b8a285642094'));

    fireEvent.click(screen.getByRole('button', { name: command }));

    expect(await screen.findByRole('dialog', { name: destination })).toBeVisible();
    expect(screen.queryByRole('dialog', { name: 'Knowledge workspace' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Project knowledge context ID')).toHaveValue('proj_b8a285642094');
  });

  it('preserves the Operations review drill-down after changing the active project', async () => {
    render(createElement(UnifiedWorkspace));

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Select knowledge project' }));
    fireEvent.click(screen.getByRole('button', { name: 'Operate' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Open governed review' }));

    expect(await screen.findByRole('dialog', { name: 'Knowledge growth workspace' })).toBeVisible();
    expect(screen.queryByRole('dialog', { name: 'Knowledge operations cockpit' })).not.toBeInTheDocument();
    expect(useKnowledgeWorkspaceStore.getState().projectId).toBe('project-action');
    expect(useGrowthWorkspaceStore.getState()).toMatchObject({
      projectId: 'project-action',
      stage: 'review',
      centerView: 'assets',
      selectedId: 'proposal-action',
    });
  });

  it('clears a prior auto-start request when the user explicitly opens a new Mission', async () => {
    render(createElement(UnifiedWorkspace));

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Select knowledge project' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Business analysis input' }), { target: { value: 'Prepare a governed expansion plan.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run workflow' }));

    expect(await screen.findByText('Auto intake: Prepare a governed expansion plan.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Close mission' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mission' }));

    expect(await screen.findByText('Blank mission')).toBeVisible();
    expect(screen.queryByText('Auto intake: Prepare a governed expansion plan.')).not.toBeInTheDocument();
  });
});
