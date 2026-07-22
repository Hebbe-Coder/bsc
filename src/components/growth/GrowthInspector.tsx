import { AlertTriangle, CheckCircle2, ExternalLink, KeyRound, Link2, LoaderCircle, Network, ShieldAlert, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import type {
  GrowthAssetDetail,
  GrowthFeedbackInput,
  GrowthLineageEdge,
  GrowthRecord,
  GrowthRequestState,
} from '../../api/growthApi';
import { growthRecordLabel, growthRecordTimestamp } from './growthModel';

type Props = {
  selected: GrowthRecord | null;
  detail: GrowthAssetDetail | null;
  state: GrowthRequestState;
  error?: string;
  edges: GrowthLineageEdge[];
  canWrite: boolean | null;
  compact: boolean;
  open: boolean;
  actionState: GrowthRequestState;
  actionMessage?: string;
  onClose: () => void;
  onAction: (detail: GrowthAssetDetail) => void;
  onFeedback: (detail: GrowthAssetDetail, payload: GrowthFeedbackInput) => void;
  onFollow: (id: string, type?: string) => void;
};

const hiddenFields = new Set(['raw_content', 'content', 'content_base64', 'body', 'operations', 'active_revision']);

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try { return JSON.stringify(value); } catch { return 'Structured value unavailable'; }
}

function metadataRows(record: GrowthRecord): Array<[string, string]> {
  const priority = ['id', 'project_id', 'status', 'source_type', 'origin', 'path', 'vault_path', 'trust_level', 'content_hash', 'active_revision_id', 'method_revision_id', 'context_revision', 'run_id', 'created_at', 'updated_at'];
  const entries = Object.entries(record).filter(([key]) => !hiddenFields.has(key));
  entries.sort(([left], [right]) => {
    const leftIndex = priority.indexOf(left);
    const rightIndex = priority.indexOf(right);
    return (leftIndex < 0 ? 100 : leftIndex) - (rightIndex < 0 ? 100 : rightIndex);
  });
  return entries.slice(0, 20).map(([key, value]) => [key, displayValue(value)]);
}

function actionLabel(detail: GrowthAssetDetail): string {
  if (detail.kind === 'source') return 'Run evidence triage';
  if (detail.kind === 'feedback' && String(detail.record.status || '') === 'pending') return 'Process feedback';
  if (detail.kind === 'output' && String(detail.record.status || '') === 'accepted') return 'File accepted output';
  return '';
}

function DetailState({ state, error }: { state: GrowthRequestState; error?: string }) {
  if (state === 'loading') return <div className="growth-empty growth-empty--inspector" role="status"><LoaderCircle className="spin" size={20} /><span>Loading the persisted asset detail...</span></div>;
  if (state === 'permission') return <div className="growth-empty growth-empty--inspector" role="alert"><ShieldAlert size={20} /><span>Detail access was denied for this project key.</span></div>;
  if (state === 'offline') return <div className="growth-empty growth-empty--inspector" role="alert"><AlertTriangle size={20} /><span>Detail is offline. Stale detail is not displayed.</span></div>;
  if (state === 'unavailable' || state === 'error') return <div className="growth-empty growth-empty--inspector" role="alert"><AlertTriangle size={20} /><span>{error || 'Asset detail is unavailable.'}</span></div>;
  return null;
}

