import { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { useWorkspace } from '../store/workspaceStore';
import { useGrowthWorkspaceStore, useKnowledgeWorkspaceStore } from '../store/knowledgeWorkspaceStore';
import {
  cancelOrchestrate,
  startOrchestrate,
  subscribeStream,
  type ContextPolicy,
  type OrchestratorEvent,
} from '../api/orchestrateApi';
import { runAnalysis } from '../api/agentOsApi';
import type { AgentContextManifest, KnowledgeContextMetadata, KnowledgeOutputRegistration } from '../api/generated/agentOsContracts';
import { fetchWrapper } from '../api/fetchWrapper';
import { adaptAgentOsToDashboard } from '../utils/agentOsAdapter';
import { fetchCompilerDashboard, type DashboardData } from '../api/compilerDashboardApi';
import { RiskPanel } from './RiskPanel';
import { ConstraintCoveragePanel } from './ConstraintCoveragePanel';
import { CitationPanel } from './CitationPanel';
import { TrustedAuditPanel } from './TrustedAuditPanel';
import { CompilerEvalPanel } from './CompilerEvalPanel';
import { EvolutionPanel } from './EvolutionPanel';
import { AgentBriefPanel } from './AgentBriefPanel';
import { SopPanel } from './SopPanel';
import { AgentTerminal } from './AgentTerminal';
import { ContextPolicyControl } from './ContextPolicyControl';
import SkillMarket from './SkillMarket';
import {
  Blocks,
  BarChart3,
  Command,
  FileCode2,
  Network,
  BookOpen,
  Play,
  Sparkles,
  Sprout,
  Workflow,
  BrainCircuit,
} from 'lucide-react';

const GrowthWorkspace = lazy(() => import('./GrowthWorkspace').then((module) => ({ default: module.GrowthWorkspace })));
const KnowledgeWorkspace = lazy(() => import('./KnowledgeWorkspace').then((module) => ({ default: module.KnowledgeWorkspace })));
const BusinessControlCenter = lazy(() => import('./dbos/BusinessControlCenter').then((module) => ({ default: module.BusinessControlCenter })));
const KnowledgeOperationsCockpit = lazy(() => import('./operations/KnowledgeOperationsCockpit').then((module) => ({ default: module.KnowledgeOperationsCockpit })));
const PersonalGrowthCockpit = lazy(() => import('./pbos/PersonalGrowthCockpit').then((module) => ({ default: module.PersonalGrowthCockpit })));
const BusinessGraph = lazy(() => import('./BusinessGraph').then((module) => ({ default: module.BusinessGraph })));

// ---- Types ----
type Mode = 'auto' | 'business' | 'analyze' | 'compile' | 'board';
type LogType = 'system' | 'agent' | 'tool' | 'error' | 'result' | 'thinking' | 'stage';
interface LogEntry { id: string; type: LogType; text: string; time: string; }
type EffectiveMode = 'business' | 'analyze' | 'compile' | 'board';

export function formatRuntimeError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason || 'Analysis failed');
  if (/signal is aborted without reason|aborterror/i.test(message)) {
    return 'The Agent OS run exceeded the UI wait budget. The backend may still be completing; check results before retrying.';
  }
  if (/failed to fetch|networkerror/i.test(message)) {
    return 'Cannot reach the BSC API. Start the backend or set VITE_API_PROXY_TARGET, then restart Vite.';
  }
  if (/status:\s*401|authentication required/i.test(message)) {
    return 'Authentication required. Enter the runtime access key in the control rail.';
  }
  return message;
}

export function syncGrowthProjectContext(projectId: string): void {
  useGrowthWorkspaceStore.getState().setProjectId(projectId.trim());
}

export function syncKnowledgeProjectContext(projectId: string): void {
  useKnowledgeWorkspaceStore.getState().setProjectId(projectId.trim());
}

function includesModeSignal(text: string, signal: string): boolean {
  const normalized = signal.toLowerCase();
  if (!/^[a-z0-9]+(?:[ -][a-z0-9]+)*$/.test(normalized)) {
    return text.includes(normalized);
  }
  const escaped = normalized.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(text);
}

