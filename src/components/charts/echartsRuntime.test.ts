import { describe, expect, it } from 'vitest';

import { echarts } from './echartsRuntime';

describe('knowledge ECharts runtime', () => {
  it('registers the graphic component used by empty-state chart options', () => {
    expect(echarts.graphic).toBeDefined();
    expect(echarts.graphic.LinearGradient).toBeTypeOf('function');
  });
});
