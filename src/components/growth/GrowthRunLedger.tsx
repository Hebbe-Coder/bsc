import { AlertTriangle, CheckCircle2, Clock3, Cpu, FileOutput, FileSearch, ListTree, LoaderCircle, PlayCircle, RefreshCw } from 'lucide-react';

import type { GrowthCaptureAttempt, GrowthFailure, GrowthRequestState, GrowthRun, GrowthRunEvent } from '../../api/growthApi';

type Props = {
  runs: GrowthRun[];
  selectedRunId: string;
  events: GrowthRunEvent[];
  captureAttempts: GrowthCaptureAttempt[];
  failures: GrowthFailure[];
  state: GrowthRequestState;
  error?: string;
  canWrite: boolean;
  busy: boolean;
  onSelect: (runId: string) => void;
  onResolveFailure: (failure: GrowthFailure) => void;
  onRetry: () => void;
};

type Reference = { kind: string; value: string };
type ModelExecution = {
  id: string;
  promptRunId: string;
  manifestFingerprint: string;
  task: string;
  revision: string;
  provider: string;
  model: string;
  usage: Record<string, unknown>;
  attemptCount: number;
  retryCount: number;
  retryCategories: string[];
};

function recordReferences(value: unknown, hint = '', depth = 0): Reference[] {
  if (depth > 4 || value === null || value === undefined) return [];
  if (typeof value === 'string' || typeof value === 'number') {
    return hint ? [{ kind: hint, value: String(value) }] : [];
  }
  if (Array.isArray(value)) return value.flatMap((item) => recordReferences(item, hint, depth + 1));
  if (typeof value !== 'object') return [];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
    const normalized = key.toLowerCase();
    const kind = /(source|proposal|output|method|page|artifact)/.test(normalized) ? key.replace(/_ids?$/, '') : hint;
    return recordReferences(item, kind, depth + 1);
  });
}

function boundedJson(value: unknown): string {
  try {
    const rendered = JSON.stringify(value, null, 2);
    return rendered.length > 1_600 ? `${rendered.slice(0, 1_600)}\n[TRUNCATED]` : rendered;
  } catch {
    return 'Structured details unavailable';
  }
}

function statusLabel(value: unknown): string {
  return String(value || 'recorded').replace(/_/g, ' ');
}

function modelExecutions(events: GrowthRunEvent[]): ModelExecution[] {
  return events.flatMap((event) => {
    if (event.event_type !== 'knowledge.growth.model.completed' || !event.payload) return [];
    const usage = event.payload.usage;
    return [{
      id: event.id,
      promptRunId: String(event.payload.prompt_run_id || ''),
      manifestFingerprint: String(event.payload.agent_manifest_fingerprint || ''),
      task: String(event.payload.task || ''),
      revision: String(event.payload.revision || ''),
      provider: String(event.payload.provider || ''),
      model: String(event.payload.model || ''),
      usage: usage && typeof usage === 'object' && !Array.isArray(usage) ? usage as Record<string, unknown> : {},
      attemptCount: typeof event.payload.attempt_count === 'number' ? event.payload.attempt_count : 1,
      retryCount: typeof event.payload.retry_count === 'number' ? event.payload.retry_count : 0,
      retryCategories: Array.isArray(event.payload.retry_categories) ? event.payload.retry_categories.filter((value): value is string => typeof value === 'string') : [],
    }];
  });
}

