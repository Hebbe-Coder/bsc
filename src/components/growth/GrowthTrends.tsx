import type { ECharts, EChartsOption } from 'echarts';
import { AlertTriangle, BarChart3, Clock3, LoaderCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import type { GrowthCounts, GrowthHealth, GrowthRequestState, GrowthTrend } from '../../api/growthApi';

type Range = 7 | 30 | 90 | 'all';
type ChartProps = { option: EChartsOption; label: string; empty: boolean; emptyText: string };

function GrowthChart({ option, label, empty, emptyText }: ChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || empty || (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent))) return undefined;
    const element = ref.current;
    let active = true;
    let chart: ECharts | undefined;
    void import('../charts/echartsRuntime').then(({ echarts }) => {
      if (!active) return;
      chart = echarts.init(element);
      chart.setOption(option, true);
    }).catch(() => { chart = undefined; });
    const resize = () => chart?.resize();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(element);
    return () => { active = false; observer?.disconnect(); chart?.dispose(); };
  }, [empty, option]);
  if (empty) return <div className="growth-chart-empty"><BarChart3 size={17} /><span>{emptyText}</span></div>;
  return <div ref={ref} className="growth-trend-chart" role="img" aria-label={label} data-chart={label} />;
}

function toTime(value: string): number | null {
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function filterByRange<T>(records: T[], getDate: (record: T) => string, range: Range): T[] {
  if (range === 'all' || !records.length) return records.slice(-120);
  const times = records.map((record) => toTime(getDate(record))).filter((value): value is number => value !== null);
  if (!times.length) return records.slice(-120);
  const cutoff = Math.max(...times) - range * 86_400_000;
  return records.filter((record) => {
    const time = toTime(getDate(record));
    return time !== null && time >= cutoff;
  }).slice(-120);
}

function baseAxes() {
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { top: 24, right: 14, bottom: 34, left: 38 },
    xAxis: { type: 'category' as const, axisLabel: { color: '#8295a4', fontSize: 9 }, axisLine: { lineStyle: { color: '#2b3d49' } } },
    yAxis: { type: 'value' as const, minInterval: 1, axisLabel: { color: '#8295a4', fontSize: 9 }, splitLine: { lineStyle: { color: '#1c2a34' } } },
  };
}

type Props = {
  trend: GrowthTrend | null;
  health: GrowthHealth | null;
  counts: GrowthCounts | null;
  state: GrowthRequestState;
  error?: string;
  onRetry: () => void;
};

