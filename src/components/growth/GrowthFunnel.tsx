import type { ECharts } from 'echarts';
import { AlertTriangle, BarChart3, LoaderCircle } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';

import type { GrowthCounts, GrowthRequestState } from '../../api/growthApi';

type Props = { counts: GrowthCounts | null; state: GrowthRequestState; error?: string };

export function GrowthFunnel({ counts, state, error }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const inventory = useMemo(() => counts ? [
    { value: counts.sources, name: 'A Evidence', color: '#76c9dc' },
    { value: counts.pages, name: 'B Knowledge', color: '#a8cf74' },
    { value: counts.methods, name: 'C Methods', color: '#e5b65e' },
    { value: counts.outputs, name: 'D Outputs', color: '#df8793' },
  ] : [], [counts]);
  const hasData = inventory.some((item) => item.value > 0);

  useEffect(() => {
    if (!chartRef.current || !counts || !hasData) return undefined;
    if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) return undefined;
    const element = chartRef.current;
    let active = true;
    let chart: ECharts | undefined;
    void import('../charts/echartsRuntime').then(({ echarts }) => {
      if (!active) return;
      chart = echarts.init(element, undefined, { renderer: 'canvas' });
      chart.setOption({
        animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        animationDuration: 360,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c} persisted records' },
        grid: { left: 92, right: 40, top: 12, bottom: 12 },
        xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#273844' } }, axisLabel: { color: '#8ca4b1' } },
        yAxis: { type: 'category', data: inventory.map((item) => item.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#d9e5eb', fontSize: 11 } },
        series: [{
          type: 'bar',
          barMaxWidth: 24,
          label: { show: true, position: 'right', color: '#d9e5eb', fontSize: 11, formatter: '{c}' },
          data: inventory.map((item) => ({ value: item.value, itemStyle: { color: item.color, borderRadius: [0, 3, 3, 0] } })),
        }],
      });
    }).catch(() => { chart = undefined; });
    const resize = () => chart?.resize();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(element);
    window.addEventListener('resize', resize);
    return () => { active = false; observer?.disconnect(); window.removeEventListener('resize', resize); chart?.dispose(); };
  }, [counts, hasData, inventory]);

  if (state === 'loading') return <div className="growth-empty growth-empty--funnel" role="status"><LoaderCircle className="spin" size={18} /><span>Loading persisted flow counts...</span></div>;
  if (state === 'permission' || state === 'offline' || state === 'unavailable' || state === 'error') {
    return <div className="growth-empty growth-empty--funnel" role="alert"><AlertTriangle size={18} /><span>{error || 'Flow counts are unavailable. No fallback values are rendered.'}</span></div>;
  }
  if (!counts || !hasData) return <div className="growth-empty growth-empty--funnel" aria-label="A to D knowledge inventory"><BarChart3 size={18} /><span>No persisted A/B/C/D records to visualize.</span></div>;

  const coverage = (covered: number, total: number) => total > 0 ? `${Math.round((covered / total) * 100)}% (${covered}/${total})` : 'No sample';
  return <div className="growth-funnel" aria-label="A to D knowledge inventory">
    <div ref={chartRef} className="growth-funnel__chart" data-chart="growth-funnel" />
    <div className="growth-funnel__summary">
      <p>Persisted coverage facts</p>
      <dl>
        <div><dt>Evidence admitted</dt><dd>{coverage(counts.eligible_sources, counts.sources)}</dd></div>
        <div><dt>Methods published</dt><dd>{coverage(counts.published_methods, counts.methods)}</dd></div>
        <div><dt>Outputs verified</dt><dd>{coverage(counts.accepted_outputs, counts.outputs)}</dd></div>
      </dl>
    </div>
    <table className="growth-visually-hidden"><caption>Persisted knowledge inventory values</caption><tbody>
      <tr><th>A Evidence</th><td>{counts.sources}</td></tr><tr><th>B Knowledge</th><td>{counts.pages}</td></tr>
      <tr><th>C Methods</th><td>{counts.methods}</td></tr><tr><th>D Outputs</th><td>{counts.outputs}</td></tr>
    </tbody></table>
  </div>;
}
