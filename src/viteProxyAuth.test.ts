import { describe, expect, it } from 'vitest';
import { resolveApiProxyTarget, resolveLocalRuntimeApiKey } from '../vite.config';

describe('resolveApiProxyTarget', () => {
  it('gives an isolated process target precedence over file defaults', () => {
    expect(resolveApiProxyTarget(
      { VITE_API_PROXY_TARGET: 'http://127.0.0.1:8010' },
      { BSC_VITE_API_PROXY_TARGET: 'http://127.0.0.1:8002' },
    )).toBe('http://127.0.0.1:8010');
  });
});

describe('resolveLocalRuntimeApiKey', () => {
  it('does not treat the generic API_KEY as a proxy credential', () => {
    expect(resolveLocalRuntimeApiKey('serve', 'development', { API_KEY: 'runtime-key' }, {})).toBe('');
  });

  it('uses an explicit local proxy setting from the process or local environment file', () => {
    expect(resolveLocalRuntimeApiKey('serve', 'development', { BSC_LOCAL_API_KEY: 'process-key' }, { BSC_LOCAL_API_KEY: 'file-key' })).toBe('process-key');
    expect(resolveLocalRuntimeApiKey('serve', 'development', {}, { BSC_LOCAL_API_KEY: 'file-key' })).toBe('file-key');
    expect(resolveLocalRuntimeApiKey('serve', 'development', {}, {})).toBe('');
  });

  it('disables proxy-managed credentials for production builds', () => {
    expect(resolveLocalRuntimeApiKey('serve', 'production', { BSC_LOCAL_API_KEY: 'local-key' }, { BSC_LOCAL_API_KEY: 'file-key' })).toBe('');
  });
});
