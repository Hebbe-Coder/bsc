import { afterEach, describe, expect, it, vi } from 'vitest';

import { configureKnowledgePlugins, configureKnowledgeVault, fetchKnowledgeWorkspace, fetchWeeklyDistillations, importFeishuKnowledgeExport, initializeKnowledgeWorkspace, KnowledgeRequestError, saveKnowledgeEvaluationCase, setKnowledgePluginTrust } from './knowledgeWorkspaceApi';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('knowledge workspace API', () => {
  it('encodes the explicit project ID in every workspace request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: {
        project_id: 'client/a', vault: { configured: false, status: 'unconfigured' }, sources: 0, runs: 0, schedules: 0,
        access: { role: 'reader', can_write: false }, scheduler: { available: false, mode: 'manual' },
      },
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchKnowledgeWorkspace('client/a');

    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/workspaces/client%2Fa');
  });

  it('normalizes typed backend errors without exposing transport internals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 409,
      message: { code: 'knowledge_conflict', message: 'Wiki revision changed' },
      data: null,
    }), { status: 409, headers: { 'content-type': 'application/json' } })));

    const failure = await fetchKnowledgeWorkspace('project-a').catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(KnowledgeRequestError);
    expect((failure as KnowledgeRequestError).code).toBe('knowledge_conflict');
    expect((failure as KnowledgeRequestError).status).toBe(409);
    expect((failure as Error).message).toBe('Wiki revision changed');
  });

  it('maps and initializes the explicit project scope through governed endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      success: true,
      data: { vault: { configured: true, status: 'configured', vault_path: 'projects/default' }, created: ['AGENTS.md'], indexing: {}, run_id: 'run-1' },
    }), { status: 200, headers: { 'content-type': 'application/json' } })));
    vi.stubGlobal('fetch', fetchMock);

    await configureKnowledgeVault('project a', 'projects/default');
    await configureKnowledgePlugins('project a', [{ id: 'readwise', name: 'Readwise Export', input_paths: ['raw/readwise'] }]);
    await initializeKnowledgeWorkspace('project a');
    await saveKnowledgeEvaluationCase('project a', {
      case_id: 'release-content', case_type: 'content', expected: { constraints: ['named owner'], require_citations: true },
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/workspaces/project%20a/vault');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ vault_path: 'projects/default' }) });
    expect(String(fetchMock.mock.calls[1][0])).toContain('/knowledge/workspaces/project%20a/plugins');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ plugins: [{ id: 'readwise', name: 'Readwise Export', input_paths: ['raw/readwise'] }] }) });
    expect(String(fetchMock.mock.calls[2][0])).toContain('/knowledge/workspaces/project%20a/initialize');
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: 'POST', body: '{}' });
    expect(String(fetchMock.mock.calls[3][0])).toContain('/knowledge/eval-cases');
    expect(fetchMock.mock.calls[3][1]).toMatchObject({
      method: 'POST', body: JSON.stringify({ project_id: 'project a', case_id: 'release-content', case_type: 'content', expected: { constraints: ['named owner'], require_citations: true } }),
    });
  });

  it('records plugin read approval through the separate trust endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: { configured: true, supported_adapters: ['filesystem_drop'], plugins: [], errors: [] },
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    await setKnowledgePluginTrust('project a', ['obsidian-clipper'], true, 'approved export path');

    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/workspaces/project%20a/plugins/trust');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'PUT',
      body: JSON.stringify({ plugin_ids: ['obsidian-clipper'], trusted: true, reason: 'approved export path' }),
    });
  });

  it('imports an explicit Feishu export under the selected project boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: { created: true, run_id: 'feishu-run-1', source: { id: 'source-1', source_type: 'feishu_minutes' } },
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    await importFeishuKnowledgeExport('project a', {
      document_id: 'doccnA1', revision_id: 'rev-7', document_type: 'minutes',
      source_url: 'https://example.feishu.cn/minutes/doccnA1', title: 'Weekly review', content: 'Decision: keep citations.',
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/sources/feishu/import');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ project_id: 'project a', export: {
        document_id: 'doccnA1', revision_id: 'rev-7', document_type: 'minutes',
        source_url: 'https://example.feishu.cn/minutes/doccnA1', title: 'Weekly review', content: 'Decision: keep citations.',
      } }),
    });
  });

  it('keeps current distillations as the default and requests revisions explicitly', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      success: true,
      data: { distillations: [], count: 0 },
    }), { status: 200, headers: { 'content-type': 'application/json' } })));
    vi.stubGlobal('fetch', fetchMock);

    await fetchWeeklyDistillations('project a');
    await fetchWeeklyDistillations('project a', true);

    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/distillations?project_id=project%20a');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('include_history');
    expect(String(fetchMock.mock.calls[1][0])).toContain('include_history=true');
  });
});
