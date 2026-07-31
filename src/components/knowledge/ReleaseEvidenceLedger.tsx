import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from 'lucide-react';

import {
  fetchKnowledgeReleaseEvidence,
  submitKnowledgeReleaseEvidence,
  verifyKnowledgeReleaseEvidence,
  type KnowledgeReleaseEvidence,
  type KnowledgeReleaseEvidenceInput,
} from '../../api/knowledgeWorkspaceApi';

type Props = {
  projectId: string;
  role: string;
  canWrite: boolean;
  onChanged?: () => void | Promise<void>;
};

const EVIDENCE_CATEGORIES = [
  'o1_secure_boundary_restart',
  'o2_metadata_views',
  'o3_real_plugin_exports',
  'o4_extraction_reference',
  'o5_visualization_inspection',
  'o6_feedback_cycle',
  'compose_recovery',
  'authorization_isolation',
  'browser_desktop_mobile',
] as const;

const OBSERVATION_STATES: Array<KnowledgeReleaseEvidence['state']> = ['pending', 'unavailable', 'failed'];

function durableIds(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
}

function replaceEvidence(records: KnowledgeReleaseEvidence[], next: KnowledgeReleaseEvidence): KnowledgeReleaseEvidence[] {
  const remaining = records.filter((item) => item.evidence_id !== next.evidence_id);
  return [...remaining, next].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));
}