export function GrowthInspector(props: Props) {
  const {
    selected, detail, state, error, edges, canWrite, compact, open, actionState, actionMessage,
    onClose, onAction, onFeedback, onFollow,
  } = props;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [feedbackType, setFeedbackType] = useState<GrowthFeedbackInput['feedback_type']>('accepted');
  const [feedbackText, setFeedbackText] = useState('');
  const [rating, setRating] = useState(90);
  const relatedIds = useMemo(() => new Set([
    selected?.id,
    typeof detail?.record.active_revision_id === 'string' ? detail.record.active_revision_id : '',
  ].filter(Boolean)), [detail?.record.active_revision_id, selected?.id]);
  const related = useMemo(() => edges.filter((edge) => relatedIds.has(edge.from_id) || relatedIds.has(edge.to_id)), [edges, relatedIds]);

  useEffect(() => {
    if (!compact || !open) return undefined;
    headingRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [compact, onClose, open]);
  useEffect(() => {
    setFeedbackType('accepted'); setFeedbackText(''); setRating(90);
  }, [selected?.id]);

  if (compact && !open) return null;
  const label = selected ? growthRecordLabel(selected) : 'Select an asset';
  const command = detail ? actionLabel(detail) : '';
  const actionDisabled = actionState === 'loading' || canWrite !== true;
  const permissionMessage = canWrite === false ? 'Read-only project role' : canWrite === null ? 'Write permission unavailable' : '';

  return <aside
    className={`growth-inspector${compact ? ' growth-inspector--drawer' : ''}`}
    aria-label="Growth inspector"
    role={compact ? 'dialog' : undefined}
    aria-modal={compact ? true : undefined}
  >
    <header className="growth-inspector__header">
      <div><p>INSPECTOR</p><h3 ref={headingRef} tabIndex={-1}>{label}</h3></div>
      {compact && <button type="button" className="growth-icon-button" aria-label="Close inspector" title="Close inspector" onClick={onClose}><X size={17} /></button>}
    </header>
    {!selected && <div className="growth-empty growth-empty--inspector"><Network size={22} /><span>Select evidence, knowledge, a method, output or review record to inspect provenance and permitted actions.</span></div>}
    {selected && <>
      <DetailState state={state} error={error} />
      {detail && state === 'success' && <>
        <div className="growth-inspector__status-row"><span className="growth-inspector__badge">{String(detail.record.status || 'recorded')}</span><time>{growthRecordTimestamp(detail.record)}</time></div>
        {detail.detailMessage && <div className="growth-inspector__availability"><AlertTriangle size={14} /><span>{detail.detailMessage}</span></div>}
        <dl>{metadataRows(detail.record).map(([key, value]) => <div key={key}><dt>{key.split('_').join(' ')}</dt><dd title={value}>{value}</dd></div>)}</dl>
        {detail.citations && <section className="growth-inspector__section"><h4><Link2 size={13} /> Citations</h4>{detail.citations.length ? detail.citations.map((citation, index) => {
          const sourceId = String(citation.source_id || '');
          return <button key={`${sourceId}-${index}`} type="button" disabled={!sourceId} onClick={() => onFollow(sourceId, 'source')}><span>{String(citation.claim_text || citation.anchor || sourceId)}</span><ExternalLink size={12} /></button>;
        }) : <p>No persisted citations are attached to this page.</p>}</section>}
        <section className="growth-inspector__section"><h4><Network size={13} /> Lineage</h4>{related.length ? related.slice(0, 12).map((edge) => {
          const outgoing = relatedIds.has(edge.from_id);
          const target = outgoing ? edge.to_id : edge.from_id;
          const type = outgoing ? edge.to_type : edge.from_type;
          return <button key={edge.id} type="button" onClick={() => onFollow(target, type)}><span><b>{edge.edge_type}</b>{target}</span><ExternalLink size={12} /></button>;
        }) : <p>No relationship in the current bounded graph slice.</p>}</section>
        {command ? <div className="growth-inspector__actions">
          <button type="button" disabled={actionDisabled} title={permissionMessage || command} onClick={() => onAction(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <CheckCircle2 size={14} /> : <KeyRound size={14} />}{command}</button>
          {permissionMessage && <small>{permissionMessage}. The API remains authoritative.</small>}
        </div> : <div className="growth-inspector__notice">No write action is exposed for this asset type by the current Growth API.</div>}
        {detail.kind === 'output' && <form className="growth-feedback-form" onSubmit={(event) => {
          event.preventDefault();
          const payload: GrowthFeedbackInput = { feedback_type: feedbackType };
          if (feedbackType === 'rated') payload.rating = rating;
          else if (feedbackType === 'corrected') payload.correction = feedbackText.trim();
          else payload.comment = feedbackText.trim();
          onFeedback(detail, payload);
        }}>
          <h4>Record feedback</h4>
          <label><span>Outcome</span><select aria-label="Output feedback type" value={feedbackType} onChange={(event) => setFeedbackType(event.target.value as GrowthFeedbackInput['feedback_type'])}><option value="accepted">Accepted</option><option value="rejected">Rejected</option><option value="corrected">Corrected</option><option value="rated">Rated</option><option value="reused">Reused</option></select></label>
          {feedbackType === 'rated' ? <label><span>Rating</span><input aria-label="Output feedback rating" type="number" min="0" max="100" value={rating} onChange={(event) => setRating(Number(event.target.value))} /></label> : <label><span>{feedbackType === 'corrected' ? 'Correction' : 'Comment'}</span><textarea aria-label="Output feedback text" value={feedbackText} required={feedbackType === 'corrected'} onChange={(event) => setFeedbackText(event.target.value)} /></label>}
          <button type="submit" disabled={actionDisabled} title={permissionMessage || 'Persist output feedback'}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <CheckCircle2 size={14} /> : <KeyRound size={14} />}Submit feedback</button>
        </form>}
        {actionMessage && <div className={`growth-action-message${actionState === 'error' || actionState === 'permission' ? ' is-error' : ''}`} role="status">{actionMessage}</div>}
      </>}
    </>}
  </aside>;
}
