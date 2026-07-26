import { describe, expect, it } from 'vitest';
import { formatRuntimeError } from './UnifiedWorkspace';

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
});
