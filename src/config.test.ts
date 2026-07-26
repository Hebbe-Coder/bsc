import { describe, expect, it } from 'vitest';
import { resolveAgentOsTimeout } from './config';

describe('resolveAgentOsTimeout', () => {
  it('keeps the default budget above the observed multi-step runtime', () => {
    expect(resolveAgentOsTimeout(undefined)).toBe(600000);
  });

  it('accepts a valid explicit long-running budget', () => {
    expect(resolveAgentOsTimeout('720000')).toBe(720000);
  });

  it('fails closed to the safe default for invalid or too-short values', () => {
    expect(resolveAgentOsTimeout('invalid')).toBe(600000);
    expect(resolveAgentOsTimeout('30000')).toBe(600000);
  });
});
