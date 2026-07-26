import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DbosRequestError,
  createDbosMission,
  executeDbosMission,
  fetchDbosControlCenter,
  reconcileDbosMissionVerifications,
  rollbackDbosExecution,
  stopDbosMission,
} from './dbosApi';

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.unstubAllGlobals());

describe('dbosApi', () => {
  it('keeps mission creation and control-center reads explicitly project scoped', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return Promise.resolve(response({ mission: { artifact_id: 'mission-a', project_id: 'project-a', title: 'Recovery', intent: 'Recover conversion', intake_mode: 'business', mission_status: 'draft' } }));
    }));

    await createDbosMission({ project_id: 'project-a', title: 'Recovery', intent: 'Recover conversion', intake_mode: 'business', context: { industry: 'ecommerce' } });
    await fetchDbosControlCenter('project-a', 'mission/a');

    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ project_id: 'project-a', context: { industry: 'ecommerce' } });
    expect(calls[1].url).toContain('/api/dbos/missions/mission%2Fa/control-center?project_id=project-a');
  });

  it('preserves execution confirmation conflicts instead of presenting them as success', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response({ detail: 'mission must be confirmed before execution' }, 409))));

    const error = await executeDbosMission('project-a', 'mission-a', 'risk_analysis').catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(DbosRequestError);
    expect((error as DbosRequestError).status).toBe(409);
    expect((error as DbosRequestError).message).toContain('confirmed');
  });

  it('uses project-scoped governance endpoints for stop and rollback', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return Promise.resolve(response({ mission: { artifact_id: 'mission-a', mission_status: 'stopped' }, execution_result: { artifact_id: 'execution-a', execution_status: 'rolled_back' } }));
    }));

    await stopDbosMission('project-a', 'mission/a', 'Owner paused the mission.');
    await rollbackDbosExecution('project-a', 'execution/a', 'Reviewer rejected the result.');

    expect(calls[0].url).toContain('/api/dbos/missions/mission%2Fa/stop');
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ project_id: 'project-a', reason: 'Owner paused the mission.' });
    expect(calls[1].url).toContain('/api/dbos/executions/execution%2Fa/rollback');
    expect(JSON.parse(String(calls[1].init?.body))).toMatchObject({ project_id: 'project-a', reason: 'Reviewer rejected the result.' });
  });

  it('reconciles historic provider proof through a project-scoped mutation endpoint', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return Promise.resolve(response({ verifications: [] }));
    }));

    await reconcileDbosMissionVerifications('project-a', 'mission/a');

    expect(calls[0].url).toContain('/api/dbos/missions/mission%2Fa/verifications/reconcile?project_id=project-a');
    expect(calls[0].init?.method).toBe('POST');
  });
});
