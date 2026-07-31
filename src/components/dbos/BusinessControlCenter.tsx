import { useEffect, useRef, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { AlertTriangle, BrainCircuit, CheckCircle2, CircleStop, ClipboardCheck, Network, Play, RefreshCw, Send, ShieldCheck, Undo2, X } from 'lucide-react';

import {
  confirmDBOSMission,
  createDBOSMission,
  diagnoseDBOSMission,
  executeDBOSCapability,
  getDBOSControlCenter,
  listDbosMissions,
  recordDBOSDecision,
  recordDBOSFeedback,
  reconcileDBOSMissionVerifications,
  reviewDBOSMission,
  rollbackDBOSExecution,
  stopDBOSMission,
  DbosRequestError,
  type DBOSControlCenter,
  type DbosMission,
} from '../../api/dbosApi';
import { BlindspotIntakePanel } from './BlindspotIntakePanel';

type Props = {
  onClose: () => void;
  initialProjectId?: string;
  initialMissionId?: string;
  initialArtifactId?: string;
  initialRequestText?: string;
  autoStartIntake?: boolean;
  initialData?: DBOSControlCenter;
  onOpenPbos?: (missionId: string) => void;
};

type MissionDraft = {
  title: string; intent: string; intake_mode: 'business' | 'career'; role: string; industry: string;
  organization_stage: string; goal: string; time_horizon: string; constraints: string; stakeholders: string;
  decision_rights: string; success_metrics: string; evidence: string;
};

type AdaptiveModelRun = {
  provider?: string; model?: string; provider_calls?: number; reported_calls?: number; usage_complete?: boolean;
  total_tokens?: number | null; latency_ms?: number; attempt_count?: number; retry_count?: number;
};

type AdaptiveCompilation = {
  status?: string; reason?: string; context_available?: boolean;
  specificity?: { anchor_count?: number; matched_anchor_count?: number };
  model_run?: AdaptiveModelRun;
};

function adaptiveCompilation(value: unknown): AdaptiveCompilation | undefined {
  return value && typeof value === 'object' ? value as AdaptiveCompilation : undefined;
}

function graphProjection(graph: DBOSControlCenter['reasoning_graph'], focusedArtifactId = ''): { nodes: Node[]; edges: Edge[] } {
  const nodes = graph.nodes.map((node, index) => ({
    id: node.id,
    data: { label: node.label || node.id },
    position: { x: 30 + (index % 3) * 220, y: 32 + Math.floor(index / 3) * 110 },
    className: `dbos-flow-node dbos-flow-node--${node.type}${node.id === focusedArtifactId ? ' is-focused' : ''}`,
    ariaLabel: `${node.type}: ${node.label}`,
  }));
  return {
    nodes,
    edges: graph.edges.map((edge, index) => ({ id: `edge-${index}-${edge.source}-${edge.target}`, source: edge.source, target: edge.target, type: 'smoothstep' })),
  };
}

function capabilityList(center: DBOSControlCenter | null): string[] {
  return center?.selection?.selected?.map((item) => item.capability_name) ?? [];
}

function lineList(value: string): string[] {
  return value.split('\n').map((item) => item.trim()).filter(Boolean);
}

function evidenceList(value: string): Array<{ source: string; finding: string; strength: string }> {
  return value.split('\n').map((line) => line.split('|').map((item) => item.trim())).flatMap(([source, finding, strength]) => (
    source && finding ? [{ source, finding, strength: strength || 'medium' }] : []
  ));
}

export function BusinessControlCenter({ onClose, initialProjectId = 'default', initialMissionId = '', initialArtifactId = '', initialRequestText = '', autoStartIntake = false, initialData, onOpenPbos }: Props) {
  const [projectId, setProjectId] = useState(initialProjectId);
  const [missionId, setMissionId] = useState(initialData?.mission.artifact_id ?? initialMissionId);
  const [focusedArtifactId, setFocusedArtifactId] = useState(initialArtifactId);
  const [missions, setMissions] = useState<DbosMission[]>([]);
  const [center, setCenter] = useState<DBOSControlCenter | null>(initialData ?? null);
  const [authorized, setAuthorized] = useState(() => capabilityList(initialData ?? null));
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState('');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [decision, setDecision] = useState({ taskId: '', statement: '', rationale: '' });
  const [inspectedTaskId, setInspectedTaskId] = useState('');
  const [activeIntakeSessionId, setActiveIntakeSessionId] = useState('');
  const currentProjectIdRef = useRef(projectId.trim());
  const refreshSequenceRef = useRef(0);
  const initialLoadRef = useRef(false);
  const refreshRef = useRef<(preferredMissionId?: string) => Promise<void>>(async () => undefined);
  const [draft, setDraft] = useState<MissionDraft>({
    title: '', intent: '', intake_mode: 'business', role: '', industry: '', organization_stage: '', goal: '', time_horizon: '',
    constraints: '', stakeholders: '', decision_rights: '', success_metrics: '', evidence: '',
  });

  const refresh = async (preferredMissionId = missionId) => {
    const requestedProjectId = projectId.trim();
    if (!requestedProjectId) return;
    const refreshSequence = ++refreshSequenceRef.current;
    const isCurrentRequest = () => (
      refreshSequence === refreshSequenceRef.current && requestedProjectId === currentProjectIdRef.current
    );
    setBusy(true); setError('');
    let resolvedMissionId = '';
    try {
      const listed = await listDbosMissions(requestedProjectId);
      if (!isCurrentRequest()) return;
      setMissions(listed.missions);
      const nextMissionId = listed.missions.some((mission) => mission.artifact_id === preferredMissionId)
        ? preferredMissionId : (listed.missions[0]?.artifact_id || '');
      resolvedMissionId = nextMissionId;
      setMissionId(nextMissionId);
      if (!nextMissionId) {
        setCenter(null); setAuthorized([]); setActiveIntakeSessionId(''); return;
      }
      const value = await getDBOSControlCenter(requestedProjectId, nextMissionId);
      if (!isCurrentRequest()) return;
      setCenter(value);
      setAuthorized((current) => current.length ? current.filter((name) => capabilityList(value).includes(name)) : capabilityList(value));
    } catch (reason) {
      if (!isCurrentRequest()) return;
      if (reason instanceof DbosRequestError && reason.status === 404) {
        setMissions((current) => current.filter((mission) => mission.artifact_id !== resolvedMissionId));
        setMissionId(''); setCenter(null); setAuthorized([]); setActiveIntakeSessionId('');
        setError('The selected Mission is no longer available in this project. Its selection was cleared; start or choose another diagnosis.');
      } else if (reason instanceof TypeError && /failed to fetch|networkerror/i.test(reason.message)) {
        setError('The Business OS connection was interrupted. No Mission or capability was changed; refresh to retry.');
      } else {
        setError(reason instanceof Error ? reason.message : 'Unable to read the DBOS mission.');
      }
    } finally {
      if (isCurrentRequest()) setBusy(false);
    }
  };
  refreshRef.current = refresh;

  useEffect(() => {
    if (!initialData && !initialLoadRef.current) {
      initialLoadRef.current = true;
      void refreshRef.current();
    }
  }, [initialData]);
  useEffect(() => { setFocusedArtifactId(initialArtifactId); }, [initialArtifactId]);

  const createAndDiagnose = async () => {
    setBusy(true); setError(''); setBusyLabel('Creating a diagnosis record...');
    try {
      const created = await createDBOSMission({
        project_id: projectId.trim(), title: draft.title, intent: draft.intent, intake_mode: draft.intake_mode,
        context: {
          role: draft.role, industry: draft.industry, organization_stage: draft.organization_stage, goal: draft.goal,
          time_horizon: draft.time_horizon, constraints: lineList(draft.constraints), stakeholders: lineList(draft.stakeholders),
          decision_rights: lineList(draft.decision_rights), success_metrics: lineList(draft.success_metrics), evidence: evidenceList(draft.evidence),
          sop_generation_mode: 'adaptive',
        },
      });
      setMissionId(created.mission.artifact_id);
      setBusyLabel('Compiling a dynamic operating system from declared evidence and project context...');
      await diagnoseDBOSMission(projectId.trim(), created.mission.artifact_id);
      await refresh(created.mission.artifact_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Mission setup failed.');
    } finally { setBusy(false); setBusyLabel(''); }
  };

  const confirm = async () => {
    if (!missionId || !authorized.length) return;
    setBusy(true); setError('');
    try { await confirmDBOSMission(projectId, missionId, authorized); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Confirmation failed.'); }
    finally { setBusy(false); }
  };

  const execute = async (capabilityName: string) => {
    setBusy(true); setError('');
    const interrupted = center?.execution_results.some((item) => item.capability_name === capabilityName && item.execution_status === 'interrupted');
    const retryKey = interrupted ? `studio-manual-retry-${Date.now()}` : '';
    try { await executeDBOSCapability(projectId, missionId, capabilityName, retryKey); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Execution failed.'); }
    finally { setBusy(false); }
  };

  const submitFeedback = async () => {
    if (!feedback.trim()) return;
    setBusy(true); setError('');
    try { await recordDBOSFeedback(projectId, missionId, feedback); setFeedback(''); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Feedback could not be stored.'); }
    finally { setBusy(false); }
  };

  const submitDecision = async () => {
    const taskId = decision.taskId || tasks[0]?.task_id || '';
    if (!taskId || !decision.statement.trim()) return;
    setBusy(true); setError('');
    try {
      await recordDBOSDecision(projectId, missionId, { task_id: taskId, statement: decision.statement, rationale: decision.rationale, actor_id: 'studio' });
      setDecision({ taskId: '', statement: '', rationale: '' });
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Decision could not be recorded.'); }
    finally { setBusy(false); }
  };

  const stopMission = async () => {
    if (!missionId) return;
    setBusy(true); setError('');
    try {
      await stopDBOSMission(projectId, missionId, 'Stopped by the Studio reviewer before further capability dispatch.');
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Mission could not be stopped.');
    } finally { setBusy(false); }
  };

  const rollbackExecution = async (executionId: string, capabilityName: string) => {
    setBusy(true); setError('');
    try {
      await rollbackDBOSExecution(projectId, executionId, `Studio reviewer requested rollback for ${capabilityName}.`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Execution could not be rolled back.');
    } finally { setBusy(false); }
  };

  const requestAdvisorReview = async () => {
    if (!missionId) return;
    setBusy(true); setError(''); setBusyLabel('Requesting a governed advisory review...');
    try {
      await reviewDBOSMission(projectId, missionId, `studio-advisor-${Date.now()}`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Advisor review could not be recorded.');
    } finally { setBusy(false); setBusyLabel(''); }
  };

  const reconcileVerifications = async () => {
    if (!missionId) return;
    setBusy(true); setError(''); setBusyLabel('Reconciling persisted provider output proof...');
    try {
      await reconcileDBOSMissionVerifications(projectId, missionId);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Historical execution proof could not be reconciled.');
    } finally { setBusy(false); setBusyLabel(''); }
  };

  const toggleAuthorization = (name: string) => setAuthorized((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const selectMission = (nextMissionId: string) => {
    if (!nextMissionId) { setMissionId(''); setCenter(null); setAuthorized([]); setActiveIntakeSessionId(''); return; }
    void refresh(nextMissionId);
  };
  const graph = center ? graphProjection(center.reasoning_graph, focusedArtifactId) : { nodes: [], edges: [] };
  const focusedGraphNode = focusedArtifactId ? center?.reasoning_graph.nodes.find((node) => node.id === focusedArtifactId) : undefined;
  const focusedConnectionCount = focusedArtifactId ? (center?.reasoning_graph.edges.filter((edge) => edge.source === focusedArtifactId || edge.target === focusedArtifactId).length ?? 0) : 0;
  const tasks = center?.dynamic_sop?.phases.flatMap((phase) => phase.tasks) ?? [];
  const inspectedTask = tasks.find((task) => task.task_id === inspectedTaskId) ?? tasks[0];
  const inspectedExecution = inspectedTask ? center?.execution_results.find((item) => item.capability_name === inspectedTask.capability_name) : undefined;
  const inspectedVerification = inspectedExecution ? (center?.verifications ?? []).find((item) => item.execution_id === inspectedExecution.artifact_id) : undefined;
  const verificationByExecution = new Map((center?.verifications ?? []).map((item) => [item.execution_id, item]));
  const hasTaskDecision = (taskId: string) => center?.decisions.some((item) => item.metadata?.task_id === taskId) ?? false;
  const hasInterruptedAttempt = (capabilityName: string) => center?.execution_results.some((item) => item.capability_name === capabilityName && item.execution_status === 'interrupted') ?? false;
  const confirmed = center?.mission.mission_status === 'confirmed' || center?.mission.status === 'confirmed';
  const terminal = ['completed', 'failed', 'stopped', 'rolled_back'].includes(String(center?.mission.mission_status || center?.mission.status || ''));
  const evidence = center?.evidence ?? [];
  const gaps = center?.gaps ?? [];
  const risks = center?.risks ?? [];
  const adaptive = adaptiveCompilation(center?.dynamic_sop?.metadata?.adaptive_compilation);
  const adaptiveModelRun = adaptive?.model_run;
  const missionIntakeSessionId = typeof center?.mission.context?.intake_session_id === 'string'
    ? center.mission.context.intake_session_id : '';
  const visibleIntakeSessionId = activeIntakeSessionId || missionIntakeSessionId;
  const adaptiveStatus = adaptive?.status === 'completed'
    ? `PROJECT CONTEXT REFINED${adaptive.context_available ? '' : ' (MISSION EVIDENCE ONLY)'}`
    : adaptive?.reason === 'model_output_not_grounded'
      ? 'SAFE DETERMINISTIC BASELINE (MODEL OUTPUT DID NOT CARRY MISSION ANCHORS)'
      : 'SAFE DETERMINISTIC BASELINE (ADAPTIVE OUTPUT DID NOT PASS REVIEW)';

  return <section className="dbos-control-center" aria-label="Business Control Center">
    <header className="dbos-control-center__header">
      <div><p>Dynamic Business OS</p><h2>Business Control Center</h2><span>Diagnosis, authorization, execution evidence, and reusable feedback.</span></div>
      <div className="dbos-control-center__actions">
        <label>Project<input aria-label="DBOS project ID" value={projectId} onChange={(event) => {
          const nextProjectId = event.target.value;
          if (nextProjectId !== projectId) {
            currentProjectIdRef.current = nextProjectId.trim();
            refreshSequenceRef.current += 1;
            setMissionId(''); setFocusedArtifactId(''); setMissions([]); setCenter(null); setAuthorized([]); setActiveIntakeSessionId(''); setError('');
          }
          setProjectId(nextProjectId);
        }} disabled={busy} /></label>
        {missions.length > 0 && <label>Mission<select aria-label="DBOS mission" value={missionId} onChange={(event) => selectMission(event.target.value)} disabled={busy}><option value="">New mission</option>{missions.map((mission) => <option key={mission.artifact_id} value={mission.artifact_id}>{mission.title}</option>)}</select></label>}
        {onOpenPbos && missionId && <button type="button" className="dbos-icon-button" aria-label="Open PBOS plan for this Mission" title="Open PBOS plan for this Mission" onClick={() => onOpenPbos(missionId)} disabled={busy}><BrainCircuit size={16} /></button>}
        <button type="button" className="dbos-icon-button" aria-label="Refresh DBOS control center" title="Refresh" onClick={() => void refresh()} disabled={busy}><RefreshCw size={16} /></button>
        <button type="button" className="dbos-icon-button" aria-label="Close Business Control Center" title="Close" onClick={onClose}><X size={17} /></button>
      </div>
    </header>

    {error && <div className="dbos-alert" role="alert"><AlertTriangle size={16} /><span>{error}</span></div>}

    {!center ? <><BlindspotIntakePanel projectId={projectId.trim()} disabled={busy} initialRequestText={initialRequestText} autoStart={autoStartIntake} onMissionConverted={(nextMissionId) => { setActiveIntakeSessionId(''); setMissionId(nextMissionId); void refresh(nextMissionId); }} /><details className="dbos-manual-intake"><summary>Manual Mission</summary><form className="dbos-intake" aria-busy={busy} onSubmit={(event) => { event.preventDefault(); void createAndDiagnose(); }}>
      <div className="dbos-intake__intro"><ShieldCheck size={22} /><div><strong>Start with a diagnosis, not an SOP title.</strong><span>The Mission stays non-executable until its capability grants are reviewed and confirmed.</span></div></div>
      {busyLabel && <div className="dbos-intake__status" role="status" aria-live="polite"><RefreshCw size={15} /><span>{busyLabel}</span></div>}
      <label>Mission title<input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>Intent<textarea required value={draft.intent} onChange={(event) => setDraft({ ...draft, intent: event.target.value })} /></label>
      <label>Entry mode<select value={draft.intake_mode} onChange={(event) => setDraft({ ...draft, intake_mode: event.target.value as 'business' | 'career' })}><option value="business">Business</option><option value="career">Career</option></select></label>
      <label>Role<input value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })} /></label>
      <label>Industry<input value={draft.industry} onChange={(event) => setDraft({ ...draft, industry: event.target.value })} /></label>
      <label>Organization stage<input value={draft.organization_stage} onChange={(event) => setDraft({ ...draft, organization_stage: event.target.value })} /></label>
      <label>Goal<input value={draft.goal} onChange={(event) => setDraft({ ...draft, goal: event.target.value })} /></label>
      <label>Time horizon<input value={draft.time_horizon} onChange={(event) => setDraft({ ...draft, time_horizon: event.target.value })} /></label>
      <label>Constraints<textarea value={draft.constraints} onChange={(event) => setDraft({ ...draft, constraints: event.target.value })} placeholder="One constraint per line" /></label>
      <label>Stakeholders<textarea value={draft.stakeholders} onChange={(event) => setDraft({ ...draft, stakeholders: event.target.value })} placeholder="One owner or reviewer per line" /></label>
      <label>Decision rights<textarea value={draft.decision_rights} onChange={(event) => setDraft({ ...draft, decision_rights: event.target.value })} placeholder="Who accepts, stops, or escalates per line" /></label>
      <label>Success metrics<textarea value={draft.success_metrics} onChange={(event) => setDraft({ ...draft, success_metrics: event.target.value })} placeholder="One measurable outcome per line" /></label>
      <label className="dbos-intake__evidence">Observed evidence<textarea aria-label="Observed evidence" value={draft.evidence} onChange={(event) => setDraft({ ...draft, evidence: event.target.value })} placeholder={'Source | finding | strength\nWeekly dashboard | Cart conversion fell 12% | high'} /></label>
      <button type="submit" disabled={busy || !projectId.trim()}><Network size={16} />{busyLabel || 'Create diagnosis'}</button>
    </form></details></> : <>
      {visibleIntakeSessionId && <BlindspotIntakePanel projectId={projectId.trim()} sessionId={visibleIntakeSessionId} disabled={busy} onMissionConverted={(nextMissionId) => { setActiveIntakeSessionId(visibleIntakeSessionId); setMissionId(nextMissionId); void refresh(nextMissionId); }} />}
      <div className="dbos-metrics">
        <div><small>MISSION</small><strong>{String(center.mission.status || center.mission.mission_status || 'draft')}</strong></div>
        <div><small>CAPABILITIES</small><strong>{center.selection?.selected?.length ?? 0}</strong></div>
        <div><small>COMPLETED / VERIFIED</small><strong>{center.health.executions_completed ?? 0} / {Number(center.health.executions_verified ?? 0)}</strong></div>
        <div><small>OPEN / EVIDENCE GAPS</small><strong>{center.health.unresolved_gaps ?? 0} / {center.health.evidence_gaps ?? 0}</strong></div>
        <div><small>EXTERNAL WORKERS</small><strong>{Number(center.health.external_worker_runs_active ?? 0)} active | {Number(center.health.external_worker_runs_completed ?? 0)} complete | {Number(center.health.external_worker_runs_cancelled ?? 0) + Number(center.health.external_worker_runs_interrupted ?? 0)} stopped</strong></div>
        <div><small>ADVISOR REVIEWS</small><strong>{Number(center.health.advisor_reviews_completed ?? 0)} complete | {Number(center.health.advisor_findings_open ?? 0)} findings</strong></div>
      </div>
      <div className="dbos-layout">
        <aside className="dbos-panel dbos-panel--mission"><header><span>MISSION GATE</span><strong>{center.mission.title}</strong></header>
          <p>{center.diagnosis?.goal || center.diagnosis?.role || 'No diagnosed goal'}</p>
          <dl><div><dt>Industry</dt><dd>{center.diagnosis?.industry || 'Missing'}</dd></div><div><dt>Stage</dt><dd>{center.diagnosis?.organization_stage || 'Missing'}</dd></div><div><dt>Constraints</dt><dd>{center.diagnosis?.constraints?.join(', ') || 'None declared'}</dd></div><div><dt>Stakeholders</dt><dd>{center.diagnosis?.stakeholders?.join(', ') || 'Not declared'}</dd></div><div><dt>Decision rights</dt><dd>{center.diagnosis?.decision_rights?.join(', ') || 'Not declared'}</dd></div></dl>
          {!confirmed && !terminal && <div className="dbos-authorization"><span>Select authorized capabilities</span>{center.selection?.selected?.map((item) => <label key={`${item.capability_name}-${item.task_family}`}><input aria-label={`Authorize ${item.capability_name}`} type="checkbox" checked={authorized.includes(item.capability_name)} onChange={() => toggleAuthorization(item.capability_name)} /><i>{item.task_family.replace(/_/g, ' ')}</i><b>{item.capability_name}</b></label>)}<button type="button" onClick={() => void confirm()} disabled={busy || !authorized.length}><ShieldCheck size={15} />Confirm {authorized.length} {authorized.length === 1 ? 'capability' : 'capabilities'}</button></div>}
          {confirmed && <div className="dbos-confirmed"><CheckCircle2 size={16} /><span>Authorization recorded. Only granted capabilities can run.</span></div>}
          {!terminal && <button type="button" className="dbos-governance-action" aria-label="Stop mission" title="Stop mission" onClick={() => void stopMission()} disabled={busy}><CircleStop size={15} />Stop mission</button>}
        </aside>
        <main className="dbos-main">
          {focusedArtifactId && <section className="dbos-panel dbos-artifact-focus" aria-label="Focused artifact inspector"><header><span>ARTIFACT FOCUS</span><strong>{focusedGraphNode?.label || 'Record not present in this bounded mission graph'}</strong></header><dl><div><dt>Durable record</dt><dd>{focusedArtifactId}</dd></div><div><dt>Type</dt><dd>{focusedGraphNode?.type || 'unavailable'}</dd></div><div><dt>Status</dt><dd>{focusedGraphNode?.status || 'unavailable'}</dd></div><div><dt>Persisted connections</dt><dd>{focusedConnectionCount}</dd></div></dl><small>{focusedGraphNode ? 'Opened from a scoped operations action. Select another graph node to inspect a different durable record.' : 'The action target is retained, but it is outside the current bounded mission projection.'}</small></section>}
          <section className="dbos-panel"><header><span>DYNAMIC SOP</span><strong>{center.dynamic_sop?.title}</strong></header>{adaptive && <small className="dbos-compilation-status">{adaptiveStatus}</small>}{adaptiveModelRun && <dl className="dbos-model-run" aria-label="Model run evidence"><div><dt>Model run</dt><dd>{adaptiveModelRun.provider || 'provider'} / {adaptiveModelRun.model || 'model'}</dd></div><div><dt>Calls</dt><dd>{adaptiveModelRun.provider_calls ?? 0} provider / {adaptiveModelRun.reported_calls ?? 0} reported</dd></div><div><dt>Attempts</dt><dd>{adaptiveModelRun.attempt_count ?? 1}{adaptiveModelRun.retry_count ? ` with ${adaptiveModelRun.retry_count} retry` : ''}</dd></div><div><dt>Usage</dt><dd>{adaptiveModelRun.total_tokens == null ? 'unreported' : `${adaptiveModelRun.total_tokens} tokens`}{adaptiveModelRun.usage_complete ? '' : ' (partial)'}</dd></div><div><dt>Grounding</dt><dd>{adaptive.specificity ? `${adaptive.specificity.matched_anchor_count ?? 0} / ${adaptive.specificity.anchor_count ?? 0} anchors` : 'not evaluated'}</dd></div><div><dt>Latency</dt><dd>{adaptiveModelRun.latency_ms ? `${adaptiveModelRun.latency_ms} ms` : 'unreported'}</dd></div></dl>}<p className="dbos-objective">{center.dynamic_sop?.objective}</p>{center.dynamic_sop?.diagnostic_summary && <p className="dbos-diagnostic-summary">{center.dynamic_sop.diagnostic_summary}</p>}{center.dynamic_sop?.quality_gates?.length ? <ul className="dbos-quality-gates">{center.dynamic_sop.quality_gates.map((gate) => <li key={gate}>{gate}</li>)}</ul> : null}<div className="dbos-timeline">{center.dynamic_sop?.phases.map((phase) => <article key={phase.phase_id}><header><span>{phase.phase_id}</span><strong>{phase.title}</strong><small>{phase.objective}</small></header>{phase.tasks.map((task) => { const taskHasDecision = hasTaskDecision(task.task_id); const isManualRetry = hasInterruptedAttempt(task.capability_name); return <div className="dbos-task" key={task.task_id}><button type="button" className="dbos-task__inspect" aria-label={`Inspect ${task.title}`} onClick={() => setInspectedTaskId(task.task_id)}><strong>{task.title}</strong><span>{task.owner} - {task.deliverable}</span><small>{task.metric}</small></button><button type="button" aria-label={isManualRetry ? `Manually retry ${task.capability_name}` : `Execute ${task.capability_name}`} title={taskHasDecision ? (isManualRetry ? 'Manual retry after interrupted execution' : `Execute ${task.capability_name}`) : 'Record the task decision before execution'} disabled={busy || !confirmed || !authorized.includes(task.capability_name) || !taskHasDecision} onClick={() => void execute(task.capability_name)}><Play size={14} fill="currentColor" /></button></div>; })}</article>)}</div></section>
          {inspectedTask && <section className="dbos-panel dbos-task-inspector"><header><span>TASK INSPECTOR</span><strong>{inspectedTask.title}</strong></header><dl><div><dt>Owner and deliverable</dt><dd>{inspectedTask.owner} - {inspectedTask.deliverable}</dd></div><div><dt>Trigger and metric</dt><dd>{inspectedTask.trigger} - {inspectedTask.metric}</dd></div><div><dt>Decision and risk</dt><dd>{inspectedTask.decision_point} {inspectedTask.risk}</dd></div><div><dt>Check and learning loop</dt><dd>{inspectedTask.check} {inspectedTask.retrospect}</dd></div><div><dt>Lineage</dt><dd>{inspectedTask.parent_refs.join(', ')}</dd></div><div><dt>Execution / rollback</dt><dd>{inspectedExecution ? `${inspectedExecution.execution_status}${inspectedExecution.rollback?.status ? ` - rollback: ${String(inspectedExecution.rollback.status)}` : ''}` : 'Not executed'}{inspectedVerification ? ` - verification: ${inspectedVerification.verification_status}` : ''}</dd></div></dl>{inspectedExecution && ['completed', 'failed', 'rejected'].includes(String(inspectedExecution.execution_status)) && <button type="button" className="dbos-governance-action" aria-label={`Rollback ${inspectedExecution.capability_name}`} title="Rollback execution" onClick={() => void rollbackExecution(inspectedExecution.artifact_id, inspectedExecution.capability_name)} disabled={busy}><Undo2 size={15} />Rollback result</button>}</section>}
          <section className="dbos-panel dbos-panel--diagnosis"><header><span>DIAGNOSIS AND EVIDENCE</span><strong>{center.diagnosis?.coverage ? `${Math.round(center.diagnosis.coverage * 100)}% declared context coverage` : 'Awaiting diagnosis'}</strong></header><div className="dbos-evidence-grid"><article><strong>Success metrics</strong><ul>{center.diagnosis?.success_metrics?.map((item) => <li key={item}>{item}</li>) || <li>Not declared</li>}</ul></article><article><strong>Operating hypotheses</strong><ul>{center.diagnosis?.operating_hypotheses?.map((item) => <li key={item}>{item}</li>) || <li>Not generated</li>}</ul></article><article><strong>Evidence</strong><ul>{evidence.length ? evidence.map((item) => <li key={item.artifact_id}><b>{item.source}</b>{item.finding}</li>) : <li>No source-backed evidence declared.</li>}</ul></article><article><strong>Gaps and risks</strong><ul>{[...gaps, ...risks].length ? [...gaps, ...risks].slice(0, 6).map((item) => <li key={item.artifact_id}>{String(item.gap_statement || item.risk_statement || item.label || '')}</li>) : <li>No open items.</li>}</ul></article></div></section>
          <section className="dbos-panel dbos-panel--capabilities"><header><span>CAPABILITY RATIONALE</span><strong>{String(center.selection?.selection_reasoning || '')}</strong></header><ul className="dbos-capability-list">{center.selection?.selected?.map((item) => <li key={`${item.capability_name}-${item.task_family}`}><div><b>{item.task_family.replace(/_/g, ' ')}</b><strong>{Math.round(item.score * 100)}%</strong></div><small>{item.reasons.join(' ')}</small></li>)}</ul>{center.selection?.rejected?.length ? <p className="dbos-rejected">Not selected: {center.selection.rejected.map((item) => item.capability_name).join(', ')}</p> : null}</section>
          <section className="dbos-panel dbos-panel--decisions"><header><span>DECISION LOG</span><strong>{center.decisions.length} persisted decisions</strong></header>{center.decisions.length ? <ol>{center.decisions.map((item) => <li key={item.artifact_id}><strong>{item.decision_statement}</strong><small>{item.rationale || item.recommendation || 'No rationale recorded.'}</small></li>)}</ol> : <p className="dbos-empty">No decision has been recorded. Decision points remain visible in the Dynamic SOP until reviewed.</p>}<form className="dbos-decision-form" onSubmit={(event) => { event.preventDefault(); void submitDecision(); }}><label>Task<select aria-label="Decision task" value={decision.taskId || tasks[0]?.task_id || ''} onChange={(event) => setDecision({ ...decision, taskId: event.target.value })}>{tasks.map((task) => <option key={task.task_id} value={task.task_id}>{task.title}</option>)}</select></label><label>Decision<input aria-label="Decision statement" value={decision.statement} onChange={(event) => setDecision({ ...decision, statement: event.target.value })} placeholder="Record the accepted choice" /></label><label>Rationale<textarea value={decision.rationale} onChange={(event) => setDecision({ ...decision, rationale: event.target.value })} placeholder="Evidence, tradeoff, and owner rationale" /></label><button type="submit" disabled={busy || !tasks.length || !decision.statement.trim()}><Send size={15} />Record decision</button></form></section>
          <section className="dbos-panel dbos-panel--events"><header><span>EXECUTION LEDGER</span><strong>{center.execution_results.length} audited attempts</strong></header>{Number(center.health.executions_unverified ?? 0) > 0 && <button type="button" className="dbos-governance-action" aria-label="Reconcile historic execution proof" title="Verify persisted provider outputs without rerunning work" onClick={() => void reconcileVerifications()} disabled={busy}><ShieldCheck size={15} />Reconcile provider proof</button>}{center.execution_results.length ? <ol>{center.execution_results.map((execution) => { const verification = verificationByExecution.get(execution.execution_id); return <li key={execution.artifact_id}><i data-status={execution.execution_status} /><div><strong>{execution.capability_name}</strong><small>{execution.execution_status}{verification ? ` | verification: ${verification.verification_status}` : ' | verification: pending'}{execution.error ? `: ${execution.error}` : ''}</small></div></li>; })}</ol> : <p className="dbos-empty">No capability has been executed. The graph shows planning lineage, not claimed runtime success.</p>}</section>
           <section className="dbos-panel dbos-panel--events"><header><span>EXTERNAL WORKER LEDGER</span><strong>{center.external_worker_runs?.length ?? 0} governed attempts</strong></header>{center.external_worker_runs?.length ? <ol>{center.external_worker_runs.map((run) => <li key={run.artifact_id}><i data-status={run.worker_status} /><div><strong>{run.worker_id}{run.model_id ? ` | ${run.model_id}` : ''}</strong><small>{run.worker_status}{run.egress_host ? ` | ${run.egress_host}` : ''}{run.reason ? `: ${run.reason}` : ''}</small></div></li>)}</ol> : <p className="dbos-empty">No external worker has been queued. A policy approval is not an execution claim.</p>}</section>
           <section className="dbos-panel dbos-panel--events"><header><span>ADVISOR REVIEW</span><strong>{center.advisor_reviews?.length ?? 0} recorded reviews</strong></header><button type="button" className="dbos-governance-action" aria-label="Run advisory review" title="Run advisory review" onClick={() => void requestAdvisorReview()} disabled={busy}><ClipboardCheck size={15} />Review mission</button>{center.advisor_reviews?.length ? <ol>{center.advisor_reviews.map((review) => <li key={review.artifact_id}><i data-status={review.advisor_status} /><div><strong>{review.verdict || review.advisor_status}</strong><small>{review.summary || review.error_category || review.advisor_status}</small>{review.findings?.length ? <ul>{review.findings.map((finding, index) => <li key={`${review.artifact_id}-${index}`}>{finding.severity}: {finding.statement}{finding.recommendation ? ` - ${finding.recommendation}` : ''}</li>)}</ul> : null}</div></li>)}</ol> : <p className="dbos-empty">No advisory review is recorded. A review can recommend changes but cannot authorize or execute a task.</p>}</section>
          {center.sop_routing_evaluation && <section className="dbos-panel dbos-panel--routing-evaluation"><header><span>ROUTING EVALUATION</span><strong>{center.sop_routing_evaluation.evaluation_status}</strong></header><p>{center.sop_routing_evaluation.positive_case_count} positive, {center.sop_routing_evaluation.near_negative_case_count} near-negative, {center.sop_routing_evaluation.holdout_case_count} isolated holdout cases.</p><p>Holdouts: {center.sop_routing_evaluation.holdout_passed ? 'passed' : 'failed'}.</p>{center.sop_routing_evaluation.findings?.length ? <ul>{center.sop_routing_evaluation.findings.map((finding) => <li key={finding}>{finding}</li>)}</ul> : <small>Versioned deterministic routing evidence is attached to this mission.</small>}</section>}
        </main>
        <aside className="dbos-panel dbos-panel--graph"><header><span>REASONING GRAPH</span><strong>{graph.nodes.length} nodes</strong></header>{graph.nodes.length ? <div className="dbos-graph"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} minZoom={0.4} maxZoom={1.5} onNodeClick={(_, node) => setFocusedArtifactId(node.id)}><Background gap={20} size={1} /><Controls showInteractive={false} /></ReactFlow></div> : <p className="dbos-empty">No persisted lineage is available.</p>}{center.runtime_context && <div className="dbos-runtime-context"><strong>CONTEXT SNAPSHOT</strong><dl><div><dt>Policy</dt><dd>{center.runtime_context.context_revision}</dd></div><div><dt>Budget</dt><dd>{center.runtime_context.estimated_tokens} / {center.runtime_context.context_window_tokens} tokens</dd></div><div><dt>Knowledge refs</dt><dd>{center.runtime_context.source_ids.length} sources, {center.runtime_context.method_ids.length} methods</dd></div></dl><small>{center.runtime_context.compaction_required ? 'Context requires review before model expansion.' : 'Redacted composition manifest recorded.'}</small></div>}<div className="dbos-feedback"><label>Outcome feedback<textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="What changed, what failed, and what should be reused?" /></label><button type="button" aria-label="Record feedback" title="Record feedback" onClick={() => void submitFeedback()} disabled={busy || !feedback.trim() || !center.execution_results.length}><Send size={15} /></button></div>{center.memories?.length ? <ul className="dbos-memory-list">{center.memories.map((memory) => <li key={String(memory.artifact_id || memory.statement || 'memory')}>{String(memory.statement || '')}</li>)}</ul> : null}</aside>
      </div>
    </>}
  </section>;
}
