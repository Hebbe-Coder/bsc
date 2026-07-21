import { useState } from 'react';
import { ArrowUpRight, CheckCircle2, CircleAlert, Gauge, Layers3 } from 'lucide-react';
import type { Evaluation, QualityDimension, RiskPayload } from '../api/compilerDashboardApi';

type Tone = 'ready' | 'review' | 'blocked';

function scoreTone(score: number): Tone {
  if (score >= 80) return 'ready';
  if (score >= 60) return 'review';
  return 'blocked';
}

function severityFor(dim: QualityDimension): string {
  const match = dim.details.match(/Severity:\s*([a-z]+)/i);
  return match?.[1]?.toLowerCase() ?? (dim.score <= 20 ? 'critical' : dim.score <= 40 ? 'high' : 'medium');
}

function labelForTone(tone: Tone): string {
  return tone === 'ready' ? '可进入决策' : tone === 'review' ? '需要复核' : '不建议推进';
}

function actionText(value: string): string {
  return value.replace(/^Address gap:\s*/i, '');
}

function IssueRow({ dimension }: { dimension: QualityDimension }) {
  const severity = severityFor(dimension);
  return (
    <div className="readiness-issue" data-severity={severity}>
      <span>{severity}</span>
      <div><strong>{dimension.name.replace(/_/g, ' ')}</strong><p>{dimension.feedback}</p></div>
      <ArrowUpRight size={14} aria-hidden="true" />
    </div>
  );
}

export function CompilerEvalPanel({ evaluation, coverage }: { evaluation?: Evaluation | null; coverage?: RiskPayload['coverage'] }) {
  const [showAll, setShowAll] = useState(false);
  if (!evaluation) return null;

  const score = Math.max(0, Math.min(100, evaluation.overall_score));
  const tone = scoreTone(score);
  const dimensions = [...(evaluation.dimensions ?? [])].sort((a, b) => a.score - b.score);
  const criticalCount = dimensions.filter((dimension) => severityFor(dimension) === 'critical').length;
  const shownIssues = showAll ? dimensions : dimensions.slice(0, 4);
  const circumference = 2 * Math.PI * 42;
  const dashOffset = circumference - (circumference * score) / 100;
  const actions = (evaluation.suggestions ?? []).slice(0, 3);

  return (
    <section className="insight-panel readiness-panel" data-tone={tone} aria-label="决策就绪度">
      <header className="insight-panel__header">
        <div>
          <p className="insight-kicker">GO / NO-GO SIGNAL</p>
          <h3>决策就绪度</h3>
        </div>
        <span className="insight-status">{tone === 'ready' ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}{labelForTone(tone)}</span>
      </header>

      <div className="readiness-hero">
        <div className="readiness-gauge" aria-label={`决策就绪度 ${score} 分（满分 100）`}>
          <svg viewBox="0 0 104 104" aria-hidden="true"><circle className="readiness-gauge__track" cx="52" cy="52" r="42" /><circle className="readiness-gauge__value" cx="52" cy="52" r="42" strokeDasharray={circumference} strokeDashoffset={dashOffset} /></svg>
          <div><strong>{score}</strong><span>/ 100</span></div>
        </div>
        <div className="readiness-hero__copy"><p>{labelForTone(tone)}</p><strong>{evaluation.summary}</strong><small>该分数衡量当前证据是否足以支撑下一步决策，不等同于模型输出文本质量。</small></div>
      </div>

      <div className="readiness-stats">
        <div><Gauge size={15} /><span>约束覆盖</span><strong>{coverage ? `${coverage.covered}/${coverage.total}` : '—'}</strong></div>
        <div><CircleAlert size={15} /><span>严重缺口</span><strong>{criticalCount}</strong></div>
        <div><Layers3 size={15} /><span>待补事项</span><strong>{evaluation.improvement_points}</strong></div>
      </div>

      {dimensions.length > 0 && <div className="readiness-issues"><div><p>优先处理</p><span>按影响排序</span></div>{shownIssues.map((dimension, index) => <IssueRow dimension={dimension} key={`${dimension.name}-${index}`} />)}{dimensions.length > 4 && <button type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? '收起问题列表' : `查看全部 ${dimensions.length} 项问题`}</button>}</div>}

      {actions.length > 0 && <div className="readiness-actions"><p>建议下一步</p><ol>{actions.map((action, index) => <li key={`${action}-${index}`}><b>{index + 1}</b><span>{actionText(action)}</span></li>)}</ol></div>}
    </section>
  );
}
