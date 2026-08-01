import {
  AlertTriangle, BarChart3, BookOpen, FileDiff, FileText,
  Download, LayoutList, ListChecks, LoaderCircle, Network, Play, RefreshCw, Settings2, ShieldAlert, Sparkles, Sprout, X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  classifyGrowthError,
  addGrowthOutputFeedback,
  distillGrowthSourceMethods,
  extractGrowthSourceCandidates,
  evaluateGrowthOutput,
  evaluateGrowthMethodProposal,
  fetchGrowthAccess,
  fetchGrowthAssetDetail,
  fetchGrowthCaptureAttempts,
  fetchGrowthFailures,
  fetchGrowthHealth,
  fetchLatestGrowthDistillation,
  fetchGrowthLineage,
  fetchGrowthOverview,
  fetchGrowthRuns,
  fetchGrowthRunEvents,
  fetchGrowthStage,
  fetchGrowthTrend,
  fileGrowthOutput,
  generateProjectSop,
  linkGrowthOutputEvidence,
  processGrowthFeedback,
  publishGrowthMethodProposal,
  reviewGrowthCandidate,
  resolveGrowthFailure,
  runGrowthWorkspaceJob,
  setGrowthAccessKey,
  triageGrowthSource,
  updateGrowthProfile,
  type GrowthAccess,
  type GrowthAssetDetail,
  type GrowthAssetKind,
  type GrowthCaptureAttempt,
  type GrowthFeedbackInput,
  type GrowthFailure,
  type GrowthHealth,
  type GrowthDistillation,
  type GrowthLineage,
  type GrowthOutputEvaluationInput,
  type GrowthOutputEvidenceInput,
  type GrowthOverview,
  type GrowthProfileUpdate,
  type GrowthRecord,
  type GrowthRequestState,
  type GrowthRun,
  type GrowthRunEvent,
  type GrowthStage,
  type GrowthStageResult,
  type GrowthTrend,
  type ProjectSopGenerationInput,
  startGrowthRun,
} from '../../api/growthApi';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore, type GrowthCenterView } from '../../store/knowledgeWorkspaceStore';
import { GrowthAssetList } from './GrowthAssetList';
import { GrowthFunnel } from './GrowthFunnel';
import { GrowthInspector } from './GrowthInspector';
import { GrowthLineageGraph } from './GrowthLineageGraph';
import { GrowthProfileEditor } from './GrowthProfileEditor';
import { GrowthRunLedger } from './GrowthRunLedger';
import { GrowthStageRail } from './GrowthStageRail';
import { GrowthTrends } from './GrowthTrends';
import { GROWTH_STAGES, growthRecordLabel, normalizeGrowthNodeType } from './growthModel';

type Props = { onClose: () => void; runtimeAccessKey?: string };
type ErrorInfo = { message: string; code: string; status: number };
type GraphSelection = { id: string; endpointType: string };

function errorInfo(reason: unknown): { state: GrowthRequestState; info: ErrorInfo } {
  const error = classifyGrowthError(reason);
  const prefix = error.status >= 500 ? `Server error (${error.status}). ` : '';
  return { state: error.state, info: { message: `${prefix}${error.message}`, code: error.code, status: error.status } };
}

function stageTotal(overview: GrowthOverview | null, stage: GrowthStage): number | undefined {
  if (!overview || stage === 'review') return undefined;
  if (stage === 'A') return overview.summary.counts.sources;
  if (stage === 'B') return overview.summary.counts.pages;
  if (stage === 'C') return overview.summary.counts.methods;
  return overview.summary.counts.outputs;
}

function stageForEndpoint(type: string): GrowthStage {
  if (type === 'method_proposal') return 'review';
  if (type === 'candidate') return 'review';
  const normalized = normalizeGrowthNodeType(type);
  if (normalized === 'source') return 'A';
  if (normalized === 'page') return 'B';
  if (normalized === 'method') return 'C';
  if (normalized === 'output') return 'D';
  return 'review';
}

function kindForEndpoint(type: string): GrowthAssetKind {
  if (type === 'method_proposal') return 'method_proposal';
  if (type === 'candidate') return 'candidate';
  const normalized = normalizeGrowthNodeType(type);
  if (normalized === 'source') return 'source';
  if (normalized === 'page') return 'page';
  if (normalized === 'method') return type === 'method_proposal' ? 'proposal' : 'method';
  if (normalized === 'output') return 'output';
  return 'feedback';
}

function outputNeedsEvidence(detail: GrowthAssetDetail | null): boolean {
  if (detail?.kind !== 'output' || String(detail.record.status || '') !== 'registered') return false;
  const sourceRefs = detail.evidence?.source_ids ?? (Array.isArray(detail.record.source_refs) ? detail.record.source_refs : []);
  const pageRefs = detail.evidence?.page_ids ?? (Array.isArray(detail.record.page_refs) ? detail.record.page_refs : []);
  const metadata = detail.record.metadata;
  const requiresEvidence = !(metadata && typeof metadata === 'object' && (metadata as Record<string, unknown>).requires_evidence === false);
  return requiresEvidence && sourceRefs.length === 0 && pageRefs.length === 0;
}

function distillationProvenance(distillation: GrowthDistillation | null, state: 'loading' | 'available' | 'unavailable'): { label: string; detail: string } {
  if (state === 'loading') return { label: 'checking', detail: 'reading persisted generation metadata' };
  if (state === 'unavailable') return { label: 'unavailable', detail: 'generation metadata could not be read' };
  if (!distillation) return { label: 'not recorded', detail: 'no managed daily or weekly bundle exists' };
  const generation = distillation.generation;
  const mode = String(generation?.mode || 'deterministic').toUpperCase();
  const model = String(generation?.model || generation?.provider || 'no model recorded');
  const period = String(distillation.period || distillation.week || 'unknown period');
  const kind = String(distillation.kind || 'distillation');
  const llmDocuments = Array.isArray(generation?.llm_documents) ? generation.llm_documents.length : 0;
  const fallbackDocuments = Array.isArray(generation?.fallback_documents) ? generation.fallback_documents.length : 0;
  if (String(generation?.mode || '') === 'llm') {
    return { label: `LLM / ${model}`, detail: `${kind} ${period} / ${llmDocuments || (distillation.paths?.length ?? 0)} LLM documents` };
  }
  if (String(generation?.mode || '') === 'hybrid') {
    return { label: `HYBRID / ${model}`, detail: `${kind} ${period} / ${llmDocuments} LLM, ${fallbackDocuments} cited fallback` };
  }
  return { label: mode, detail: `${kind} ${period} / ${generation?.reason || 'cited deterministic generation'}` };
}

