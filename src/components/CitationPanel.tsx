import { BookOpenCheck, CircleAlert, Link2 } from 'lucide-react';
import type { DashboardData } from '../api/compilerDashboardApi';

function asPercent(value: number | undefined): number {
  const raw = value ?? 0;
  return Math.max(0, Math.min(100, raw <= 1 ? raw * 100 : raw));
}

function refsFor(step: Record<string, unknown>): string[] {
  const refs = step.source_ref;
  return Array.isArray(refs) ? refs.filter((ref): ref is string => typeof ref === 'string') : [];
}

export function CitationPanel({ sop }: { sop: DashboardData['sop'] }) {
  const coverage = sop?._citation_coverage;
  const pct = asPercent(coverage?.coverage);
  const steps = sop?.sops ?? [];
  const cited = steps.filter((step: Record<string, unknown>) => refsFor(step).length > 0).length;
  const total = coverage?.total ?? steps.length;
  const covered = coverage?.covered ?? cited;
  const missing = Math.max(0, total - covered);

  return (
    <section className="insight-panel citation-panel" data-tone={pct >= 80 ? 'healthy' : pct >= 50 ? 'review' : 'blocked'} aria-label="证据与引用">
      <header className="insight-panel__header">
        <div>
          <p className="insight-kicker">SOURCE TRACEABILITY</p>
          <h3>证据与引用</h3>
        </div>
        <span className="insight-status"><BookOpenCheck size={14} />{covered}/{total || '—'} 已链接</span>
      </header>

      <div className="citation-meter">
        <div className="citation-meter__numbers"><strong>{pct}%</strong><span>结论带来源</span></div>
        <div className="citation-meter__track" aria-label={`引用覆盖率 ${pct}%`}><i style={{ width: `${pct}%` }} /></div>
      </div>

      {missing > 0 && (
        <p className="citation-panel__notice"><CircleAlert size={14} />{missing} 项结论尚未链接外部证据，应按“待验证假设”而非既成事实处理。</p>
      )}

      <div className="citation-list">
        {steps.slice(0, 4).map((step: Record<string, unknown>, index: number) => {
          const refs = refsFor(step);
          const title = typeof step.title === 'string' ? step.title : `分析项 ${index + 1}`;
          return (
            <div className="citation-row" data-linked={refs.length > 0} key={typeof step.id === 'string' ? step.id : index}>
              <div><p>{title}</p><small>{refs.length > 0 ? '已关联来源' : '待补外部证据'}</small></div>
              {refs.length > 0 ? (
                <div className="citation-row__refs">{refs.slice(0, 2).map((ref) => <span key={ref}><Link2 size={11} />{ref}</span>)}</div>
              ) : <span className="citation-row__empty">未引用</span>}
            </div>
          );
        })}
        {steps.length === 0 && <p className="citation-panel__empty">本次运行没有可追溯的分析结论。</p>}
      </div>
    </section>
  );
}
