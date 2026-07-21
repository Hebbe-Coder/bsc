import { ArrowUpRight, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { CSSProperties } from 'react';
import type { RiskPayload } from '../api/compilerDashboardApi';

function toneForCoverage(pct: number): 'healthy' | 'review' | 'blocked' {
  if (pct >= 80) return 'healthy';
  if (pct >= 60) return 'review';
  return 'blocked';
}

function readableId(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function ConstraintCoveragePanel({ coverage }: { coverage: RiskPayload['coverage'] }) {
  const pct = Math.max(0, Math.min(100, coverage?.coverage_pct ?? 0));
  const total = coverage?.total ?? 0;
  const covered = coverage?.covered ?? 0;
  const uncovered = coverage?.uncovered_ids ?? [];
  const tone = toneForCoverage(pct);
  const remaining = Math.max(0, total - covered);

  return (
    <section className="insight-panel coverage-panel" data-tone={tone} aria-label="约束覆盖">
      <header className="insight-panel__header">
        <div>
          <p className="insight-kicker">DECISION EVIDENCE</p>
          <h3>约束覆盖</h3>
        </div>
        <span className="insight-status">
          {tone === 'healthy' ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
          {tone === 'healthy' ? '证据充足' : tone === 'review' ? '需要复核' : '证据不足'}
        </span>
      </header>

      <div className="coverage-panel__body">
        <div className="coverage-ring" style={{ '--coverage': `${pct}%` } as CSSProperties}>
          <div><strong>{pct}%</strong><span>已覆盖</span></div>
        </div>
        <div className="coverage-panel__summary">
          <p><strong>{covered}</strong> / {total || '—'} 项约束已有对应证据或控制措施</p>
          <div className="coverage-bar" aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>
          <small>{remaining === 0 ? '当前没有待补的约束。' : `还有 ${remaining} 项关键约束需要补证。`}</small>
        </div>
      </div>

      {uncovered.length > 0 && (
        <div className="coverage-panel__gaps">
          <div><p>优先补证</p><span>{uncovered.length} 项未覆盖</span></div>
          <ul>
            {uncovered.slice(0, 5).map((id) => <li key={id}><ArrowUpRight size={12} />{readableId(id)}</li>)}
          </ul>
          {uncovered.length > 5 && <small>另有 {uncovered.length - 5} 项待处理</small>}
        </div>
      )}
    </section>
  );
}
