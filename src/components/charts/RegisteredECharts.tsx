import type { ComponentProps } from 'react';
import EChartsReactCore from 'echarts-for-react/lib/core';

import { echarts } from './echartsRuntime';

type Props = Omit<ComponentProps<typeof EChartsReactCore>, 'echarts'>;

export default function RegisteredECharts(props: Props) {
  return <EChartsReactCore {...props} echarts={echarts} />;
}
