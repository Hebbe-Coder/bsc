import { afterEach, describe, expect, it, vi } from 'vitest';
import { createFetchWrapper } from './fetchWrapper';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FetchWrapper error parsing', () => {
  it('surfaces structured backend detail instead of an unknown error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: 'recovery_failed', reason: 'database unavailable' } }),
      { status: 500 },
    )));

    await expect(createFetchWrapper().fetch('/agent/analyze', { skipRetry: true }))
      .rejects
      .toThrow('recovery_failed');
  });
});