function WorkspaceBoundary({ state, error, onRetry }: { state: GrowthRequestState; error: ErrorInfo | null; onRetry: () => void }) {
  const content: Partial<Record<GrowthRequestState, { title: string; detail: string }>> = {
    permission: { title: 'Project access denied', detail: 'Use a key scoped to this project. No prior project data is being shown.' },
    offline: { title: 'Knowledge service offline', detail: 'The browser cannot reach the API. No mock or stale snapshot is being shown.' },
    unavailable: { title: 'Growth workspace unavailable', detail: 'The server reports that this capability or dependency is disabled.' },
    error: { title: error?.status === 500 ? 'Server boundary reached' : 'Growth workspace failed', detail: 'The failed response cleared previous data. Retry after the service is healthy.' },
  };
  if (state === 'loading') return <div className="growth-state" role="status"><LoaderCircle size={18} className="spin" /><span>Loading the project-scoped growth contract...</span></div>;
  const current = content[state];
  if (!current) return null;
  return <div className={`growth-state growth-state--boundary growth-state--${state}`} role="alert">
    {state === 'permission' ? <ShieldAlert size={21} /> : <AlertTriangle size={21} />}
    <div><strong>{current.title}</strong><span>{error?.message || current.detail}</span><small>{current.detail}{error?.code ? ` Code: ${error.code}.` : ''}</small></div>
    <button type="button" onClick={onRetry}>Retry</button>
  </div>;
}

function SafeTextPreview({ content }: { content: string }) {
  const rawLines = content.split(/\r?\n/);
  const closingFrontmatter = rawLines[0] === '---' ? rawLines.indexOf('---', 1) : -1;
  const lines = closingFrontmatter > 0 ? rawLines.slice(closingFrontmatter + 1) : rawLines;
  return <div className="growth-markdown-preview" aria-label="Safe Markdown preview">{lines.map((line, index) => {
    if (line.startsWith('### ')) return <h5 key={index}>{line.slice(4)}</h5>;
    if (line.startsWith('## ')) return <h4 key={index}>{line.slice(3)}</h4>;
    if (line.startsWith('# ')) return <h3 key={index}>{line.slice(2)}</h3>;
    if (line.startsWith('- ')) return <p className="growth-markdown-preview__list" key={index}>{line.slice(2)}</p>;
    if (!line.trim()) return <span className="growth-markdown-preview__space" key={index} aria-hidden="true" />;
    return <p key={index}>{line}</p>;
  })}</div>;
}

function ProposalDiff({ detail }: { detail: GrowthAssetDetail }) {
  const operations = Array.isArray(detail.record.operations)
    ? detail.record.operations as Array<{ id?: string; operation?: string; path?: string; destination_path?: string; content?: string }>
    : [];
  if (!operations.length) return <div className="growth-empty"><FileDiff size={18} /><span>No Wiki operations are present in this proposal.</span></div>;
  return <div className="growth-diff-view">{operations.map((operation, index) => {
    const path = String(operation.path || operation.destination_path || `operation-${index + 1}`);
    const baseline = detail.baselines?.[path];
    return <article key={operation.id || `${path}-${index}`}>
      <header><span>{operation.operation || 'change'}</span><strong>{path}</strong></header>
      <div><section><h5>Current published content</h5><pre>{baseline === undefined ? 'Baseline unavailable' : baseline || 'New file: no published baseline'}</pre></section><section><h5>Proposed content</h5><pre>{operation.content || 'No proposed text body'}</pre></section></div>
    </article>;
  })}</div>;
}

function AssetReader({ selected, detail, state, error }: { selected: GrowthRecord | null; detail: GrowthAssetDetail | null; state: GrowthRequestState; error?: string }) {
  if (!selected) return <div className="growth-empty growth-empty--reader"><BookOpen size={20} /><span>Select a stage asset to open its governed reader, preview or diff.</span></div>;
  if (state === 'loading') return <div className="growth-empty growth-empty--reader" role="status"><LoaderCircle size={18} className="spin" /><span>Loading real asset detail...</span></div>;
  if (!detail) return <div className="growth-empty growth-empty--reader" role="alert"><AlertTriangle size={18} /><span>{error || 'This asset detail is unavailable.'}</span></div>;
  if (detail.kind === 'page' && detail.content !== undefined) return <SafeTextPreview content={detail.content} />;
  if (detail.kind === 'method' && detail.content !== undefined) return <SafeTextPreview content={detail.content} />;
  if (detail.kind === 'method_proposal' && detail.content !== undefined) return <SafeTextPreview content={detail.content} />;
  if (detail.kind === 'distillation') return <div className="growth-output-preview">
    {detail.content !== undefined ? <SafeTextPreview content={detail.content} /> : <div className="growth-descriptor-preview"><FileText size={20} /><h4>{growthRecordLabel(detail.record)}</h4><p>{detail.detailMessage || 'No bounded inline preview is available.'}</p></div>}
    {detail.detailMessage && detail.content !== undefined && <p>{detail.detailMessage}</p>}
  </div>;
  if (detail.kind === 'output') return <div className="growth-output-preview">
    {detail.content !== undefined ? <SafeTextPreview content={detail.content} /> : <div className="growth-descriptor-preview"><FileText size={20} /><h4>{growthRecordLabel(detail.record)}</h4><p>{detail.detailMessage || 'No bounded inline preview is available.'}</p><code>{String(detail.record.vault_path || '')}</code></div>}
    <section aria-label="Output evaluations"><h4>Evaluation</h4>{detail.evaluations?.length ? detail.evaluations.map((evaluation) => <dl key={evaluation.id}><div><dt>Quality</dt><dd>{String(evaluation.quality ?? 'n/a')}</dd></div><div><dt>Groundedness</dt><dd>{String(evaluation.groundedness ?? 'n/a')}</dd></div><div><dt>Status</dt><dd>{String(evaluation.status || 'recorded')}</dd></div></dl>) : <p>No persisted evaluation is attached.</p>}</section>
    <section aria-label="Output feedback history"><h4>Feedback</h4>{detail.feedback?.length ? detail.feedback.map((item) => <p key={item.id}><strong>{String(item.feedback_type || 'feedback')}</strong>{String(item.correction || item.comment || '')}</p>) : <p>No feedback has been recorded.</p>}</section>
  </div>;
  if (detail.kind === 'proposal' && Array.isArray(detail.record.operations)) return <ProposalDiff detail={detail} />;
  if (detail.kind === 'proposal' && typeof detail.record.body === 'string') return <SafeTextPreview content={detail.record.body} />;
  if (detail.kind === 'feedback') {
    const correction = String(detail.record.correction || '');
    const comment = String(detail.record.comment || '');
    return <div className="growth-feedback-preview"><span>{String(detail.record.feedback_type || 'feedback')}</span><h4>{correction ? 'Correction' : 'Comment'}</h4><p>{correction || comment || 'No textual feedback was recorded.'}</p>{detail.record.rating !== null && detail.record.rating !== undefined && <strong>Rating {String(detail.record.rating)}</strong>}</div>;
  }
  return <div className="growth-descriptor-preview"><FileText size={20} /><h4>{growthRecordLabel(detail.record)}</h4><p>{detail.detailMessage || 'The persisted descriptor is available in the inspector.'}</p>{typeof detail.record.vault_path === 'string' && <code>{detail.record.vault_path}</code>}</div>;
}

