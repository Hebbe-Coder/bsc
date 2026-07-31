import { FormEvent, useCallback, useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { AlertTriangle, BrainCircuit, CircleCheckBig, FileCheck2, KeyRound, RefreshCw, ShieldCheck, X } from 'lucide-react';
import {
  capturePbosWorkspaceExecution,
  fetchPbosCockpit,
  fetchPbosProfile,
  recordPbosExecution,
  recordPbosFeedback,
  recordPbosOutcome,
  reviewPbosOutcome,
  savePbosProfile,
  type PbosCockpit,
  type PbosProfile,
} from '../../api/pbosApi';
import RegisteredECharts from '../charts/RegisteredECharts';

type Props = {
  projectId: string;
  onClose: () => void;
  runtimeAccessKey?: string;
  onConfigureAccess?: () => void;
};

function isAccessFailure(reason: unknown): boolean {
  const message = reason instanceof Error ? reason.message : String(reason || '');
  return /\b(?:401|403)\b|auth(?:entication|orization)?|forbidden|permission/i.test(message);
}

function connectorLabel(state: string): string {
  return state.replace(/_/g, ' ');
}

function stringRefs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(new Set(value.map((item) => String(item).trim()).filter(Boolean)));
}

function visibleVaultRef(reference: string): string {
  return reference.replace(/^vault:/u, '');
}

function planStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function planObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

type OutcomeReviewDraft = {
  qualityScore: string;
  reviewNote: string;
};

function readableRequirement(value: string): string {
  return value.replace(/_/g, ' ');
}

function planGenerationStatus(plan: Record<string, unknown> | null | undefined): {
  label: string;
  detail: string;
  tone: 'is-ready' | 'is-pending';
} {
  const metadata = planObject(plan?.compiler_metadata);
  const mode = String(metadata.mode || '');
  const failure = String(metadata.llm_failure || '').replace(/_/g, ' ').trim();
  if (mode === 'llm_contextual') {
    const provider = String(metadata.provider || '').trim();
    const model = String(metadata.model || '').trim();
    return {
      label: 'LLM contextual',
      detail: [provider, model].filter(Boolean).join(' / ') || 'configured model',
      tone: 'is-ready',
    };
  }
  if (failure) {
    return { label: 'LLM fallback', detail: failure, tone: 'is-pending' };
  }
  if (String(plan?.compilation_state || '') === 'capture_required') {
    return { label: 'Capture required', detail: 'evidence gap', tone: 'is-pending' };
  }
  return { label: 'Contextual deterministic', detail: 'no model result recorded', tone: 'is-pending' };
}

