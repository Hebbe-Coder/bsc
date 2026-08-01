import { FormEvent, useCallback, useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { AlertTriangle, BrainCircuit, CircleCheckBig, FileCheck2, KeyRound, RefreshCw, ShieldCheck, Workflow, X } from 'lucide-react';
import {
  capturePbosWorkspaceExecution,
  compilePbosPlan,
  fetchPbosCockpit,
  fetchPbosProfile,
  recordPbosExecution,
  recordPbosFeedback,
  recordPbosOutcome,
  reviewPbosExecutionAttribution,
  reviewPbosOutcome,
  savePbosProfile,
  type PbosCockpit,
  type PbosProfile,
} from '../../api/pbosApi';
import { fetchGrowthStage, type GrowthRecord } from '../../api/growthApi';
import RegisteredECharts from '../charts/RegisteredECharts';

type Props = {
  projectId: string;
  onClose: () => void;
  runtimeAccessKey?: string;
  onConfigureAccess?: () => void;
  initialMissionId?: string;
  onStartMission?: () => void;
  onOpenOutputReview?: (outputId: string) => void;
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

function isUnreadableLegacyText(value: unknown): boolean {
  const text = String(value ?? '').trim();
  if (!text) return false;
  if (text.includes('\uFFFD')) return true;
  const characters = Array.from(text).filter((character) => !/\s/u.test(character));
  const questionCount = characters.filter((character) => character === '?').length;
  if (questionCount < 3 || characters.length === 0) return false;
  return /\?{3,}/u.test(text) || questionCount / characters.length >= 0.25;
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

function scrollToPbosPanel(panelId: string) {
  if (typeof document === 'undefined') return;
  document.getElementById(panelId)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
}

type OutcomeReviewDraft = {
  qualityScore: string;
  outcomeSummary: string;
  observedImpacts: string;
  reviewNote: string;
};

type ExecutionAttribution = 'owner' | 'agent' | 'mixed';

type AttributionReviewDraft = {
  executionAttribution: ExecutionAttribution;
  ownerContribution: string;
  reviewNote: string;
};

function readableRequirement(value: string): string {
  return value.replace(/_/g, ' ');
}

function executionAttributionLabel(value: string): string {
  if (value === 'owner') return 'Owner work';
  if (value === 'mixed') return 'Co-authored work';
  if (value === 'agent') return 'Agent work';
  return 'Attribution required';
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

type PendingOutputReview = {
  id: string;
  source: 'Copilot' | 'External';
};

function pendingOutputReviews(records: GrowthRecord[]): PendingOutputReview[] {
  return records
    .filter((record) => String(record.status || '') === 'registered')
    .map((record) => {
      const metadata = planObject(record.metadata);
      const pluginId = String(metadata.obsidian_plugin_id || metadata.plugin_id || '');
      const legacyPlugin = String(metadata.obsidian_plugin || metadata.plugin_name || '').toLowerCase();
      const originalPath = String(metadata.original_path || record.vault_path || '').replace(/\\/g, '/').toLowerCase();
      const isCopilot = pluginId === 'copilot-agent'
        || legacyPlugin.includes('copilot')
        || /(?:^|\/)04_outputs\/copilot(?:\/|$)/.test(originalPath);
      return {
        id: String(record.id || ''),
        source: isCopilot ? 'Copilot' as const : 'External' as const,
      };
    })
    .filter((record) => Boolean(record.id))
    .slice(0, 12);
}

export function PersonalGrowthCockpit({ projectId, onClose, runtimeAccessKey = '', onConfigureAccess, initialMissionId = '', onStartMission, onOpenOutputReview }: Props) {
  const [data, setData] = useState<PbosCockpit | null>(null);
  const [profile, setProfile] = useState<PbosProfile | null>(null);
  const [error, setError] = useState('');
  const [accessState, setAccessState] = useState<'required' | 'rejected' | null>(null);
  const [saving, setSaving] = useState(false);
  const [recompiling, setRecompiling] = useState(false);
  const [role, setRole] = useState('');
  const [industry, setIndustry] = useState('');
  const [organizationStage, setOrganizationStage] = useState('');
  const [focus, setFocus] = useState('');
  const [goals, setGoals] = useState('');
  const [workStyle, setWorkStyle] = useState('');
  const [decisionStyle, setDecisionStyle] = useState('');
  const [resources, setResources] = useState('');
  const [constraints, setConstraints] = useState('');
  const [reflection, setReflection] = useState('');
  const [outcomeSummary, setOutcomeSummary] = useState('');
  const [observedImpacts, setObservedImpacts] = useState('');
  const [blocker, setBlocker] = useState('');
  const [feedbackDraft, setFeedbackDraft] = useState('');
  const [evidencePaths, setEvidencePaths] = useState('');
  const [executionAttribution, setExecutionAttribution] = useState<ExecutionAttribution>('owner');
  const [ownerContribution, setOwnerContribution] = useState('');
  const [acceptanceConfirmed, setAcceptanceConfirmed] = useState(false);
  const [qualityScore, setQualityScore] = useState('');
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, OutcomeReviewDraft>>({});
  const [reviewingOutcomeId, setReviewingOutcomeId] = useState('');
  const [attributionReviewDrafts, setAttributionReviewDrafts] = useState<Record<string, AttributionReviewDraft>>({});
  const [reviewingAttributionExecutionId, setReviewingAttributionExecutionId] = useState('');
  const [creatingOutcomeExecutionId, setCreatingOutcomeExecutionId] = useState('');
  const [pendingOutputState, setPendingOutputState] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [pendingOutputs, setPendingOutputs] = useState<PendingOutputReview[]>([]);
  const load = useCallback(async () => {
    if (!runtimeAccessKey.trim()) {
      setData(null); setProfile(null); setPendingOutputs([]); setPendingOutputState('unavailable'); setError(''); setAccessState('required');
      return;
    }
    try {
      setError(''); setAccessState(null); setPendingOutputState('loading');
      const dLayerResult = fetchGrowthStage(projectId, 'D', 100)
        .then((result) => ({ state: 'ready' as const, outputs: pendingOutputReviews(result.records) }))
        .catch(() => ({ state: 'unavailable' as const, outputs: [] as PendingOutputReview[] }));
      const [cockpit, profileResult, dLayer] = await Promise.all([
        fetchPbosCockpit(projectId, initialMissionId),
        fetchPbosProfile(projectId),
        dLayerResult,
      ]);
      setData(cockpit);
      setPendingOutputState(dLayer.state);
      setPendingOutputs(dLayer.outputs);
      const nextProfile = profileResult.profile ?? cockpit.profile;
      setProfile(nextProfile);
      setRole(nextProfile?.role ?? '');
      setIndustry(nextProfile?.industry ?? '');
      setOrganizationStage(nextProfile?.organization_stage ?? '');
      setFocus((nextProfile?.focus ?? []).join(', '));
      setGoals((nextProfile?.goals ?? []).join(', '));
      setWorkStyle((nextProfile?.work_style ?? []).join(', '));
      setDecisionStyle((nextProfile?.decision_style ?? []).join(', '));
      setResources((nextProfile?.resources ?? []).join(', '));
      setConstraints((nextProfile?.constraints ?? []).join(', '));
    } catch (reason) {
      if (isAccessFailure(reason)) {
        setData(null); setProfile(null); setPendingOutputs([]); setPendingOutputState('unavailable'); setError(''); setAccessState('rejected');
        return;
      }
      setError(reason instanceof Error ? reason.message : 'Unable to load PBOS');
    }
  }, [initialMissionId, projectId, runtimeAccessKey]);
  useEffect(() => { void load(); }, [load]);
  const capabilities = data?.capabilities ?? [];
  const executions = data?.executions ?? [];
  const outcomes = data?.outcomes ?? [];
  const outcomeObservations = data?.outcome_observations ?? [];
  const feedback = data?.feedback ?? [];
  const readableFeedback = feedback.filter((item) => !isUnreadableLegacyText(item.statement));
  const unreadableFeedbackCount = feedback.length - readableFeedback.length;
  const strategies = data?.strategies ?? [];
  const failurePatterns = data?.failure_patterns ?? [];
  const projectHealth = data?.project_health ?? {};
  const todayAction = planObject(data?.today_action);
  const scope = planObject(data?.scope);
  const scopedMissionId = String(scope.mission_id || initialMissionId || '').trim();
  const scopedMissionTitle = String(scope.title || '').trim();
  const generation = planGenerationStatus(data?.today);
  const acceptedOutcomes = outcomes.filter((item) => item.acceptance_status === 'accepted').length;
  const qualitySeries = outcomes.filter((item) => item.acceptance_status === 'accepted' && typeof item.quality_score === 'number').slice().reverse();
  const pendingReviewOutcomes = outcomes.filter((item) => String(item.acceptance_status || '') === 'unverified');
  const awaitingOutcomeExecutions = executions.filter((item) => item.outcome_state === 'awaiting_outcome');
  const unattributedExecutions = executions.filter((item) => item.attribution_reviewable || item.execution_attribution === 'unattributed');
  const contextReferences = stringRefs(data?.today?.knowledge_context_refs);
  const strategyReferences = stringRefs(data?.today?.strategy_refs);
  const appliedStrategies = strategies.filter((item) => strategyReferences.includes(String(item.artifact_id || '')));
  const knowledgeContextReady = projectHealth.knowledge_context_ready ?? contextReferences.length > 0;
  const personalLearningReady = projectHealth.personal_learning_ready ?? projectHealth.evidence_ready ?? false;
  const contextReferenceCount = Number(projectHealth.knowledge_context_reference_count ?? contextReferences.length);
  const personalizationReadiness = data?.personalization_readiness ?? {
    state: personalLearningReady ? 'personalized' : 'learning_evidence_required',
    declared_profile_ready: Boolean(profile),
    missing_profile_fields: [],
    accepted_outcome_count: Number(projectHealth.eligible_personal_outcomes ?? 0),
    required_comparable_outcomes: 3,
  };
  const readinessState = String(personalizationReadiness.state || 'learning_evidence_required');
  const readinessLabel = readinessState === 'personalized'
    ? 'Personal strategy grounded'
    : readinessState === 'profile_context_required'
      ? 'Profile context needed'
      : readinessState === 'promotion_evaluation_required'
        ? 'Promotion evaluation ready'
        : 'Learning evidence needed';
  const readinessMissing = (personalizationReadiness.missing_profile_fields ?? []).map((field) => {
    if (field === 'role') return '角色';
    if (field === 'industry') return '领域';
    if (field === 'organization_stage') return '当前阶段';
    return field.replace(/_/g, ' ');
  });
  const profileSetupComplete = readinessMissing.length === 0;
  const outcomeReviewComplete = pendingReviewOutcomes.length === 0 && awaitingOutcomeExecutions.length === 0;
  const comparableOutcomeCount = Number(personalizationReadiness.accepted_outcome_count ?? 0);
  const requiredComparableOutcomes = Number(personalizationReadiness.required_comparable_outcomes ?? 3);
  const outcomeActionTarget = pendingReviewOutcomes.length > 0
    ? 'pbos-outcome-review'
    : 'pbos-three-minute-reflection';
  const outcomeActionLabel = pendingReviewOutcomes.length > 0 ? '审阅待确认结果' : '记录真实交付';
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
        role: role.trim(), industry: industry.trim(), organization_stage: organizationStage.trim(),
        focus: splitList(focus), goals: splitList(goals), resources: splitList(resources), constraints: splitList(constraints),
        work_style: splitList(workStyle), decision_style: splitList(decisionStyle),
        preferences: { architecture_first: true, evidence_first: true },
      });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save profile'); }
    finally { setSaving(false); }
  };
  const recompileCurrentPlan = async () => {
    const missionId = String(data?.today?.mission_id || scopedMissionId || '');
    if (!missionId) {
      setError('PBOS needs a selected Mission before it can compile a personal execution plan.');
      return;
    }
    setRecompiling(true);
    try {
      await compilePbosPlan(projectId, missionId, String(data?.today?.diagnosis_id || ''));
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to compile the updated personal plan'); }
    finally { setRecompiling(false); }
  };
  const submitReflection = async (event: FormEvent) => {
    event.preventDefault();
    const today = data?.today;
    const missionId = String(today?.mission_id || '');
    const planId = String(today?.artifact_id || '');
    if (!missionId || !planId || !reflection.trim()) return;
    if (!outcomeSummary.trim()) {
      setError('Record the observed delivery result before creating an outcome.');
      return;
    }
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
    if (executionAttribution === 'mixed' && !ownerContribution.trim()) {
      setError('Describe your contribution before a co-authored execution can support personal learning.');
      return;
    }
    setSaving(true);
    try {
      const executionPayload = {
        plan_id: planId,
        actions: [reflection.trim()],
        reflection: { completed: reflection.trim(), blocker: blocker.trim() },
        execution_attribution: executionAttribution,
        owner_contribution: ownerContribution.trim(),
      };
      const execution = paths.length
        ? await capturePbosWorkspaceExecution(projectId, missionId, { ...executionPayload, paths })
        : await recordPbosExecution(projectId, missionId, executionPayload);
      const outcome = await recordPbosOutcome(projectId, String(execution.execution.artifact_id || ''), {
        acceptance_status: acceptanceConfirmed ? 'accepted' : 'unverified',
        outcome_summary: outcomeSummary.trim(),
        observed_impacts: splitList(observedImpacts),
        ...(acceptanceConfirmed ? { quality_score: parsedQuality } : {}),
        metrics: { reflection_recorded: true, evidence_capture: paths.length ? 'bsc_workspace' : 'none' },
      });
      if (feedbackDraft.trim()) await recordPbosFeedback(projectId, String(outcome.outcome.artifact_id || ''), feedbackDraft.trim());
      setReflection(''); setOutcomeSummary(''); setObservedImpacts(''); setBlocker(''); setFeedbackDraft(''); setEvidencePaths(''); setExecutionAttribution('owner'); setOwnerContribution(''); setAcceptanceConfirmed(false); setQualityScore(''); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to record reflection'); }
    finally { setSaving(false); }
  };
  const reviewPendingOutcome = async (outcomeId: string, decision: 'accepted' | 'rejected') => {
    const observation = outcomeObservations.find((item) => item.artifact_id === outcomeId);
    const missingRequirements = observation?.missing_requirements ?? [];
    const unresolvedEvidence = missingRequirements.filter((item) => item !== 'accepted_outcome' && item !== 'quality_score' && item !== 'outcome_summary');
    const draft = reviewDrafts[outcomeId] ?? { qualityScore: '', outcomeSummary: '', observedImpacts: '', reviewNote: '' };
    const parsedQuality = Number(draft.qualityScore);
    if (decision === 'accepted' && unresolvedEvidence.length) {
      setError(`Capture the missing evidence before accepting this result: ${unresolvedEvidence.map(readableRequirement).join(', ')}.`);
      return;
    }
    if (decision === 'accepted' && (!draft.qualityScore.trim() || !Number.isFinite(parsedQuality) || parsedQuality < 0 || parsedQuality > 100)) {
      setError('An accepted outcome needs a quality score from 0 to 100.');
      return;
    }
    if (decision === 'accepted' && !draft.outcomeSummary.trim()) {
      setError('An accepted outcome needs an observed delivery result.');
      return;
    }
    setReviewingOutcomeId(outcomeId);
    try {
      await reviewPbosOutcome(projectId, outcomeId, {
        decision,
        outcome_summary: draft.outcomeSummary.trim(),
        observed_impacts: splitList(draft.observedImpacts),
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
  const reviewLegacyExecutionAttribution = async (executionId: string) => {
    const draft = attributionReviewDrafts[executionId] ?? { executionAttribution: 'owner', ownerContribution: '', reviewNote: '' };
    if (draft.executionAttribution === 'mixed' && !draft.ownerContribution.trim()) {
      setError('Describe your contribution before confirming a co-authored historical execution.');
      return;
    }
    if (!draft.reviewNote.trim()) {
      setError('Add an attribution review note before changing a historical execution.');
      return;
    }
    setReviewingAttributionExecutionId(executionId);
    try {
      await reviewPbosExecutionAttribution(projectId, executionId, {
        execution_attribution: draft.executionAttribution,
        owner_contribution: draft.ownerContribution.trim(),
        review_note: draft.reviewNote.trim(),
      });
      setAttributionReviewDrafts((current) => {
        const next = { ...current };
        delete next[executionId];
        return next;
      });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to review execution attribution'); }
    finally { setReviewingAttributionExecutionId(''); }
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
    <header><div><p>PERSONAL LOOP ENGINEERING</p><h2>Personal Growth Cockpit</h2></div><div>{onStartMission && <button type="button" aria-label="Start a new Mission" title="Start a new Mission" onClick={onStartMission}><Workflow size={17} /></button>}<button type="button" aria-label="Refresh PBOS evidence" title="Refresh evidence" onClick={() => void load()}><RefreshCw size={17} /></button><button type="button" aria-label="Close Personal Growth Cockpit" title="Close" onClick={onClose}><X size={18} /></button></div></header>
    {accessState && <section className="pbos-access-state" role="status">
      <div><KeyRound size={21} aria-hidden="true" /><div><p className="pbos-label">STUDIO ACCESS</p><h3>{accessState === 'required' ? 'Studio access is required' : 'Studio access was rejected'}</h3><p>{accessState === 'required' ? 'PBOS reads a project-scoped evidence ledger. Add a runtime access key before the cockpit requests any personal records.' : 'The runtime access key cannot read this project. Replace it in the control rail, then return to the cockpit.'}</p></div></div>
      <div className="pbos-access-state__actions">{accessState === 'rejected' && <button type="button" onClick={() => void load()}><RefreshCw size={15} />Retry</button>}<button type="button" className="pbos-primary-action" onClick={onConfigureAccess ?? onClose}><KeyRound size={15} />Open runtime access</button></div>
    </section>}
    {error && <p className="pbos-error"><AlertTriangle size={16} />{error}</p>}
    {!data && !error && !accessState && <p className="pbos-empty">Loading verified personal evidence...</p>}
    {data && <div className="pbos-grid">
      <section className="pbos-today"><div className="pbos-panel-heading"><p className="pbos-label">CURRENT LOOP</p><span className={knowledgeContextReady ? 'is-ready' : 'is-pending'}><ShieldCheck size={14} />{knowledgeContextReady ? 'Vault context connected' : 'Vault context needed'}</span></div>{scopedMissionTitle && <small>Mission: {scopedMissionTitle}</small>}<h3>{String(data.today?.title || todayAction.title || 'Capture a real execution receipt')}</h3><p>{todayGuidance}</p>{todayAction.success_check && <small>Success check: {String(todayAction.success_check)}</small>}{scopedMissionId && !data.today && <button type="button" className="pbos-primary-action" disabled={recompiling} onClick={() => void recompileCurrentPlan()}>{recompiling ? 'Compiling personal plan...' : 'Compile personal plan'}</button>}<dl><div><dt>Accepted outcomes</dt><dd>{acceptedOutcomes}</dd></div><div><dt>Feedback inputs</dt><dd>{feedback.length}</dd></div><div><dt>Verified capabilities</dt><dd>{capabilities.length}</dd></div></dl></section>
      {!personalLearningReady && <section className="pbos-activation" aria-label="启动个人闭环">
        <div className="pbos-panel-heading"><p className="pbos-label">PERSONAL LOOP ACTIVATION</p><span className="is-pending">需要真实输入</span></div>
        <h3>让 PBOS 开始学习你的工作方式</h3>
        <p>知识上下文已经接通；以下步骤只在你主动保存或确认后才会进入个人模型。</p>
        <ol>
          <li className={profileSetupComplete ? 'is-ready' : 'is-pending'}><div><span>01</span><p><strong>声明个人工作画像</strong><small>{profileSetupComplete ? '角色、领域与当前阶段已声明。' : `仍需填写：${readinessMissing.join('、')}。`}</small></p></div><button type="button" onClick={() => scrollToPbosPanel('pbos-personal-context')}>{profileSetupComplete ? '查看画像' : '填写画像'}</button></li>
          <li className={outcomeReviewComplete ? 'is-ready' : 'is-pending'}><div><span>02</span><p><strong>审阅一次真实交付</strong><small>{pendingReviewOutcomes.length ? `${pendingReviewOutcomes.length} 条结果等待你确认。` : awaitingOutcomeExecutions.length ? `${awaitingOutcomeExecutions.length} 条执行记录可创建结果。` : '记录结果、影响与质量评分。'}</small></p></div><button type="button" onClick={() => scrollToPbosPanel(outcomeActionTarget)}>{outcomeActionLabel}</button></li>
          <li className={comparableOutcomeCount >= requiredComparableOutcomes ? 'is-ready' : 'is-pending'}><div><span>03</span><p><strong>积累可比交付证据</strong><small>{comparableOutcomeCount} / {requiredComparableOutcomes} 条已接受的可比结果；达到门槛后才评估个人策略升级。</small></p></div></li>
        </ol>
      </section>}
      {Object.keys(currentPhase).length > 0 && <section className="pbos-execution-path"><div className="pbos-panel-heading"><p className="pbos-label">TODAY'S EXECUTION PATH</p><span>phase 1 of {phases.length}</span></div><h3>{String(currentPhase.title || 'Clarify the next evidence-backed slice')}</h3>{currentPhase.why_now && <p>{String(currentPhase.why_now)}</p>}<div className="pbos-execution-path__io"><div><strong>Inputs</strong>{phaseInputs.slice(0, 3).map((item) => <span key={item}>{item}</span>)}</div><div><strong>Reviewable output</strong>{phaseOutputs.slice(0, 2).map((item) => <span key={item}>{item}</span>)}</div></div>{phaseActions.length > 0 && <ol>{phaseActions.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ol>}{decisionPoint.question && <div className="pbos-decision-point"><strong>Decision: {String(decisionPoint.question)}</strong><span>Proceed: {String(decisionPoint.proceed_when || 'when the phase output is reviewable')}</span><span>Adapt: {String(decisionPoint.adapt_when || 'when the evidence boundary is not met')}</span></div>}{executionContract.reflection_entry && <small>{String(executionContract.reflection_entry)}</small>}</section>}
      <section className="pbos-connectors"><div className="pbos-panel-heading"><p className="pbos-label">CONNECTORS</p><span>{Object.keys(data.connectors).length} configured</span></div><div>{Object.entries(data.connectors).map(([name, state]) => <p key={name}><strong>{name}</strong><span data-state={state}>{connectorLabel(state)}</span></p>)}</div><small>External sources stay outside personal evidence until their scoped authorization and receipts are available.</small></section>
      <section className="pbos-review-queue pbos-output-review" id="pbos-d-layer-review"><div className="pbos-panel-heading"><p className="pbos-label">PENDING D-LAYER REVIEW</p><span className={pendingOutputs.length ? 'is-pending' : 'is-ready'}>{pendingOutputState === 'loading' ? 'checking' : pendingOutputState === 'unavailable' ? 'unavailable' : `${pendingOutputs.length} pending`}</span></div><p>Registered Copilot and external outputs remain outside personal learning until their evidence and quality review are complete.</p>{pendingOutputState === 'loading' ? <p className="pbos-empty-panel">Checking governed output descriptors...</p> : pendingOutputState === 'unavailable' ? <p className="pbos-review-warning" role="status">D-layer review status is unavailable. PBOS does not assume that an external output is verified.</p> : pendingOutputs.length ? <div className="pbos-review-list">{pendingOutputs.map((output) => <article key={output.id} className="pbos-review-card"><div><strong>{output.source} output</strong><small>{output.id}</small></div><button type="button" className="pbos-primary-action" aria-label={`Open D-layer review for ${output.id}`} disabled={!onOpenOutputReview} onClick={() => onOpenOutputReview?.(output.id)}>Open review</button></article>)}</div> : <p className="pbos-empty-panel">No registered external D-layer output needs review.</p>}</section>
      <section className="pbos-health"><div className="pbos-panel-heading"><p className="pbos-label">PROJECT HEALTH</p><span>ledger projection</span></div><dl><div><dt>Vault context</dt><dd className={knowledgeContextReady ? 'is-ready' : 'is-pending'}>{knowledgeContextReady ? `connected (${contextReferenceCount})` : 'needed'}</dd></div><div><dt>Personal learning</dt><dd className={personalLearningReady ? 'is-ready' : 'is-pending'}>{personalLearningReady ? 'grounded' : 'awaiting evidence'}</dd></div><div><dt>Accepted</dt><dd>{String(projectHealth.accepted_outcomes ?? 0)}</dd></div><div><dt>Learning-eligible</dt><dd>{String(projectHealth.eligible_personal_outcomes ?? 0)}</dd></div><div><dt>Unverified</dt><dd>{String(projectHealth.unverified_outcomes ?? 0)}</dd></div><div><dt>Active strategies</dt><dd>{String(projectHealth.active_strategies ?? 0)}</dd></div></dl></section>
      <section className="pbos-readiness"><div className="pbos-panel-heading"><p className="pbos-label">PERSONALIZATION READINESS</p><span className={readinessState === 'personalized' ? 'is-ready' : 'is-pending'}>{readinessLabel}</span></div><dl><div><dt>Profile context</dt><dd>{personalizationReadiness.declared_profile_ready ? 'declared' : 'incomplete'}</dd></div><div><dt>Comparable outcomes</dt><dd>{personalizationReadiness.accepted_outcome_count} of {personalizationReadiness.required_comparable_outcomes} comparable accepted outcomes</dd></div></dl>{readinessMissing.length > 0 && <p>Missing personal context: {readinessMissing.join(', ')}.</p>}<p>{readinessState === 'personalized' ? 'This plan can reuse a verified personal strategy within its matching context.' : 'Vault context can guide this plan, but it is not yet a learned personal method.'}</p></section>
      {data.today && <section className="pbos-grounding"><div className="pbos-panel-heading"><p className="pbos-label">PLAN GROUNDING</p><span>{contextReferences.length} governed reference{contextReferences.length === 1 ? '' : 's'}</span></div><dl><div><dt>Plan engine</dt><dd><span className={`pbos-plan-generation ${generation.tone}`}>{generation.label}</span><small>{generation.detail}</small></dd></div><div><dt>Weekly handoff</dt><dd>{weeklyHandoffs.length} weekly handoff{weeklyHandoffs.length === 1 ? '' : 's'}</dd></div><div><dt>Feedback input</dt><dd>{feedbackReferences.length} feedback input{feedbackReferences.length === 1 ? '' : 's'}</dd></div><div><dt>Personal strategy</dt><dd>{appliedStrategies.length ? `${appliedStrategies.length} verified strategy applied` : 'not yet earned'}</dd></div></dl>{contextReferences.length ? <ul>{contextReferences.slice(0, 4).map((item) => <li key={item}><code>{visibleVaultRef(item)}</code></li>)}</ul> : <p className="pbos-grounding-empty">No governed context was selected for this plan.</p>}{appliedStrategies.length > 0 && <ul className="pbos-strategy-inputs">{appliedStrategies.map((item) => <li key={String(item.artifact_id)}><BrainCircuit size={13} /><span>{String(item.strategy_name || 'Personal strategy')} v{String(item.version || 1)}</span></li>)}</ul>}<p>These are planning inputs. They do not establish a personal capability without verified execution evidence.</p></section>}
      <section id="pbos-personal-context" className="pbos-profile"><p className="pbos-label">PERSONAL CONTEXT</p><form onSubmit={saveProfile}><label>Role<input value={role} onChange={(event) => setRole(event.target.value)} placeholder="Independent AI product builder" /></label><label>Industry or domain<input value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder="AI productivity software" /></label><label>Working stage<input value={organizationStage} onChange={(event) => setOrganizationStage(event.target.value)} placeholder="Solo validation" /></label><label>Focus<input value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="AI systems, knowledge engineering" /></label><label>Goals<input value={goals} onChange={(event) => setGoals(event.target.value)} placeholder="Ship a verified personal operating system" /></label><label>Work style<input value={workStyle} onChange={(event) => setWorkStyle(event.target.value)} placeholder="Architecture first, rapid validation" /></label><label>Decision style<input value={decisionStyle} onChange={(event) => setDecisionStyle(event.target.value)} placeholder="Evidence before expansion" /></label><label>Resources<input value={resources} onChange={(event) => setResources(event.target.value)} placeholder="Obsidian, BSC" /></label><label>Constraints<input value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="Solo delivery, limited time" /></label><button type="submit" disabled={saving} title="Save personal context">Save personal context</button>{data?.today && <button type="button" disabled={recompiling} title="Compile the current Mission with saved personal context" onClick={() => void recompileCurrentPlan()}>{recompiling ? 'Compiling plan...' : 'Recompile current plan'}</button>}</form><p>{profile ? 'This is declared context. Capability claims still require execution evidence.' : 'Add your real operating context before PBOS personalizes a plan.'}</p></section>
      {data.today && <section id="pbos-three-minute-reflection" className="pbos-reflection"><p className="pbos-label">THREE-MINUTE REFLECTION</p><form onSubmit={submitReflection}><label>What changed?<textarea value={reflection} onChange={(event) => setReflection(event.target.value)} required placeholder="Completed, decision made, or blocker resolved" /></label><label>Observed delivery result<textarea value={outcomeSummary} onChange={(event) => setOutcomeSummary(event.target.value)} required placeholder="What was delivered and what was actually observed" /></label><label>Observed impact<input value={observedImpacts} onChange={(event) => setObservedImpacts(event.target.value)} placeholder="Optional, comma-separated metric or impact" /></label><label>What blocked you?<input value={blocker} onChange={(event) => setBlocker(event.target.value)} placeholder="Optional blocker" /></label><label>Evidence files in this BSC workspace<input value={evidencePaths} onChange={(event) => setEvidencePaths(event.target.value)} placeholder="app/pbos/service.py, app/knowledge/wiki_sync.py" /></label><small>Only approved project paths are hashed. File contents and credentials are never sent to the PBOS ledger.</small><label>Who performed this work?<select value={executionAttribution} onChange={(event) => setExecutionAttribution(event.target.value as ExecutionAttribution)}><option value="owner">I performed the work</option><option value="mixed">I co-authored the work with an agent</option><option value="agent">Agent performed the work</option></select></label>{executionAttribution === 'mixed' && <label>My contribution<textarea value={ownerContribution} onChange={(event) => setOwnerContribution(event.target.value)} placeholder="Describe the decisions, work, or review you personally performed" /></label>}<small>Only owner work, or co-authored work with a recorded personal contribution, can become evidence for your capability. Agent-only work remains auditable but cannot be promoted as your skill.</small><label className="pbos-reflection__acceptance"><input type="checkbox" checked={acceptanceConfirmed} onChange={(event) => setAcceptanceConfirmed(event.target.checked)} />I accept this result based on the attached evidence</label><label>Quality score (0-100)<input type="number" min="0" max="100" step="1" value={qualityScore} onChange={(event) => setQualityScore(event.target.value)} disabled={!acceptanceConfirmed} placeholder="82" /></label><label>What should change next time?<input value={feedbackDraft} onChange={(event) => setFeedbackDraft(event.target.value)} placeholder="Optional feedback for the next plan" /></label><button type="submit" disabled={saving || !reflection.trim() || !outcomeSummary.trim()} title="Record evidence-backed reflection">Record reflection</button></form><p>Without an observed delivery result, attached receipt, explicit attribution, and explicit acceptance, PBOS keeps the result unverified and does not learn a personal method from it.</p></section>}
      {unattributedExecutions.length > 0 && <section id="pbos-attribution-review" className="pbos-review-queue"><div className="pbos-panel-heading"><p className="pbos-label">EXECUTION ATTRIBUTION REVIEW</p><span>{unattributedExecutions.length} historical record{unattributedExecutions.length === 1 ? '' : 's'}</span></div><p>These records predate execution attribution. Review each one once before it can be considered for personal learning; this preserves the original receipts and records your decision.</p><div className="pbos-review-list">{unattributedExecutions.map((execution) => { const executionId = String(execution.artifact_id || ''); const draft = attributionReviewDrafts[executionId] ?? { executionAttribution: 'owner', ownerContribution: '', reviewNote: '' }; const reviewing = reviewingAttributionExecutionId === executionId; return <article key={executionId} className="pbos-review-card"><div><strong>{executionId}</strong><small>{execution.verified_receipt_count} verified receipt{execution.verified_receipt_count === 1 ? '' : 's'} / attribution required</small></div><label>Attribution for {executionId}<select value={draft.executionAttribution} disabled={reviewing} onChange={(event) => setAttributionReviewDrafts((current) => ({ ...current, [executionId]: { ...draft, executionAttribution: event.target.value as ExecutionAttribution } }))}><option value="owner">I performed the work</option><option value="mixed">I co-authored the work with an agent</option><option value="agent">Agent performed the work</option></select></label>{draft.executionAttribution === 'mixed' && <label>My contribution for {executionId}<textarea value={draft.ownerContribution} disabled={reviewing} onChange={(event) => setAttributionReviewDrafts((current) => ({ ...current, [executionId]: { ...draft, ownerContribution: event.target.value } }))} placeholder="Describe the work, decision, or review you personally performed" /></label>}<label>Attribution review note for {executionId}<input value={draft.reviewNote} disabled={reviewing} onChange={(event) => setAttributionReviewDrafts((current) => ({ ...current, [executionId]: { ...draft, reviewNote: event.target.value } }))} placeholder="Why this attribution is accurate" /></label><button type="button" className="pbos-primary-action" disabled={reviewing} onClick={() => void reviewLegacyExecutionAttribution(executionId)}>{reviewing ? 'Saving attribution...' : 'Confirm attribution'}</button></article>; })}</div></section>}
      {awaitingOutcomeExecutions.length > 0 && <section className="pbos-outcome-intake"><div className="pbos-panel-heading"><p className="pbos-label">OUTCOMES TO RECORD</p><span>{awaitingOutcomeExecutions.length} reviewable execution{awaitingOutcomeExecutions.length === 1 ? '' : 's'}</span></div><p>These executions already have server-verified receipts and a reflection. Create one unverified result, then explicitly accept or reject it in the review queue.</p><div className="pbos-review-list">{awaitingOutcomeExecutions.map((execution) => { const creating = creatingOutcomeExecutionId === execution.artifact_id; return <article key={execution.artifact_id} className="pbos-review-card"><div><strong>Ready for outcome review</strong><small>{execution.verified_receipt_count} verified receipt{execution.verified_receipt_count === 1 ? '' : 's'} / reflection recorded</small></div><button type="button" className="pbos-primary-action" aria-label={`Create reviewable outcome for ${execution.artifact_id}`} disabled={Boolean(creatingOutcomeExecutionId)} onClick={() => void createOutcomeForExecution(execution.artifact_id)}>{creating ? 'Creating outcome...' : 'Create reviewable outcome'}</button></article>; })}</div></section>}
      {pendingReviewOutcomes.length > 0 && <section id="pbos-outcome-review" className="pbos-review-queue"><div className="pbos-panel-heading"><p className="pbos-label">REVIEW PENDING OUTCOMES</p><span>{pendingReviewOutcomes.length} explicit review{pendingReviewOutcomes.length === 1 ? '' : 's'}</span></div><div className="pbos-review-list">{pendingReviewOutcomes.map((outcome) => { const outcomeId = String(outcome.artifact_id || ''); const observation = outcomeObservations.find((item) => item.artifact_id === outcomeId); const missingRequirements = observation?.missing_requirements ?? ['accepted_outcome', 'quality_score', 'outcome_summary']; const unresolvedEvidence = missingRequirements.filter((item) => item !== 'accepted_outcome' && item !== 'quality_score' && item !== 'outcome_summary'); const canAccept = unresolvedEvidence.length === 0; const executionId = String(outcome.execution_record_id || ''); const execution = executions.find((item) => item.artifact_id === executionId); const persistedSummary = String(outcome.outcome_summary || '').trim(); const suggestedSummary = String(observation?.outcome_summary_draft || '').trim(); const unreadablePersistedSummary = isUnreadableLegacyText(persistedSummary); const unreadableSuggestedSummary = isUnreadableLegacyText(suggestedSummary); const unreadableSummary = unreadablePersistedSummary || unreadableSuggestedSummary; const draft = reviewDrafts[outcomeId] ?? { qualityScore: '', outcomeSummary: unreadableSummary ? '' : persistedSummary || suggestedSummary, observedImpacts: stringRefs(outcome.observed_impacts).join(', '), reviewNote: '' }; const parsedQuality = Number(draft.qualityScore); const validQuality = draft.qualityScore.trim() !== '' && Number.isFinite(parsedQuality) && parsedQuality >= 0 && parsedQuality <= 100; const validSummary = Boolean(draft.outcomeSummary.trim()); const updating = reviewingOutcomeId === outcomeId; return <article key={outcomeId} className="pbos-review-card"><div><strong>{outcomeId}</strong><small>{executionId || 'Execution record unavailable'}{execution ? ` / ${execution.verified_receipt_count} verified receipt${execution.verified_receipt_count === 1 ? '' : 's'}` : ''}</small>{unresolvedEvidence.length > 0 && <em>Evidence gap: {unresolvedEvidence.map(readableRequirement).join(', ')}</em>}{unreadableSummary && <small className="pbos-review-warning" role="status">Historical outcome text is unreadable; audit metadata is preserved. Enter the real observed delivery result before accepting.</small>}</div><label>Observed delivery result for {outcomeId}<textarea value={draft.outcomeSummary} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, outcomeSummary: event.target.value } }))} disabled={updating} placeholder="What was delivered and what actually changed" /></label>{!persistedSummary && suggestedSummary && !unreadableSuggestedSummary && <small>Draft source: {Number(observation?.outcome_summary_draft_receipts ?? 0)} verified execution receipt{Number(observation?.outcome_summary_draft_receipts ?? 0) === 1 ? '' : 's'} and recorded reflection.</small>}<label>Observed impact for {outcomeId}<input value={draft.observedImpacts} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, observedImpacts: event.target.value } }))} disabled={updating} placeholder="Optional, comma-separated metric or impact" /></label><label>Quality score for {outcomeId}<input type="number" min="0" max="100" step="1" value={draft.qualityScore} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, qualityScore: event.target.value } }))} disabled={updating || !canAccept} placeholder="82" /></label><label>Review note for {outcomeId}<input value={draft.reviewNote} onChange={(event) => setReviewDrafts((current) => ({ ...current, [outcomeId]: { ...draft, reviewNote: event.target.value } }))} disabled={updating} placeholder="Optional audit note" /></label><div className="pbos-review-actions"><button type="button" className="pbos-primary-action" disabled={updating || !canAccept || !validQuality || !validSummary} onClick={() => void reviewPendingOutcome(outcomeId, 'accepted')}>Accept result</button><button type="button" disabled={updating} onClick={() => void reviewPendingOutcome(outcomeId, 'rejected')}>Reject result</button></div></article>; })}</div></section>}
      <section className="pbos-executions"><div className="pbos-panel-heading"><p className="pbos-label">RECENT EXECUTION RECEIPTS</p><span>{executions.length} reviewable record{executions.length === 1 ? '' : 's'}</span></div><div className="pbos-outcomes">{executions.length ? executions.map((execution) => <p key={execution.artifact_id}><FileCheck2 size={15} /><span><strong>{execution.artifact_id.slice(0, 16)}</strong><small>{execution.verified_receipt_count} verified receipt{execution.verified_receipt_count === 1 ? '' : 's'} / {execution.receipt_count} captured / {execution.reflection_recorded ? 'reflection recorded' : 'reflection missing'} / {executionAttributionLabel(String(execution.execution_attribution || 'unattributed'))}</small></span><em>{execution.outcome_state === 'awaiting_outcome' ? 'Awaiting explicit outcome' : execution.outcome_state === 'learning_eligible' ? 'Learning eligible' : execution.outcome_state.replace(/_/g, ' ')}</em></p>) : <p>No execution receipt has been recorded yet.</p>}</div><p>Receipt metadata proves a reviewable execution. A quality-scored, explicitly accepted, owner-attributed outcome is still required before PBOS learns a personal method.</p></section>
      <section className="pbos-chart"><div className="pbos-panel-heading"><p className="pbos-label">OUTCOME QUALITY</p><span>{qualitySeries.length ? `${qualitySeries.length} scored result${qualitySeries.length === 1 ? '' : 's'}` : 'awaiting score'}</span></div>{qualitySeries.length ? <RegisteredECharts option={qualityChart} style={{ height: 210 }} notMerge /> : <p className="pbos-empty-panel">No scored outcome has been recorded.</p>}</section>
      <section className="pbos-lineage"><p className="pbos-label">PERSONAL WORKFLOW LINEAGE</p><ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.12 }} minZoom={0.25} nodesDraggable={false} nodesConnectable={false}><Background /><Controls /></ReactFlow></section>
      <section><p className="pbos-label">STRATEGY ASSETS</p><div className="pbos-outcomes">{strategies.length ? strategies.map((item) => { const genome = item.genome as Record<string, unknown> | undefined; return <p key={String(item.artifact_id)}><CircleCheckBig size={15} /><span><strong>{String(item.strategy_name || 'Strategy')} v{String(item.version || 1)}</strong><small>{String(item.status || 'draft')} / {String(genome?.comparison_context || 'unclassified context')} / median {String(genome?.median_quality ?? 'unverified')}</small></span></p>; }) : <p>No Strategy Genome has passed the evidence gate yet.</p>}</div></section>
      <section><p className="pbos-label">VERIFIED CAPABILITIES</p><div className="pbos-outcomes">{capabilities.length ? capabilities.map((item) => <p key={String(item.artifact_id)}><CircleCheckBig size={15} />{String(item.name || 'Capability')}: level {String(item.level || 0)}</p>) : <p>No capability has enough verified evidence yet.</p>}</div></section>
      <section><p className="pbos-label">FAILURE PATTERNS</p><div className="pbos-outcomes">{failurePatterns.length ? failurePatterns.map((item, index) => <p key={`${String(item.kind)}-${index}`}><AlertTriangle size={15} /><span><strong>{String(item.kind || 'observed pattern').replace(/_/g, ' ').toUpperCase()}</strong><small>{String(item.count || 0)} evidence-backed record(s)</small></span></p>) : <p>No repeated failure pattern has enough evidence yet.</p>}</div></section>
      <section><p className="pbos-label">FEEDBACK FOR NEXT PLAN</p><div className="pbos-outcomes">{unreadableFeedbackCount > 0 && <p className="pbos-review-warning" role="status"><AlertTriangle size={15} />{unreadableFeedbackCount} historical feedback text record{unreadableFeedbackCount === 1 ? '' : 's'} is unreadable; the audit record is preserved but it is excluded from next-plan reasoning.</p>}{readableFeedback.length ? readableFeedback.map((item) => <p key={String(item.artifact_id)}><BrainCircuit size={15} />{String(item.statement || 'No feedback statement')}</p>) : unreadableFeedbackCount === 0 && <p>No feedback is available for the next plan.</p>}</div><p>Feedback remains an unverified execution direction until it is corroborated by outcomes and evidence.</p></section>
    </div>}
  </section>;
}
