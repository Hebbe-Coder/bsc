import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from 'lucide-react';

import {
  fetchKnowledgeReleaseEvidence,
  submitKnowledgeReleaseEvidence,
  verifyKnowledgeReleaseEvidence,
  type KnowledgeReleaseEvidence,
  type KnowledgeReleaseEvidenceInput,
  type KnowledgeReleaseGateMatrixRow,
} from '../../api/knowledgeWorkspaceApi';

type Props = {
  projectId: string;
  role: string;
  canWrite: boolean;
  enabled?: boolean;
  matrix?: KnowledgeReleaseGateMatrixRow[];
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

type EvidenceCategory = typeof EVIDENCE_CATEGORIES[number];

type EvidenceGuidance = {
  label: string;
  requiredProof: string;
  nextAction: string;
};

const EVIDENCE_GUIDANCE: Record<EvidenceCategory, EvidenceGuidance> = {
  o1_secure_boundary_restart: {
    label: 'Secure Obsidian boundary',
    requiredProof: 'A restarted Local REST listener is protected over TLS and the plaintext listener is closed.',
    nextAction: 'Restart Obsidian and record the protected-route result for this project.',
  },
  o2_metadata_views: {
    label: 'Metadata workspace views',
    requiredProof: 'A project-scoped review confirms governed metadata fields and read-only derived indexes.',
    nextAction: 'Open the configured project in Obsidian and review its metadata workspace before submitting a run ID.',
  },
  o3_real_plugin_exports: {
    label: 'Real plugin export',
    requiredProof: 'A trusted plugin export is captured as an immutable project source with producer provenance.',
    nextAction: 'Export a real item through a configured plugin route, then run the approved Source Sync.',
  },
  o4_extraction_reference: {
    label: 'Multimodal extraction and references',
    requiredProof: 'A real extraction produces a durable anchor and a reference linked to its project source.',
    nextAction: 'After an approved Source Sync, inspect a real PDF, image, table, or canvas and record its extraction and reference IDs.',
  },
  o5_visualization_inspection: {
    label: 'Evidence visualization inspection',
    requiredProof: 'An authorized Evidence Atlas and relationship-graph inspection uses persisted project records.',
    nextAction: 'Inspect the project Evidence Atlas and graph after records exist, then record the inspected run or browser check ID.',
  },
  o6_feedback_cycle: {
    label: 'Feedback changes a later action',
    requiredProof: 'A reviewed output receives typed feedback that changes a later method, context pack, claim, or action.',
    nextAction: 'Save a real reviewed output, submit feedback, then execute and record the resulting follow-up action.',
  },
  compose_recovery: {
    label: 'Compose service recovery',
    requiredProof: 'API, worker, beat, PostgreSQL, and Redis recover with their project-scoped work intact.',
    nextAction: 'Run the controlled recovery check and record its durable run IDs after the services are healthy.',
  },
  authorization_isolation: {
    label: 'Authorization isolation',
    requiredProof: 'Tenant and project authorization deny cross-project access while allowing the selected project.',
    nextAction: 'Run the protected project and tenant isolation check, then submit only its bounded result IDs.',
  },
  browser_desktop_mobile: {
    label: 'Desktop and mobile workspace',
    requiredProof: 'The authorized workspace shows real data, charts, and graph controls without blank states or overflow.',
    nextAction: 'Inspect the selected project at desktop width and 390x844, then record the bounded browser-check IDs.',
  },
};

function evidenceLabel(evidenceId: string): string {
  const guidance = EVIDENCE_GUIDANCE[evidenceId as EvidenceCategory];
  return guidance ? `${guidance.label} (${evidenceId})` : evidenceId;
}

const OBSERVATION_STATES: Array<KnowledgeReleaseEvidence['state']> = ['pending', 'unavailable', 'failed'];

function durableIds(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
}

type LedgerRow = Omit<KnowledgeReleaseEvidence, 'state'> & {
  state: KnowledgeReleaseEvidence['state'] | 'missing';
};

function replaceEvidence(records: KnowledgeReleaseEvidence[], next: KnowledgeReleaseEvidence): KnowledgeReleaseEvidence[] {
  const remaining = records.filter((item) => item.evidence_id !== next.evidence_id);
  return [...remaining, next].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));
}

function releaseRows(evidence: KnowledgeReleaseEvidence[], matrix: KnowledgeReleaseGateMatrixRow[]): LedgerRow[] {
  const records = new Map(evidence.map((item) => [item.evidence_id, item]));
  const rows = new Map(matrix.map((item) => [item.evidence_id, {
    evidence_id: item.evidence_id,
    state: item.state,
    proof_class: item.proof_class,
    observed_at: '',
    durable_ids: [],
    detail_code: item.detail_code,
    revision: 0,
    recorded_by: '',
  } satisfies LedgerRow]));
  for (const evidenceId of EVIDENCE_CATEGORIES) {
    if (!rows.has(evidenceId)) {
      rows.set(evidenceId, {
        evidence_id: evidenceId,
        state: 'missing',
        proof_class: 'none',
        observed_at: '',
        durable_ids: [],
        detail_code: 'missing_evidence',
        revision: 0,
        recorded_by: '',
      });
    }
  }
  for (const [evidenceId, record] of records) rows.set(evidenceId, record);
  return [...rows.values()].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));
}