function isProjectPrdSource(source: GrowthRecord): boolean {
  if (!['eligible', 'processed'].includes(String(source.status || ''))) return false;
  const metadata = source.metadata;
  const evidenceRole = metadata && typeof metadata === 'object'
    ? String((metadata as Record<string, unknown>).evidence_role || '').toLowerCase()
    : '';
  return evidenceRole === 'project_prd' || evidenceRole === 'prd';
}

function ProjectSopGenerator({
  sources,
  supportingSources,
  sourceState,
  canWrite,
  busy,
  onGenerate,
}: {
  sources: GrowthRecord[];
  supportingSources: GrowthRecord[];
  sourceState: GrowthRequestState;
  canWrite: boolean;
  busy: boolean;
  onGenerate: (input: Omit<ProjectSopGenerationInput, 'idempotency_key' | 'channel'>) => void;
}) {
  const [prdSourceId, setPrdSourceId] = useState('');
  const [supportingSourceIds, setSupportingSourceIds] = useState<string[]>([]);
  const [goal, setGoal] = useState('');
  const [audience, setAudience] = useState('');

  useEffect(() => {
    if (!sources.some((source) => source.id === prdSourceId)) setPrdSourceId(sources[0]?.id || '');
  }, [prdSourceId, sources]);

  useEffect(() => {
    setSupportingSourceIds((current) => current.filter((sourceId) => sourceId !== prdSourceId && supportingSources.some((source) => source.id === sourceId)));
  }, [prdSourceId, supportingSources]);

  const unavailable = ['loading', 'permission', 'offline', 'unavailable', 'error'].includes(sourceState);
  const disabled = !canWrite || busy || unavailable || !prdSourceId || goal.trim().length < 8 || audience.trim().length < 2;
  return <section className="growth-panel growth-sop-generator" aria-label="Project PRD to SOP">
    <div className="growth-panel__heading"><div><p>PRD TO SOP</p><h3>Reviewable project output</h3></div><Sparkles size={18} /></div>
    <form onSubmit={(event) => {
      event.preventDefault();
      if (!disabled) onGenerate({ prd_source_id: prdSourceId, supporting_source_ids: supportingSourceIds, goal: goal.trim(), audience: audience.trim() });
    }}>
      <label><span>Admitted project PRD</span><select aria-label="Admitted project PRD" value={prdSourceId} onChange={(event) => setPrdSourceId(event.target.value)} disabled={busy || sourceState === 'loading'}>
        {sources.map((source) => <option key={source.id} value={source.id}>{growthRecordLabel(source)} ({source.id.slice(0, 8)})</option>)}
      </select></label>
      <label><span>Supporting admitted evidence</span><select aria-label="Supporting admitted evidence" multiple size={Math.min(5, Math.max(2, supportingSources.length))} value={supportingSourceIds} onChange={(event) => setSupportingSourceIds(Array.from(event.currentTarget.selectedOptions, (option) => option.value).filter((sourceId) => sourceId !== prdSourceId).slice(0, 12))} disabled={busy || sourceState === 'loading'}>
        {supportingSources.filter((source) => source.id !== prdSourceId).map((source) => <option key={source.id} value={source.id}>{growthRecordLabel(source)} ({source.id.slice(0, 8)})</option>)}
      </select></label>
      <label><span>Delivery goal</span><textarea aria-label="SOP delivery goal" value={goal} onChange={(event) => setGoal(event.target.value)} minLength={8} maxLength={4000} required /></label>
      <label><span>Audience</span><input aria-label="SOP audience" value={audience} onChange={(event) => setAudience(event.target.value)} minLength={2} maxLength={1000} required /></label>
      {sourceState === 'loading' ? <small>Loading admitted project PRDs...</small> : !sources.length ? <small>No eligible source is designated as a project PRD.</small> : null}
      <button type="submit" disabled={disabled} title={canWrite ? 'Generate a registered SOP for review' : 'Project write permission is required'}>{busy ? <LoaderCircle size={14} className="spin" /> : <Sparkles size={14} />}Generate reviewable SOP</button>
    </form>
  </section>;
}

