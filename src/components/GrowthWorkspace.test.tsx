import { describe, expect, it } from 'vitest';

import { GrowthWorkspace } from './GrowthWorkspace';

describe('GrowthWorkspace compatibility export', () => {
  it('keeps the UnifiedWorkspace import stable after the P8 component split', () => {
    expect(GrowthWorkspace).toBeTypeOf('function');
  });
});