export function ReleaseEvidenceLedger({ projectId, role, canWrite, enabled = true, matrix = [], onChanged }: Props) {
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
      const nextEvidence = Array.isArray(response?.evidence) ? response.evidence : null;
      if (!nextEvidence) {
        setEvidence([]);
        setReviewEvidenceId('');
        setError('Release ledger response is incomplete. Required checks remain unverified.');
        return;
      }
      setEvidence(nextEvidence);
      setReviewEvidenceId((current) => current || nextEvidence[0]?.evidence_id || '');
    } catch (reason) {
      setEvidence([]);
      setError(reason instanceof Error ? reason.message : 'Release evidence could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!enabled) return;
    void load();
  }, [enabled, load]);

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
  const rows = releaseRows(evidence, matrix);
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
      <button className="icon-button" type="button" aria-label="Refresh release evidence" title="Refresh release evidence" onClick={() => void load()} disabled={!enabled || loading || saving}><RefreshCw size={14} className={loading ? 'spin' : ''} /></button>
    </header>
    {!enabled && <p className="knowledge-empty">Release evidence loads after Studio verifies access to a selected project.</p>}
    {enabled && <>
    {error && <p className="knowledge-release-ledger__message is-error" role="alert">{error}</p>}
    {message && <p className="knowledge-release-ledger__message" role="status">{message}</p>}
    <div className="knowledge-release-ledger__rows" role="list">
      {loading && <p className="knowledge-empty">Loading release evidence...</p>}
      {!loading && evidence.length === 0 && <p className="knowledge-empty">No release evidence has been recorded. Missing requirements remain visible below.</p>}
      {!loading && rows.map((item) => {
        const guidance = EVIDENCE_GUIDANCE[item.evidence_id as EvidenceCategory];
        return <article key={item.evidence_id} role="listitem" aria-label={guidance?.label || item.evidence_id}>
        <header><div><strong>{guidance?.label || item.evidence_id}</strong><code>{item.evidence_id}</code></div><span className={`source-status source-status--${item.state}`}>{item.state}</span></header>
        <dl>
          <div><dt>Proof</dt><dd>{item.proof_class}</dd></div>
          <div><dt>Revision</dt><dd>{item.revision || 'not recorded'}</dd></div>
          <div><dt>Actor</dt><dd>{item.recorded_by || 'unrecorded'}</dd></div>
          <div><dt>Observed</dt><dd>{item.observed_at || 'not verified'}</dd></div>
          <div><dt>Durable IDs</dt><dd>{item.durable_ids.length ? item.durable_ids.join(', ') : 'none'}</dd></div>
          <div><dt>Detail</dt><dd>{item.detail_code || 'none'}</dd></div>
        </dl>
        {guidance && <div className="knowledge-release-ledger__guidance">
          <p><span>Required proof</span>{guidance.requiredProof}</p>
          {item.state !== 'verified' && <p><span>Next action</span>{guidance.nextAction}</p>}
        </div>}
      </article>;
      })}
    </div>
    {canWrite && <form className="knowledge-release-ledger__form" onSubmit={recordObservation}>
      <h4><AlertTriangle size={14} /> Record observation</h4>
      <label>Evidence category<select aria-label="Evidence category" value={evidenceId} onChange={(event) => setEvidenceId(event.target.value)} disabled={saving}>{EVIDENCE_CATEGORIES.map((item) => <option value={item} key={item}>{evidenceLabel(item)}</option>)}</select></label>
      <label>Observation status<select aria-label="Observation status" value={observationState} onChange={(event) => setObservationState(event.target.value as KnowledgeReleaseEvidence['state'])} disabled={saving}>{OBSERVATION_STATES.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      <label>Detail code<input aria-label="Detail code" value={detailCode} maxLength={128} onChange={(event) => setDetailCode(event.target.value)} disabled={saving} /></label>
      <button type="submit" disabled={saving || !detailCode.trim()}><AlertTriangle size={14} /> Record observation</button>
    </form>}
    {role === 'admin' && canWrite && <form className="knowledge-release-ledger__form knowledge-release-ledger__form--review" onSubmit={verifyProof}>
      <h4><ShieldCheck size={14} /> Administrator review</h4>
      <label>Evidence category<select aria-label="Review evidence category" value={reviewEvidenceId} onChange={(event) => setReviewEvidenceId(event.target.value)} disabled={saving || evidence.length === 0}><option value="" disabled>Select submitted evidence</option>{evidence.map((item) => <option value={item.evidence_id} key={item.evidence_id}>{evidenceLabel(item.evidence_id)}</option>)}</select></label>
      <label>Observed at<input aria-label="Observed at" value={observedAt} placeholder="2026-08-01T00:00:00+00:00" maxLength={64} onChange={(event) => setObservedAt(event.target.value)} disabled={saving} /></label>
      <label>Durable evidence IDs<input aria-label="Durable evidence IDs" value={reviewDurableIds} placeholder="run:example-1, browser:check-1" maxLength={256} onChange={(event) => setReviewDurableIds(event.target.value)} disabled={saving} /></label>
      <label>Review detail code<input aria-label="Review detail code" value={reviewDetailCode} maxLength={128} onChange={(event) => setReviewDetailCode(event.target.value)} disabled={saving} /></label>
      <button type="submit" disabled={!canVerify}><CheckCircle2 size={14} /> Verify real proof</button>
    </form>}
    </>}
  </section>;
}
