import * as echarts from 'echarts/core';
import {
  BarChart,
  FunnelChart,
  LineChart,
} from 'echarts/charts';
import {
  AriaComponent,
  DatasetComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

// The recurring knowledge and PBOS workspaces use these primitives. The
// presentation editor registers its additional chart types in a lazy module.
echarts.use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  DatasetComponent,
  FunnelChart,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  LineChart,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
]);

export { echarts };
