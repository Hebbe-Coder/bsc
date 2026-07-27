import { useEffect, useRef, useState } from 'react';
import { ArrowRight, FileOutput, RefreshCw, RotateCcw, Sparkles, Undo2 } from 'lucide-react';

import {
  answerDbosIntake,
  convertDbosIntake,
  createDbosIntake,
  directReviewDbosIntake,
  exportDbosIntakeHandoff,
  fetchDbosIntake,
  fetchDbosIntakeAvailability,
  listDbosIntakeRevisions,
  nextDbosIntakeQuestion,
  recommendDbosIntake,
  resolveDbosIntake,
  revertDbosIntakeAnswer,
  selectDbosIntakeTier,
  type DbosIntake,
  type DbosIntakeQuestion,
  type DbosIntakeRevision,
} from '../../api/dbosApi';

type Props = {
  projectId: string;
  sessionId?: string;
  disabled?: boolean;
  initialRequestText?: string;
  autoStart?: boolean;
  onMissionConverted: (missionId: string) => void;
};

function formatIntakeError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason || 'Unable to update governed Intake.');
  if (/failed to fetch|networkerror/i.test(message)) {
    return 'The Business OS connection was interrupted. No Mission or capability was changed; retry when the local API is ready.';
  }
  return message;
}

export function BlindspotIntakePanel({ projectId, sessionId = '', disabled = false, initialRequestText = '', autoStart = false, onMissionConverted }: Props) {
  const [availability, setAvailability] = useState<boolean | null>(null);
  const [requestText, setRequestText] = useState(initialRequestText);
  const [intake, setIntake] = useState<DbosIntake | null>(null);
  const [question, setQuestion] = useState<DbosIntakeQuestion | null>(null);
  const [revisions, setRevisions] = useState<DbosIntakeRevision[]>([]);
  const [answer, setAnswer] = useState('');
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const autoStartKeyRef = useRef('');

  // A persisted session is scoped to one project. Never carry its review state into a new scope.
  useEffect(() => {
    setIntake(null);
    setQuestion(null);
    setRevisions([]);
    setAnswer('');
    setApproved(false);
    setError('');
    if (!sessionId) {
      setRequestText(initialRequestText);
      autoStartKeyRef.current = '';
    }
  }, [initialRequestText, projectId, sessionId]);

  const run = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try { await operation(); }
    catch (reason) { setError(formatIntakeError(reason)); }
    finally { setBusy(false); }
  };

  const loadRevisions = async (targetSessionId: string) => {
    const result = await listDbosIntakeRevisions(projectId, targetSessionId);
    setRevisions(result.revisions);
  };

  const loadQuestion = async (targetSessionId: string) => {
    const result = await nextDbosIntakeQuestion(projectId, targetSessionId);
    setIntake(result.intake);
    setQuestion(result.question);
    setAnswer('');
  };

  useEffect(() => {
    let active = true;
    void fetchDbosIntakeAvailability()
      .then((result) => { if (active) setAvailability(result.enabled); })
      .catch((reason) => {
        if (!active) return;
        setAvailability(true);
        setError(formatIntakeError(reason));
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!sessionId || availability !== true) return;
    let active = true;
    void Promise.all([fetchDbosIntake(projectId, sessionId), listDbosIntakeRevisions(projectId, sessionId)])
      .then(([restored, revisionResult]) => {
        if (!active) return;
        setIntake(restored);
        setRevisions(revisionResult.revisions);
      })
      .catch((reason) => { if (active) setError(formatIntakeError(reason)); });
    return () => { active = false; };
  }, [availability, projectId, sessionId]);

  const begin = () => void run(async () => {
    const created = await createDbosIntake(projectId, requestText);
    setIntake(created);
    setQuestion(null);
    await loadRevisions(created.artifact_id);
    if (created.phase === 'clarifying') await loadQuestion(created.artifact_id);
  });

  useEffect(() => {
    const request = initialRequestText.trim();
    if (!autoStart || !request || availability !== true || sessionId || intake || busy || !projectId.trim()) return;
    const requestKey = `${projectId}:${request}`;
    if (autoStartKeyRef.current === requestKey) return;
    autoStartKeyRef.current = requestKey;
    setRequestText(request);
    void run(async () => {
      const created = await createDbosIntake(projectId, request);
      setIntake(created);
      setQuestion(null);
      await loadRevisions(created.artifact_id);
      if (created.phase === 'clarifying') await loadQuestion(created.artifact_id);
    });
  }, [autoStart, availability, busy, initialRequestText, intake, loadQuestion, loadRevisions, projectId, run, sessionId]);

  const resolve = (action: 'clarify' | 'direct' | 'help') => void run(async () => {
    if (!intake) return;
    const resolved = await resolveDbosIntake(projectId, intake.artifact_id, action);
    setIntake(resolved);
    if (resolved.phase === 'clarifying') await loadQuestion(resolved.artifact_id);
  });

  const submitAnswer = (skipped: boolean) => void run(async () => {
    if (!intake || !question || (!skipped && !answer.trim())) return;
    const updated = await answerDbosIntake(projectId, intake.artifact_id, question.question_id, answer, skipped);
    setIntake(updated);
    setQuestion(null);
    await loadRevisions(updated.artifact_id);
    if (updated.phase === 'clarifying') await loadQuestion(updated.artifact_id);
  });

  const directToReview = () => void run(async () => {
    if (!intake) return;
    const reviewed = await directReviewDbosIntake(projectId, intake.artifact_id);
    setIntake(reviewed);
    setQuestion(null);
  });

  const latestActiveRevision = [...revisions].reverse().find((revision) => revision.status !== 'superseded');
  const undoLatest = () => void run(async () => {
    if (!intake || !latestActiveRevision) return;
    const reopened = await revertDbosIntakeAnswer(projectId, intake.artifact_id, latestActiveRevision.artifact_id);
    setIntake(reopened);
    await loadRevisions(reopened.artifact_id);
    await loadQuestion(reopened.artifact_id);
  });

  if (availability === false) return null;

  if (availability === null) {
    return <section className="blindspot-intake" aria-label="Governed intake" aria-busy="true">
      <header><span>GOVERNED INTAKE</span><strong>Checking governed Intake availability</strong></header>
    </section>;
  }

  if (!intake) {
    return <section className="blindspot-intake" aria-label="Governed intake">
      <header><span>GOVERNED INTAKE</span><strong>Frame the work before a Mission exists</strong></header>
      <label>Request<textarea value={requestText} onChange={(event) => setRequestText(event.target.value)} placeholder="Describe the outcome, decision, or work to begin." disabled={disabled || busy} /></label>
      {error && <p className="blindspot-intake__error" role="alert">{error}</p>}
      <button type="button" onClick={begin} disabled={disabled || busy || !projectId.trim() || !requestText.trim()}><Sparkles size={16} />{busy ? 'Classifying' : 'Start intake'}</button>
    </section>;
  }

  return <section className="blindspot-intake" aria-live="polite">
    <header><span>{intake.classification.toUpperCase()} / {intake.domain.toUpperCase()}</span><strong>{intake.phase.replace(/_/g, ' ')}</strong></header>
    <p className="blindspot-intake__request">{intake.original_request}</p>
    {error && <p className="blindspot-intake__error" role="alert">{error}</p>}

    {intake.phase === 'classified' && <div className="blindspot-intake__actions"><button type="button" onClick={() => resolve('clarify')} disabled={busy}>Clarify</button><button type="button" onClick={() => resolve('direct')} disabled={busy}>Direct Mission</button><button type="button" onClick={() => resolve('help')} disabled={busy}>Help only</button></div>}
    {intake.phase === 'exited' && <div className="blindspot-intake__review"><p className="blindspot-intake__note">This is an explanation request, not a build workflow. No Mission or external action was created.</p><div className="blindspot-intake__actions"><button type="button" onClick={() => { setIntake(null); setQuestion(null); setRevisions([]); setRequestText(''); }} disabled={busy}><RotateCcw size={15} />New request</button></div></div>}

    {intake.phase === 'clarifying' && question && <div className="blindspot-intake__question"><small>{question.phase.toUpperCase()} {question.field.replace(/_/g, ' ')}</small><strong>{question.prompt}</strong><div className="blindspot-intake__options">{question.options.map((option) => <button type="button" key={option.value} onClick={() => setAnswer(option.value)} aria-pressed={answer === option.value} disabled={busy}>{option.label}</button>)}</div><label>Answer<input value={answer} onChange={(event) => setAnswer(event.target.value)} disabled={busy} /></label><div className="blindspot-intake__actions"><button type="button" onClick={() => submitAnswer(false)} disabled={busy || !answer.trim()}><ArrowRight size={15} />Continue</button><button type="button" className="blindspot-intake__secondary" onClick={() => submitAnswer(true)} disabled={busy}>Skip</button><button type="button" className="blindspot-intake__secondary" onClick={directToReview} disabled={busy}>Skip to review</button>{latestActiveRevision && <button type="button" className="blindspot-intake__secondary" onClick={undoLatest} disabled={busy}><Undo2 size={15} />Undo last answer</button>}</div></div>}

    {intake.phase === 'ready_for_review' && <div className="blindspot-intake__review"><small>OPERATING DEPTH</small>{intake.unresolved_fields.length > 0 && <p className="blindspot-intake__note">Known gaps: {intake.unresolved_fields.join(', ')}</p>}<div className="blindspot-intake__tiers">{(['lite', 'standard', 'full'] as const).map((tier) => <button type="button" key={tier} aria-pressed={intake.tier === tier} onClick={() => void run(async () => setIntake(await selectDbosIntakeTier(projectId, intake.artifact_id, tier)))} disabled={busy}>{tier}</button>)}</div>{intake.tier && <div className="blindspot-intake__actions"><button type="button" onClick={() => void run(async () => setIntake(await recommendDbosIntake(projectId, intake.artifact_id)))} disabled={busy}><RefreshCw size={15} />Sources</button><button type="button" onClick={() => void run(async () => { const result = await convertDbosIntake(projectId, intake.artifact_id); setIntake(result.intake); onMissionConverted(result.mission.artifact_id); })} disabled={busy}><ArrowRight size={15} />Create Mission</button>{latestActiveRevision && <button type="button" className="blindspot-intake__secondary" onClick={undoLatest} disabled={busy}><Undo2 size={15} />Undo last answer</button>}</div>}{intake.recommendations?.length ? <ul className="blindspot-intake__sources">{intake.recommendations.map((item, index) => <li key={String(item.source_id || index)}>{item.state === 'unavailable' ? String(item.reason) : <><a href={String(item.source_url)} target="_blank" rel="noreferrer">{String(item.source_id)}</a><span>{String(item.summary)}</span><small>{String(item.trust_level)} | {String(item.status)}</small><small>{String(item.applicability)}</small><time dateTime={String(item.captured_at)}>Captured {String(item.captured_at)}</time></>}</li>)}</ul> : null}</div>}

    {intake.phase === 'converted' && <div className="blindspot-intake__review"><small>MISSION READY FOR CONFIRMATION</small><label className="blindspot-intake__approval"><input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} disabled={busy} />Approve Vault handoff</label><button type="button" onClick={() => void run(async () => setIntake((await exportDbosIntakeHandoff(projectId, intake.artifact_id, 'studio-owner', approved)).intake))} disabled={busy || !approved}><FileOutput size={15} />Export handoff</button>{intake.handoff_path && <p className="blindspot-intake__handoff">{intake.handoff_path}</p>}</div>}
  </section>;
}