// ---- Auto-detect ----
export function detectMode(input: string): { mode: EffectiveMode; confidence: number; reason: string } {
  const text = input.toLowerCase(); const len = input.length;
  const boardSignals = ['board', '??', '??', 'ceo', 'cfo', 'cto', 'board review', 'multi-agent', '???'];
  const compileSignals = ['prd', '????', '????', 'compile', '??', 'sop', '????', 'pipeline', '????', '????', '???', '## ', '??', '??', '???'];
  const analyzeSignals = ['??', '??', '??', '??', '????', '??', '??', '??', 'analyze', 'gap', 'coverage', 'assumption', 'risk', '???', 'how', 'what', 'strategy'];
  const boardHits = boardSignals.filter((signal) => includesModeSignal(text, signal)).length;
  const compileHits = compileSignals.filter((signal) => includesModeSignal(text, signal)).length;
  const analyzeHits = analyzeSignals.filter((signal) => includesModeSignal(text, signal)).length;
  if (len > 500 && compileHits >= 2) return { mode: 'compile', confidence: 0.85, reason: 'Long structured document with PRD signals' };
  if (boardHits >= 2) return { mode: 'board', confidence: 0.9, reason: 'Explicit board/multi-agent review request' };
  if (boardHits === 1 && len < 200) return { mode: 'board', confidence: 0.7, reason: 'Board review signal detected' };
  if (compileHits >= 3) return { mode: 'compile', confidence: 0.85, reason: 'Strong compile/PRD signals detected' };
  if (compileHits >= 1 && len > 300) return { mode: 'compile', confidence: 0.7, reason: 'Structured content with compile signals' };
  if (analyzeHits >= 1) return { mode: 'analyze', confidence: 0.8, reason: 'Explicit analysis/evaluation request detected' };
  if (len > 400) return { mode: 'compile', confidence: 0.55, reason: 'Long content, defaulting to compile' };
  return { mode: 'business', confidence: 0.7, reason: 'Business requests begin with diagnosis before a Dynamic SOP is compiled' };
}

// ---- Constants ----
const MODE_LABELS: Record<Mode, string> = { auto: 'Auto', business: 'Business OS', analyze: 'Agent OS', compile: 'Compiler', board: 'Board' };
const MODE_HINTS: Record<EffectiveMode, string> = {
  business: 'Diagnose the role, environment, objective, evidence, and constraints before compiling a Dynamic SOP.',
  analyze: 'Deep LLM analysis: assumptions, risks, gaps, coverage',
  compile: 'Real-time pipeline: PRD \u2192 Business Model \u2192 Risk \u2192 SOP \u2192 KPI \u2192 Review',
  board: 'Multi-agent board review with CEO, CFO, CTO perspectives',
};
const LOG_COLORS: Record<LogType, string> = {
  system: 'text-[#8b949e]', agent: 'text-[#58a6ff]', tool: 'text-[#d29922]',
  error: 'text-[#f85149]', result: 'text-[#3fb950]', thinking: 'text-[#a371f7]',
  stage: 'text-[#58a6ff]',
};
let logCounter = 0;
// This is a non-secret marker for Vite's local-only authorized proxy. The
// actual API key remains in the Vite process and overwrites this sentinel.
const LOCAL_PROXY_SENTINEL = import.meta.env.DEV
  && typeof __BSC_LOCAL_PROXY_AUTH__ !== 'undefined'
  && __BSC_LOCAL_PROXY_AUTH__
  ? 'local-proxy'
  : '';

export function isLocalProxySession(runtimeAccessKey: string, sentinel = LOCAL_PROXY_SENTINEL): boolean {
  return Boolean(sentinel) && runtimeAccessKey === sentinel;
}

// The rail renders actual runtime capability events, not a parallel UI-only plan.
const PIPELINE_STAGES = [
  'business_understanding',
  'assumption_reasoning',
  'risk_analysis',
  'constraint_generation',
  'coverage_analysis',
  'gap_detection',
  'decision_support',
  'report_composition',
];

const BUSINESS_OS_STAGES = [
  'diagnosis',
  'capability_selection',
  'dynamic_sop',
  'authorization_gate',
  'execution_feedback',
];

function stageLabel(stage: string): string {
  return stage.replace(/_/g, ' ');
}

function projectAgentPipeline(executions: Array<{ capability_name: string; status: string; error: string }>): Record<string, string> {
  const byCapability = new Map(executions.map((execution) => [execution.capability_name, execution]));
  return Object.fromEntries(PIPELINE_STAGES.map((stage) => {
    const execution = byCapability.get(stage);
    if (!execution) return [stage, 'pending'];
    if (execution.status === 'success' || execution.status === 'completed') return [stage, 'completed'];
    return [stage, execution.error ? 'failed' : execution.status || 'pending'];
  }));
}

