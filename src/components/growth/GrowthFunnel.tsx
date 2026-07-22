import type { ECharts } from 'echarts';
import { AlertTriangle, BarChart3, LoaderCircle } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';

import type { GrowthCounts, GrowthRequestState } from '../../api/growthApi';

type Props = { counts: GrowthCounts | null; state: GrowthRequestState; error?: string };

export function GrowthFunnel({ counts, state, error }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const values = useMemo(() => counts ? [counts.sources, counts.pages, counts.methods, counts.outputs] : [], [counts]);
  const hasData = values.some((value) => value > 0);

  useEffect(() => {
    if (!chartRef.current || !counts || !hasData) return undefined;
    if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) return undefined;
    const element = chartRef.current;
    let active = true;
    let chart: ECharts | undefined;
    void import('echarts').then((echarts) => {
      if (!active) return;
      chart = echarts.init(element, undefined, { renderer: 'canvas' });
      chart.setOption({
        animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        animationDuration: 360,
        color: ['#76c9dc', '#a8cf74', '#e5b65e', '#df8793'],
        tooltip: { trigger: 'item', formatter: '{b}: {c}' },
        series: [{
          type: 'funnel', left: '4%', top: 8, bottom: 8, width: '92%', min: 0,
          max: Math.max(...values, 1), minSize: '10%', maxSize: '100%', sort: 'none', gap: 4,
          label: { color: '#d9e5eb', fontSize: 11 },
          itemStyle: { borderColor: '#0c151d', borderWidth: 2 },
          data: [
            { value: counts.sources, name: 'A Evidence' },
            { value: counts.pages, name: 'B Knowledge' },
            { value: counts.methods, name: 'C Methods' },
            { value: counts.outputs, name: 'D Outputs' },
          ],
        }],
      });
    }).catch(() => { chart = undefined; });
    const resize = () => chart?.resize();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(element);
    window.addEventListener('resize', resize);
    return () => { active = false; observer?.disconnect(); window.removeEventListener('resize', resize); chart?.dispose(); };
  }, [counts, hasData, values]);

  if (state === 'loading') return <div className="growth-empty growth-empty--funnel" role="status"><LoaderCircle className="spin" size={18} /><span>Loading persisted flow counts...</span></div>;
  if (state === 'permission' || state === 'offline' || state === 'unavailable' || state === 'error') {
    return <div className="growth-empty growth-empty--funnel" role="alert"><AlertTriangle size={18} /><span>{error || 'Flow counts are unavailable. No fallback values are rendered.'}</span></div>;
  }
  if (!counts || !hasData) return <div className="growth-empty growth-empty--funnel" aria-label="A to D growth funnel"><BarChart3 size={18} /><span>No persisted A/B/C/D records to visualize.</span></div>;

  const conversion = (next: number, previous: number) => previous > 0 ? `${Math.round((next / previous) * 100)}%` : 'n/a';
  return <div className="growth-funnel" aria-label="A to D growth funnel">
    <div ref={chartRef} className="growth-funnel__chart" data-chart="growth-funnel" />
    <div className="growth-funnel__summary">
      <p>Persisted project snapshot</p>
      <dl>
        <div><dt>A to B</dt><dd>{conversion(counts.pages, counts.sources)}</dd></div>
        <div><dt>B to C</dt><dd>{conversion(counts.methods, counts.pages)}</dd></div>
        <div><dt>C to D</dt><dd>{conversion(counts.outputs, counts.methods)}</dd></div>
      </dl>
    </div>
    <table className="growth-visually-hidden"><caption>Persisted growth funnel values</caption><tbody>
      <tr><th>A Evidence</th><td>{counts.sources}</td></tr><tr><th>B Knowledge</th><td>{counts.pages}</td></tr>
      <tr><th>C Methods</th><td>{counts.methods}</td></tr><tr><th>D Outputs</th><td>{counts.outputs}</td></tr>
    </tbody></table>
  </div>;
}
