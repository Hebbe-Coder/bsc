import { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { useWorkspace } from '../store/workspaceStore';
import {
  cancelOrchestrate,
  startOrchestrate,
  subscribeStream,
  type ContextPolicy,
  type OrchestratorEvent,
} from '../api/orchestrateApi';
import { runAnalysis } from '../api/agentOsApi';
import { adaptAgentOsToDashboard } from '../utils/agentOsAdapter';
import { fetchCompilerDashboard, type DashboardData } from '../api/compilerDashboardApi';
import { RiskPanel } from './RiskPanel';
import { ConstraintCoveragePanel } from './ConstraintCoveragePanel';
import { CitationPanel } from './CitationPanel';
import { TrustedAuditPanel } from './TrustedAuditPanel';
import { CompilerEvalPanel } from './CompilerEvalPanel';
import { EvolutionPanel } from './EvolutionPanel';
import { AgentBriefPanel } from './AgentBriefPanel';
import { BusinessGraph } from './BusinessGraph';
import { SopPanel } from './SopPanel';
import { AgentTerminal } from './AgentTerminal';
import { ContextPolicyControl } from './ContextPolicyControl';
import SkillMarket from './SkillMarket';
import { KnowledgeWorkspace } from './KnowledgeWorkspace';
import {
  Blocks,
  Command,
  FileCode2,
  Network,
  BookOpen,
  Play,
  Sparkles,
  Sprout,
  Workflow,
} from 'lucide-react';

const GrowthWorkspace = lazy(() => import('./GrowthWorkspace').then((module) => ({ default: module.GrowthWorkspace })));

// ---- Types ----
type Mode = 'auto' | 'analyze' | 'compile' | 'board';
type LogType = 'system' | 'agent' | 'tool' | 'error' | 'result' | 'thinking' | 'stage';
interface LogEntry { id: string; type: LogType; text: string; time: string; }
type EffectiveMode = 'analyze' | 'compile' | 'board';

function includesModeSignal(text: string, signal: string): boolean {
  const normalized = signal.toLowerCase();
  if (!/^[a-z0-9]+(?:[ -][a-z0-9]+)*$/.test(normalized)) {
    return text.includes(normalized);
  }
  const escaped = normalized.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(text);
}

// ---- Auto-detect ----
function detectMode(input: string): { mode: EffectiveMode; confidence: number; reason: string } {
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
  if (analyzeHits >= 1) return { mode: 'analyze', confidence: 0.8, reason: 'Analysis/evaluation question detected' };
  if (len > 400) return { mode: 'compile', confidence: 0.55, reason: 'Long content, defaulting to compile' };
  return { mode: 'analyze', confidence: 0.6, reason: 'Default analysis mode' };
}

// ---- Constants ----
const MODE_LABELS: Record<Mode, string> = { auto: 'Auto', analyze: 'Agent OS', compile: 'Compiler', board: 'Board' };
const MODE_HINTS: Record<EffectiveMode, string> = {
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
  const logEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Workspace store
  const beginSession = useWorkspace((s) => s.beginSession);
  const appendEvent = useWorkspace((s) => s.appendEvent);
  const clearTerminal = useWorkspace((s) => s.clearTerminal);
  const terminalEvents = useWorkspace((s) => s.terminalEvents);
  const applyDashboard = useWorkspace((s) => s.applyDashboard);
  const businessModel = useWorkspace((s) => s.businessModel);
  const sop = useWorkspace((s) => s.sop);
  const workspaceIdea = useWorkspace((s) => s.idea);

  const addLog = useCallback((type: LogType, text: string) => {
    const entry: LogEntry = { id: String(++logCounter), type, text, time: new Date().toLocaleTimeString('en-US', { hour12: false }) };
    setLogs(prev => [...prev.slice(-300), entry]);
  }, []);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

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

  const effectiveMode: EffectiveMode = mode === 'auto' ? (detectedMode || 'analyze') : (mode as EffectiveMode);

  // ---- Submit Handler ----
  const handleSubmit = async () => {
    if (!input.trim() || loading) return;
    if (effectiveMode === 'compile' && contextPolicy !== 'fresh' && !parentSessionId.trim()) {
      setError('Parent session id is required for fork or resume');
      return;
    }
    const value = input.trim();
    setInput(''); setLoading(true); setError(null); setDashData(null); setLogs([]);
    logCounter = 0; setPipelineStages({});
    clearTerminal();

    addLog('system', 'Mode: ' + MODE_LABELS[effectiveMode] + (mode === 'auto' ? ' (auto)' : ''));
    addLog('system', 'Input: ' + (value.length > 80 ? value.slice(0, 80) + '...' : value));

    try {
      if (effectiveMode === 'compile') {
        // ---- Real-time Pipeline Compilation ----
        setCompiling(true);
        addLog('agent', 'Starting compiler pipeline...');
        const res = await startOrchestrate(value, {
          contextPolicy,
          parentSessionId: contextPolicy === 'fresh' ? undefined : parentSessionId.trim(),
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
        const result = await runAnalysis({ input: value, mode: 'llm', board: isBoard });
        if (result.status !== 'completed') {
          throw new Error(result.runtime.errors[0] || 'Agent OS did not complete the analysis');
        }
        beginSession(result.execution_id, value);
        setSessionId(result.execution_id);
        setPipelineStages(projectAgentPipeline(result.runtime.capability_executions));
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
    } catch (e: any) {
      addLog('error', e.message || 'Failed');
      setError(e.message || 'Analysis failed');
      setCompiling(false);
      setLoading(false);
    }
  };

  const statusColor = loading ? 'status-dot--running' : error ? 'status-dot--error' : 'status-dot--active';
  const statusLabel = loading ? (compiling ? 'Compiling' : 'Running') : error ? 'Error' : 'Ready';
  const completedStages = PIPELINE_STAGES.filter((stage) => pipelineStages[stage] === 'completed').length;
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
          <button type="button" className="skill-trigger" onClick={() => setKnowledgeOpen(true)}>
            <BookOpen size={15} aria-hidden="true" /> Knowledge
          </button>
          <button type="button" className="skill-trigger" onClick={() => setGrowthOpen(true)}>
            <Sprout size={15} aria-hidden="true" /> Growth
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
              {(['auto', 'analyze', 'compile', 'board'] as Mode[]).map((nextMode) => (
                <button
                  key={nextMode}
                  type="button"
                  role="radio"
                  aria-checked={mode === nextMode}
                  onClick={() => setMode(nextMode)}
                  className={mode === nextMode ? 'is-selected' : ''}
                >
                  <span>{nextMode === 'compile' ? <Workflow size={15} /> : nextMode === 'board' ? <Sparkles size={15} /> : <FileCode2 size={15} />}</span>
                  <span><strong>{nextMode === 'auto' && detectedMode ? `Auto: ${MODE_LABELS[detectedMode]}` : MODE_LABELS[nextMode]}</strong><small>{nextMode === 'compile' ? 'Durable multi-stage run' : nextMode === 'board' ? 'Multi-agent verdict' : nextMode === 'analyze' ? 'Focused capability run' : 'Choose from input'}</small></span>
                </button>
              ))}
            </div>
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
          </section>

          <section className="rail-section rail-stages">
            <div className="rail-section__heading"><p className="rail-label">{effectiveMode === 'compile' ? 'PIPELINE' : 'CAPABILITY PLAN'}</p><span>{completedStages}/{PIPELINE_STAGES.length}</span></div>
            <ol>
              {PIPELINE_STAGES.map((stage) => {
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
            <section className="artifact-preview"><div className="panel-heading"><div><p>IN-FLIGHT ARTIFACTS</p><h2>Streaming work products</h2></div></div>{businessModel && Object.keys(businessModel).length > 0 && <BusinessGraph model={businessModel} />}{sop && Object.keys(sop).length > 0 && <SopPanel sop={sop} />}</section>
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
          {!loading && !error && !dashData && <div className="inspector-empty"><div><FileCode2 size={25} aria-hidden="true" /></div><h3>Output with evidence.</h3><p>{effectiveMode === 'compile' ? 'The inspector will collect the decision gate, risk coverage, graph and SOP produced by this run.' : 'Analysis results, coverage evidence and multi-agent decisions will be collected here.'}</p></div>}
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

      <footer className="studio-footer"><span>{mode === 'auto' && detectedMode ? `Auto -> ${MODE_LABELS[detectedMode]}` : MODE_LABELS[effectiveMode]}</span><span>Session: {sessionDisplay}</span>{compiling && <span className="is-live">pipeline active</span>}{dashData && <span>coverage: {dashData.risk.coverage.coverage_pct}%</span>}<span className="studio-footer__right">BSC Studio 5.0</span></footer>
      {skillsOpen && <SkillMarket onClose={() => setSkillsOpen(false)} context={input || workspaceIdea} />}
      {knowledgeOpen && <KnowledgeWorkspace onClose={() => setKnowledgeOpen(false)} />}
      {growthOpen && <Suspense fallback={<section className="growth-workspace" aria-label="Knowledge growth workspace"><div className="growth-state" role="status">Loading growth workspace...</div></section>}><GrowthWorkspace onClose={() => setGrowthOpen(false)} /></Suspense>}
    </div>
  );
}
