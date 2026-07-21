import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchKnowledgeWorkspace, KnowledgeRequestError } from './knowledgeWorkspaceApi';

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
});