function usageValue(value: unknown, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}${suffix}` : 'not reported';
}

export function GrowthRunLedger({
  runs, selectedRunId, events, captureAttempts, failures, state, error, canWrite, busy, onSelect, onResolveFailure, onRetry,
}: Props) {
  const selected = runs.find((run) => run.id === selectedRunId) ?? null;
  const inputRefs = recordReferences(selected?.input_refs);
  const outputRefs = recordReferences(selected?.output_refs);
  const executions = modelExecutions(events);
  if (state === 'loading') return <div className="growth-empty growth-run-ledger__empty" role="status"><LoaderCircle className="spin" size={18} /><span>Loading the durable run ledger...</span></div>;
  if (state === 'permission' || state === 'offline' || state === 'unavailable' || state === 'error') return <div className="growth-empty growth-run-ledger__empty" role="alert"><AlertTriangle size={18} /><span>{error || 'Run ledger is unavailable. No simulated activity is shown.'}</span><button type="button" onClick={onRetry}><RefreshCw size={14} />Retry</button></div>;
  if (!runs.length) return <div className="growth-empty growth-run-ledger__empty"><PlayCircle size={18} /><span>No durable growth run exists for this project yet.</span></div>;

  return <div className="growth-run-ledger">
    <nav className="growth-run-ledger__runs" aria-label="Growth runs">
      {runs.map((run) => <button
        key={run.id}
        type="button"
        className={run.id === selectedRunId ? 'is-active' : ''}
        aria-pressed={run.id === selectedRunId}
        onClick={() => onSelect(run.id)}
      ><span><Clock3 size={14} />{String(run.run_type || 'growth run')}</span><strong>{statusLabel(run.status)}</strong><small>{String(run.created_at || run.id)}</small></button>)}
    </nav>
    {selected && <section className="growth-run-ledger__detail" aria-label="Selected run audit ledger">
      <header><div><p>RUN AUDIT</p><h4>{String(selected.run_type || 'Growth run')}</h4></div><span>{statusLabel(selected.status)}</span></header>
      <div className="growth-run-ledger__refs">
        <section><h5><ListTree size={13} />Input plan</h5><pre>{boundedJson(selected.input_refs || {})}</pre>{inputRefs.length > 0 && <ul>{inputRefs.slice(0, 24).map((item, index) => <li key={`${item.kind}-${item.value}-${index}`}><b>{item.kind}</b>{item.value}</li>)}</ul>}</section>
        <section><h5><FileOutput size={13} />Outputs and references</h5><pre>{boundedJson(selected.output_refs || {})}</pre>{outputRefs.length > 0 && <ul>{outputRefs.slice(0, 24).map((item, index) => <li key={`${item.kind}-${item.value}-${index}`}><b>{item.kind}</b>{item.value}</li>)}</ul>}</section>
      </div>
      <section className="growth-run-ledger__models"><h5><Cpu size={13} />Model execution</h5>{executions.length ? <ul>{executions.map((execution) => <li key={execution.id}><header><strong>{execution.provider || 'provider'} / {execution.model || 'model not recorded'}</strong><span>{execution.usage.complete === true ? 'usage complete' : 'usage incomplete'}</span></header><small>{execution.task || 'governed task'}{execution.revision ? ` / ${execution.revision}` : ''}{execution.retryCount ? ` / ${execution.retryCount} retry ${execution.retryCount === 1 ? 'attempt' : 'attempts'}${execution.retryCategories.length ? `: ${execution.retryCategories.join(', ').replace(/_/g, ' ')}` : ''}` : ''}</small><dl><div><dt>Calls</dt><dd>{usageValue(execution.usage.provider_calls)}</dd></div><div><dt>Attempts</dt><dd>{execution.attemptCount}</dd></div><div><dt>Total tokens</dt><dd>{usageValue(execution.usage.total_tokens, ' total tokens')}</dd></div><div><dt>Reasoning</dt><dd>{usageValue(execution.usage.reasoning_tokens)}</dd></div><div><dt>Latency</dt><dd>{usageValue(execution.usage.latency_ms, ' ms')}</dd></div></dl><footer><code title={execution.promptRunId}>run {execution.promptRunId || 'not recorded'}</code><code title={execution.manifestFingerprint}>manifest {execution.manifestFingerprint ? execution.manifestFingerprint.slice(0, 16) : 'not recorded'}</code></footer></li>)}</ul> : <p>No governed model invocation was persisted for this run.</p>}</section>
      <section className="growth-run-ledger__captures"><h5><FileSearch size={13} />Source capture ledger</h5>{captureAttempts.length ? <ul>{captureAttempts.map((attempt) => <li key={attempt.id}><div><strong>{statusLabel(attempt.outcome)}</strong><span>{String(attempt.source_type || 'source')} / {String(attempt.origin || attempt.source_id || 'origin not recorded')}</span><small>{String(attempt.created_at || 'timestamp not recorded')}{attempt.content_hash ? ` / ${attempt.content_hash.slice(0, 12)}` : ''}</small><pre>{boundedJson({ policy: attempt.policy || {}, projection: attempt.projection || {} })}</pre></div></li>)}</ul> : <p>No persisted source capture attempt is linked to this run.</p>}</section>
      <section className="growth-run-ledger__timeline"><h5><Clock3 size={13} />Event timeline</h5>{events.length ? <ol>{events.map((event) => <li key={`${event.id}-${event.sequence}`}><span>{event.sequence}</span><div><strong>{event.event_type}</strong><time>{String(event.created_at || 'timestamp not recorded')}</time>{event.payload && <pre>{boundedJson(event.payload)}</pre>}</div></li>)}</ol> : <p>No persisted events were recorded for this run.</p>}</section>
      <section className="growth-run-ledger__failures"><h5><AlertTriangle size={13} />Failures</h5>{failures.length ? <ul>{failures.map((failure) => <li key={failure.id}><div><strong>{failure.diagnostic_pattern || 'UNCLASSIFIED'} / {failure.code}</strong><span>{failure.summary}</span><small>{failure.severity} / {statusLabel(failure.status)}{failure.event_sequence ? ` / event ${failure.event_sequence}` : ''}{failure.secondary_diagnostic_patterns?.length ? ` / related ${failure.secondary_diagnostic_patterns.join(', ')}` : ''}</small>{failure.minimal_structural_fix ? <p>Structural fix: {failure.minimal_structural_fix}</p> : null}</div>{failure.status !== 'resolved' && <button type="button" disabled={!canWrite || busy} title={canWrite ? 'Mark this failure resolved after an auditable remediation.' : 'Read-only project role'} onClick={() => onResolveFailure(failure)}><CheckCircle2 size={14} />Resolve</button>}</li>)}</ul> : <p>No persisted failure record is linked to this run.</p>}</section>
    </section>}
  </div>;
}