export function ReleaseEvidenceLedger({ projectId, role, canWrite, onChanged }: Props) {
  const [evidence, setEvidence] = useState<KnowledgeReleaseEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [evidenceId, setEvidenceId] = useState<string>(EVIDENCE_CATEGORIES[0]);
  const [observationState, setObservationState] = useState<KnowledgeReleaseEvidence['state']>('pending');
  const [detailCode, setDetailCode] = useState('awaiting_observation');
  const [reviewEvidenceId, setReviewEvidenceId] = useState('');
  const [observedAt, setObservedAt] = useState('');
  const [reviewDurableIds, setReviewDurableIds] = useState('');
  const [reviewDetailCode, setReviewDetailCode] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetchKnowledgeReleaseEvidence(projectId);
      setEvidence(response.evidence);
      setReviewEvidenceId((current) => current || response.evidence[0]?.evidence_id || '');
    } catch (reason) {
      setEvidence([]);
      setError(reason instanceof Error ? reason.message : 'Release evidence could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { void load(); }, [load]);

  const notifyChanged = async () => {
    await onChanged?.();
  };

  const recordObservation = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canWrite || saving || !detailCode.trim()) return;
    const payload: KnowledgeReleaseEvidenceInput = {
      evidence_id: evidenceId,
      state: observationState,
      proof_class: 'none',
      observed_at: '',
      durable_ids: [],
      detail_code: detailCode.trim(),
    };
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await submitKnowledgeReleaseEvidence(projectId, payload);
      setEvidence((current) => replaceEvidence(current, response.evidence));
      setReviewEvidenceId(response.evidence.evidence_id);
      setMessage('Observation recorded. Release status remains derived from reviewed evidence.');
      await notifyChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Observation could not be recorded.');
    } finally {
      setSaving(false);
    }
  };

  const selectedReview = evidence.find((item) => item.evidence_id === reviewEvidenceId) || null;
  const reviewedDurableIds = durableIds(reviewDurableIds);
  const canVerify = role === 'admin'
    && canWrite
    && Boolean(selectedReview)
    && Boolean(observedAt.trim())
    && reviewedDurableIds.length > 0
    && Boolean(reviewDetailCode.trim())
    && !saving;

  const verifyProof = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedReview || !canVerify) return;
    const payload: KnowledgeReleaseEvidenceInput = {
      evidence_id: selectedReview.evidence_id,
      state: 'verified',
      proof_class: 'real',
      observed_at: observedAt.trim(),
      durable_ids: reviewedDurableIds,
      detail_code: reviewDetailCode.trim(),
    };
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await verifyKnowledgeReleaseEvidence(projectId, selectedReview.evidence_id, payload);
      setEvidence((current) => replaceEvidence(current, response.evidence));
      setMessage('Administrator review recorded. The release gate will recompute from the full evidence matrix.');
      await notifyChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Real-proof review could not be recorded.');
    } finally {
      setSaving(false);
    }
  };

  return <section className="knowledge-release-ledger" aria-label="Release evidence ledger">
    <header>
      <div><span className="eyebrow">RELEASE EVIDENCE</span><h3>Auditable proof ledger</h3><p>Only bounded IDs and review metadata are retained. Release state is computed, never edited here.</p></div>
      <button className="icon-button" type="button" aria-label="Refresh release evidence" title="Refresh release evidence" onClick={() => void load()} disabled={loading || saving}><RefreshCw size={14} className={loading ? 'spin' : ''} /></button>
    </header>
    {error && <p className="knowledge-release-ledger__message is-error" role="alert">{error}</p>}
    {message && <p className="knowledge-release-ledger__message" role="status">{message}</p>}
    <div className="knowledge-release-ledger__rows" role="list">
      {loading && <p className="knowledge-empty">Loading release evidence...</p>}
      {!loading && evidence.length === 0 && <p className="knowledge-empty">No release evidence has been recorded for this project.</p>}
      {evidence.map((item) => <article key={item.evidence_id} role="listitem">
        <header><strong>{item.evidence_id}</strong><span className={`source-status source-status--${item.state}`}>{item.state}</span></header>
        <dl>
          <div><dt>Proof</dt><dd>{item.proof_class}</dd></div>
          <div><dt>Revision</dt><dd>{item.revision}</dd></div>
          <div><dt>Actor</dt><dd>{item.recorded_by || 'unrecorded'}</dd></div>
          <div><dt>Observed</dt><dd>{item.observed_at || 'not verified'}</dd></div>
          <div><dt>Durable IDs</dt><dd>{item.durable_ids.length ? item.durable_ids.join(', ') : 'none'}</dd></div>
          <div><dt>Detail</dt><dd>{item.detail_code || 'none'}</dd></div>
        </dl>
      </article>)}
    </div>
    {canWrite && <form className="knowledge-release-ledger__form" onSubmit={recordObservation}>
      <h4><AlertTriangle size={14} /> Record observation</h4>
      <label>Evidence category<select aria-label="Evidence category" value={evidenceId} onChange={(event) => setEvidenceId(event.target.value)} disabled={saving}>{EVIDENCE_CATEGORIES.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      <label>Observation status<select aria-label="Observation status" value={observationState} onChange={(event) => setObservationState(event.target.value as KnowledgeReleaseEvidence['state'])} disabled={saving}>{OBSERVATION_STATES.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      <label>Detail code<input aria-label="Detail code" value={detailCode} maxLength={128} onChange={(event) => setDetailCode(event.target.value)} disabled={saving} /></label>
      <button type="submit" disabled={saving || !detailCode.trim()}><AlertTriangle size={14} /> Record observation</button>
    </form>}
    {role === 'admin' && canWrite && <form className="knowledge-release-ledger__form knowledge-release-ledger__form--review" onSubmit={verifyProof}>
      <h4><ShieldCheck size={14} /> Administrator review</h4>
      <label>Evidence category<select aria-label="Review evidence category" value={reviewEvidenceId} onChange={(event) => setReviewEvidenceId(event.target.value)} disabled={saving || evidence.length === 0}><option value="" disabled>Select submitted evidence</option>{evidence.map((item) => <option value={item.evidence_id} key={item.evidence_id}>{item.evidence_id}</option>)}</select></label>
      <label>Observed at<input aria-label="Observed at" value={observedAt} placeholder="2026-08-01T00:00:00+00:00" maxLength={64} onChange={(event) => setObservedAt(event.target.value)} disabled={saving} /></label>
      <label>Durable evidence IDs<input aria-label="Durable evidence IDs" value={reviewDurableIds} placeholder="run:example-1, browser:check-1" maxLength={256} onChange={(event) => setReviewDurableIds(event.target.value)} disabled={saving} /></label>
      <label>Review detail code<input aria-label="Review detail code" value={reviewDetailCode} maxLength={128} onChange={(event) => setReviewDetailCode(event.target.value)} disabled={saving} /></label>
      <button type="submit" disabled={!canVerify}><CheckCircle2 size={14} /> Verify real proof</button>
    </form>}
  </section>;
}
