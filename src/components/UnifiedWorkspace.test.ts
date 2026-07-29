import { describe, expect, it } from 'vitest';
import { detectMode, formatRuntimeError, isLocalProxySession } from './UnifiedWorkspace';

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
