import { Fingerprint, Link2, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { AuditEntry, TrustedAudit } from '../api/compilerDashboardApi';

const GATE_LABEL: Record<string, string> = { pass: '通过', review: '复核', warn: '警告', block: '阻断' };

function shortHash(hash: string): string {
  return hash.length > 22 ? `${hash.slice(0, 12)}…${hash.slice(-8)}` : hash || '—';
}

function timeLabel(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp || '未记录时间';
  return date.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
}

function ChainEvent({ entry }: { entry: AuditEntry }) {
  return (
    <li className="audit-event">
      <span className="audit-event__node" aria-hidden="true" />
      <div>
        <p><b>#{entry.seq + 1}</b>{entry.agent} <span>/</span> {entry.action}</p>
        <code title={entry.hash}>{shortHash(entry.hash)}</code>
      </div>
      <time>{timeLabel(entry.timestamp)}</time>
    </li>
  );
}

export function TrustedAuditPanel({ trustedAudit }: { trustedAudit: TrustedAudit }) {
  const verified = trustedAudit?.verified ?? false;
  const coverage = trustedAudit?.coverage;
  const gate = coverage?.gate_decision ?? 'review';
  const refs = trustedAudit?.source_refs ?? [];
  const audit = trustedAudit?.audit ?? [];
  const pct = coverage?.coverage_pct ?? 0;

  return (
    <section className="insight-panel audit-panel" data-verified={verified} aria-label="可信审计链">
      <header className="insight-panel__header">
        <div>
          <p className="insight-kicker">TAMPER-EVIDENT TRACE</p>
          <h3>可信审计链</h3>
        </div>
        <span className="insight-status">{verified ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}{verified ? '完整性已验证' : '完整性异常'}</span>
      </header>

      <div className="audit-metrics">
        <div><span>链头哈希</span><code title={trustedAudit?.chain_hash}>{shortHash(trustedAudit?.chain_hash ?? '')}</code></div>
        <div><span>决策门禁</span><strong data-gate={gate}>{GATE_LABEL[gate] ?? gate}</strong><small>{pct == null ? '未计算覆盖率' : `${pct}% 约束已覆盖`}</small></div>
        <div><span>关联工件</span><strong>{refs.length}</strong><small>可回溯的输出证据</small></div>
      </div>

      {refs.length > 0 && (
        <div className="audit-evidence">
          <p><Link2 size={13} />审计证据</p>
          <div>{refs.slice(0, 6).map((ref) => <code key={ref}>{ref}</code>)}{refs.length > 6 && <span>+{refs.length - 6}</span>}</div>
        </div>
      )}

      <div className="audit-timeline">
        <p><Fingerprint size={13} />审计事件 <span>{audit.length} 个节点</span></p>
        {audit.length > 0 ? <ol>{audit.map((entry) => <ChainEvent key={entry.seq} entry={entry} />)}</ol> : <small>本次运行没有审计事件。</small>}
      </div>
    </section>
  );
}