export function UnifiedWorkspace() {
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<Mode>('auto');
  const [detectedMode, setDetectedMode] = useState<EffectiveMode | null>(null);
  const [detectReason, setDetectReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [dashData, setDashData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [pipelineStages, setPipelineStages] = useState<Record<string, string>>({});
  const [contextPolicy, setContextPolicy] = useState<ContextPolicy>('fresh');
  const [parentSessionId, setParentSessionId] = useState('');
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [growthOpen, setGrowthOpen] = useState(false);
  const [operationsOpen, setOperationsOpen] = useState(false);
  const [dbosOpen, setDbosOpen] = useState(false);
  const [pbosOpen, setPbosOpen] = useState(false);
  const [dbosMissionId, setDbosMissionId] = useState('');
  const [dbosArtifactId, setDbosArtifactId] = useState('');
  const [dbosInitialRequest, setDbosInitialRequest] = useState('');
  const [runtimeAccessKey, setRuntimeAccessKey] = useState(LOCAL_PROXY_SENTINEL);
  const [knowledgeContext, setKnowledgeContext] = useState<KnowledgeContextMetadata | null>(null);
  const [knowledgeOutputRegistration, setKnowledgeOutputRegistration] = useState<KnowledgeOutputRegistration | null>(null);
  const localProxySession = isLocalProxySession(runtimeAccessKey);
  const [contextManifest, setContextManifest] = useState<AgentContextManifest | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const runtimeAccessRef = useRef<HTMLInputElement>(null);

  // Workspace store
  const beginSession = useWorkspace((s) => s.beginSession);
  const appendEvent = useWorkspace((s) => s.appendEvent);
  const clearTerminal = useWorkspace((s) => s.clearTerminal);
  const terminalEvents = useWorkspace((s) => s.terminalEvents);
  const applyDashboard = useWorkspace((s) => s.applyDashboard);
  const businessModel = useWorkspace((s) => s.businessModel);
  const sop = useWorkspace((s) => s.sop);
  const workspaceIdea = useWorkspace((s) => s.idea);
  const storeKnowledgeProjectId = useKnowledgeWorkspaceStore((s) => s.projectId);
  const [knowledgeProjectId, setKnowledgeProjectId] = useState(storeKnowledgeProjectId);
  const activateKnowledgeProject = useCallback((projectId: string) => {
    const normalized = projectId.trim();
    setKnowledgeProjectId(normalized);
    syncKnowledgeProjectContext(normalized);
  }, []);

  // Keep the Studio-level selection stable when a lazy workspace mounts.
  // An explicit blank field is still honored as the user's clear action.
  useEffect(() => {
    const normalized = storeKnowledgeProjectId.trim();
    if (normalized && normalized !== knowledgeProjectId) setKnowledgeProjectId(normalized);
  }, [knowledgeProjectId, storeKnowledgeProjectId]);

  const addLog = useCallback((type: LogType, text: string) => {
    const entry: LogEntry = { id: String(++logCounter), type, text, time: new Date().toLocaleTimeString('en-US', { hour12: false }) };
    setLogs(prev => [...prev.slice(-300), entry]);
  }, []);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  useEffect(() => {
    fetchWrapper.setAuthToken(runtimeAccessKey.trim() || undefined);
  }, [runtimeAccessKey]);

  // Keyboard shortcut
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); inputRef.current?.focus(); } };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h);
  }, []);

  // Auto-detect on input change
  useEffect(() => {
    if (mode === 'auto' && input.trim()) {
      const d = detectMode(input); setDetectedMode(d.mode); setDetectReason(d.reason);
    }
  }, [input, mode]);

  const effectiveMode: EffectiveMode = mode === 'auto' ? (detectedMode || 'business') : (mode as EffectiveMode);

  // ---- Submit Handler ----
  const handleSubmit = async () => {
    if (!input.trim() || loading) return;
    if (effectiveMode === 'compile' && contextPolicy !== 'fresh' && !parentSessionId.trim()) {
      setError('Parent session id is required for fork or resume');
      return;
    }
    const value = input.trim();
    setInput(''); setLoading(true); setError(null); setDashData(null); setLogs([]); setKnowledgeContext(null); setKnowledgeOutputRegistration(null); setContextManifest(null);
    logCounter = 0; setPipelineStages({});
    clearTerminal();

    addLog('system', 'Mode: ' + MODE_LABELS[effectiveMode] + (mode === 'auto' ? ' (auto)' : ''));
    addLog('system', 'Input: ' + (value.length > 80 ? value.slice(0, 80) + '...' : value));
    addLog('system', 'Project context: ' + (knowledgeProjectId.trim() || 'unscoped'));

    try {
      if (effectiveMode === 'business') {
        // Creating an Intake is non-executable: it collects context before a Mission or capability grant exists.
        addLog('agent', 'Opening governed diagnosis before compiling a Dynamic SOP...');
        setDbosInitialRequest(value);
        setDbosMissionId('');
        setDbosArtifactId('');
        setDbosOpen(true);
        return;
      }

      if (effectiveMode === 'compile') {
        // ---- Real-time Pipeline Compilation ----
        setCompiling(true);
        addLog('agent', 'Starting compiler pipeline...');
        const res = await startOrchestrate(value, {
          contextPolicy,
          parentSessionId: contextPolicy === 'fresh' ? undefined : parentSessionId.trim(),
          projectId: knowledgeProjectId.trim() || undefined,
        });
        beginSession(res.session_id, value);
        setSessionId(res.session_id);
        setParentSessionId(res.session_id);
        addLog('system', 'Session ' + res.session_id.slice(0, 8));

        let source: EventSource | null = null;
        source = subscribeStream(
          res,
          (event: OrchestratorEvent) => {
            appendEvent(event);
            const status = event.status === 'done'
              ? 'completed'
              : (event.status || 'running');
            setPipelineStages((previous) => ({
              ...previous,
              [event.stage]: status,
            }));
            addLog(
              'stage',
              `[${event.stage}] ${event.type}${event.message ? `: ${event.message}` : ''}`,
            );

            if (!event.terminal) return;
            source?.close();
            setCompiling(false);

            if (event.type === 'pipeline.completed') {
              void fetchCompilerDashboard(res.session_id)
                .then((dashboard) => {
                  applyDashboard(dashboard);
                  setDashData(dashboard);
                  if (dashboard.execution?.degraded) {
                    addLog('error', 'Completed with degraded LLM fallback output');
                  }
                  addLog('result', 'Pipeline completed');
                })
                .catch((dashboardError: unknown) => {
                  const message = dashboardError instanceof Error
                    ? dashboardError.message
                    : 'Dashboard request failed';
                  setError(message);
                  addLog('error', message);
                })
                .finally(() => setLoading(false));
              return;
            }

            const message = event.message || `Pipeline ended with ${event.status}`;
            setError(message);
            addLog('error', message);
            setLoading(false);
          },
          () => {
            addLog('system', 'Event stream disconnected; browser will retry');
          },
        );

      } else {
        // ---- Agent OS / Board ----
        const isBoard = effectiveMode === 'board';
        addLog('thinking', isBoard ? 'Convening board: CEO, CFO, CTO, Ops...' : 'Planning mission capabilities...');
        const result = await runAnalysis({
          input: value,
          mode: 'llm',
          board: isBoard,
          project_id: knowledgeProjectId.trim(),
        });
        if (result.status !== 'completed') {
          throw new Error(result.runtime.errors[0] || 'Agent OS did not complete the analysis');
        }
        beginSession(result.execution_id, value);
        setSessionId(result.execution_id);
        setPipelineStages(projectAgentPipeline(result.runtime.capability_executions));
        setKnowledgeContext(result.runtime.knowledge_context);
        setKnowledgeOutputRegistration(result.runtime.knowledge_output_registration);
        setContextManifest(result.runtime.context_manifest);
        if (result.runtime.context_manifest) {
          const inherited = result.runtime.context_manifest.inherited;
          const summarized = inherited.filter((item) => item.disposition === 'summarized').length;
          const omitted = inherited.filter((item) => item.disposition === 'omitted').length;
          addLog('tool', `Context ${result.runtime.context_manifest.policy || 'fresh'}: ${inherited.length} inherited, ${summarized} summarized, ${omitted} omitted`);
        }
        if (result.runtime.knowledge_context.knowledge_context_used) {
          const references = result.runtime.knowledge_context.page_ids.length
            + result.runtime.knowledge_context.source_ids.length
            + result.runtime.knowledge_context.method_revision_ids.length
            + result.runtime.knowledge_context.output_ids.length;
          addLog('tool', 'Project knowledge used: ' + references + ' governed references / pack ' + result.runtime.knowledge_context.context_pack_id.slice(0, 12));
        } else {
          const gap = result.runtime.knowledge_context.research_gaps[0];
          addLog('tool', 'Project knowledge unavailable' + (gap ? ': ' + gap : ''));
        }
        const registration = result.runtime.knowledge_output_registration;
        if (registration.registered > 0) {
          addLog('result', `D-layer staged ${registration.registered} reviewable output${registration.registered === 1 ? '' : 's'}; evaluation is required before reuse.`);
        } else if (registration.attempted > 0) {
          addLog('error', 'D-layer staging did not complete: ' + (registration.errors[0] || registration.status));
        } else if (result.runtime.knowledge_context.knowledge_context_used) {
          addLog('tool', 'D-layer staging: ' + registration.status.replace(/_/g, ' '));
        }
        addLog('agent', 'Mission: ' + result.mission.title);
        addLog('system', 'Steps: ' + result.mission.steps + ' | Mode: ' + result.mission.mode);
        if (result.artifacts > 0) addLog('result', 'Artifacts: ' + result.artifacts);
        if (result.gaps > 0) {
          addLog('tool', 'Gaps: ' + result.gaps);
          result.gap_details.forEach(g => addLog('tool', '[' + g.severity.toUpperCase() + '] ' + g.category + ': ' + g.description));
        }
        if (result.runtime.degraded) {
          addLog('error', 'Analysis completed with degraded LLM fallback output');
        }
        if (result.board_verdict) {
          addLog('result', 'Verdict: ' + result.board_verdict.toUpperCase());
          if (result.board_consensus) addLog('agent', 'Consensus: ' + result.board_consensus);
        }
        setDashData(adaptAgentOsToDashboard(result));
        addLog('result', 'Analysis complete');
        setLoading(false);
      }
    } catch (reason: unknown) {
      const message = formatRuntimeError(reason);
      addLog('error', message);
      setError(message);
      setCompiling(false);
      setLoading(false);
    }
  };

  const statusColor = loading ? 'status-dot--running' : error ? 'status-dot--error' : 'status-dot--active';
  const statusLabel = loading ? (compiling ? 'Compiling' : 'Running') : error ? 'Error' : 'Ready';
  const visibleStages = effectiveMode === 'business' ? BUSINESS_OS_STAGES : PIPELINE_STAGES;
  const completedStages = visibleStages.filter((stage) => pipelineStages[stage] === 'completed').length;
  const sessionDisplay = sessionId ? sessionId.slice(0, 12) : 'new session';

  return (
    <div className="studio-shell" role="application" aria-label="BSC Studio">
      <header className="studio-header">
        <div className="studio-brand">
          <span className="studio-mark" aria-hidden="true"><Command size={16} /></span>
          <div><strong>BSC Studio</strong><span>orchestration workspace</span></div>
        </div>
        <div className="studio-header__crumb"><Network size={14} aria-hidden="true" /> Business Runtime</div>
        <div className="studio-header__actions">
          <button type="button" className="skill-trigger" onClick={() => setSkillsOpen(true)}>
            <Blocks size={15} aria-hidden="true" /> Skills
          </button>
          <button type="button" className="skill-trigger" onClick={() => { activateKnowledgeProject(knowledgeProjectId); setKnowledgeOpen(true); }}>
            <BookOpen size={15} aria-hidden="true" /> Knowledge
          </button>
          <button type="button" className="skill-trigger" onClick={() => { syncGrowthProjectContext(knowledgeProjectId); setGrowthOpen(true); }} disabled={!knowledgeProjectId.trim()} title={knowledgeProjectId.trim() ? 'Open the active project growth loop' : 'Select an authorized knowledge project first'}>
            <Sprout size={15} aria-hidden="true" /> Growth
          </button>
          <button type="button" className="skill-trigger" onClick={() => setOperationsOpen(true)}>
            <BarChart3 size={15} aria-hidden="true" /> Operate
          </button>
          <button type="button" className="skill-trigger" onClick={() => setPbosOpen(true)} disabled={!knowledgeProjectId.trim()} title={knowledgeProjectId.trim() ? 'Open the active project personal operating loop' : 'Select an authorized knowledge project first'}>
            <BrainCircuit size={15} aria-hidden="true" /> PBOS
          </button>
          <button type="button" className="skill-trigger" onClick={() => { setDbosMissionId(''); setDbosArtifactId(''); setDbosOpen(true); }} disabled={!knowledgeProjectId.trim()} title={knowledgeProjectId.trim() ? 'Open a mission for the active project' : 'Select an authorized knowledge project first'}>
            <Workflow size={15} aria-hidden="true" /> Mission
          </button>
          <span className={'studio-status ' + statusColor}><i aria-hidden="true" />{statusLabel}</span>
          <code>{sessionDisplay}</code>
        </div>
      </header>

      <div className="studio-workbench">
        <aside className="control-rail" aria-label="Workspace controls">
          <section className="rail-section">
            <p className="rail-label">RUN PROFILE</p>
            <div className="mode-stack" role="radiogroup" aria-label="Execution mode">
              {(['auto', 'business', 'analyze', 'compile', 'board'] as Mode[]).map((nextMode) => (
                <button
                  key={nextMode}
                  type="button"
                  role="radio"
                  aria-checked={mode === nextMode}
                  onClick={() => setMode(nextMode)}
                  className={mode === nextMode ? 'is-selected' : ''}
                >
                  <span>{nextMode === 'business' ? <Blocks size={15} /> : nextMode === 'compile' ? <Workflow size={15} /> : nextMode === 'board' ? <Sparkles size={15} /> : <FileCode2 size={15} />}</span>
                  <span><strong>{nextMode === 'auto' && detectedMode ? `Auto: ${MODE_LABELS[detectedMode]}` : MODE_LABELS[nextMode]}</strong><small>{nextMode === 'business' ? 'Diagnosis to Dynamic SOP' : nextMode === 'compile' ? 'Durable multi-stage run' : nextMode === 'board' ? 'Multi-agent verdict' : nextMode === 'analyze' ? 'Risk and coverage analysis' : 'Business OS by default'}</small></span>
                </button>
              ))}
            </div>
          </section>

          <section className="rail-section runtime-access">
            <div className="rail-section__heading"><p className="rail-label">RUNTIME ACCESS</p><span>{runtimeAccessKey ? (localProxySession ? 'local proxy' : 'ready') : 'required'}</span></div>
            <label className="runtime-access__field">
              <span>{localProxySession ? 'Local proxy authentication' : 'API key'}</span>
              <input
                ref={runtimeAccessRef}
                type="password"
                value={localProxySession ? '' : runtimeAccessKey}
                onChange={(event) => {
                  const value = event.target.value;
                  setRuntimeAccessKey(value || LOCAL_PROXY_SENTINEL);
                }}
                placeholder={localProxySession ? 'Authenticated locally' : 'Runtime access key'}
                aria-label="Runtime access key"
                autoComplete="off"
              />
            </label>
          </section>

          <section className="rail-section runtime-access knowledge-context-control">
            <div className="rail-section__heading"><p className="rail-label">PROJECT KNOWLEDGE</p><span>{knowledgeContext ? (knowledgeContext.knowledge_context_used ? 'used' : knowledgeContext.availability) : 'not checked'}</span></div>
            <label className="runtime-access__field">
              <span>Project ID</span>
              <input
                type="text"
                value={knowledgeProjectId}
                onChange={(event) => activateKnowledgeProject(event.target.value)}
                placeholder="Mapped knowledge project"
                aria-label="Project knowledge context ID"
                autoComplete="off"
                disabled={loading}
              />
            </label>
            <p className="rail-note">A run verifies the mapped Vault, pages, methods and prior outputs before it reports that knowledge was used.</p>
            {knowledgeContext && <p className={'knowledge-context-status ' + (knowledgeContext.knowledge_context_used ? 'is-used' : 'is-unavailable')}>
              {knowledgeContext.knowledge_context_used
                ? `${knowledgeContext.page_ids.length} pages, ${knowledgeContext.source_ids.length} sources, ${knowledgeContext.method_revision_ids.length} methods, ${knowledgeContext.output_ids.length} prior outputs`
                : (knowledgeContext.research_gaps[0] || 'No approved project context was available for this run.')}
            </p>}
            {knowledgeOutputRegistration && <p className={'knowledge-context-status ' + (knowledgeOutputRegistration.registered > 0 ? 'is-used' : 'is-unavailable')}>
              {knowledgeOutputRegistration.registered > 0
                ? `${knowledgeOutputRegistration.registered} new D-layer output${knowledgeOutputRegistration.registered === 1 ? '' : 's'} awaiting evaluation before knowledge reuse`
                : `D-layer: ${knowledgeOutputRegistration.status.replace(/_/g, ' ')}`}
            </p>}
          </section>

          <section className="rail-section rail-context">
            <div className="rail-section__heading"><p className="rail-label">CONTEXT LINEAGE</p><span>{effectiveMode === 'compile' ? contextPolicy : 'not used'}</span></div>
            {effectiveMode === 'compile' ? (
              <ContextPolicyControl
                policy={contextPolicy}
                parentSessionId={parentSessionId}
                disabled={loading}
                onPolicyChange={setContextPolicy}
                onParentSessionIdChange={setParentSessionId}
              />
            ) : (
              <p className="rail-note">Fresh, fork and resume are applied to Compiler runs, where session context is persisted and validated.</p>
            )}
            {contextManifest && <div className="context-manifest-status" aria-label="Last runtime context manifest">
              <div><span>Last runtime</span><code>{contextManifest.manifest_id.slice(0, 12)}</code></div>
              <p>{contextManifest.policy || 'fresh'} / {contextManifest.compaction_mode || 'summary'} / {contextManifest.source_session_ids.length} source sessions</p>
              <dl>
                <div><dt>Included</dt><dd>{contextManifest.inherited.filter((item) => item.disposition === 'included').length}</dd></div>
                <div><dt>Summarized</dt><dd>{contextManifest.inherited.filter((item) => item.disposition === 'summarized').length}</dd></div>
                <div><dt>Omitted</dt><dd>{contextManifest.inherited.filter((item) => item.disposition === 'omitted').length}</dd></div>
              </dl>
            </div>}
          </section>

          <section className="rail-section rail-stages">
            <div className="rail-section__heading"><p className="rail-label">{effectiveMode === 'business' ? 'BUSINESS SYSTEM' : effectiveMode === 'compile' ? 'PIPELINE' : 'CAPABILITY PLAN'}</p><span>{completedStages}/{visibleStages.length}</span></div>
            <ol>
              {visibleStages.map((stage) => {
                const stageStatus = pipelineStages[stage] || 'pending';
                return <li key={stage} data-status={stageStatus}><i aria-hidden="true" /><span>{stageLabel(stage)}</span><small>{stageStatus}</small></li>;
              })}
            </ol>
          </section>
        </aside>

        <div className="command-column">
          <section className="mission-deck" aria-labelledby="mission-title">
            <div className="mission-deck__top"><span>NEW MISSION</span><span>{mode === 'auto' && detectedMode ? `${Math.round(detectMode(input).confidence * 100)}% match` : MODE_LABELS[effectiveMode]}</span></div>
            <h1 id="mission-title">Turn a prompt into an executable business system.</h1>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                  event.preventDefault();
                  void handleSubmit();
                }
              }}
              placeholder="Describe an idea, paste a PRD, or ask for a strategic decision..."
              disabled={loading}
              aria-label="Business analysis input"
            />
            <div className="mission-deck__footer">
              <p>{mode === 'auto' && detectedMode ? `Auto selected ${MODE_LABELS[detectedMode]}: ${detectReason}` : MODE_HINTS[effectiveMode]}</p>
              <div><kbd>Ctrl</kbd><span>+</span><kbd>Enter</kbd><span>to run</span></div>
              <button type="button" onClick={() => void handleSubmit()} disabled={loading || !input.trim()}>
                {loading ? <><i className="spinner" aria-hidden="true" /> Running</> : <><Play size={15} fill="currentColor" aria-hidden="true" /> Run workflow</>}
              </button>
            </div>
          </section>

          <section className="runtime-card" aria-label="Runtime activity">
            <div className="panel-heading"><div><p>LIVE RUNTIME</p><h2>{compiling ? 'Pipeline is executing' : terminalEvents.length ? 'Runtime event stream' : 'Ready for a mission'}</h2></div><span>{terminalEvents.length ? `${terminalEvents.length} events` : 'SSE ready'}</span></div>
            <div className="runtime-card__body">
              {(terminalEvents.length > 0 || effectiveMode === 'compile') ? <AgentTerminal /> : (
                <div className="activity-log" role="log" aria-live="polite">
                  {logs.length === 0 && !loading && <div className="runtime-empty"><Command size={26} aria-hidden="true" /><p>Runtime output lands here.</p><small>Choose a run profile, add a mission, then execute it.</small></div>}
                  {logs.map((entry) => <div key={entry.id} className="log-entry" style={{ animationDelay: '0ms' }}><time>{entry.time}</time><span className={LOG_COLORS[entry.type]}>{entry.text}</span></div>)}
                  {loading && <div className="log-entry is-pending"><time>{new Date().toLocaleTimeString('en-US', { hour12: false })}</time><span>{compiling ? 'Pipeline running...' : 'Thinking...'}</span></div>}
                  <div ref={logEndRef} />
                </div>
              )}
            </div>
          </section>

          {compiling && (businessModel && Object.keys(businessModel).length > 0 || sop && Object.keys(sop).length > 0) && (
            <section className="artifact-preview"><div className="panel-heading"><div><p>IN-FLIGHT ARTIFACTS</p><h2>Streaming work products</h2></div></div>{businessModel && Object.keys(businessModel).length > 0 && <Suspense fallback={<div className="artifact-graph-loading" role="status">Loading workflow graph...</div>}><BusinessGraph model={businessModel} /></Suspense>}{sop && Object.keys(sop).length > 0 && <SopPanel sop={sop} />}</section>
          )}
        </div>

        <main className="inspector-column" aria-label="Results inspector">
          <div className="panel-heading inspector-heading"><div><p>RESULT INSPECTOR</p><h2>{dashData ? 'Decision-ready output' : loading ? 'Building results' : 'No result selected'}</h2></div>{dashData && <span className="decision-badge">{dashData.risk.gate.decision}</span>}</div>
          {error && !dashData && <div className="inline-error" role="alert"><strong>Run stopped</strong><p>{error}</p></div>}
          {loading && !dashData && (
            <div className="run-progress">
              <div className="run-progress__meta"><span>{compiling ? 'Compiler stages' : 'Capability execution'}</span><strong>{compiling ? `${completedStages}/${PIPELINE_STAGES.length}` : 'working'}</strong></div>
              {compiling && PIPELINE_STAGES.map((stage) => <div key={stage} className="stage-progress" data-status={pipelineStages[stage] || 'pending'}><span>{stageLabel(stage)}</span><i /><small>{pipelineStages[stage] || 'queued'}</small></div>)}
              {compiling && sessionId && <button type="button" className="cancel-run" onClick={() => { addLog('system', 'Cancellation requested'); void cancelOrchestrate(sessionId).catch((cancelError: unknown) => { const message = cancelError instanceof Error ? cancelError.message : 'Cancellation request failed'; setError(message); addLog('error', message); }); }}>Cancel run</button>}
            </div>
          )}
          {!loading && !error && !dashData && <div className="inspector-empty"><div><FileCode2 size={25} aria-hidden="true" /></div><h3>{effectiveMode === 'business' ? 'Start with a business diagnosis.' : 'Output with evidence.'}</h3><p>{effectiveMode === 'business' ? 'Your request will be clarified into a Mission, then compiled into a role-specific capability set and Dynamic SOP. No capability executes until you authorize it.' : effectiveMode === 'compile' ? 'The inspector will collect the decision gate, risk coverage, graph and SOP produced by this run.' : 'Analysis results, coverage evidence and multi-agent decisions will be collected here.'}</p></div>}
          {dashData && (
            <div className="result-stack animate-fade-in-up">
              <div className="result-summary"><div><span>RISK GATE</span><strong>{dashData.risk.gate.decision}</strong></div><div><span>COVERAGE</span><strong>{dashData.risk.coverage.coverage_pct}%</strong></div><div><span>RISKS</span><strong>{dashData.risk.risks.length}</strong></div></div>
              <section className="result-block"><AgentBriefPanel businessModel={dashData.business_model} /></section>
              <section className="result-block"><RiskPanel risk={dashData.risk} /></section>
              <section className="result-block"><ConstraintCoveragePanel coverage={dashData.risk.coverage} /></section>
              <section className="result-block"><CitationPanel sop={dashData.sop} /></section>
              {dashData.trusted_audit && <section className="result-block"><TrustedAuditPanel trustedAudit={dashData.trusted_audit} /></section>}
              {dashData.evaluation && <section className="result-block"><CompilerEvalPanel evaluation={dashData.evaluation} coverage={dashData.risk.coverage} /></section>}
              {dashData.evolution && <section className="result-block"><EvolutionPanel evolution={dashData.evolution} /></section>}
            </div>
          )}
        </main>
      </div>

      <footer className="studio-footer"><span>{mode === 'auto' && detectedMode ? `Auto -> ${MODE_LABELS[detectedMode]}` : MODE_LABELS[effectiveMode]}</span><span>Project: {knowledgeProjectId || 'unscoped'}</span><span>Session: {sessionDisplay}</span>{compiling && <span className="is-live">pipeline active</span>}{dashData && <span>coverage: {dashData.risk.coverage.coverage_pct}%</span>}<span className="studio-footer__right">BSC Studio 5.0</span></footer>
      {skillsOpen && <SkillMarket onClose={() => setSkillsOpen(false)} context={input || workspaceIdea} />}
      {knowledgeOpen && <Suspense fallback={<section className="knowledge-workspace" aria-label="Knowledge workspace"><div className="knowledge-loading" role="status">Loading knowledge workspace...</div></section>}><KnowledgeWorkspace onClose={() => setKnowledgeOpen(false)} runtimeAccessKey={runtimeAccessKey} activeProjectId={knowledgeProjectId} onProjectChange={activateKnowledgeProject} /></Suspense>}
      {growthOpen && <Suspense fallback={<section className="growth-workspace" aria-label="Knowledge growth workspace"><div className="growth-state" role="status">Loading growth workspace...</div></section>}><GrowthWorkspace onClose={() => setGrowthOpen(false)} runtimeAccessKey={runtimeAccessKey} /></Suspense>}
      {operationsOpen && <Suspense fallback={<section className="operations-cockpit" aria-label="Knowledge operations cockpit"><div className="operations-loading" role="status">Loading knowledge operations...</div></section>}><KnowledgeOperationsCockpit onClose={() => setOperationsOpen(false)} initialProjectId={knowledgeProjectId} onOpenKnowledge={(projectId, entityId) => { activateKnowledgeProject(projectId); useKnowledgeWorkspaceStore.getState().setNavigationTarget(entityId); setOperationsOpen(false); setKnowledgeOpen(true); }} onOpenGrowth={(projectId, entityId) => { activateKnowledgeProject(projectId); const growthStore = useGrowthWorkspaceStore.getState(); growthStore.setProjectId(projectId); growthStore.setStage('review'); growthStore.setCenterView('assets'); growthStore.setSelectedId(entityId); setOperationsOpen(false); setGrowthOpen(true); }} onOpenDbos={(projectId, missionId, artifactId) => { activateKnowledgeProject(projectId); setDbosMissionId(missionId); setDbosArtifactId(artifactId); setOperationsOpen(false); setDbosOpen(true); }} /></Suspense>}
      {pbosOpen && Boolean(knowledgeProjectId.trim()) && <Suspense fallback={<section className="pbos-cockpit" aria-label="Personal Growth Cockpit"><p className="pbos-empty">Loading personal growth evidence...</p></section>}><PersonalGrowthCockpit projectId={knowledgeProjectId} runtimeAccessKey={runtimeAccessKey} onClose={() => setPbosOpen(false)} onConfigureAccess={() => { setPbosOpen(false); window.requestAnimationFrame(() => runtimeAccessRef.current?.focus()); }} /></Suspense>}
      {dbosOpen && Boolean(knowledgeProjectId.trim()) && <Suspense fallback={<section className="dbos-control-center" aria-label="Business Control Center"><div className="dbos-message" role="status">Loading mission control center...</div></section>}><BusinessControlCenter onClose={() => setDbosOpen(false)} initialProjectId={knowledgeProjectId} initialMissionId={dbosMissionId} initialArtifactId={dbosArtifactId} initialRequestText={dbosInitialRequest} autoStartIntake={Boolean(dbosInitialRequest)} /></Suspense>}
    </div>
  );
}