export function PersonalGrowthCockpit({ projectId, onClose, runtimeAccessKey = '', onConfigureAccess }: Props) {
  const [data, setData] = useState<PbosCockpit | null>(null);
  const [profile, setProfile] = useState<PbosProfile | null>(null);
  const [error, setError] = useState('');
  const [accessState, setAccessState] = useState<'required' | 'rejected' | null>(null);
  const [saving, setSaving] = useState(false);
  const [focus, setFocus] = useState('');
  const [goals, setGoals] = useState('');
  const [resources, setResources] = useState('');
  const [constraints, setConstraints] = useState('');
  const [reflection, setReflection] = useState('');
  const [blocker, setBlocker] = useState('');
  const [feedbackDraft, setFeedbackDraft] = useState('');
  const [evidencePaths, setEvidencePaths] = useState('');
  const [acceptanceConfirmed, setAcceptanceConfirmed] = useState(false);
  const [qualityScore, setQualityScore] = useState('');
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, OutcomeReviewDraft>>({});
  const [reviewingOutcomeId, setReviewingOutcomeId] = useState('');
  const [creatingOutcomeExecutionId, setCreatingOutcomeExecutionId] = useState('');
  const load = useCallback(async () => {
    if (!runtimeAccessKey.trim()) {
      setData(null); setProfile(null); setError(''); setAccessState('required');
      return;
    }
    try {
      setError(''); setAccessState(null);
      const [cockpit, profileResult] = await Promise.all([fetchPbosCockpit(projectId), fetchPbosProfile(projectId)]);
      setData(cockpit);
      const nextProfile = profileResult.profile ?? cockpit.profile;
      setProfile(nextProfile);
      setFocus((nextProfile?.focus ?? []).join(', '));
      setGoals((nextProfile?.goals ?? []).join(', '));
      setResources((nextProfile?.resources ?? []).join(', '));
      setConstraints((nextProfile?.constraints ?? []).join(', '));
    } catch (reason) {
      if (isAccessFailure(reason)) {
        setData(null); setProfile(null); setError(''); setAccessState('rejected');
        return;
      }
      setError(reason instanceof Error ? reason.message : 'Unable to load PBOS');
    }
  }, [projectId, runtimeAccessKey]);
  useEffect(() => { void load(); }, [load]);
  const capabilities = data?.capabilities ?? [];
  const executions = data?.executions ?? [];
  const outcomes = data?.outcomes ?? [];
  const outcomeObservations = data?.outcome_observations ?? [];
  const feedback = data?.feedback ?? [];
  const strategies = data?.strategies ?? [];
  const failurePatterns = data?.failure_patterns ?? [];
  const projectHealth = data?.project_health ?? {};
  const todayAction = planObject(data?.today_action);
  const generation = planGenerationStatus(data?.today);
  const acceptedOutcomes = outcomes.filter((item) => item.acceptance_status === 'accepted').length;
  const qualitySeries = outcomes.filter((item) => item.acceptance_status === 'accepted' && typeof item.quality_score === 'number').slice().reverse();
  const pendingReviewOutcomes = outcomes.filter((item) => String(item.acceptance_status || '') === 'unverified');
  const awaitingOutcomeExecutions = executions.filter((item) => item.outcome_state === 'awaiting_outcome');
  const contextReferences = stringRefs(data?.today?.knowledge_context_refs);
  const strategyReferences = stringRefs(data?.today?.strategy_refs);
  const appliedStrategies = strategies.filter((item) => strategyReferences.includes(String(item.artifact_id || '')));
  const knowledgeContextReady = projectHealth.knowledge_context_ready ?? contextReferences.length > 0;
  const personalLearningReady = projectHealth.personal_learning_ready ?? projectHealth.evidence_ready ?? false;
  const contextReferenceCount = Number(projectHealth.knowledge_context_reference_count ?? contextReferences.length);
  const weeklyHandoffs = contextReferences.filter((item) => /^vault:distillations\/每周蒸馏\/[^/]+\/03-下周上下文包\.md$/u.test(item));
  const feedbackReferences = stringRefs(data?.today?.feedback_refs);
  const phases = Array.isArray(data?.today?.phases) ? data.today.phases.map(planObject) : [];
  const currentPhase = phases[0] ?? {};
  const phaseInputs = planStrings(currentPhase.inputs);
  const phaseOutputs = planStrings(currentPhase.outputs);
  const phaseActions = planStrings(currentPhase.actions);
  const decisionPoint = planObject(currentPhase.decision_point);
  const executionContract = planObject(data?.today?.execution_contract);
  const todayGuidance = data?.today?.compilation_state === 'capture_required'
    ? 'PBOS needs evidence before it can claim a personal next step.'
    : capabilities.length
      ? 'This plan is grounded in declared personal context and verified execution evidence.'
      : 'This plan is grounded in declared personal context and governed Vault evidence. Capability claims still await verified execution evidence.';
  const compactGraph = typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(max-width: 720px)').matches;
  const splitList = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean);
  const saveProfile = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true);
    try {
      await savePbosProfile(projectId, {
        focus: splitList(focus), goals: splitList(goals), resources: splitList(resources), constraints: splitList(constraints),
        preferences: { architecture_first: true, evidence_first: true },
      });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save profile'); }
    finally { setSaving(false); }
  };
  const submitReflection = async (event: FormEvent) => {
    event.preventDefault();
    const today = data?.today;
    const missionId = String(today?.mission_id || '');
    const planId = String(today?.artifact_id || '');
    if (!missionId || !planId || !reflection.trim()) return;
    const paths = splitList(evidencePaths);
    const parsedQuality = Number(qualityScore);
    if (acceptanceConfirmed && !paths.length) {
      setError('Attach at least one BSC workspace evidence file before accepting an outcome.');
      return;
    }
    if (acceptanceConfirmed && (!qualityScore.trim() || !Number.isFinite(parsedQuality) || parsedQuality < 0 || parsedQuality > 100)) {
      setError('An accepted outcome needs a quality score from 0 to 100.');
      return;
    }
    if (!acceptanceConfirmed && qualityScore.trim()) {
      setError('Confirm acceptance before recording a quality score.');
      return;
    }
    setSaving(true);
    try {
      const executionPayload = {
        plan_id: planId,
        actions: [reflection.trim()],
        reflection: { completed: reflection.trim(), blocker: blocker.trim() },
      };
      const execution = paths.length
        ? await capturePbosWorkspaceExecution(projectId, missionId, { ...executionPayload, paths })
        : await recordPbosExecution(projectId, missionId, executionPayload);
      const outcome = await recordPbosOutcome(projectId, String(execution.execution.artifact_id || ''), {
        acceptance_status: acceptanceConfirmed ? 'accepted' : 'unverified',
        ...(acceptanceConfirmed ? { quality_score: parsedQuality } : {}),
        metrics: { reflection_recorded: true, evidence_capture: paths.length ? 'bsc_workspace' : 'none' },
      });
      if (feedbackDraft.trim()) await recordPbosFeedback(projectId, String(outcome.outcome.artifact_id || ''), feedbackDraft.trim());
      setReflection(''); setBlocker(''); setFeedbackDraft(''); setEvidencePaths(''); setAcceptanceConfirmed(false); setQualityScore(''); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to record reflection'); }
    finally { setSaving(false); }
  };
  const reviewPendingOutcome = async (outcomeId: string, decision: 'accepted' | 'rejected') => {
    const observation = outcomeObservations.find((item) => item.artifact_id === outcomeId);
    const missingRequirements = observation?.missing_requirements ?? [];
    const unresolvedEvidence = missingRequirements.filter((item) => item !== 'accepted_outcome' && item !== 'quality_score');
    const draft = reviewDrafts[outcomeId] ?? { qualityScore: '', reviewNote: '' };
    const parsedQuality = Number(draft.qualityScore);
    if (decision === 'accepted' && unresolvedEvidence.length) {
      setError(`Capture the missing evidence before accepting this result: ${unresolvedEvidence.map(readableRequirement).join(', ')}.`);
      return;
    }
    if (decision === 'accepted' && (!draft.qualityScore.trim() || !Number.isFinite(parsedQuality) || parsedQuality < 0 || parsedQuality > 100)) {
      setError('An accepted outcome needs a quality score from 0 to 100.');
      return;
    }
    setReviewingOutcomeId(outcomeId);
    try {
      await reviewPbosOutcome(projectId, outcomeId, {
        decision,
        ...(decision === 'accepted' ? { quality_score: parsedQuality } : {}),
        review_note: draft.reviewNote.trim(),
      });
      setReviewDrafts((current) => {
        const next = { ...current };
        delete next[outcomeId];
        return next;
      });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to review outcome'); }
    finally { setReviewingOutcomeId(''); }
  };
  const createOutcomeForExecution = async (executionId: string) => {
    setCreatingOutcomeExecutionId(executionId);
    try {
      await recordPbosOutcome(projectId, executionId, {
        acceptance_status: 'unverified',
        metrics: { outcome_intake: 'explicit_existing_execution' },
      });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create a reviewable outcome'); }
    finally { setCreatingOutcomeExecutionId(''); }
  };
  const nodes: Node[] = [
    { id: 'weekly-handoff', position: compactGraph ? { x: 0, y: 6 } : { x: 0, y: 24 }, data: { label: weeklyHandoffs.length ? `${weeklyHandoffs.length} weekly handoff` : 'No weekly handoff' }, type: 'default', className: 'pbos-lineage__input' },
    { id: 'vault-context', position: compactGraph ? { x: 0, y: 76 } : { x: 0, y: 136 }, data: { label: `${contextReferences.length} Vault ref${contextReferences.length === 1 ? '' : 's'}` }, type: 'default', className: 'pbos-lineage__input' },
    { id: 'current-plan', position: compactGraph ? { x: 158, y: 40 } : { x: 190, y: 80 }, data: { label: 'Current plan' }, type: 'default', className: 'pbos-lineage__plan' },
    { id: 'outcome', position: compactGraph ? { x: 316, y: 6 } : { x: 375, y: 80 }, data: { label: `${outcomes.length} outcome${outcomes.length === 1 ? '' : 's'}` }, type: 'default' },
    { id: 'feedback', position: compactGraph ? { x: 316, y: 76 } : { x: 555, y: 80 }, data: { label: `${feedbackReferences.length} feedback input${feedbackReferences.length === 1 ? '' : 's'}` }, type: 'default', className: 'pbos-lineage__feedback' },
    { id: 'next-plan', position: compactGraph ? { x: 158, y: 146 } : { x: 735, y: 80 }, data: { label: 'Next plan' }, type: 'default', className: 'pbos-lineage__plan' },
    { id: 'capability', position: compactGraph ? { x: 316, y: 146 } : { x: 375, y: 172 }, data: { label: `${capabilities.length} capabilities` }, type: 'default' },
  ];
  const edges: Edge[] = [
    { id: 'weekly-plan', source: 'weekly-handoff', target: 'current-plan' },
    { id: 'vault-plan', source: 'vault-context', target: 'current-plan' },
    { id: 'plan-outcome', source: 'current-plan', target: 'outcome' },
    { id: 'outcome-feedback', source: 'outcome', target: 'feedback' },
    { id: 'feedback-next-plan', source: 'feedback', target: 'next-plan' },
    { id: 'outcome-capability', source: 'outcome', target: 'capability' },
  ];
  const qualityChart = {
    backgroundColor: 'transparent',
    grid: { left: 38, right: 16, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis', backgroundColor: '#111e26', borderColor: '#3a5962', textStyle: { color: '#e1eff0', fontFamily: 'ui-monospace, monospace' } },
    xAxis: { type: 'category', boundaryGap: false, data: qualitySeries.map((_, index) => `Result ${index + 1}`), axisLine: { lineStyle: { color: '#304852' } }, axisLabel: { color: '#7f9aa1', fontSize: 10 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}', color: '#7f9aa1', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(99, 134, 144, 0.18)' } } },
    series: [{
      name: 'Quality',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 9,
      data: qualitySeries.map((item) => Number(item.quality_score ?? 0)),
      lineStyle: { color: '#7ad6bc', width: 3 },
      itemStyle: { color: '#7ad6bc' },
      areaStyle: { color: 'rgba(122, 214, 188, 0.12)' },
    }],
  };
  return <section className="pbos-cockpit" aria-label="Personal Growth Cockpit">
    <header><div><p>PERSONAL LOOP ENGINEERING</p><h2>Personal Growth Cockpit</h2></div><div><button type="button" aria-label="Refresh PBOS evidence" title="Refresh evidence" onClick={() => void load()}><RefreshCw size={17} /></button><button type="button" aria-label="Close Personal Growth Cockpit" title="Close" onClick={onClose}><X size={18} /></button></div></header>
    {accessState && <section className="pbos-access-state" role="status">
      <div><KeyRound size={21} aria-hidden="true" /><div><p className="pbos-label">STUDIO ACCESS</p><h3>{accessState === 'required' ? 'Studio access is required' : 'Studio access was rejected'}</h3><p>{accessState === 'required' ? 'PBOS reads a project-scoped evidence ledger. Add a runtime access key before the cockpit requests any personal records.' : 'The runtime access key cannot read this project. Replace it in the control rail, then return to the cockpit.'}</p></div></div>
      <div className="pbos-access-state__actions">{accessState === 'rejected' && <button type="button" onClick={() => void load()}><RefreshCw size={15} />Retry</button>}<button type="button" className="pbos-primary-action" onClick={onConfigureAccess ?? onClose}><KeyRound size={15} />Open runtime access</button></div>
    </section>}
    {error && <p className="pbos-error"><AlertTriangle size={16} />{error}</p>}
    {!data && !error && !accessState && <p className="pbos-empty">Loading verified personal evidence...</p>}
    {data && <div className="pbos-grid">
      <section className="pbos-today"><div className="pbos-panel-heading"><p className="pbos-label">CURRENT LOOP</p><span className={knowledgeContextReady ? 'is-ready' : 'is-pending'}><ShieldCheck size={14} />{knowledgeContextReady ? 'Vault context connected' : 'Vault context needed'}</span></div><h3>{String(data.today?.title || todayAction.title || 'Capture a real execution receipt')}</h3><p>{todayGuidance}</p>{todayAction.success_check && <small>Success check: {String(todayAction.success_check)}</small>}<dl><div><dt>Accepted outcomes</dt><dd>{acceptedOutcomes}</dd></div><div><dt>Feedback inputs</dt><dd>{feedback.length}</dd></div><div><dt>Verified capabilities</dt><dd>{capabilities.length}</dd></div></dl></section>
      {Object.keys(currentPhase).length > 0 && <section className="pbos-execution-path"><div className="pbos-panel-heading"><p className="pbos-label">TODAY'S EXECUTION PATH</p><span>phase 1 of {phases.length}</span></div><h3>{String(currentPhase.title || 'Clarify the next evidence-backed slice')}</h3>{currentPhase.why_now && <p>{String(currentPhase.why_now)}</p>}<div className="pbos-execution-path__io"><div><strong>Inputs</strong>{phaseInputs.slice(0, 3).map((item) => <span key={item}>{item}</span>)}</div><div><strong>Reviewable output</strong>{phaseOutputs.slice(0, 2).map((item) => <span key={item}>{item}</span>)}</div></div>{phaseActions.length > 0 && <ol>{phaseActions.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ol>}{decisionPoint.question && <div className="pbos-decision-point"><strong>Decision: {String(decisionPoint.question)}</strong><span>Proceed: {String(decisionPoint.proceed_when || 'when the phase output is reviewable')}</span><span>Adapt: {String(decisionPoint.adapt_when || 'when the evidence boundary is not met')}</span></div>}{executionContract.reflection_entry && <small>{String(executionContract.reflection_entry)}</small>}</section>}
      <section className="pbos-connectors"><div className="pbos-panel-heading"><p className="pbos-label">CONNECTORS</p><span>{Object.keys(data.connectors).length} configured</span></div><div>{Object.entries(data.connectors).map(([name, state]) => <p key={name}><strong>{name}</strong><span data-state={state}>{connectorLabel(state)}</span></p>)}</div><small>External sources stay outside personal evidence until their scoped authorization and receipts are available.</small></section>
      <section className="pbos-health"><div className="pbos-panel-heading"><p className="pbos-label">PROJECT HEALTH</p><span>ledger projection</span></div><dl><div><dt>Vault context</dt><dd className={knowledgeContextReady ? 'is-ready' : 'is-pending'}>{knowledgeContextReady ? `connected (${contextReferenceCount})` : 'needed'}</dd></div><div><dt>Personal learning</dt><dd className={personalLearningReady ? 'is-ready' : 'is-pending'}>{personalLearningReady ? 'grounded' : 'awaiting evidence'}</dd></div><div><dt>Accepted</dt><dd>{String(projectHealth.accepted_outcomes ?? 0)}</dd></div><div><dt>Learning-eligible</dt><dd>{String(projectHealth.eligible_personal_outcomes ?? 0)}</dd></div><div><dt>Unverified</dt><dd>{String(projectHealth.unverified_outcomes ?? 0)}</dd></div><div><dt>Active strategies</dt><dd>{String(projectHealth.active_strategies ?? 0)}</dd></div></dl></section>
      {data.today && <section className="pbos-grounding"><div className="pbos-panel-heading"><p className="pbos-label">PLAN GROUNDING</p><span>{contextReferences.length} governed reference{contextReferences.length === 1 ? '' : 's'}</span></div><dl><div><dt>Plan engine</dt><dd><span className={`pbos-plan-generation ${generation.tone}`}>{generation.label}</span><small>{generation.detail}</small></dd></div><div><dt>Weekly handoff</dt><dd>{weeklyHandoffs.length} weekly handoff{weeklyHandoffs.length === 1 ? '' : 's'}</dd></div><div><dt>Feedback input</dt><dd>{feedbackReferences.length} feedback input{feedbackReferences.length === 1 ? '' : 's'}</dd></div><div><dt>Personal strategy</dt><dd>{appliedStrategies.length ? `${appliedStrategies.length} verified strategy applied` : 'not yet earned'}</dd></div></dl>{contextReferences.length ? <ul>{contextReferences.slice(0, 4).map((item) => <li key={item}><code>{visibleVaultRef(item)}</code></li>)}</ul> : <p className="pbos-grounding-empty">No governed context was selected for this plan.</p>}{appliedStrategies.length > 0 && <ul className="pbos-strategy-inputs">{appliedStrategies.map((item) => <li key={String(item.artifact_id)}><BrainCircuit size={13} /><span>{String(item.strategy_name || 'Personal strategy')} v{String(item.version || 1)}</span></li>)}</ul>}<p>These are planning inputs. They do not establish a personal capability without verified execution evidence.</p></section>}
      <section className="pbos-profile"><p className="pbos-label">PERSONAL CONTEXT</p><form onSubmit={saveProfile}><label>Focus<input value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="AI systems, knowledge engineering" /></label><label>Goals<input value={goals} onChange={(event) => setGoals(event.target.value)} placeholder="Ship a verified personal operating system" /></label><label>Resources<input value={resources} onChange={(event) => setResources(event.target.value)} placeholder="Obsidian, BSC" /></label><label>Constraints<input value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="Solo delivery, limited time" /></label><button type="submit" disabled={saving} title="Save personal context">Save personal context</button></form><p>{profile ? 'This is declared context. Capability claims still require execution evidence.' : 'Add your real operating context before PBOS personalizes a plan.'}</p></section>
      {data.today && <section className="pbos-reflection"><p className="pbos-label">THREE-MINUTE REFLECTION</p><form onSubmit={submitReflection}><label>What changed?<textarea value={reflection} onChange={(event) => setReflection(event.target.value)} required placeholder="Completed, observed result, or decision made" /></label><label>What blocked you?<input value={blocker} onChange={(event) => setBlocker(event.target.value)} placeholder="Optional blocker" /></label><label>Evidence files in this BSC workspace<input value={evidencePaths} onChange={(event) => setEvidencePaths(event.target.value)} placeholder="app/pbos/service.py, app/knowledge/wiki_sync.py" /></label><small>Only approved project paths are hashed. File contents and credentials are never sent to the PBOS ledger.</small><label className="pbos-reflection__acceptance"><input type="checkbox" checked={acceptanceConfirmed} onChange={(event) => setAcceptanceConfirmed(event.target.checked)} />I accept this result based on the attached evidence</label><label>Quality score (0-100)<input type="number" min="0" max="100" step="1" value={qualityScore} onChange={(event) => setQualityScore(event.target.value)} disabled={!acceptanceConfirmed} placeholder="82" /></label><label>What should change next time?<input value={feedbackDraft} onChange={(event) => setFeedbackDraft(event.target.value)} placeholder="Optional feedback for the next plan" /></label><button type="submit" disabled={saving || !reflection.trim()} title="Record evidence-backed reflection">Record reflection</button></form><p>Without an attached receipt and explicit acceptance, PBOS keeps the result unverified and does not learn a personal method from it.</p></section>}
      {awaitingOutcomeExecutions.length > 0 && <section className="pbos-outcome-intake"><div className="pbos-panel-heading"><p className="pbos-label">OUTCOMES TO RECORD</p><span>{awaitingOutcomeExecutions.length} reviewable execution{awaitingOutcomeExecutions.length === 1 ? '' : 's'}</span></div><p>These executions already have server-verified receipts and a reflection. Create one unverified result, then explicitly accept or reject it in the review queue.</p><div className="pbos-review-list">{awaitingOutcomeExecutions.map((execution) => { const creating = creatingOutcomeExecutionId === execution.artifact_id; return <article key={execution.artifact_id} className="pbos-review-card"><div><strong>Ready for outcome review</strong><small>{execution.verified_receipt_count} verified receipt{execution.verified_receipt_count === 1 ? '' : 's'} / reflection recorded</small></div><button type="button" className="pbos-primary-action" aria-label={`Create reviewable outcome for ${execution.artifact_id}`} disabled={Boolean(creatingOutcomeExecutionId)} onClick={() => void createOutcomeForExecution(execution.artifact_id)}>{creating ? 'Creating outcome...' : 'Create reviewable outcome'}</button></article>; })}</div></section>}
      {pendingReviewOutcomes.length > 0 && <section className="pbos-review-queue"><div className="pbos-panel-heading"><p className="pbos-label">REVIEW PENDING OUTCOMES</p><span>{pendingReviewOutcomes.length} explicit review{pendingReviewOutcomes.length === 1 ? '' : 's'}</span></div><div className="pbos-review-list">{pendingReviewOutcomes.map((outcome) => { const outcomeId = String(outcome.artifact_id || ''); const observation = outcomeObservations.find((item) => item.artifact_id === outcomeId); const missingRequirements = observation?.missing_requirements ?? ['accepted_outcome', 'quality_score']; const unresolvedEvidence = missingRequirements.filter((item) => item !== 'accepted_outcome' && item !== 'quality_score'); const canAccept = unresolvedEvidence.length === 0; const executionId = String(outcome.execution_record_id || ''); const execution = executions.find((item) => item.artifact_id === executionId); const draft = reviewDrafts[outcomeId] ?? { qualityScore: '', reviewNote: '' }; const parsedQuality = Number(draft.qualityScore); const validQuality = draft.qualityScore.trim() !== '' && Number.isFinite(parsedQuality) && parsedQuality >= 0 && parsedQuality <= 100; const updating = reviewingOutcomeId === outcomeId; return <article key={outcomeId} className="pbos-review-card"><div><strong>{outcomeId}</strong><small>{executionId || 'Execution record unavailable'}{execution ? ` / ${execution.verified_receipt_count} verified receipt${execution.verified_receipt_count === 1 ? '' : 's'}` : ''}</small>{unresolvedEvidence.length > 0 && <em>Evidence gap: {unresolvedEvidence.map(readableRequirement).join(', ')}</em>}</div><label>Quality score for {outcomeId}<input type="number" min="0" max="100" step="1" value={draft.qualityScore} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, qualityScore: event.target.value } }))} disabled={updating || !canAccept} placeholder="82" /></label><label>Review note for {outcomeId}<input value={draft.reviewNote} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, reviewNote: event.target.value } }))} disabled={updating} placeholder="Optional audit note" /></label><div className="pbos-review-actions"><button type="button" className="pbos-primary-action" disabled={updating || !canAccept || !validQuality} onClick={() => void reviewPendingOutcome(outcomeId, 'accepted')}>Accept result</button><button type="button" disabled={updating} onClick={() => void reviewPendingOutcome(outcomeId, 'rejected')}>Reject result</button></div></article>; })}</div></section>}
      <section className="pbos-executions"><div className="pbos-panel-heading"><p className="pbos-label">RECENT EXECUTION RECEIPTS</p><span>{executions.length} reviewable record{executions.length === 1 ? '' : 's'}</span></div><div className="pbos-outcomes">{executions.length ? executions.map((execution) => <p key={execution.artifact_id}><FileCheck2 size={15} /><span><strong>{execution.artifact_id.slice(0, 16)}</strong><small>{execution.verified_receipt_count} verified receipt{execution.verified_receipt_count === 1 ? '' : 's'} / {execution.receipt_count} captured / {execution.reflection_recorded ? 'reflection recorded' : 'reflection missing'}</small></span><em>{execution.outcome_state === 'awaiting_outcome' ? 'Awaiting explicit outcome' : execution.outcome_state === 'learning_eligible' ? 'Learning eligible' : execution.outcome_state.replace(/_/g, ' ')}</em></p>) : <p>No execution receipt has been recorded yet.</p>}</div><p>Receipt metadata proves a reviewable execution. A quality-scored, explicitly accepted outcome is still required before PBOS learns a personal method.</p></section>
      <section className="pbos-chart"><div className="pbos-panel-heading"><p className="pbos-label">OUTCOME QUALITY</p><span>{qualitySeries.length ? `${qualitySeries.length} scored result${qualitySeries.length === 1 ? '' : 's'}` : 'awaiting score'}</span></div>{qualitySeries.length ? <RegisteredECharts option={qualityChart} style={{ height: 210 }} notMerge /> : <p className="pbos-empty-panel">No scored outcome has been recorded.</p>}</section>
      <section className="pbos-lineage"><p className="pbos-label">PERSONAL WORKFLOW LINEAGE</p><ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.12 }} minZoom={0.25} nodesDraggable={false} nodesConnectable={false}><Background /><Controls /></ReactFlow></section>
      <section><p className="pbos-label">STRATEGY ASSETS</p><div className="pbos-outcomes">{strategies.length ? strategies.map((item) => { const genome = item.genome as Record<string, unknown> | undefined; return <p key={String(item.artifact_id)}><CircleCheckBig size={15} /><span><strong>{String(item.strategy_name || 'Strategy')} v{String(item.version || 1)}</strong><small>{String(item.status || 'draft')} / {String(genome?.comparison_context || 'unclassified context')} / median {String(genome?.median_quality ?? 'unverified')}</small></span></p>; }) : <p>No Strategy Genome has passed the evidence gate yet.</p>}</div></section>
      <section><p className="pbos-label">VERIFIED CAPABILITIES</p><div className="pbos-outcomes">{capabilities.length ? capabilities.map((item) => <p key={String(item.artifact_id)}><CircleCheckBig size={15} />{String(item.name || 'Capability')}: level {String(item.level || 0)}</p>) : <p>No capability has enough verified evidence yet.</p>}</div></section>
      <section><p className="pbos-label">FAILURE PATTERNS</p><div className="pbos-outcomes">{failurePatterns.length ? failurePatterns.map((item, index) => <p key={`${String(item.kind)}-${index}`}><AlertTriangle size={15} /><span><strong>{String(item.kind || 'observed pattern').replace(/_/g, ' ').toUpperCase()}</strong><small>{String(item.count || 0)} evidence-backed record(s)</small></span></p>) : <p>No repeated failure pattern has enough evidence yet.</p>}</div></section>
      <section><p className="pbos-label">FEEDBACK FOR NEXT PLAN</p><div className="pbos-outcomes">{feedback.length ? feedback.map((item) => <p key={String(item.artifact_id)}><BrainCircuit size={15} />{String(item.statement || 'No feedback statement')}</p>) : <p>No feedback is available for the next plan.</p>}</div><p>Feedback remains an unverified execution direction until it is corroborated by outcomes and evidence.</p></section>
    </div>}
  </section>;
}
