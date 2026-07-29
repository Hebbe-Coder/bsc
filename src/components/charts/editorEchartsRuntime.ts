import {
  GaugeChart,
  PieChart,
  RadarChart,
  ScatterChart,
} from 'echarts/charts';
import {
  PolarComponent,
  RadarComponent,
} from 'echarts/components';

import { echarts } from './echartsRuntime';

// The legacy slide editor supports a broader chart palette. Keep it out of
// operational workspaces until the editor itself is rendered.
echarts.use([
  GaugeChart,
  PieChart,
  PolarComponent,
  RadarChart,
  RadarComponent,
  ScatterChart,
]);

export { echarts };