export function GrowthTrends({ trend, health, counts, state, error, onRetry }: Props) {
  const [range, setRange] = useState<Range>(30);
  const sourceSeries = useMemo(() => filterByRange(trend?.source_throughput ?? [], (item) => item.date, range), [range, trend]);
  const evaluationSeries = useMemo(() => filterByRange(trend?.evaluations ?? [], (item) => item.at, range), [range, trend]);
  const proposalSeries = useMemo(() => filterByRange(trend?.proposal_outcomes ?? [], (item) => item.date, range), [range, trend]);
  const proposalStatuses = [...new Set(proposalSeries.flatMap((item) => Object.keys(item.statuses)))];

  const sourceOption: EChartsOption = {
    animation: false, ...baseAxes(),
    xAxis: { ...baseAxes().xAxis, data: sourceSeries.map((item) => item.date) },
    series: [{ type: 'line', data: sourceSeries.map((item) => item.count), smooth: false, showSymbol: sourceSeries.length < 20, lineStyle: { color: '#76c9dc', width: 2 }, itemStyle: { color: '#76c9dc' } }],
  };
  const evaluationOption: EChartsOption = {
    animation: false, ...baseAxes(),
    xAxis: { ...baseAxes().xAxis, data: evaluationSeries.map((item) => item.at.slice(0, 10)) },
    yAxis: { ...baseAxes().yAxis, min: 0, max: 100 },
    series: [{ type: 'line', connectNulls: false, data: evaluationSeries.map((item) => item.score), lineStyle: { color: '#a8cf74', width: 2 }, itemStyle: { color: '#a8cf74' } }],
  };
  const proposalOption: EChartsOption = {
    animation: false, color: ['#a8cf74', '#df8793', '#e5b65e', '#76c9dc'], ...baseAxes(),
    legend: { data: proposalStatuses, textStyle: { color: '#91a3af', fontSize: 9 }, top: 0 },
    grid: { top: 34, right: 14, bottom: 34, left: 38 },
    xAxis: { ...baseAxes().xAxis, data: proposalSeries.map((item) => item.date) },
    series: proposalStatuses.map((status) => ({ name: status, type: 'bar', stack: 'outcomes', barMaxWidth: 24, data: proposalSeries.map((item) => item.statuses[status] ?? 0) })),
  };
  const debtLabels = ['Stale pages', 'Orphan pages', 'Dangling cites', 'Stale cites', 'Uncited evidence', 'Contradictions'];
  const debtValues = health ? [health.stale_page_ids.length, health.orphan_page_ids.length, health.dangling_citation_count, health.stale_citation_count, health.uncited_eligible_source_ids.length, health.contradiction_count] : [];
  const debtOption: EChartsOption = {
    animation: false, ...baseAxes(), grid: { top: 16, right: 14, bottom: 58, left: 38 },
    xAxis: { ...baseAxes().xAxis, data: debtLabels, axisLabel: { color: '#8295a4', fontSize: 9, rotate: 28 } },
    series: [{ type: 'bar', data: debtValues, barMaxWidth: 28, itemStyle: { color: '#df8793' } }],
  };

  if (state === 'loading') return <div className="growth-state growth-state--panel" role="status"><LoaderCircle className="spin" size={18} /><span>Loading persisted health and trend observations...</span></div>;
  if (state === 'permission' || state === 'offline' || state === 'unavailable' || state === 'error') return <div className={`growth-state growth-state--panel growth-state--${state}`} role="alert"><AlertTriangle size={18} /><div><strong>{state === 'error' ? 'Trend request failed' : `Trend data ${state}`}</strong><span>{error || 'No cached or generated trend series is displayed.'}</span></div><button type="button" onClick={onRetry}>Retry</button></div>;
  if (!trend || !health) return <div className="growth-empty"><BarChart3 size={18} /><span>No persisted health snapshot is available.</span></div>;

  const percent = (numerator: number, denominator: number) => denominator > 0 ? `${Math.round((numerator / denominator) * 100)}%` : 'n/a';
  return <section className="growth-trends" aria-label="Knowledge growth trends">
    <header className="growth-trends__toolbar"><div><p>TIME WINDOW</p><span>Anchored to the newest persisted observation</span></div><div role="group" aria-label="Trend date range">{([7, 30, 90, 'all'] as Range[]).map((value) => <button type="button" key={value} className={range === value ? 'is-active' : ''} aria-pressed={range === value} onClick={() => setRange(value)}>{value === 'all' ? 'All' : `${value}d`}</button>)}</div></header>
    <div className="growth-metric-strip">
      <div><span>CITATION COVERAGE</span><strong>{health.citation_coverage === null ? 'n/a' : `${Math.round(health.citation_coverage * 100)}%`}</strong><small>health API</small></div>
      <div><span>METHOD PUBLISHED</span><strong>{counts ? percent(counts.published_methods, counts.methods) : 'n/a'}</strong><small>{counts?.published_methods ?? 0} persisted</small></div>
      <div><span>OUTPUT VERIFICATION</span><strong>{counts ? percent(counts.accepted_outputs, counts.outputs) : 'n/a'}</strong><small>{counts?.rejected_outputs ?? 0} rejected</small></div>
      <div><span>AUTOMATION FRESHNESS</span><strong>n/a</strong><small>not exposed by P7</small></div>
    </div>
    <div className="growth-chart-grid">
      <article><h4>Evidence throughput</h4><GrowthChart option={sourceOption} label="Evidence throughput trend" empty={!sourceSeries.length} emptyText="No source throughput observations in this range." /></article>
      <article><h4>Evaluation score</h4><GrowthChart option={evaluationOption} label="Evaluation score trend" empty={!evaluationSeries.length} emptyText="No evaluation observations in this range." /></article>
      <article><h4>Proposal outcomes</h4><GrowthChart option={proposalOption} label="Proposal outcome trend" empty={!proposalSeries.length || !proposalStatuses.length} emptyText="No proposal outcomes in this range." /></article>
      <article><h4>Current quality debt</h4><GrowthChart option={debtOption} label="Current knowledge quality debt" empty={!debtValues.some((value) => value > 0)} emptyText="No persisted quality debt is currently reported." /></article>
    </div>
    <div className="growth-trends__footnote"><Clock3 size={13} /><span>Series are capped at 120 persisted points in the browser. Missing metrics remain unavailable.</span></div>
  </section>;
}
