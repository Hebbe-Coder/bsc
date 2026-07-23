import { describe, expect, it } from 'vitest';

import type { KnowledgeWorkspaceData } from '../api/knowledgeWorkspaceApi';
import { resolveStudioAccessStatus } from './knowledgeWorkspaceAccess';

const workspace: KnowledgeWorkspaceData = {
  project_id: 'default',
  vault: { configured: false, status: 'unconfigured' },
  plugins: { configured: false, supported_adapters: ['filesystem_drop', 'filesystem_output'], plugins: [], errors: [] },
  sources: 0,
  runs: 0,
  schedules: 0,
  access: { role: 'project_admin', can_write: true },
  features: { wiki: true, obsidian_sync: true, schedules: true, mcp_write: true, horizon: false, automatic_publication: false },
  sync: { status: 'not_run', last_run: null },
  scheduler: { available: true, mode: 'celery' },
};

describe('resolveStudioAccessStatus', () => {
  it('never treats key presence as successful authentication', () => {
    expect(resolveStudioAccessStatus('key-present', null, false, 'authentication required')).toMatchObject({
      state: 'rejected', verified: false,
    });
  });

  it('requires a successful workspace response before enabling write access', () => {
    expect(resolveStudioAccessStatus('key-present', workspace, false, '')).toMatchObject({
      state: 'verified', verified: true, label: 'Studio access verified',
    });
  });

  it('keeps an old workspace untrusted while a replacement key is being checked', () => {
    expect(resolveStudioAccessStatus('replacement-key', workspace, true, '')).toMatchObject({
      state: 'checking', verified: false,
    });
  });
});