export function GrowthWorkspace({ onClose, runtimeAccessKey = '' }: Props) {
  const {
    projectId, stage, selectedId, inspectorOpen, query, statusFilter, page, pageSize, centerView, requestStates,
    setProjectId, setStage, setSelectedId, setInspectorOpen, setQuery, setStatusFilter, setPage, setCenterView, setRequestState,
  } = useGrowthWorkspaceStore();
  const knowledgeProjectId = useKnowledgeWorkspaceStore((state) => state.projectId);
  const setKnowledgeProjectId = useKnowledgeWorkspaceStore((state) => state.setProjectId);
  const [projectInput, setProjectInput] = useState(projectId);
  const [reloadEpoch, setReloadEpoch] = useState(0);
  const [overview, setOverview] = useState<GrowthOverview | null>(null);
  const [overviewError, setOverviewError] = useState<ErrorInfo | null>(null);
  const [access, setAccess] = useState<GrowthAccess | null>(null);
  const [accessState, setAccessState] = useState<GrowthRequestState>('idle');
  const [accessError, setAccessError] = useState<ErrorInfo | null>(null);
  const [stageResult, setStageResult] = useState<GrowthStageResult | null>(null);
  const [stageError, setStageError] = useState<ErrorInfo | null>(null);
  const [detail, setDetail] = useState<GrowthAssetDetail | null>(null);
  const [detailError, setDetailError] = useState<ErrorInfo | null>(null);
  const [health, setHealth] = useState<GrowthHealth | null>(null);
  const [trend, setTrend] = useState<GrowthTrend | null>(null);
  const [metricsError, setMetricsError] = useState<ErrorInfo | null>(null);
  const [lineage, setLineage] = useState<GrowthLineage | null>(null);
  const [lineageError, setLineageError] = useState<ErrorInfo | null>(null);
  const [evidenceSources, setEvidenceSources] = useState<GrowthRecord[]>([]);
  const [evidenceState, setEvidenceState] = useState<GrowthRequestState>('idle');
  const [relation, setRelation] = useState('');
  const [compact, setCompact] = useState(() => typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 760px)').matches : false);
  const [actionMessage, setActionMessage] = useState('');
  const [graphSelection, setGraphSelection] = useState<GraphSelection | null>(null);
  const [latestRun, setLatestRun] = useState<GrowthRun | null>(null);
  const [runs, setRuns] = useState<GrowthRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runEvents, setRunEvents] = useState<GrowthRunEvent[]>([]);
  const [runCaptureAttempts, setRunCaptureAttempts] = useState<GrowthCaptureAttempt[]>([]);
  const [runFailures, setRunFailures] = useState<GrowthFailure[]>([]);
  const [runsError, setRunsError] = useState<ErrorInfo | null>(null);
  const [runMessage, setRunMessage] = useState('No growth cycle has been recorded yet.');
  const [latestDistillation, setLatestDistillation] = useState<GrowthDistillation | null>(null);
  const [latestDistillationState, setLatestDistillationState] = useState<'loading' | 'available' | 'unavailable'>('loading');
  const [profileEditorOpen, setProfileEditorOpen] = useState(false);
  const [profileMessage, setProfileMessage] = useState('');
  const [projectPrds, setProjectPrds] = useState<GrowthRecord[]>([]);
  const [projectSopSupportingSources, setProjectSopSupportingSources] = useState<GrowthRecord[]>([]);
  const [projectPrdState, setProjectPrdState] = useState<GrowthRequestState>('idle');
  const projectSopIdempotencyKey = useRef('');

  useEffect(() => {
    document.documentElement.classList.add('growth-workspace-open');
    return () => document.documentElement.classList.remove('growth-workspace-open');
  }, []);
  useEffect(() => {
    const sharedProjectId = knowledgeProjectId.trim() || 'default';
    setProjectInput(sharedProjectId);
    if (projectId !== sharedProjectId) setProjectId(sharedProjectId);
  }, [knowledgeProjectId, projectId, setProjectId]);
  useEffect(() => {
    setGrowthAccessKey(runtimeAccessKey);
    setReloadEpoch((value) => value + 1);
  }, [runtimeAccessKey]);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const media = window.matchMedia('(max-width: 760px)');
    const update = () => setCompact(media.matches);
    update(); media.addEventListener?.('change', update);
    return () => media.removeEventListener?.('change', update);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setOverview(null); setOverviewError(null); setRequestState('overview', 'loading');
    void fetchGrowthOverview(projectId, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setOverview(next); setRequestState('overview', 'success');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setOverview(null); setOverviewError(failure.info); setRequestState('overview', failure.state);
    });
    setAccess(null); setAccessError(null); setAccessState('loading');
    void fetchGrowthAccess(projectId, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setAccess(next); setAccessState('success');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setAccess(null); setAccessError(failure.info); setAccessState(failure.state);
    });
    void fetchGrowthRuns(projectId, controller.signal).then((runs) => {
      if (controller.signal.aborted) return;
      const latest = runs[0] ?? null;
      setRuns(runs); setRunsError(null);
      setSelectedRunId((current) => runs.some((run) => run.id === current) ? current : (latest?.id || ''));
      setLatestRun(latest);
      setRunMessage(latest ? `${String(latest.run_type || 'growth cycle')}: ${String(latest.status || 'recorded')}` : 'No growth cycle has been recorded yet.');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setRuns([]); setSelectedRunId(''); setRunsError(failure.info); setLatestRun(null); setRunMessage(`Run status unavailable: ${failure.info.message}`);
    });
    setLatestDistillation(null); setLatestDistillationState('loading');
    void fetchLatestGrowthDistillation(projectId, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setLatestDistillation(next); setLatestDistillationState('available');
    }).catch(() => {
      if (controller.signal.aborted) return;
      setLatestDistillation(null); setLatestDistillationState('unavailable');
    });
    return () => controller.abort();
  }, [projectId, reloadEpoch, setRequestState]);

  useEffect(() => {
    if (!selectedRunId) {
      setRunEvents([]); setRunCaptureAttempts([]); setRunFailures([]); setRequestState('runs', 'empty');
      return undefined;
    }
    const controller = new AbortController();
    setRunEvents([]); setRunCaptureAttempts([]); setRunFailures([]); setRunsError(null); setRequestState('runs', 'loading');
    void Promise.all([
      fetchGrowthRunEvents(projectId, selectedRunId, controller.signal),
      fetchGrowthCaptureAttempts(projectId, { runId: selectedRunId }, controller.signal),
      fetchGrowthFailures(projectId, { runId: selectedRunId }, controller.signal),
    ]).then(([timeline, captureAttempts, failures]) => {
      if (controller.signal.aborted) return;
      setRunEvents(timeline.events); setRunCaptureAttempts(captureAttempts); setRunFailures(failures);
      setRequestState('runs', 'success');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setRunEvents([]); setRunCaptureAttempts([]); setRunFailures([]); setRunsError(failure.info); setRequestState('runs', failure.state);
    });
    return () => controller.abort();
  }, [projectId, reloadEpoch, selectedRunId, setRequestState]);

  useEffect(() => {
    const pendingMethodRun = runs.some((run) => (
      ['source_method_distillation', 'cangjie_candidate_extraction'].includes(String(run.run_type || ''))
      && ['queued', 'running'].includes(String(run.status || ''))
    ));
    if (!pendingMethodRun) return undefined;
    const timer = window.setTimeout(() => setReloadEpoch((value) => value + 1), 1_500);
    return () => window.clearTimeout(timer);
  }, [runs]);

  useEffect(() => {
    const controller = new AbortController();
    const requestedLimit = query.trim() || statusFilter ? 500 : Math.min(500, page * pageSize);
    setStageResult(null); setStageError(null); setRequestState('stage', 'loading');
    void fetchGrowthStage(projectId, stage, requestedLimit, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setStageResult(next); setRequestState('stage', next.records.length ? 'success' : 'empty');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setStageResult(null); setStageError(failure.info); setRequestState('stage', failure.state);
    });
    return () => controller.abort();
  }, [page, pageSize, projectId, query, reloadEpoch, setRequestState, stage, statusFilter]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); setDetailError(null); setRequestState('detail', 'idle'); return undefined; }
    const controller = new AbortController();
    setDetail(null); setDetailError(null); setRequestState('detail', 'loading');
    void fetchGrowthAssetDetail(projectId, stage, selectedId, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setDetail(next); setRequestState('detail', 'success');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason);
      if (failure.info.status === 404 && graphSelection?.id === selectedId) {
        const kind = kindForEndpoint(graphSelection.endpointType);
        setDetail({
          kind,
          record: { id: selectedId, endpoint_type: graphSelection.endpointType, detail_source: 'persisted lineage edge' },
          detailAvailability: 'metadata_only',
          detailMessage: 'This endpoint exists in the bounded lineage slice but has no detail endpoint in P7.',
        });
        setRequestState('detail', 'success');
        return;
      }
      setDetail(null); setDetailError(failure.info); setRequestState('detail', failure.state);
    });
    return () => controller.abort();
  }, [graphSelection, projectId, reloadEpoch, selectedId, setRequestState, stage]);

  useEffect(() => {
    if (!outputNeedsEvidence(detail)) {
      setEvidenceSources([]); setEvidenceState('idle');
      return undefined;
    }
    const controller = new AbortController();
    setEvidenceSources([]); setEvidenceState('loading');
    void fetchGrowthStage(projectId, 'A', 500, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setEvidenceSources(result.records.filter((source) => ['eligible', 'processed'].includes(String(source.status || ''))));
      setEvidenceState(result.records.length ? 'success' : 'empty');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setEvidenceSources([]); setEvidenceState(errorInfo(reason).state);
    });
    return () => controller.abort();
  }, [detail, projectId, reloadEpoch]);

  useEffect(() => {
    if (stage !== 'D') {
      setProjectPrds([]); setProjectSopSupportingSources([]); setProjectPrdState('idle');
      return undefined;
    }
    const controller = new AbortController();
    setProjectPrds([]); setProjectPrdState('loading');
    void fetchGrowthStage(projectId, 'A', 500, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      const admitted = result.records.filter((source) => ['eligible', 'processed'].includes(String(source.status || '')));
      const prds = admitted.filter(isProjectPrdSource);
      setProjectPrds(prds); setProjectSopSupportingSources(admitted); setProjectPrdState(prds.length ? 'success' : 'empty');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setProjectPrds([]); setProjectSopSupportingSources([]); setProjectPrdState(errorInfo(reason).state);
    });
    return () => controller.abort();
  }, [projectId, reloadEpoch, stage]);

  useEffect(() => {
    const controller = new AbortController();
    setHealth(null); setTrend(null); setMetricsError(null); setRequestState('metrics', 'loading');
    void Promise.all([fetchGrowthHealth(projectId, controller.signal), fetchGrowthTrend(projectId, controller.signal)]).then(([nextHealth, nextTrend]) => {
      if (controller.signal.aborted) return;
      setHealth(nextHealth); setTrend(nextTrend); setRequestState('metrics', 'success');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setHealth(null); setTrend(null); setMetricsError(failure.info); setRequestState('metrics', failure.state);
    });
    return () => controller.abort();
  }, [projectId, reloadEpoch, setRequestState]);

  useEffect(() => {
    const controller = new AbortController();
    setLineage(null); setLineageError(null); setRequestState('lineage', 'loading');
    void fetchGrowthLineage(projectId, relation, 200, controller.signal).then((next) => {
      if (controller.signal.aborted) return;
      setLineage(next); setRequestState('lineage', next.edges.length ? 'success' : 'empty');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      const failure = errorInfo(reason); setLineage(null); setLineageError(failure.info); setRequestState('lineage', failure.state);
    });
    return () => controller.abort();
  }, [projectId, relation, reloadEpoch, setRequestState]);

  const records = stageResult?.records ?? [];
  const selected = records.find((record) => record.id === selectedId) ?? detail?.record ?? (graphSelection?.id === selectedId ? { id: selectedId, endpoint_type: graphSelection.endpointType } : null);
  const counts = overview?.summary.counts ?? null;
  const stageCounts: Partial<Record<GrowthStage, number>> = counts ? { A: counts.sources, B: counts.pages, C: counts.methods, D: counts.outputs } : {};
  if (counts) stageCounts.review = counts.review_records ?? counts.feedback;
  if (stage === 'review' && stageResult?.truncated) stageCounts.review = stageResult.records.length;
  const stageBounds: Partial<Record<GrowthStage, boolean>> = stageResult?.truncated ? { [stage]: true } : {};
  const relevantEdges = lineage?.edges ?? [];
  const stageMeta = GROWTH_STAGES.find((item) => item.id === stage);
  const refresh = () => setReloadEpoch((value) => value + 1);

  const submitProject = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextProject = projectInput.trim() || 'default';
    setActionMessage(''); setGraphSelection(null);
    setKnowledgeProjectId(nextProject);
    if (nextProject === projectId) refresh();
  };
  const selectAsset = (record: GrowthRecord) => { setGraphSelection(null); setActionMessage(''); setSelectedId(record.id); };
  const followAsset = (id: string, endpointType = '') => {
    const nextStage = stageForEndpoint(endpointType);
    setGraphSelection({ id, endpointType }); setStage(nextStage); setSelectedId(id); setCenterView('assets');
  };
  const runAction = async (current: GrowthAssetDetail) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      if (current.kind === 'source') await triageGrowthSource(projectId, current.record.id);
      else if (current.kind === 'feedback') await processGrowthFeedback(projectId, current.record.id);
      else if (current.kind === 'output') await fileGrowthOutput(projectId, current.record.id);
      else throw new Error('No Growth API action exists for this asset type.');
      setRequestState('action', 'success'); setActionMessage('The operation completed and persisted data is being reloaded.'); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const distillSourceMethods = async (current: GrowthAssetDetail) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const result = await distillGrowthSourceMethods(projectId, current.record.id);
      setLatestRun(result.run); setSelectedRunId(result.run.id); setCenterView('runs'); setInspectorOpen(false);
      setRequestState('action', 'success');
      const execution = result.execution.execution === 'celery' ? 'the durable worker queue' : 'the local API process';
      setRunMessage(`source_method_distillation: ${String(result.run.status || 'queued')} / ${result.execution.execution}`);
      setActionMessage(`Method proposal generation was submitted to ${execution}. This request can now close safely; inspect the persisted run ledger and review queue after it reaches a terminal state.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const distillAcceptedCandidate = async (current: GrowthAssetDetail) => {
    const sourceId = String(current.record.source_id || '').trim();
    if (!sourceId) {
      setRequestState('action', 'error');
      setActionMessage('The accepted candidate has no persisted immutable source reference. No method draft was submitted.');
      return;
    }
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const result = await distillGrowthSourceMethods(projectId, sourceId, [current.record.id]);
      setLatestRun(result.run); setSelectedRunId(result.run.id); setCenterView('runs'); setInspectorOpen(false);
      setRequestState('action', 'success');
      const execution = result.execution.execution === 'celery' ? 'the durable worker queue' : 'the local API process';
      setRunMessage(`source_method_distillation: ${String(result.run.status || 'queued')} / ${result.execution.execution}`);
      setActionMessage(`The accepted ${String(current.record.candidate_type || 'evidence')} selection was submitted to ${execution}. The resulting method remains a review-only proposal and must pass evaluation before publication.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const extractSourceCandidates = async (current: GrowthAssetDetail) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const result = await extractGrowthSourceCandidates(projectId, current.record.id);
      setLatestRun(result.run); setSelectedRunId(result.run.id); setCenterView('runs'); setInspectorOpen(false);
      setRequestState('action', 'success');
      const execution = result.execution.execution === 'celery' ? 'the durable worker queue' : 'the local API process';
      setRunMessage(`cangjie_candidate_extraction: ${String(result.run.status || 'queued')} / ${result.execution.execution}`);
      setActionMessage(`Five independent evidence extractors were submitted to ${execution}. Their output will remain in the review queue; no Wiki page, method, or Skill can be published by this run.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const reviewCandidate = async (current: GrowthAssetDetail, review: { decision: 'accepted' | 'rejected'; review_note?: string }) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      await reviewGrowthCandidate(projectId, current.record.id, review);
      setRequestState('action', 'success');
      setActionMessage(`Candidate ${review.decision}. This decision records review state only; it does not publish a method or Wiki page.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const submitFeedback = async (current: GrowthAssetDetail, payload: GrowthFeedbackInput) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      await addGrowthOutputFeedback(projectId, current.record.id, payload);
      setRequestState('action', 'success'); setActionMessage('Feedback was persisted and the review queue is being reloaded.'); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const submitEvidence = async (current: GrowthAssetDetail, payload: GrowthOutputEvidenceInput) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      await linkGrowthOutputEvidence(projectId, current.record.id, payload);
      setRequestState('action', 'success'); setActionMessage('Evidence lineage was persisted. Inspect it, then complete the quality gate.'); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const submitProjectSop = async (input: Omit<ProjectSopGenerationInput, 'idempotency_key' | 'channel'>) => {
    setRequestState('action', 'loading'); setActionMessage('');
    const idempotencyKey = projectSopIdempotencyKey.current || `browser-prd-to-sop-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    projectSopIdempotencyKey.current = idempotencyKey;
    try {
      const result = await generateProjectSop(projectId, { ...input, idempotency_key: idempotencyKey, channel: 'knowledge_workspace' });
      projectSopIdempotencyKey.current = '';
      setLatestRun(result.run); setSelectedRunId(result.run.id); setStage('D'); setSelectedId(result.output.id); setCenterView('assets'); setInspectorOpen(true);
      setRequestState('action', 'success');
      setActionMessage(`${result.idempotent ? 'Existing' : 'New'} registered SOP is open for lineage inspection and quality evaluation.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason);
      // Keep a key only after an ambiguous transport error. Retrying after an
      // observed terminal API response must create a distinct model run.
      if (failure.info.status > 0 && failure.info.status < 500) projectSopIdempotencyKey.current = '';
      setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const submitEvaluation = async (current: GrowthAssetDetail, payload: GrowthOutputEvaluationInput) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const evaluation = await evaluateGrowthOutput(projectId, current.record.id, payload);
      setRequestState('action', 'success'); setActionMessage(`Quality review persisted: ${String(evaluation.quality ?? 'unavailable')}. Reloading the D-layer lifecycle.`); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const evaluateMethodCandidate = async (current: GrowthAssetDetail) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const evaluation = await evaluateGrowthMethodProposal(projectId, current.record.id);
      setRequestState('action', 'success'); setActionMessage(`Method gate recorded: ${String(evaluation.eligible ? 'eligible for publication' : 'more evidence or evaluation is required')}.`); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const publishMethodCandidate = async (current: GrowthAssetDetail) => {
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const method = await publishGrowthMethodProposal(projectId, current.record.id, overview?.profile.revision);
      setRequestState('action', 'success'); setActionMessage(`Published method ${String(method.id)}. It is now available to future governed context packs.`); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setActionMessage(failure.info.message);
    }
  };
  const startGrowthCycle = async (jobType: 'growth_daily' | 'growth_weekly_distillation') => {
    setRequestState('action', 'loading'); setRunMessage('Submitting durable growth run...');
    try {
      const run = await startGrowthRun(projectId, jobType);
      setLatestRun(run); setRunMessage(`${jobType}: ${String(run.status || 'queued')}`);
      setRequestState('action', 'success'); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setRunMessage(`Run submission failed: ${failure.info.message}`);
    }
  };
  const runWorkspaceJob = async (jobType: 'source_sync' | 'horizon_capture') => {
    setRequestState('action', 'loading'); setRunMessage(`Submitting ${jobType}...`);
    try {
      const run = await runGrowthWorkspaceJob(projectId, jobType);
      setRunMessage(`${jobType}: ${String(run.status || 'queued')}`);
      setRequestState('action', 'success'); refresh();
    } catch (reason) {
      const failure = errorInfo(reason); setRequestState('action', failure.state); setRunMessage(`${jobType} failed: ${failure.info.message}`);
    }
  };
  const resolveFailure = async (failure: GrowthFailure) => {
    const note = window.prompt(`Resolution note for ${failure.code}:`);
    if (!note?.trim()) return;
    setRequestState('action', 'loading'); setActionMessage('');
    try {
      const resolved = await resolveGrowthFailure(projectId, failure.id, { resolution_note: note.trim() });
      setRunFailures((current) => current.map((item) => item.id === resolved.id ? resolved : item));
      setRequestState('action', 'success'); setActionMessage(`Failure ${resolved.code} was resolved and remains in the audit ledger.`); refresh();
    } catch (reason) {
      const failureInfo = errorInfo(reason); setRequestState('action', failureInfo.state); setActionMessage(failureInfo.info.message);
    }
  };
  const saveProfile = async (profile: GrowthProfileUpdate) => {
    setRequestState('action', 'loading');
    setProfileMessage('');
    try {
      const saved = await updateGrowthProfile(projectId, profile);
      setOverview((current) => current ? { ...current, profile: saved } : current);
      setRequestState('action', 'success');
      setProfileMessage(`Saved revision ${saved.revision ?? 0}. Future triage and context packs will use this project profile.`);
      refresh();
    } catch (reason) {
      const failure = errorInfo(reason);
      setRequestState('action', failure.state);
      setProfileMessage(`Profile was not saved: ${failure.info.message}`);
    }
  };

  const accessLabel = accessState === 'loading' ? 'Checking access' : access ? `${access.role || 'project role'} / ${access.can_write ? 'write' : 'read only'}` : `${accessState}${accessError?.status ? ` ${accessError.status}` : ''}`;
  const sessionLabel = runtimeAccessKey.trim() ? 'Studio session applied' : 'Studio access required';
  const vaultLabel = access?.vault?.connection?.state || access?.vault?.status || 'not checked';
  const pluginBridges = access?.plugins?.plugins ?? [];
  const readyPluginBridges = pluginBridges.filter((plugin) => plugin.path_status === 'ready').length;
  const capturedPluginBridges = pluginBridges.filter((plugin) => plugin.status === 'captured' || plugin.status === 'registered_output').length;
  const horizonStore = access?.horizon?.artifact_store;
  const horizonRun = access?.horizon?.last_run;
  const horizonLabel = !access?.horizon?.enabled ? 'disabled'
    : horizonRun?.outcome === 'channel_error' ? 'channel unavailable'
      : horizonRun?.outcome === 'configuration_error' ? 'configuration needed'
        : horizonRun?.outcome === 'empty_result' ? 'last run: no items'
          : horizonRun?.outcome === 'no_new_artifact' ? 'awaiting new run'
            : horizonStore?.available ? `ready / ${horizonStore.mode}` : horizonStore?.configured ? 'configured / unavailable' : 'unconfigured';
  const horizonDetail = horizonRun?.outcome === 'channel_error'
    ? `${horizonRun.failure?.code || 'horizon_unavailable'}${horizonRun.failure?.retryable ? ' / retryable' : ''}`
    : horizonRun?.outcome === 'configuration_error'
      ? (horizonRun.failure?.code || 'horizon_not_configured')
      : horizonRun?.outcome === 'empty_result'
        ? 'last source stage returned zero items'
        : horizonRun?.outcome === 'no_new_artifact'
          ? 'no unconsumed native run is available'
          : `${access?.horizon?.captured_sources ?? 0} immutable signals captured`;
  const schedulerLabel = access?.scheduler?.available ? 'Celery ready' : access?.scheduler ? 'manual only' : 'not checked';
  const latestDistillationProvenance = distillationProvenance(latestDistillation, latestDistillationState);
  const viewButtons: Array<{ id: GrowthCenterView; label: string; icon: typeof LayoutList }> = [
    { id: 'assets', label: 'Assets', icon: LayoutList }, { id: 'runs', label: 'Runs', icon: ListChecks }, { id: 'metrics', label: 'Metrics', icon: BarChart3 }, { id: 'lineage', label: 'Lineage', icon: Network },
  ];

  return <section className="growth-workspace" aria-label="Knowledge growth workspace">
    <header className="growth-workspace__header">
      <div className="growth-workspace__brand"><span className="growth-workspace__mark"><Sprout size={17} /></span><div><p>KNOWLEDGE GROWTH</p><h2>Knowledge growth workspace</h2><span>A evidence to B knowledge to C methods to D outputs</span></div></div>
      <div className="growth-workspace__actions">
        <form onSubmit={submitProject}>
          <label><span>Project</span><input value={projectInput} onChange={(event) => setProjectInput(event.target.value)} aria-label="Growth project ID" /></label>
          <button type="submit" title="Load the shared project growth state"><RefreshCw size={14} /> Load</button>
        </form>
        <button type="button" className="growth-icon-button" disabled={access?.can_write !== true || requestStates.action === 'loading' || access?.features.obsidian_sync === false} onClick={() => void runWorkspaceJob('source_sync')} title="Capture declared Obsidian exports as immutable evidence" aria-label="Sync Obsidian evidence"><Download size={15} /></button>
        <button type="button" className="growth-icon-button" disabled={access?.can_write !== true || requestStates.action === 'loading' || access?.features.horizon === false || horizonStore?.available === false} onClick={() => void runWorkspaceJob('horizon_capture')} title="Import the latest unconsumed Horizon run through the evidence gate" aria-label="Import Horizon evidence"><Sparkles size={15} /></button>
        <button type="button" className="growth-icon-button" disabled={access?.can_write !== true || requestStates.action === 'loading'} onClick={() => void startGrowthCycle('growth_daily')} title="Run daily growth cycle" aria-label="Run daily growth cycle"><Play size={15} /></button>
        <button type="button" className="growth-icon-button" disabled={access?.can_write !== true || requestStates.action === 'loading'} onClick={() => void startGrowthCycle('growth_weekly_distillation')} title="Run weekly growth distillation" aria-label="Run weekly growth distillation"><Sprout size={15} /></button>
        <span className={runtimeAccessKey.trim() ? 'growth-session-state is-ready' : 'growth-session-state is-pending'}>{sessionLabel}</span>
        <button type="button" className="growth-icon-button" disabled={access?.can_write !== true} onClick={() => { setProfileMessage(''); setProfileEditorOpen(true); }} title="Configure the project knowledge profile" aria-label="Configure project profile"><Settings2 size={16} /></button>
        <button type="button" className="growth-icon-button" onClick={refresh} title="Refresh project growth state" aria-label="Refresh growth workspace"><RefreshCw size={16} className={requestStates.overview === 'loading' ? 'spin' : ''} /></button>
        <button type="button" className="growth-icon-button" onClick={onClose} title="Close growth workspace" aria-label="Close growth workspace"><X size={18} /></button>
      </div>
    </header>
    <WorkspaceBoundary state={requestStates.overview} error={overviewError} onRetry={refresh} />
    {overview && <>
      <div className="growth-status-strip">
        <div><span>PROFILE ROLE</span><strong>{overview.profile.user_role || 'not configured'}</strong><small>revision {overview.profile.revision || 0}</small></div>
        <div><span>API ACCESS</span><strong>{accessLabel}</strong><small>{access?.can_write ? 'permission-gated actions enabled' : `${sessionLabel}; actions stay disabled until authorized`}</small></div>
        <div><span>VAULT</span><strong>{vaultLabel}</strong><small>{access?.vault?.configured ? 'mapped project workspace' : 'Vault mapping required'}</small></div>
        <div><span>PLUGIN BRIDGES</span><strong>{`${readyPluginBridges}/${pluginBridges.length} ready`}</strong><small>{capturedPluginBridges} captured or registered</small></div>
        <div><span>HORIZON</span><strong>{horizonLabel}</strong><small>{horizonDetail}</small></div>
        <div><span>AUTOMATION</span><strong>{schedulerLabel}</strong><small>{access?.growth?.status || 'no growth run'} growth state</small></div>
        <div><span>ELIGIBLE A</span><strong>{counts?.eligible_sources ?? 0}</strong><small>of {counts?.sources ?? 0} captured</small></div>
        <div><span>VERIFIED D</span><strong>{counts?.accepted_outputs ?? 0}</strong><small>{counts?.rejected_outputs ?? 0} rejected</small></div>
        <div><span>OPEN FAILURES</span><strong>{counts?.open_failures ?? 0}</strong><small>reviewed in the run ledger</small></div>
        <div><span>LATEST DISTILLATION</span><strong>{latestDistillationProvenance.label}</strong><small>{latestDistillationProvenance.detail}</small></div>
        <div><span>LATEST CYCLE</span><strong>{String(latestRun?.status || 'not run')}</strong><small>{runMessage}</small></div>
      </div>
      {profileEditorOpen && <GrowthProfileEditor
        profile={overview.profile}
        canWrite={access?.can_write === true}
        busy={requestStates.action === 'loading'}
        message={profileMessage}
        onSave={(profile) => void saveProfile(profile)}
        onClose={() => { setProfileEditorOpen(false); setProfileMessage(''); }}
      />}
      <div className="growth-layout">
        <GrowthStageRail projectId={projectId} stage={stage} counts={stageCounts} truncated={stageBounds} onChange={(next) => { setGraphSelection(null); setStage(next); setCenterView('assets'); }} />
        <main className="growth-main" id="growth-stage-panel" role="tabpanel" aria-labelledby={`growth-stage-${stage}`}>
          <header className="growth-main__header"><div><p>{stage === 'review' ? 'REVIEW QUEUE' : `STAGE ${stage}`}</p><h3>{stageMeta?.detail}</h3></div><div className="growth-view-switcher" role="group" aria-label="Growth workspace view">{viewButtons.map(({ id, label, icon: Icon }) => <button type="button" key={id} className={centerView === id ? 'is-active' : ''} aria-pressed={centerView === id} onClick={() => setCenterView(id)}><Icon size={14} />{label}</button>)}</div></header>
          {centerView === 'assets' && <>
            <section className="growth-panel growth-panel--overview"><div className="growth-panel__heading"><div><p>GROWTH HEALTH</p><h3>Persisted inventory and coverage</h3></div><BarChart3 size={18} /></div><GrowthFunnel counts={counts} state={requestStates.overview} error={overviewError?.message} /></section>
            {stage === 'D' && <ProjectSopGenerator sources={projectPrds} supportingSources={projectSopSupportingSources} sourceState={projectPrdState} canWrite={access?.can_write === true} busy={requestStates.action === 'loading'} onGenerate={(input) => void submitProjectSop(input)} />}
            <div className="growth-assets-view">
              <section className="growth-panel"><div className="growth-panel__heading"><div><p>ASSET INDEX</p><h3>{stageMeta?.label}</h3></div><span>{stageResult ? `${stageResult.records.length}${stageResult.truncated ? '+' : ''} loaded` : 'not loaded'}</span></div><GrowthAssetList stage={stage} records={records} selectedId={selectedId} query={query} statusFilter={statusFilter} page={page} pageSize={pageSize} totalHint={stageTotal(overview, stage)} truncated={Boolean(stageResult?.truncated)} serverCapped={stageResult?.limit === 500} state={requestStates.stage} error={stageError?.message} onQueryChange={setQuery} onStatusChange={setStatusFilter} onPageChange={setPage} onSelect={selectAsset} onRetry={refresh} /></section>
              <section className="growth-panel growth-reader"><div className="growth-panel__heading"><div><p>{detail?.kind === 'proposal' ? 'DIFF' : 'READER'}</p><h3>{selected ? growthRecordLabel(selected) : 'No asset selected'}</h3></div>{detail?.kind === 'proposal' ? <FileDiff size={17} /> : <BookOpen size={17} />}</div><AssetReader selected={selected} detail={detail} state={requestStates.detail} error={detailError?.message} /></section>
            </div>
          </>}
          {centerView === 'metrics' && <section className="growth-panel"><div className="growth-panel__heading"><div><p>QUALITY & TRENDS</p><h3>Persisted health observations</h3></div><BarChart3 size={18} /></div><GrowthTrends trend={trend} health={health} counts={counts} state={requestStates.metrics} error={metricsError?.message} onRetry={refresh} /></section>}
          {centerView === 'runs' && <section className="growth-panel"><div className="growth-panel__heading"><div><p>RUN LEDGER</p><h3>Inputs, sources, events, outputs and failure diagnostics</h3></div><span>{runs.length} durable runs</span></div><GrowthRunLedger runs={runs} selectedRunId={selectedRunId} events={runEvents} captureAttempts={runCaptureAttempts} failures={runFailures} state={requestStates.runs} error={runsError?.message} canWrite={access?.can_write === true} busy={requestStates.action === 'loading'} onSelect={setSelectedRunId} onResolveFailure={(failure) => void resolveFailure(failure)} onRetry={refresh} /></section>}
          {centerView === 'lineage' && <section className="growth-panel"><div className="growth-panel__heading"><div><p>LINEAGE</p><h3>Bounded evidence relationships</h3></div><span>{lineage ? `${lineage.edges.length}${lineage.truncated ? '+' : ''} edges` : 'not loaded'}</span></div><GrowthLineageGraph lineage={lineage} state={requestStates.lineage} error={lineageError?.message} relation={relation} onRelationChange={setRelation} onSelect={followAsset} onRetry={refresh} /></section>}
        </main>
        <GrowthInspector selected={selected} detail={detail} state={requestStates.detail} error={detailError?.message} edges={relevantEdges} nodes={lineage?.nodes} canWrite={access?.can_write ?? null} compact={compact} open={inspectorOpen} actionState={requestStates.action} actionMessage={actionMessage} evidenceSources={evidenceSources} evidenceState={evidenceState} onClose={() => setInspectorOpen(false)} onAction={(current) => void runAction(current)} onDistillSourceMethods={(current) => void distillSourceMethods(current)} onDistillAcceptedCandidate={(current) => void distillAcceptedCandidate(current)} onExtractSourceCandidates={(current) => void extractSourceCandidates(current)} onReviewCandidate={(current, review) => void reviewCandidate(current, review)} onEvaluate={(current, payload) => void submitEvaluation(current, payload)} onEvaluateMethod={(current) => void evaluateMethodCandidate(current)} onPublishMethod={(current) => void publishMethodCandidate(current)} onLinkEvidence={(current, payload) => void submitEvidence(current, payload)} onFeedback={(current, payload) => void submitFeedback(current, payload)} onFollow={followAsset} />
      </div>
    </>}
  </section>;
}
