import { AlertTriangle, CheckCircle2, ExternalLink, KeyRound, Link2, LoaderCircle, Network, ShieldAlert, Sparkles, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import type {
  GrowthAssetDetail,
  GrowthCandidateReviewInput,
  GrowthFeedbackInput,
  GrowthLineageEdge,
  GrowthLineageNode,
  GrowthOutputEvaluationInput,
  GrowthOutputEvidenceInput,
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
  nodes?: GrowthLineageNode[];
  canWrite: boolean | null;
  compact: boolean;
  open: boolean;
  actionState: GrowthRequestState;
  actionMessage?: string;
  evidenceSources: GrowthRecord[];
  evidenceState: GrowthRequestState;
  onClose: () => void;
  onAction: (detail: GrowthAssetDetail) => void;
  onDistillSourceMethods: (detail: GrowthAssetDetail) => void;
  onDistillAcceptedCandidate: (detail: GrowthAssetDetail) => void;
  onExtractSourceCandidates: (detail: GrowthAssetDetail) => void;
  onReviewCandidate: (detail: GrowthAssetDetail, review: GrowthCandidateReviewInput) => void;
  onEvaluate: (detail: GrowthAssetDetail, payload: GrowthOutputEvaluationInput) => void;
  onEvaluateMethod: (detail: GrowthAssetDetail) => void;
  onPublishMethod: (detail: GrowthAssetDetail) => void;
  onLinkEvidence: (detail: GrowthAssetDetail, payload: GrowthOutputEvidenceInput) => void;
  onFeedback: (detail: GrowthAssetDetail, payload: GrowthFeedbackInput) => void;
  onFollow: (id: string, type?: string) => void;
};

const hiddenFields = new Set(['raw_content', 'content', 'content_base64', 'body', 'operations', 'active_revision', 'evidence', 'claim', 'explanation', 'evolution_experiments']);

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

const evaluationFields: Array<{ key: Exclude<keyof GrowthOutputEvaluationInput, 'findings'>; label: string }> = [
  { key: 'groundedness', label: 'Groundedness' },
  { key: 'task_fit', label: 'Task fit' },
  { key: 'usefulness', label: 'Usefulness' },
  { key: 'coherence', label: 'Coherence' },
  { key: 'format_quality', label: 'Format quality' },
];

function ids(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item)) : [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function requiresEvidence(detail: GrowthAssetDetail): boolean {
  const metadata = detail.record.metadata;
  return !(metadata && typeof metadata === 'object' && (metadata as Record<string, unknown>).requires_evidence === false);
}

export function GrowthInspector(props: Props) {
  const {
    selected, detail, state, error, edges, nodes = [], canWrite, compact, open, actionState, actionMessage,
    evidenceSources, evidenceState, onClose, onAction, onDistillSourceMethods, onDistillAcceptedCandidate, onExtractSourceCandidates, onReviewCandidate, onEvaluate, onEvaluateMethod, onPublishMethod, onLinkEvidence, onFeedback, onFollow,
  } = props;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [feedbackType, setFeedbackType] = useState<GrowthFeedbackInput['feedback_type']>('accepted');
  const [feedbackText, setFeedbackText] = useState('');
  const [rating, setRating] = useState(90);
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<string[]>([]);
  const [findings, setFindings] = useState('');
  const [candidateReviewNote, setCandidateReviewNote] = useState('');
  const [scores, setScores] = useState<Omit<GrowthOutputEvaluationInput, 'findings'>>({
    groundedness: 0,
    task_fit: 0,
    usefulness: 0,
    coherence: 0,
    format_quality: 0,
  });
  const relatedIds = useMemo(() => new Set([
    selected?.id,
    typeof detail?.record.active_revision_id === 'string' ? detail.record.active_revision_id : '',
  ].filter(Boolean)), [detail?.record.active_revision_id, selected?.id]);
  const related = useMemo(() => edges.filter((edge) => relatedIds.has(edge.from_id) || relatedIds.has(edge.to_id)), [edges, relatedIds]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  useEffect(() => {
    if (!compact || !open) return undefined;
    headingRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [compact, onClose, open]);
  useEffect(() => {
    setFeedbackType('accepted'); setFeedbackText(''); setRating(90);
    setSelectedEvidenceIds(ids(detail?.evidence?.source_ids ?? detail?.record.source_refs));
    setFindings(''); setCandidateReviewNote('');
    setScores({ groundedness: 0, task_fit: 0, usefulness: 0, coherence: 0, format_quality: 0 });
  }, [detail?.evidence?.source_ids, detail?.record.source_refs, selected?.id]);

  if (compact && !open) return null;
  const label = selected ? growthRecordLabel(selected) : 'Select an asset';
  const command = detail ? actionLabel(detail) : '';
  const actionDisabled = actionState === 'loading' || canWrite !== true;
  const permissionMessage = canWrite === false ? 'Read-only project role' : canWrite === null ? 'Write permission unavailable' : '';
  const outputStatus = detail?.kind === 'output' ? String(detail.record.status || '') : '';
  const hasEvidenceReferences = detail?.kind === 'output' && ((detail.evidence?.source_ids.length ?? ids(detail.record.source_refs).length) > 0 || (detail.evidence?.page_ids.length ?? ids(detail.record.page_refs).length) > 0);
  const evidenceRequired = detail?.kind === 'output' && requiresEvidence(detail);
  const hasEvaluation = Boolean(detail?.kind === 'output' && detail.evaluations?.some((evaluation) => evaluation.status === 'completed'));
  const canAttachEvidence = detail?.kind === 'output' && outputStatus === 'registered';
  const canEvaluate = detail?.kind === 'output' && outputStatus === 'registered' && !hasEvaluation && (!evidenceRequired || hasEvidenceReferences);
  const sourceStatus = detail?.kind === 'source' ? String(detail.record.status || '') : '';
  const sourceMetadata = detail?.kind === 'source' && detail.record.metadata && typeof detail.record.metadata === 'object'
    ? detail.record.metadata as Record<string, unknown>
    : {};
  const sourceClassification = String(sourceMetadata.data_classification || 'internal').toLowerCase();
  const sourceCanDistill = detail?.kind === 'source'
    && ['eligible', 'processed'].includes(sourceStatus)
    && !['private', 'confidential'].includes(sourceClassification);
  const sourceDistillationReason = ['private', 'confidential'].includes(sourceClassification)
    ? 'Private raw evidence is excluded. Create an approved sanitized derivative before model distillation.'
    : !['eligible', 'processed'].includes(sourceStatus)
      ? 'Run evidence triage and resolve admission requirements before method distillation.'
      : '';
  const candidateStatus = detail?.kind === 'candidate' ? String(detail.record.status || '') : '';
  const candidateEvidence = detail?.kind === 'candidate' && Array.isArray(detail.record.evidence)
    ? detail.record.evidence.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : [];
  const methodEvaluation = detail?.kind === 'method_proposal' ? record(detail.record.eval_summary) : {};
  const methodEvolution = record(methodEvaluation.evolution);
  const holdout = record(methodEvolution.holdout);
  const mutation = record(methodEvolution.mutation);
  const cost = record(methodEvolution.cost);
  const isMethodUpdate = detail?.kind === 'method_proposal' && String(detail.record.operation || '') === 'update';
  const updateEvaluationPassed = methodEvolution.passed === true;
  const updateFindings = Array.isArray(methodEvolution.findings)
    ? methodEvolution.findings.filter((item): item is string => typeof item === 'string' && Boolean(item))
    : [];
  const updatePublicationBlocked = isMethodUpdate && !updateEvaluationPassed;
  const methodExperiments = detail?.kind === 'method' && Array.isArray(detail.record.evolution_experiments)
    ? detail.record.evolution_experiments.filter((item): item is GrowthRecord => Boolean(item) && typeof item === 'object')
    : [];

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
          const targetNode = nodesById.get(target);
          const label = targetNode?.label || target;
          return <button key={edge.id} type="button" onClick={() => onFollow(target, type)}><span><b>{edge.edge_type}</b><strong>{label}</strong>{targetNode && <small>{target}</small>}</span><ExternalLink size={12} /></button>;
        }) : <p>No relationship in the current bounded graph slice.</p>}</section>
        {detail.kind === 'method' && <section className="growth-inspector__section" aria-label="Method evolution experiments">
          <h4><Sparkles size={13} /> Method evolution experiments</h4>
          {methodExperiments.length ? methodExperiments.map((experiment) => {
            const proposalId = typeof experiment.candidate_proposal_id === 'string' ? experiment.candidate_proposal_id : '';
            const decision = String(experiment.decision || experiment.status || 'recorded');
            return <button key={experiment.id} type="button" disabled={!proposalId} title={proposalId ? 'Open the review-only candidate proposal' : 'Candidate proposal not recorded'} onClick={() => onFollow(proposalId, 'method_proposal')}><span><b>{decision}</b><strong>{String(experiment.mutation_dimension || 'method mutation')}</strong><small>{String(experiment.baseline_revision_id || 'baseline not recorded')}</small></span><ExternalLink size={12} /></button>;
          }) : <p>No durable method-evolution experiment has been recorded for this method.</p>}
        </section>}
        {command ? <div className="growth-inspector__actions">
          <button type="button" disabled={actionDisabled} title={permissionMessage || command} onClick={() => onAction(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <CheckCircle2 size={14} /> : <KeyRound size={14} />}{command}</button>
          {permissionMessage && <small>{permissionMessage}. The API remains authoritative.</small>}
        </div> : detail.kind !== 'output' && detail.kind !== 'candidate' && <div className="growth-inspector__notice">No write action is exposed for this asset type by the current Growth API.</div>}
        {detail.kind === 'source' && <section className="growth-inspector__section" aria-label="Source method distillation">
          <h4><Sparkles size={13} /> Distill review-only methods</h4>
          <p>Creates RIA-TV++ candidates from this immutable evidence. Evidence anchors, trigger boundaries and routing tests are required; publication remains a separate review step.</p>
          {sourceDistillationReason && <div className="growth-inspector__notice">{sourceDistillationReason}</div>}
          <button type="button" disabled={actionDisabled || !sourceCanDistill} title={permissionMessage || sourceDistillationReason || 'Distill source into review-only method proposals'} onClick={() => onDistillSourceMethods(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <Sparkles size={14} /> : <KeyRound size={14} />}Distill source into methods</button>
          <button type="button" disabled={actionDisabled || !sourceCanDistill} title={permissionMessage || sourceDistillationReason || 'Extract review-only framework, principle, case, counterexample and glossary candidates'} onClick={() => onExtractSourceCandidates(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <Sparkles size={14} /> : <KeyRound size={14} />}Extract five evidence candidates</button>
        </section>}
        {detail.kind === 'candidate' && <section className="growth-inspector__section" aria-label="Evidence candidate review">
          <h4><Sparkles size={13} /> Evidence candidate review</h4>
          <p>{String(detail.record.claim || 'No candidate claim was persisted.')}</p>
          {typeof detail.record.explanation === 'string' && detail.record.explanation && <div className="growth-inspector__notice">{detail.record.explanation}</div>}
          <div className="growth-candidate-evidence">
            {candidateEvidence.length ? candidateEvidence.map((item, index) => {
              const sourceId = typeof item.source_id === 'string' ? item.source_id : '';
              const anchor = String(item.anchor || `evidence ${index + 1}`);
              const quote = String(item.quote || '');
              return <button key={`${sourceId}-${anchor}-${index}`} type="button" disabled={!sourceId} onClick={() => onFollow(sourceId, 'source')}><span>{anchor}</span><strong>{quote}</strong><small>{sourceId}</small><ExternalLink size={12} /></button>;
            }) : <p>No exact evidence anchors were returned; this candidate cannot be used for promotion.</p>}
          </div>
          {candidateStatus === 'pending_review' ? <form className="growth-feedback-form" onSubmit={(event) => {
            event.preventDefault();
            onReviewCandidate(detail, { decision: 'accepted', review_note: candidateReviewNote.trim() });
          }}>
            <label><span>Review note</span><textarea aria-label="Candidate review note" value={candidateReviewNote} onChange={(event) => setCandidateReviewNote(event.target.value)} placeholder="Why this should be retained or rejected" /></label>
            <div className="growth-candidate-review-actions">
              <button type="submit" disabled={actionDisabled} title={permissionMessage || 'Accept candidate for later selection'}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : <CheckCircle2 size={14} />}Accept for later selection</button>
              <button type="button" disabled={actionDisabled} title={permissionMessage || 'Reject candidate'} onClick={() => onReviewCandidate(detail, { decision: 'rejected', review_note: candidateReviewNote.trim() })}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : <X size={14} />}Reject candidate</button>
            </div>
          </form> : <>
            <div className="growth-inspector__notice">Review decision recorded: {candidateStatus || 'unknown'}. This is still not a publication action.</div>
            {candidateStatus === 'accepted' && <button type="button" disabled={actionDisabled} title={permissionMessage || 'Draft a review-only method from this accepted evidence selection'} onClick={() => onDistillAcceptedCandidate(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <Sparkles size={14} /> : <KeyRound size={14} />}Draft method from accepted candidate</button>}
          </>}
        </section>}
        {detail.kind === 'output' && <>
          {canAttachEvidence ? <form className="growth-feedback-form growth-evidence-form" onSubmit={(event) => {
            event.preventDefault();
            onLinkEvidence(detail, { source_ids: selectedEvidenceIds, page_ids: [] });
          }}>
            <h4>Link registered evidence</h4>
            <p>Attach eligible A-layer sources before reviewing this standalone output. This records lineage only; it never changes the plugin file or its immutable D-layer copy.</p>
            {evidenceState === 'loading' ? <div className="growth-inspector__notice">Loading eligible A-layer sources...</div> : evidenceSources.length ? <label><span>Registered evidence sources</span><select aria-label="Registered evidence sources" multiple size={Math.min(6, evidenceSources.length)} value={selectedEvidenceIds} onChange={(event) => setSelectedEvidenceIds(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{evidenceSources.map((source) => <option key={source.id} value={source.id}>{growthRecordLabel(source)} ({source.id.slice(0, 8)})</option>)}</select></label> : <div className="growth-inspector__notice">No eligible A-layer sources are available. Capture and triage evidence first; this output cannot claim groundedness yet.</div>}
            <button type="submit" disabled={actionDisabled || evidenceState === 'loading' || selectedEvidenceIds.length === 0} title={permissionMessage || 'Link selected evidence'}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <Link2 size={14} /> : <KeyRound size={14} />}Link selected evidence</button>
          </form> : evidenceRequired && !hasEvidenceReferences ? <div className="growth-inspector__notice">Evidence references are locked after evaluation starts. This output cannot claim groundedness without existing external A-layer evidence.</div> : null}
          {canEvaluate ? <form className="growth-feedback-form growth-evaluation-form" onSubmit={(event) => {
            event.preventDefault();
            onEvaluate(detail, { ...scores, findings: findings.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) });
          }}>
            <h4>Review quality gate</h4>
            <p>Scores are a persisted, immutable review revision. Use the linked evidence and output preview; a passing score is required before filing.</p>
            {evaluationFields.map(({ key, label }) => <label className="growth-evaluation-score" key={key}><span>{label}</span><div><input aria-label={`${label} score`} type="range" min="0" max="100" step="1" value={Math.round(scores[key] * 100)} onChange={(event) => setScores((current) => ({ ...current, [key]: Number(event.target.value) / 100 }))} /><output>{Math.round(scores[key] * 100)}%</output></div></label>)}
            <label><span>Findings</span><textarea aria-label="Output evaluation findings" value={findings} placeholder="One auditable finding per line" onChange={(event) => setFindings(event.target.value)} /></label>
            <button type="submit" disabled={actionDisabled} title={permissionMessage || 'Persist quality evaluation'}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : canWrite ? <CheckCircle2 size={14} /> : <KeyRound size={14} />}Evaluate output</button>
          </form> : outputStatus === 'registered' && evidenceRequired && !hasEvidenceReferences ? <div className="growth-inspector__notice">Link at least one eligible external source before submitting an evaluation. Groundedness above zero without that lineage is rejected by the API.</div> : hasEvaluation ? <div className="growth-inspector__notice">A persisted evaluation already exists for this immutable review revision. Add feedback or file an accepted output.</div> : null}
          {outputStatus !== 'registered' && <form className="growth-feedback-form" onSubmit={(event) => {
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
        </>}
        {actionMessage && <div className={`growth-action-message${actionState === 'error' || actionState === 'permission' ? ' is-error' : ''}`} role="status">{actionMessage}</div>}
        {detail.kind === 'method_proposal' && <section className="growth-inspector__section" aria-label="Method candidate gate">
          <h4>Method candidate gate</h4>
          <p>Evaluation reads the immutable supporting outputs and their persisted quality records. It never promotes a candidate by itself.</p>
          {isMethodUpdate && <div className="growth-method-evolution" aria-label="Method update evaluation">
            <h5>UPDATE EVALUATION</h5>
            <dl>
              <div><dt>Protocol</dt><dd>{String(methodEvolution.protocol_revision || 'not evaluated')}</dd></div>
              <div><dt>Gate</dt><dd>{updateEvaluationPassed ? 'passed' : String(methodEvolution.status || 'not evaluated')}</dd></div>
              <div><dt>Positive</dt><dd>{displayValue(methodEvolution.positive_case_count)}</dd></div>
              <div><dt>Near negative</dt><dd>{displayValue(methodEvolution.near_negative_case_count)}</dd></div>
              <div><dt>Holdout</dt><dd>{displayValue(holdout.case_count)}</dd></div>
              <div><dt>Candidate</dt><dd>{displayValue(holdout.candidate_passed)}</dd></div>
              <div><dt>Baseline</dt><dd>{displayValue(holdout.baseline_passed)}</dd></div>
              <div><dt>Regressions</dt><dd>{ids(holdout.regressed_case_ids).join(', ') || 'none'}</dd></div>
              <div><dt>Mutation</dt><dd>{ids(mutation.observed_dimensions).join(', ') || 'not evaluated'}</dd></div>
              <div><dt>Cost</dt><dd>{String(cost.status || 'not recorded')}</dd></div>
            </dl>
            {updateFindings.length > 0 && <ul>{updateFindings.map((finding) => <li key={finding}>{finding}</li>)}</ul>}
          </div>}
          <button type="button" disabled={actionDisabled} title={permissionMessage || 'Evaluate method candidate'} onClick={() => onEvaluateMethod(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : <CheckCircle2 size={14} />}Evaluate method candidate</button>
          {String(detail.record.status || '') === 'approved' && <button type="button" disabled={actionDisabled || updatePublicationBlocked} title={permissionMessage || (updatePublicationBlocked ? 'Passing isolated holdout and non-regression evaluation required' : 'Publish approved method')} onClick={() => onPublishMethod(detail)}>{actionState === 'loading' ? <LoaderCircle size={14} className="spin" /> : <CheckCircle2 size={14} />}Publish approved method</button>}
        </section>}
      </>}
    </>}
  </aside>;
}
